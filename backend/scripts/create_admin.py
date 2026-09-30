"""Create a real administrator account in the live database. You type the password; it is never echoed or stored in files.

Usage (from the repository root):  .\\run.ps1 create-admin
(or from backend/:  set ENV_FILE=.env.production, then python scripts/create_admin.py)
After the first sign-in, turn on MFA for this account on the Security centre -> MFA tab.
"""
import getpass
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))  # backend/

from app import config  # noqa: E402
from app.security.auth import password_problems  # noqa: E402


def main() -> int:
    if config.IS_DEMO:
        print("ERROR: DB_MODE is demo. Run this with ENV_FILE=.env.production (.\\run.ps1 create-admin).")
        return 2
    from app.services import container

    name = input("Full name: ").strip() or "Administrator"
    email = input("Email: ").strip()
    while True:
        pw = getpass.getpass("Password (10+ chars, upper + lower case, a digit): ")
        problems = password_problems(pw)
        if problems:
            print("Password needs " + ", ".join(problems) + ".")
            continue
        if getpass.getpass("Repeat password: ") != pw:
            print("Passwords do not match.")
            continue
        break
    try:
        user = container.doctor_manager().register_doctor(name=name, email=email, password=pw, role="admin",
                                                          clinic_name=input("Clinic name (optional): ").strip() or None)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 1
    from app.security.audit_log import audit
    audit().record("ADMIN_CREATED", actor="cli", details={"role": "admin", "source": "scripts/create_admin.py"})
    print(f"Created admin account for {email}. Sign in, then enable MFA under Security centre -> MFA.")
    return 0 if user else 1


if __name__ == "__main__":
    raise SystemExit(main())
