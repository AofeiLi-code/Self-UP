"""
services/sect_service.py — 门派业务逻辑（LORE.md §5）

公开函数：
  load_sects_from_yaml    — 启动时从 sects/*.yaml 导入/更新门派数据
  get_available_sects     — 列出所有可用门派
  join_sect               — 修士加入门派（正式弟子/游历修士双轨）
  leave_sect              — 修士退出指定门派（按 sect_str_id）
  get_cultivator_sects    — 返回修士当前所有门派关系（正式+游历）
  get_all_resources       — 返回修士门派秘籍（游历修士可查看全部）
  get_active_quests       — 返回指定宗门的任务列表（含修士当前进度）
  check_quest_progress    — 在修炼后检查所有宗门任务完成情况，发放奖励
  check_achievements      — 检查修士通用里程碑成就（仅对有正式宗门的修士触发）
  check_sect_push         — 检查今日是否触发门派推送消息（仅正式弟子）
  get_sect_techniques     — 返回宗门功法列表（含修士是否已添加）
  add_sect_technique      — 游历修士手动添加宗门功法
"""

import json
from datetime import date, datetime
from pathlib import Path

import yaml
from sqlalchemy import func
from sqlalchemy.orm import Session

from models import (
    AchievementRecord,
    CultivationRecord,
    CultivationStats,
    Cultivator,
    Sect,
    SectMember,
    SectQuestProgress,
    SectResource,
    SystemMessage,
    Technique,
)

# sects/ 目录位于仓库根目录（backend/services/ 上两级）
SECTS_DIR = Path(__file__).parent.parent.parent / "sects"

# 大境界顺序（对照 LORE.md §2.1），用于 unlock_realm 解锁比较
_MAJOR_REALM_ORDER = [
    "练气期", "筑基期", "金丹期", "元婴期",
    "化神期", "合体期", "大乘期", "渡劫期",
]

# 通用里程碑成就定义（不依赖 YAML，全局生效）
# type: total_spiritual_energy | streak_days | checkin_count
_ACHIEVEMENT_MILESTONES = [
    {"id": "energy_1000",   "title": "灵气积累·千",   "type": "total_spiritual_energy", "target": 1000,   "reward": 50},
    {"id": "energy_5000",   "title": "灵气积累·五千", "type": "total_spiritual_energy", "target": 5000,   "reward": 100},
    {"id": "energy_10000",  "title": "灵气积累·万",   "type": "total_spiritual_energy", "target": 10000,  "reward": 200},
    {"id": "streak_7",      "title": "七日不辍",       "type": "streak_days",            "target": 7,      "reward": 30},
    {"id": "streak_30",     "title": "三旬修炼",       "type": "streak_days",            "target": 30,     "reward": 100},
    {"id": "checkins_10",   "title": "十次修炼",       "type": "checkin_count",          "target": 10,     "reward": 20},
    {"id": "checkins_100",  "title": "百次修炼",       "type": "checkin_count",          "target": 100,    "reward": 200},
]


# ──────────────────────────────────────────────────────────────
# 内部工具
# ──────────────────────────────────────────────────────────────

def _major_realm_rank(realm_name: str) -> int:
    """
    从 '筑基期·初阶' 或 '筑基期' 提取大境界名称，返回其在 _MAJOR_REALM_ORDER 中的下标。
    未知名称返回 0（最低级）。
    """
    major = realm_name.split("·")[0]
    try:
        return _MAJOR_REALM_ORDER.index(major)
    except ValueError:
        return 0


