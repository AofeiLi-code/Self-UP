from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# 功法典籍存放路径（SQLite 数据库文件）
DATABASE_URL = "sqlite:///./selfup.db"

# 创造界域（数据库引擎）
# check_same_thread=False：允许 FastAPI 多线程共用同一 SQLite 连接
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

# 修炼会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """所有表的基础元类，承载整个修炼世界的规则"""
    pass


def _migrate(conn) -> None:
    """
    增量迁移：为已存在的表补全新增字段。
    SQLite 不支持 create_all 时自动 ALTER，需手动检测并补列。
    """
    # v0.2 — techniques.added_by_sect_id（门派自动添加功法标记）
    tech_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(techniques)"))}
    if "added_by_sect_id" not in tech_cols:
        conn.execute(text(
            "ALTER TABLE techniques ADD COLUMN "
            "added_by_sect_id INTEGER REFERENCES sects(id)"
        ))

    # v0.3 — techniques AI 定价字段
    if "spiritual_energy_ai_suggested" not in tech_cols:
        conn.execute(text(
            "ALTER TABLE techniques ADD COLUMN spiritual_energy_ai_suggested INTEGER"
        ))
    if "spiritual_energy_min_allowed" not in tech_cols:
        conn.execute(text(
            "ALTER TABLE techniques ADD COLUMN spiritual_energy_min_allowed INTEGER"
        ))
    if "spiritual_energy_max_allowed" not in tech_cols:
        conn.execute(text(
            "ALTER TABLE techniques ADD COLUMN spiritual_energy_max_allowed INTEGER"
        ))

    # v0.3 — cultivation_stats 每日上限与气海字段
    stats_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(cultivation_stats)"))}
    if "daily_spiritual_energy_earned" not in stats_cols:
        conn.execute(text(
            "ALTER TABLE cultivation_stats ADD COLUMN "
            "daily_spiritual_energy_earned INTEGER NOT NULL DEFAULT 0"
        ))
    if "spiritual_energy_overflow" not in stats_cols:
        conn.execute(text(
            "ALTER TABLE cultivation_stats ADD COLUMN "
            "spiritual_energy_overflow INTEGER NOT NULL DEFAULT 0"
        ))
    if "daily_earned_date" not in stats_cols:
        conn.execute(text(
            "ALTER TABLE cultivation_stats ADD COLUMN daily_earned_date DATE"
        ))

    # v0.4 — sect_members 成员类型字段
    sect_member_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(sect_members)"))}
    if "membership_type" not in sect_member_cols:
        conn.execute(text(
            "ALTER TABLE sect_members ADD COLUMN "
            "membership_type VARCHAR(16) NOT NULL DEFAULT 'formal'"
        ))

    # v0.5 — 宗门任务进度表 + 修炼成就记录表（CREATE IF NOT EXISTS）
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS sect_quest_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cultivator_id INTEGER NOT NULL REFERENCES cultivators(id),
            sect_id INTEGER NOT NULL REFERENCES sects(id),
            quest_id VARCHAR(64) NOT NULL,
            is_completed BOOLEAN NOT NULL DEFAULT 0,
            completed_at DATETIME
        )
    """))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS achievement_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cultivator_id INTEGER NOT NULL REFERENCES cultivators(id),
            achievement_id VARCHAR(64) NOT NULL,
            completed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))


def init_db() -> None:
    """开天辟地——启动时自动建表，若已存在则跳过，再运行增量迁移"""
    import models  # noqa: F401  让 Base 感知所有模型后再建表
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        _migrate(conn)
        conn.commit()


def get_db():
    """FastAPI 依赖注入：取得一次修炼会话，用完后自动归还"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
