"""
models.py — 修炼世界的基石
五张表，构成宿主踏上修仙之路的完整记录。
"""

from datetime import datetime, date
from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey,
    Integer, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


# ============================================================
# 一、修士表（cultivators）
# 每一个注册用户，皆是一名踏上修炼之路的修士
# ============================================================
class Cultivator(Base):
    __tablename__ = "cultivators"

    # 修士唯一编号
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 道号（登录用户名，不可重复）
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # 传音符（邮箱，不可重复）
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    # 秘法印记（密码哈希）
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # 入道之日
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # 系统称号（随身系统的自称，默认"初始系统"）
    system_name: Mapped[str] = mapped_column(
        String(64), nullable=False, default="初始系统"
    )
    # 系统人设（宿主对系统口吻的自定义描述，可为空则使用系统默认人设）
    system_personality: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ---- 关联 ----
    # 宿主习得的所有功法
    techniques: Mapped[list["Technique"]] = relationship(
        "Technique", back_populates="cultivator", cascade="all, delete-orphan"
    )
    # 宿主的所有修炼记录
    cultivation_records: Mapped[list["CultivationRecord"]] = relationship(
        "CultivationRecord", back_populates="cultivator", cascade="all, delete-orphan"
    )
    # 宿主的修为面板（一对一）
    stats: Mapped["CultivationStats | None"] = relationship(
        "CultivationStats",
        back_populates="cultivator",
        uselist=False,
        cascade="all, delete-orphan",
    )
    # 系统下发的所有消息
    system_messages: Mapped[list["SystemMessage"]] = relationship(
        "SystemMessage", back_populates="cultivator", cascade="all, delete-orphan"
    )
    # 历史门派成员记录（is_active=True 的最多只有一条）
    sect_memberships: Mapped[list["SectMember"]] = relationship(
        "SectMember", back_populates="cultivator", cascade="all, delete-orphan"
    )


# ============================================================
# 二、功法表（techniques）
# 每门功法对应一项现实中的自律任务
# 例："淬体功" → 健身，"凝神功" → 早睡，"观书功" → 读书
# ============================================================
class Technique(Base):
    __tablename__ = "techniques"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 所属修士
    cultivator_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cultivators.id"), nullable=False
    )
    # 功法名称（修仙世界的命名，如"淬体功"）
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    # 现实任务描述（如"每天健身30分钟"）
    real_task: Mapped[str] = mapped_column(Text, nullable=False)
    # 每日修炼时刻（24小时制字符串，如"07:00"，可为空表示无固定时间）
    scheduled_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    # 完成一次修炼可获得的灵气值（默认50）
    spiritual_energy_reward: Mapped[int] = mapped_column(
        Integer, nullable=False, default=50
    )
    # 是否仍在修炼中（停修则设为 False）
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # 门派自动添加标记（FK → sects.id）
    # 非空：此功法由加入门派时自动创建；退出门派时自动停修
    # 为空：用户自己创建，门派操作不影响
    added_by_sect_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("sects.id"), nullable=True, default=None
    )
    # AI 建议的灵气奖励值（调用 /evaluate 时写入，可为空）
    spiritual_energy_ai_suggested: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    # 天道允许的最低灵气定价（AI评估 ±10%）
    spiritual_energy_min_allowed: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    # 天道允许的最高灵气定价
    spiritual_energy_max_allowed: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    # ---- 关联 ----
    cultivator: Mapped["Cultivator"] = relationship(
        "Cultivator", back_populates="techniques"
    )
    cultivation_records: Mapped[list["CultivationRecord"]] = relationship(
        "CultivationRecord", back_populates="technique", cascade="all, delete-orphan"
    )
    system_messages: Mapped[list["SystemMessage"]] = relationship(
        "SystemMessage", back_populates="technique"
    )


# ============================================================
# 三、修炼记录表（cultivation_records）
# 每一次打卡，皆是宿主修炼的铁证
# ============================================================
class CultivationRecord(Base):
    __tablename__ = "cultivation_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 修炼者
    cultivator_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cultivators.id"), nullable=False
    )
    # 本次修炼的功法
    technique_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("techniques.id"), nullable=False
    )
    # 修炼完成时刻
    cultivated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    # 修炼凭证（照片URL，可为空）
    photo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # 修炼感悟（心得笔记，可为空）
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 本次修炼获得的灵气值
    spiritual_energy_gained: Mapped[int] = mapped_column(Integer, nullable=False)

    # ---- 关联 ----
    cultivator: Mapped["Cultivator"] = relationship(
        "Cultivator", back_populates="cultivation_records"
    )
    technique: Mapped["Technique"] = relationship(
        "Technique", back_populates="cultivation_records"
    )


# ============================================================
# 四、修为面板（cultivation_stats）
# 每位修士的成长数据，与修士一对一绑定
# ============================================================
class CultivationStats(Base):
    __tablename__ = "cultivation_stats"

    # 修士ID即主键，确保一对一
    cultivator_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cultivators.id"), primary_key=True
    )
    # 累计灵气总量
    total_spiritual_energy: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    # 当前境界（文字描述，如"练气期·初阶"）
    current_realm: Mapped[str] = mapped_column(
        String(32), nullable=False, default="练气期·初阶"
    )
    # 境界等级（数字，用于后台计算突破阈值，从1开始）
    realm_level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # 连续修炼天数（断修则归零）
    current_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 历史最长连续修炼天数
    longest_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 最近一次修炼日期（用于判断是否断修）
    last_cultivation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # 今日已获灵气（每日重置，用于每日上限计算）
    daily_spiritual_energy_earned: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    # 气海存储：今日溢出的灵气暂存，次日结算30%回流
    spiritual_energy_overflow: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    # 每日计数器的重置日期（None=从未修炼）
    daily_earned_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # ---- 关联 ----
    cultivator: Mapped["Cultivator"] = relationship(
        "Cultivator", back_populates="stats"
    )


