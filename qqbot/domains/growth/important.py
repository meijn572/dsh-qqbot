"""重要的事：定时自检 + 手写文件同步。"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Awaitable, Callable

from qqbot.clients.memory import cmem_call, l0_recent, persona_context
from settings import DSH_HOME, OWNER_CHAT_KEY

log = logging.getLogger("qqbot.growth.important")
CHECK_STATE = DSH_HOME / "important-check-state.json"
THINGS_FILE = DSH_HOME / "important" / "important.md"
Turn = Callable[[str], Awaitable[str]]


def _load_state() -> dict:
    try:
        return json.loads(CHECK_STATE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save_state(state: dict) -> None:
    try:
        CHECK_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def _items(constitution: str) -> list[str]:
    match = re.search(r"<!-- important:begin -->(.*?)<!-- important:end -->", constitution, re.S)
    if not match:
        return []
    return [line[2:].strip() for line in match.group(1).splitlines() if line.strip().startswith("- ")]


async def check_once(turn: Turn) -> str:
    persona = await cmem_call("GET", "/persona")
    persona_text = await persona_context()
    current = _items(str(persona.get("constitution") or ""))
    recent = await l0_recent(OWNER_CHAT_KEY, 80) or "（最近没聊什么）"
    prompt = (
        "（内部维护，不要回复用户）现在是 " + time.strftime("%Y-%m-%d %H:%M") + "。\n"
        "回看最近这段相处，判断有没有一件事重要到「以后不能忘」：约定、底线、身份、关系里最关键的事。\n"
        "日常小事、情绪、一次性经历、称呼纠正、角色名这类事实都不算；那些属于普通记忆。\n"
        "没有就跳过，不要为了填而填。\n\n"
        + (persona_text or "（当前人格为空）") + "\n\n"
        f"【已经记下的】\n" + ("\n".join(f"- {x}" for x in current) or "（空）") + "\n\n"
        f"【最近】\n{recent}\n\n"
        "最多补一条，写一句具体的话，不要写标签。\n"
        '只输出 JSON：{"item":"..."} 或 {"skip":true}。'
    )
    reply = await turn(prompt)
    match = re.search(r"\{.*\}", reply or "", re.S)
    data = {}
    if match:
        try:
            data = json.loads(match.group(0))
        except Exception:  # noqa: BLE001
            data = {}
    item = str(data.get("item") or "").strip()[:100]
    if not item or data.get("skip") or item in current:
        return ""
    await cmem_call("POST", "/persona/important", {"action": "add", "item": item})
    log.info("重要的事：%s", item)
    return item


async def loop(turn: Turn, cfg: dict) -> None:
    if not cfg.get("enabled", False):
        log.info("重要的事自检：未启用")
        return
    state = _load_state()
    while True:
        try:
            if not cfg.get("enabled", False):
                await asyncio.sleep(600)
                continue
            day = time.strftime("%Y-%m-%d")
            hour = time.localtime().tm_hour
            hours = cfg.get("hours")
            if not isinstance(hours, list):
                hours = [int(cfg.get("hour", 22))]
            hours = [int(x) for x in hours]
            slot = f"{day}-{hour}"
            if state.get("slot") == slot:
                await asyncio.sleep(1800)
                continue
            if hour not in hours:
                await asyncio.sleep(600)
                continue
            before = str((await cmem_call("GET", "/persona")).get("constitution") or "")
            item = await check_once(turn)
            after = str((await cmem_call("GET", "/persona")).get("constitution") or "")
            state.update({"date": day, "slot": slot, "last_item": item})
            _save_state(state)
            if after != before:
                log.info("重要的事自检：已更新")
            elif not item:
                log.info("重要的事自检：今天没有要补的")
        except Exception as exc:  # noqa: BLE001
            log.warning("important_check err: %s", exc)
        await asyncio.sleep(1800)


def read_file() -> list[str]:
    try:
        lines = THINGS_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return [line[2:].strip() for line in lines if line.strip().startswith("- ") and line[2:].strip()]


async def file_loop() -> None:
    while True:
        try:
            if THINGS_FILE.exists():
                items = read_file()
                persona = await cmem_call("GET", "/persona")
                current = _items(str(persona.get("constitution") or ""))
                if items != current:
                    await cmem_call("POST", "/persona/important", {"action": "replace", "items": items})
                    log.info("重要的事：已从 important.md 同步 %s 条", len(items))
        except Exception as exc:  # noqa: BLE001
            log.warning("important_file_loop err: %s", exc)
        await asyncio.sleep(60)
