from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_current_user
from database import get_db
from models.document import Document
from services.document_service import upload_document
from services.embedding_service import collection
from services.llm_service import get_openai_client


router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    description: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    client = get_openai_client()
    doc = await upload_document(file, description, client, db)
    return {
        "id": doc.id,
        "filename": doc.filename,
        "doc_type": doc.doc_type,
        "status": doc.status,
        "chunk_count": doc.chunk_count,
        "error_message": doc.error_message,
    }


@router.get("/")
async def list_documents(db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    result = await db.execute(select(Document).order_by(Document.created_at.desc()))
    documents = result.scalars().all()
    return [
        {
            "id": doc.id,
            "filename": doc.filename,
            "doc_type": doc.doc_type,
            "description": doc.description,
            "status": doc.status,
            "chunk_count": doc.chunk_count,
            "created_at": str(doc.created_at),
            "error_message": doc.error_message,
        }
        for doc in documents
    ]


@router.delete("/{doc_id}")
async def delete_document(doc_id: int, db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user)):
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    await db.delete(doc)
    await db.commit()
    collection.delete(where={"doc_id": doc_id})
    return {"message": "Deleted"}
