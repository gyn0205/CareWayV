from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import SessionLocal


class SessionDependency:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def __call__(self) -> Iterator[Session]:
        with self._session_factory() as session:
            yield session


get_db = SessionDependency(SessionLocal)
DbSession = Annotated[Session, Depends(get_db)]
