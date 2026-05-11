"""
routers/planning.py — 周日联动路由（HTTP 薄层）
职责：解析请求、调用 services/planning_service、返回响应。
不包含任何业务逻辑，所有计算在 planning_service 完成。

接口：
    POST /generate-weekly      → 生成五天周计划 JSON
    POST /generate-term-plan   → 园部学期-月-周骨架
    POST /apply-daily-feedback → 日计划反馈回流周计划
    GET  /roadmap              → 模块分期配置
    POST /generate-daily       → 周→日联动导出 Word
    POST /preview-daily        → 日教案 JSON 预览（调试）
"""
from __future__ import annotations

import asyncio
import copy
import io
import json
import os
import re
import time
from typing import Optional
from uuid import uuid4

from docx.opc.exceptions import PackageNotFoundError
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from core.auth import require_permission
from core.settings import MAX_UPLOAD_FILE_SIZE
from core.utils import _read_upload_with_limit
from word_engine.docx_filler import _build_content_disposition
from word_engine.aspose_filler import _export_http_headers
from services.planning_service import (
    generate_weekly_content,
    build_term_month_week_skeleton,
    generate_daily_content,
    fill_daily_word_template,
    _build_daily_structured_docx_bytes,
)
from word_engine.doc_reader import extract_doc_context, to_markdown
from services.doc_space import get_doc_md, get_all_docs_md

router = APIRouter()

# ── 内存 Job Store（单实例 Cloud Run 可用） ──────────────────────────────
_JOB_STORE: dict[str, dict] = {}
_JOB_TTL = 600  # 10 分钟后过期



# ── /generate-weekly ──────────────────────────────────────────────────
@router.post("/generate-weekly", tags=["周日联动"])
async def generate_weekly(
    user_token: str = Form(..., description="登录 token"),
    theme:       str = Form(...,  description="周主题"),
    phil:        str = Form(...,  description="教育理念"),
    activities:  str = Form("[]", description="活动类型列表（JSON）"),
    class_level: str = Form("中班", description="班级（小班/中班/大班）"),
    model:       str = Form("",   description="指定模型，空则使用默认快模型"),
    ref_doc:     Optional[UploadFile] = File(None,  description="临时参考文档（不存储，用完即走）"),
    doc_id:      str = Form("",   description="已存储文档的 ID（从用户空间读取，优先级高于 ref_doc）"),
    scan_space:  str = Form("0",  description="是否扫描用户全部文档空间（1=是）"),
):
    """
    基于主题、理念和班级，自动生成高质量周计划。
    返回 JSON，前端可直接展示，并允许用户选择某一天生成日教案。

    参考文档三种方式（优先级从高到低）：
    1. doc_id    从用户空间读已存储文档的 MD（推荐，无需重复上传）
    2. scan_space=1  扫描用户空间全部文档，拼合注入（Agent 模式）
    3. ref_doc   临时上传文件，用完不存储（兼容旧流程）
    """
    account = require_permission(user_token, "generate")
    account_id = str(account.get("account_id", "")).strip()

    try:
        acts_list: list[str] = json.loads(activities) if activities else []
        if not isinstance(acts_list, list):
            acts_list = [str(acts_list)]
    except (json.JSONDecodeError, TypeError):
        acts_list = [a.strip() for a in activities.split(",") if a.strip()] if activities else []

    ALLOWED_EXTS = {"docx", "pdf", "jpg", "jpeg", "png", "webp", "gif"}
    doc_md = ""
    doc_info: dict = {}

    # ── 优先级 1：从用户空间读已存储文档 ──
    if doc_id.strip():
        md = get_doc_md(account_id, doc_id.strip())
        if md:
            doc_md = md
            doc_info = {"source": "doc_space", "doc_id": doc_id.strip()}
        else:
            doc_info = {"source": "doc_space", "doc_id": doc_id.strip(), "error": "文档不存在"}

    # ── 优先级 2：Agent 扫描全部空间 ──
    elif scan_space.strip() == "1":
        doc_md = get_all_docs_md(account_id)
        doc_info = {"source": "space_scan", "user_id": account_id}

    # ── 优先级 3：临时上传（兼容旧流程） ──
    elif ref_doc is not None:
        filename = ref_doc.filename or ""
        ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
        if ext not in ALLOWED_EXTS:
            raise HTTPException(
                status_code=400,
                detail="参考文件仅支持 .docx、.pdf、.jpg、.jpeg、.png、.webp 格式",
            )
        file_bytes = await _read_upload_with_limit(ref_doc, MAX_UPLOAD_FILE_SIZE)
        ctx = extract_doc_context(file_bytes, filename)
        if ctx.ok:
            doc_md = to_markdown(ctx)
            doc_info = {
                "source":      "temp_upload",
                "filename":    ctx.filename,
                "file_type":   ctx.file_type,
                "char_count":  ctx.char_count,
                "table_count": ctx.table_count,
            }
        else:
            doc_info = {"source": "temp_upload", "filename": filename, "error": ctx.error}

    plan = generate_weekly_content(theme, phil, acts_list, class_level, model=model, doc_md=doc_md)
    resp: dict = {"status": "ok", "weekly_plan": plan}
    if doc_info:
        resp["doc_analyzed"] = doc_info
    return resp


