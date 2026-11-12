import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# SQLite untuk development. Tukar ke PostgreSQL bila nak deploy:
# DATABASE_URL=postgresql+psycopg2://user:pass@host/dbname
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./pssgutm.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
