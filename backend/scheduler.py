"""
scheduler.py — 随身系统定时督促模块

启动时读取所有 is_active=True 的功法，按 scheduled_time 注册 cron 任务。
到点后：调用 Claude 生成与连续打卡天数匹配的督促语气，写入 system_messages 表，并记录日志。

TODO: 接入 Web Push，实现移动端推送
"""

import logging
from datetime import date, datetime, time

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from ai_client import build_system_prompt, call_claude
from database import SessionLocal
from models import CultivationStats, Cultivator, Sect, SectMember, SystemMessage, Technique
from services.sect_service import check_sect_push

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")


# ──────────────────────────────────────────────────────────────
# 公开接口
# ──────────────────────────────────────────────────────────────

def init_scheduler() -> None:
    """
    读取全部 is_active=True 且设有 scheduled_time 的功法，
    为每条功法注册一个每日 cron 定时提醒任务。
    """
    db = SessionLocal()
    try:
        techniques = (
            db.query(Technique)
            .filter(Technique.is_active == True, Technique.scheduled_time != None)  # noqa: E712
            .all()
        )
        for tech in techniques:
            _register_job(tech.id, tech.name, tech.scheduled_time)
        logger.info("[督促] 已注册 %d 条功法提醒", len(techniques))
    finally:
        db.close()


def register_technique_job(technique_id: int, name: str, scheduled_time: str) -> None:
    """对外暴露：新增功法后立即注册对应的定时任务。"""
    _register_job(technique_id, name, scheduled_time)


def remove_technique_job(technique_id: int) -> None:
    """对外暴露：停修或删除功法后取消对应定时任务。"""
    job_id = f"technique_{technique_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        logger.info("[督促] 已移除功法(%d)定时任务", technique_id)


# ──────────────────────────────────────────────────────────────
# 内部函数
# ──────────────────────────────────────────────────────────────

def _register_job(technique_id: int, name: str, scheduled_time: str) -> None:
    """
    将 "HH:MM" 格式的 scheduled_time 解析为 CronTrigger 并注册任务。
    同一 technique_id 已存在任务时直接替换（replace_existing=True）。
    """
    try:
        hour, minute = scheduled_time.split(":")
    except ValueError:
        logger.warning("[督促] 功法(%d) scheduled_time 格式有误: %s", technique_id, scheduled_time)
        return

    scheduler.add_job(
        _send_reminder,
        trigger=CronTrigger(hour=int(hour), minute=int(minute)),
        id=f"technique_{technique_id}",
        args=[technique_id],
        replace_existing=True,
        misfire_grace_time=300,  # 5 分钟内的误触发仍执行
    )
    logger.info("[督促] 功法「%s」(%d) 定时任务已注册，触发时刻 %s", name, technique_id, scheduled_time)


async def _send_reminder(technique_id: int) -> None:
    """
    定时任务执行体：
    1. 查询功法及其宿主信息
    2. 优先检查今日是否有门派专属推送（sect push）
       - 有：使用门派消息替代默认督促，加【门派名】前缀，防当日重复发送
       - 无：调用 Claude 生成常规督促文案（失败则使用兜底文本）
    3. 写入 system_messages 表
    4. 记录日志
    TODO: 接入 Web Push，实现移动端推送
    """
    db = SessionLocal()
    try:
        technique: Technique | None = db.get(Technique, technique_id)
        if technique is None or not technique.is_active:
            return

        cultivator: Cultivator | None = db.get(Cultivator, technique.cultivator_id)
        if cultivator is None:
            return

        stats: CultivationStats | None = db.get(CultivationStats, technique.cultivator_id)
        streak = stats.current_streak if stats else 0
        realm = stats.current_realm if stats else "练气期·初阶"

        # ── 优先处理门派专属推送，否则生成日常督促 ────────────
        message = await _resolve_message(
            technique=technique,
            cultivator=cultivator,
            streak=streak,
            realm=realm,
            db=db,
        )

        # ── 写入系统消息表 ────────────────────────────────────
        db.add(SystemMessage(
            cultivator_id=cultivator.id,
            technique_id=technique_id,
            message=message,
            sent_at=datetime.now(),
        ))
        db.commit()

        logger.info(
            "[督促] 已向 %s 发送修炼提醒（功法：%s，连续%d天）",
            cultivator.username, technique.name, streak,
        )
        # TODO: 接入 Web Push，实现移动端推送

    except Exception:
        logger.exception("[督促] 发送提醒失败，technique_id=%d", technique_id)
        db.rollback()
    finally:
        db.close()


