"""Model calls are serialised: the start-up self-check and analysis requests never run a model at the same time.

YOLO models are not thread-safe; running one from two threads at once failed with a tensor-size mismatch when the
self-check overlapped the first analysis (found while building the demo sets, 2026-10-07)."""
import threading

from app.ml import canary
from app.ml.inference_lock import MODEL_LOCK
from app.services import analysis_service


def _owned():
    return MODEL_LOCK._is_owned()        # RLock: True only in the thread that holds it


def test_analysis_runs_under_the_model_lock(monkeypatch):
    seen = {}

    def fake_decode(_png):
        seen["locked"] = _owned()
        raise RuntimeError("stop after the check")

    monkeypatch.setattr(analysis_service, "_decode", fake_decode)
    try:
        analysis_service.run_analysis(b"x", {}, {})
    except RuntimeError:
        pass
    assert seen["locked"] is True


def test_self_check_runs_under_the_model_lock(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(canary, "fingerprints", lambda: seen.setdefault("locked", _owned()) and {})
    monkeypatch.setattr(canary.config, "WEIGHTS_DIR", tmp_path)
    (tmp_path / canary.EXPECTED_FILE).write_text('{"fingerprints": {}}')
    from app.security.model_signing import Signer
    monkeypatch.setattr(Signer, "verify_weight_file", lambda self, p, *a, **k: {"verified": True})
    canary.run()
    assert seen["locked"] is True


def test_two_threads_take_turns():
    order = []

    def worker(name):
        with MODEL_LOCK:
            order.append(f"{name}-in")
            order.append(f"{name}-out")

    threads = [threading.Thread(target=worker, args=(n,)) for n in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert order in (["a-in", "a-out", "b-in", "b-out"], ["b-in", "b-out", "a-in", "a-out"])