def _load_sect_yaml(sect_str_id: str) -> dict:
    """根据门派字符串 ID 读取并解析对应 YAML 文件。"""
    path = SECTS_DIR / f"{sect_str_id}.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _serialize_content(value) -> str | None:
    """将 YAML 解析结果序列化为数据库 TEXT 字段：dict → JSON，其余转字符串。"""
    if value is None:
        return None
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def _upsert_resources(data: dict, sect_pk: int, db: Session) -> None:
    """
    将 YAML resources[] 写入 sect_resources 表。

    按 resource_id 做 upsert：已存在的行更新所有字段，不存在的行插入。
    不在 YAML 中的旧资源标记为 is_active=False（软删除）。
    """
    yaml_ids: set[str] = set()
    for res in data.get("resources", []):
        raw_content = res.get("content") or res.get("description")
        resource_id: str = res["id"]
        yaml_ids.add(resource_id)

        existing_res: SectResource | None = (
            db.query(SectResource)
            .filter(
                SectResource.sect_id == sect_pk,
                SectResource.resource_id == resource_id,
            )
            .first()
        )
        if existing_res is None:
            db.add(SectResource(
                sect_id=sect_pk,
                resource_id=resource_id,
                title=res["title"],
                type=res["type"],
                content=_serialize_content(raw_content),
                url=res.get("url"),
                unlock_realm=res.get("unlock_realm"),
                is_active=True,
            ))
        else:
            existing_res.title = res["title"]
            existing_res.type = res["type"]
            existing_res.content = _serialize_content(raw_content)
            existing_res.url = res.get("url")
            existing_res.unlock_realm = res.get("unlock_realm")
            existing_res.is_active = True

    # 将 YAML 中已移除的资源软删除
    db.query(SectResource).filter(
        SectResource.sect_id == sect_pk,
        SectResource.resource_id.notin_(yaml_ids),
    ).update({"is_active": False}, synchronize_session="fetch")


def _get_formal_membership(cultivator_id: int, db: Session) -> SectMember | None:
    """返回修士当前活跃的正式弟子记录，无则返回 None。"""
    return (
        db.query(SectMember)
        .filter(
            SectMember.cultivator_id == cultivator_id,
            SectMember.is_active == True,  # noqa: E712
            SectMember.membership_type == "formal",
        )
        .first()
    )


def _get_membership_by_sect(
    cultivator_id: int, sect_pk: int, db: Session
) -> SectMember | None:
    """返回修士在指定门派（sect PK）的活跃成员记录，无则 None。"""
    return (
        db.query(SectMember)
        .filter(
            SectMember.cultivator_id == cultivator_id,
            SectMember.sect_id == sect_pk,
            SectMember.is_active == True,  # noqa: E712
        )
        .first()
    )


def _get_primary_membership(cultivator_id: int, db: Session) -> SectMember | None:
    """
    返回修士的「主要」活跃成员记录：优先正式弟子，否则取第一个游历记录。
    """
    formal = _get_formal_membership(cultivator_id, db)
    if formal:
        return formal
    return (
        db.query(SectMember)
        .filter(
            SectMember.cultivator_id == cultivator_id,
            SectMember.is_active == True,  # noqa: E712
        )
        .first()
    )


def _compute_quest_progress(
    cultivator_id: int,
    criteria: dict,
    db: Session,
    joined_at: datetime | None = None,
) -> int:
    """
    根据任务完成条件计算修士当前进度值。

    criteria.type:
      - checkin_count:          修士所有修炼记录总次数
      - streak_days:            历史最长连续修炼天数
      - total_spiritual_energy: 修士当前累计总灵气
      - total_days:             有打卡记录的不重复自然天数（可断签），从 joined_at 起算
    """
    c_type = criteria.get("type", "")
    if c_type == "checkin_count":
        return (
            db.query(CultivationRecord)
            .filter(CultivationRecord.cultivator_id == cultivator_id)
            .count()
        )
    if c_type == "streak_days":
        stats: CultivationStats | None = db.get(CultivationStats, cultivator_id)
        return stats.longest_streak if stats else 0
    if c_type == "total_spiritual_energy":
        stats = db.get(CultivationStats, cultivator_id)
        return stats.total_spiritual_energy if stats else 0
    if c_type == "total_days":
        query = db.query(
            func.count(func.distinct(func.date(CultivationRecord.cultivated_at)))
        ).filter(CultivationRecord.cultivator_id == cultivator_id)
        if joined_at is not None:
            query = query.filter(CultivationRecord.cultivated_at >= joined_at)
        return query.scalar() or 0
    return 0


