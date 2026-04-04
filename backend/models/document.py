from sqlalchemy import Column, DateTime, Integer, String, Text, func

from database import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    doc_type = Column(String(50))
    description = Column(Text)
    chunk_count = Column(Integer, default=0)
    status = Column(String(20), default="processing")
    error_message = Column(Text)
    created_at = Column(DateTime, server_default=func.now())