async def _resolve_message(
    technique: Technique,
    cultivator: Cultivator,
    streak: int,
    realm: str,
    db,
) -> str:
    """
    决定本次推送内容：

    优先级：
      1. 今日有门派专属推送 AND 今日尚未发送过该条  →  返回「【门派名】门派消息」
      2. 否则  →  调用 Claude 生成日常督促（失败则使用兜底文本）

    防重复机制：
      同一修士同一天同一门派消息若已存在于 system_messages，跳过门派推送，
      改用日常督促（避免多功法触发时重复推送相同消息）。
    """
    # 查询门派专属推送
    sect_push = check_sect_push(technique.cultivator_id, db)

    if sect_push["has_message"]:
        # 获取门派名称
        membership: SectMember | None = (
            db.query(SectMember)
            .filter(
                SectMember.cultivator_id == technique.cultivator_id,
                SectMember.is_active == True,  # noqa: E712
            )
            .first()
        )
        sect_name = ""
        if membership:
            sect: Sect | None = db.get(Sect, membership.sect_id)
            sect_name = sect.name if sect else ""

        sect_message = (
            f"【{sect_name}】{sect_push['message']}"
            if sect_name
            else sect_push["message"]
        )

        # 防重复：今日是否已发送过完全相同的门派消息
        today_start = datetime.combine(date.today(), time(0, 0, 0))
        already_sent = (
            db.query(SystemMessage)
            .filter(
                SystemMessage.cultivator_id == technique.cultivator_id,
                SystemMessage.sent_at >= today_start,
                SystemMessage.message == sect_message,
            )
            .first()
        )
        if already_sent is None:
            return sect_message
        # 今日已发过，降级为日常督促

    return await _generate_reminder(cultivator, technique, streak, realm)


async def _generate_reminder(
    cultivator: Cultivator,
    technique: Technique,
    streak: int,
    realm: str,
) -> str:
    """调用 Claude 生成与修炼状态匹配的督促文案，失败则兜底。"""
    try:
        system_prompt = build_system_prompt(
            system_name=cultivator.system_name,
            system_personality=cultivator.system_personality,
            realm_name=realm,
            streak=streak,
        )

        # 根据连续天数调整催修语气
        if streak > 7:
            tone_hint = "宿主连续修炼已超过7天，语气应充满赞许与激励，鼓励其再接再厉。"
        elif streak >= 1:
            tone_hint = f"宿主已连续修炼{streak}天，语气平和自然，提醒其今日功法尚未完成。"
        else:
            tone_hint = "宿主已断修，语气应带有一丝警示与担忧，提醒其走火入魔的风险。"

        user_content = (
            f"【定时督促】现在是{technique.name}的修炼时刻（{technique.scheduled_time}）。"
            f"现实任务：{technique.real_task}。{tone_hint}"
            "请以随身系统的身份，用一两句话催促宿主去完成今日修炼。"
        )

        return await call_claude(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": user_content}],
            max_tokens=100,
        )
    except Exception:
        # Claude 不可用时的兜底督促文案
        if streak > 7:
            return f"宿主已连续修炼{streak}天，甚好。今日【{technique.name}】时辰已到，切勿懈怠。"
        elif streak >= 1:
            return f"【{technique.name}】修炼时辰已至，宿主速去完成：{technique.real_task}。"
        else:
            return f"宿主久未修炼，根基动摇！速速完成【{technique.name}】，莫要走火入魔！"
