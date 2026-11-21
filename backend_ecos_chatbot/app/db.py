# db.py
"""Connexion à la base (PostgreSQL en production, SQLite pour les tests)."""
import os

from sqlmodel import Session, create_engine

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://user:password@localhost:5432/dbname")

_pool = {} if DATABASE_URL.startswith("sqlite") else {
    # Par processus uvicorn : DB_POOL_SIZE connexions permanentes + DB_MAX_OVERFLOW temporaires.
    # Total à garder sous max_connections de PostgreSQL (100 par défaut) : workers × (taille + débord).
    "pool_size": int(os.getenv("DB_POOL_SIZE", "10")),
    "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "20")),
    "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", "30")),
    "pool_recycle": 1800,
}

engine = create_engine(DATABASE_URL, pool_pre_ping=True, **_pool)


def get_session():
    with Session(engine) as session:
        yield session
