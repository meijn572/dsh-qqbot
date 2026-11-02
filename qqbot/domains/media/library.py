"""表情包元数据、索引和 [[meme]] 选择。

只处理本地文件，不依赖 bridge。
"""
from __future__ import annotations

import json
import logging
import random
import re
import time
from pathlib import Path

from settings import BOT_DIR

log = logging.getLogger("qqbot.media.library")

MEME_DIR = BOT_DIR / "stickers"
INDEX_FILE = MEME_DIR / "index.json"
STICKER_META_FILE = MEME_DIR / "meta.json"
IMAGE_META: dict[str, dict] = {}
STICKER_META: dict[str, dict] = {}
LAST_STICKER_INFO: dict[str, dict] = {}
MEME_RE = re.compile(r"\[\[meme:([^\]]+)\]\]")

STICKER_CATEGORIES = [
    "happy", "angry", "sad", "confused", "surprised", "shy", "sleep",
    "affection", "food", "money", "greeting", "work", "entertainment", "teasing", "reply",
]
CATEGORY_CN = {
    "开心": "happy", "笑": "happy", "庆祝": "happy", "高兴": "happy",
    "生气": "angry", "怒": "angry", "凶": "angry",
    "难过": "sad", "哭": "sad", "委屈": "sad",
    "疑惑": "confused", "无语": "confused", "问号": "confused",
    "震惊": "surprised", "惊讶": "surprised",
    "害羞": "shy", "脸红": "shy",
    "困": "sleep", "睡觉": "sleep", "躺平": "sleep",
    "喜欢": "affection", "贴贴": "affection", "抱": "affection",
    "吃": "food", "馋": "food", "干饭": "food", "饿": "food",
    "钱": "money", "红包": "money", "穷": "money",
    "你好": "greeting", "打招呼": "greeting", "再见": "greeting",
    "上班": "work", "摸鱼": "work", "加班": "work", "学习": "work",
    "搞笑": "entertainment", "看戏": "entertainment", "乐子": "entertainment",
    "调侃": "teasing", "得意": "teasing", "嘲讽": "teasing",
    "收到": "reply", "好的": "reply", "点头": "reply",
}
NOTE_STOPWORDS = [
    "现在", "能不能", "可不可以", "可以", "帮我", "收藏", "这个", "那个", "这张", "那张",
    "表情包", "表情", "图片", "一下", "请问", "怎么", "为什么", "是不是", "有没有",
    "放进", "存进", "收进", "库里", "里面", "给我", "我要", "想要", "记得", "记住",
    "吗", "呢", "呀", "啊", "吧", "了", "的", "地", "得", "是", "叫", "把", "和", "跟",
]


def load_sticker_meta() -> None:
    try:
        data = json.loads(STICKER_META_FILE.read_text(encoding="utf-8"))
        STICKER_META.clear()
        if isinstance(data, dict):
            STICKER_META.update({
                str(key).replace("\\", "/"): value
                for key, value in data.items()
                if isinstance(value, dict)
            })
    except Exception:  # noqa: BLE001
        STICKER_META.clear()


