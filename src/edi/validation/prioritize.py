"""Exception prioritization. Ranking is transparent: the default key is the expected benefit of acting
now net of investigation cost; every component stays visible so users can re-sort."""

from __future__ import annotations

from typing import Any


def prioritize(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each item needs: cost_of_inaction, investigation_cost, days_of_cover, downside, feasible."""
    for it in items:
        it["net_benefit"] = float(it["cost_of_inaction"]) - float(it.get("investigation_cost", 0.0))
        it["urgency"] = (
            "today" if it["days_of_cover"] < 1 else ("this week" if it["days_of_cover"] < 3 else "monitor")
        )
    ranked = sorted(items, key=lambda x: (not x.get("feasible", True), -x["net_benefit"], x["days_of_cover"]))
    for i, it in enumerate(ranked, 1):
        it["rank"] = i
    return ranked
