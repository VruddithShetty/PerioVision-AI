"""Model self-check ("canary"): fixed inputs in, recorded outputs expected back.

Every model is run on the same seeded synthetic input and its raw output is reduced to a few numbers. Those numbers
are recorded when the weights are signed (`python scripts/sign_model.py` writes weights/canary_expected.json, which
is itself part of the signed manifest) and checked again when the backend starts. A swapped or corrupted weight
file that somehow passed its hash check, a different library version that changes the numerics, or a broken
deploy shows up as a FAIL before anyone analyses a film.

What it does NOT show: clinical accuracy. The inputs are synthetic, so the check proves "same model, same maths
as when it was signed", not "correct answers"; accuracy on real films is in tests_live/ and docs/RESULTS_WITH_CI.md.

On FAIL every analysis gets the review reason `model_self_check_failed` (nothing is auto-cleared) and the failure
is written to the audit log. Running it also loads every model, so the first real analysis is not a cold start.
"""
from __future__ import annotations

import json
import logging
import threading

import numpy as np

from app import config

logger = logging.getLogger(__name__)
EXPECTED_FILE = "canary_expected.json"
RTOL, ATOL = 2e-3, 2e-3          # CPU / BLAS differences between machines stay far below this
_state: dict = {"status": "not_run", "checks": []}
_lock = threading.Lock()


def _input(h: int, w: int, seed: int) -> np.ndarray:
    """Deterministic grey 'film': smooth gradients plus seeded texture (no real radiograph is shipped)."""
    rng = np.random.default_rng(seed)  # audit-ok: fixed synthetic self-check input, never a reported value
    yy, xx = np.mgrid[0:h, 0:w]
    base = 90 + 60 * np.sin(xx / 37.0) * np.cos(yy / 53.0) + 30 * (yy / h)
    return np.clip(base + rng.normal(0, 12, (h, w)), 0, 255).astype(np.uint8)


def _yolo_fingerprint(model) -> list[float] | None:
    import torch

    if model is None:
        return None
    net = model.model.float().eval()
    g = _input(640, 640, 7)
    x = torch.from_numpy(np.repeat(g[None, None], 3, axis=1)).float() / 255.0
    with torch.inference_mode():
        out = net(x)
    out = out[0] if isinstance(out, (list, tuple)) else out
    a = out.detach().cpu().numpy().astype(np.float64)
    return [round(float(a.mean()), 6), round(float(a.std()), 6), round(float(a[0, 4:].max()), 6)]


def fingerprints() -> dict[str, list[float] | None]:
    """Current outputs of every model on the fixed inputs (None for a model that is not loaded)."""
    from app.ml.fusion.multimodal_risk import predict_patient_risk
    from app.ml.panoramic.whole_film import whole_film
    from app.services import container

    out: dict[str, list[float] | None] = {}
    out["tooth_detector"] = _yolo_fingerprint(container.tooth_detector().model)
    out["landmarks"] = _yolo_fingerprint(container.landmark_detector().model)
    wf = whole_film()
    g = _input(1024, 2048, 11)
    for name, outputs in (("panoramic_screen", 2), ("panoramic_severity", 1)):
        loaded = wf._load(name, outputs)
        if loaded is None:
            out[name] = None
            continue
        import torch

        net, m = loaded
        with torch.inference_mode():
            y = net(wf._input(g, m["input_size"]))[0].detach().cpu().numpy().astype(np.float64)
        out[name] = [round(float(v), 6) for v in y]
    risk = predict_patient_risk({"age": 55, "sex": "male", "smoking_status": "current", "cigarettes_per_day": 10,
                                 "diabetic": True, "hba1c": 7.5})
    out["risk_model"] = None if risk.get("probability") is None else [round(float(risk["probability"]), 6)]
    return out


def record() -> dict:
    """Write the current fingerprints as the expected ones (called by scripts/sign_model.py before signing)."""
    data = {"note": "Expected outputs of every model on fixed synthetic inputs; see app/ml/canary.py.",
            "fingerprints": fingerprints()}
    (config.WEIGHTS_DIR / EXPECTED_FILE).write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def run() -> dict:
    """Compare current outputs with the signed expected ones; store and return the result."""
    from app.security.audit_log import audit
    from app.security.model_signing import Signer

    path = config.WEIGHTS_DIR / EXPECTED_FILE
    if not path.exists():
        result = {"status": "not_recorded", "checks": [],
                  "message": "No recorded outputs: run python scripts/sign_model.py to record them."}
    elif not Signer().verify_weight_file(path).get("verified"):
        result = {"status": "fail", "checks": [], "message": "canary_expected.json fails the signed manifest."}
    else:
        expected = json.loads(path.read_text(encoding="utf-8"))["fingerprints"]
        current = fingerprints()
        checks = []
        for name, exp in expected.items():
            cur = current.get(name)
            if exp is None and cur is None:
                checks.append({"model": name, "status": "absent"})
                continue
            ok = exp is not None and cur is not None and len(exp) == len(cur) and \
                bool(np.allclose(cur, exp, rtol=RTOL, atol=ATOL))
            checks.append({"model": name, "status": "pass" if ok else "fail", "expected": exp, "current": cur})
        failed = [c["model"] for c in checks if c["status"] == "fail"]
        result = {"status": "fail" if failed else "pass", "checks": checks,
                  "message": f"Outputs drifted for: {', '.join(failed)}" if failed else "All models reproduce their "
                             "recorded outputs."}
    with _lock:
        _state.clear()
        _state.update(result)
    if result["status"] == "fail":
        logger.error("[SECURITY] Model self-check FAILED: %s", result.get("message"))
        audit().record("MODEL_SELF_CHECK_FAILED", outcome="error", actor="system",
                       details={"message": result.get("message")})
    else:
        logger.info("Model self-check: %s", result["status"])
    return result


def state() -> dict:
    with _lock:
        return dict(_state)


def start_in_background() -> None:
    """Warm the models up and run the check without delaying startup."""
    def _go():
        try:
            run()
        except Exception as exc:   # the check must never take the server down; report it instead
            with _lock:
                _state.clear()
                _state.update({"status": "error", "checks": [], "message": type(exc).__name__})
            logger.exception("Model self-check could not run")
    threading.Thread(target=_go, name="model-self-check", daemon=True).start()
