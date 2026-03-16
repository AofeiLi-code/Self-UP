"""
routers/sects.py — 门派相关 API

GET  /api/sects                                   列出所有可用门派，标注当前修士的成员类型
GET  /api/sects/memberships                       获取修士当前所有门派关系（正式+游历）
POST /api/sects/join                              加入门派（正式弟子/游历修士双轨）
POST /api/sects/leave                             退出指定门派
GET  /api/sects/resources?cultivator_id=          获取已解锁的门派秘籍及未解锁计数
GET  /api/sects/{sect_id}/quests?cultivator_id=   获取宗门任务列表（含修士进度）
GET  /api/sects/{sect_id}/techniques?cultivator_id=  获取宗门功法列表（含是否已添加）
POST /api/sects/{sect_id}/techniques/add          添加宗门功法到功课（游历修士可用）
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ai_client import build_system_prompt, call_claude
from database import get_db
from models import Cultivator, CultivationStats, Sect, SectMember, SystemMessage
from schemas import (
    AddSectTechniqueRequest,
    AddSectTechniqueResponse,
    CultivatorSectMemberInfo,
    CultivatorSectsResponse,
    JoinSectRequest,
    JoinSectResponse,
    LeaveSectRequest,
    LeaveSectResponse,
    QuestOut,
    SectOut,
    SectQuestsResponse,
    SectResourceOut,
    SectResourcesResponse,
    SectTechniqueOut,
    SectTechniquesResponse,
    SectsResponse,
)
from services.sect_service import (
    add_sect_technique,
    get_active_quests,
    get_all_resources,
    get_available_sects,
    get_cultivator_sects,
    get_sect_techniques,
    join_sect,
    leave_sect,
)

router = APIRouter(prefix="/api/sects", tags=["门派"])


# ──────────────────────────────────────────────────────────────
# GET /api/sects
# ──────────────────────────────────────────────────────────────

@router.get("", response_model=SectsResponse)
def list_sects(
    cultivator_id: Optional[int] = Query(None, description="修士ID（用于标注成员类型）"),
    db: Session = Depends(get_db),
) -> SectsResponse:
    """
    返回所有 is_active=True 的门派列表。
    传入 cultivator_id 时，membership_type 字段标注该修士与每个门派的关系
    （None=未加入, 'formal'=正式弟子, 'visiting'=游历修士）。
    """
    sects_data = get_available_sects(db)

    # 构建 {sect_pk → membership_type} 映射
    membership_map: dict[int, str] = {}
    if cultivator_id is not None:
        memberships = (
            db.query(SectMember)
            .filter(
                SectMember.cultivator_id == cultivator_id,
                SectMember.is_active == True,  # noqa: E712
            )
            .all()
        )
        for m in memberships:
            membership_map[m.sect_id] = m.membership_type

    return SectsResponse(
        sects=[
            SectOut(
                id=s["id"],
                sect_id=s["sect_id"],
                name=s["name"],
                tagline=s["tagline"],
                focus=s["focus"],
                difficulty=s["difficulty"],
                recommended_for=s["recommended_for"],
                membership_type=membership_map.get(s["id"]),
            )
            for s in sects_data
        ]
    )


# ──────────────────────────────────────────────────────────────
# GET /api/sects/memberships
# ──────────────────────────────────────────────────────────────

@router.get("/memberships", response_model=CultivatorSectsResponse)
def get_memberships(
    cultivator_id: int = Query(..., description="修士ID"),
    db: Session = Depends(get_db),
) -> CultivatorSectsResponse:
    """返回修士当前所有门派关系（正式宗门 + 游历宗门列表）。"""
    data = get_cultivator_sects(cultivator_id, db)

    formal_info = None
    if data["formal"]:
        f = data["formal"]
        formal_info = CultivatorSectMemberInfo(
            sect_id=f["sect_id"],
            name=f["name"],
            joined_at=f["joined_at"],
            days_in_sect=f["days_in_sect"],
        )

    visiting_list = [
        CultivatorSectMemberInfo(
            sect_id=v["sect_id"],
            name=v["name"],
            joined_at=v["joined_at"],
            days_in_sect=v["days_in_sect"],
        )
        for v in data["visiting"]
    ]

    return CultivatorSectsResponse(formal=formal_info, visiting=visiting_list)


# ──────────────────────────────────────────────────────────────
# POST /api/sects/join
# ──────────────────────────────────────────────────────────────

@router.post("/join", response_model=JoinSectResponse)
async def join_sect_endpoint(
    req: JoinSectRequest,
    db: Session = Depends(get_db),
) -> JoinSectResponse:
    """
    修士加入指定门派（正式弟子或游历修士）。

    formal：
      - 自动添加门派功法
      - AI 生成入宗欢迎消息并写入 system_messages

    visiting：
      - 不添加功法，不注册推送
      - 简短欢迎提示（无 AI 调用）
    """
    try:
        result = join_sect(req.cultivator_id, req.sect_id, req.membership_type, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    sect: Sect = db.query(Sect).filter(Sect.sect_id == req.sect_id).first()  # type: ignore[assignment]

    from schemas import SectTechniqueItem

    if req.membership_type == "formal":
        welcome_message = await _generate_welcome_message(req.cultivator_id, sect, db)
        # 写入系统消息
        db.add(SystemMessage(
            cultivator_id=req.cultivator_id,
            message=welcome_message,
            sent_at=datetime.now(),
        ))
        db.commit()
        available_techniques = []
    else:
        avail = result.get("available_techniques", [])
        welcome_message = (
            f"宿主已登记为{sect.name}游历修士，可阅览入门典籍，观摩门派修炼之道。"
            + (f"本宗共有{len(avail)}门功法可自行选修，加入功课后按常规打卡即可获得灵气。" if avail else "")
        )
        available_techniques = [
            SectTechniqueItem(
                name=t["name"],
                real_task=t["real_task"],
                spiritual_energy_reward=t["spiritual_energy_reward"],
            )
            for t in avail
        ]

    return JoinSectResponse(
        success=True,
        welcome_message=welcome_message,
        added_techniques=result["added_techniques"],
        membership_type=result["membership_type"],
        available_techniques=available_techniques,
    )


# ──────────────────────────────────────────────────────────────
# POST /api/sects/leave
# ──────────────────────────────────────────────────────────────

@router.post("/leave", response_model=LeaveSectResponse)
def leave_sect_endpoint(
    req: LeaveSectRequest,
    db: Session = Depends(get_db),
) -> LeaveSectResponse:
    """退出指定门派（sect_id 为 YAML ID），软删除门派功法（仅正式弟子），保留修炼记录。"""
    result = leave_sect(req.cultivator_id, req.sect_id, db)
    return LeaveSectResponse(success=result["success"])


# ──────────────────────────────────────────────────────────────
# GET /api/sects/resources
# ──────────────────────────────────────────────────────────────

@router.get("/resources", response_model=SectResourcesResponse)
def get_sect_resources(
    cultivator_id: int = Query(..., description="修士ID"),
    sect_id: Optional[str] = Query(None, description="宗门YAML ID（游历时可指定查看的宗门）"),
    db: Session = Depends(get_db),
) -> SectResourcesResponse:
    """
    返回修士指定宗门的全部秘籍（不再按境界锁定，附带推荐状态）。
    传入 sect_id 可查看游历宗门的秘籍。
    """
    data = get_all_resources(cultivator_id, db, sect_str_id=sect_id)

    return SectResourcesResponse(
        sect_name=data["sect_name"],
        cultivator_realm=data["cultivator_realm"],
        membership_type=data.get("membership_type", "formal"),
        resources=[
            SectResourceOut(
                id=r["id"],
                resource_id=r["resource_id"],
                title=r["title"],
                type=r["type"],
                content=r["content"],
                url=r["url"],
                recommended_realm=r["recommended_realm"],
                is_recommended=r["is_recommended"],
                can_access=r["can_access"],
            )
            for r in data["resources"]
        ],
        recommended_count=data.get("recommended_count", 0),
    )


# ──────────────────────────────────────────────────────────────
# GET /api/sects/{sect_id}/quests
# ──────────────────────────────────────────────────────────────

@router.get("/{sect_id}/quests", response_model=SectQuestsResponse)
def get_sect_quests(
    sect_id: str,
    cultivator_id: int = Query(..., description="修士ID"),
    db: Session = Depends(get_db),
) -> SectQuestsResponse:
    """
    返回指定宗门的任务列表（附带修士当前进度和参与权限）。

    - formal 成员：所有任务均可参与
    - visiting 成员：特别任务（reward_title 不为空）can_participate=False
    """
    try:
        data = get_active_quests(cultivator_id, sect_id, db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return SectQuestsResponse(
        sect_name=data["sect_name"],
        sect_id=data["sect_id"],
        membership_type=data["membership_type"],
        quests=[
            QuestOut(
                quest_id=q["quest_id"],
                title=q["title"],
                description=q["description"],
                type=q["type"],
                reward_spiritual_energy=q["reward_spiritual_energy"],
                reward_title=q["reward_title"],
                criteria_type=q["criteria_type"],
                criteria_target=q["criteria_target"],
                current_progress=q["current_progress"],
                is_completed=q["is_completed"],
                can_participate=q["can_participate"],
                restrict_reason=q["restrict_reason"],
            )
            for q in data["quests"]
        ],
    )


# ──────────────────────────────────────────────────────────────
# GET /api/sects/{sect_id}/techniques
# ──────────────────────────────────────────────────────────────

@router.get("/{sect_id}/techniques", response_model=SectTechniquesResponse)
def get_sect_techniques_endpoint(
    sect_id: str,
    cultivator_id: int = Query(..., description="修士ID"),
    db: Session = Depends(get_db),
) -> SectTechniquesResponse:
    """
    返回指定宗门的功法列表，附带修士是否已添加。

    - 正式弟子：所有功法 is_added=True（加入时自动添加）
    - 游历修士：is_added 取决于是否手动添加过
    """
    sect: Sect | None = db.query(Sect).filter(Sect.sect_id == sect_id).first()
    if sect is None:
        raise HTTPException(status_code=404, detail="门派不存在")

    membership = (
        db.query(SectMember)
        .filter(
            SectMember.cultivator_id == cultivator_id,
            SectMember.sect_id == sect.id,
            SectMember.is_active == True,  # noqa: E712
        )
        .first()
    )
    if membership is None:
        raise HTTPException(status_code=403, detail="宿主未加入该门派")

    techniques = get_sect_techniques(cultivator_id, sect_id, db)
    return SectTechniquesResponse(
        sect_name=sect.name,
        membership_type=membership.membership_type,
        techniques=[
            SectTechniqueOut(
                name=t["name"],
                real_task=t["real_task"],
                scheduled_time=t.get("scheduled_time"),
                spiritual_energy_reward=t["spiritual_energy_reward"],
                is_added=t["is_added"],
            )
            for t in techniques
        ],
    )


# ──────────────────────────────────────────────────────────────
# POST /api/sects/{sect_id}/techniques/add
# ──────────────────────────────────────────────────────────────

@router.post("/{sect_id}/techniques/add", response_model=AddSectTechniqueResponse)
def add_sect_technique_endpoint(
    sect_id: str,
    req: AddSectTechniqueRequest,
    db: Session = Depends(get_db),
) -> AddSectTechniqueResponse:
    """
    游历修士手动将宗门功法添加到个人功课。
    正式弟子的功法在加入时已自动添加，无需此接口。
    """
    try:
        result = add_sect_technique(req.cultivator_id, sect_id, req.technique_name, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return AddSectTechniqueResponse(
        success=True,
        technique_name=result["name"],
        message=f"功法「{result['name']}」已加入功课",
    )


# ──────────────────────────────────────────────────────────────
# 内部辅助
# ──────────────────────────────────────────────────────────────

async def _generate_welcome_message(
    cultivator_id: int,
    sect: Sect,
    db: Session,
) -> str:
    """
    调用 AI 生成正式入宗欢迎消息（LORE.md §4.5 场景：打卡成功/突破语气）。
    失败时返回兜底文案，不阻塞加入流程。
    """
    fallback = (
        f"欢迎宿主加入{sect.name}。"
        f"{sect.tagline}。"
        "愿此后修炼，道心坚固，功成圆满。"
    )
    try:
        cultivator: Cultivator | None = db.get(Cultivator, cultivator_id)
        if cultivator is None:
            return fallback

        stats: CultivationStats | None = db.get(CultivationStats, cultivator_id)
        realm = stats.current_realm if stats else "练气期·初阶"
        streak = stats.current_streak if stats else 0

        system_prompt = build_system_prompt(
            system_name=cultivator.system_name,
            system_personality=cultivator.system_personality,
            realm_name=realm,
            streak=streak,
        )

        user_content = (
            f"宿主刚刚正式拜入{sect.name}。"
            f"门派简介：{sect.tagline}"
            "生成一条欢迎入门的系统消息，体现该门派的修炼风格，不超过3句话。"
        )

        return await call_claude(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": user_content}],
            max_tokens=120,
        )
    except Exception:
        return fallback