# ──────────────────────────────────────────────────────────────
# 公开接口
# ──────────────────────────────────────────────────────────────

def load_sects_from_yaml(db: Session) -> None:
    """
    扫描 sects/*.yaml，将门派元数据及秘籍写入数据库。

    - 新门派：直接插入 sects 表 + sect_resources 表
    - 已存在且版本相同：跳过
    - 已存在但版本升级：更新元数据，停用旧资源，插入新资源

    启动时（main.py lifespan）自动调用，允许失败（静默记录，不影响启动）。
    """
    if not SECTS_DIR.exists():
        return

    for yaml_path in sorted(SECTS_DIR.glob("*.yaml")):
        try:
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        meta = data.get("meta", {})
        sect_str_id: str | None = meta.get("id")
        if not sect_str_id:
            continue

        focus_str = ",".join(meta.get("focus", []))
        new_version: str = meta.get("version", "0.0.0")

        existing: Sect | None = (
            db.query(Sect).filter(Sect.sect_id == sect_str_id).first()
        )

        if existing is None:
            sect = Sect(
                sect_id=sect_str_id,
                name=meta["name"],
                tagline=meta["tagline"],
                description=meta["description"],
                focus=focus_str,
                difficulty=meta["difficulty"],
                recommended_for=meta["recommended_for"],
                version=new_version,
                maintainer=meta["maintainer"],
            )
            db.add(sect)
            db.flush()
            _upsert_resources(data, sect.id, db)

        else:
            # 门派元数据：版本升级时才更新
            if existing.version != new_version:
                existing.name = meta["name"]
                existing.tagline = meta["tagline"]
                existing.description = meta["description"]
                existing.focus = focus_str
                existing.difficulty = meta["difficulty"]
                existing.recommended_for = meta["recommended_for"]
                existing.version = new_version
                existing.maintainer = meta["maintainer"]

            # 资源（秘籍）：每次启动都按 resource_id upsert，无需 bump 版本号
            _upsert_resources(data, existing.id, db)

    db.commit()


def get_available_sects(db: Session) -> list[dict]:
    """返回所有 is_active=True 的门派列表（基本信息）。"""
    sects = db.query(Sect).filter(Sect.is_active == True).all()  # noqa: E712
    return [
        {
            "id": s.id,
            "sect_id": s.sect_id,
            "name": s.name,
            "tagline": s.tagline,
            "focus": s.focus.split(",") if s.focus else [],
            "difficulty": s.difficulty,
            "recommended_for": s.recommended_for,
        }
        for s in sects
    ]


