"""One-shot setup for model trust: sign the weights, then clear them for clinical use.

Why this exists. The registry runs two gates. Integrity asks whether a weight file is
unaltered since it was signed; provenance asks whether it is the model this deployment is
approved to run. A manifest produced before provenance existed carries only hashes, so it
passes the first gate and fails the second, and every model is refused with:

    manifest carries no provenance (re-sign with scripts/sign_model.py)

That is the gate working, not a bug - but it means a repository whose weights were signed
earlier needs one re-signing pass before the models load. This script is that pass.

It does three things, and each needs a secret you must set first:

    1. create the build keypair          MODEL_SIGNING_PASSWORD
    2. create the approval keypair       MODEL_APPROVAL_PASSWORD   (a different secret)
    3. sign the manifest with provenance from config/model_approvals.json,
       then countersign the approvals you name

The two keys are deliberately separate: the build key says what a model is, the approval
key says it may be used on patients. Whoever holds both can do both, which is why in a real
deployment they belong to different people and ideally different machines.

Usage (from the backend/ folder):
    python scripts/bootstrap_model_trust.py --init-keys
    # edit config/model_approvals.json: set model_version and approval_status for each model
    python scripts/bootstrap_model_trust.py --sign
    python scripts/bootstrap_model_trust.py --approve tooth_detector landmarks \\
        --by "Dr A Patel, GDC 123456"
    python scripts/bootstrap_model_trust.py --status
"""
import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))  # backend/

from app import config  # noqa: E402
from app.security.model_approval import (  # noqa: E402
    ApprovalError,
    ApprovalRecord,
    approval_signer,
    load_approvals,
    sign_approvals,
)
from app.security.model_signing import MANIFEST_NAME, Signer, SigningError  # noqa: E402

APPROVALS_CONFIG = os.path.join(config.BACKEND_DIR, "config", "model_approvals.json")


def _declared() -> dict:
    with open(APPROVALS_CONFIG, encoding="utf-8") as f:
        return json.load(f).get("models") or {}


def cmd_init_keys() -> int:
    build = Signer()
    approve = approval_signer()
    for signer, label, env in ((build, "build", "MODEL_SIGNING_PASSWORD"),
                               (approve, "approval", "MODEL_APPROVAL_PASSWORD")):
        if signer.priv_path.exists():
            print(f"{label} key already exists at {signer.priv_path} - left alone")
            continue
        if not signer.password:
            print(f"ERROR: {env} is not set, so the {label} key cannot be created.")
            return 2
        signer.generate_keypair()
        print(f"created {label} key: {signer.priv_path}")
    if build.password and approve.password and build.password == approve.password:
        print()
        print("WARNING: MODEL_SIGNING_PASSWORD and MODEL_APPROVAL_PASSWORD are the same.")
        print("         The separation of duties is then only on paper. Use different secrets.")
    return 0


def cmd_sign(weights: str) -> int:
    models = _declared()
    if not models:
        print(f"ERROR: {APPROVALS_CONFIG} declares no models.")
        return 2
    manifest = Signer().sign_manifest(weights, models=models)
    print(f"signed {len(manifest['files'])} weight file(s), manifest_version "
          f"{manifest['manifest_version']}")
    for name, meta in (manifest.get("models") or {}).items():
        state = str(meta.get("approval_status", "?")).upper()
        print(f"  {'OK ' if state == 'APPROVED' else '!! '}{name:<20} "
              f"v{meta.get('model_version')}  {state}")
    pending = [n for n, m in manifest["models"].items()
               if str(m.get("approval_status", "")).lower() != "approved"]
    if pending:
        print()
        print("Still PENDING in config/model_approvals.json, so the registry will refuse them:")
        print("  " + ", ".join(pending))
        print("Set approval_status to 'approved' there, re-run --sign, then --approve them.")
    return 0


def cmd_approve(weights: str, names: list[str], by: str, expires: str | None) -> int:
    if not by:
        print("ERROR: --by is required. An approval must name an accountable person.")
        return 2
    manifest_path = os.path.join(weights, MANIFEST_NAME)
    if not os.path.exists(manifest_path):
        print(f"ERROR: no {MANIFEST_NAME}. Run --sign first.")
        return 2
    with open(manifest_path, encoding="utf-8") as f:
        declared = json.load(f).get("models") or {}

    signer = approval_signer()
    try:
        existing = list(load_approvals(weights, signer).get("approvals", []))
    except ApprovalError:
        existing = []

    records = [ApprovalRecord(**a) for a in existing if a["model_id"] not in names]
    for name in names:
        entry = declared.get(name)
        if entry is None:
            print(f"ERROR: {name} is not in the signed manifest.")
            return 2
        if not entry.get("sha256"):
            print(f"ERROR: {name} has no hash in the manifest; re-run --sign.")
            return 2
        records.append(ApprovalRecord(
            model_id=name, model_version=str(entry["model_version"]), sha256=entry["sha256"],
            approved_by=by, approved_at=dt.datetime.now(dt.timezone.utc).isoformat(),
            expires_at=expires))
        print(f"approved {name} v{entry['model_version']}  sha256={entry['sha256'][:16]}...")

    sign_approvals(weights, records, signer)
    print(f"countersigned by: {by}")
    print("Each clearance covers those exact bytes. Rebuilding a model voids its approval.")
    return 0


def cmd_status(weights: str) -> int:
    from app.ml.registry import MODEL_SPECS, ModelRegistry

    registry = ModelRegistry(weights_dir=weights, record_events=False,
                             approval_signer=approval_signer())
    print(f"{'model':<22}{'present':<9}{'signed':<8}{'approved':<10}reason")
    ready = 0
    for name in MODEL_SPECS:
        s = registry.check(name)
        ready += bool(s.approved)
        print(f"{name:<22}{str(s.present):<9}{str(s.signature_valid):<8}"
              f"{str(s.approved):<10}{s.reason or ''}")
    print()
    print(f"{ready}/{len(MODEL_SPECS)} model(s) will load. The rest fall back to labelled DEMO output.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--weights", default=str(config.WEIGHTS_DIR))
    parser.add_argument("--init-keys", action="store_true")
    parser.add_argument("--sign", action="store_true")
    parser.add_argument("--approve", nargs="+", metavar="MODEL_ID")
    parser.add_argument("--by", help="who is approving: a named, accountable person")
    parser.add_argument("--expires", help="optional expiry, ISO date")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    try:
        if args.init_keys:
            return cmd_init_keys()
        if args.sign:
            return cmd_sign(args.weights)
        if args.approve:
            return cmd_approve(args.weights, args.approve, args.by, args.expires)
        if args.status:
            return cmd_status(args.weights)
    except SigningError as exc:
        print(f"ERROR: {exc}")
        return 2
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
