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
SCENE_TAG_WORDS = (
    "我", "你", "他", "她", "它", "咱", "主人", "群友", "刚才", "刚刚", "今天", "昨天",
    "现在", "然后", "觉得", "知道", "可以", "就是", "这个", "那个", "什么", "怎么",
    "为什么", "是不是", "有没有", "已经", "还是", "但是", "因为", "所以", "如果",
    "时候", "东西", "事情", "视频", "直播", "聊天", "群里", "弹幕", "评论", "b站", "B站",
    "kpl", "KPL", "token", "表情包", "表情", "图片",
)


FACET_KEYS = ("identity", "action", "expression", "generic")
FACET_WEIGHTS = {"identity": 100, "action": 50, "expression": 40, "generic": 10}


def clean_facets(values: list[str] | str | None, limit: int = 12) -> list[str]:
    """清洗一个语义分面；不做跨分面猜测。"""
    if isinstance(values, str):
        values = re.split(r"[,，、\s]+", values)
    kept = []
    for raw in values or []:
        value = str(raw or "").strip()
        if not value or value in kept:
            continue
        if len(value) > 12 or len(value) < 1:
            continue
        if any(p in value for p in "，。！？、,!?;；:："):
            continue
        if any(w in value for w in SCENE_TAG_WORDS):
            continue
        kept.append(value)
        if len(kept) >= limit:
            break
    return kept


def clean_label(value: str) -> str:
    """label 只校验，不生成；空就是空。"""
    label = str(value or "").strip().replace("\n", " ")
    if not label or len(label) > 12 or "[[" in label or "]]" in label:
        return ""
    if any(p in label for p in "，。！？、,!?;；:："):
        return ""
    return label


def _entry_facets(entry: dict) -> dict[str, list[str]]:
    return {key: [str(v).strip() for v in (entry.get(key) or []) if str(v).strip()] for key in FACET_KEYS}


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
        "label": str(entry.get("label") or ""),
        "identity": list(entry.get("identity") or []),
        "action": list(entry.get("action") or []),
        "expression": list(entry.get("expression") or []),
        "generic": list(entry.get("generic") or []),
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


def index_add(rel_path: str, category: str, caption: str, *,
              identity: list[str] | str | None = None,
              action: list[str] | str | None = None,
              expression: list[str] | str | None = None,
              generic: list[str] | str | None = None,
              label: str = "",
              sig: tuple[int, int, int] | None = None,
              replace_facets: bool = False) -> None:
    rel_path = str(rel_path or "").replace("\\", "/")
    caption = str(caption or "").strip()[:80]
    entries = load_index()
    existing = next(
        (e for e in entries if str(e.get("file") or "").replace("\\", "/") == rel_path),
        None,
    )
    incoming = {
        "identity": clean_facets(identity),
        "action": clean_facets(action),
        "expression": clean_facets(expression),
        "generic": clean_facets(generic),
    }
    new_label = clean_label(label)
    if existing is not None:
        existing["file"] = rel_path
        for key in FACET_KEYS:
            values = incoming[key]
            if replace_facets:
                existing[key] = values
            else:
                old = [str(v).strip() for v in (existing.get(key) or []) if str(v).strip()]
                existing[key] = list(dict.fromkeys(old + values))[:24]
        if new_label:
            existing["label"] = new_label
        if caption and not existing.get("caption"):
            existing["caption"] = caption
        existing["category"] = category or existing.get("category", "")
        if sig:
            existing["w"], existing["h"], existing["sig"] = sig[0], sig[1], format(sig[2], "016x")
        save_index(entries)
        return
    entry = {"file": rel_path, "category": category, "caption": caption, "ts": int(time.time())}
    if new_label:
        entry["label"] = new_label
    for key in FACET_KEYS:
        if incoming[key]:
            entry[key] = incoming[key]
    if sig:
        entry["w"], entry["h"], entry["sig"] = sig[0], sig[1], format(sig[2], "016x")
    entries.append(entry)
    save_index(entries)


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
    """按 label 和 identity/action/expression/generic 分面加权匹配。"""
    q = str(query or "").strip().lower()
    if category and str(entry.get("category") or "").lower() != category.lower():
        return None
    if not q:
        return _habit_score(entry)
    caption = str(entry.get("caption") or "").lower()
    file = str(entry.get("file") or "").lower()
    score = 0.0
    for key, weight in FACET_WEIGHTS.items():
        values = [str(v).strip().lower() for v in (entry.get(key) or []) if str(v).strip()]
        if q in values:
            score += weight
        elif any(q in value or value in q for value in values):
            score += weight * 0.45
    if score <= 0:
        # caption/file 只在分面全空时兜底，不参与主排序
        if q in caption:
            score = 15
        elif q in file:
            score = 5
        else:
            return None
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
        score = _score_entry(entry, query, category) if query else _habit_score(entry)
        if score is not None:
            candidates.append((score, entry))
    if candidates:
        if query:
            candidates.sort(key=lambda item: item[0], reverse=True)
            pool = candidates[:min(5, len(candidates))]
        else:
            # 没给具体词时，优先平时最常发、最近发得多的
            candidates.sort(key=lambda item: _habit_score(item[1]), reverse=True)
            pool = candidates[:min(6, len(candidates))]
        weights = [max(0.1, score) for score, _ in pool]
        chosen = random.choices(pool, weights=weights, k=1)[0]
        return str(MEME_DIR / str(chosen[1].get("file")))
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
        candidates = []
        for key in FACET_KEYS:
            candidates.extend(str(v) for v in (entry.get(key) or []))
        for word in candidates:
            word = str(word).strip()
            if len(word) >= 2 and word not in words:
                words.append(word)
    return words[:limit]


def find_index_hit(text: str) -> tuple[str, str] | None:
    text = text or ""
    for entry in reversed(load_index()):
        if not is_sticker_rel(str(entry.get("file") or "")):
            continue
        candidates = []
        for key in FACET_KEYS:
            candidates.extend(str(v) for v in (entry.get(key) or []))
        for word in candidates:
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