def join_sect(
    cultivator_id: int,
    sect_str_id: str,
    membership_type: str,
    db: Session,
) -> dict:
    """
    修士加入指定门派，支持正式弟子（formal）和游历修士（visiting）双轨。

    formal：
      - 检查是否已有其他正式宗门 → 有则 ValueError（需先叛出）
      - 检查是否已是本门派任意类型成员 → 有则 ValueError
      - 创建 SectMember(membership_type='formal')，自动添加功法

    visiting：
      - 检查是否已是本门派成员 → 有则 ValueError
      - 创建 SectMember(membership_type='visiting')，不添加功法，不注册推送
    """
    sect: Sect | None = db.query(Sect).filter(
        Sect.sect_id == sect_str_id,
        Sect.is_active == True,  # noqa: E712
    ).first()
    if sect is None:
        raise ValueError(f"门派 '{sect_str_id}' 不存在或已下架")

    existing_here = _get_membership_by_sect(cultivator_id, sect.id, db)
    if existing_here is not None:
        raise ValueError("宿主已是该门派弟子，无需重复加入")

    if membership_type == "formal":
        formal_membership = _get_formal_membership(cultivator_id, db)
        if formal_membership is not None:
            raise ValueError("宿主已有正式师门，如需转宗请先叛出师门")

        membership = SectMember(
            cultivator_id=cultivator_id,
            sect_id=sect.id,
            days_in_sect=0,
            membership_type="formal",
        )
        db.add(membership)

        added_techniques: list[str] = []
        try:
            data = _load_sect_yaml(sect.sect_id)
            for tech_cfg in data.get("techniques", []):
                tech = Technique(
                    cultivator_id=cultivator_id,
                    name=tech_cfg["name"],
                    real_task=tech_cfg["real_task"],
                    scheduled_time=tech_cfg.get("scheduled_time"),
                    spiritual_energy_reward=tech_cfg.get("spiritual_energy_reward", 50),
                    added_by_sect_id=sect.id,
                )
                db.add(tech)
                added_techniques.append(tech_cfg["name"])
        except FileNotFoundError:
            pass

        db.commit()
        return {
            "success": True,
            "sect_name": sect.name,
            "added_techniques": added_techniques,
            "membership_type": "formal",
        }

    else:  # visiting
        membership = SectMember(
            cultivator_id=cultivator_id,
            sect_id=sect.id,
            days_in_sect=0,
            membership_type="visiting",
        )
        db.add(membership)
        db.commit()

        available_techniques: list[dict] = []
        try:
            data = _load_sect_yaml(sect.sect_id)
            for tech_cfg in data.get("techniques", []):
                available_techniques.append({
                    "name": tech_cfg["name"],
                    "real_task": tech_cfg.get("real_task", ""),
                    "spiritual_energy_reward": tech_cfg.get("spiritual_energy_reward", 50),
                })
        except FileNotFoundError:
            pass

        return {
            "success": True,
            "sect_name": sect.name,
            "added_techniques": [],
            "membership_type": "visiting",
            "available_techniques": available_techniques,
        }


def leave_sect(cultivator_id: int, sect_str_id: str, db: Session) -> dict:
    """
    修士退出指定门派（通过 YAML sect_str_id 定位）。

    - formal：停用该门派自动添加的功法，软删除成员记录
    - visiting：仅软删除成员记录
    """
    sect: Sect | None = db.query(Sect).filter(
        Sect.sect_id == sect_str_id,
    ).first()
    if sect is None:
        return {"success": True}

    membership = _get_membership_by_sect(cultivator_id, sect.id, db)
    if membership is None:
        return {"success": True}

    # 软删除该门派添加的功法（正式弟子自动功法 + 游历修士手动添加的功法）
    db.query(Technique).filter(
        Technique.cultivator_id == cultivator_id,
        Technique.added_by_sect_id == sect.id,
        Technique.is_active == True,  # noqa: E712
    ).update({"is_active": False})

    membership.is_active = False
    db.commit()
    return {"success": True}


def get_cultivator_sects(cultivator_id: int, db: Session) -> dict:
    """返回修士当前所有活跃门派关系（正式+游历）。"""
    memberships = (
        db.query(SectMember)
        .filter(
            SectMember.cultivator_id == cultivator_id,
            SectMember.is_active == True,  # noqa: E712
        )
        .all()
    )

    formal_info = None
    visiting_list = []

    for m in memberships:
        sect: Sect | None = db.get(Sect, m.sect_id)
        if sect is None:
            continue
        info = {
            "sect_id": sect.sect_id,
            "name": sect.name,
            "joined_at": m.joined_at.isoformat(),
            "days_in_sect": m.days_in_sect,
        }
        if m.membership_type == "formal":
            formal_info = info
        else:
            visiting_list.append(info)

    return {"formal": formal_info, "visiting": visiting_list}


