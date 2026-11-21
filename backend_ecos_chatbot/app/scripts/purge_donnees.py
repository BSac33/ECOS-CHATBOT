#!/usr/bin/env python3
"""
Purge des données anciennes (durée de conservation, RGPD) : supprime les tentatives
commencées il y a plus de N mois, avec leurs messages, corrections et signalements.

    python scripts/purge_donnees.py --mois 24 --simulation   # compte sans rien supprimer
    python scripts/purge_donnees.py --mois 24                # supprime
    python scripts/purge_donnees.py --mois 24 --garder-tests # garde les tentatives de test des enseignants

À planifier (cron) une fois par mois, par exemple :
    docker compose -f docker-compose.prod.yml exec -T api python scripts/purge_donnees.py --mois 24
La durée est à fixer avec le délégué à la protection des données de l'établissement.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mois", type=int, required=True, help="durée de conservation en mois (≥ 1)")
    parser.add_argument("--simulation", action="store_true", help="afficher le nombre sans supprimer")
    parser.add_argument("--garder-tests", action="store_true", help="ne pas supprimer les tentatives de test")
    args = parser.parse_args(argv)
    if args.mois < 1:
        parser.error("--mois doit valoir au moins 1")

    from sqlmodel import Session, create_engine, func, select

    from models import Attempts
    from user_data import purge_attempts

    before = datetime.now() - timedelta(days=30 * args.mois)
    engine = create_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        if args.simulation:
            stmt = select(func.count()).select_from(Attempts).where(Attempts.created_at < before)
            if args.garder_tests:
                stmt = stmt.where(Attempts.is_test == False)  # noqa: E712
            print(f"{session.exec(stmt).one()} tentative(s) commencée(s) avant le {before:%d/%m/%Y} seraient supprimées.")
            return 0
        n = purge_attempts(session, before, include_tests=not args.garder_tests)
    print(f"{n} tentative(s) commencée(s) avant le {before:%d/%m/%Y} supprimée(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
