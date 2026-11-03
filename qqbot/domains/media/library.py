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


def index_add(rel_path: str, category: str, caption: str, tags: list[str], sig: tuple[int, int, int] | None = None,
              name: str = "", aliases: list[str] | None = None) -> None:
    entries = load_index()
    existing = next((e for e in entries if e.get("file") == rel_path), None)
    clean_name = str(name or "").strip()
    clean_aliases = [str(a).strip() for a in (aliases or []) if str(a).strip()]
    if existing is not None:
        merged = list(existing.get("tags") or [])
        for tag in tags:
            tag = str(tag).strip()
            if tag and tag not in merged:
                merged.append(tag)
        existing["tags"] = merged
        if caption and not existing.get("caption"):
            existing["caption"] = caption
        if existing.get("caption") and not existing.get("name"):
            existing["name"] = str(existing["caption"])[:20]
        existing["category"] = category or existing.get("category", "")
        if clean_name and not existing.get("name"):
            existing["name"] = clean_name
        if clean_aliases:
            old_aliases = list(existing.get("aliases") or [])
            existing["aliases"] = list(dict.fromkeys(old_aliases + clean_aliases))
        if sig:
            existing["w"], existing["h"], existing["sig"] = sig[0], sig[1], format(sig[2], "016x")
        save_index(entries)
        return
    entry = {"file": rel_path, "category": category, "caption": caption, "tags": tags, "ts": int(time.time())}
    if clean_name or caption:
        entry["name"] = clean_name or caption[:20]
    if clean_aliases:
        entry["aliases"] = clean_aliases
    if sig:
        entry["w"], entry["h"], entry["sig"] = sig[0], sig[1], format(sig[2], "016x")
    entries.append(entry)
    save_index(entries)


def _entry_text(entry: dict) -> tuple[str, str, list[str]]:
    name = str(entry.get("name") or "").strip()
    caption = str(entry.get("caption") or "").strip()
    aliases = [str(a).strip() for a in (entry.get("aliases") or []) if str(a).strip()]
    return name, caption, aliases


def _habit_score(entry: dict) -> float:
    """用得多、最近用得多的更符合人的习惯。"""
    try:
        usage = max(0, int(entry.get("usage_count") or 0))
    except (TypeError, ValueError):
        usage = 0
    score = min(20, usage) * 1.5
    try:
        last = float(entry.get("last_used_at") or 0)
        if last:
            age = max(0.0, time.time() - last)
            if age < 300:
                score += 12
            elif age < 3600:
                score += 8
            elif age < 86400:
                score += 4
    except (TypeError, ValueError):
        pass
    return score


def _score_entry(entry: dict, query: str, category: str | None = None) -> float | None:
    """本地语义匹配：别名/名称/标签/描述，类别只作为过滤和兜底。"""
    q = str(query or "").strip().lower()
    if category and str(entry.get("category") or "").lower() != category.lower():
        return None
    name, caption, aliases = _entry_text(entry)
    tags = [str(t).strip().lower() for t in (entry.get("tags") or []) if str(t).strip()]
    file = str(entry.get("file") or "").lower()
    if not q:
        return _habit_score(entry)
    score = 0.0
    if q == file or q == name.lower() or q in {a.lower() for a in aliases}:
        score += 200
    elif q in name.lower() or any(q in a.lower() for a in aliases):
        score += 80
    for tag in tags:
        if q == tag:
            score += 60
        elif q in tag or tag in q:
            score += 22
    if q in caption.lower():
        score += 25
    if q in file:
        score += 8
    if score <= 0:
        return None
    # 语义命中之后，再按“平时爱用、最近爱用”加分
    score += _habit_score(entry) * 0.5
    return score


def _best_match(query: str, category: str | None = None) -> tuple[float, dict] | None:
    if not STICKER_META:
        load_sticker_meta()
    best: tuple[float, dict] | None = None
    for entry in load_index():
        if not is_sticker_rel(str(entry.get("file") or "")):
            continue
        path = MEME_DIR / str(entry.get("file") or "")
        if not path.is_file():
            continue
        score = _score_entry(entry, query, category)
        if score is None:
            continue
        if best is None or score > best[0]:
            best = (score, entry)
    return best


def mark_sticker_used(rel_path: str) -> None:
    key = str(rel_path or "").replace("\\", "/")
    entries = load_index()
    changed = False
    for entry in entries:
        if str(entry.get("file") or "").replace("\\", "/") != key:
            continue
        entry["usage_count"] = int(entry.get("usage_count") or 0) + 1
        entry["last_used_at"] = time.time()
        changed = True
        break
    if changed:
        save_index(entries)


def pick_meme(category: str, query: str = "") -> str | None:
    category = str(category or "").strip().lower()
    if not category:
        return None
    if not STICKER_META:
        load_sticker_meta()
    candidates: list[tuple[float, dict]] = []
    for entry in load_index():
        if str(entry.get("category") or "").lower() != category:
            continue
        if not is_sticker_rel(str(entry.get("file") or "")):
            continue
        path = MEME_DIR / str(entry.get("file") or "")
        if not path.is_file():
            continue
        score = _score_entry(entry, query, category) if query else 1.0
        if score is not None:
            candidates.append((score, entry))
    if candidates:
        if query:
            candidates.sort(key=lambda item: item[0], reverse=True)
            top = candidates[:min(5, len(candidates))]
            return str(MEME_DIR / str(random.choice(top)[1].get("file")))
        # 没给具体词时，优先平时最常发、最近发得多的
        candidates.sort(key=lambda item: _habit_score(item[1]), reverse=True)
        pool = candidates[:min(6, len(candidates))]
        return str(MEME_DIR / str(random.choice(pool)[1].get("file")))
    # 索引缺失时回退到目录扫描，兼容旧数据；只有泛类别才允许随便挑
    if query:
        return None
    folder = MEME_DIR / category
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
    keyword = keyword.strip()
    if not keyword:
        return None
    best = _best_match(keyword)
    if best is None:
        return None
    return str(MEME_DIR / str(best[1].get("file") or ""))


def resolve_meme(token: str) -> str | None:
    token = token.strip()
    if not token:
        return None
    category: str | None = None
    query = token
    for sep in (":", "："):
        if sep not in token:
            continue
        left, right = token.split(sep, 1)
        left = left.strip().lower()
        right = right.strip()
        if left in STICKER_CATEGORIES:
            category, query = left, right
        elif left in CATEGORY_CN:
            category, query = CATEGORY_CN[left], right
        if category:
            break
    if category and not query:
        return pick_meme(category)
    if not category:
        lower = token.lower()
        if lower in STICKER_CATEGORIES:
            return pick_meme(lower)
        if token in CATEGORY_CN:
            return pick_meme(CATEGORY_CN[token])
    # 先按名称/别名/标签/描述找具体图，类别只做过滤和兜底
    best = _best_match(query, category)
    if best is not None:
        return str(MEME_DIR / str(best[1].get("file") or ""))
    if category:
        return pick_meme(category, query)
    for word, fallback in CATEGORY_CN.items():
        if word in token:
            return pick_meme(fallback, token)
    return None


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
