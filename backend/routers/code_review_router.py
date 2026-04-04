import json
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from dependencies import get_current_user
from services.code_review_service import stream_code_review
from services.llm_service import get_openai_client


router = APIRouter(prefix="/api/code-review", tags=["code-review"])


@router.post("/stream")
async def review_stream(
    code: str = Form(default=""),
    language: str = Form(default="diff"),
    file: Optional[UploadFile] = File(default=None),
    current_user=Depends(get_current_user),
):
    client = get_openai_client()
    if file is not None:
        content = await file.read()
        code_content = content.decode("utf-8", errors="ignore")
    else:
        code_content = code

    if not code_content.strip():
        raise HTTPException(status_code=400, detail="Code content cannot be empty")

    async def generate():
        async for chunk in stream_code_review(code_content, language, client):
            yield f"data: {json.dumps({'content': chunk})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Access-Control-Allow-Origin": "*"},
    )
