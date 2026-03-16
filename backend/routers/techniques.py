"""
routers/techniques.py — 功法接口

GET    /api/techniques?cultivator_id=xxx                   列出功法（含今日是否已修炼）
POST   /api/techniques                                     新增功法（含天道定价校验）
POST   /api/techniques/evaluate                            AI 灵气定价评估
PUT    /api/techniques/{technique_id}?cultivator_id=xxx    修改功法
DELETE /api/techniques/{technique_id}?cultivator_id=xxx    废弃功法（软删除）
"""

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ai_client import call_claude
from database import get_db
from models import Cultivator, CultivationRecord, SectMember, Technique
from schemas import (
    ClearInactiveTechniquesResponse,
    DeleteTechniqueResponse,
    EvaluateTechniqueRequest,
    EvaluateTechniqueResponse,
    TechniqueCreate,
    TechniqueOut,
    TechniqueUpdate,
)
from scheduler import register_technique_job

router = APIRouter(prefix="/api/techniques", tags=["功法"])

# AI 定价评估的 system prompt（LORE.md §3.2）
_EVALUATE_SYSTEM_PROMPT = """\
分析以下修炼任务的合理灵气奖励值，范围限定在 20-150 之间。

评估维度：
1. 时间成本（5分钟 vs 1小时以上）
2. 体力或脑力消耗程度
3. 是否需要出门或外部条件
4. 长期坚持的难度
5. 对身心健康的实际价值

只返回 JSON，不要任何其他文字：
{
  "suggested_reward": 60,
  "min_allowed": 54,
  "max_allowed": 66,
  "reasoning": "中等强度有氧运动，耗时约40分钟，需要出门，坚持难度中等"
}

min_allowed 和 max_allowed 是 suggested_reward 的 ±10%，向下取整。\
"""


@router.post("/evaluate", response_model=EvaluateTechniqueResponse)
async def evaluate_technique(body: EvaluateTechniqueRequest):
    """调用 AI 对功法进行灵气定价评估，返回建议值及允许范围。"""
    user_content = f"功法名：{body.name}\n现实任务：{body.real_task}"
    try:
        raw = await call_claude(
            system_prompt=_EVALUATE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
            max_tokens=200,
        )
        # 剥离可能的 markdown 代码块
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            parts = cleaned.split("```")
            cleaned = parts[1] if len(parts) > 1 else parts[0]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()
        data = json.loads(cleaned)
        return EvaluateTechniqueResponse(**data)
    except Exception:
        raise HTTPException(status_code=500, detail="AI定价服务暂时不可用，请稍后重试")


@router.get("", response_model=list[TechniqueOut])
def list_techniques(
    cultivator_id: int = Query(..., description="修士ID"),
    include_inactive: bool = Query(False, description="是否包含已废弃功法"),
    db: Session = Depends(get_db),
):
    query = db.query(Technique).filter(Technique.cultivator_id == cultivator_id)
    if not include_inactive:
        query = query.filter(Technique.is_active == True)  # noqa: E712
    techniques = query.all()

    today = date.today().isoformat()
    result = []
    for tech in techniques:
        completed_today = (
            db.query(CultivationRecord)
            .filter(
                CultivationRecord.technique_id == tech.id,
                func.date(CultivationRecord.cultivated_at) == today,
            )
            .first()
        ) is not None
        result.append(TechniqueOut(
            id=tech.id,
            name=tech.name,
            real_task=tech.real_task,
            scheduled_time=tech.scheduled_time,
            spiritual_energy_reward=tech.spiritual_energy_reward,
            completed_today=completed_today,
            is_active=tech.is_active,
            added_by_sect_id=tech.added_by_sect_id,
            spiritual_energy_ai_suggested=tech.spiritual_energy_ai_suggested,
            spiritual_energy_min_allowed=tech.spiritual_energy_min_allowed,
            spiritual_energy_max_allowed=tech.spiritual_energy_max_allowed,
        ))
    return result


