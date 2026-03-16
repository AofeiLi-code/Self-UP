import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from database import SessionLocal, init_db
from routers import auth, cultivate, cultivators, dialogue, messages, sects, techniques
from scheduler import init_scheduler, scheduler
from services.sect_service import load_sects_from_yaml

UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)

# 启动时加载 .env（文件不存在时静默跳过）
load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # 从 sects/*.yaml 导入/更新门派数据（幂等，版本相同时跳过）
    _db = SessionLocal()
    try:
        load_sects_from_yaml(_db)
    finally:
        _db.close()
    init_scheduler()
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="Self-UP API", lifespan=lifespan)

# CORS —— 开发环境允许所有来源，生产环境应限制为前端域名
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件：修炼凭证图片
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

# 注册路由
app.include_router(auth.router)
app.include_router(cultivate.router)
app.include_router(cultivators.router)
app.include_router(dialogue.router)
app.include_router(messages.router)
app.include_router(sects.router)
app.include_router(techniques.router)


@app.get("/health")
def health():
    return {"status": "ok", "message": "系统运行中"}