def get_all_resources(
    cultivator_id: int,
    db: Session,
    sect_str_id: str | None = None,
) -> dict:
    """
    返回修士指定宗门的全部秘籍（不再按境界锁定，仅标注推荐状态）。

    - 所有成员（正式/游历）均可查看全部资源
    - is_recommended: True 表示修士当前境界已达推荐境界，供参考排序
    - sect_str_id: 指定宗门 YAML ID；不传则取修士主要宗门
    """
    def _empty(mt: str = "formal") -> dict:
        return {
            "sect_name": "", "cultivator_realm": "",
            "membership_type": mt, "resources": [], "recommended_count": 0,
        }

    if sect_str_id is not None:
        sect: Sect | None = db.query(Sect).filter(
            Sect.sect_id == sect_str_id, Sect.is_active == True  # noqa: E712
        ).first()
        if sect is None:
            return _empty()
        membership = _get_membership_by_sect(cultivator_id, sect.id, db)
        if membership is None:
            return _empty()
    else:
        membership = _get_primary_membership(cultivator_id, db)
        if membership is None:
            return _empty()
        sect = db.get(Sect, membership.sect_id)
        if sect is None:
            return _empty()

    stats: CultivationStats | None = db.get(CultivationStats, cultivator_id)
    if stats is None:
        return _empty(membership.membership_type)

    cultivator_realm = stats.current_realm
    cultivator_rank = _major_realm_rank(cultivator_realm)

    resources = (
        db.query(SectResource)
        .filter(
            SectResource.sect_id == membership.sect_id,
            SectResource.is_active == True,  # noqa: E712
        )
        .all()
    )

    result = []
    recommended_count = 0
    for res in resources:
        is_recommended = (
            res.unlock_realm is None
            or _major_realm_rank(res.unlock_realm) <= cultivator_rank
        )
        if is_recommended:
            recommended_count += 1
        result.append({
            "id": res.id,
            "resource_id": res.resource_id,
            "title": res.title,
            "type": res.type,
            "content": res.content,
            "url": res.url,
            "recommended_realm": res.unlock_realm,
            "is_recommended": is_recommended,
            "can_access": True,
        })

    return {
        "sect_name": sect.name,
        "cultivator_realm": cultivator_realm,
        "membership_type": membership.membership_type,
        "resources": result,
        "recommended_count": recommended_count,
    }


def get_active_quests(cultivator_id: int, sect_str_id: str, db: Session) -> dict:
    """
    返回指定宗门的任务列表，附带修士当前进度和参与权限。

    - formal 成员：所有任务可参与（can_participate=True）
    - visiting 成员：reward_title 不为空的任务为特别任务，can_participate=False
    - 已完成的任务：is_completed=True，仍显示在列表中

    返回 { sect_name, sect_id, membership_type, quests: list[...] }
    """
    sect: Sect | None = db.query(Sect).filter(Sect.sect_id == sect_str_id).first()
    if sect is None:
        raise ValueError(f"门派 '{sect_str_id}' 不存在")

    membership = _get_membership_by_sect(cultivator_id, sect.id, db)
    if membership is None:
        raise ValueError("宿主未加入该门派")

    is_visiting = membership.membership_type == "visiting"

    try:
        data = _load_sect_yaml(sect_str_id)
    except FileNotFoundError:
        return {
            "sect_name": sect.name, "sect_id": sect_str_id,
            "membership_type": membership.membership_type, "quests": [],
        }

    quests_yaml = data.get("quests", [])

    # 查询已完成记录
    completed_ids = {
        row.quest_id
        for row in db.query(SectQuestProgress).filter(
            SectQuestProgress.cultivator_id == cultivator_id,
            SectQuestProgress.sect_id == sect.id,
            SectQuestProgress.is_completed == True,  # noqa: E712
        ).all()
    }

    quest_list = []
    for q in quests_yaml:
        quest_id = q["id"]
        criteria = q.get("completion_criteria", {})
        current_progress = _compute_quest_progress(cultivator_id, criteria, db, joined_at=membership.joined_at)
        is_completed = quest_id in completed_ids
        reward_title = q.get("reward_title")  # None 或 null YAML → None

        if is_visiting and reward_title:
            can_participate = False
            restrict_reason = "需正式拜入方可参与特别任务"
        else:
            can_participate = True
            restrict_reason = None

        quest_list.append({
            "quest_id": quest_id,
            "title": q["title"],
            "description": q["description"],
            "type": q.get("type", "long_term"),
            "reward_spiritual_energy": q.get("reward_spiritual_energy", 0),
            "reward_title": reward_title,
            "criteria_type": criteria.get("type", ""),
            "criteria_target": criteria.get("target", 0),
            "current_progress": current_progress,
            "is_completed": is_completed,
            "can_participate": can_participate,
            "restrict_reason": restrict_reason,
        })

    return {
        "sect_name": sect.name,
        "sect_id": sect_str_id,
        "membership_type": membership.membership_type,
        "quests": quest_list,
    }


