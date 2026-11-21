"""Admin tool: make an account a company admin (or back to employee).

    python -m app.tools.set_role friend@example.com admin
    docker compose exec backend python -m app.tools.set_role friend@example.com admin
    docker compose exec backend python -m app.tools.set_role friend@example.com employee

The person just reloads the page; no need to sign out.
"""
import sys

from app.database import ROLES, SessionLocal, UserAccount, init_db


def main(argv):
    if len(argv) != 3 or argv[2].lower() not in ROLES:
        print(__doc__)
        return 2
    email, role = argv[1].strip().lower(), argv[2].lower()
    init_db()
    with SessionLocal() as db:
        acc = db.get(UserAccount, email)
        if not acc:
            emails = [a.email for a in db.query(UserAccount).order_by(UserAccount.email).all()]
            print(f"No account for {email}. Accounts: {', '.join(emails) or '(none)'}")
            return 1
        acc.role = role
        db.commit()
    print(f"{email} is now: {role}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
