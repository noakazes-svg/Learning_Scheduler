from pathlib import Path
from sqlmodel import Session, SQLModel, create_engine, text

_DB_DIR = Path(__file__).parent.parent.parent / "data"
_DB_DIR.mkdir(exist_ok=True)

DATABASE_URL = f"sqlite:///{_DB_DIR / 'learning_scheduler.db'}"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _run_migrations()


def _run_migrations() -> None:
    """Add columns / tables introduced after the initial schema without Alembic."""
    with engine.connect() as conn:
        existing = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(users)"))
        }
        if "target_role" not in existing:
            conn.execute(text("ALTER TABLE users ADD COLUMN target_role TEXT"))
            conn.commit()


def get_session():
    with Session(engine) as session:
        yield session