def check_quest_progress(cultivator_id: int, db: Session) -> list[dict]:
    """
    检查修士在所有活跃宗门的任务完成情况，自动发放奖励。

    逻辑：
      对每个活跃成员关系（formal + visiting）：
        - 加载该宗门 YAML quests[]
        - 对每个任务：若未完成且进度已达标 → 标记完成，发放灵气，写系统消息
        - visiting 完成任务：灵气正常发放，系统消息中注明归属 formal 宗门

    注意事项：
      # 示例：修士正式拜入炼体宗，游历凝神宗期间打卡100次
      # 触发凝神宗任务「月锻体魄」，获得200灵气
      # 灵气归入修士总量（与炼体宗修为共用同一个账户）
      # 系统消息提示：「游历凝神宗期间完成任务，灵气已归流入炼体宗修为」
      # 随后调用 check_achievements 检查炼体宗成就进度

    完成任何任务后，调用 check_achievements 触发成就检查。

    返回已完成任务的摘要列表（供调试/日志使用，cultivate endpoint 可忽略返回值）。
    """
    # 防止循环导入，在函数内部导入
    from services.realm_service import add_spiritual_energy

    memberships = (
        db.query(SectMember)
        .filter(
            SectMember.cultivator_id == cultivator_id,
            SectMember.is_active == True,  # noqa: E712
        )
        .all()
    )

    formal_sect_name: str | None = None
    formal_membership = _get_formal_membership(cultivator_id, db)
    if formal_membership:
        formal_sect_obj: Sect | None = db.get(Sect, formal_membership.sect_id)
        if formal_sect_obj:
            formal_sect_name = formal_sect_obj.name

    completed_this_run: list[dict] = []

    for m in memberships:
        sect: Sect | None = db.get(Sect, m.sect_id)
        if sect is None:
            continue

        try:
            data = _load_sect_yaml(sect.sect_id)
        except FileNotFoundError:
            continue

        quests_yaml = data.get("quests", [])
        is_visiting = m.membership_type == "visiting"

        for q in quests_yaml:
            quest_id = q["id"]
            reward_title = q.get("reward_title")

            # visiting 成员跳过特别任务
            if is_visiting and reward_title:
                continue

            # 已完成则跳过
            existing = db.query(SectQuestProgress).filter(
                SectQuestProgress.cultivator_id == cultivator_id,
                SectQuestProgress.sect_id == m.sect_id,
                SectQuestProgress.quest_id == quest_id,
                SectQuestProgress.is_completed == True,  # noqa: E712
            ).first()
            if existing:
                continue

            # 检查进度
            criteria = q.get("completion_criteria", {})
            progress = _compute_quest_progress(cultivator_id, criteria, db, joined_at=m.joined_at)
            target = criteria.get("target", 0)

            if progress < target:
                continue

            # ── 达成！标记完成，发放奖励 ─────────────────
            db.add(SectQuestProgress(
                cultivator_id=cultivator_id,
                sect_id=m.sect_id,
                quest_id=quest_id,
                is_completed=True,
                completed_at=datetime.now(),
            ))

            reward_energy = q.get("reward_spiritual_energy", 0)
            if reward_energy > 0:
                try:
                    add_spiritual_energy(cultivator_id, reward_energy, db)
                except (ValueError, Exception):
                    pass

            # 系统消息
            if is_visiting and formal_sect_name:
                msg = (
                    f"游历{sect.name}期间完成任务「{q['title']}」，"
                    f"获得{reward_energy}灵气，已归流入{formal_sect_name}修为"
                )
            else:
                msg = (
                    f"宗门任务「{q['title']}」已达成！"
                    f"获得{reward_energy}灵气奖励"
                )

            db.add(SystemMessage(
                cultivator_id=cultivator_id,
                technique_id=None,
                message=msg,
                sent_at=datetime.now(),
            ))
            db.commit()

            completed_this_run.append({
                "quest_id": quest_id,
                "sect": sect.name,
                "reward_energy": reward_energy,
            })

    # 有任务完成后，检查通用成就
    if completed_this_run:
        check_achievements(cultivator_id, db)

    return completed_this_run


