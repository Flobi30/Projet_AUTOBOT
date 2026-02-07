"""Regenerate admin salt in users.json to fix all-zero salt vulnerability."""

import json
import os
import hashlib
import getpass


def regenerate_salt(users_file: str = "users.json") -> None:
    if not os.path.exists(users_file):
        print(f"Error: {users_file} not found")
        return

    with open(users_file, "r") as f:
        data = json.load(f)

    for username, user in data.get("users", {}).items():
        old_salt = user.get("salt", "")
        if old_salt == "0" * 64:
            print(f"User '{username}' has all-zero salt. Regenerating...")
            new_salt = os.urandom(32).hex()
            password = getpass.getpass(f"Enter password for '{username}': ")
            new_hash = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                bytes.fromhex(new_salt),
                100000,
            ).hex()
            user["salt"] = new_salt
            user["password_hash"] = new_hash
            print(f"Salt regenerated for '{username}'")

    with open(users_file, "w") as f:
        json.dump(data, f, indent=2)
    print("users.json updated successfully")


if __name__ == "__main__":
    regenerate_salt()
