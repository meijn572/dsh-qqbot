"""Phase 0 备份：代码、配置、插件、记忆库。

用法：
    python scripts/backup_state.py
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import time
from pathlib import Path

BOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT))
from settings import CONFIG, DSH_HOME  # noqa: E402

SERVICE = Path(r"C:\Users\12152\.dsh-qqbot\remembers-service")
PLUGIN = DSH_HOME / "plugins" / "dsh-remembers"
DB = DSH_HOME / "remembers-data" / "memories.db"


def copy_file(src: Path, dst: Path) -> None:
    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def main() -> int:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = BOT / "backups" / f"refactor-phase0-{stamp}"
    target.mkdir(parents=True, exist_ok=True)

    files = [
        (BOT / "config.json", target / "dshbot" / "config.json"),
        (BOT / "bridge.py", target / "dshbot" / "bridge.py"),
        (BOT / "panel.py", target / "dshbot" / "panel.py"),
        (BOT / "settings.py", target / "dshbot" / "settings.py"),
        (SERVICE / "server.py", target / "service" / "server.py"),
        (SERVICE / "extractor.py", target / "service" / "extractor.py"),
        (SERVICE / "memory_core.py", target / "service" / "memory_core.py"),
        (PLUGIN / "index.mjs", target / "plugin" / "index.mjs"),
        (PLUGIN / "client.mjs", target / "plugin" / "client.mjs"),
    ]
    for src, dst in files:
        copy_file(src, dst)

    if DB.exists():
        dst = target / "data" / "memories.db"
        dst.parent.mkdir(parents=True, exist_ok=True)
        src = sqlite3.connect(DB)
        out = sqlite3.connect(dst)
        src.backup(out)
        out.close()
        src.close()

    manifest = {
        "created_at": int(time.time()),
        "dsh_home": str(DSH_HOME),
        "files": [str(dst.relative_to(target)) for _, dst in files],
        "db": str(DB),
    }
    (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
