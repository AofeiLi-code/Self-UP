"""
routers/dialogue.py — 与随身系统对话接口

POST /api/system/dialogue
  接收  : cultivator_id、message
  流程  : 读取修士信息 → 构建 system prompt →
          拼接历史（最近5轮）→ 调用 Claude → 更新内存历史
  返回  : reply（AI 回复）

对话历史仅存内存（dict），重启后清空。
如需持久化，可将 _history 改为写入 system_messages 表。
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ai_client import build_system_prompt, call_claude
from database import get_db
from models import CultivationStats, Cultivator
from schemas import DialogueRequest, DialogueResponse

router = APIRouter(prefix="/api/system", tags=["系统对话"])

# ── 内存对话历史 ────────────────────────────────────────────────
# 结构：{cultivator_id: [{"role": "user"|"assistant", "content": "..."}, ...]}
# 每位修士保留最近 10 条消息（= 5 组 user/assistant 对话）
_history: dict[int, list[dict]] = {}
_MAX_HISTORY = 10  # 5 exchanges × 2 roles


@router.post("/dialogue", response_model=DialogueResponse)
async def dialogue(
    req: DialogueRequest,
    db: Session = Depends(get_db),
) -> DialogueResponse:
    """
    与随身系统对话。

    1. 验证修士和修为面板存在
    2. 构建含人设与当前修为的 system prompt
    3. 拼接最近5轮对话历史 + 本次消息
    4. 调用 Claude 获取回复
    5. 更新内存对话历史（滚动保留最近 _MAX_HISTORY 条）
    """
    # ── 1. 验证修士 ──────────────────────────────────────────────
    cultivator: Cultivator | None = db.get(Cultivator, req.cultivator_id)
    if cultivator is None:
        raise HTTPException(status_code=404, detail="修士不存在")

    stats: CultivationStats | None = db.get(CultivationStats, req.cultivator_id)
    if stats is None:
        raise HTTPException(status_code=404, detail="修为面板不存在，请先完成初始化")

    # ── 2. 构建 system prompt ─────────────────────────────────────
    system_prompt = build_system_prompt(
        system_name=cultivator.system_name,
        system_personality=cultivator.system_personality,
        realm_name=stats.current_realm,
        streak=stats.current_streak,
    )

    # ── 3. 拼接历史 + 当前消息 ───────────────────────────────────
    history = _history.get(req.cultivator_id, [])
    messages = history[-_MAX_HISTORY:] + [
        {"role": "user", "content": req.message}
    ]

    # ── 4. 调用 Claude ────────────────────────────────────────────
    try:
        reply = await call_claude(
            system_prompt=system_prompt,
            messages=messages,
            max_tokens=300,
        )
    except RuntimeError as e:
        # API Key 未配置
        raise HTTPException(status_code=503, detail=str(e))
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="随身系统暂时无响应，请稍后再试",
        )

    # ── 5. 更新内存历史（滚动窗口）───────────────────────────────
    updated = history + [
        {"role": "user", "content": req.message},
        {"role": "assistant", "content": reply},
    ]
    _history[req.cultivator_id] = updated[-_MAX_HISTORY:]

    return DialogueResponse(reply=reply)
