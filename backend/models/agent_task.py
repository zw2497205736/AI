from sqlalchemy import Column, DateTime, Integer, String, Text, func

from database import Base


class AgentTask(Base):
    __tablename__ = "agent_tasks"

    id = Column(Integer, primary_key=True, index=True)
    repo_id = Column(Integer, nullable=False, index=True)
    user_id = Column(String(100), nullable=False, index=True)
    task_type = Column(String(50), nullable=False, default="pr_review")
    event_type = Column(String(50), nullable=False)
    pr_number = Column(Integer, nullable=True, index=True)
    commit_sha = Column(String(100), nullable=True)
    title = Column(String(255), nullable=False)
    status = Column(String(30), nullable=False, default="queued", index=True)
    source_payload = Column(Text, nullable=True)
    review_content = Column(Text, nullable=True)
    test_suggestion_content = Column(Text, nullable=True)
    unit_test_generation_content = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