@router.post("", response_model=TechniqueOut, status_code=201)
def create_technique(body: TechniqueCreate, db: Session = Depends(get_db)):
    if not db.get(Cultivator, body.cultivator_id):
        raise HTTPException(404, detail="修士不存在")

    # 天道定价校验：若提供了允许范围，奖励值必须在区间内
    if body.spiritual_energy_min_allowed is not None and body.spiritual_energy_max_allowed is not None:
        if not (body.spiritual_energy_min_allowed <= body.spiritual_energy_reward <= body.spiritual_energy_max_allowed):
            raise HTTPException(400, detail="灵气定价超出天道允许范围")

    tech = Technique(
        cultivator_id=body.cultivator_id,
        name=body.name,
        real_task=body.real_task,
        scheduled_time=body.scheduled_time,
        spiritual_energy_reward=body.spiritual_energy_reward,
        spiritual_energy_ai_suggested=body.spiritual_energy_ai_suggested,
        spiritual_energy_min_allowed=body.spiritual_energy_min_allowed,
        spiritual_energy_max_allowed=body.spiritual_energy_max_allowed,
    )
    db.add(tech)
    db.commit()
    db.refresh(tech)

    # 有修炼时刻则立即注册定时督促任务
    if tech.scheduled_time:
        register_technique_job(tech.id, tech.name, tech.scheduled_time)

    return TechniqueOut(
        id=tech.id,
        name=tech.name,
        real_task=tech.real_task,
        scheduled_time=tech.scheduled_time,
        spiritual_energy_reward=tech.spiritual_energy_reward,
        completed_today=False,
        is_active=True,
        added_by_sect_id=tech.added_by_sect_id,
        spiritual_energy_ai_suggested=tech.spiritual_energy_ai_suggested,
        spiritual_energy_min_allowed=tech.spiritual_energy_min_allowed,
        spiritual_energy_max_allowed=tech.spiritual_energy_max_allowed,
    )


@router.put("/{technique_id}", response_model=TechniqueOut)
def update_technique(
    technique_id: int,
    body: TechniqueUpdate,
    cultivator_id: int = Query(..., description="修士ID（权限校验）"),
    db: Session = Depends(get_db),
):
    """
    修改功法信息。

    规则：
    - 只能修改属于自己的功法（cultivator_id 校验）
    - 宗门自动添加的功法（added_by_sect_id 不为空）不可修改灵气值
    - 修改灵气值时必须同时提供 AI 定价范围，且值须在允许范围内
    - is_active=True 可用于恢复已废弃的功法
    """
    tech: Technique | None = db.get(Technique, technique_id)
    if tech is None or tech.cultivator_id != cultivator_id:
        raise HTTPException(404, detail="功法不存在或无权修改")

    is_sect_tech = tech.added_by_sect_id is not None

    # 宗门功法禁止修改灵气值
    if is_sect_tech and body.spiritual_energy_reward is not None:
        raise HTTPException(400, detail="宗门功法灵气值不可修改，随离宗自动调整")

    # 修改灵气值：需提供定价范围，且值须在范围内
    if body.spiritual_energy_reward is not None:
        min_v = body.spiritual_energy_min_allowed or tech.spiritual_energy_min_allowed
        max_v = body.spiritual_energy_max_allowed or tech.spiritual_energy_max_allowed
        if min_v is not None and max_v is not None:
            if not (min_v <= body.spiritual_energy_reward <= max_v):
                raise HTTPException(400, detail="灵气定价超出天道允许范围")

    # 应用字段更新
    if body.name is not None:
        tech.name = body.name
    if body.real_task is not None:
        tech.real_task = body.real_task
    if body.scheduled_time is not None:
        tech.scheduled_time = body.scheduled_time
    if body.is_active is not None:
        tech.is_active = body.is_active
    if body.spiritual_energy_reward is not None:
        tech.spiritual_energy_reward = body.spiritual_energy_reward
    if body.spiritual_energy_ai_suggested is not None:
        tech.spiritual_energy_ai_suggested = body.spiritual_energy_ai_suggested
    if body.spiritual_energy_min_allowed is not None:
        tech.spiritual_energy_min_allowed = body.spiritual_energy_min_allowed
    if body.spiritual_energy_max_allowed is not None:
        tech.spiritual_energy_max_allowed = body.spiritual_energy_max_allowed

    db.commit()
    db.refresh(tech)

    today = date.today().isoformat()
    completed_today = (
        db.query(CultivationRecord)
        .filter(
            CultivationRecord.technique_id == tech.id,
            func.date(CultivationRecord.cultivated_at) == today,
        )
        .first()
    ) is not None

    return TechniqueOut(
        id=tech.id,
        name=tech.name,
        real_task=tech.real_task,
        scheduled_time=tech.scheduled_time,
        spiritual_energy_reward=tech.spiritual_energy_reward,
        completed_today=completed_today,
        is_active=tech.is_active,
        added_by_sect_id=tech.added_by_sect_id,
        spiritual_energy_ai_suggested=tech.spiritual_energy_ai_suggested,
        spiritual_energy_min_allowed=tech.spiritual_energy_min_allowed,
        spiritual_energy_max_allowed=tech.spiritual_energy_max_allowed,
    )


