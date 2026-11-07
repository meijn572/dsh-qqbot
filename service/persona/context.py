"""人格块格式。"""
from __future__ import annotations


def build_persona_context(persona: dict) -> dict:
    parts = [
        ("核心设定", str(persona.get("constitution") or "")),
        ("自我认知", str(persona.get("self_model") or "")),
        ("我眼中的主人", str(persona.get("user_profile") or "")),
    ]
    text = "\n\n".join(f"【{name}】\n{content}" for name, content in parts if content.strip())
    return {"ok": True, "text": text}
