"""任务执行器：读素材 → 调模型（带会话）→ 落库。

和 /input/<recipe> 的区别：
    /input  只给素材，不调模型，无副作用
    /task   调模型、写库、维护会话，有副作用
"""
from __future__ import annotations

import time

from session import TaskSession


def run_profile(store, llm, embedder, body: dict) -> dict:
    """画像刷新：读最近素材，重写「我眼中的主人」。"""
    import inputs

    data = inputs.run(store, "profile", body, embedder)
    blocks = data.get("blocks") or {}
    if not blocks.get("evidence"):
        return {"ok": False, "error": "no-material", "task": "profile"}

    system = _profile_system()
    user = _profile_user(blocks)

    sess = TaskSession(store, "profile")
    result = sess.turn(llm, system, user, max_tokens=1200, json_mode=True)
    if not result.get("ok"):
        return {"ok": False, "error": result.get("error"), "task": "profile",
                "usage": result.get("usage")}

    payload = result.get("data") or {}
    sections = payload.get("sections") if isinstance(payload, dict) else None
    if not isinstance(sections, dict):
        return {"ok": False, "error": "bad-json", "task": "profile",
                "usage": result.get("usage"), "raw": str(result.get("text"))[:300]}
    if not sections:
        # 模型认为没变化。不是错误，但也不该落库。
        return {"ok": True, "task": "profile", "changed": False,
                "reason": "no-change", "usage": result.get("usage"),
                "turns": sess.turns(), "rotated": result.get("rotated")}

    if body.get("dry_run"):
        return {"ok": True, "task": "profile", "dry_run": True,
                "sections": sections, "usage": result.get("usage"),
                "turns": sess.turns(), "rotated": result.get("rotated")}

    new_text = _render_profile(sections)
    old_text = str(store.get_user_profile() or "").strip()
    if not new_text or new_text == old_text:
        return {"ok": True, "task": "profile", "changed": False,
                "reason": "same-as-before", "usage": result.get("usage"),
                "turns": sess.turns(), "rotated": result.get("rotated")}

    applied = _apply_profile(store, sections)
    return {"ok": True, "task": "profile", "changed": applied,
            "usage": result.get("usage"), "turns": sess.turns(),
            "rotated": result.get("rotated"), "sections": list(sections)}


def _profile_system() -> str:
    """画像刷新的 system。内容必须稳定，变了缓存全失效。"""
    return (
        "你在更新「我眼中的主人」这份画像。\n\n"
        "输入是最近几天的记录和以前的画像。输出四组：\n"
        "stable_facts  他是谁（身份、专业、作息这类不太变的）\n"
        "appearance    他日常什么样子（说话习惯、做事方式）\n"
        "preferences   他喜欢什么、不喜欢什么\n"
        "values        他信什么、看重什么\n\n"
        "只写这次真的看出新东西的组，没变化的组不要重写。\n"
        "每组 3-8 条，每条一句话，具体。\n"
        "不要写推测，不要写你自己的事。\n\n"
        '只返回 JSON：{"sections":{"stable_facts":["..."],"appearance":["..."],'
        '"preferences":["..."],"values":["..."]}}'
    )


PROFILE_TAIL = (
    "\n\n---\n"
    "现在输出这一次的完整四组。"
    "即使和上次完全一样也要照抄一遍，不要返回空对象。"
)


def _profile_user(blocks: dict) -> str:
    parts = []
    if blocks.get("persona"):
        parts.append("【现在的你（人格）】\n" + str(blocks["persona"])[:2000])
    if blocks.get("profile"):
        parts.append("【现在的画像】\n" + str(blocks["profile"])[:2000])
    if blocks.get("evidence"):
        parts.append("【最近的记录】\n" + str(blocks["evidence"])[:12000])
    if blocks.get("recent"):
        parts.append("【最近的原话】\n" + str(blocks["recent"])[:4000])
    return "\n\n".join(parts) + PROFILE_TAIL


def _render_profile(sections: dict) -> str:
    titles = {
        "stable_facts": "他是谁",
        "appearance": "他平时什么样子",
        "preferences": "他的偏好",
        "values": "他看重什么",
    }
    lines = []
    for key, title in titles.items():
        items = sections.get(key)
        if not isinstance(items, list):
            continue
        clean = [str(x).strip() for x in items if str(x).strip()][:10]
        if not clean:
            continue
        lines.append(f"**{title}**")
        lines.extend(f"- {x}" for x in clean)
        lines.append("")
    return "\n".join(lines).strip()


def _apply_profile(store, sections: dict) -> bool:
    """把四组写回 user_profile。格式跟面板一致：**标题** + 列表。"""
    titles = {
        "stable_facts": "他是谁",
        "appearance": "他平时什么样子",
        "preferences": "他的偏好",
        "values": "他看重什么",
    }
    lines = []
    for key, title in titles.items():
        items = sections.get(key)
        if not isinstance(items, list):
            continue
        clean = [str(x).strip() for x in items if str(x).strip()][:10]
        if not clean:
            continue
        lines.append(f"**{title}**")
        lines.extend(f"- {x}" for x in clean)
        lines.append("")
    text = "\n".join(lines).strip()
    if not text:
        return False
    try:
        store.set_user_profile(text)
        return True
    except Exception:  # noqa: BLE001
        return False


TASKS = {
    "profile": run_profile,
}


def run(store, llm, embedder, name: str, body: dict) -> dict:
    fn = TASKS.get(str(name or "").strip().lower())
    if fn is None:
        return {"ok": False, "error": f"unknown task: {name}",
                "available": sorted(TASKS)}
    if llm is None or not getattr(llm, "enabled", False):
        return {"ok": False, "error": "llm-disabled", "task": name}
    started = time.time()
    out = fn(store, llm, embedder, body or {})
    out.setdefault("task", name)
    out["elapsed"] = round(time.time() - started, 2)
    return out