@router.delete("/inactive", response_model=ClearInactiveTechniquesResponse)
def clear_inactive_techniques(
    cultivator_id: int = Query(..., description="修士ID"),
    db: Session = Depends(get_db),
):
    """
    永久删除修士所有已废弃的功法及其历史记录。

    - 正式宗门自动添加的功法无法清空（需离宗后再操作）
    - 注意：关联的修炼历史记录会一并删除（不可恢复）
    """
    inactive = (
        db.query(Technique)
        .filter(
            Technique.cultivator_id == cultivator_id,
            Technique.is_active == False,  # noqa: E712
        )
        .all()
    )

    cleared_count = 0
    skipped_names: list[str] = []

    for tech in inactive:
        if tech.added_by_sect_id is not None:
            active_membership = db.query(SectMember).filter(
                SectMember.cultivator_id == cultivator_id,
                SectMember.sect_id == tech.added_by_sect_id,
                SectMember.is_active == True,  # noqa: E712
            ).first()
            if active_membership is not None and active_membership.membership_type == "formal":
                skipped_names.append(tech.name)
                continue

        db.delete(tech)
        cleared_count += 1

    db.commit()

    return ClearInactiveTechniquesResponse(
        cleared=cleared_count,
        skipped=len(skipped_names),
        skipped_names=skipped_names,
    )


@router.delete("/{technique_id}", response_model=DeleteTechniqueResponse)
def delete_technique(
    technique_id: int,
    cultivator_id: int = Query(..., description="修士ID（权限校验）"),
    db: Session = Depends(get_db),
):
    """
    废弃功法（软删除）。

    - 只能废弃属于自己的功法
    - 宗门自动添加的功法不可单独废弃（需通过离宗移除）
    - 历史修炼记录完整保留
    """
    tech: Technique | None = db.get(Technique, technique_id)
    if tech is None or tech.cultivator_id != cultivator_id:
        raise HTTPException(404, detail="功法不存在或无权操作")

    if tech.added_by_sect_id is not None:
        # 正式弟子的宗门功法禁止单独删除；游历修士手动添加的可删除
        active_membership = db.query(SectMember).filter(
            SectMember.cultivator_id == cultivator_id,
            SectMember.sect_id == tech.added_by_sect_id,
            SectMember.is_active == True,  # noqa: E712
        ).first()
        if active_membership is not None and active_membership.membership_type == "formal":
            raise HTTPException(400, detail="宗门功法需通过离宗方式移除")

    tech.is_active = False
    db.commit()

    return DeleteTechniqueResponse(success=True, message="功法已废弃")
