"""Runner guardrails + dispatch, with geospacelab execution mocked out."""

import datetime as dt

import pytest

from gsl_dashboard import bootstrap, runner, settings
from gsl_dashboard.catalog import get_catalog
from gsl_dashboard.runner import RunResult, _precheck, build_and_render
from gsl_dashboard.spec import RequestSpec, RunRequest

CAT = get_catalog()


def _req(pid, hours=1.0, params=None):
    fr = dt.datetime(2016, 1, 2, 0, 0)
    to = fr + dt.timedelta(hours=hours)
    return RunRequest((RequestSpec(pid, params or {}),), fr, to)


def test_precheck_rejects_too_long_span():
    msg = _precheck(_req("swarm.mag_lr", hours=999), CAT)
    assert msg and "exceeds" in msg


def test_precheck_defers_geomap(monkeypatch):
    monkeypatch.setattr(settings, "ENABLE_GEOMAP_PREVIEW", False)
    msg = _precheck(_req("ampere.fitted"), CAT)
    assert msg and "deferred" in msg.lower()


def test_precheck_disables_credentialed_in_docker(monkeypatch):
    monkeypatch.setattr(settings, "MODE", "docker")
    monkeypatch.setattr(runner, "credentials_present", lambda kind: True)
    msg = _precheck(_req("swarm.mag_lr"), CAT)
    assert msg and "disabled" in msg.lower()


def test_precheck_reports_missing_credentials(monkeypatch):
    monkeypatch.setattr(settings, "MODE", "local")
    monkeypatch.setattr(runner, "credentials_present", lambda kind: kind is None)
    msg = _precheck(_req("swarm.mag_lr"), CAT)
    assert msg and "esa_eo" in msg


def test_precheck_passes_for_no_cred_source(monkeypatch):
    monkeypatch.setattr(settings, "MODE", "local")
    assert _precheck(_req("indices.kpap"), CAT) is None


_APEX_SPEC = {"sat_id": "A", "source": "ESA EO", "variant": "OPER", "add_APEX": True}


def test_precheck_rejects_apex_without_apexpy(monkeypatch):
    monkeypatch.setattr(runner, "credentials_present", lambda kind: True)
    monkeypatch.setattr(runner, "apex_available", lambda: False)
    msg = _precheck(_req("swarm.mag_lr", params=_APEX_SPEC), CAT)
    assert msg and "apexpy" in msg


def test_precheck_allows_apex_with_apexpy(monkeypatch):
    monkeypatch.setattr(runner, "credentials_present", lambda kind: True)
    monkeypatch.setattr(runner, "apex_available", lambda: True)
    assert _precheck(_req("swarm.mag_lr", params=_APEX_SPEC), CAT) is None


@pytest.fixture
def _mock_exec(monkeypatch):
    monkeypatch.setattr(bootstrap, "prime_in_memory_config", lambda: None)
    monkeypatch.setattr(runner, "credentials_present", lambda kind: True)
    monkeypatch.setattr(runner, "_run_express", lambda req, cat: RunResult(fig="EXPRESS"))
    monkeypatch.setattr(runner, "_run_datahub", lambda req, cat: RunResult(fig="DATAHUB"))


def test_dispatch_express(_mock_exec):
    res = build_and_render(_req("omni.combined", params={"omni_type": "OMNI2", "omni_res": "1min"}), CAT)
    assert res.fig == "EXPRESS"


def test_dispatch_datahub(_mock_exec):
    res = build_and_render(_req("indices.kpap"), CAT)
    assert res.fig == "DATAHUB"


def test_dispatch_multi_is_datahub(_mock_exec):
    fr = dt.datetime(2016, 1, 2)
    to = fr + dt.timedelta(hours=1)
    req = RunRequest(
        (RequestSpec("omni.combined", {"omni_type": "OMNI2", "omni_res": "1min"}), RequestSpec("indices.ae")),
        fr, to,
    )
    assert build_and_render(req, CAT).fig == "DATAHUB"


def test_empty_request_errors(_mock_exec):
    res = build_and_render(RunRequest((), dt.datetime(2016, 1, 2), dt.datetime(2016, 1, 2, 1)), CAT)
    assert res.error


def test_log_capture(monkeypatch):
    monkeypatch.setattr(bootstrap, "prime_in_memory_config", lambda: None)
    monkeypatch.setattr(runner, "credentials_present", lambda kind: True)

    def _noisy(req, cat):
        import logging

        print("hello-from-geospacelab")
        logging.getLogger("gsl.test").warning("a-warning")
        return RunResult(fig="X")

    monkeypatch.setattr(runner, "_run_datahub", _noisy)
    res = build_and_render(_req("indices.kpap"), CAT)
    assert "hello-from-geospacelab" in res.log
    assert "a-warning" in res.log
