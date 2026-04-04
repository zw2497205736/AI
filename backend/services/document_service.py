import io

import PyPDF2
import docx
from fastapi import HTTPException, UploadFile
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from models.document import Document
from services.embedding_service import add_chunks_to_store
from utils.text_splitter import split_by_token


async def parse_document(file: UploadFile) -> str:
    content = await file.read()
    filename = (file.filename or "").lower()

    if filename.endswith(".pdf"):
        reader = PyPDF2.PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    if filename.endswith(".docx"):
        document = docx.Document(io.BytesIO(content))
        return "\n".join(paragraph.text for paragraph in document.paragraphs).strip()
    return content.decode("utf-8", errors="ignore").strip()


async def upload_document(file: UploadFile, description: str, client: AsyncOpenAI, db: AsyncSession) -> Document:
    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else "txt"
    doc = Document(filename=file.filename or "untitled", doc_type=ext, description=description, status="processing")
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    try:
        text = await parse_document(file)
        if not text:
            raise HTTPException(status_code=400, detail="Document contains no extractable text")
        chunks = split_by_token(text)
        if not chunks:
            raise HTTPException(status_code=400, detail="Document could not be split into chunks")
        await add_chunks_to_store(doc.id, doc.filename, chunks, client)
        doc.chunk_count = len(chunks)
        doc.status = "ready"
        doc.error_message = None
    except Exception as exc:
        doc.status = "error"
        doc.error_message = str(exc)

    await db.commit()
    await db.refresh(doc)
    return doc

