"""qqbot 进程入口。

当前阶段只建立骨架，不替换 bridge.py。
"""
from __future__ import annotations

import sys


def main() -> int:
    print("qqbot runtime 尚未接线；当前仍使用 bridge.py", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
