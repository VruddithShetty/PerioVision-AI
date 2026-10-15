"""Clear a model for clinical use. Separate tool, separate key, separate person.

`sign_model.py` attests what a model *is*: these bytes, this version, this provenance.
This attests that it *may be used on patients*. They are deliberately different actions
under different keys, so whoever builds a model cannot also clear it.

An approval names the model's exact SHA-256, so it covers specific bytes. Rebuilding a
model - even keeping the version number - changes the hash and the old approval stops
applying. That is the intended behaviour, not an inconvenience.

Usage (from the backend/ folder):
    python scripts/approve_model.py --init-keys          # create the approval keypair once
    python scripts/approve_model.py --list               # what the manifest offers
    python scripts/approve_model.py --approve tooth_detector --by "Dr A Patel, GDC 123456"
    python scripts/approve_model.py --approve landmarks --by "..." --expires 2027-01-01
    python scripts/approve_model.py --revoke tooth_detector
    python scripts/approve_model.py --verify             # check what is currently cleared

Needs MODEL_APPROVAL_PASSWORD. It must not be the same secret as MODEL_SIGNING_PASSWORD,
and the two keys should not live on the same machine in a real deployment.
"""
import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))  # backend/

from app import config  # noqa: E402
from app.security.model_approval import (  # noqa: E402
    APPROVALS_NAME,
    ApprovalError,
    ApprovalRecord,
    approval_signer,
    load_approvals,
    sign_approvals,
)
from app.security.model_signing import MANIFEST_NAME, SigningError  # noqa: E402


def _manifest(weights_dir) -> dict:
    path = os.path.join(weights_dir, MANIFEST_NAME)
    if not os.path.exists(path):
        raise SystemExit(f"No {MANIFEST_NAME} in {weights_dir}. Run scripts/sign_model.py first.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _existing(weights_dir, signer) -> list[dict]:
    try:
        return list(load_approvals(weights_dir, signer).get("approvals", []))
    except ApprovalError:
        return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--weights", default=str(config.WEIGHTS_DIR))
    parser.add_argument("--init-keys", action="store_true", help="create the approval keypair")
    parser.add_argument("--list", action="store_true", help="show what the manifest offers")
    parser.add_argument("--verify", action="store_true", help="show what is currently cleared")
    parser.add_argument("--approve", metavar="MODEL_ID", help="clear a model for clinical use")
    parser.add_argument("--revoke", metavar="MODEL_ID", help="withdraw a clearance")
    parser.add_argument("--by", help="who is approving: a named, accountable person")
    parser.add_argument("--expires", help="optional expiry, ISO date (e.g. 2027-01-01)")
    parser.add_argument("--note", help="optional note recorded with the approval")
    args = parser.parse_args()

    signer = approval_signer()

    try:
        if args.init_keys:
            signer.generate_keypair()
            print(f"Approval keypair created in {signer.keys_dir}")
            print("Keep MODEL_APPROVAL_PASSWORD separate from MODEL_SIGNING_PASSWORD.")
            return 0

        if args.list:
            models = _manifest(args.weights).get("models") or {}
            if not models:
                print("The manifest declares no models.")
                return 1
            cleared = {a["model_id"]: a for a in _existing(args.weights, signer)}
            for name, meta in models.items():
                mark = "APPROVED" if name in cleared else "not approved"
                print(f"{name:<18} v{meta.get('model_version'):<12} "
                      f"sha256={str(meta.get('sha256'))[:16]}...  {mark}")
            return 0

        if args.verify:
            try:
                document = load_approvals(args.weights, signer)
            except ApprovalError as exc:
                print(f"No usable approval record: {exc}")
                return 1
            approvals = document.get("approvals", [])
            print(f"{len(approvals)} approval(s), signed and verified:")
            for a in approvals:
                expiry = f", expires {a['expires_at']}" if a.get("expires_at") else ""
                print(f"  {a['model_id']} v{a['model_version']} "
                      f"sha256={a['sha256'][:16]}...  by {a['approved_by']}{expiry}")
            return 0

        if args.revoke:
            remaining = [a for a in _existing(args.weights, signer) if a["model_id"] != args.revoke]
            sign_approvals(args.weights, [ApprovalRecord(**a) for a in remaining], signer)
            print(f"Withdrew clearance for {args.revoke}. {len(remaining)} approval(s) remain.")
            return 0

        if args.approve:
            if not args.by:
                print("ERROR: --by is required. An approval must name an accountable person.")
                return 2
            models = _manifest(args.weights).get("models") or {}
            entry = models.get(args.approve)
            if entry is None:
                print(f"ERROR: {args.approve} is not in the signed manifest.")
                return 2
            digest = entry.get("sha256")
            if not digest:
                print("ERROR: the manifest entry carries no hash; re-run scripts/sign_model.py.")
                return 2

            record = ApprovalRecord(
                model_id=args.approve, model_version=str(entry["model_version"]), sha256=digest,
                approved_by=args.by,
                approved_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                expires_at=args.expires, note=args.note)
            others = [a for a in _existing(args.weights, signer) if a["model_id"] != args.approve]
            sign_approvals(args.weights,
                           [ApprovalRecord(**a) for a in others] + [record], signer)
            print(f"Approved {args.approve} v{record.model_version}")
            print(f"  hash    {digest[:32]}...")
            print(f"  by      {args.by}")
            print(f"  written {os.path.join(args.weights, APPROVALS_NAME)} (+ .sig)")
            print("This clearance covers these exact bytes. Rebuilding the model voids it.")
            return 0

        parser.print_help()
        return 1

    except SigningError as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
