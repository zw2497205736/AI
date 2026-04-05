from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import create_tables
from routers import auth_router, chat_router, code_review_router, document_router, github_router, settings_router


app = FastAPI(title="AI Team Assistant", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await create_tables()


app.include_router(auth_router.router)
app.include_router(document_router.router)
app.include_router(chat_router.router)
app.include_router(code_review_router.router)
app.include_router(github_router.router)
app.include_router(settings_router.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
