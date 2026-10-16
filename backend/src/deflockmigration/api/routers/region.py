from __future__ import annotations

from fastapi import APIRouter, Request

from deflockmigration.api.schemas import DISCLAIMER, ProfileOut, RegionResponse
from deflockmigration.domain.routes import CameraScope

router = APIRouter(tags=["region"])

ATTRIBUTIONS = [
    "Camera records and road data © OpenStreetMap contributors, Open Database License (https://www.openstreetmap.org/copyright)",
    "Basemap: Protomaps © OpenStreetMap",
    "Boundary: City and County of Denver Open Data (provided as is; not for engineering purposes)",
]


@router.get("/region", response_model=RegionResponse)
def get_region(request: Request) -> RegionResponse:
    config = request.app.state.config
    region = config.region
    providers = config.providers
    boundary = config.service_boundary
    envelope = config.envelope
    return RegionResponse(
        region_id=region.region_id,
        display_name=region.display_name,
        config_version=region.config_version,
        service_boundary={
            "id": boundary.boundary_id,
            "geometry": boundary.geojson_geometry(),
            "bbox_wsen": list(boundary.bbox_wsen),
            "source": region.service_boundary.source,
            "retrieved_at": region.service_boundary.retrieved_at,
        },
        camera_data_envelope={
            "id": envelope.boundary_id,
            "bbox_wsen": list(envelope.bbox_wsen),
            "buffer_m": region.camera_data_envelope.buffer_m,
            "meaning": "Area within which camera records of a snapshot are assessed; not a claim of camera coverage.",
        },
        routing_graph={
            "id": region.routing_graph.id,
            "extract_data_timestamp": region.routing_graph.extract_data_timestamp,
            "engine_image": region.routing_graph.engine_image,
        },
        basemap={
            "path": providers.basemap.path,
            "fonts_path": providers.basemap.fonts_path,
            "sprite_path": providers.basemap.sprite_path,
            "attribution": providers.basemap.attribution,
            "bbox_wsen": region.basemap.bbox_wsen,
            "max_zoom": region.basemap.max_zoom,
        },
        capabilities={
            "geocoder_configured": request.app.state.geocoder.name != "none",
            "geocoder_provider": request.app.state.geocoder.name,
            "routing_provider": providers.routing.provider,
            "camera_source_adapter": providers.camera_source.adapter,
            "camera_assessment": "not_implemented_in_m1",
            "coordinate_input": True,
            "map_pins": True,
        },
        profiles={name: ProfileOut(label=p.label, description=p.description, max_extra_seconds=p.max_extra_seconds, max_relative_factor=p.max_relative_factor) for name, p in config.route_profiles.profiles.items()},
        camera_scopes=[scope.value for scope in CameraScope],
        attributions=ATTRIBUTIONS,
        disclaimer=DISCLAIMER,
    )
