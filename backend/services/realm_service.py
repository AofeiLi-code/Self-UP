"""
realm_service.py — 境界与灵气法则（对照 LORE.md §2.1 / §2.3）

掌管三件要事：
  1. calculate_realm      — 将累计灵气换算为境界名称与进度
  2. add_spiritual_energy — 为修士增加/扣减灵气并检测境界突破
  3. update_streak        — 维护连续修炼天数，返回走火入魔惩罚信息
"""

from datetime import date, timedelta
import math

from sqlalchemy.orm import Session

from models import CultivationStats

# ──────────────────────────────────────────────────────────────
# 境界体系（LORE.md §2.1 完整境界表）
# 每个元组：(大境界, 小阶, 起点灵气, 终点灵气 | None=无上限)
# ──────────────────────────────────────────────────────────────
REALM_STAGES: list[tuple[str, str, int, int | None]] = [
    ("练气期", "初阶",  0,       124),
    ("练气期", "中阶",  125,     249),
    ("练气期", "高阶",  250,     374),
    ("练气期", "圆满",  375,     499),
    ("筑基期", "初阶",  500,     874),
    ("筑基期", "中阶",  875,     1249),
    ("筑基期", "高阶",  1250,    1624),
    ("筑基期", "圆满",  1625,    1999),
    ("金丹期", "初阶",  2000,    2999),
    ("金丹期", "中阶",  3000,    3749),
    ("金丹期", "高阶",  3750,    4374),
    ("金丹期", "圆满",  4375,    4999),
    ("元婴期", "初阶",  5000,    6874),
    ("元婴期", "中阶",  6875,    8124),
    ("元婴期", "高阶",  8125,    9374),
    ("元婴期", "圆满",  9375,    9999),
    ("化神期", "初阶",  10000,   14999),
    ("化神期", "中阶",  15000,   17499),
    ("化神期", "高阶",  17500,   19999),
    ("化神期", "圆满",  20000,   24999),
    ("合体期", "初阶",  25000,   34999),
    ("合体期", "中阶",  35000,   39999),
    ("合体期", "高阶",  40000,   44999),
    ("合体期", "圆满",  45000,   49999),
    ("大乘期", "初阶",  50000,   64999),
    ("大乘期", "中阶",  65000,   72499),
    ("大乘期", "高阶",  72500,   79999),
    ("大乘期", "圆满",  80000,   99999),
    ("渡劫期", "初阶",  100000,  None),   # 无上限，超凡入圣
]

# 走火入魔惩罚表（LORE.md §2.3）
# key = 断修天数，value = (扣减百分比, 状态描述)
_BREAK_PENALTIES: dict[int, tuple[int, str]] = {
    1: (0,  "心神动摇"),   # 断1天，仅警示，不扣灵气
    2: (5,  "道心不稳"),
    3: (10, "轻微走火"),
}
_BREAK_PENALTY_MAX: tuple[int, str] = (15, "走火入魔")  # 断4天及以上

# 每日灵气获取上限（LORE.md §3.2）
# key = 大境界名称，value = 当日可获灵气上限
_DAILY_CAPS: dict[str, int] = {
    "练气期": 150,
    "筑基期": 200,
    "金丹期": 280,
    "元婴期": 350,
}
_DAILY_CAP_DEFAULT = 450  # 化神期及以上


def _daily_cap(major_realm: str) -> int:
    """根据大境界名称返回每日灵气上限。"""
    return _DAILY_CAPS.get(major_realm, _DAILY_CAP_DEFAULT)


# ──────────────────────────────────────────────────────────────
# 内部工具
# ──────────────────────────────────────────────────────────────

def _find_stage(total_se: int) -> tuple[int, str, str, int, int | None]:
    """
    根据灵气总量定位所在小阶。
    返回 (index, realm, stage, lower, upper)。
    """
    for i, (realm, stage, lower, upper) in enumerate(REALM_STAGES):
        if upper is None or total_se <= upper:
            return i, realm, stage, lower, upper
    last = REALM_STAGES[-1]
    return len(REALM_STAGES) - 1, last[0], last[1], last[2], last[3]


def _major_realm(total_se: int) -> str:
    """返回所在大境界名称，如 '练气期'。"""
    _, realm, _, _, _ = _find_stage(total_se)
    return realm


# ──────────────────────────────────────────────────────────────
# 公开接口
# ──────────────────────────────────────────────────────────────

def calculate_realm(total_spiritual_energy: int) -> dict:
    """
    将累计灵气总量换算为境界信息。

    返回：
        realm_name       — "筑基期·中阶" 格式的境界全称
        realm_level      — 1–29（练气期初阶=1，渡劫期初阶=29）
        progress_to_next — 当前小阶内的进度（0.0–1.0）；渡劫期无上限返回 0.0
    """
    idx, realm, stage, lower, upper = _find_stage(total_spiritual_energy)

    if upper is None:
        progress_to_next = 0.0
    else:
        stage_width = upper - lower + 1
        progress_to_next = round((total_spiritual_energy - lower) / stage_width, 4)

    return {
        "realm_name": f"{realm}·{stage}",
        "realm_level": idx + 1,
        "progress_to_next": progress_to_next,
    }