# ── /generate-term-plan ───────────────────────────────────────────────
@router.post("/generate-term-plan", tags=["园部计划"])
async def generate_term_plan(
    user_token:  str = Form(..., description="登录 token"),
    term_theme:  str = Form(..., description="学期主题"),
    start_month: int = Form(2,   description="起始月份（1-12）"),
    month_count: int = Form(5,   description="学期月数（1-6）"),
):
    """园部计划骨架生成：输出学期→月→周三级结构。"""
    require_permission(user_token, "generate")
    if not (1 <= start_month <= 12):
        raise HTTPException(status_code=400, detail="start_month 必须在 1-12 之间")
    skeleton = build_term_month_week_skeleton(term_theme, start_month, month_count)
    return {"status": "ok", "term_plan": skeleton}


# ── /apply-daily-feedback ─────────────────────────────────────────────
@router.post("/apply-daily-feedback", tags=["周日联动"])
async def apply_daily_feedback(
    user_token:         str = Form(..., description="登录 token"),
    weekly_plan:       str = Form(..., description="周计划 JSON"),
    day:               str = Form(..., description="目标星期，如 周一"),
    completion_score:  int = Form(..., description="执行完成度（1-5）"),
    highlights:        str = Form("",  description="今日亮点"),
    risks:             str = Form("",  description="风险与问题"),
    adjust_suggestion: str = Form("",  description="下次调整建议"),
):
    """
    日计划执行后反馈回流周计划：
    将某天的完成度与复盘意见写回 weekly_plan，形成可迭代闭环。
    """
    require_permission(user_token, "generate")
    if not (1 <= completion_score <= 5):
        raise HTTPException(status_code=400, detail="completion_score 必须在 1-5 之间")
    try:
        plan: dict = json.loads(weekly_plan)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="weekly_plan 不是合法 JSON")

    days: list[dict] = plan.get("days", [])
    target_idx = next((i for i, d in enumerate(days) if d.get("day") == day), None)
    if target_idx is None:
        raise HTTPException(status_code=400, detail=f"未找到目标日期：{day}")

    day_item = copy.deepcopy(days[target_idx])
    day_item["execution_feedback"] = {
        "completion_score": completion_score,
        "highlights":       highlights.strip(),
        "risks":            risks.strip(),
        "adjust_suggestion": adjust_suggestion.strip(),
    }
    day_item["status"] = "reviewed"
    days[target_idx]   = day_item
    plan["days"]       = days

    return {"status": "ok", "updated_weekly_plan": plan, "updated_day": day_item}


# ── /roadmap ──────────────────────────────────────────────────────────
@router.get("/roadmap", tags=["版本规划"])
async def roadmap():
    """模块分期配置：P0 已落地，P1/P2 预留，供前端展示与后续接口扩展。"""
    return {
        "status":  "ok",
        "version": "v1.2.0",
        "tracks": {
            "to_b": [
                {"module": "模块1 园部学期-月-周计划",  "phase": "P0", "status": "ready"},
                {"module": "模块4 幼儿成长中台",        "phase": "P1", "status": "reserved"},
                {"module": "模块6 家园沟通中台",        "phase": "P1", "status": "reserved"},
                {"module": "模块7 教师发展中台",        "phase": "P2", "status": "reserved"},
            ],
            "to_c": [
                {"module": "模块2 日计划生成与调整并回流周计划", "phase": "P0", "status": "ready"},
                {"module": "模块3 拍照观察与现场记录",           "phase": "P0", "status": "ready"},
                {"module": "模块5 多场景活动引擎",               "phase": "P2", "status": "reserved"},
                {"module": "模块7 教师个人档案与成长",           "phase": "P2", "status": "reserved"},
            ],
        },
    }


