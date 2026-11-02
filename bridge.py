"""QQ <-> DSH 桥：SnowLuma OneBot WS 收消息，走 DSH Typert RPC 会话，回复发回 QQ。"""

from __future__ import annotations

import asyncio
import base64
import difflib
import hashlib
import hmac
import io
import json
import logging
import os
import random
import re
import sqlite3
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

import aiohttp

from settings import (
    AGENTS,
    BOT_DIR as D,
    BOT_QQ,
    OWNER_CHAT_KEY,
    CMEM_BASE,
    CONFIG,
    DEEPSEEK_KEY_FILE,
    DSH_HOME,
    HEALTH_FILE,
    LOG_DIR,
    STATE_FILE,
    TOKEN_OB_HTTP,
    TOKEN_OB_WS,
    WORKSPACE,
)
from qqbot.domains.media.preprocess import native_image, vision_image
from qqbot.domains.media.download import download_images as media_download
from qqbot.domains.media.vision import classify_sticker, describe_sticker
from qqbot.domains.media.library import (
    CATEGORY_CN,
    IMAGE_META,
    INDEX_FILE,
    LAST_STICKER_INFO,
    MEME_DIR,
    MEME_RE,
    STICKER_CATEGORIES,
    STICKER_META,
    STICKER_META_FILE,
    extract_note_keywords,
    find_by_keyword,
    find_existing_sticker,
    find_index_hit,
    find_signature_match,
    history_hint,
    index_add,
    index_keywords,
    is_sticker_path,
    is_sticker_rel,
    load_index,
    load_sticker_meta,
    pick_meme,
    remember_sticker_info,
    remember_sticker_meta,
    resolve_meme,
    save_index,
    save_sticker_meta,
    sticker_signature,
    category_from_text,
    should_hint,
)
from qqbot.domains.media.stickers import collect_sticker
from qqbot.domains.growth import profile as growth_profile
from qqbot.domains.growth import reflect as growth_reflect
from qqbot.domains.growth import style as growth_style
from qqbot.domains.growth import emotion as growth_emotion
from qqbot.domains.growth import important as growth_important
from qqbot.domains.group.slang import (
    GROUP_LOG_DIR,
    GROUP_SLANG_DIR,
    load_network_memes,
    load_slang,
    log_group_message,
    network_meme_hint,
    save_network_memes,
    save_slang,
)
from qqbot.domains.qzone import publish as qzone_publish
from qqbot.domains.group import proactive as group_proactive
from qqbot.domains.autonomy.state import (
    AUT_REPORT_DIR,
    autonomy_cfg,
    aut_seen_set,
    load_aut_seen,
    load_aut_state,
    load_interests,
    mark_aut_seen,
    read_new_l1,
    save_aut_state,
    save_interests,
    similar_topic,
)
from qqbot.domains.autonomy.bili import (
    apply_interest,
    compose_share_text,
    fetch_bili_feed,
    fetch_bili_view,
    pick_topic,
)
from qqbot.domains.autonomy import round as autonomy_round
from qqbot.domains.autonomy import interests as autonomy_interests
from qqbot.clients.memory import (
    cmem_call,
    l0_recent as l0_recent_text,
    long_term_memory as long_term_memory_text,
    persona_context as full_persona_text,
    recent_dialogue as recent_dialogue_text,
)

SESSION_SCOPES_FILE = DSH_HOME / "session-scopes.json"


def save_session_scope(chat_key: str, sid: str) -> None:
    if not sid or not chat_key.startswith(("private:", "group:")):
        return
    kind, _, target = chat_key.partition(":")
    try:
        uid = int(target)
    except ValueError:
        return
    data = {}
    if SESSION_SCOPES_FILE.exists():
        try:
            data = json.loads(SESSION_SCOPES_FILE.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001
            data = {}
    entry = {
        "userId": str(uid) if kind == "private" else "",
        "scope": f"private:{uid}" if kind == "private" else f"group:{uid}",
        "chat": chat_key,
    }
    if data.get(sid) == entry:
        return
    data[sid] = entry
    try:
        SESSION_SCOPES_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def sync_session_scopes() -> None:
    state = load_state()
    for chat_key, value in state.items():
        if isinstance(value, dict):
            save_session_scope(str(chat_key), str(value.get("sid") or ""))
        elif isinstance(value, str):
            save_session_scope(str(chat_key), value)
AUTH_COOKIE_PREFIX = "dsh-auth-"
AUTH_COOKIE_TTL_MS = 60 * 60 * 1000

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_DIR / "bridge.log", encoding="utf-8"), logging.StreamHandler()],
)
log = logging.getLogger("bridge")
PROACTIVE = CONFIG.get("proactive") or {}
LOCKS: dict[str, asyncio.Lock] = {}