def save_sticker_meta() -> None:
    try:
        MEME_DIR.mkdir(parents=True, exist_ok=True)
        STICKER_META_FILE.write_text(json.dumps(STICKER_META, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def remember_sticker_meta(source: Path, rel: str) -> None:
    meta = IMAGE_META.get(str(source))
    if not meta or not meta.get("sticker"):
        return
    key = str(rel or "").replace("\\", "/")
    STICKER_META[key] = {
        "sticker": True,
        "emoji_id": str(meta.get("emoji_id") or ""),
        "emoji_package_id": str(meta.get("emoji_package_id") or ""),
        "key": str(meta.get("key") or ""),
        "summary": str(meta.get("summary") or "[动画表情]"),
        "sub_type": 1,
    }
    save_sticker_meta()


def is_sticker_rel(rel: str) -> bool:
    key = str(rel or "").replace("\\", "/")
    return bool((STICKER_META.get(key) or {}).get("sticker"))


def is_sticker_path(path: Path | str) -> bool:
    try:
        rel = str(Path(path).resolve().relative_to(MEME_DIR.resolve())).replace("\\", "/")
    except Exception:  # noqa: BLE001
        return False
    return is_sticker_rel(rel)


def remember_sticker_info(source: Path, rel: str) -> None:
    entry = next((e for e in load_index() if e.get("file") == rel), {})
    LAST_STICKER_INFO[str(source)] = {
        "file": rel,
        "caption": str(entry.get("caption") or ""),
        "tags": list(entry.get("tags") or []),
    }


def load_index() -> list[dict]:
    if not INDEX_FILE.exists():
        return []
    try:
        data = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001
        return []


def save_index(entries: list[dict]) -> None:
    INDEX_FILE.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")


def find_existing_sticker(name: str) -> Path | None:
    for path in MEME_DIR.rglob(name):
        if path.is_file():
            return path
    return None


def sticker_signature(path: Path) -> tuple[int, int, int] | None:
    try:
        from PIL import Image

        with Image.open(path) as im:
            width, height = im.size
            im = im.convert("L").resize((8, 8), Image.LANCZOS)
            pixels = list(im.getdata())
        avg = sum(pixels) / len(pixels)
        bits = "".join("1" if value > avg else "0" for value in pixels)
        return width, height, int(bits, 2)
    except Exception:  # noqa: BLE001
        return None


def find_signature_match(sig: tuple[int, int, int] | None) -> str | None:
    if not sig:
        return None
    width, height, value = sig
    for entry in load_index():
        if entry.get("w") != width or entry.get("h") != height or not entry.get("sig"):
            continue
        try:
            other = int(entry["sig"], 16)
        except (TypeError, ValueError):
            continue
        if bin(other ^ value).count("1") <= 2 and (MEME_DIR / entry["file"]).is_file():
            return str(entry["file"])
    return None


def extract_note_keywords(note: str) -> list[str]:
    text = (note or "").strip()
    if not text:
        return []
    for word in sorted(NOTE_STOPWORDS, key=len, reverse=True):
        text = text.replace(word, " ")
    parts = re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]{2,8}", text)
    words: list[str] = []
    for part in parts:
        part = part.strip()
        if part and part not in words:
            words.append(part)
    return words[:3]


def index_add(rel_path: str, category: str, caption: str, tags: list[str], sig: tuple[int, int, int] | None = None) -> None:
    entries = load_index()
    existing = next((e for e in entries if e.get("file") == rel_path), None)
    if existing is not None:
        merged = list(existing.get("tags") or [])
        for tag in tags:
            tag = str(tag).strip()
            if tag and tag not in merged:
                merged.append(tag)
        existing["tags"] = merged
        if caption and not existing.get("caption"):
            existing["caption"] = caption
        existing["category"] = category or existing.get("category", "")
        if sig:
            existing["w"], existing["h"], existing["sig"] = sig[0], sig[1], format(sig[2], "016x")
        save_index(entries)
        return
    entry = {"file": rel_path, "category": category, "caption": caption, "tags": tags, "ts": int(time.time())}
    if sig:
        entry["w"], entry["h"], entry["sig"] = sig[0], sig[1], format(sig[2], "016x")
    entries.append(entry)
    save_index(entries)


def pick_meme(category: str) -> str | None:
    folder = MEME_DIR / category.lower()
    if not folder.is_dir():
        return None
    files = [
        f for f in folder.iterdir()
        if f.is_file() and f.suffix.lower() in {".jpg", ".jpeg", ".png", ".gif", ".webp"}
        and f.stat().st_size <= 4 * 1024 * 1024 and is_sticker_path(f)
    ]
    if not files:
        return None
    user_files = [f for f in files if f.name.startswith("u_")]
    if user_files and random.random() < 0.6:
        return str(random.choice(user_files))
    return str(random.choice(files))


def find_by_keyword(keyword: str) -> str | None:
    keyword = keyword.strip().lower()
    if not keyword:
        return None
    for entry in reversed(load_index()):
        if not is_sticker_rel(str(entry.get("file") or "")):
            continue
        haystack = (entry.get("caption") or "") + " " + " ".join(entry.get("tags") or []) + " " + (entry.get("file") or "")
        if keyword in haystack.lower():
            path = MEME_DIR / entry["file"]
            if path.is_file():
                return str(path)
    return None


def resolve_meme(token: str) -> str | None:
    token = token.strip()
    lower = token.lower()
    if lower in STICKER_CATEGORIES:
        return pick_meme(lower)
    if token in CATEGORY_CN:
        return pick_meme(CATEGORY_CN[token])
    for word, category in CATEGORY_CN.items():
        if word in token:
            return pick_meme(category)
    return find_by_keyword(token)


def index_keywords(limit: int = 16) -> list[str]:
    words: list[str] = []
    for entry in load_index():
        if not is_sticker_rel(str(entry.get("file") or "")):
            continue
        for word in entry.get("tags") or []:
            word = str(word).strip()
            if len(word) >= 2 and word not in words:
                words.append(word)
    return words[:limit]


def find_index_hit(text: str) -> tuple[str, str] | None:
    text = text or ""
    for entry in reversed(load_index()):
        if not is_sticker_rel(str(entry.get("file") or "")):
            continue
        for word in (entry.get("tags") or []):
            word = str(word).strip()
            if len(word) >= 2 and word in text:
                path = MEME_DIR / entry["file"]
                if path.is_file():
                    return word, str(path)
        for token in re.findall(r"[\u4e00-\u9fa5A-Za-z]{2,8}", entry.get("caption") or ""):
            if token in text:
                path = MEME_DIR / entry["file"]
                if path.is_file():
                    return token, str(path)
    return None


def category_from_text(text: str) -> str | None:
    for word, category in CATEGORY_CN.items():
        if word in (text or ""):
            return category
    return None


def should_hint(text: str) -> bool:
    """只有聊到表情/图片时才附检索提示，平时不塞系统话。"""
    text = text or ""
    if any(word in text for word in ("表情", "图片", "照片", "贴纸", "动图", "gif", "meme")):
        return True
    markers = ("发", "来", "找", "看", "那张", "刚才", "刚刚", "你的")
    if any(marker in text for marker in markers):
        return find_index_hit(text) is not None
    return False


def history_hint() -> str:
    words = index_keywords()
    if not words:
        return ""
    return "（表情库检索提示：可用的关键词有 " + "、".join(words) + "；想发某张表情就在回复末尾写 [[meme:关键词]]，系统会按描述去找。）"
