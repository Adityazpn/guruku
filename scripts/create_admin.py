"""Create or promote an admin user.  Usage (from backend/):
    python ../scripts/create_admin.py owner@example.com super_admin
Roles: super_admin (everything), ai_admin (providers/tools/prompts/pricing; no user credits or audit log).
The password is asked interactively (never passed on the command line) and only when creating a new account."""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import app.models  # noqa: E402,F401
from app.auth.service import get_or_create_role  # noqa: E402
from app.core import db as dbmod  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.users.models import User, UserRole  # noqa: E402

ROLES = {"super_admin", "ai_admin"}


def main(email: str, role: str) -> None:
    if role not in ROLES:
        sys.exit(f"role must be one of {sorted(ROLES)}")
    email = email.lower()
    dbmod.get_engine()
    with dbmod._SessionLocal() as db:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            pw = getpass.getpass("New account password (min 10 chars): ")
            if len(pw) < 10 or pw != getpass.getpass("Repeat: "):
                sys.exit("password too short or does not match")
            user = User(email=email, password_hash=hash_password(pw))
            db.add(user)
            db.flush()
            print("created user")
        if role not in user.role_codes:
            user.roles.append(UserRole(user_id=user.id, role=get_or_create_role(db, role)))
        db.commit()
        print(f"{email} now has roles: {user.role_codes}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