def chat_lock(key: str) -> asyncio.Lock:
    lock = LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        LOCKS[key] = lock
    return lock


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _decode_b64url(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _extract_secret(text: str) -> bytes | None:
    lines = text.splitlines()
    record = "client-connection/browser-session"
    for idx, line in enumerate(lines):
        if line.strip() != record + ":":
            continue
        indent = len(line) - len(line.lstrip(" "))
        for follow in lines[idx + 1:]:
            stripped = follow.strip()
            if stripped and (len(follow) - len(follow.lstrip(" "))) <= indent:
                break
            if stripped.startswith("secret:"):
                raw = stripped.partition(":")[2].strip().strip("'\"")
                return _decode_b64url(raw) if raw else None
    return None


def build_cookie(secret: bytes, authority: str) -> str:
    name = AUTH_COOKIE_PREFIX + _b64url(hashlib.sha256(authority.encode()).digest())
    now = int(time.time() * 1000)
    payload = {"version": 1, "authority": authority, "issuedAt": now, "expiresAt": now + AUTH_COOKIE_TTL_MS}
    body = _b64url(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode())
    sig = _b64url(hmac.new(secret, body.encode("ascii"), hashlib.sha256).digest())
    return f"{name}=v1.{body}.{sig}"


class Dsh:
    def __init__(self) -> None:
        self.http = aiohttp.ClientSession()
        self.cookie = ""
        self.cookie_at = 0.0

    def _authority(self) -> str:
        return CONFIG["dsh_base"].split("://", 1)[-1]

    async def refresh(self) -> None:
        text = (DSH_HOME / ".credentials.yaml").read_text(encoding="utf-8")
        secret = _extract_secret(text)
        if not secret:
            raise RuntimeError("no browser-session secret in " + str(DSH_HOME))
        self.cookie = build_cookie(secret, self._authority())
        self.cookie_at = time.time()
        log.info("cookie refreshed (len %s)", len(self.cookie))

    async def rpc(self, method: str, args: dict) -> dict:
        if not self.cookie or time.time() - self.cookie_at > AUTH_COOKIE_TTL_MS / 1000 - 300:
            await self.refresh()
        body = {"type": "client-request", "rpcId": str(uuid.uuid4()), "method": method, "payload": {"args": args}}
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                # 每次用新连接：避免复用到被服务端关掉的 keep-alive 连接
                async with aiohttp.ClientSession() as sess:
                    async with sess.post(
                        CONFIG["dsh_base"] + "/api/" + method,
                        json=body,
                        headers={"cookie": self.cookie, "origin": CONFIG["dsh_base"], "referer": CONFIG["dsh_base"] + "/"},
                        timeout=aiohttp.ClientTimeout(total=120),
                    ) as r:
                        if r.status == 401 and attempt < 2:
                            await self.refresh()
                            continue
                        data = await r.json()
                        res = data.get("result") or {}
                        if not res.get("ok"):
                            raise RuntimeError(f"{method} failed: {res.get('error')}")
                        return res.get("value") or {}
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_exc = exc
                log.warning("rpc %s 连接异常（第 %s 次）：%s", method, attempt + 1, exc)
                await asyncio.sleep(0.6)
        raise RuntimeError(f"{method} 重试后仍失败：{last_exc}")

    async def projections(self, sid: str) -> dict:
        return await self.rpc("session/projections", {"request": {"sessionId": sid}})

    async def create_session(self) -> str:
        value = await self.rpc("session/create", {"request": {"cwd": CONFIG["cwd"]}})
        sid = str(value.get("sessionId"))
        try:
            await self.rpc(
                "commands/execute",
                {"agentId": sid, "line": "/permission danger-full-access", "submittedAttachments": []},
            )
            log.info("session %s permission -> danger-full-access", sid)
        except Exception as exc:  # noqa: BLE001
            log.warning("set permission failed: %s", exc)
        return sid

    async def prompt(self, sid: str, text: str, images: list[str] | None = None) -> None:
        content: list[dict] = [{"type": "text", "text": text}]
        for image in (images or [])[:3]:
            try:
                mime, raw = native_image(Path(image))
                content.append({
                    "type": "image",
                    "mediaType": f"image/{mime}",
                    "data": base64.b64encode(raw).decode(),
                    "name": Path(image).name[:80],
                })
            except Exception as exc:  # noqa: BLE001
                log.warning("图片附件准备失败：%s", exc)
        await self.rpc(
            "session/prompt",
            {
                "request": {
                    "requestId": str(uuid.uuid4()),
                    "sessionId": sid,
                    "mode": "queue",
                    "content": content,
                    "clientTimeZone": "Asia/Shanghai",
                }
            },
        )

    async def page(self, sid: str, through: int) -> list:
        value = await self.rpc(
            "session/page",
            {"request": {"address": {"kind": "session", "sessionId": sid}, "throughSeq": through, "maxMessages": 120}},
        )
        return value.get("records") or []

    async def wait_reply(self, sid: str, after_seq: int, timeout: float = 150.0) -> str:
        deadline = time.time() + timeout
        text = ""
        while time.time() < deadline:
            await asyncio.sleep(1.5)
            proj = await self.projections(sid)
            as_of = int(proj.get("asOfSeq") or 0)
            records = await self.page(sid, as_of)
            parts = []
            ended = False
            for rec in records:
                ev = (rec or {}).get("event") or {}
                if int(ev.get("seq") or 0) <= after_seq:
                    continue
                if ev.get("type") == "assistant/message":
                    data = ev.get("data") or {}
                    msg = data.get("message") or {}
                    for c in msg.get("content") or []:
                        if isinstance(c, dict) and c.get("type") in ("text", "markdown"):
                            parts.append(c.get("text", ""))
                if ev.get("type") == "turn/end":
                    ended = True
            if parts:
                text = "\n".join(parts).strip()
            if ended:
                break
        return text



def sanitize_markdown(text: str) -> str:
    """把 Markdown 答案卡语气清理成聊天文本：去加粗/标题/水平线，把 [文字](链接) 展开。"""
    text = text or ""
    if "```" in text:
        return text
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1 \2", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", text)
    text = re.sub(r"(?m)^\s*(?:-{3,}|\*{3,})\s*$", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_bubbles(text: str) -> list[str]:
    """按句子分气泡；一句话不硬切，只有超长单句才按逗号兜底。"""
    try:
        limit = max(1, int(CONFIG.get("split_max_bubbles", 3)))
        min_len = max(10, int(CONFIG.get("split_min_chars", 40)))
    except (TypeError, ValueError):
        limit, min_len = 3, 40
    text = (text or "").strip()
    if len(text) <= min_len or limit <= 1:
        return [text]
    sentences = [s.strip() for s in re.findall(r"[^。！？!?…~\n]+[。！？!?…~]?", text) if s.strip()]
    if len(sentences) <= 1:
        if len(text) <= 1200:
            return [text]
        units = [s.strip() for s in re.split(r"(?<=[，,；;、])", text) if s.strip()]
        if len(units) <= 1:
            units = [text[i:i + 600] for i in range(0, len(text), 600)]
    else:
        units = sentences
    target = max(24, len(text) // limit)
    chunks: list[str] = []
    current = ""
    for unit in units:
        if current and len(current) >= target and len(chunks) < limit - 1:
            chunks.append(current.strip())
            current = unit
        else:
            current += unit
    if current.strip():
        chunks.append(current.strip())
    while len(chunks) > limit:
        chunks[-2] += chunks.pop()
    return [c for c in chunks if c]


class OneBot:
    def __init__(self) -> None:
        self.http = aiohttp.ClientSession(headers={"Authorization": f"Bearer {TOKEN_OB_HTTP}"})

    async def _post(self, url: str, payload: dict) -> int:
        async with self.http.post(url, json=payload) as r:
            return r.status

    async def send(self, message_type: str, target: int, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        if not STICKER_META:
            load_sticker_meta()
        categories = MEME_RE.findall(text)
        clean = MEME_RE.sub("", text).strip()
        clean = sanitize_markdown(clean)
        if len(clean) > 1500:
            clean = clean[:1500] + "……"
        images: list[dict] = []
        custom_faces: list[tuple[str, bytes]] = []
        for token in categories:
            path = resolve_meme(token)
            if not path:
                log.info("meme 找不到：%s", token)
                continue
            try:
                raw = Path(path).read_bytes()
            except OSError:
                continue
            rel = ""
            try:
                rel = str(Path(path).resolve().relative_to(MEME_DIR.resolve())).replace("\\", "/")
            except Exception:  # noqa: BLE001
                rel = ""
            meta = STICKER_META.get(rel) or {}
            if meta.get("emoji_id"):
                custom_faces.append((str(meta["emoji_id"]), raw))
                continue
            data = {"file": "base64://" + base64.b64encode(raw).decode()}
            if meta.get("sub_type") == 1:
                data["sub_type"] = 1
                data["summary"] = str(meta.get("summary") or "[动画表情]")
            images.append({"type": "image", "data": data})
        if not clean and not images and not custom_faces:
            return
        if message_type == "private":
            url = CONFIG["onebot_http"] + "/send_private_msg"
            base_payload = {"user_id": target}
        else:
            url = CONFIG["onebot_http"] + "/send_group_msg"
            base_payload = {"group_id": target}
        bubbles = split_bubbles(clean) if clean else []
        for index, bubble in enumerate(bubbles):
            if not bubble:
                continue
            message = bubble
            status = await self._post(url, {**base_payload, "message": message})
            log.info("send %s %s -> %s (text bubble=%s/%s)", message_type, target, status, index + 1, len(bubbles))
            if index < len(bubbles) - 1:
                await asyncio.sleep(random.uniform(1.2, 3.2))
        if images:
            if bubbles:
                await asyncio.sleep(random.uniform(0.8, 2.0))
            message = images
            status = await self._post(url, {**base_payload, "message": message})
            log.info("send %s %s -> %s (image x%s)", message_type, target, status, len(images))
        for emoji_id, raw in custom_faces:
            if bubbles or images:
                await asyncio.sleep(random.uniform(0.6, 1.4))
            payload = {**base_payload, "emoji_id": emoji_id}
            status = await self._post(CONFIG["onebot_http"] + "/send_custom_face", payload)
            if status != 200:
                data = {"file": "base64://" + base64.b64encode(raw).decode(), "sub_type": 1, "summary": "[动画表情]"}
                status = await self._post(url, {**base_payload, "message": [{"type": "image", "data": data}]})
            log.info("send %s %s -> %s (sticker)", message_type, target, status)

    async def post_qzone(self, text: str, ugc_right: int = 4) -> int:
        payload = {"content": (text or "").strip(), "ugc_right": int(ugc_right)}
        return await self._post(CONFIG["onebot_http"] + "/send_qzone_msg", payload)


def local_path_from(raw: str) -> Path | None:
    """把 OneBot 的 file/file:// 字段解析成本地路径。"""
    if not raw:
        return None
    from urllib.parse import unquote, urlparse

    if raw.startswith("file://"):
        path = unquote(urlparse(raw).path)
        if re.match(r"^/[A-Za-z]:", path):
            path = path[1:]
        candidate = Path(path)
        return candidate if candidate.is_file() else None
    if re.match(r"^[A-Za-z]:[\\/]", raw) or raw.startswith("\\\\"):
        candidate = Path(raw)
        return candidate if candidate.is_file() else None
    return None


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def state_entry(chat_key: str) -> dict:
    raw = load_state().get(chat_key)
    if isinstance(raw, str):
        return {"sid": raw, "seq": 0}
    if isinstance(raw, dict):
        return {"sid": str(raw.get("sid") or ""), "seq": int(raw.get("seq") or 0)}
    return {"sid": "", "seq": 0}


def set_state(chat_key: str, sid: str, seq: int | None = None) -> None:
    state = load_state()
    current = state_entry(chat_key)
    current["sid"] = sid or current["sid"]
    if seq is not None:
        current["seq"] = int(seq)
    state[chat_key] = current
    save_state(state)
    save_session_scope(chat_key, current["sid"])


def split_chat(chat_key: str) -> tuple[str, int]:
    kind, _, target = chat_key.partition(":")
    try:
        return kind, int(target)
    except ValueError:
        return "private", 0


async def session_watch(dsh: Dsh, onebot: OneBot) -> None:
    """盯着所有绑定会话：DSH 自己冒出来的话（主动开口），转发到 QQ。"""
    while True:
        await asyncio.sleep(8)
        try:
            state = load_state()
            for chat_key in list(state.keys()):
                sid = state_entry(chat_key)["sid"]
                if not sid:
                    continue
                lock = chat_lock(chat_key)
                if lock.locked():
                    continue
                try:
                    proj = await dsh.projections(sid)
                    as_of = int(proj.get("asOfSeq") or 0)
                except Exception:  # noqa: BLE001
                    continue
                last = state_entry(chat_key)["seq"]
                if SUPPRESS.get(chat_key, 0) > 0:
                    # 内部轮（例如写表情包理解），不转发，只推进基线
                    set_state(chat_key, sid, as_of)
                    continue
                if last == 0:
                    # 首次接管（老状态没有 seq）：只记基线，不补发历史
                    set_state(chat_key, sid, as_of)
                    log.info("初始化会话基线 %s seq=%s", chat_key, as_of)
                    continue
                if as_of <= last:
                    continue
                try:
                    records = await dsh.page(sid, as_of)
                except Exception:  # noqa: BLE001
                    continue
                parts = []
                for rec in records:
                    ev = (rec or {}).get("event") or {}
                    if int(ev.get("seq") or 0) <= last:
                        continue
                    if ev.get("type") != "assistant/message":
                        continue
                    data = ev.get("data") or {}
                    msg = data.get("message") or {}
                    for block in msg.get("content") or []:
                        if isinstance(block, dict) and block.get("type") in ("text", "markdown"):
                            parts.append(block.get("text", ""))
                text = "\n".join(p for p in parts if p).strip()
                if not text:
                    set_state(chat_key, sid, as_of)
                    continue
                kind, target = split_chat(chat_key)
                async with lock:
                    await onebot.send(kind, target, text)
                    set_state(chat_key, sid, as_of)
                log.info("会话自主动转发 (%s): %s", chat_key, text[:160])
        except Exception as exc:  # noqa: BLE001
            log.warning("session_watch err: %s", exc)


def extract_text(event: dict) -> str:
    parts = []
    for seg in event.get("message") or []:
        if seg.get("type") == "text":
            parts.append(seg.get("data", {}).get("text", ""))
    return "".join(parts).strip()


def sender_name(event: dict) -> str:
    sender = event.get("sender") or {}
    name = str(sender.get("card") or sender.get("nickname") or "").strip()
    return name


def is_addressed(event: dict, text: str = "") -> bool:
    """私聊永远算；群聊只认 @ 它 或 戳一戳。"""
    if event.get("message_type") == "private":
        return True
    for seg in event.get("message") or []:
        if seg.get("type") == "at" and str(seg.get("data", {}).get("qq")) == str(BOT_QQ):
            return True
        if seg.get("type") == "poke":
            target = str(seg.get("data", {}).get("qq") or seg.get("data", {}).get("target_id") or "")
            if target in ("", str(BOT_QQ)):
                return True
    return False


PENDING: dict[str, dict] = {}
SUPPRESS: dict[str, int] = {}
ACTIVE_GROUP: dict[str, float] = {}
INTERJECT: dict[str, dict] = {}
GROUP_SEEN: dict[str, float] = {}
GROUP_PRO_STATE: dict[str, dict] = {}


async def extract_group_slang(dsh: Dsh, gid: str) -> None:
    path = GROUP_LOG_DIR / f"{gid}.jsonl"
    if not path.exists():
        return
    state_path = GROUP_SLANG_DIR / "state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        state = {}
    last_ts = int(state.get(f"ts_{gid}") or 0)
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    fresh = [row for row in rows if int(row.get("ts") or 0) > last_ts]
    if not fresh:
        return
    convo = "\n".join(str(row.get("text", "")) for row in fresh[-200:])
    if len(convo) < 80:
        return
    chat_key = f"group:{gid}"
    existing = load_slang(gid)
    existing_list = "\n".join(
        f"- {i.get('term')}：{i.get('meaning') or '（未记）'}（已见 {i.get('count')} 次）" for i in existing[:40]
    ) or "（还没有）"
    prompt = (
        "（内部记录，不要回复用户）下面是群里最近的聊天：\n" + convo[:4000] + "\n\n"
        f"已有黑话表：\n{existing_list}\n\n"
        "找出聊天里反复出现的黑话、口癖、梗或特定称呼（出现 2 次以上）。\n"
        "重要：如果这次看到的说法就是表里已有某条（哪怕叫法略有不同），**必须直接复用表里的名字**，不要另起新名；"
        "表里已有、这次聊天里又出现的，也要列出来（同名，occurrences 填这次出现的次数），用来刷新它的次数和最后出现时间。"
        "如果这次看到了更准确的意思或更好的原话例子，就把 meaning/example 一起更新（名字保持不变）。"
        "只有确实是全新的说法才给新名字。\n"
        "只输出 JSON 数组："
        '[{"term":"说法","meaning":"大概什么意思","example":"原话例子","occurrences":2}]; 没有就输出 []。不要输出别的。'
    )
    reply = await maintenance_turn(dsh, chat_key, prompt)
    match = re.search(r"\[.*\]", reply or "", re.S)
    if not match:
        return
    try:
        found = json.loads(match.group(0))
    except Exception:  # noqa: BLE001
        return
    items = load_slang(gid)
    by_term = {str(i.get("term")): i for i in items}
    now = int(time.time())
    for item in found if isinstance(found, list) else []:
        if not isinstance(item, dict):
            continue
        term = str(item.get("term") or "").strip()[:24]
        if not term:
            continue
        meaning = str(item.get("meaning") or "").strip()[:80]
        example = str(item.get("example") or "").strip()[:80]
        occurrences = max(2, int(item.get("occurrences") or 2))
        if term in by_term:
            entry = by_term[term]
            entry["count"] = int(entry.get("count") or 0) + occurrences
            entry["meaning"] = meaning or entry.get("meaning", "")
            entry["example"] = example or entry.get("example", "")
            entry["last_seen"] = now
        else:
            by_term[term] = {"term": term, "meaning": meaning, "example": example, "count": occurrences, "last_seen": now}
    merged = sorted(by_term.values(), key=lambda x: int(x.get("count") or 0), reverse=True)
    merged = [i for i in merged if now - int(i.get("last_seen") or 0) < 30 * 86400][:40]
    save_slang(gid, merged)
    state[f"ts_{gid}"] = max(int(row.get("ts") or 0) for row in fresh)
    try:
        GROUP_SLANG_DIR.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    log.info("群黑话更新 (%s): %s", gid, [i.get("term") for i in merged[:8]])


async def group_slang_loop(dsh: Dsh) -> None:
    await asyncio.sleep(60)
    while True:
        try:
            cfg = {"enabled": True, "extract_hour": 22, "min_messages": 30}
            cfg.update(CONFIG.get("group_slang") or {})
            if cfg.get("enabled", True):
                state_path = GROUP_SLANG_DIR / "state.json"
                try:
                    state = json.loads(state_path.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    state = {}
                today = time.strftime("%Y-%m-%d")
                if time.localtime().tm_hour >= int(cfg.get("extract_hour", 22)) and state.get("date") != today:
                    for gid in CONFIG.get("allowed_groups") or []:
                        gid_s = str(gid)
                        log_path = GROUP_LOG_DIR / f"{gid_s}.jsonl"
                        if log_path.exists() and len(log_path.read_text(encoding="utf-8").splitlines()) >= int(cfg.get("min_messages", 30)):
                            await extract_group_slang(dsh, gid_s)
                    GROUP_SLANG_DIR.mkdir(parents=True, exist_ok=True)
                    state["date"] = today
                    state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            log.warning("group_slang_loop err: %s", exc)
        await asyncio.sleep(1800)


def group_proactive_cfg() -> dict:
    merged = {
        "enabled": True,
        "min_minutes": 90,
        "max_minutes": 180,
        "quiet_hours": "0-8",
        "idle_minutes": 30,
        "daily_max": 2,
    }
    merged.update(CONFIG.get("group_proactive") or {})
    return merged
LAST_INBOUND: dict[str, float] = {}
GROUP_HISTORY: dict[str, list[dict]] = {}


def remember_group(chat_key: str, user_id: int, text: str) -> None:
    if not text:
        return
    items = GROUP_HISTORY.setdefault(chat_key, [])
    items.append({"user": str(user_id), "text": text[:200]})
    del items[:-10]
    log_group_message(chat_key, user_id, text)


async def topic_relevant(chat_key: str, text: str) -> bool:
    """窗口内不 @ 的消息：问一下模型这条是不是在跟大肥鱼说话/它会不会感兴趣。"""
    try:
        key = DEEPSEEK_KEY_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    history = GROUP_HISTORY.get(chat_key) or []
    lines = "\n".join(f"{item['user']}: {item['text']}" for item in history[-8:])
    prompt = (
        "你在一个 QQ 群里，扮演的角色叫「大肥鱼」，一条爱偷吃 token、说话简短傲娇的胖鱼。\n"
        f"最近的群聊：\n{lines}\n\n"
        f"新消息：{text}\n\n"
        "判断：这条新消息是在跟大肥鱼说话吗？或者跟它有关、是它会感兴趣的话题吗？"
        "只回答 YES 或 NO，不要解释。"
    )
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 8,
        "temperature": 0,
    }
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.post(
                "https://api.deepseek.com/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {key}"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                data = await r.json()
        answer = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip().upper()
        return answer.startswith("YES")
    except Exception as exc:  # noqa: BLE001
        log.warning("topic_relevant failed: %s", exc)
        return False


def group_activity_cfg() -> dict:
    merged = {
        "followup_seconds": 300,
        "gate_skip_probability": 0.6,
        "interject_probability": 0.15,
        "interject_min_gap_seconds": 180,
        "interject_daily_max": 20,
    }
    merged.update(CONFIG.get("group_activity") or {})
    return merged


def interject_allowed(chat_key: str) -> bool:
    cfg = group_activity_cfg()
    state = INTERJECT.get(chat_key) or {}
    today = time.strftime("%Y-%m-%d")
    if state.get("date") != today:
        state = {"date": today, "count": 0, "last": 0}
        INTERJECT[chat_key] = state
    if int(state.get("count", 0)) >= int(cfg.get("interject_daily_max", 20)):
        return False
    return time.time() - float(state.get("last", 0)) >= float(cfg.get("interject_min_gap_seconds", 180))


def mark_interject(chat_key: str) -> None:
    state = INTERJECT.setdefault(chat_key, {"date": time.strftime("%Y-%m-%d"), "count": 0, "last": 0})
    if state.get("date") != time.strftime("%Y-%m-%d"):
        state.update({"date": time.strftime("%Y-%m-%d"), "count": 0})
    state["count"] = int(state.get("count", 0)) + 1
    state["last"] = time.time()


def followup_seconds() -> float:
    try:
        return max(0.0, float(group_activity_cfg().get("followup_seconds", 300)))
    except (TypeError, ValueError):
        return 300.0


def other_at(event: dict) -> bool:
    for seg in event.get("message") or []:
        if seg.get("type") == "at" and str(seg.get("data", {}).get("qq")) != str(BOT_QQ):
            return True
    return False


def merge_seconds() -> float:
    try:
        return max(0.0, float(CONFIG.get("merge_seconds", 6.5)))
    except (TypeError, ValueError):
        return 6.5


async def _process_locked(dsh: Dsh, onebot: OneBot, mtype: str, target: int, chat_key: str, text: str, images: list[str] | None = None) -> str:
    RECENT_TEXT[chat_key] = (text or "")[:500]
    entry = state_entry(chat_key)
    sid = entry["sid"]
    if not sid:
        sid = await dsh.create_session()
        set_state(chat_key, sid, 0)
        log.info("new dsh session %s for %s", sid, chat_key)
    try:
        prompt_started = time.time()
        proj = await dsh.projections(sid)
        baseline = int(proj.get("asOfSeq") or 0)
        extras: list[str] = []
        hint = history_hint() if should_hint(text) else ""
        if hint:
            extras.append(hint)
        if chat_key.startswith("group:"):
            gid = chat_key.split(":", 1)[1]
            items = load_slang(gid)[:8]
            if items:
                slang = "；".join(f"{i.get('term')}→{i.get('meaning') or '（未记）'}" for i in items)
                extras.append("（群里常用说法：" + slang[:400] + "。自然理解，别硬套、别解释。）")
        elif mtype == "private" and (CONFIG.get("allowed_groups") or []):
            gid = str((CONFIG.get("allowed_groups") or [])[0])
            items = load_slang(gid)[:6]
            if items:
                slang = "；".join(f"{i.get('term')}→{i.get('meaning') or '（未记）'}" for i in items)
                extras.append("（你和主人在群里学到的说法：" + slang[:300] + "。跟主人私聊时也可以自然用，别解释、别硬套。）")
        link_hint = await bili_link_hint(text)
        if link_hint:
            extras.append(link_hint)
        meme_hint = network_meme_hint(text)
        if meme_hint:
            extras.append(meme_hint)
        payload = text
        if extras:
            payload = text + "\n[[bridge-note]]\n" + "\n".join(extras) + "\n[[/bridge-note]]"
        await dsh.prompt(sid, payload, images=images)
        reply = await dsh.wait_reply(sid, baseline)
        log.info("reply (%s): %s", chat_key, reply[:200])
        if LAST_INBOUND.get(chat_key, 0) > prompt_started:
            # 生成期间你又发了新消息：这条已经过时，交给下一轮一起回
            log.info("处理期间来了新消息，丢弃这条过期回复 (%s)", chat_key)
        else:
            await onebot.send(mtype, target, reply)
        try:
            proj_after = await dsh.projections(sid)
            set_state(chat_key, sid, int(proj_after.get("asOfSeq") or 0))
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        log.exception("handle failed: %s", exc)
        try:
            await onebot.send(mtype, target, "呜……本鱼这边卡了一下，等会儿再试？")
        except Exception:  # noqa: BLE001
            pass
    return sid


async def process_message(dsh: Dsh, onebot: OneBot, mtype: str, target: int, chat_key: str, text: str, images: list[str] | None = None) -> str:
    async with chat_lock(chat_key):
        return await _process_locked(dsh, onebot, mtype, target, chat_key, text, images)


async def sticker_enrich_loop(dsh: Dsh) -> None:
    """后台补写表情包理解：索引里 caption 为空的，逐个让模型写描述。"""
    while True:
        await asyncio.sleep(60)
        try:
            users = CONFIG.get("allowed_users") or []
            if not users:
                continue
            chat_key = f"private:{int(users[0])}"
            if chat_lock(chat_key).locked():
                continue
            entries = load_index()
            targets = [
                e for e in entries
                if not (e.get("caption") or "").strip() and (MEME_DIR / e.get("file", "")).is_file()
            ]
            if not targets:
                continue
            entry = targets[0]
            path = str(MEME_DIR / entry["file"])
            hint = "主人之前发过这张表情包"
            if entry.get("tags"):
                hint += "，相关信息：" + "、".join(str(t) for t in entry["tags"][:4])
            log.info("后台补写表情理解：%s", entry["file"])
            await enrich_stickers(dsh, chat_key, [path], hint)
        except Exception as exc:  # noqa: BLE001
            log.warning("sticker_enrich_loop err: %s", exc)


async def enrich_stickers(dsh: Dsh, chat_key: str, images: list[str], context_text: str) -> None:
    """让模型在对话后自己写一条表情包理解（名字/描述/标签），写回索引。"""
    for img in images:
        rel_path = None
        try:
            raw = Path(img).read_bytes()
            digest = hashlib.sha256(raw).hexdigest()[:16]
            for candidate in MEME_DIR.rglob(f"u_{digest}*"):
                rel_path = str(candidate.relative_to(MEME_DIR))
                category = candidate.parent.name
                break
        except OSError:
            continue
        if not rel_path:
            continue
        prompt = (
            "（内部记录，不要回复用户、不要调用工具）"
            f"刚才收藏了一张表情包：{rel_path}，对话里主人说的是：{context_text[:120]!r}。"
            "用你自己的理解，只输出 JSON："
            '{"name":"主人怎么称呼它（不知道就空）","description":"一句话描述它长什么样、什么场合用",'
            '"tags":["2-4个中文关键词"]}'
        )
        reply = await maintenance_turn(dsh, chat_key, prompt)
        data = {}
        match = re.search(r"\{.*\}", reply or "", re.S)
        if match:
            try:
                data = json.loads(match.group(0))
            except Exception:  # noqa: BLE001
                data = {}
        if not isinstance(data, dict) or not (data.get("description") or data.get("name") or data.get("tags")):
            log.info("表情包理解没拿到有效 JSON，跳过：%s", rel_path)
            continue
        tags = [str(t) for t in (data.get("tags") or []) if str(t).strip()][:6]
        if data.get("name"):
            tags.insert(0, str(data["name"]))
        index_add(rel_path, category, str(data.get("description") or ""), tags)
        log.info("表情包理解已写入：%s %s %s", rel_path, data.get("name"), tags)


RECENT_TEXT: dict[str, str] = {}
LAST_SHARE: dict[str, dict] = {}
MAINT_STATE_FILE = DSH_HOME / "maintenance-session.json"
ACTIVITY_SESSION_FILE = DSH_HOME / "activity-session.json"
SESSION_MODES_FILE = DSH_HOME / "memory" / "session-modes.json"
MAINT_SESSION: dict[str, str] = {"sid": ""}
ACTIVITY_SESSION: dict[str, str] = {"sid": ""}
MAINT_LOCK = asyncio.Lock()
ACTIVITY_LOCK = asyncio.Lock()


def mark_session_mode_off(sid: str) -> None:
    """把维护会话登记为记忆档位 off：不捕获、不蒸馏。"""
    try:
        data = {"version": 1, "sessions": {}}
        if SESSION_MODES_FILE.exists():
            data = json.loads(SESSION_MODES_FILE.read_text(encoding="utf-8"))
        sessions = data.setdefault("sessions", {})
        sessions[sid] = {"mode": "off", "updatedAt": int(time.time() * 1000)}
        SESSION_MODES_FILE.parent.mkdir(parents=True, exist_ok=True)
        SESSION_MODES_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("写 session-modes 失败：%s", exc)


async def maintenance_sid(dsh: Dsh) -> str:
    if MAINT_SESSION["sid"]:
        return MAINT_SESSION["sid"]
    try:
        data = json.loads(MAINT_STATE_FILE.read_text(encoding="utf-8"))
        sid = str(data.get("sid") or "")
    except Exception:  # noqa: BLE001
        sid = ""
    if not sid:
        sid = await dsh.create_session()
        try:
            MAINT_STATE_FILE.write_text(json.dumps({"sid": sid}, ensure_ascii=False), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    mark_session_mode_off(sid)
    MAINT_SESSION["sid"] = sid
    return sid


async def maintenance_turn(dsh: Dsh, chat_key: str, prompt: str) -> str:
    sid = await maintenance_sid(dsh)
    async with MAINT_LOCK:
        return await internal_turn(dsh, sid, chat_key, prompt)


async def activity_sid(dsh: Dsh) -> str:
    if ACTIVITY_SESSION["sid"]:
        return ACTIVITY_SESSION["sid"]
    try:
        data = json.loads(ACTIVITY_SESSION_FILE.read_text(encoding="utf-8"))
        sid = str(data.get("sid") or "")
    except Exception:  # noqa: BLE001
        sid = ""
    if not sid:
        sid = await dsh.create_session()
        try:
            ACTIVITY_SESSION_FILE.write_text(json.dumps({"sid": sid}, ensure_ascii=False), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    mark_session_mode_off(sid)
    ACTIVITY_SESSION["sid"] = sid
    return sid


IMPORTANT_BEGIN = "<!-- persona-important:begin -->"
IMPORTANT_END = "<!-- persona-important:end -->"
IMPORTANT_USER_BEGIN = "<!-- user-important:begin -->"
IMPORTANT_USER_END = "<!-- user-important:end -->"
IMPORTANT_STORE = DSH_HOME / "persona-roles" / "state" / "important.json"
IMPORTANT_MAX = 8


def persona_reflect_cfg() -> dict:
    merged = {"enabled": True, "hour": 23, "min_gap_hours": 20}
    merged.update(CONFIG.get("persona_reflect") or {})
    return merged


def load_reflect_state() -> dict:
    return growth_reflect.load_state()


def record_share_feedback(chat_key: str, text: str) -> None:
    info = LAST_SHARE.pop(chat_key, None)
    if not info:
        return
    if time.time() - float(info.get("ts", 0)) > 1800:
        return
    message = (text or "").strip()
    if not message:
        return
    topic = str(info.get("topic", ""))
    if any(word in message for word in ("不感兴趣", "别发", "没意思", "不想看", "无聊", "换一个", "别刷")):
        delta = -0.8
    elif len(message) <= 3 or message in {"嗯", "哦", "好", "行", "可以", "收到", "好吧"}:
        delta = 0.0
    elif any(word in message for word in ("？", "?", "为什么", "怎么", "有意思", "笑死", "确实", "真的", "我也")):
        delta = 1.5
    elif len(message) >= 6:
        delta = 0.5
    else:
        delta = 0.0
    if delta == 0:
        log.info("分享反馈：%s 未加权（%s）", topic, message[:20])
        return
    apply_interest(topic, delta, "主人回应了分享：" + message[:40], "feedback")
    log.info("分享反馈加权：%s %+.1f", topic, delta)


async def run_persona_reflect(dsh: Dsh) -> bool:
    users = CONFIG.get("allowed_users") or []
    if not users:
        return False
    chat_key = f"private:{int(users[0])}"
    return await growth_reflect.run(lambda prompt: maintenance_turn(dsh, chat_key, prompt))


async def persona_reflect_loop(dsh: Dsh) -> None:
    await asyncio.sleep(60)
    while True:
        try:
            cfg = persona_reflect_cfg()
            if cfg.get("enabled", True):
                state = load_reflect_state()
                last = float(state.get("last_run_at") or 0)
                hour = time.localtime().tm_hour
                try:
                    start_s, _, end_s = str(cfg.get("active_hours") or "8-24").partition("-")
                    active = int(start_s) <= hour < int(end_s)
                except (TypeError, ValueError):
                    active = 8 <= hour < 24
                due = active and time.time() - last >= float(cfg.get("min_gap_hours", 8)) * 3600
                if due:
                    await run_persona_reflect(dsh)
        except Exception as exc:  # noqa: BLE001
            log.warning("persona_reflect_loop err: %s", exc)
        await asyncio.sleep(1800)


def add_l1_event(content: str) -> None:
    """桥接直接写一条结果记忆（只写结果，不写过程）。"""
    text = re.sub(r"\s+", " ", str(content or "")).strip()
    if not text:
        return
    text = re.sub(r"^事件：", "", text)
    for prefix in ("我记得：", "我记住：", "我眼中的主人："):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
            break
    # 同步进新记忆服务（L3 事件），否则自主刷/主动搭话的结果只留在旧库里
    try:
        payload = json.dumps({
            "text": text,
            "tier": "L3",
            "subject": "self",
            "tags": ["event", "bridge"],
            "embed": False,
            "ts": int(time.time()),
        }, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            CMEM_BASE + "/ingest", data=payload,
            headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=5).read()
    except Exception as exc:  # noqa: BLE001
        log.warning("写新记忆失败：%s", exc)


def add_l0_message(chat_key: str, text: str) -> None:
    """把桥接自己发出去的话补进 L0，让 L0 成为完整对话。"""
    text = str(text or "").strip()
    if not text:
        return
    sid = str((state_entry(chat_key) or {}).get("sid") or "")
    tags = ["raw"] + ([f"session:{sid}"] if sid else [])
    try:
        payload = json.dumps({
            "text": f"我：{text[:1000]}",
            "tier": "L0",
            "subject": "self",
            "tags": tags,
            "embed": False,
            "ts": int(time.time()),
        }, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            CMEM_BASE + "/ingest", data=payload,
            headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=5).read()
    except Exception as exc:  # noqa: BLE001
        log.warning("写 L0 失败：%s", exc)


def log_activity(kind: str, detail: str, thought: str = "") -> None:
    """活动日志：她做过什么，不进记忆。"""
    try:
        payload = json.dumps({
            "kind": kind,
            "detail": str(detail or "")[:500],
            "thought": str(thought or "")[:500],
        }, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            CMEM_BASE + "/activity", data=payload,
            headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=5).read()
    except Exception as exc:  # noqa: BLE001
        log.warning("写活动日志失败：%s", exc)


def quiet_now() -> bool:
    cfg = autonomy_cfg()
    try:
        start_s, _, end_s = str(cfg.get("quiet_hours") or "0-8").partition("-")
        start, end = int(start_s), int(end_s)
    except (TypeError, ValueError):
        start, end = 0, 8
    hour = time.localtime().tm_hour
    if start <= end:
        return start <= hour < end
    return hour >= start or hour < end


async def internal_turn(dsh: Dsh, sid: str, chat_key: str, prompt: str) -> str:
    SUPPRESS[chat_key] = SUPPRESS.get(chat_key, 0) + 1
    try:
        proj = await dsh.projections(sid)
        baseline = int(proj.get("asOfSeq") or 0)
        await dsh.prompt(sid, prompt)
        reply = await dsh.wait_reply(sid, baseline)
    except Exception as exc:  # noqa: BLE001
        log.warning("internal_turn failed: %s", exc)
        reply = ""
    finally:
        try:
            if state_entry(chat_key).get("sid") == sid:
                proj_after = await dsh.projections(sid)
                set_state(chat_key, sid, int(proj_after.get("asOfSeq") or 0))
        except Exception:  # noqa: BLE001
            pass
        SUPPRESS[chat_key] = max(0, SUPPRESS.get(chat_key, 0) - 1)
    return reply or ""


async def extract_interests(dsh: Dsh, chat_key: str, text: str) -> None:
    await autonomy_interests.extract(
        lambda prompt: maintenance_turn(dsh, chat_key, prompt), chat_key, text
    )


async def bili_link_hint(text: str) -> str:
    urls = re.findall(r"https?://[^\s<>\"']+", text or "")
    if not urls:
        return ""
    infos: list[dict] = []
    seen: set[str] = set()
    for url in urls[:3]:
        bvid = ""
        match = re.search(r"(BV[0-9A-Za-z]{10})", url)
        if match:
            bvid = match.group(1)
        elif any(host in url for host in ("b23.tv", "bili2233.cn", "bili22.cn")):
            try:
                async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as sess:
                    async with sess.get(url, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        final = str(resp.url)
                found = re.search(r"(BV[0-9A-Za-z]{10})", final)
                if found:
                    bvid = found.group(1)
            except Exception:  # noqa: BLE001
                continue
        if not bvid or bvid in seen:
            continue
        seen.add(bvid)
        info = await fetch_bili_view(bvid)
        infos.append(info or {"bvid": bvid, "title": "", "up": "", "duration": 0})
    if not infos:
        return ""
    lines = []
    for info in infos[:2]:
        label = f"BV{info['bvid'][2:]}" if info["bvid"].startswith("BV") else info["bvid"]
        meta = "《" + info["title"] + "》" if info.get("title") else ""
        up = " UP：" + info["up"] if info.get("up") else ""
        mins = f" {info['duration'] // 60}分{info['duration'] % 60}秒" if info.get("duration") else ""
        lines.append(f"{label}{meta}{up}{mins}")
    return "\n（你收到 B 站视频：" + "；".join(lines) + "。可以调 bili_subtitle 看字幕，画面重要时调 bili_frames 看几帧。）"


async def recent_scene(chat_key: str, limit: int = 6) -> str:
    """给自主刷看的现场：直接从 L0 取最近几条。"""
    text = await l0_recent_text(chat_key, limit)
    if not text:
        return "【最近】没有可参考的对话。"
    return "【最近几条】\n" + text


def _autonomy_deps(dsh: Dsh, onebot: OneBot) -> autonomy_round.Deps:
    users = [int(x) for x in (CONFIG.get("allowed_users") or [])]

    async def activity_sid_cb() -> str:
        return await activity_sid(dsh)

    async def internal(sid: str, chat_key: str, prompt: str) -> str:
        return await internal_turn(dsh, sid, chat_key, prompt)

    async def send_private(uid: int, text: str) -> None:
        await onebot.send("private", uid, text)

    async def consolidate(chat_key: str) -> None:
        await consolidate_interests(dsh, chat_key)

    return autonomy_round.Deps(
        users=users,
        activity_sid=activity_sid_cb,
        internal_turn=internal,
        maintenance_turn=lambda prompt: maintenance_turn(dsh, f"private:{users[0] if users else 0}", prompt),
        recent_scene=recent_scene,
        recent_text=RECENT_TEXT,
        last_share=LAST_SHARE,
        add_l0=add_l0_message,
        add_event=add_l1_event,
        log_activity=log_activity,
        send_private=send_private,
        lock=ACTIVITY_LOCK,
        consolidate=consolidate,
    )


async def run_autonomy_round(dsh: Dsh, onebot: OneBot) -> dict | None:
    return await autonomy_round.run_round(_autonomy_deps(dsh, onebot))


async def consolidate_interests(dsh: Dsh, chat_key: str) -> None:
    await autonomy_interests.consolidate(
        lambda prompt: maintenance_turn(dsh, chat_key, prompt), chat_key
    )


async def autonomy_loop(dsh: Dsh, onebot: OneBot) -> None:
    await autonomy_round.loop(_autonomy_deps(dsh, onebot))


def group_merge_seconds() -> float:
    try:
        return max(0.0, float(CONFIG.get("group_merge_seconds", 10)))
    except (TypeError, ValueError):
        return 10.0


async def collect_sticker_bg(path: Path, note: str) -> None:
    try:
        await asyncio.wait_for(collect_sticker(path, category_from_text(note), note), timeout=30)
    except asyncio.TimeoutError:
        log.warning("后台表情包分类超时：%s", path)
    except Exception as exc:  # noqa: BLE001
        log.warning("后台表情包分类失败：%s", exc)


async def schedule_flush(dsh: Dsh, onebot: OneBot, chat_key: str) -> None:
    entry = PENDING.get(chat_key) or {}
    window = group_merge_seconds() if entry.get("mtype") == "group" else merge_seconds()
    started = time.time()
    await asyncio.sleep(window)
    pending = PENDING.pop(chat_key, None)
    if not pending:
        return
    if pending.get("last_at", 0) > started + window - 0.3:
        # 睡眠期间又来了新消息（取消没赶上），重新计时，绝不提前回
        PENDING[chat_key] = pending
        old = pending.get("task")
        if old is not None:
            old.cancel()
        pending["task"] = asyncio.create_task(schedule_flush(dsh, onebot, chat_key))
        log.info("窗口内有新消息，重新计时 (%s)", chat_key)
        return
    texts = [t for t in pending.get("texts", []) if t]
    merged = "\n".join(texts)
    notes = []
    for img in pending.get("images", []):
        img_path = Path(img)
        meta = IMAGE_META.get(str(img_path)) or {}
        if meta.get("sticker"):
            notes.append(f"[表情包：{img_path}]")
            asyncio.create_task(collect_sticker_bg(img_path, merged))
        else:
            notes.append(f"[图片：{img_path}]")
    if notes:
        merged = (merged + "\n[[bridge-note]]\n" + "\n".join(notes) + "\n[[/bridge-note]]").strip()
    if not merged:
        return
    if pending.get("mtype") == "group" and not pending.get("addressed") and pending.get("need_gate"):
        cfg = group_activity_cfg()
        skip_gate = (not pending.get("interjected")) and random.random() < float(cfg.get("gate_skip_probability", 0.6))
        if not skip_gate and not await topic_relevant(chat_key, merged):
            log.info("整批话题不相关，跳过 (%s): %s", chat_key, merged[:80])
            return
    log.info("合并 %s 条消息后处理 (%s): %s", len(texts), chat_key, merged[:160])
    async with chat_lock(chat_key):
        await _process_locked(dsh, onebot, pending["mtype"], pending["target"], chat_key, merged, pending.get("images", []))
        if pending["mtype"] == "group":
            ACTIVE_GROUP[chat_key] = time.time()
            if pending.get("interjected"):
                mark_interject(chat_key)
        images = [str(p) for p in pending.get("images", [])]
        if images:
            await enrich_stickers(dsh, chat_key, images, merged)
        await extract_interests(dsh, chat_key, merged)


GUEST_TOUCH_TS: dict[str, float] = {}


async def touch_guest(uid: int, name: str, *, affinity: bool = True) -> None:
    """把群友的昵称/亲密度补进记忆服务的 profiles。"""
    if not uid or not name:
        return
    now = time.time()
    if now - float(GUEST_TOUCH_TS.get(str(uid)) or 0) >= 600:
        GUEST_TOUCH_TS[str(uid)] = now
        try:
            await cmem_call("POST", "/profiles", {"user_id": str(uid), "name": name})
        except Exception:  # noqa: BLE001
            pass
    if affinity:
        try:
            await cmem_call("POST", "/affinity", {"user_id": str(uid), "delta": 0.5})
        except Exception:  # noqa: BLE001
            pass


async def handle(dsh: Dsh, onebot: OneBot, event: dict, forced: bool = False) -> None:
    mtype = event.get("message_type")
    uid = int(event.get("user_id") or 0)
    gid = int(event.get("group_id") or 0)
    if mtype == "private":
        if uid not in CONFIG["allowed_users"]:
            return
        chat_key, target = f"private:{uid}", uid
    elif mtype == "group":
        if gid not in CONFIG["allowed_groups"]:
            return
        chat_key, target = f"group:{gid}", gid
    else:
        return

    text = extract_text(event)
    if text.startswith("/"):
        return
    speaker = sender_name(event) if mtype == "group" else ""
    if mtype == "group" and uid and speaker:
        asyncio.create_task(touch_guest(uid, speaker))
    elif mtype == "private" and uid:
        asyncio.create_task(touch_guest(uid, "九歌", affinity=False))
    if text:
        record_share_feedback(chat_key, text)
    if mtype == "group":
        GROUP_SEEN[chat_key] = time.time()
        if text:
            remember_group(chat_key, uid, text)

    async def download_images() -> list[str]:
        return await media_download(event, Path(CONFIG["cwd"]) / "inbox", IMAGE_META, local_path_from)

    async def collect_quietly(paths: list[str]) -> None:
        if not CONFIG.get("collect_group_stickers", True):
            return
        for path in paths:
            meta = IMAGE_META.get(path) or {}
            if not meta.get("sticker"):
                continue
            try:
                category = await collect_sticker(Path(path), category_from_text(text), text)
                if category:
                    log.info("群里静默收藏表情 -> %s (%s)", path, category)
            except Exception as exc:  # noqa: BLE001
                log.warning("collect_sticker failed: %s", exc)

    interjected = False
    if mtype == "group":
        addressed = forced or is_addressed(event, text)
        followed = (time.time() - ACTIVE_GROUP.get(chat_key, 0)) < followup_seconds()
        if other_at(event) and not addressed:
            await collect_quietly(await download_images())
            return
        if not addressed and not followed and chat_key not in PENDING:
            cfg = group_activity_cfg()
            chance = float(cfg.get("interject_probability", 0.15))
            if interject_allowed(chat_key) and len(text.strip()) >= 4 and random.random() < chance:
                interjected = True
                log.info("群插话机会 (%s): %s", chat_key, text[:60])
            else:
                await collect_quietly(await download_images())
                return
    else:
        addressed = True

    images = await download_images()

    if not text and not images:
        return

    pending = PENDING.setdefault(
        chat_key,
        {"texts": [], "images": [], "task": None, "mtype": mtype, "target": target, "addressed": False, "need_gate": False},
    )
    if text:
        if mtype == "group":
            owner_ids = {int(x) for x in (CONFIG.get("allowed_users") or [])}
            if uid in owner_ids:
                label = f"主人（{speaker or '九歌'}）"
            else:
                label = speaker or "群友"
            pending["texts"].append(f"{label}：{text}")
        else:
            pending["texts"].append(text)
    pending["images"].extend(images)
    pending["mtype"] = mtype
    pending["target"] = target
    pending["last_at"] = time.time()
    LAST_INBOUND[chat_key] = pending["last_at"]
    if chat_key == OWNER_CHAT_KEY:
        autonomy_round.note_user_reply(chat_key)
    if mtype == "group":
        pending["addressed"] = bool(pending.get("addressed")) or addressed
        if not pending["addressed"]:
            pending["need_gate"] = True
        if interjected:
            pending["interjected"] = True
    old = pending.get("task")
    if old is not None:
        old.cancel()
    pending["task"] = asyncio.create_task(schedule_flush(dsh, onebot, chat_key))


async def heartbeat() -> None:
    """把存活时间写进 health.json，供面板判断桥是否活着。"""
    path = HEALTH_FILE
    while True:
        try:
            path.write_text(
                json.dumps({"ts": int(time.time() * 1000), "pid": os.getpid()}), encoding="utf-8"
            )
        except Exception:  # noqa: BLE001
            pass
        await asyncio.sleep(20)


async def ask(dsh: Dsh, sid: str, prompt_text: str) -> str:
    proj = await dsh.projections(sid)
    baseline = int(proj.get("asOfSeq") or 0)
    await dsh.prompt(sid, prompt_text)
    return await dsh.wait_reply(sid, baseline)


SPONTANEOUS_PROMPT = (
    "（没人说话的时候。想到什么、刚看到什么、或者突然冒出的念头，就随手说一两句；"
    "想说什么就直接说，别加 SKIP。真的什么都不想说，才只回 SKIP 两个字母。）"
)


def strip_skip_lines(reply: str) -> str:
    lines = [line for line in (reply or "").splitlines() if line.strip().upper() not in ("SKIP", "跳过")]
    return "\n".join(lines).strip()


def is_skip(reply: str) -> bool:
    head = strip_skip_lines(reply).upper()
    return not head or head.startswith("SKIP") or head.startswith("跳过")


async def proactive_say(dsh: Dsh, onebot: OneBot, kind: str, extra: str = "") -> str | None:
    """让 DSH 主动说一句；它选择 SKIP 就不发。"""
    users = CONFIG.get("allowed_users") or []
    if not users:
        return None
    uid = int(users[0])
    chat_key = f"private:{uid}"
    sid = await activity_sid(dsh)
    prompt_text = SPONTANEOUS_PROMPT if kind == "spontaneous" else (
        f"（你刚刷完 B 站，今天的报告在 {extra}。如果里面有感兴趣、想跟我分享的，"
        "就说一两句话；没有就只回复 SKIP，不要发别的。）"
    )
    async with ACTIVITY_LOCK:
        try:
            reply = await ask(dsh, sid, prompt_text)
        except Exception as exc:  # noqa: BLE001
            log.warning("proactive[%s] 失败: %s", kind, exc)
            return None
    if is_skip(reply):
        log.info("proactive[%s] 本鱼这次没话说，跳过", kind)
        return None
    text = strip_skip_lines(reply)
    if not text:
        log.info("proactive[%s] 清洗后为空，跳过", kind)
        return None
    if len(text) > 800:
        text = text[:800] + "……"
    await onebot.send("private", uid, text)
    add_l0_message(f"private:{uid}", text)
    log.info("proactive[%s] 已发送: %s", kind, text[:160])
    return text


def parse_quiet(value: str) -> tuple[int, int]:
    try:
        start, _, end = str(value).partition("-")
        return int(start), int(end)
    except Exception:  # noqa: BLE001
        return (0, 8)


def in_quiet(now_hour: int) -> bool:
    start, end = parse_quiet(PROACTIVE.get("quiet_hours", "0-8"))
    if start <= end:
        return start <= now_hour < end
    return now_hour >= start or now_hour < end


PROACTIVE_STATE_FILE = DSH_HOME / "proactive-state.json"


def load_proactive_next() -> float:
    try:
        data = json.loads(PROACTIVE_STATE_FILE.read_text(encoding="utf-8"))
        return float(data.get("next_at") or 0)
    except Exception:  # noqa: BLE001
        return 0.0


def save_proactive_next(next_at: float) -> None:
    try:
        PROACTIVE_STATE_FILE.write_text(json.dumps({"next_at": int(next_at)}, ensure_ascii=False), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


async def proactive_loop(dsh: Dsh, onebot: OneBot) -> None:
    if not PROACTIVE.get("enabled", False):
        log.info("主动说话：未启用")
        return
    lo = max(10, int(PROACTIVE.get("min_minutes", 50)))
    hi = max(lo, int(PROACTIVE.get("max_minutes", 150)))
    log.info("主动说话：已启用，间隔 %s-%s 分钟", lo, hi)
    next_at = load_proactive_next()
    if next_at <= 0:
        next_at = time.time() + random.uniform(5, 10) * 60
        save_proactive_next(next_at)
    while True:
        wait = next_at - time.time()
        if wait > 0:
            await asyncio.sleep(min(wait, 3600))
            continue
        if in_quiet(time.localtime().tm_hour):
            log.info("主动说话：静默时段，跳过")
            next_at = time.time() + random.randint(lo, hi) * 60
            save_proactive_next(next_at)
            continue
        try:
            await proactive_say(dsh, onebot, "spontaneous")
        except Exception as exc:  # noqa: BLE001
            log.warning("proactive loop err: %s", exc)
        next_at = time.time() + random.randint(lo, hi) * 60
        save_proactive_next(next_at)
        log.info("主动说话：下次约 %s", time.strftime("%H:%M", time.localtime(next_at)))


async def group_proactive_say(dsh: Dsh, onebot: OneBot) -> str | None:
    groups = CONFIG.get("allowed_groups") or []
    if not groups:
        return None
    gid = int(groups[0])
    chat_key = f"group:{gid}"

    async def turn(prompt: str) -> str:
        sid = await activity_sid(dsh)
        async with ACTIVITY_LOCK:
            return await ask(dsh, sid, prompt)

    async def send(text: str) -> None:
        await onebot.send("group", gid, text)

    return await group_proactive.say(
        groups=groups,
        turn=turn,
        send=send,
        add_l0=lambda text: add_l0_message(chat_key, text),
        history=lambda key: GROUP_HISTORY.get(key) or [],
        mark_active=lambda key: ACTIVE_GROUP.__setitem__(key, time.time()),
    )


async def group_proactive_loop(dsh: Dsh, onebot: OneBot) -> None:
    await group_proactive.loop(
        cfg=group_proactive_cfg(),
        groups=CONFIG.get("allowed_groups") or [],
        turn=lambda prompt: maintenance_turn(dsh, OWNER_CHAT_KEY, prompt),
        send=lambda text: onebot.send("group", int((CONFIG.get("allowed_groups") or [0])[0]), text),
        add_l0=lambda text: add_l0_message(f"group:{int((CONFIG.get('allowed_groups') or [0])[0])}", text),
        history=lambda key: GROUP_HISTORY.get(key) or [],
        mark_active=lambda key: ACTIVE_GROUP.__setitem__(key, time.time()),
        seen=lambda key: float(GROUP_SEEN.get(key, 0)),
    )


async def report_watch(dsh: Dsh, onebot: OneBot) -> None:
    if not PROACTIVE.get("report_push", False):
        return
    folder = Path(PROACTIVE.get("report_dir") or "")
    if not folder.is_dir():
        log.warning("日报目录不存在：%s", folder)
        return
    seen: dict[str, float] = {}
    for f in folder.glob("*.md"):
        try:
            seen[str(f)] = f.stat().st_mtime
        except OSError:
            pass
    log.info("日报监听：已启动 %s（已有 %s 份）", folder, len(seen))
    while True:
        await asyncio.sleep(45)
        try:
            for f in folder.glob("*.md"):
                try:
                    mtime = f.stat().st_mtime
                except OSError:
                    continue
                if mtime > seen.get(str(f), 0):
                    seen[str(f)] = mtime
                    log.info("日报有更新：%s", f.name)
                    await proactive_say(dsh, onebot, "report", str(f))
        except Exception as exc:  # noqa: BLE001
            log.warning("report watch err: %s", exc)


PROFILE_STATE_FILE = DSH_HOME / "persona-roles" / "state" / "profile-refresh-state.json"


async def refresh_user_profile(dsh: Dsh) -> bool:
    return await growth_profile.run(
        lambda prompt: maintenance_turn(dsh, OWNER_CHAT_KEY, prompt)
    )


async def profile_refresh_loop(dsh: Dsh) -> None:
    await asyncio.sleep(120)
    while True:
        try:
            state = {}
            if PROFILE_STATE_FILE.exists():
                try:
                    state = json.loads(PROFILE_STATE_FILE.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    state = {}
            if time.time() - float(state.get("last_run") or 0) >= int(CONFIG.get("profile_refresh_days", 2)) * 86400:
                await refresh_user_profile(dsh)
        except Exception as exc:  # noqa: BLE001
            log.warning("画像刷新失败：%s", exc)
        await asyncio.sleep(6 * 3600)


STYLE_BEGIN = "<!-- style:begin -->"
STYLE_END = "<!-- style:end -->"
STYLE_PROPOSAL_FILE = DSH_HOME / "persona-roles" / "state" / "style-proposal.json"
STYLE_STATE_FILE = DSH_HOME / "persona-roles" / "state" / "style-review-state.json"
STYLE_DAYS = int(CONFIG.get("style_review_days", 3))


def style_block(constitution: str) -> str:
    match = re.search(re.escape(STYLE_BEGIN) + r"(.*?)" + re.escape(STYLE_END), constitution or "", re.S)
    return match.group(1).strip() if match else ""


async def run_style_review(dsh: Dsh, chat_key: str) -> bool:
    return await growth_style.run(
        lambda prompt: maintenance_turn(dsh, chat_key, prompt), chat_key
    )


async def style_review_loop(dsh: Dsh) -> None:
    await asyncio.sleep(300)
    while True:
        try:
            if not STYLE_PROPOSAL_FILE.exists():
                state = {}
                if STYLE_STATE_FILE.exists():
                    try:
                        state = json.loads(STYLE_STATE_FILE.read_text(encoding="utf-8"))
                    except Exception:  # noqa: BLE001
                        state = {}
                last = float(state.get("last_run") or 0)
                if time.time() - last >= STYLE_DAYS * 86400:
                    ok = await run_style_review(dsh, OWNER_CHAT_KEY)
                    if ok:
                        STYLE_STATE_FILE.write_text(json.dumps(
                            {"last_run": int(time.time())}, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            log.warning("style_review err: %s", exc)
        await asyncio.sleep(6 * 3600)


INJECT_FILE = DSH_HOME / "qq-inject.jsonl"
LAST_WAKE_TS = 0.0


async def inject_watch(dsh: Dsh, onebot: OneBot) -> None:
    """轮询 dsh-remembers 的主动唤醒文件；非静默事件由桥接生成一句主动消息。"""
    offset = INJECT_FILE.stat().st_size if INJECT_FILE.exists() else 0
    log.info("主动唤醒监听：%s（从 %s 字节开始）", INJECT_FILE, offset)
    while True:
        try:
            if INJECT_FILE.exists():
                size = INJECT_FILE.stat().st_size
                if size < offset:
                    offset = 0
                if size > offset:
                    with INJECT_FILE.open("r", encoding="utf-8") as handle:
                        handle.seek(offset)
                        lines = handle.readlines()
                        offset = handle.tell()
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            event = json.loads(line)
                        except Exception:  # noqa: BLE001
                            continue
                        if event.get("silent"):
                            log.info("主动唤醒：静默事件，跳过")
                            continue
                        global LAST_WAKE_TS
                        if time.time() - LAST_WAKE_TS < 10 * 60:
                            log.info("主动唤醒：距上次不到 10 分钟，跳过")
                            continue
                        LAST_WAKE_TS = time.time()
                        log.info("主动唤醒：收到非静默事件，生成一句")
                        await proactive_say(dsh, onebot, "spontaneous")
        except Exception as exc:  # noqa: BLE001
            log.warning("inject_watch err: %s", exc)
        await asyncio.sleep(15)


async def qzone_loop(dsh: Dsh, onebot: OneBot) -> None:
    await qzone_publish.loop(
        CONFIG.get("qzone") or {},
        lambda prompt: maintenance_turn(dsh, OWNER_CHAT_KEY, prompt),
        onebot.post_qzone,
        add_l1_event,
        lambda: [str(i.get("topic")) for i in load_interests()],
    )


async def emotion_check_loop(dsh: Dsh) -> None:
    await growth_emotion.loop(
        lambda prompt: maintenance_turn(dsh, OWNER_CHAT_KEY, prompt),
        CONFIG.get("emotion_check") or {},
    )


async def important_check_loop(dsh: Dsh) -> None:
    await growth_important.loop(
        lambda prompt: maintenance_turn(dsh, OWNER_CHAT_KEY, prompt),
        CONFIG.get("important_check") or {},
    )


async def important_file_loop(dsh: Dsh) -> None:
    await growth_important.file_loop()


async def memory_batch_loop() -> None:
    """批量蒸馏：L0→L1，多条 L1→L3，L1+L3→L4。"""
    await asyncio.sleep(60)
    while True:
        try:
            result = await cmem_call("POST", "/batch/run", {})
            if result.get("l1") or result.get("l3") or result.get("l4"):
                log.info("批量记忆：L1+%s L3+%s L4+%s", result.get("l1"), result.get("l3"), result.get("l4"))
        except Exception as exc:  # noqa: BLE001
            log.warning("memory_batch_loop err: %s", exc)
        await asyncio.sleep(300)


async def diary_loop() -> None:
    """每天 23 点后让记忆服务根据当天素材写一篇日记。"""
    await asyncio.sleep(90)
    state_path = DSH_HOME / "diary-state.json"
    while True:
        try:
            cfg = CONFIG.get("diary") or {}
            if cfg.get("enabled", True) and time.localtime().tm_hour >= int(cfg.get("hour", 23)):
                today = time.strftime("%Y-%m-%d")
                try:
                    state = json.loads(state_path.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    state = {}
                if state.get("last_date") != today:
                    existing = await cmem_call("GET", "/diary")
                    has_today = any(
                        str(item.get("date")) == today and str(item.get("text") or "").strip()
                        for item in (existing or [])
                        if isinstance(item, dict)
                    )
                    if not has_today:
                        result = await cmem_call("POST", "/diary/write", {"date": today})
                        if result.get("ok"):
                            state["last_date"] = today
                            state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
                            log.info("日记已写：%s 字", len(str(result.get("text") or "")))
                        else:
                            log.warning("日记写入失败：%s", result.get("error") or result)
                    else:
                        state["last_date"] = today
                        state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            log.warning("diary_loop err: %s", exc)
        await asyncio.sleep(15 * 60)


async def run() -> None:
    sync_session_scopes()
    load_sticker_meta()
    asyncio.create_task(heartbeat())
    dsh = Dsh()
    await dsh.refresh()
    onebot = OneBot()
    asyncio.create_task(inject_watch(dsh, onebot))
    asyncio.create_task(group_proactive_loop(dsh, onebot))
    asyncio.create_task(style_review_loop(dsh))
    asyncio.create_task(profile_refresh_loop(dsh))
    asyncio.create_task(qzone_loop(dsh, onebot))
    asyncio.create_task(emotion_check_loop(dsh))
    asyncio.create_task(important_check_loop(dsh))
    asyncio.create_task(important_file_loop(dsh))
    asyncio.create_task(memory_batch_loop())
    asyncio.create_task(diary_loop())
    asyncio.create_task(group_slang_loop(dsh))
    asyncio.create_task(report_watch(dsh, onebot))
    asyncio.create_task(session_watch(dsh, onebot))
    asyncio.create_task(sticker_enrich_loop(dsh))
    asyncio.create_task(autonomy_loop(dsh, onebot))
    backoff = 3
    meta_seen = 0
    while True:
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.ws_connect(
                    CONFIG["onebot_ws"], headers={"Authorization": f"Bearer {TOKEN_OB_WS}"}, heartbeat=30
                ) as ws:
                    log.info("connected to onebot ws %s", CONFIG["onebot_ws"])
                    backoff = 3
                    async for msg in ws:
                        if msg.type != aiohttp.WSMsgType.TEXT:
                            continue
                        try:
                            data = json.loads(msg.data)
                        except Exception:
                            continue
                        post_type = data.get("post_type")
                        if post_type == "meta_event":
                            meta_seen += 1
                            if meta_seen <= 2 or meta_seen % 20 == 0:
                                log.info("meta_event #%s: %s", meta_seen, data.get("meta_event_type"))
                            continue
                        if post_type == "notice":
                            notice_type = str(data.get("notice_type") or "")
                            sub_type = str(data.get("sub_type") or "")
                            target = str(data.get("target_id") or "")
                            is_poke = notice_type == "poke" or (notice_type == "notify" and sub_type == "poke")
                            if is_poke and (not target or target == str(BOT_QQ)):
                                gid = data.get("group_id")
                                uid = data.get("user_id")
                                log.info("poke event user=%s group=%s", uid, gid)
                                ev = {
                                    "post_type": "message",
                                    "message_type": "group" if gid else "private",
                                    "group_id": gid,
                                    "user_id": uid,
                                    "message": [{"type": "text", "data": {"text": "（戳了戳你）"}}],
                                }
                                asyncio.create_task(handle(dsh, onebot, ev, forced=True))
                            continue
                        if post_type == "message":
                            log.info(
                                "inbound message type=%s user=%s group=%s",
                                data.get("message_type"),
                                data.get("user_id"),
                                data.get("group_id"),
                            )
                            asyncio.create_task(handle(dsh, onebot, data))
        except Exception as exc:  # noqa: BLE001
            log.warning("ws error: %s; reconnect in %ss", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)


if __name__ == "__main__":
    asyncio.run(run())
