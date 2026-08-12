import secrets
import sys
from getpass import getpass

from labhub.auth import hash_password


def main():
    password = getpass("Password admin Laboran baru: ")
    confirmation = getpass("Ulangi password admin: ")
    if password != confirmation:
        raise SystemExit("Password tidak sama.")
    if len(password) < 12:
        raise SystemExit("Gunakan password admin minimal 12 karakter.")

    admin_hash = hash_password(password)
    print("\nMasukkan nilai berikut ke file .env production:\n")
    print(f"LABHUB_SESSION_SECRET={secrets.token_urlsafe(48)}")
    print(f"LABHUB_EDGE_DEVICE_TOKEN={secrets.token_urlsafe(48)}")
    print(f"POSTGRES_PASSWORD={secrets.token_urlsafe(36)}")
    # Docker Compose melakukan interpolasi '$VAR' pada nilai .env yang tidak
    # di-single-quote. Hash PBKDF2 memakai '$' sebagai delimiter, jadi wajib literal.
    print(f"LABHUB_ADMIN_PASSWORD_HASH='{admin_hash}'")
    print("\nJangan commit output ini ke GitHub.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nDibatalkan.")
