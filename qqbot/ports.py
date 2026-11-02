"""跨层端口：领域只依赖 Protocol，不依赖具体适配器。"""
from __future__ import annotations

from typing import Protocol

from .contracts import InboundBatch, OutboundMessage, ReplyPlan


class OutboundPort(Protocol):
    async def send(self, message: OutboundMessage) -> None: ...


class MemoryPort(Protocol):
    async def context(self, *, query: str = "", tiers: dict[str, int] | None = None) -> str: ...

    async def ingest(self, *, text: str, tier: str = "L0", tags: list[str] | None = None) -> int | None: ...


class PersonaPort(Protocol):
    async def context(self) -> str: ...


class ConversationPort(Protocol):
    async def handle(self, batch: InboundBatch) -> ReplyPlan: ...
