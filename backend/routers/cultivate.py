"""
routers/cultivate.py — 修炼打卡接口

POST /api/cultivate
  接收  : technique_id (form)、cultivator_id (form)
          photo (可选 file)、note (可选 form)
  流程  : 验证 → 更新streak + 走火入魔惩罚 → 计算实际灵气 → 增减灵气 → 保存记录 → AI反馈
  返回  : spiritual_energy_gained / new_realm / breakthrough /
          current_streak / system_response / penalty_energy / penalty_status

灵气计算规则（LORE.md §3.2）：
  actual_reward = int(base × streak_multiplier) + photo_bonus + note_bonus
  streak_multiplier : 7天×1.1，14天×1.2，30天×1.5，100天×2.0
  photo_bonus       : +10（提交了修炼凭证图片）
  note_bonus        : +5（填写了修炼感悟）
  走火入魔惩罚      : 断修后首次打卡，扣减当前总灵气的 0/5/10/15%
"""

import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ai_client import build_system_prompt, call_claude
from database import get_db
from models import CultivationRecord, CultivationStats, Cultivator, SystemMessage, Technique
from schemas import CultivateResponse, CultivationHistoryRecord, CultivationHistoryResponse
from services.realm_service import add_spiritual_energy, update_streak
from services.sect_service import check_quest_progress

UPLOADS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")

router = APIRouter(prefix="/api", tags=["修炼"])


# ──────────────────────────────────────────────────────────────
# 连击加成倍率（LORE.md §3.2）
# ──────────────────────────────────────────────────────────────

def _streak_multiplier(streak: int) -> float:
    if streak >= 100:
        return 2.0
    if streak >= 30:
        return 1.5
    if streak >= 14:
        return 1.2
    if streak >= 7:
        return 1.1
    return 1.0


