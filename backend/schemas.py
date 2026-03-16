"""
schemas.py — 接口数据规范

定义所有 API 请求与响应的 Pydantic 模型。
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


# ──────────────────────────────────────────────────────────────
# POST /api/cultivate  （修炼打卡）
# ──────────────────────────────────────────────────────────────

class CultivateResponse(BaseModel):
    spiritual_energy_gained: int        # 本次修炼获得的灵气（含连击倍率和附图/感悟加成，未扣惩罚）
    new_realm: str                      # 打卡后的境界名称
    breakthrough: bool                  # 是否突破了大境界
    current_streak: int                 # 当前连续修炼天数
    system_response: str                # AI 生成的系统反馈
    penalty_energy: int = 0             # 走火入魔扣减的灵气值（0 表示无惩罚）
    penalty_status: str | None = None   # 走火入魔状态描述，如"道心不稳"
    overflow_added: int = 0             # 本次因超每日上限进入气海的灵气量
    overflow_settled: int = 0           # 本次从气海回流的灵气量（新的一天才会 > 0）


# ──────────────────────────────────────────────────────────────
# POST /api/system/dialogue  （与系统对话）
# ──────────────────────────────────────────────────────────────

class DialogueRequest(BaseModel):
    cultivator_id: int   # 修士ID
    message: str         # 宿主发送的消息


class DialogueResponse(BaseModel):
    reply: str           # 随身系统的回复


# ──────────────────────────────────────────────────────────────
# GET /api/system/messages  （读取系统消息）
# ──────────────────────────────────────────────────────────────

class SystemMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cultivator_id: int
    technique_id: int | None
    message: str
    sent_at: datetime
    is_read: bool


class MessagesResponse(BaseModel):
    messages: list[SystemMessageOut]
    total: int           # 本次返回的消息条数


class DeleteMessageResponse(BaseModel):
    success: bool


class ClearMessagesResponse(BaseModel):
    cleared: int         # 删除的消息数量


# ──────────────────────────────────────────────────────────────
# POST /api/auth/register & /api/auth/login
# ──────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    access_token: str
    cultivator_id: int
    username: str
    system_name: str


# ──────────────────────────────────────────────────────────────
# GET /api/cultivators/{id}
# ──────────────────────────────────────────────────────────────

class CultivatorOut(BaseModel):
    id: int
    username: str
    system_name: str
    total_spiritual_energy: int
    current_realm: str
    realm_level: int
    current_streak: int
    longest_streak: int
    progress_to_next: float          # 0.0 – 1.0，距下一阶的进度
    daily_spiritual_energy_earned: int = 0   # 今日已获灵气（用于每日上限进度展示）
    spiritual_energy_overflow: int = 0       # 气海存储量（用于气海状态展示）


# ──────────────────────────────────────────────────────────────
# GET /api/techniques  &  POST /api/techniques
# ──────────────────────────────────────────────────────────────

class TechniqueOut(BaseModel):
    id: int
    name: str
    real_task: str
    scheduled_time: str | None
    spiritual_energy_reward: int
    completed_today: bool            # 今日是否已完成修炼
    is_active: bool = True           # False = 已废弃
    added_by_sect_id: int | None = None   # 宗门自动添加时非 None，禁止独立修改灵气值
    spiritual_energy_ai_suggested: int | None = None
    spiritual_energy_min_allowed: int | None = None
    spiritual_energy_max_allowed: int | None = None


class TechniqueCreate(BaseModel):
    cultivator_id: int
    name: str
    real_task: str
    scheduled_time: str | None = None
    spiritual_energy_reward: int = 50
    spiritual_energy_ai_suggested: int | None = None
    spiritual_energy_min_allowed: int | None = None
    spiritual_energy_max_allowed: int | None = None


# ──────────────────────────────────────────────────────────────
# POST /api/techniques/evaluate  （AI 灵气定价）
# ──────────────────────────────────────────────────────────────

class EvaluateTechniqueRequest(BaseModel):
    name: str        # 功法名称
    real_task: str   # 现实任务描述


class EvaluateTechniqueResponse(BaseModel):
    suggested_reward: int    # AI 建议灵气值
    min_allowed: int         # 允许最低值（suggested ×0.9，向下取整）
    max_allowed: int         # 允许最高值（suggested ×1.1，向下取整）
    reasoning: str           # AI 给出的定价理由


# ──────────────────────────────────────────────────────────────
# GET /api/sects  （门派列表）
# ──────────────────────────────────────────────────────────────

class SectOut(BaseModel):
    id: int
    sect_id: str             # YAML meta.id，如 "lianti_zong"
    name: str
    tagline: str
    focus: list[str]
    difficulty: str
    recommended_for: str
    membership_type: str | None = None  # None=未加入, 'formal'=正式弟子, 'visiting'=游历修士


class SectsResponse(BaseModel):
    sects: list[SectOut]


# ──────────────────────────────────────────────────────────────
# POST /api/sects/join  （加入门派）
# ──────────────────────────────────────────────────────────────

class JoinSectRequest(BaseModel):
    cultivator_id: int
    sect_id: str             # YAML门派ID，如 "lianti_zong"
    membership_type: str = "formal"   # 'formal'（正式弟子）或 'visiting'（游历修士）


class SectTechniqueItem(BaseModel):
    """宗门功法简要信息（用于游历时展示可添加列表）"""
    name: str
    real_task: str
    spiritual_energy_reward: int


class JoinSectResponse(BaseModel):
    success: bool
    welcome_message: str     # AI 生成的入宗欢迎消息（visiting 时为简短提示）
    added_techniques: list[str]   # 自动添加的功法名称列表（visiting 时为空）
    membership_type: str = "formal"
    available_techniques: list[SectTechniqueItem] = []  # visiting 时返回可选添加的宗门功法


# ──────────────────────────────────────────────────────────────
# POST /api/sects/leave  （退出门派）
# ──────────────────────────────────────────────────────────────

class LeaveSectRequest(BaseModel):
    cultivator_id: int
    sect_id: str             # YAML门派ID，需明确指定要退出哪个门派


class LeaveSectResponse(BaseModel):
    success: bool


# ──────────────────────────────────────────────────────────────
# GET /api/sects/memberships  （修士当前门派关系）
# ──────────────────────────────────────────────────────────────

class CultivatorSectMemberInfo(BaseModel):
    sect_id: str             # YAML meta.id
    name: str                # 门派名称
    joined_at: str           # 加入时间（ISO 字符串）
    days_in_sect: int


class CultivatorSectsResponse(BaseModel):
    formal: CultivatorSectMemberInfo | None = None   # 正式宗门（最多一个）
    visiting: list[CultivatorSectMemberInfo] = []    # 游历宗门列表


# ──────────────────────────────────────────────────────────────
# GET /api/sects/resources  （门派秘籍）
# ──────────────────────────────────────────────────────────────

class SectResourceOut(BaseModel):
    id: int
    resource_id: str
    title: str
    type: str                       # article / video_link / schedule
    content: str | None
    url: str | None
    recommended_realm: str | None   # 推荐境界（原 unlock_realm，仅作参考，不再锁定）
    is_recommended: bool = True     # 修士当前境界是否已达推荐境界
    can_access: bool = True         # 所有资源均可访问，永远为 True


class SectResourcesResponse(BaseModel):
    sect_name: str = ""              # 修士当前所在门派名称（未加入则为空）
    cultivator_realm: str = ""       # 修士当前境界（用于页面展示）
    membership_type: str = "formal"  # 当前修士的成员类型
    resources: list[SectResourceOut]
    recommended_count: int = 0       # 适合当前境界的资源数


# ──────────────────────────────────────────────────────────────
# GET /api/sects/{sect_id}/quests  （宗门任务列表）
# ──────────────────────────────────────────────────────────────

class QuestOut(BaseModel):
    quest_id: str               # YAML quests[].id
    title: str
    description: str
    type: str                   # long_term | seasonal
    reward_spiritual_energy: int
    reward_title: str | None = None   # 不为空 = 特别任务
    criteria_type: str          # total_checkins | max_streak | total_spiritual_energy
    criteria_target: int
    current_progress: int       # 修士当前进度值
    is_completed: bool
    can_participate: bool       # 游历身份对特别任务为 False
    restrict_reason: str | None = None   # can_participate=False 时的原因说明


class SectQuestsResponse(BaseModel):
    sect_name: str
    sect_id: str                # YAML sect_str_id
    membership_type: str        # 'formal' | 'visiting'
    quests: list[QuestOut]


# ──────────────────────────────────────────────────────────────
# PUT /api/techniques/{id}  （修改功法）
# ──────────────────────────────────────────────────────────────

class TechniqueUpdate(BaseModel):
    name: str | None = None
    real_task: str | None = None
    scheduled_time: str | None = None
    is_active: bool | None = None          # 用于恢复已废弃功法
    spiritual_energy_reward: int | None = None
    spiritual_energy_ai_suggested: int | None = None
    spiritual_energy_min_allowed: int | None = None
    spiritual_energy_max_allowed: int | None = None


# ──────────────────────────────────────────────────────────────
# DELETE /api/techniques/{id}  （废弃功法）
# ──────────────────────────────────────────────────────────────

class DeleteTechniqueResponse(BaseModel):
    success: bool
    message: str


class ClearInactiveTechniquesResponse(BaseModel):
    cleared: int                  # 成功清空的数量
    skipped: int                  # 跳过的数量（正式宗门功法，需离宗移除）
    skipped_names: list[str]      # 跳过的功法名称列表


# ──────────────────────────────────────────────────────────────
# GET  /api/sects/{sect_id}/techniques  （宗门功法列表）
# POST /api/sects/{sect_id}/techniques/add  （添加宗门功法到功课）
# ──────────────────────────────────────────────────────────────

class SectTechniqueOut(BaseModel):
    name: str
    real_task: str
    scheduled_time: str | None = None
    spiritual_energy_reward: int
    is_added: bool = False     # 修士是否已将该功法加入功课


class SectTechniquesResponse(BaseModel):
    sect_name: str
    membership_type: str       # 'formal' | 'visiting'
    techniques: list[SectTechniqueOut]


class AddSectTechniqueRequest(BaseModel):
    cultivator_id: int
    technique_name: str


class AddSectTechniqueResponse(BaseModel):
    success: bool
    technique_name: str
    message: str


# ──────────────────────────────────────────────────────────────
# GET /api/cultivation/history  （修炼历史）
# ──────────────────────────────────────────────────────────────

class CultivationHistoryRecord(BaseModel):
    id: int
    technique_name: str
    cultivated_at: datetime
    photo_url: str | None
    note: str | None
    spiritual_energy_gained: int


class CultivationHistoryResponse(BaseModel):
    records: list[CultivationHistoryRecord]
    total: int
    page: int
    page_size: int
