from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User
from schemas.auth import AuthPayload
from services.auth_service import create_token, get_user_by_username, hash_password, verify_password


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register")
async def register(payload: AuthPayload, db: AsyncSession = Depends(get_db)):
    username = payload.username.strip()
    existing = await get_user_by_username(username, db)
    if existing is not None:
        raise HTTPException(status_code=400, detail="Username already exists")
    user = User(username=username, password_hash=hash_password(payload.password))
    db.add(user)
    await db.commit()
    return {"token": create_token(username), "username": username}


@router.post("/login")
async def login(payload: AuthPayload, db: AsyncSession = Depends(get_db)):
    username = payload.username.strip()
    user = await get_user_by_username(username, db)
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return {"token": create_token(username), "username": username}

