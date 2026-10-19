"""Snapshot validation rules (roadmap section 8, step 7). Pure functions so they are unit-testable."""

from __future__ import annotations

from dataclasses import dataclass

from deflockmigration.core.config_loader import SnapshotValidationConfig


@dataclass(frozen=True)
class QualityVerdict:
    quarantine_reason: str | None
    report: dict

    @property
    def publishable(self) -> bool:
        return self.quarantine_reason is None


def evaluate_snapshot(element_count: int, alpr_count: int, previous_alpr_count: int | None, config: SnapshotValidationConfig) -> QualityVerdict:
    """Decide whether a fetched snapshot may be published automatically.

    An empty or near-empty result and a large drop versus the active snapshot are treated as
    suspicious and quarantined for operator review; they never silently become "zero cameras".
    """
    report: dict = {"element_count": element_count, "alpr_count": alpr_count, "previous_alpr_count": previous_alpr_count}
    if element_count < config.min_element_count:
        reason = f"element count {element_count} below minimum {config.min_element_count}"
        report["quarantine_reason"] = reason
        return QualityVerdict(reason, report)
    if previous_alpr_count:
        drop = 1.0 - (alpr_count / previous_alpr_count)
        report["alpr_drop_fraction_vs_previous"] = round(drop, 4)
        if drop > config.max_count_drop_fraction:
            reason = f"ALPR count dropped by {drop:.0%} versus the active snapshot (limit {config.max_count_drop_fraction:.0%})"
            report["quarantine_reason"] = reason
            return QualityVerdict(reason, report)
    return QualityVerdict(None, report)
