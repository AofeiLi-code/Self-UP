"""
test_realm_service.py — 验证境界与灵气系统

重点验证：
  - calculate_realm 在各关键灵气节点的境界计算（LORE.md §2.1 精确阈值）
  - 练气期 → 筑基期 的大境界突破是否正确触发
  - update_streak 的连续天数逻辑（连续/中断/幂等）
  - 走火入魔惩罚（LORE.md §2.3）的正确计算
"""

import pytest
from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import Cultivator, CultivationStats
from services.realm_service import (
    REALM_STAGES,
    add_spiritual_energy,
    calculate_realm,
    update_streak,
)


# ──────────────────────────────────────────────────────────────
# 测试夹具
# ──────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    """每个测试用例独享一个内存数据库，互不干扰。"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def cultivator_at_400(db):
    """
    创建一位灵气为 400 的修士（练气期·圆满），
    昨日有修炼记录，当前连续3天，历史最长5天。
    """
    cultivator = Cultivator(
        username="test_xiu",
        email="test@selfup.dev",
        password_hash="hashed_pw",
        system_name="初始系统",
    )
    db.add(cultivator)
    db.flush()  # 获取自增 id

    stats = CultivationStats(
        cultivator_id=cultivator.id,
        total_spiritual_energy=400,
        current_realm="练气期·圆满",
        realm_level=4,
        current_streak=3,
        longest_streak=5,
        last_cultivation_date=date.today() - timedelta(days=1),
    )
    db.add(stats)
    db.commit()
    return cultivator, stats


# ──────────────────────────────────────────────────────────────
# calculate_realm — 境界计算（LORE.md §2.1 精确阈值）
# ──────────────────────────────────────────────────────────────

class TestCalculateRealm:

    def test_零灵气_练气期初阶(self):
        r = calculate_realm(0)
        assert r["realm_name"] == "练气期·初阶"
        assert r["realm_level"] == 1
        assert r["progress_to_next"] == 0.0

    def test_练气期_四个小阶(self):
        # 练气期各阶起点：0, 125, 250, 375
        cases = [
            (0,   "练气期·初阶", 1),
            (125, "练气期·中阶", 2),
            (250, "练气期·高阶", 3),
            (375, "练气期·圆满", 4),
        ]
        for se, name, level in cases:
            r = calculate_realm(se)
            assert r["realm_name"] == name, f"灵气={se} 期望 {name}，实得 {r['realm_name']}"
            assert r["realm_level"] == level

    def test_练气期圆满边界_499仍未突破(self):
        """499 灵气尚在练气期，不应提前进入筑基期。"""
        r = calculate_realm(499)
        assert r["realm_name"] == "练气期·圆满"
        assert r["realm_level"] == 4

    def test_500灵气_恰好进入筑基期初阶(self):
        """500 是练气期→筑基期的突破临界点。"""
        r = calculate_realm(500)
        assert r["realm_name"] == "筑基期·初阶"
        assert r["realm_level"] == 5

    def test_筑基期_四个小阶(self):
        # 筑基期各阶起点：500, 875, 1250, 1625
        cases = [
            (500,  "筑基期·初阶", 5),
            (875,  "筑基期·中阶", 6),
            (1250, "筑基期·高阶", 7),
            (1625, "筑基期·圆满", 8),
        ]
        for se, name, level in cases:
            r = calculate_realm(se)
            assert r["realm_name"] == name, f"灵气={se}"
            assert r["realm_level"] == level

    def test_所有大境界起点均正确识别(self):
        """每个大境界的初阶起点，应恰好识别为该境界·初阶。"""
        for i, (realm, stage, lower, _) in enumerate(REALM_STAGES):
            if stage != "初阶":
                continue
            r = calculate_realm(lower)
            assert r["realm_name"] == f"{realm}·初阶", (
                f"灵气={lower} 应在 {realm}·初阶，实得 {r['realm_name']}"
            )
            assert r["realm_level"] == i + 1

    def test_渡劫期初阶_无进度(self):
        r = calculate_realm(100_000)
        assert r["realm_name"] == "渡劫期·初阶"
        assert r["realm_level"] == 29
        assert r["progress_to_next"] == 0.0  # 无上限，进度无意义

    def test_渡劫期_超高灵气仍在渡劫期(self):
        r = calculate_realm(999_999)
        assert r["realm_name"].startswith("渡劫期")

    def test_progress_to_next_在合法范围内(self):
        """所有有上限境界的进度值应在 0.0–1.0 之间。"""
        test_values = [0, 100, 499, 500, 1000, 5000, 40000, 79999]
        for se in test_values:
            r = calculate_realm(se)
            assert 0.0 <= r["progress_to_next"] <= 1.0, (
                f"灵气={se}，progress={r['progress_to_next']} 超出范围"
            )

    def test_大乘期_圆满上限_99999(self):
        """大乘期·圆满终止于 99999，100000 进入渡劫期。"""
        assert calculate_realm(99999)["realm_name"] == "大乘期·圆满"
        assert calculate_realm(100000)["realm_name"] == "渡劫期·初阶"

    def test_合体期各阶(self):
        cases = [
            (25000, "合体期·初阶", 21),
            (35000, "合体期·中阶", 22),
            (40000, "合体期·高阶", 23),
            (45000, "合体期·圆满", 24),
        ]
        for se, name, level in cases:
            r = calculate_realm(se)
            assert r["realm_name"] == name, f"灵气={se}"
            assert r["realm_level"] == level


