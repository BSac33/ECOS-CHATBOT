#!/usr/bin/env python3
"""
Importe des packs privés de stations (voir station_packs.py).

    cd backend_ecos_chatbot/app
    python scripts/import_stations.py                         # tous les packs de private/stations/
    python scripts/import_stations.py /chemin/livre-ecos.zip  # un pack précis
    python scripts/import_stations.py --author bensac ...     # auteur des stations (défaut : 1er admin)
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("packs", nargs="*", type=Path)
    parser.add_argument("--author", help="nom d'utilisateur de l'auteur (défaut : premier administrateur)")
    args = parser.parse_args()

    from sqlmodel import Session, create_engine, select

    from models import User, UserRole
    from station_packs import PRIVATE_DIR, find_packs, import_pack

    packs = args.packs or find_packs()
    if not packs:
        raise SystemExit(f"Aucun pack : passez un chemin ou déposez-le dans {PRIVATE_DIR}")
    with Session(create_engine(os.environ["DATABASE_URL"])) as session:
        stmt = select(User).where(User.username == args.author) if args.author else \
            select(User).where(User.role == UserRole.admin).order_by(User.id)
        author = session.exec(stmt).first()
        if author is None:
            raise SystemExit("Auteur introuvable : créez d'abord un compte administrateur.")
        for path in packs:
            report = import_pack(session, path, author)
            print(f"✅ {report.summary()}")
            for line in report.messages:
                print(f"   ⚠️  {line}")


if __name__ == "__main__":
    main()
