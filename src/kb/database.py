from pathlib import Path
from sqlmodel import Session, SQLModel, create_engine

_DB_DIR = Path(__file__).parent.parent.parent / "data"
_DB_DIR.mkdir(exist_ok=True)

DATABASE_URL = f"sqlite:///{_DB_DIR / 'learning_scheduler.db'}"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
