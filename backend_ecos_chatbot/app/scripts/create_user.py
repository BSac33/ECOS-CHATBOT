#!/usr/bin/env python3
"""
Crée (ou met à jour) un compte depuis le serveur.

    python scripts/create_user.py admin --role admin                # mot de passe demandé
    python scripts/create_user.py dupont --role teacher --full-name "Dr Dupont"
    ECOS_PASSWORD=... python scripts/create_user.py etu1            # sans saisie (scripts)
    python scripts/create_user.py etu1 --reset-password             # compte existant

Rôles : student (défaut), teacher, admin.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("username")
    parser.add_argument("--role", choices=["student", "teacher", "admin"], default="student")
    parser.add_argument("--full-name")
    parser.add_argument("--reset-password", action="store_true", help="changer le mot de passe d'un compte existant")
    args = parser.parse_args()

    from sqlmodel import Session, create_engine, select

    from auth import get_password_hash
    from models import User, UserRole

    password = os.environ.get("ECOS_PASSWORD") or getpass.getpass(f"Mot de passe pour {args.username} : ")
    if len(password) < 8:
        raise SystemExit("Mot de passe trop court (8 caractères minimum).")

    with Session(create_engine(os.environ["DATABASE_URL"])) as session:
        user = session.exec(select(User).where(User.username == args.username)).first()
        if user and not args.reset_password:
            raise SystemExit(f"Le compte {args.username} existe déjà (--reset-password pour changer le mot de passe).")
        if user is None:
            user = User(username=args.username, hashed_password="", role=UserRole(args.role), is_active=True)
        else:
            user.role = UserRole(args.role)
        user.hashed_password = get_password_hash(password)
        if args.full_name:
            user.full_name = args.full_name
        session.add(user)
        session.commit()
        print(f"✅ Compte {args.username} ({args.role}) prêt.")


if __name__ == "__main__":
    main()
