# db.py
from typing import final
from sqlmodel import Session, create_engine
import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://user:password@localhost:5432/dbname"
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # évite les connexions mortes
)

def get_session():
    with Session(engine) as session:
        try:
            yield session
        finally:
            session.close()