def check_achievements(cultivator_id: int, db: Session) -> list[dict]:
    """
    检查修士通用里程碑成就，对有正式宗门的修士生效。

    规则：
    - 无正式宗门 → 直接返回（跳过）
    - 遍历 _ACHIEVEMENT_MILESTONES，检查修士当前 stats 是否满足条件
    - 已记录过的成就跳过
    - 满足则：写入 AchievementRecord，发放少量灵气，写系统消息

    返回本次新触发的成就列表。
    """
    # 仅对有正式宗门的修士触发
    formal = _get_formal_membership(cultivator_id, db)
    if formal is None:
        return []

    from services.realm_service import add_spiritual_energy

    stats: CultivationStats | None = db.get(CultivationStats, cultivator_id)
    if stats is None:
        return []

    # 已完成的成就 ID 集合
    completed_ids = {
        row.achievement_id
        for row in db.query(AchievementRecord).filter(
            AchievementRecord.cultivator_id == cultivator_id
        ).all()
    }

    # 当前各维度数值
    checkin_count = (
        db.query(CultivationRecord)
        .filter(CultivationRecord.cultivator_id == cultivator_id)
        .count()
    )

    values = {
        "total_spiritual_energy": stats.total_spiritual_energy,
        "streak_days": stats.longest_streak,
        "checkin_count": checkin_count,
    }

    triggered: list[dict] = []
    for milestone in _ACHIEVEMENT_MILESTONES:
        if milestone["id"] in completed_ids:
            continue
        current = values.get(milestone["type"], 0)
        if current < milestone["target"]:
            continue

        # 新成就触发
        db.add(AchievementRecord(
            cultivator_id=cultivator_id,
            achievement_id=milestone["id"],
        ))

        reward = milestone.get("reward", 0)
        if reward > 0:
            try:
                add_spiritual_energy(cultivator_id, reward, db)
            except (ValueError, Exception):
                pass

        _TYPE_LABEL = {
            "total_spiritual_energy": "累计灵气",
            "streak_days": "最长连击",
            "checkin_count": "累计打卡",
        }
        db.add(SystemMessage(
            cultivator_id=cultivator_id,
            technique_id=None,
            message=(
                f"成就解锁：【{milestone['title']}】"
                f"（{_TYPE_LABEL.get(milestone['type'], milestone['type'])}达到{milestone['target']}）"
                f"，获得{reward}灵气奖励"
            ),
            sent_at=datetime.now(),
        ))
        db.commit()
        triggered.append(milestone)

    return triggered


def get_sect_techniques(cultivator_id: int, sect_str_id: str, db: Session) -> list[dict]:
    """
    返回指定宗门的功法列表，附带修士是否已添加。

    - 正式弟子：功法在加入时自动添加，is_added 均为 True
    - 游历修士：is_added 取决于是否已手动添加
    """
    sect: Sect | None = db.query(Sect).filter(
        Sect.sect_id == sect_str_id, Sect.is_active == True  # noqa: E712
    ).first()
    if sect is None:
        return []

    if _get_membership_by_sect(cultivator_id, sect.id, db) is None:
        return []

    try:
        data = _load_sect_yaml(sect_str_id)
    except FileNotFoundError:
        return []

    # 该门派已在功课中（is_active）的功法名称集合
    added_names = {
        t.name
        for t in db.query(Technique).filter(
            Technique.cultivator_id == cultivator_id,
            Technique.added_by_sect_id == sect.id,
            Technique.is_active == True,  # noqa: E712
        ).all()
    }

    return [
        {
            "name": tech_cfg["name"],
            "real_task": tech_cfg.get("real_task", ""),
            "scheduled_time": tech_cfg.get("scheduled_time"),
            "spiritual_energy_reward": tech_cfg.get("spiritual_energy_reward", 50),
            "is_added": tech_cfg["name"] in added_names,
        }
        for tech_cfg in data.get("techniques", [])
    ]


