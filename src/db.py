from collections.abc import AsyncGenerator

from fastapi import Depends
from fastapi_users.db import SQLAlchemyBaseUserTableUUID, SQLAlchemyUserDatabase
from sqlalchemy import ForeignKey, String, delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DATABASE_URL = "sqlite+aiosqlite:///./agenticsystem.db"

TOPIC_DEFINITIONS = [
    {"key": "variables", "title": "Переменные и типы данных"},
    {"key": "operators", "title": "Операторы"},
    {"key": "conditions", "title": "Условия"},
    {"key": "loops", "title": "Циклы"},
    {"key": "functions", "title": "Функции"},
    {"key": "arrays", "title": "Массивы"},
    {"key": "objects", "title": "Объекты"},
    {"key": "strings", "title": "Строки"},
    {"key": "dom", "title": "DOM"},
    {"key": "events", "title": "События"},
    {"key": "async", "title": "Async / Await"},
    {"key": "api", "title": "Fetch / API"},
]


class Base(DeclarativeBase):
    pass


class User(SQLAlchemyBaseUserTableUUID, Base):
    pass


class Topic(Base):
    __tablename__ = "topics"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)


class UserTopic(Base):
    __tablename__ = "user_topics"

    user_id = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), primary_key=True)
    topic_key: Mapped[str] = mapped_column(ForeignKey("topics.key", ondelete="CASCADE"), primary_key=True)


class UserRoadmapItem(Base):
    """Stores individual roadmap item completion, e.g. 'variables__hoisting'."""
    __tablename__ = "user_roadmap_items"

    user_id = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), primary_key=True)
    item_slug: Mapped[str] = mapped_column(String(200), primary_key=True)


engine = create_async_engine(DATABASE_URL, echo=False)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


async def create_db_and_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def seed_topics() -> None:
    async with async_session_maker() as session:
        existing = await session.execute(select(Topic.key))
        existing_keys = set(existing.scalars().all())

        for topic in TOPIC_DEFINITIONS:
            if topic["key"] not in existing_keys:
                session.add(Topic(key=topic["key"], title=topic["title"]))

        await session.commit()


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session


async def get_user_db(session: AsyncSession = Depends(get_async_session)):
    yield SQLAlchemyUserDatabase(session, User)