"""Snapshot-to-snapshot differences in terms of source keys and versions. Pure, unit-tested.

Vocabulary (roadmap section 8): "added" = newly mapped record, "changed" = same key with a new
source version, "missing" = present before and absent now ("no longer mapped", never "removed"),
"reappeared" = a previously missing key that is present again, "still missing" = absent again.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SnapshotDiffResult:
    added_keys: list[str] = field(default_factory=list)
    changed: list[dict] = field(default_factory=list)  # {"key", "from_version", "to_version"}
    missing_keys: list[str] = field(default_factory=list)
    reappeared_keys: list[str] = field(default_factory=list)
    still_missing_keys: list[str] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        return {
            "added": len(self.added_keys),
            "changed": len(self.changed),
            "missing": len(self.missing_keys),
            "reappeared": len(self.reappeared_keys),
            "still_missing": len(self.still_missing_keys),
        }


def compute_diff(previous_present: dict[str, int | None], previous_carried: set[str], current: dict[str, int | None]) -> SnapshotDiffResult:
    """previous_present: keys that were present in the source in the previous snapshot (key -> version).
    previous_carried: keys that the previous snapshot carried as no-longer-mapped.
    current: keys present in the new fetch (key -> version)."""
    added = sorted(k for k in current if k not in previous_present and k not in previous_carried)
    reappeared = sorted(k for k in current if k in previous_carried)
    changed = [
        {"key": k, "from_version": previous_present[k], "to_version": current[k]}
        for k in sorted(current)
        if k in previous_present and previous_present[k] != current[k]
    ]
    missing = sorted(k for k in previous_present if k not in current)
    still_missing = sorted(k for k in previous_carried if k not in current)
    return SnapshotDiffResult(added, changed, missing, reappeared, still_missing)
