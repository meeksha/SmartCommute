"""Admin tool: reset a user's password.

    python -m app.tools.reset_password user@example.com NewPassword123
    docker compose exec backend python -m app.tools.reset_password user@example.com NewPassword123

Also signs the user out everywhere (existing sessions are revoked).
"""
import sys

from app.database import SessionLocal, UserAccount, LoginSession, init_db
from app.security import hash_password


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    email, password = argv[1].strip().lower(), argv[2]
    if len(password) < 8:
        print("Password must be at least 8 characters.")
        return 1
    init_db()
    with SessionLocal() as db:
        acc = db.get(UserAccount, email)
        if not acc:
            print(f"No account for {email}.")
            return 1
        acc.password_hash = hash_password(password)
        revoked = db.query(LoginSession).filter(LoginSession.user_email == email).delete()
        db.commit()
    print(f"Password reset for {email}; {revoked} session(s) revoked.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
