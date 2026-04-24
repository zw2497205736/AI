from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import settings


engine = create_async_engine(settings.database_url, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with SessionLocal() as session:
        yield session


async def create_tables():
    from models import agent_task, conversation, document, github_repository, memory, repo_review_memory, user  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        result = await conn.execute(text("PRAGMA table_info(agent_tasks)"))
        columns = {row[1] for row in result.fetchall()}
        if "unit_test_generation_content" not in columns:
            await conn.execute(text("ALTER TABLE agent_tasks ADD COLUMN unit_test_generation_content TEXT"))
