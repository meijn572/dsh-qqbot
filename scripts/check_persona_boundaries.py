"""检查人格分层有没有串味。

只读，不改数据。输出 warning 列表；有 warning 时退出码 1。
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from settings import AGENTS, CMEM_BASE

CORE_HEADINGS = ("## 我是谁", "## 表现", "## 偏好", "## 价值取向", "## 弱点", "## 我们怎么对彼此", "## 我们之间有什么")
CORE_FORBIDDEN = re.compile(r"(回答时|默认|你必须|工具名|主人喜欢|主人是|消息条数|\[\[meme)")
AGENTS_FORBIDDEN = re.compile(r"(傲娇|口癖|不确定先查|来源|人格|情绪记录)")
SELF_FORBIDDEN = re.compile(r"(回答时|默认|必须|不要|每次|主人喜欢|主人是)")
PROFILE_FORBIDDEN = re.compile(r"(回答时|默认|你应该|你应当|口癖|人格设定)")


def persona() -> dict:
    with urllib.request.urlopen(CMEM_BASE + "/persona", timeout=10) as resp:
        return json.loads(resp.read())


def warnings() -> list[str]:
    data = persona()
    out: list[str] = []
    core = str(data.get("constitution") or "")
    self_model = str(data.get("self_model") or "")
    profile = str(data.get("user_profile") or "")

    for heading in CORE_HEADINGS:
        if heading not in core:
            out.append(f"core: 缺少 {heading}")
    if "<!-- important:begin -->" not in core or "<!-- important:end -->" not in core:
        out.append("core: important 块不完整")
    for match in CORE_FORBIDDEN.finditer(core):
        out.append(f"core: 出现越界内容 {match.group(0)!r}")
    for match in SELF_FORBIDDEN.finditer(self_model):
        out.append(f"self_model: 出现规则/事实 {match.group(0)!r}")
    for match in PROFILE_FORBIDDEN.finditer(profile):
        out.append(f"profile: 出现指令/人格 {match.group(0)!r}")

    if AGENTS.exists():
        text = AGENTS.read_text(encoding="utf-8")
        for match in AGENTS_FORBIDDEN.finditer(text):
            out.append(f"AGENTS: 出现人格/行为政策 {match.group(0)!r}")
    else:
        out.append("AGENTS: 文件不存在")
    return out


def main() -> int:
    items = warnings()
    if not items:
        print("persona boundaries OK")
        return 0
    for item in items:
        print("[WARN]", item)
    return 1


if __name__ == "__main__":
    sys.exit(main())
