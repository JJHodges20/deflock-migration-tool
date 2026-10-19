"""Cache of nearest-road candidates per camera record and routing-graph version."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from deflockmigration.domain.assessment import RoadCandidate, is_ambiguous
from deflockmigration.storage.models import CameraRoadAssociation

METHOD = "valhalla_locate_nearest_way"


def _to_json(c: RoadCandidate) -> dict:
    return {"way_id": c.way_id, "names": c.names, "distance_m": c.distance_m, "road_class": c.road_class, "use": c.use, "bridge": c.bridge, "tunnel": c.tunnel, "correlated_lat": c.correlated_lat, "correlated_lon": c.correlated_lon, "side_of_street": c.side_of_street}


def _from_json(d: dict) -> RoadCandidate:
    return RoadCandidate(int(d["way_id"]), list(d.get("names") or []), float(d["distance_m"]), d.get("road_class"), d.get("use"), bool(d.get("bridge")), bool(d.get("tunnel")), d.get("correlated_lat"), d.get("correlated_lon"), d.get("side_of_street"))


class AssociationCache:
    def __init__(self, session: Session):
        self.s = session

    def get_many(self, source_keys: list[str], graph_version: str, radius_m: int) -> dict[str, list[RoadCandidate]]:
        if not source_keys:
            return {}
        stmt = select(CameraRoadAssociation).where(
            CameraRoadAssociation.graph_version == graph_version,
            CameraRoadAssociation.radius_m == radius_m,
            CameraRoadAssociation.source_key.in_(source_keys),
        )
        return {row.source_key: [_from_json(c) for c in row.candidates] for row in self.s.execute(stmt).scalars().all()}

    def put(self, source_key: str, graph_version: str, radius_m: int, candidates: list[RoadCandidate], now: dt.datetime) -> None:
        nearest = candidates[0] if candidates else None
        self.s.execute(delete(CameraRoadAssociation).where(
            CameraRoadAssociation.source_key == source_key, CameraRoadAssociation.graph_version == graph_version, CameraRoadAssociation.radius_m == radius_m,
        ))
        self.s.add(CameraRoadAssociation(
            source_key=source_key, graph_version=graph_version, radius_m=radius_m, method=METHOD, computed_at=now,
            nearest_way_id=nearest.way_id if nearest else None, nearest_road_names=nearest.names if nearest else [],
            nearest_distance_m=nearest.distance_m if nearest else None, candidate_count=len(candidates),
            ambiguous=is_ambiguous(candidates), candidates=[_to_json(c) for c in candidates],
        ))

    def count_for(self, graph_version: str, radius_m: int) -> int:
        stmt = select(CameraRoadAssociation.id).where(CameraRoadAssociation.graph_version == graph_version, CameraRoadAssociation.radius_m == radius_m)
        return len(self.s.execute(stmt).all())

    def clear_for(self, graph_version: str, radius_m: int) -> int:
        """Drop the rows of one graph version and radius so they can be recomputed (after a method change)."""
        result = self.s.execute(delete(CameraRoadAssociation).where(CameraRoadAssociation.graph_version == graph_version, CameraRoadAssociation.radius_m == radius_m))
        return int(result.rowcount or 0)

    def prune_other_graphs(self, keep_graph_version: str) -> int:
        result = self.s.execute(delete(CameraRoadAssociation).where(CameraRoadAssociation.graph_version != keep_graph_version))
        return int(result.rowcount or 0)
