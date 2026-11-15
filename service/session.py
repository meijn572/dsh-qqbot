"""任务会话：多轮调用 + 前缀缓存。

**默认不累积历史。** 缓存靠的是稳定且够长的前缀，不是历史。

实测：/task/profile 不累积任何历史，
      prompt 9942 / cached 9728 = 98%

累积历史反而有害 —— 模型看到上次输出过，就判断「没变化」：

    第 1 轮    正常输出四组
    第 2 轮    {"sections":{}}
    第 3 轮    {"sections":{}}

所以 turn() 默认 keep_history=False。只有「同一任务分多步完成」
的场景才需要打开（先出草稿 → 基于草稿改 → 定稿），目前没有这样的任务。

保留的两件事：
    一、keep_history 开关         留给将来的多步任务
    二、轮换与裁剪                真开历史时防止上下文无限长
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any

# 超过这个上下文就换新会话。跟桥接那边的 maintenance_rotate_tokens 一个量级。
ROTATE_TOKENS = 30000
# 最多留几轮对话；超了砍最早的，保住 system 和最近几轮。
MAX_TURNS = 12
KEEP_TURNS = 6


class TaskSession:
    """一个任务的会话。同一 task 并发时加锁。"""

    _locks: dict[str, threading.Lock] = {}
    _guard = threading.Lock()

    def __init__(self, store, task: str):
        self.store = store
        self.task = str(task or "default")
        with self._guard:
            self._lock = self._locks.setdefault(self.task, threading.Lock())

    # -- 读 ---------------------------------------------------------------

    def load(self) -> list[dict]:
        """历史消息。空会话返回 []。"""
        row = self._row()
        if not row:
            return []
        try:
            data = json.loads(row["messages"] or "[]")
        except Exception:  # noqa: BLE001
            return []
        return data if isinstance(data, list) else []

    def pressure(self) -> int:
        row = self._row()
        return int(row["pressure"] or 0) if row else 0

    def turns(self) -> int:
        row = self._row()
        return int(row["turns"] or 0) if row else 0

    def _row(self):
        try:
            return self.store.conn.execute(
                "SELECT messages,turns,pressure FROM task_session WHERE task=?",
                (self.task,),
            ).fetchone()
        except Exception:  # noqa: BLE001
            return None

    # -- 写 ---------------------------------------------------------------

    def append(self, user: str, assistant: str, *, pressure: int = 0) -> None:
        """一问一答追加进历史。只追加，不改已有内容。"""
        with self._lock:
            messages = self.load()
            messages.append({"role": "user", "content": str(user)})
            messages.append({"role": "assistant", "content": str(assistant)})
            messages = self._trim(messages)
            turns = len([m for m in messages if m.get("role") == "user"])
            self._save(messages, turns, pressure)

    def reset(self) -> None:
        """清空会话（换新前缀）。"""
        with self._lock:
            self._save([], 0, 0)

    def _trim(self, messages: list[dict]) -> list[dict]:
        """超过 MAX_TURNS 轮就砍最早的，保留最近 KEEP_TURNS 轮。"""
        users = [i for i, m in enumerate(messages) if m.get("role") == "user"]
        if len(users) <= MAX_TURNS:
            return messages
        cut = users[len(users) - KEEP_TURNS]
        return messages[cut:]

    def _save(self, messages: list[dict], turns: int, pressure: int) -> None:
        try:
            self.store.conn.execute(
                "INSERT INTO task_session(task,messages,turns,pressure,updated_at) "
                "VALUES (?,?,?,?,?) "
                "ON CONFLICT(task) DO UPDATE SET "
                "messages=excluded.messages, turns=excluded.turns, "
                "pressure=excluded.pressure, updated_at=excluded.updated_at",
                (self.task, json.dumps(messages, ensure_ascii=False),
                 int(turns), int(pressure), time.time()),
            )
            self.store.conn.commit()
        except Exception:  # noqa: BLE001
            pass

    # -- 一次完整交互 ------------------------------------------------------

    def turn(self, llm, system: str, user: str, *, max_tokens: int = 1200,
             json_mode: bool = False, keep_history: bool = False) -> dict:
        """带上历史调一次模型，成功后自动追加。

        返回 {"ok", "text"|"data", "usage", "rotated", "error"}
        """
        with self._lock:
            # 默认不累积：同一任务每轮素材几乎一样，历史只会让模型误以为"已经答过"
            # 需要跨次记忆的任务才传 keep_history=True
            messages = self.load() if keep_history else []
            last_pressure = self.pressure() if keep_history else 0
            # 上一轮就已经接近上限 → 这轮换新，别等爆了才反应
            soft = ROTATE_TOKENS * 0.8
            if ROTATE_TOKENS > 0 and last_pressure >= soft:
                messages = []
                rotated = True
            else:
                rotated = False

            # 历史里 assistant 的空对象会诱导模型继续输出空对象，清掉
            messages = [m for m in messages
                        if not (m.get("role") == "assistant"
                                and str(m.get("content") or "").strip()
                                in ('{"sections":{}}', "{}", ""))]

            # system 永远在最前，且内容必须稳定 —— 变了缓存全失效
            full = [{"role": "system", "content": system}] + messages
            full.append({"role": "user", "content": str(user)})

            if json_mode:
                result = llm.chat_json_messages(full, max_tokens=max_tokens)
                payload = result.get("data")
            else:
                result = llm.chat_messages(full, max_tokens=max_tokens)
                payload = result.get("text")

            usage = result.get("usage") or {}
            error = result.get("error")
            if error or not result.get("text"):
                return {"ok": False, "error": error or "empty", "usage": usage,
                        "rotated": False}

            # 已经在锁里，直接写，不能再调 append（会重入死锁）
            messages = self._trim(messages + [
                {"role": "user", "content": str(user)},
                {"role": "assistant", "content": str(result.get("text") or "")},
            ])
            turns = len([m for m in messages if m.get("role") == "user"])
            self._save(messages, turns, int(usage.get("prompt") or 0))
            return {"ok": True, "text": result.get("text"), "data": payload,
                    "usage": usage, "rotated": rotated, "error": None}


def session_stats(store) -> list[dict]:
    """面板/调试用：各任务会话现状。"""
    try:
        rows = store.conn.execute(
            "SELECT task,turns,pressure,updated_at FROM task_session ORDER BY task"
        ).fetchall()
    except Exception:  # noqa: BLE001
        return []
    return [{"task": r["task"], "turns": int(r["turns"] or 0),
             "pressure": int(r["pressure"] or 0),
             "updated_at": float(r["updated_at"] or 0)} for r in rows]

