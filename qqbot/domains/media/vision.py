"""表情包视觉分类与描述。"""
from __future__ import annotations

import base64
import json
import logging
import re
from pathlib import Path

import aiohttp

from settings import DEEPSEEK_KEY_FILE, SILICONFLOW_KEY_FILE
from qqbot.domains.media.preprocess import vision_image

log = logging.getLogger("qqbot.media.vision")

CATEGORY_HINTS = {
    "happy": "开心、庆祝、期待、笑",
    "angry": "生气、威胁、催人、嫌弃",
    "sad": "难过、委屈、哭、低落",
    "confused": "疑惑、无语、问号脸",
    "surprised": "震惊、意外、吓到",
    "shy": "害羞、脸红、不好意思",
    "sleep": "困、睡觉、躺平、累",
    "affection": "喜欢、亲昵、贴贴、抱抱",
    "food": "吃的、馋、干饭、饿",
    "money": "钱、红包、穷、要钱",
    "greeting": "打招呼、你好、再见",
    "work": "上班、摸鱼、加班、学习",
    "entertainment": "搞笑、看戏、乐子、吃瓜",
    "teasing": "调侃、得意、嘲讽、坏笑",
    "reply": "收到、好的、回应、点头",
}
SF_KEY_FILE = SILICONFLOW_KEY_FILE
DEEPSEEK_KEY_FILE = DEEPSEEK_KEY_FILE
SF_VISION_MODEL = "Qwen/Qwen3-VL-30B-A3B-Instruct"


def _vision_prompt() -> str:
    lines = "\n".join(f"- {k}: {v}" for k, v in CATEGORY_HINTS.items())
    return f"给这张聊天表情包选一个最合适的类别。\n{lines}\n只输出 JSON：{{\"category\":\"...\"}}"


def _parse_category(text: str) -> str | None:
    match = re.search(r'"category"\s*:\s*"([a-z_]+)"', text or "")
    if match and match.group(1) in CATEGORY_HINTS:
        return match.group(1)
    for category in CATEGORY_HINTS:
        if category in (text or ""):
            return category
    return None


async def _classify_siliconflow(path: Path) -> str | None:
    try:
        key = SF_KEY_FILE.read_text(encoding="utf-8").strip()
        mime, raw = vision_image(path)
    except OSError:
        return None
    payload = {
        "model": SF_VISION_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": _vision_prompt()},
                {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{base64.b64encode(raw).decode()}"}},
            ],
        }],
        "max_tokens": 32,
        "temperature": 0.1,
    }
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.post(
                "https://api.siliconflow.cn/v1/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {key}"},
                timeout=aiohttp.ClientTimeout(total=60),
            ) as r:
                data = await r.json()
        text = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip().lower()
        return _parse_category(text)
    except Exception as exc:  # noqa: BLE001
        log.warning("siliconflow classify failed: %s", exc)
        return None


async def classify_sticker(path: Path) -> str:
    """先试 Qwen3-VL（硅基流动），失败再用 deepseek 兜底。"""
    category = await _classify_siliconflow(path)
    if category:
        return category
    try:
        key = DEEPSEEK_KEY_FILE.read_text(encoding="utf-8").strip()
        mime, raw = vision_image(path)
    except OSError:
        return "entertainment"
    payload = {
        "model": "deepseek-chat",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": _vision_prompt()},
                {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{base64.b64encode(raw).decode()}"}},
            ],
        }],
        "max_tokens": 32,
    }
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.post(
                "https://api.deepseek.com/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {key}"},
                timeout=aiohttp.ClientTimeout(total=60),
            ) as r:
                data = await r.json()
        text = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip().lower()
        return _parse_category(text) or "entertainment"
    except Exception as exc:  # noqa: BLE001
        log.warning("classify_sticker failed: %s", exc)
        return "entertainment"


async def describe_sticker(path: Path) -> dict:
    """让 Qwen3-VL 给表情包输出类别 + 描述 + 标签，供以后按关键词检索。"""
    try:
        key = SF_KEY_FILE.read_text(encoding="utf-8").strip()
        mime, raw = vision_image(path)
    except OSError:
        return {}
    lines = "\n".join(f"- {k}: {v}" for k, v in CATEGORY_HINTS.items())
    prompt = (
        "看这张聊天表情包，输出 JSON（不要解释）：\n"
        '{"category":"类别英文名","caption":"一句中文描述：里面有谁/什么角色、在做什么、什么表情或文字",'
        '"tags":["3到6个中文关键词"]}\n'
        f"类别只能从这些里选：\n{lines}"
    )
    payload = {
        "model": SF_VISION_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{base64.b64encode(raw).decode()}"}},
            ],
        }],
        "max_tokens": 200,
        "temperature": 0.1,
    }
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.post(
                "https://api.siliconflow.cn/v1/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {key}"},
                timeout=aiohttp.ClientTimeout(total=90),
            ) as r:
                data = await r.json()
        text = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        match = re.search(r"\{.*\}", text, re.S)
        info: dict = {}
        if match:
            try:
                info = json.loads(match.group(0))
            except Exception:  # noqa: BLE001
                info = {}
        category = str(info.get("category") or "").lower()
        if category not in CATEGORY_HINTS:
            category = _parse_category(text) or ""
        caption = str(info.get("caption") or "")
        if not caption:
            cap_match = re.search(r'"caption"\s*:\s*"([^"]*)"', text)
            caption = cap_match.group(1) if cap_match else ""
        tags = [str(t) for t in (info.get("tags") or []) if str(t).strip()][:8]
        if not tags:
            tag_match = re.search(r'"tags"\s*:\s*\[(.*?)\]', text, re.S)
            if tag_match:
                tags = [t.strip().strip('"\' ') for t in tag_match.group(1).split(",") if t.strip()][:8]
        return {"category": category, "caption": caption[:120], "tags": tags}
    except Exception as exc:  # noqa: BLE001
        log.warning("describe_sticker failed: %s", exc)
        return {}