# ──────────────────────────────────────────────────────────────
# add_spiritual_energy — 灵气增减与突破检测
# ──────────────────────────────────────────────────────────────

class TestAddSpiritualEnergy:

    def test_练气期到筑基期突破正确触发(self, db, cultivator_at_400):
        """
        核心突破测试：
        修士灵气 400，练气期每日上限 150，增加 200 → 实际获得 150 → 总计 550，
        跨越练气期→筑基期，breakthrough 必须为 True。
        """
        cultivator, _ = cultivator_at_400
        result = add_spiritual_energy(cultivator.id, 200, db)

        assert result["new_total"] == 550  # 400 + 150（上限封顶）
        assert result["old_realm"].startswith("练气期"), "增加前应在练气期"
        assert result["new_realm"].startswith("筑基期"), "增加后应在筑基期"
        assert result["breakthrough"] is True, "跨大境界必须触发 breakthrough"

    def test_境界内提升_不触发突破(self, db, cultivator_at_400):
        """灵气 400 + 50 = 450，仍在练气期，breakthrough 必须为 False。"""
        cultivator, _ = cultivator_at_400
        result = add_spiritual_energy(cultivator.id, 50, db)

        assert result["new_total"] == 450
        assert result["new_realm"].startswith("练气期")
        assert result["breakthrough"] is False

    def test_小阶提升_不触发突破(self, db, cultivator_at_400):
        """练气期内从圆满再往前一点，大境界不变，breakthrough=False。"""
        cultivator, _ = cultivator_at_400
        result = add_spiritual_energy(cultivator.id, 10, db)
        assert result["breakthrough"] is False

    def test_恰好跨越临界点_突破触发(self, db, cultivator_at_400):
        """增加灵气使总量恰好等于 500，应触发突破。"""
        cultivator, _ = cultivator_at_400
        result = add_spiritual_energy(cultivator.id, 100, db)  # 400 + 100 = 500

        assert result["new_total"] == 500
        assert result["new_realm"] == "筑基期·初阶"
        assert result["breakthrough"] is True

    def test_数据库正确持久化(self, db, cultivator_at_400):
        """增加灵气后，数据库中的值应与返回值一致（每日上限150，实际+150=550）。"""
        cultivator, _ = cultivator_at_400
        add_spiritual_energy(cultivator.id, 200, db)

        stats = db.get(CultivationStats, cultivator.id)
        assert stats.total_spiritual_energy == 550  # 400 + 150（上限封顶）
        assert stats.current_realm == "筑基期·初阶"
        assert stats.realm_level == 5

    def test_修士不存在时抛出异常(self, db):
        """面板不存在时应抛出 ValueError，不能静默失败。"""
        with pytest.raises(ValueError, match="修为面板不存在"):
            add_spiritual_energy(9999, 100, db)

    def test_超出每日上限_多余进入气海(self, db, cultivator_at_400):
        """
        练气期修士（灵气400）增加200，每日上限150，超出50进入气海。
        breakthrough 仍触发（400+150=550 已入筑基期）。
        """
        cultivator, _ = cultivator_at_400
        result = add_spiritual_energy(cultivator.id, 200, db)

        assert result["overflow_added"] == 50
        assert result["new_total"] == 550
        assert result["breakthrough"] is True
        stats = db.get(CultivationStats, cultivator.id)
        assert stats.spiritual_energy_overflow == 50
        assert stats.daily_spiritual_energy_earned == 150

    def test_气海隔日结算_30pct回流(self, db, cultivator_at_400):
        """
        气海有100灵气，次日首次修炼时30%回流（30灵气），气海清空。
        """
        cultivator, stats = cultivator_at_400
        stats.spiritual_energy_overflow = 100
        stats.daily_earned_date = date.today() - timedelta(days=1)
        db.commit()

        result = add_spiritual_energy(cultivator.id, 50, db)

        assert result["overflow_settled"] == 30  # floor(100 × 0.3)
        stats_after = db.get(CultivationStats, cultivator.id)
        assert stats_after.spiritual_energy_overflow == 0  # 气海清空
        # 400（起始）+ 30（结算）+ 50（今日修炼，在上限内）= 480
        assert stats_after.total_spiritual_energy == 480

    def test_负数灵气_总量不低于零(self, db, cultivator_at_400):
        """扣减灵气超过持有量时，总量应归零而不是负数。"""
        cultivator, _ = cultivator_at_400
        result = add_spiritual_energy(cultivator.id, -10000, db)  # 400 - 10000 → 0
        assert result["new_total"] == 0

    def test_走火入魔扣减_不触发突破(self, db, cultivator_at_400):
        """灵气因惩罚减少导致境界降级时，breakthrough 应为 False。"""
        cultivator, _ = cultivator_at_400
        result = add_spiritual_energy(cultivator.id, -400, db)  # 400 → 0（练气期）
        assert result["breakthrough"] is False


