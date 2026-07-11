import asyncio
from collections import Counter
from collections.abc import Awaitable, Callable
from math import ceil
from typing import TypedDict

from app.config import get_settings
from app.schemas import (
    AnalysisEvent,
    AnalysisRequest,
    AnalysisResult,
    Classification,
    ConfidenceAdjustment,
    EventStatus,
    Language,
    Recommendation,
    Scenario,
)

settings = get_settings()
EmitEvent = Callable[[AnalysisEvent], Awaitable[None]]


class Transaction(TypedDict):
    transaction_id: str
    provider: str
    transaction_type: str
    amount: float
    minutes_ago: int
    status: str


def build_transactions(
    scenario: Scenario,
) -> tuple[list[Transaction], float, float, int, int, str | None]:
    if scenario == Scenario.normal_day:
        transactions: list[Transaction] = []
        for index in range(24):
            transactions.append(
                {
                    "transaction_id": f"NORMAL-{index:03d}",
                    "provider": ["bKash", "Nagad", "Rocket"][index % 3],
                    "transaction_type": "cash_out" if index % 2 == 0 else "cash_in",
                    "amount": float(2500 + (index % 4) * 500),
                    "minutes_ago": index + 1,
                    "status": "completed",
                }
            )
        return transactions, 245000, 20000, 0, 3, None

    repeated: list[Transaction] = [
        {
            "transaction_id": f"BK-REPEAT-{index:03d}",
            "provider": "bKash",
            "transaction_type": "cash_out",
            "amount": 12000.0,
            "minutes_ago": index + 1,
            "status": "completed",
        }
        for index in range(8)
    ]
    extra_out: list[Transaction] = [
        {
            "transaction_id": f"OUT-{index:03d}",
            "provider": ["bKash", "Nagad", "Rocket", "bKash"][index],
            "transaction_type": "cash_out",
            "amount": 4000.0,
            "minutes_ago": 10 + index,
            "status": "completed",
        }
        for index in range(4)
    ]
    cash_in: list[Transaction] = [
        {
            "transaction_id": f"IN-{index:03d}",
            "provider": ["Nagad", "Rocket", "bKash"][index % 3],
            "transaction_type": "cash_in",
            "amount": 5000.0 if index < 4 else 7000.0,
            "minutes_ago": 15 + index,
            "status": "completed",
        }
        for index in range(6)
    ]
    conflicts = 4 if scenario == Scenario.data_conflict else 2
    age = 47 if scenario == Scenario.data_conflict else 9
    return repeated + extra_out + cash_in, 155000, 20000, conflicts, age, "pre_eid_demand"


def build_summary(
    language: Language,
    classification: Classification,
    eta: int | None,
    confidence: float,
) -> str:
    percent = round(confidence * 100)
    if classification == Classification.normal_operational_spike:
        if language == Language.bangla:
            return f"বর্তমান ডেটায় কার্যক্রম নিরাপদ সীমার মধ্যে আছে। বিশ্বাসযোগ্যতা {percent}%। পর্যবেক্ষণ চালিয়ে যাওয়া উচিত।"
        if language == Language.banglish:
            return f"Current data-te operation safe threshold-er moddhe ache. Confidence {percent}%. Monitoring continue kora uchit."
        return f"Current operations remain within the safe threshold. Confidence is {percent}%. Continued monitoring is recommended."

    if classification == Classification.data_quality_issue:
        if language == Language.bangla:
            return f"প্রোভাইডার ডেটায় বিলম্ব ও অসঙ্গতি পাওয়া গেছে। বিশ্বাসযোগ্যতা {percent}% এ কমানো হয়েছে। আগে ডেটা যাচাই প্রয়োজন।"
        if language == Language.banglish:
            return f"Provider data-te delay ebong conflict detect hoyeche. Confidence {percent}% e reduce kora hoyeche. Provider feed verify kora proyojon."
        return f"Delayed and conflicting provider data was detected. Confidence was reduced to {percent}%. Verify the provider feed first."

    eta_text = str(eta) if eta is not None else "unknown"
    if language == Language.bangla:
        return f"শেয়ার্ড ক্যাশে চাপ শনাক্ত হয়েছে। প্রায় {eta_text} মিনিটের মধ্যে নিরাপদ সীমার নিচে যেতে পারে। বিশ্বাসযোগ্যতা {percent}%। এটি জালিয়াতির সিদ্ধান্ত নয়; মানব পর্যালোচনা প্রয়োজন।"
    if language == Language.banglish:
        return f"Shared cash pressure detect hoyeche. Approximately {eta_text} minute-er moddhe safe threshold-er niche jete pare. Confidence {percent}%. Eta fraud verdict na; human review proyojon."
    return f"Shared-cash pressure was detected. The balance may cross the safe threshold in approximately {eta_text} minutes. Confidence is {percent}%. This is not a fraud verdict."


