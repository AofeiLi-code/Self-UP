"""
routers/auth.py — 认证接口

POST /api/auth/register  注册新修士
POST /api/auth/login     登录
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth_utils import create_token, hash_password, verify_password
from database import get_db
from models import Cultivator, CultivationStats
from schemas import AuthResponse, LoginRequest, RegisterRequest

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/register", response_model=AuthResponse)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(Cultivator).filter(Cultivator.username == body.username).first():
        raise HTTPException(400, detail="道号已被占用")
    if db.query(Cultivator).filter(Cultivator.email == body.email).first():
        raise HTTPException(400, detail="传音符已被注册")

    cultivator = Cultivator(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
    )
    db.add(cultivator)
    db.flush()  # 获取自增 id

    db.add(CultivationStats(cultivator_id=cultivator.id))
    db.commit()
    db.refresh(cultivator)

    token = create_token(cultivator.id, cultivator.username)
    return AuthResponse(
        access_token=token,
        cultivator_id=cultivator.id,
        username=cultivator.username,
        system_name=cultivator.system_name,
    )


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    cultivator = db.query(Cultivator).filter(Cultivator.username == body.username).first()
    if not cultivator or not verify_password(body.password, cultivator.password_hash):
        raise HTTPException(401, detail="道号或密码有误")

    token = create_token(cultivator.id, cultivator.username)
    return AuthResponse(
        access_token=token,
        cultivator_id=cultivator.id,
        username=cultivator.username,
        system_name=cultivator.system_name,
    )