def add_sect_technique(
    cultivator_id: int,
    sect_str_id: str,
    technique_name: str,
    db: Session,
) -> dict:
    """
    游历修士手动将宗门功法添加到个人功课。

    - 检查修士是否为该门派成员
    - 从 YAML 找到对应功法配置
    - 防止重复添加
    - 创建 Technique 记录（added_by_sect_id=sect.id）
    """
    sect: Sect | None = db.query(Sect).filter(
        Sect.sect_id == sect_str_id, Sect.is_active == True  # noqa: E712
    ).first()
    if sect is None:
        raise ValueError(f"门派 '{sect_str_id}' 不存在")

    membership = _get_membership_by_sect(cultivator_id, sect.id, db)
    if membership is None:
        raise ValueError("宿主未加入该门派")

    try:
        data = _load_sect_yaml(sect_str_id)
    except FileNotFoundError:
        raise ValueError("门派配置不存在")

    tech_cfg = next(
        (t for t in data.get("techniques", []) if t["name"] == technique_name),
        None,
    )
    if tech_cfg is None:
        raise ValueError(f"该门派不存在功法「{technique_name}」")

    # 防止重复添加（is_active=True 才算已添加）
    existing = db.query(Technique).filter(
        Technique.cultivator_id == cultivator_id,
        Technique.added_by_sect_id == sect.id,
        Technique.name == technique_name,
        Technique.is_active == True,  # noqa: E712
    ).first()
    if existing:
        raise ValueError("该功法已在功课中")

    tech = Technique(
        cultivator_id=cultivator_id,
        name=tech_cfg["name"],
        real_task=tech_cfg["real_task"],
        scheduled_time=tech_cfg.get("scheduled_time"),
        spiritual_energy_reward=tech_cfg.get("spiritual_energy_reward", 50),
        added_by_sect_id=sect.id,
    )
    db.add(tech)
    db.commit()
    db.refresh(tech)

    return {
        "id": tech.id,
        "name": tech.name,
        "real_task": tech.real_task,
        "scheduled_time": tech.scheduled_time,
        "spiritual_energy_reward": tech.spiritual_energy_reward,
        "added_by_sect_id": tech.added_by_sect_id,
    }


def check_sect_push(cultivator_id: int, db: Session) -> dict:
    """
    检查今日是否触发门派推送消息（LORE.md §5.2 push_schedule）。

    仅对正式弟子触发；游历修士直接返回 has_message=False。

    返回 { has_message: bool, message: str | None }
    """
    membership = _get_formal_membership(cultivator_id, db)
    if membership is None:
        return {"has_message": False, "message": None}

    days_since_joining = (date.today() - membership.joined_at.date()).days

    if membership.days_in_sect != days_since_joining:
        membership.days_in_sect = days_since_joining
        db.commit()

    try:
        sect: Sect | None = db.get(Sect, membership.sect_id)
        if sect is None:
            return {"has_message": False, "message": None}

        data = _load_sect_yaml(sect.sect_id)
        push_schedule: list[dict] = data.get("push_schedule", [])

        for entry in push_schedule:
            if entry.get("day") == days_since_joining:
                return {
                    "has_message": True,
                    "message": entry["message"],
                }
    except FileNotFoundError:
        pass

    return {"has_message": False, "message": None}
