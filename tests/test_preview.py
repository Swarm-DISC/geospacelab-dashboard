"""Out-of-process preview: worker rendering, result handling, and stop/kill."""

import asyncio
import os
import pickle

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from gsl_dashboard import preview_worker, runner  # noqa: E402
from gsl_dashboard.runner import RunResult  # noqa: E402
from gsl_dashboard.state import RequestState  # noqa: E402


def test_preview_worker_renders_png(monkeypatch, tmp_path):
    """The worker turns a RunResult figure into PNG bytes and pickles a result dict."""
    import gsl_dashboard.bootstrap as bootstrap
    import gsl_dashboard.catalog as catalog

    fig = plt.figure()
    fig.add_subplot(111).plot([0, 1, 2], [2, 0, 1])
    monkeypatch.setattr(bootstrap, "seed_geospacelab_config", lambda: None)
    monkeypatch.setattr(catalog, "get_catalog", lambda: None)
    monkeypatch.setattr(runner, "build_and_render", lambda req, cat: RunResult(fig=fig, data_repr="d", log="ran"))

    ip, op = tmp_path / "req.pkl", tmp_path / "out.pkl"
    ip.write_bytes(pickle.dumps({"dummy": 1}))
    preview_worker.main(str(ip), str(op))

    out = pickle.loads(op.read_bytes())
    assert out["png"][:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic
    assert out["data_repr"] == "d" and out["log"] == "ran" and out["error"] is None


def test_run_preview_sets_png(monkeypatch):
    st = RequestState()
    monkeypatch.setattr(st, "_run_worker", lambda req: {"png": b"PNGDATA", "data_repr": "tbl", "log": "L"})
    asyncio.run(st.run_preview())
    assert st.preview_png == b"PNGDATA" and st.data_repr == "tbl"
    assert st.console_log == "L" and st.error_msg == "" and st.is_running is False


def test_run_preview_reports_stopped(monkeypatch):
    st = RequestState()
    monkeypatch.setattr(st, "_run_worker", lambda req: {"stopped": True})
    asyncio.run(st.run_preview())
    assert st.error_msg == "Preview stopped." and st.preview_png is None and st.is_running is False


def test_run_preview_reports_error(monkeypatch):
    st = RequestState()
    monkeypatch.setattr(st, "_run_worker", lambda req: {"error": "boom", "log": "trace"})
    asyncio.run(st.run_preview())
    assert st.error_msg == "boom" and st.preview_png is None and st.console_log == "trace"


def test_stop_preview_terminates_process():
    st = RequestState()

    class _FakeProc:
        def __init__(self):
            self.terminated = False

        def poll(self):
            return None  # still running

        def terminate(self):
            self.terminated = True

    proc = _FakeProc()
    st._proc = proc
    st.stop_preview()
    assert st._stop_requested is True and proc.terminated is True


def test_stop_preview_kills_real_subprocess(monkeypatch, tmp_path):
    """End-to-end: a slow worker is terminated promptly (not waited out)."""
    import time

    import gsl_dashboard.state as state_mod

    sleeper = tmp_path / "sleeper.py"
    sleeper.write_text("import time\ntime.sleep(30)\n")
    monkeypatch.setattr(state_mod, "_WORKER_SCRIPT", str(sleeper))
    st = RequestState()

    async def go():
        task = asyncio.ensure_future(st.run_preview())
        for _ in range(200):
            if st._proc is not None and st._proc.poll() is None:
                break
            await asyncio.sleep(0.02)
        t0 = time.monotonic()
        st.stop_preview()
        await task
        return time.monotonic() - t0

    elapsed = asyncio.run(go())
    assert elapsed < 5  # killed, not waited out
    assert st.error_msg == "Preview stopped." and st.is_running is False
