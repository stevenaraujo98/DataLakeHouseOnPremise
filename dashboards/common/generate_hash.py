"""Genera un hash bcrypt para pegar en el campo `password` de config.yaml.

Uso:
    python generate_hash.py                # pide la contraseña de forma interactiva
    python generate_hash.py "MiClave123!"  # o la recibe como argumento
"""
import argparse
import getpass

import bcrypt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("password", nargs="?", help="Contraseña a hashear")
    args = parser.parse_args()

    password = args.password or getpass.getpass("Contraseña: ")
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    print(hashed)


if __name__ == "__main__":
    main()
