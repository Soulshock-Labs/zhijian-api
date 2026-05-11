"""
小纸笺 · AI幼师助手  —  FastAPI 后端
==========================================
职责：App 工厂 + Router 挂载 + Startup 事件
所有业务逻辑已下沉至 services/ 和 routers/ 模块
"""

from __future__ import annotations

import asyncio
import os

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.settings import APP_VERSION, CORS_ALLOW_ORIGINS
from core.state import logger
from services.webhook_service import _webhook_retry_loop

# ──────────────────────────────────────────────
# App & CORS
# ──────────────────────────────────────────────
app = FastAPI(
    title="小纸笺 API",
    description="AI幼师助手后端服务",
    version=APP_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────
# 路由模块挂载
# ──────────────────────────────────────────────
from routers.planning import router as planning_router
from routers.frontend import router as frontend_router
from routers.system import router as system_router
from routers.ops import router as ops_router
from routers.redeem import router as redeem_router
from routers.users import router as users_router
from routers.templates import router as templates_router
from routers.generate import router as generate_router
from routers.observation import router as observation_router
from routers.mini import router as mini_router
from routers.doc_space import router as doc_space_router

app.include_router(planning_router)
app.include_router(frontend_router)
app.include_router(system_router)
app.include_router(ops_router)
app.include_router(redeem_router)
app.include_router(users_router)
app.include_router(templates_router)
app.include_router(generate_router)
app.include_router(observation_router)
app.include_router(mini_router)
app.include_router(doc_space_router)

# ──────────────────────────────────────────────
# 应用启动事件
# ──────────────────────────────────────────────
@app.on_event("startup")
async def _startup() -> None:
    asyncio.create_task(_webhook_retry_loop())
    logger.info("Webhook 重试任务已启动（每 2 分钟检查一次）")

# ──────────────────────────────────────────────
# 本地启动入口
# ──────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    is_local = port == 8000
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=is_local)
