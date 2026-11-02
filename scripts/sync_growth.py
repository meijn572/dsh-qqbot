"""把角色卡（唯一人格源）同步进 AGENTS.md 的 persona 区块（本鱼每轮都能读到）。"""

import re
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from settings import DSH_HOME, WORKSPACE

CARD = DSH_HOME / "persona-roles" / "roles" / "小肥鱼.md"
AGENTS = WORKSPACE / "AGENTS.md"

BEGIN = "<!-- persona:begin -->"
END = "<!-- persona:end -->"


def card_body() -> str:
    text = CARD.read_text(encoding="utf-8").strip()
    # AGENTS 自己有一级标题，这里去掉角色卡的一级标题，避免重复
    text = re.sub(r"^#\s+.*?\n+", "", text, count=1)
    return text.strip()


def main() -> None:
    body = card_body()
    block = f"{BEGIN}\n{body}\n{END}"
    base = AGENTS.read_text(encoding="utf-8")
    if BEGIN in base and END in base:
        new = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END), lambda _: block, base, count=1, flags=re.S)
    else:
        # 没有标记时插在一级标题之后
        match = re.match(r"(#\s+.*?\n)", base)
        if match:
            new = base[: match.end()] + "\n" + block + "\n" + base[match.end() :]
        else:
            new = block + "\n\n" + base
    AGENTS.write_text(new, encoding="utf-8")
    print("role card chars:", len(body), "-> AGENTS.md", len(new))


if __name__ == "__main__":
    main()
