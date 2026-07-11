import pytest
from fastapi import HTTPException

from app.security import (
    AuthenticatedUser,
    UserRole,
    authenticate_user,
    create_access_token,
    decode_access_token,
    require_roles,
)


def test_demo_login_accepts_valid_user() -> None:
    user = authenticate_user("operator@sentinel.local", "operator-demo-pass")

    assert user is not None
    assert user.role == UserRole.outlet_operator
    assert user.username == "operator@sentinel.local"


def test_demo_login_rejects_wrong_password() -> None:
    user = authenticate_user("operator@sentinel.local", "wrong-password")

    assert user is None


def test_demo_login_rejects_unknown_user() -> None:
    user = authenticate_user("missing@sentinel.local", "operator-demo-pass")

    assert user is None


def test_token_round_trip_preserves_user_claims() -> None:
    user = authenticate_user("manager@sentinel.local", "manager-demo-pass")
    assert user is not None

    token, expires_at = create_access_token(user)
    decoded = decode_access_token(token)

    assert token
    assert expires_at.tzinfo is not None
    assert decoded.username == user.username
    assert decoded.role == UserRole.area_manager
    assert decoded.outlet_ids == user.outlet_ids


@pytest.mark.asyncio
async def test_role_dependency_allows_matching_role() -> None:
    dependency = require_roles(UserRole.area_manager)
    user = AuthenticatedUser(
        username="manager@sentinel.local",
        display_name="Demo Area Manager",
        role=UserRole.area_manager,
        outlet_ids=["AGT-SYL-017"],
    )

    assert await dependency(user) == user


@pytest.mark.asyncio
async def test_role_dependency_allows_admin_override() -> None:
    dependency = require_roles(UserRole.area_manager)
    user = AuthenticatedUser(
        username="admin@sentinel.local",
        display_name="Demo Admin",
        role=UserRole.admin,
        outlet_ids=["*"],
    )

    assert await dependency(user) == user


@pytest.mark.asyncio
async def test_role_dependency_rejects_unauthorized_role() -> None:
    dependency = require_roles(UserRole.area_manager)
    user = AuthenticatedUser(
        username="operator@sentinel.local",
        display_name="Demo Outlet Operator",
        role=UserRole.outlet_operator,
        outlet_ids=["AGT-SYL-017"],
    )

    with pytest.raises(HTTPException) as exc:
        await dependency(user)

    assert exc.value.status_code == 403
