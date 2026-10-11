"""Command line administration. There are no default users; create the first admin with:

    python -m app.cli create-admin --username <name>

The password is prompted twice (getpass, never echoed or logged) and must be 12+ characters.
"""
import argparse
import getpass
import sys

from app.auth import UsernameTaken, create_user, validate_new_user


def create_admin(username: str) -> int:
    from app.db import SessionLocal  # applies migrations; imported here so --help needs no database

    with SessionLocal() as session:
        try:
            name = validate_new_user(username, "x" * 12, "admin")  # check the username before prompting
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        from models import User
        if session.query(User.id).filter(User.username == name).first() is not None:
            print(f"error: user '{name}' already exists", file=sys.stderr)
            return 1
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Repeat password: "):
            print("error: the passwords do not match", file=sys.stderr)
            return 1
        try:
            create_user(session, name, password, "admin")
        except UsernameTaken:
            print(f"error: user '{name}' already exists", file=sys.stderr)
            return 1
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    print(f"Created admin '{name}'.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    admin = commands.add_parser("create-admin", help="create an admin user (prompts for the password)")
    admin.add_argument("--username", required=True)
    args = parser.parse_args(argv)
    return create_admin(args.username)


if __name__ == "__main__":
    sys.exit(main())
