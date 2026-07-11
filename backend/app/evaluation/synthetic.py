from __future__ import annotations

import csv
import hashlib
import json
import math
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DATASET_VERSION = "phase3-synthetic-v1"
DEFAULT_SEED = 20260711
PROVIDERS = ("bKash", "Nagad", "Rocket")
AREAS = ("Zindabazar", "Amberkhana", "Mirabazar", "Subidbazar", "Shibgonj", "Uposhohor")


@dataclass(frozen=True)
class SyntheticConfig:
    agents: int = 18
    days: int = 21
    interval_minutes: int = 60
    seed: int = DEFAULT_SEED
    start_at: datetime = datetime(2026, 5, 1, tzinfo=timezone.utc)


def _round_money(value: float) -> int:
    return max(0, int(round(value / 10.0) * 10))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _split_name(index: int, total: int) -> str:
    fraction = index / max(total - 1, 1)
    if fraction < 0.70:
        return "train"
    if fraction < 0.85:
        return "validation"
    return "test"


def generate_dataset(output_dir: Path, config: SyntheticConfig | None = None) -> dict[str, Any]:
    config = config or SyntheticConfig()
    rng = random.Random(config.seed)
    output_dir.mkdir(parents=True, exist_ok=True)

    steps_per_day = int(24 * 60 / config.interval_minutes)
    total_steps = config.days * steps_per_day
    end_at = config.start_at + timedelta(minutes=config.interval_minutes * (total_steps - 1))

    agent_rows: list[dict[str, Any]] = []
    provider_rows: list[dict[str, Any]] = []

    shortage_windows: dict[str, set[int]] = defaultdict(set)
    burst_windows: dict[tuple[str, str], set[int]] = defaultdict(set)
    conflict_windows: dict[tuple[str, str], set[int]] = defaultdict(set)
    missing_windows: dict[tuple[str, str], set[int]] = defaultdict(set)

    agent_ids = [f"AGT-SYL-{index:03d}" for index in range(1, config.agents + 1)]

    for agent_index, agent_id in enumerate(agent_ids):
        # Structured injections guarantee enough positive examples in every time split.
        for day in (3, 8, 13, 18):
            base = day * steps_per_day + (12 + (agent_index % 4))
            for offset in range(4):
                if base + offset < total_steps:
                    shortage_windows[agent_id].add(base + offset)

        for provider_index, provider in enumerate(PROVIDERS):
            for day in (4 + provider_index, 10 + provider_index, 16 + provider_index):
                base = day * steps_per_day + (14 + agent_index % 3)
                for offset in range(3):
                    if base + offset < total_steps:
                        burst_windows[(agent_id, provider)].add(base + offset)

            for day in (6 + provider_index, 15 + provider_index):
                base = day * steps_per_day + (9 + agent_index % 5)
                for offset in range(2):
                    if base + offset < total_steps:
                        conflict_windows[(agent_id, provider)].add(base + offset)

            day = 12 + provider_index
            base = day * steps_per_day + (4 + agent_index % 4)
            if base < total_steps:
                missing_windows[(agent_id, provider)].add(base)

    for agent_index, agent_id in enumerate(agent_ids):
        area = AREAS[agent_index % len(AREAS)]
        shared_threshold = 28000 + (agent_index % 4) * 3000
        shared_cash = 210000 + agent_index * 4500 + rng.randint(-12000, 12000)
        provider_balance = {
            provider: 90000 + rng.randint(-12000, 18000) + provider_index * 9000
            for provider_index, provider in enumerate(PROVIDERS)
        }
        provider_threshold = {
            provider: 15000 + provider_index * 2000
            for provider_index, provider in enumerate(PROVIDERS)
        }

        for step in range(total_steps):
            timestamp = config.start_at + timedelta(minutes=config.interval_minutes * step)
            local_hour = (timestamp.hour + 6) % 24
            day_index = step // steps_per_day
            weekday = timestamp.weekday()
            split = _split_name(step, total_steps)

            if 8 <= local_hour <= 21:
                hour_factor = 1.0 + 0.55 * math.sin((local_hour - 8) / 13 * math.pi)
            else:
                hour_factor = 0.18

            payday_factor = 1.35 if day_index in {0, 1, 14, 15} else 1.0
            weekend_factor = 1.18 if weekday in {4, 5} else 1.0
            festival_factor = 1.45 if 17 <= day_index <= 20 else 1.0
            demand_factor = hour_factor * payday_factor * weekend_factor * festival_factor

            total_cash_in = 0
            total_cash_out = 0
            context_parts: list[str] = []
            if payday_factor > 1:
                context_parts.append("payday")
            if weekend_factor > 1:
                context_parts.append("weekend")
            if festival_factor > 1:
                context_parts.append("festival_demand")
            if not context_parts:
                context_parts.append("routine")

            current_provider_rows: list[dict[str, Any]] = []

            for provider_index, provider in enumerate(PROVIDERS):
                provider_weight = (1.00, 0.82, 0.58)[provider_index]
                base_volume = (5600 + agent_index * 90) * provider_weight * demand_factor
                noise_in = rng.gauss(1.0, 0.16)
                noise_out = rng.gauss(1.0, 0.17)

                cash_in = max(0.0, base_volume * 0.93 * noise_in)
                cash_out = max(0.0, base_volume * 1.02 * noise_out)
                anomaly_type = "none"
                is_anomaly = 0

                if step in burst_windows[(agent_id, provider)]:
                    cash_out += 30000 + 4500 * provider_index + rng.randint(0, 8000)
                    anomaly_type = "cashout_burst"
                    is_anomaly = 1

                if step in shortage_windows[agent_id]:
                    cash_out += 19000 + provider_index * 3500 + rng.randint(0, 4500)
                    if anomaly_type == "none":
                        anomaly_type = "liquidity_pressure"
                        is_anomaly = 1

                feed_status = "fresh"
                feed_age_minutes = rng.randint(1, 8)
                data_quality_issue = 0

                if step in conflict_windows[(agent_id, provider)]:
                    feed_status = "conflicting"
                    feed_age_minutes = rng.randint(18, 45)
                    anomaly_type = "feed_conflict"
                    is_anomaly = 1
                    data_quality_issue = 1
                elif step in missing_windows[(agent_id, provider)]:
                    feed_status = "missing"
                    feed_age_minutes = rng.randint(60, 180)
                    anomaly_type = "feed_missing"
                    is_anomaly = 1
                    data_quality_issue = 1
                elif rng.random() < 0.006:
                    feed_status = "delayed"
                    feed_age_minutes = rng.randint(20, 55)
                    anomaly_type = "feed_delay"
                    is_anomaly = 1
                    data_quality_issue = 1

                cash_in = _round_money(cash_in)
                cash_out = _round_money(cash_out)

                e_money_before = provider_balance[provider]
                # Cash-in consumes provider e-money; cash-out replenishes it.
                e_money_after = e_money_before - cash_in + cash_out
                authorized_topup = 0
                if e_money_after < provider_threshold[provider] and local_hour in {7, 8, 9}:
                    authorized_topup = 75000
                    e_money_after += authorized_topup
                provider_balance[provider] = max(0, e_money_after)

                total_cash_in += cash_in
                total_cash_out += cash_out

                current_provider_rows.append(
                    {
                        "timestamp": timestamp.isoformat(),
                        "split": split,
                        "agent_id": agent_id,
                        "area": area,
                        "provider": provider,
                        "cash_in_bdt": cash_in,
                        "cash_out_bdt": cash_out,
                        "provider_emoney_before_bdt": _round_money(e_money_before),
                        "provider_emoney_after_bdt": _round_money(provider_balance[provider]),
                        "provider_safe_threshold_bdt": provider_threshold[provider],
                        "authorized_topup_bdt": authorized_topup,
                        "feed_status": feed_status,
                        "feed_age_minutes": feed_age_minutes,
                        "ground_truth_anomaly": is_anomaly,
                        "ground_truth_anomaly_type": anomaly_type,
                        "ground_truth_data_quality_issue": data_quality_issue,
                        "event_context": "+".join(context_parts),
                    }
                )

            shared_cash_before = shared_cash
            authorized_cash_support = 0
            shared_cash = shared_cash + total_cash_in - total_cash_out

            # Authorized support is delayed intentionally, allowing real shortage labels.
            if shared_cash < 12000 and local_hour in {8, 9, 10, 16}:
                authorized_cash_support = 165000
                shared_cash += authorized_cash_support

            shared_cash = max(0, shared_cash)
            net_cash_change = shared_cash - shared_cash_before - authorized_cash_support

            agent_rows.append(
                {
                    "timestamp": timestamp.isoformat(),
                    "split": split,
                    "agent_id": agent_id,
                    "area": area,
                    "shared_cash_before_bdt": _round_money(shared_cash_before),
                    "shared_cash_after_bdt": _round_money(shared_cash),
                    "shared_cash_safe_threshold_bdt": shared_threshold,
                    "total_cash_in_bdt": _round_money(total_cash_in),
                    "total_cash_out_bdt": _round_money(total_cash_out),
                    "net_cash_change_bdt": _round_money(net_cash_change),
                    "authorized_cash_support_bdt": authorized_cash_support,
                    "event_context": "+".join(context_parts),
                    "ground_truth_shortage_within_6h": 0,
                    "ground_truth_shortage_minutes": "",
                    "next_shared_cash_bdt": "",
                }
            )

            for row in current_provider_rows:
                row["shared_cash_after_bdt"] = _round_money(shared_cash)
                row["shared_cash_safe_threshold_bdt"] = shared_threshold
                provider_rows.append(row)

    rows_by_agent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in agent_rows:
        rows_by_agent[row["agent_id"]].append(row)

    horizon_steps = int(6 * 60 / config.interval_minutes)
    for rows in rows_by_agent.values():
        for index, row in enumerate(rows):
            if index + 1 < len(rows):
                row["next_shared_cash_bdt"] = rows[index + 1]["shared_cash_after_bdt"]
            future = rows[index + 1 : index + horizon_steps + 1]
            first_shortage_offset = None
            threshold = int(row["shared_cash_safe_threshold_bdt"])
            for offset, future_row in enumerate(future, start=1):
                if int(future_row["shared_cash_after_bdt"]) < threshold:
                    first_shortage_offset = offset
                    break
            if first_shortage_offset is not None:
                row["ground_truth_shortage_within_6h"] = 1
                row["ground_truth_shortage_minutes"] = first_shortage_offset * config.interval_minutes

    agent_path = output_dir / "agent_hourly.csv"
    provider_path = output_dir / "provider_hourly.csv"
    manifest_path = output_dir / "manifest.json"

    def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    write_csv(agent_path, agent_rows)
    write_csv(provider_path, provider_rows)

    shortage_positive_rows = sum(int(row["ground_truth_shortage_within_6h"]) for row in agent_rows)
    anomaly_positive_rows = sum(int(row["ground_truth_anomaly"]) for row in provider_rows)
    data_quality_positive_rows = sum(int(row["ground_truth_data_quality_issue"]) for row in provider_rows)

    manifest = {
        "dataset_version": DATASET_VERSION,
        "seed": config.seed,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "agents": config.agents,
        "providers": list(PROVIDERS),
        "areas": list(AREAS),
        "start_at": config.start_at.isoformat(),
        "end_at": end_at.isoformat(),
        "interval_minutes": config.interval_minutes,
        "agent_rows": len(agent_rows),
        "provider_rows": len(provider_rows),
        "shortage_positive_rows": shortage_positive_rows,
        "anomaly_positive_rows": anomaly_positive_rows,
        "data_quality_positive_rows": data_quality_positive_rows,
        "files": [
            {
                "path": f"data/synthetic/{agent_path.name}",
                "rows": len(agent_rows),
                "sha256": _sha256(agent_path),
            },
            {
                "path": f"data/synthetic/{provider_path.name}",
                "rows": len(provider_rows),
                "sha256": _sha256(provider_path),
            },
        ],
        "assumptions": [
            "One shared physical-cash pool is modelled per outlet.",
            "Provider e-money balances remain separate and are never converted across providers.",
            "Cash-in increases physical cash and consumes the selected provider's e-money.",
            "Cash-out decreases physical cash and replenishes the selected provider's e-money.",
            "All names, balances, events and labels are synthetic and reproducible from the seed.",
        ],
        "limitations": [
            "Synthetic behaviour cannot prove production accuracy on real provider traffic.",
            "Injected events are simplified and may be easier to detect than real-world anomalies.",
            "Regulatory, settlement and real-provider integration are outside this prototype.",
        ],
    }

    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    return manifest
