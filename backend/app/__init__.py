"""PerioVision AI backend: Flask application factory."""
from __future__ import annotations

import logging
import os
import sys

from flask import Flask, request
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from app import config
from app.extensions import limiter

logger = logging.getLogger("periovision")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-site",
    # The API only returns JSON, images and PDFs, so nothing may run or be framed.
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
}


def _seed_accounts() -> None:
    """Accounts from .env only (never from code). DEMO_* accounts are for demonstrations."""
    from app.services import container

    users = container.doctor_manager()
    specs = [
        ("BOOTSTRAP_ADMIN", "admin", "Administrator"),
        ("DEMO", "dentist", "Demo Dentist"),
        ("DEMO_TECHNICIAN", "technician", "Demo Technician"),
        ("DEMO_AUDITOR", "auditor", "Demo Auditor"),
        ("DEMO_ADMIN", "admin", "Demo Admin"),
    ]
    for prefix, role, name in specs:
        email, password = os.getenv(f"{prefix}_EMAIL"), os.getenv(f"{prefix}_PASSWORD")
        if not (email and password):
            continue
        try:
            if not users.collection.find_one({"email": email.strip().lower()}):
                users.register_doctor(name=name, email=email, password=password, role=role,
                                      clinic_name="PerioVision Demo Clinic")
                logger.info("Seeded %s account from .env", role)
        except Exception as exc:  # seeding must never stop the API from starting
            logger.warning("Account seeding skipped for %s: %s", prefix, exc)


def _install_security(app: Flask) -> None:
    from app.api._common import fail
    from app.security.zero_trust import enforce_deny_by_default

    CORS(app, resources={r"/api/*": {"origins": config.CORS_ORIGINS}}, supports_credentials=True,
         allow_headers=["Authorization", "Content-Type"], methods=["GET", "POST", "PATCH", "OPTIONS"], max_age=600)
    enforce_deny_by_default(app)

    @app.after_request
    def _headers(resp):
        for k, v in SECURITY_HEADERS.items():
            resp.headers.setdefault(k, v)
        if request.is_secure:
            resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if request.path.startswith("/api/"):
            resp.headers.setdefault("Cache-Control", "no-store")
        resp.headers.pop("Server", None)
        return resp

    @app.errorhandler(HTTPException)
    def _http_error(exc: HTTPException):
        messages = {404: "Not found.", 405: "Method not allowed.", 413: "The upload is too large.",
                    429: "Too many requests. Please wait a moment and try again."}
        return fail(exc.code or 500, messages.get(exc.code, exc.name))

    @app.errorhandler(Exception)
    def _unhandled(exc: Exception):
        logger.exception("Unhandled error")
        return fail(500, "Internal error. It has been logged.")  # never leak stack traces or internals


def create_app(seed_accounts: bool = True) -> Flask:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    config.ensure_runtime_dirs()
    if config.IS_DEMO and config.BLOB_DIR.name == "blobs-demo":
        for leftover in config.BLOB_DIR.glob("*.bin"):  # orphaned demo files from a previous run
            leftover.unlink()
    config.BLOB_DIR.mkdir(parents=True, exist_ok=True)

    app = Flask(__name__)
    app.config.from_object(config.FlaskConfig)
    app.json.sort_keys = False
    limiter.init_app(app)
    _install_security(app)

    from app.api import analysis, audit, auth, clinical, health, patients, progression, radiographs, reports, security
    for module in (health, auth, patients, radiographs, analysis, progression, clinical, reports, audit, security):
        app.register_blueprint(module.bp)

    from app.api.docs import bp as docs_bp
    app.register_blueprint(docs_bp)

    if seed_accounts:
        _seed_accounts()
        try:
            from app.security.honeypot import HoneypotManager

            HoneypotManager().deploy()
        except Exception as exc:
            logger.warning("Decoy deployment skipped: %s", exc)
    from app.security.audit_log import audit as audit_log

    audit_log().record("SYSTEM_START", actor="system", details={"mode": config.APP_MODE})
    if seed_accounts and config.IS_DEMO and os.getenv("SEED_DEMO_DATA", "1") == "1":
        try:
            from app.services.demo_seed import seed

            seed()
        except Exception as exc:  # the demo must never block startup
            logger.warning("Demo data seeding skipped: %s", exc)
    if seed_accounts and os.getenv("MODEL_SELF_CHECK", "1") == "1" and "pytest" not in sys.modules:
        from app.ml import canary

        canary.start_in_background()   # warms the models up and checks them against their recorded outputs
    return app