# ── /generate-daily ───────────────────────────────────────────────────
@router.post("/generate-daily", tags=["周日联动"])
async def generate_daily(
    user_token:  str            = Form(..., description="登录 token"),
    weekly_plan: str            = Form(..., description="周计划 JSON（由 /generate-weekly 返回或前端暂存）"),
    day:         str            = Form(..., description="目标星期，如 周一"),
    phil:        str            = Form(..., description="教育理念"),
    template:    Optional[UploadFile] = File(None, description="日教案 Word 模板 (.docx，可选)"),
):
    """
    周→日联动：将周计划中某一天拆解为四维日教案并导出 Word。

    四维结构：**导入**（情境激活）→ **过程**（分步操作）→ **延伸**（区域/家园）→ **反思**（观察要点）

    · 有模板：识别模板关键字单元格并回填
    · 无模板：生成结构化（非表格）日计划文档
    """
    require_permission(user_token, "generate")
    template_bytes: Optional[bytes] = None
    if template is not None:
        if not (template.filename or "").lower().endswith(".docx"):
            raise HTTPException(status_code=400, detail="仅支持 .docx 格式")
        template_bytes = await _read_upload_with_limit(template, MAX_UPLOAD_FILE_SIZE)

    try:
        plan: dict = json.loads(weekly_plan)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="weekly_plan 不是合法 JSON")

    days: list[dict] = plan.get("days", [])
    target = next((d for d in days if d.get("day") == day), None)
    if not target:
        raise HTTPException(
            status_code=400,
            detail=f"在周计划中未找到「{day}」，可用值：{[d.get('day') for d in days]}",
        )

    week_theme = plan.get("week_theme", "本周主题")
    task = (
        target.get("task")
        or target.get("activity_name")
        or target.get("title")
        or target.get("domain")
        or day
    )

    daily_content = generate_daily_content(
        week_theme=week_theme,
        day=day,
        task=task,
        phil=phil,
    )

    if template_bytes:
        try:
            filled_bytes, export_engine = fill_daily_word_template(
                template_bytes=template_bytes,
                daily_content=daily_content,
                week_theme=week_theme,
                day=day,
                phil=phil,
            )
        except PackageNotFoundError:
            raise HTTPException(status_code=400, detail="模板解析失败，请确认上传的是有效 .docx 文件")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"日教案模板填充失败：{e}")
        original_name = os.path.basename(template.filename or "daily-template.docx")
        original_name = re.sub(r'[\\/*?:"<>|]+', "_", original_name)
        if not original_name.lower().endswith(".docx"):
            original_name += ".docx"
    else:
        filled_bytes  = _build_daily_structured_docx_bytes(
            daily_content=daily_content,
            week_theme=week_theme,
            day=day,
            phil=phil,
            source_day=target,
        )
        export_engine = "python-docx-structured"
        original_name = re.sub(r'[\\/*?:"<>|]+', "_", f"{week_theme}_{day}_日计划.docx")

    h = {"Content-Disposition": _build_content_disposition(original_name)}
    h.update(_export_http_headers(export_engine))
    return StreamingResponse(
        io.BytesIO(filled_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=h,
    )


# ── /preview-daily ────────────────────────────────────────────────────
@router.post("/preview-daily", tags=["调试"])
async def preview_daily(
    user_token: str = Form(..., description="登录 token"),
    weekly_plan: str = Form(...),
    day:         str = Form(...),
    phil:        str = Form(...),
):
    """返回日教案 AI 内容 JSON，用于前端预览调试（不生成 Word）。"""
    require_permission(user_token, "generate")
    try:
        plan = json.loads(weekly_plan)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="weekly_plan 不是合法 JSON")
    days   = plan.get("days", [])
    target = next((d for d in days if d.get("day") == day), None)
    if not target:
        raise HTTPException(status_code=400, detail=f"未找到「{day}」")
    content = generate_daily_content(
        week_theme=plan.get("week_theme", ""),
        day=day,
        task=target.get("task", ""),
        phil=phil,
    )
    return {"status": "ok", "day": day, "task": target.get("task"), "content": content}


