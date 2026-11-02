"""跨层数据契约：不允许把 OneBot event 或裸 dict 传进领域层。"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class InboundMessage:
    chat_key: str
    user_id: int
    nickname: str
    text: str = ""
    images: list[str] = field(default_factory=list)
    is_addressed: bool = False
    message_id: str = ""


@dataclass(slots=True)
class InboundBatch:
    chat_key: str
    messages: list[InboundMessage]
    merged_text: str
    images: list[str] = field(default_factory=list)
    is_group: bool = False
    addressed: bool = False
    need_gate: bool = True


@dataclass(slots=True)
class OutboundMessage:
    chat_key: str
    text: str = ""
    images: list[str] = field(default_factory=list)
    sticker_categories: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ReplyPlan:
    should_reply: bool
    messages: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    reason: str = ""
