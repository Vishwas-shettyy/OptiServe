"""Print a bcrypt hash for ADMIN_PASSWORD_HASH. Usage: python scripts/hash_password.py"""

import getpass
import sys

import bcrypt


def main() -> int:
    """Prompt for a password twice and print the .env line."""
    password = getpass.getpass("Admin password: ")
    if len(password) < 8:
        print("Use at least 8 characters.", file=sys.stderr)
        return 1
    if getpass.getpass("Repeat password: ") != password:
        print("Passwords do not match.", file=sys.stderr)
        return 1
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    # Single quotes stop .env loaders from treating the '$' signs in the hash as variables.
    print(f"ADMIN_PASSWORD_HASH='{hashed}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
