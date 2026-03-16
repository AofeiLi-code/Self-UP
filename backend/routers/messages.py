"""
routers/messages.py — 系统消息接口

GET  /api/system/messages?cultivator_id=xxx[&unread_only=true]
  返回该修士的系统消息列表（默认仅未读）

PATCH /api/system/messages/{message_id}/read
  将指定消息标记为已读
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models import SystemMessage
from schemas import ClearMessagesResponse, DeleteMessageResponse, MessagesResponse, SystemMessageOut

router = APIRouter(prefix="/api/system", tags=["系统消息"])


@router.get("/messages", response_model=MessagesResponse)
def get_messages(
    cultivator_id: int = Query(..., description="修士ID"),
    unread_only: bool = Query(True, description="是否只返回未读消息"),
    db: Session = Depends(get_db),
) -> MessagesResponse:
    """
    获取修士的系统消息。

    默认仅返回未读消息，按发送时间倒序排列（最新在前）。
    传入 unread_only=false 可查看全部历史消息。
    """
    query = db.query(SystemMessage).filter(
        SystemMessage.cultivator_id == cultivator_id
    )
    if unread_only:
        query = query.filter(SystemMessage.is_read == False)  # noqa: E712

    messages = query.order_by(SystemMessage.sent_at.desc()).all()
    return MessagesResponse(
        messages=[SystemMessageOut.model_validate(m) for m in messages],
        total=len(messages),
    )


@router.patch("/messages/{message_id}/read", response_model=SystemMessageOut)
def mark_as_read(
    message_id: int,
    db: Session = Depends(get_db),
) -> SystemMessageOut:
    """
    将指定系统消息标记为已读。

    若消息不存在或不属于该宿主，返回 404。
    """
    msg: SystemMessage | None = db.get(SystemMessage, message_id)
    if msg is None:
        raise HTTPException(status_code=404, detail="消息不存在")

    msg.is_read = True
    db.commit()
    db.refresh(msg)
    return SystemMessageOut.model_validate(msg)


@router.delete("/messages/{message_id}", response_model=DeleteMessageResponse)
def delete_message(
    message_id: int,
    cultivator_id: int = Query(..., description="修士ID（权限校验）"),
    db: Session = Depends(get_db),
) -> DeleteMessageResponse:
    """删除指定系统消息。"""
    msg: SystemMessage | None = db.get(SystemMessage, message_id)
    if msg is None or msg.cultivator_id != cultivator_id:
        raise HTTPException(status_code=404, detail="消息不存在")
    db.delete(msg)
    db.commit()
    return DeleteMessageResponse(success=True)


@router.delete("/messages", response_model=ClearMessagesResponse)
def clear_messages(
    cultivator_id: int = Query(..., description="修士ID"),
    db: Session = Depends(get_db),
) -> ClearMessagesResponse:
    """删除该修士的全部系统消息。"""
    count = (
        db.query(SystemMessage)
        .filter(SystemMessage.cultivator_id == cultivator_id)
        .count()
    )
    db.query(SystemMessage).filter(
        SystemMessage.cultivator_id == cultivator_id
    ).delete()
    db.commit()
    return ClearMessagesResponse(cleared=count)