# ============================================================
# 五、系统消息表（system_messages）
# 随身系统下发的催修通知、突破贺报、怠惰警告等
# ============================================================
class SystemMessage(Base):
    __tablename__ = "system_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 消息接收者（宿主）
    cultivator_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cultivators.id"), nullable=False
    )
    # 关联的功法（若为空则表示系统全局消息，如境界突破贺报）
    technique_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("techniques.id", ondelete="SET NULL"), nullable=True
    )
    # 消息正文
    message: Mapped[str] = mapped_column(Text, nullable=False)
    # 系统发送时刻
    sent_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    # 宿主是否已阅
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # ---- 关联 ----
    cultivator: Mapped["Cultivator"] = relationship(
        "Cultivator", back_populates="system_messages"
    )
    technique: Mapped["Technique | None"] = relationship(
        "Technique", back_populates="system_messages"
    )


# ============================================================
# 六、门派表（sects）
# 门派元数据从 YAML 文件导入（sects/*.yaml），不由用户手动创建
# v0.2 阶段为只读数据，随版本更新分发
# ============================================================
class Sect(Base):
    __tablename__ = "sects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # YAML meta.id，全局唯一标识符，如 "lianti_zong"
    sect_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # 门派名称，如 "炼体宗"
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    # 简介口号，如 "以肉身为炉，千锤百炼，方成大道"
    tagline: Mapped[str] = mapped_column(String(256), nullable=False)
    # 详细描述
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # 核心方向，逗号分隔，如 "健身,体能,饮食"（对应 YAML focus 列表）
    focus: Mapped[str] = mapped_column(String(256), nullable=False)
    # 难度，如 "中等"
    difficulty: Mapped[str] = mapped_column(String(32), nullable=False)
    # 推荐对象描述，如 "想改变体型、建立运动习惯的修士"
    recommended_for: Mapped[str] = mapped_column(Text, nullable=False)
    # YAML 版本号，如 "1.0.0"
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    # YAML 维护者，如 "Self-UP官方"
    maintainer: Mapped[str] = mapped_column(String(128), nullable=False)
    # 是否在当前版本可用（下架门派设为 False，数据保留）
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # ---- 关联 ----
    members: Mapped[list["SectMember"]] = relationship(
        "SectMember", back_populates="sect", cascade="all, delete-orphan"
    )
    resources: Mapped[list["SectResource"]] = relationship(
        "SectResource", back_populates="sect", cascade="all, delete-orphan"
    )


# ============================================================
# 七、门派成员关系表（sect_members）
# 记录修士与门派的绑定关系，保留历史记录
#
# 业务约束：同一 cultivator 最多只有一条 is_active=True 的记录
# （应用层强制，退出/换派时将旧记录 is_active 置 False）
# ============================================================
class SectMember(Base):
    __tablename__ = "sect_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 修士 ID
    cultivator_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cultivators.id"), nullable=False
    )
    # 所属门派（FK → sects.id）
    sect_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sects.id"), nullable=False
    )
    # 加入时间
    joined_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    # 在门派中的天数（由定时任务每日更新，用于触发门派推送计划 push_schedule）
    days_in_sect: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 是否为当前有效成员（退出门派时置 False，记录保留）
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # 成员类型：'formal'（正式弟子）或 'visiting'（游历修士）
    membership_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="formal"
    )

    # ---- 关联 ----
    cultivator: Mapped["Cultivator"] = relationship(
        "Cultivator", back_populates="sect_memberships"
    )
    sect: Mapped["Sect"] = relationship("Sect", back_populates="members")


# ============================================================
# 八、门派秘籍表（sect_resources）
# 对应 YAML resources[] 列表，门派内置的学习资料
# 按修士当前境界解锁（unlock_realm 为大境界名称，如 "练气期"）
# ============================================================
class SectResource(Base):
    __tablename__ = "sect_resources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 所属门派（FK → sects.id）
    sect_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sects.id"), nullable=False
    )
    # YAML resources[].id，同一门派内唯一，如 "res_001"
    resource_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # 资源标题
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    # 资源类型：article / video_link / schedule
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    # 文字内容（article / schedule 类型使用，可为空）
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 外链 URL（video_link 类型使用，可为空）
    url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # 解锁所需大境界名称，如 "练气期" / "筑基期"（None 表示无限制）
    unlock_realm: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # 是否有效（下架资源时置 False）
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # ---- 关联 ----
    sect: Mapped["Sect"] = relationship("Sect", back_populates="resources")


# ============================================================
# 九、宗门任务进度表（sect_quest_progress）
# 记录修士对各宗门 YAML quests[] 的完成情况
# 一条记录 = 一个修士 × 一个宗门 × 一个任务ID
# ============================================================
class SectQuestProgress(Base):
    __tablename__ = "sect_quest_progress"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cultivator_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cultivators.id"), nullable=False
    )
    sect_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sects.id"), nullable=False
    )
    # YAML quests[].id，如 "q_100_training"
    quest_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # 是否已完成（领取过奖励）
    is_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 完成时间
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ============================================================
# 十、修炼成就记录表（achievement_records）
# 记录修士已触发的里程碑成就（能量阈值、连击阈值等）
# achievement_id 对应 sect_service._ACHIEVEMENT_MILESTONES 中的 id 字段
# ============================================================
class AchievementRecord(Base):
    __tablename__ = "achievement_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cultivator_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cultivators.id"), nullable=False
    )
    # 成就ID，如 "energy_1000" / "streak_30"
    achievement_id: Mapped[str] = mapped_column(String(64), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
