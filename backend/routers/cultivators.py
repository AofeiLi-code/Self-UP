"""
routers/cultivators.py — 修士信息接口

GET /api/cultivators/{cultivator_id}  获取修士修炼面板
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Cultivator, CultivationStats
from schemas import CultivatorOut
from services.realm_service import calculate_realm

router = APIRouter(prefix="/api/cultivators", tags=["修士"])


@router.get("/{cultivator_id}", response_model=CultivatorOut)
def get_cultivator(cultivator_id: int, db: Session = Depends(get_db)):
    cultivator = db.get(Cultivator, cultivator_id)
    if not cultivator:
        raise HTTPException(404, detail="修士不存在")

    stats = db.get(CultivationStats, cultivator_id)
    if not stats:
        raise HTTPException(404, detail="修炼数据不存在")

    realm_info = calculate_realm(stats.total_spiritual_energy)
    return CultivatorOut(
        id=cultivator.id,
        username=cultivator.username,
        system_name=cultivator.system_name,
        total_spiritual_energy=stats.total_spiritual_energy,
        current_realm=stats.current_realm,
        realm_level=stats.realm_level,
        current_streak=stats.current_streak,
        longest_streak=stats.longest_streak,
        progress_to_next=realm_info["progress_to_next"],
        daily_spiritual_energy_earned=stats.daily_spiritual_energy_earned,
        spiritual_energy_overflow=stats.spiritual_energy_overflow,
    )