# ──────────────────────────────────────────────────────────────
# update_streak — 连续修炼天数 + 走火入魔惩罚
# ──────────────────────────────────────────────────────────────

class TestUpdateStreak:

    def test_昨日打卡_今日streak加一(self, db, cultivator_at_400):
        """昨日有记录，今日打卡，streak 从 3 增至 4。"""
        cultivator, stats = cultivator_at_400
        result = update_streak(cultivator.id, db)

        assert result["current_streak"] == 4
        assert result["streak_updated"] is True
        assert result["penalty_pct"] == 0
        assert result["penalty_status"] is None

    def test_今日重复打卡_幂等(self, db, cultivator_at_400):
        """同一天调用两次，streak 只增加一次。"""
        cultivator, _ = cultivator_at_400
        first = update_streak(cultivator.id, db)
        second = update_streak(cultivator.id, db)

        assert second["streak_updated"] is False
        assert second["current_streak"] == first["current_streak"]

    def test_断1天_心神动摇_无惩罚(self, db, cultivator_at_400):
        """最后修炼日在 2 天前（断1天），streak 归一，penalty_pct=0。"""
        cultivator, stats = cultivator_at_400
        stats.last_cultivation_date = date.today() - timedelta(days=2)
        db.commit()

        result = update_streak(cultivator.id, db)
        assert result["current_streak"] == 1
        assert result["streak_updated"] is True
        assert result["penalty_pct"] == 0
        assert result["penalty_status"] == "心神动摇"

    def test_断2天_道心不稳_5pct(self, db, cultivator_at_400):
        """断2天，penalty_pct=5，status=道心不稳。"""
        cultivator, stats = cultivator_at_400
        stats.last_cultivation_date = date.today() - timedelta(days=3)
        db.commit()

        result = update_streak(cultivator.id, db)
        assert result["current_streak"] == 1
        assert result["penalty_pct"] == 5
        assert result["penalty_status"] == "道心不稳"

    def test_断3天_轻微走火_10pct(self, db, cultivator_at_400):
        """断3天，penalty_pct=10，status=轻微走火。"""
        cultivator, stats = cultivator_at_400
        stats.last_cultivation_date = date.today() - timedelta(days=4)
        db.commit()

        result = update_streak(cultivator.id, db)
        assert result["current_streak"] == 1
        assert result["penalty_pct"] == 10
        assert result["penalty_status"] == "轻微走火"

    def test_断4天以上_走火入魔_15pct(self, db, cultivator_at_400):
        """断4天及以上（含30天），penalty_pct=15，status=走火入魔。"""
        cultivator, stats = cultivator_at_400
        stats.last_cultivation_date = date.today() - timedelta(days=5)
        db.commit()

        result = update_streak(cultivator.id, db)
        assert result["current_streak"] == 1
        assert result["penalty_pct"] == 15
        assert result["penalty_status"] == "走火入魔"

    def test_中断多天_同样走火入魔(self, db, cultivator_at_400):
        """中断一个月后复修，仍是走火入魔级别惩罚。"""
        cultivator, stats = cultivator_at_400
        stats.last_cultivation_date = date.today() - timedelta(days=30)
        db.commit()

        result = update_streak(cultivator.id, db)
        assert result["current_streak"] == 1
        assert result["penalty_pct"] == 15
        assert result["penalty_status"] == "走火入魔"

    def test_首次修炼_streak为一_无惩罚(self, db, cultivator_at_400):
        """从未打卡（last_cultivation_date=None），初次修炼 streak=1，无惩罚。"""
        cultivator, stats = cultivator_at_400
        stats.last_cultivation_date = None
        stats.current_streak = 0
        db.commit()

        result = update_streak(cultivator.id, db)
        assert result["current_streak"] == 1
        assert result["penalty_pct"] == 0
        assert result["penalty_status"] is None

    def test_连续超越历史_longest_streak更新(self, db, cultivator_at_400):
        """
        当 current_streak 突破 longest_streak 时，longest 应同步更新。
        初始：current=3，longest=5。
        打卡后：current=4，longest 仍为 5（未超越）。
        再强制 current=5+昨日，打卡后 current=6，longest 更新为 6。
        """
        cultivator, _ = cultivator_at_400

        # 第一次打卡：current 3→4，longest 仍 5
        r1 = update_streak(cultivator.id, db)
        assert r1["current_streak"] == 4
        assert r1["longest_streak"] == 5

        # 强制拉高 current_streak 使其逼近 longest
        stats = db.get(CultivationStats, cultivator.id)
        stats.current_streak = 5
        stats.last_cultivation_date = date.today() - timedelta(days=1)
        db.commit()

        # 第二次打卡：current 5→6，突破 longest=5，longest 更新为 6
        r2 = update_streak(cultivator.id, db)
        assert r2["current_streak"] == 6
        assert r2["longest_streak"] == 6

    def test_修士不存在时抛出异常(self, db):
        with pytest.raises(ValueError, match="修为面板不存在"):
            update_streak(9999, db)
