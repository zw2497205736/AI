from sqlalchemy import Column, DateTime, Integer, Text, UniqueConstraint, func

from database import Base


class RepoReviewMemory(Base):
    __tablename__ = "repo_review_memories"
    __table_args__ = (UniqueConstraint("repo_id", name="uq_repo_review_memories_repo_id"),)

    id = Column(Integer, primary_key=True, index=True)
    repo_id = Column(Integer, nullable=False, index=True)
    memory_text = Column(Text, nullable=False)
    risk_patterns = Column(Text, nullable=True)
    test_preferences = Column(Text, nullable=True)
    source_task_ids = Column(Text, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime, server_default=func.now())
