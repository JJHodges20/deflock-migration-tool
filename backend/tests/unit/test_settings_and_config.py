from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from deflockmigration.core.config_loader import ConfigError, load_app_config
from deflockmigration.core.settings import Settings


def test_settings_from_environment(monkeypatch):
    monkeypatch.setenv("DEFLOCK_APP_ENV", "production")
    monkeypatch.setenv("DEFLOCK_LOG_LEVEL", "warning")
    monkeypatch.setenv("DEFLOCK_VALHALLA_URL", "http://router:8002")
    s = Settings()
    assert s.app_env == "production" and s.log_level == "WARNING" and s.valhalla_url == "http://router:8002"
    assert s.resolve(Path("configs/x.yaml")) == Path("/app/configs/x.yaml")


def test_settings_reject_unknown_env(monkeypatch):
    monkeypatch.setenv("DEFLOCK_APP_ENV", "staging")
    with pytest.raises(ValueError):
        Settings()


def test_repo_config_loads(app_config):
    assert app_config.region.region_id == "denver"
    assert app_config.region.service_boundary.id == app_config.service_boundary.boundary_id == "denver-service-v1"
    assert app_config.envelope.boundary_id == "denver-envelope-v1-20km"
    assert "standard" in app_config.route_profiles.profiles
    assert app_config.providers.geocoding.provider == "nominatim_local"
    assert "[bbox:" in app_config.camera_query_text
    assert all(v is False for v in app_config.privacy.model_dump().values())


def test_privacy_flag_true_refused_in_production(project_root, tmp_path):
    root = tmp_path / "root"
    shutil.copytree(project_root / "configs", root / "configs")
    shutil.copytree(project_root / "data" / "boundaries", root / "data" / "boundaries")
    (root / "data" / "raw" / "overpass").mkdir(parents=True)
    shutil.copy(project_root / "data" / "raw" / "overpass" / "denver_alpr_envelope_query.overpassql", root / "data" / "raw" / "overpass")
    privacy = root / "configs" / "privacy.yaml"
    privacy.write_text(privacy.read_text(encoding="utf-8").replace("persist_trips: false", "persist_trips: true"), encoding="utf-8")
    with pytest.raises(ConfigError, match="persist_trips"):
        load_app_config(Settings(app_env="production", project_root=root))
    # The same configuration still loads outside production, but the flag is visible.
    cfg = load_app_config(Settings(app_env="development", project_root=root))
    assert cfg.privacy.persist_trips is True


def test_missing_boundary_file_fails_loudly(project_root, tmp_path):
    root = tmp_path / "root"
    shutil.copytree(project_root / "configs", root / "configs")
    (root / "data" / "boundaries").mkdir(parents=True)
    with pytest.raises(ConfigError, match="not found"):
        load_app_config(Settings(app_env="test", project_root=root))


def test_unknown_config_key_is_rejected(project_root, tmp_path):
    root = tmp_path / "root"
    shutil.copytree(project_root / "configs", root / "configs")
    shutil.copytree(project_root / "data" / "boundaries", root / "data" / "boundaries")
    (root / "data" / "raw" / "overpass").mkdir(parents=True)
    shutil.copy(project_root / "data" / "raw" / "overpass" / "denver_alpr_envelope_query.overpassql", root / "data" / "raw" / "overpass")
    providers = root / "configs" / "providers.yaml"
    providers.write_text(providers.read_text(encoding="utf-8") + "\nunexpected_key: 1\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="unexpected_key"):
        load_app_config(Settings(app_env="test", project_root=root))