async def run_analysis(
    analysis_id: str,
    payload: AnalysisRequest,
    emit: EmitEvent,
) -> AnalysisResult:
    sequence = 0
    delay = settings.analysis_stage_delay_ms / 1000

    async def publish(
        stage: str,
        label: str,
        event_status: EventStatus,
        detail: str | None = None,
        metric: int | float | str | None = None,
    ) -> None:
        nonlocal sequence
        sequence += 1
        await emit(
            AnalysisEvent(
                sequence=sequence,
                stage=stage,
                label=label,
                status=event_status,
                detail=detail,
                metric=metric,
            )
        )
        if delay > 0:
            await asyncio.sleep(delay)

    transactions, shared_cash, threshold, conflicts, feed_age, event_context = (
        build_transactions(payload.scenario)
    )

    await publish(
        "problem_understood",
        "Understood the operational problem",
        EventStatus.completed,
    )
    await publish(
        "checks_created",
        "Created 5 analytical checks",
        EventStatus.completed,
        metric=5,
    )

    valid = [
        tx
        for tx in transactions
        if tx["amount"] > 0
        and tx["transaction_type"] in {"cash_in", "cash_out"}
        and tx["provider"] in {"bKash", "Nagad", "Rocket"}
    ]
    await publish(
        "records_validated",
        f"Checked {len(valid)} transaction records",
        EventStatus.completed,
        metric=len(valid),
    )

    providers = {tx["provider"] for tx in valid}
    await publish(
        "balances_reconciled",
        f"Reconciled {len(providers)} provider balances",
        EventStatus.completed,
        metric=len(providers),
    )

    cash_out_total = sum(
        tx["amount"] for tx in valid if tx["transaction_type"] == "cash_out"
    )
    cash_in_total = sum(
        tx["amount"] for tx in valid if tx["transaction_type"] == "cash_in"
    )
    net_outflow = max((cash_out_total - cash_in_total) / 30, 0)
    eta = ceil((shared_cash - threshold) / net_outflow) if net_outflow > 0 else None
    await publish(
        "liquidity_forecast",
        "Forecasted shared-cash pressure",
        EventStatus.completed,
        metric=eta or "not_reached",
    )

    repeated_groups = Counter(
        (tx["provider"], tx["transaction_type"], tx["amount"])
        for tx in valid
    )
    repeated = max(
        (
            count
            for (provider, tx_type, amount), count in repeated_groups.items()
            if provider == "bKash" and tx_type == "cash_out" and amount >= 10000
        ),
        default=0,
    )
    bkash_out = sum(
        tx["amount"]
        for tx in valid
        if tx["provider"] == "bKash" and tx["transaction_type"] == "cash_out"
    )
    contribution = round((bkash_out / cash_out_total) * 100) if cash_out_total else 0

    if payload.scenario == Scenario.normal_day:
        evidence = [
            "Cash-in and cash-out volumes remained near balance",
            "All provider feeds were fresh",
            "No repeated high-value cluster was detected",
            "Shared cash remained above the safe threshold",
        ]
    else:
        evidence = [
            f"{repeated} repeated high-value bKash cash-outs",
            f"bKash contributed {contribution}% of recent cash-out volume",
            f"Net shared-cash outflow was {round(net_outflow)} BDT per minute",
            f"Current shared cash was {round(shared_cash)} BDT",
            f"Safe threshold was {round(threshold)} BDT",
            f"Provider feed age was {feed_age} minutes",
            "Pre-Eid demand was considered as a possible normal explanation",
        ]

    await publish(
        "evidence_collected",
        f"Found {len(evidence)} supporting claims",
        EventStatus.completed,
        metric=len(evidence),
    )

    if conflicts:
        await publish(
            "data_conflicts",
            f"Found {conflicts} conflicting records",
            EventStatus.warning,
            metric=conflicts,
        )
    else:
        await publish(
            "data_conflicts",
            "No conflicting records found",
            EventStatus.completed,
            metric=0,
        )

    confidence = 0.92
    adjustments: list[ConfidenceAdjustment] = []
    if event_context:
        confidence -= 0.08
        adjustments.append(
            ConfidenceAdjustment(reason="pre_eid_demand_context", impact=-0.08)
        )
    conflict_penalty = min(conflicts * 0.05, 0.25)
    if conflict_penalty:
        confidence -= conflict_penalty
        adjustments.append(
            ConfidenceAdjustment(reason="conflicting_records", impact=-conflict_penalty)
        )
    if feed_age > 30:
        confidence -= 0.12
        adjustments.append(
            ConfidenceAdjustment(reason="delayed_provider_feed", impact=-0.12)
        )
    confidence = round(max(min(confidence, 0.95), 0.20), 2)
    await publish(
        "confidence_calculated",
        f"Calculated confidence at {round(confidence * 100)}%",
        EventStatus.warning if confidence < 0.70 else EventStatus.completed,
        metric=round(confidence * 100),
    )

    if payload.scenario == Scenario.normal_day:
        classification = Classification.normal_operational_spike
        recommendation = Recommendation.monitor_more_frequently
        owner = "Outlet Operations"
        provider = "Multiple providers"
        resource = "shared_cash"
        context = ["Routine operational demand"]
    elif payload.scenario == Scenario.data_conflict:
        classification = Classification.data_quality_issue
        recommendation = Recommendation.verify_provider_feed
        owner = "Provider Operations Data Steward"
        provider = "Nagad"
        resource = "provider_data"
        context = [
            "Delayed provider synchronization",
            "Temporary reporting inconsistency",
        ]
    else:
        classification = Classification.requires_review
        recommendation = Recommendation.request_approved_cash_support
        owner = "bKash Field Officer"
        provider = "bKash"
        resource = "shared_cash"
        context = ["Pre-Eid demand spike", "High legitimate merchant activity"]

    await publish(
        "decision_generated",
        "Generated the safe recommendation",
        EventStatus.completed,
        detail=f"Recommended owner: {owner}. Action: {recommendation.value}.",
    )

    return AnalysisResult(
        analysis_id=analysis_id,
        agent_id=payload.agent_id,
        classification=classification,
        affected_resource=resource,
        affected_provider=provider,
        shortage_eta_minutes=eta,
        confidence=confidence,
        confidence_adjustments=adjustments,
        records_checked=len(valid),
        supporting_claims=len(evidence),
        conflicting_records=conflicts,
        evidence=evidence,
        possible_normal_context=context,
        recommendation=recommendation,
        recommended_owner=owner,
        summary=build_summary(payload.language, classification, eta, confidence),
        safe_boundary=(
            "Advisory decision support only. No transfer, blocking, wallet refill, "
            "accusation or final fraud determination is performed."
        ),
    )