# ── /generate-weekly-job（异步 Job 版） ───────────────────────────────────
@router.post("/generate-weekly-job", tags=["周日联动"])
async def start_generate_weekly_job(
    user_token:  str = Form(..., description="登录 token"),
    theme:       str = Form(...,  description="周主题"),
    phil:        str = Form(...,  description="教育理念"),
    activities:  str = Form("[]", description="活动类型列表（JSON）"),
    class_level: str = Form("中班", description="班级（小班/中班/大班）"),
    model:       str = Form("",   description="指定模型，空则使用默认"),
    ref_doc:     Optional[UploadFile] = File(None, description="参考文档（可选）"),
):
    """启动异步周计划生成任务，立即返回 job_id，前端轮询 /generation-jobs/{job_id}。"""
    account = require_permission(user_token, "generate")
    account_id = str(account.get("account_id", "")).strip()

    try:
        acts_list: list[str] = json.loads(activities) if activities else []
        if not isinstance(acts_list, list):
            acts_list = []
    except (json.JSONDecodeError, TypeError):
        acts_list = []

    # 提前读文件（UploadFile 只能在请求生命周期内读取）
    doc_md = ""
    if ref_doc is not None:
        filename = ref_doc.filename or ""
        ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
        ALLOWED_EXTS = {"docx", "pdf", "jpg", "jpeg", "png", "webp", "gif"}
        if ext in ALLOWED_EXTS:
            file_bytes = await _read_upload_with_limit(ref_doc, MAX_UPLOAD_FILE_SIZE)
            ctx = extract_doc_context(file_bytes, filename)
            if ctx.ok:
                doc_md = to_markdown(ctx)

    job_id = f"wj_{uuid4().hex[:12]}"
    _JOB_STORE[job_id] = {
        "status": "running",
        "job_id": job_id,
        "type": "weekly",
        "started_at": time.time(),
        "progress": 5,
    }

    # 清理过期 job（顺手，不阻塞）
    now = time.time()
    expired = [k for k, v in _JOB_STORE.items() if now - v.get("started_at", now) > _JOB_TTL]
    for k in expired:
        _JOB_STORE.pop(k, None)

    async def _run_job():
        t0 = time.time()
        try:
            loop = asyncio.get_event_loop()
            plan = await loop.run_in_executor(
                None,
                lambda: generate_weekly_content(theme, phil, acts_list, class_level, model=model, doc_md=doc_md),
            )
            _JOB_STORE[job_id].update({
                "status": "success",
                "progress": 100,
                "elapsed_seconds": round(time.time() - t0, 1),
                "result": {"status": "ok", "weekly_plan": plan},
            })
        except Exception as exc:
            _JOB_STORE[job_id].update({
                "status": "error",
                "error": str(exc),
                "elapsed_seconds": round(time.time() - t0, 1),
            })

    asyncio.create_task(_run_job())
    return {"status": "ok", "job_id": job_id}


# ── /generation-jobs/{job_id}（轮询） ────────────────────────────────────
@router.get("/generation-jobs/{job_id}", tags=["周日联动"])
async def get_generation_job(job_id: str, user_token: str):
    """轮询任务状态。status: running / success / error。"""
    require_permission(user_token, "generate")
    job = _JOB_STORE.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    elapsed = round(time.time() - job.get("started_at", time.time()), 1)
    progress = job.get("progress", 5)
    if job["status"] == "running":
        # 基于时间估算进度（周计划通常 15-30 秒）
        progress = min(90, max(progress, int(elapsed / 25 * 90)))
        _JOB_STORE[job_id]["progress"] = progress
    return {
        **job,
        "elapsed_seconds": job.get("elapsed_seconds", elapsed),
        "progress": progress,
    }


# ── /generations（最近生成记录） ─────────────────────────────────────────
@router.get("/generations", tags=["历史记录"])
async def list_generations(user_token: str, limit: int = 20):
    """返回最近生成记录列表（当前仅返回内存中的 job 快照）。"""
    require_permission(user_token, "generate")
    records = []
    for job in sorted(_JOB_STORE.values(), key=lambda j: j.get("started_at", 0), reverse=True):
        if job.get("status") == "success":
            records.append({
                "record_id": job["job_id"],
                "type": job.get("type", "weekly"),
                "status": "success",
                "title": job.get("result", {}).get("weekly_plan", {}).get("week_theme", ""),
                "duration_ms": int(job.get("elapsed_seconds", 0) * 1000),
            })
        if len(records) >= limit:
            break
    return {"status": "ok", "records": records, "total": len(records)}
