"""Architecture rules that must not erode: production code never imports tests or fixtures,
inner layers never import outer ones, and dependency pins stay in sync."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "deflockmigration"
BACKEND = Path(__file__).resolve().parents[2]

LAYER_RULES = {
    "domain": {"api", "application", "storage", "routing", "geocoding", "data_sources", "ingestion", "workers"},
    "geospatial": {"api", "application", "storage", "routing", "geocoding", "data_sources", "ingestion", "workers"},
    "routing": {"api", "application", "storage", "ingestion", "workers"},
    "geocoding": {"api", "application", "storage", "ingestion", "workers"},
    "data_sources": {"api", "application", "storage", "ingestion", "workers"},
    "storage": {"api", "application", "workers"},
    "application": {"api", "workers"},
}


def _imports(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return re.findall(r"^\s*(?:from|import)\s+([\w.]+)", text, flags=re.MULTILINE)


def test_production_code_never_imports_tests_or_fixtures():
    for path in SRC.rglob("*.py"):
        for module in _imports(path):
            assert not module.startswith("tests"), f"{path} imports {module}"
        assert "fixture_" not in path.read_text(encoding="utf-8"), f"{path} references a fixture file"


def test_layer_dependencies():
    for layer, forbidden in LAYER_RULES.items():
        for path in (SRC / layer).rglob("*.py"):
            for module in _imports(path):
                if module.startswith("deflockmigration."):
                    target = module.split(".")[1]
                    assert target not in forbidden, f"{layer}/{path.name} imports deflockmigration.{target}"


def test_requirements_match_pyproject():
    pyproject = tomllib.loads((BACKEND / "pyproject.toml").read_text(encoding="utf-8"))
    pins = set(pyproject["project"]["dependencies"]) | set(pyproject["project"]["optional-dependencies"]["dev"])
    requirements = {line.strip() for line in (BACKEND / "requirements.txt").read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")}
    assert pins == requirements


def test_fixture_files_are_labelled():
    fixtures = BACKEND / "tests" / "fixtures"
    for path in fixtures.iterdir():
        assert path.name.startswith("fixture_"), path