@router.post("/cultivate", response_model=CultivateResponse)
async def cultivate(
    cultivator_id: int = Form(..., description="修士ID"),
    technique_id: int = Form(..., description="功法ID"),
    note: Optional[str] = Form(None, description="修炼感悟（可选）"),
    photo: Optional[UploadFile] = File(None, description="修炼凭证图片（可选）"),
    db: Session = Depends(get_db),
) -> CultivateResponse:
    """
    修炼打卡。

    1. 验证功法存在且属于该修士
    2. 更新连续修炼天数，获取走火入魔惩罚信息
    3. 计算实际灵气奖励（含连击倍率、附图/感悟加成）
    4. 先扣走火入魔惩罚，再增加本次奖励（净值传入 add_spiritual_energy）
    5. 保存修炼记录到典籍
    6. 调用 AI 生成系统反馈（失败时使用兜底文本，不影响打卡）
    """
    # ── 1. 验证功法 ──────────────────────────────────────────────
    technique: Technique | None = db.get(Technique, technique_id)
    if technique is None or technique.cultivator_id != cultivator_id:
        raise HTTPException(status_code=404, detail="功法不存在或无权使用")
    if not technique.is_active:
        raise HTTPException(status_code=400, detail="该功法已停修，无法打卡")

    # ── 2. 处理图片：保存到 uploads/{cultivator_id}/{date}_{filename} ──
    photo_url: str | None = None
    if photo and photo.filename:
        cultivator_dir = os.path.join(UPLOADS_DIR, str(cultivator_id))
        os.makedirs(cultivator_dir, exist_ok=True)
        date_prefix = datetime.now().strftime("%Y%m%d")
        safe_name = os.path.basename(photo.filename).replace(" ", "_")
        file_name = f"{date_prefix}_{safe_name}"
        file_path = os.path.join(cultivator_dir, file_name)
        content = await photo.read()
        with open(file_path, "wb") as f:
            f.write(content)
        photo_url = f"/uploads/{cultivator_id}/{file_name}"

    # ── 3. 更新连续修炼天数，获取走火入魔惩罚 ───────────────────
    try:
        streak_result = update_streak(cultivator_id, db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    current_streak = streak_result["current_streak"]
    penalty_pct = streak_result["penalty_pct"]
    penalty_status = streak_result["penalty_status"]

    # ── 4. 计算走火入魔扣减量 ────────────────────────────────────
    penalty_energy = 0
    if penalty_pct > 0:
        stats_now: CultivationStats | None = db.get(CultivationStats, cultivator_id)
        if stats_now is not None:
            penalty_energy = int(stats_now.total_spiritual_energy * penalty_pct / 100)

    # ── 5. 计算本次实际灵气奖励（含加成）────────────────────────
    multiplier = _streak_multiplier(current_streak)
    actual_reward = int(technique.spiritual_energy_reward * multiplier)
    if photo_url:
        actual_reward += 10
    if note and note.strip():
        actual_reward += 5

    # ── 6. 应用净灵气变化（奖励 - 惩罚）────────────────────────
    try:
        energy_result = add_spiritual_energy(
            cultivator_id, actual_reward - penalty_energy, db
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # ── 7. 若气海回流，下发系统消息通知 ─────────────────────────────
    if energy_result.get("overflow_settled", 0) > 0:
        overflow_msg = SystemMessage(
            cultivator_id=cultivator_id,
            technique_id=None,
            message=f"气海灵气回流，获得 {energy_result['overflow_settled']} 灵气",
        )
        db.add(overflow_msg)
        db.flush()

    # ── 8. 保存修炼记录 ──────────────────────────────────────────
    record = CultivationRecord(
        cultivator_id=cultivator_id,
        technique_id=technique_id,
        photo_url=photo_url,
        note=note,
        spiritual_energy_gained=actual_reward,  # 记录毛收益，惩罚另计
    )
    db.add(record)
    db.commit()

    # ── 9. 宗门任务进度检查（非阻塞，失败不影响打卡）──────────────
    try:
        check_quest_progress(cultivator_id, db)
    except Exception:
        pass

    # ── 10. AI 系统反馈（失败时降级为兜底文本）──────────────────
    system_response = await _generate_system_feedback(
        cultivator_id=cultivator_id,
        technique=technique,
        energy_result=energy_result,
        streak=current_streak,
        actual_reward=actual_reward,
        penalty_energy=penalty_energy,
        penalty_status=penalty_status,
        db=db,
    )

    return CultivateResponse(
        spiritual_energy_gained=actual_reward,
        new_realm=energy_result["new_realm"],
        breakthrough=energy_result["breakthrough"],
        current_streak=current_streak,
        system_response=system_response,
        penalty_energy=penalty_energy,
        penalty_status=penalty_status,
        overflow_added=energy_result.get("overflow_added", 0),
        overflow_settled=energy_result.get("overflow_settled", 0),
    )


# ──────────────────────────────────────────────────────────────
# 内部辅助函数
# ──────────────────────────────────────────────────────────────

async def _generate_system_feedback(
    cultivator_id: int,
    technique: Technique,
    energy_result: dict,
    streak: int,
    actual_reward: int,
    penalty_energy: int,
    penalty_status: str | None,
    db: Session,
) -> str:
    """调用 DeepSeek 生成打卡后的系统反馈。任何异常均降级为兜底文本。"""
    try:
        cultivator: Cultivator | None = db.get(Cultivator, cultivator_id)
        if cultivator is None:
            return _fallback(energy_result, actual_reward, penalty_energy)

        system_prompt = build_system_prompt(
            system_name=cultivator.system_name,
            system_personality=cultivator.system_personality,
            realm_name=energy_result["new_realm"],
            streak=streak,
        )

        parts = [
            f"宿主完成了【{technique.name}】（{technique.real_task}），",
            f"获得{actual_reward}灵气",
        ]
        if penalty_energy > 0:
            parts.append(f"（{penalty_status}，扣减{penalty_energy}灵气）")
        parts.append(f"。当前境界：{energy_result['new_realm']}，连续修炼{streak}天。")
        if energy_result["breakthrough"]:
            parts.append(
                f"【大境界突破！"
                f"从{energy_result['old_realm']}晋升至{energy_result['new_realm']}！】"
            )

        return await call_claude(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": "".join(parts)}],
            max_tokens=150,
        )

    except Exception:
        return _fallback(energy_result, actual_reward, penalty_energy)


def _fallback(energy_result: dict, actual_reward: int, penalty_energy: int) -> str:
    """AI 不可用时的兜底系统回复。"""
    if energy_result.get("breakthrough"):
        return (
            f"宿主突破至{energy_result['new_realm']}，本座早有预料。"
            "继续修炼，莫要懈怠。"
        )
    net = actual_reward - penalty_energy
    return f"修炼完成，灵气净增{net}。记录已录入，宿主继续。"


# ──────────────────────────────────────────────────────────────
# GET /api/cultivation/history
# ──────────────────────────────────────────────────────────────

@router.get("/cultivation/history", response_model=CultivationHistoryResponse)
def get_cultivation_history(
    cultivator_id: int,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
) -> CultivationHistoryResponse:
    """返回修士的修炼历史记录（含功法名、图片、感悟），按时间倒序分页。"""
    from sqlalchemy import desc

    offset = (page - 1) * page_size

    total = (
        db.query(CultivationRecord)
        .filter(CultivationRecord.cultivator_id == cultivator_id)
        .count()
    )

    rows = (
        db.query(CultivationRecord, Technique.name)
        .join(Technique, CultivationRecord.technique_id == Technique.id)
        .filter(CultivationRecord.cultivator_id == cultivator_id)
        .order_by(desc(CultivationRecord.cultivated_at))
        .offset(offset)
        .limit(page_size)
        .all()
    )

    records = [
        CultivationHistoryRecord(
            id=rec.id,
            technique_name=name,
            cultivated_at=rec.cultivated_at,
            photo_url=rec.photo_url,
            note=rec.note,
            spiritual_energy_gained=rec.spiritual_energy_gained,
        )
        for rec, name in rows
    ]

    return CultivationHistoryResponse(
        records=records,
        total=total,
        page=page,
        page_size=page_size,
    )
