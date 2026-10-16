from __future__ import annotations

import logging

from deflockmigration.core.logging import RedactionFilter, configure_logging, redact


def test_redact_masks_coordinates_and_keys():
    assert "39.7530" not in redact("origin 39.7530, -105.0002 to 39.7503,-104.9500")
    assert redact("lat=39.7530&lon=-105.0002") == "lat=[redacted]&lon=[redacted]"
    assert "39.4341" not in redact("bbox=-105.34,39.4341,-104.36,40.09")
    assert redact("GET /api/v1/cameras?bbox=1,2,3,4") == "GET /api/v1/cameras?[redacted]"
    assert "Wynkoop" not in redact('{"q": "1701 Wynkoop St"}')
    assert redact("plain 12 ms, status 200") == "plain 12 ms, status 200"


def test_filter_rewrites_records(caplog):
    logger = logging.getLogger("deflockmigration.test")
    logger.addFilter(RedactionFilter())
    with caplog.at_level(logging.INFO, logger="deflockmigration.test"):
        logger.info("trip from %s", "39.7530, -105.0002")
    assert "39.7530" not in caplog.text and "[redacted]" in caplog.text
    logger.removeFilter(RedactionFilter())


def test_configure_logging_disables_access_log_and_filters_root(capsys):
    configure_logging("INFO")
    assert logging.getLogger("uvicorn.access").disabled is True
    root = logging.getLogger()
    assert any(isinstance(f, RedactionFilter) for h in root.handlers for f in h.filters)
    logging.getLogger("something").warning("lat=39.75 lon=-104.99")
    assert "39.75" not in capsys.readouterr().out


def test_plan_request_leaves_no_coordinates_in_logs(client, caplog):
    with caplog.at_level(logging.DEBUG):
        resp = client.post("/api/v1/routes/plan", json={"origin": {"lat": 39.7530, "lon": -105.0002}, "destination": {"lat": 39.7503, "lon": -104.9500}})
        assert resp.status_code == 200
    for value in ("39.753", "-105.0002", "39.7503", "-104.95"):
        assert value not in caplog.text
    assert "POST /api/v1/routes/plan -> 200" in caplog.text