def add_spiritual_energy(
    cultivator_id: int,
    amount: int,
    db: Session,
) -> dict:
    """
    为修士增加（或扣减）灵气，更新修为面板，检测大境界突破。

    正数 amount：受每日上限约束，超出部分进入气海（overflow）。
    负数 amount（走火入魔惩罚）：绕过每日上限，直接扣减，总量最低归零。

    新的一天首次调用时，自动结算气海：30% 回流总量，70% 消散。

    返回：
        new_total        — 变动后的灵气总量
        old_realm        — 变动前的境界全称
        new_realm        — 变动后的境界全称
        breakthrough     — True 表示跨越大境界向上突破（不含惩罚导致的降级）
        current_streak   — 当前连续修炼天数（原样返回）
        overflow_added   — 本次因超上限进入气海的灵气量
        overflow_settled — 本次从气海结算回流的灵气量（新的一天才会 > 0）
    """
    stats: CultivationStats | None = db.get(CultivationStats, cultivator_id)
    if stats is None:
        raise ValueError(f"修士 {cultivator_id} 的修为面板不存在，请先完成初始化")

    old_total = stats.total_spiritual_energy
    old_info = calculate_realm(old_total)
    old_major = _major_realm(old_total)

    today = date.today()
    overflow_settled = 0

    # ── 新的一天：结算气海（30%回流，70%消散），重置每日计数器 ──────
    if stats.daily_earned_date != today:
        if stats.spiritual_energy_overflow > 0:
            overflow_settled = math.floor(stats.spiritual_energy_overflow * 0.3)
            stats.spiritual_energy_overflow = 0
        stats.daily_spiritual_energy_earned = 0
        stats.daily_earned_date = today
        stats.total_spiritual_energy += overflow_settled

    # ── 应用灵气变化 ─────────────────────────────────────────────
    overflow_added = 0
    if amount > 0:
        major = _major_realm(stats.total_spiritual_energy)
        cap = _daily_cap(major)
        remaining = cap - stats.daily_spiritual_energy_earned
        actual_add = min(amount, max(0, remaining))
        overflow_added = amount - actual_add
        stats.spiritual_energy_overflow += overflow_added
        stats.daily_spiritual_energy_earned += actual_add
        stats.total_spiritual_energy += actual_add
    else:
        # 负数惩罚：绕过上限，总量最低归零
        stats.total_spiritual_energy = max(0, stats.total_spiritual_energy + amount)

    new_total = stats.total_spiritual_energy
    new_info = calculate_realm(new_total)
    new_major = _major_realm(new_total)

    stats.current_realm = new_info["realm_name"]
    stats.realm_level = new_info["realm_level"]
    db.commit()
    db.refresh(stats)

    return {
        "new_total": new_total,
        "old_realm": old_info["realm_name"],
        "new_realm": new_info["realm_name"],
        # 只有灵气净增且大境界名称变化，才算突破（排除惩罚导致的降级）
        "breakthrough": new_major != old_major and new_total > old_total,
        "current_streak": stats.current_streak,
        "overflow_added": overflow_added,
        "overflow_settled": overflow_settled,
    }


def update_streak(cultivator_id: int, db: Session) -> dict:
    """
    每次修炼打卡后调用，维护连续修炼天数，并计算走火入魔惩罚。
    幂等：今日已打卡则直接返回，不重复计算。

    走火入魔惩罚（LORE.md §2.3）：
        断1天 → penalty_pct=0，心神动摇（仅警示）
        断2天 → penalty_pct=5，道心不稳
        断3天 → penalty_pct=10，轻微走火
        断4天+ → penalty_pct=15，走火入魔

    返回：
        current_streak  — 更新后的连续修炼天数
        longest_streak  — 历史最长连续天数
        streak_updated  — False 表示今日已记录，本次幂等跳过
        penalty_pct     — 本次应扣减的灵气百分比（0/5/10/15）
        penalty_status  — 状态描述，无中断则为 None
    """
    stats: CultivationStats | None = db.get(CultivationStats, cultivator_id)
    if stats is None:
        raise ValueError(f"修士 {cultivator_id} 的修为面板不存在，请先完成初始化")

    today = date.today()
    last = stats.last_cultivation_date

    if last == today:
        return {
            "current_streak": stats.current_streak,
            "longest_streak": stats.longest_streak,
            "streak_updated": False,
            "penalty_pct": 0,
            "penalty_status": None,
        }

    penalty_pct = 0
    penalty_status: str | None = None

    if last is None:
        # 首次修炼
        stats.current_streak = 1
    else:
        gap = (today - last).days   # gap=1: 昨日打卡，gap=2: 断1天，…
        break_days = gap - 1        # 实际断修天数

        if break_days == 0:
            # 昨日有记录，今日继续，道心坚固
            stats.current_streak += 1
        else:
            # 断修：streak 归一，计算走火入魔惩罚
            stats.current_streak = 1
            if break_days in _BREAK_PENALTIES:
                penalty_pct, penalty_status = _BREAK_PENALTIES[break_days]
            else:
                penalty_pct, penalty_status = _BREAK_PENALTY_MAX

    stats.longest_streak = max(stats.longest_streak, stats.current_streak)
    stats.last_cultivation_date = today
    db.commit()
    db.refresh(stats)

    return {
        "current_streak": stats.current_streak,
        "longest_streak": stats.longest_streak,
        "streak_updated": True,
        "penalty_pct": penalty_pct,
        "penalty_status": penalty_status,
    }
