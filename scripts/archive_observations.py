"""把当天可观察的原始数据导出到本地归档。

不进入 git；只写 data/raw/YYYY-MM-DD/。
用法：python scripts/archive_observations.py [--date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from settings import CMEM_BASE, DSH_HOME  # noqa: E402

DB = DSH_HOME / "remembers-data" / "memories.db"
OUT_ROOT = ROOT / "data" / "raw"


def _json(value, default):
    try:
        return json.loads(value) if value else default
    except Exception:  # noqa: BLE001
        return default


def _persona() -> dict:
    try:
        with urllib.request.urlopen(CMEM_BASE + "/persona", timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, timeout=10
        ).strip()
    except Exception:  # noqa: BLE001
        return ""


def export(day: str) -> Path:
    out = OUT_ROOT / day
    out.mkdir(parents=True, exist_ok=True)
    counts = {}
    if DB.exists():
        con = sqlite3.connect(DB)
        con.row_factory = sqlite3.Row
        tiers = [str(row[0]) for row in con.execute(
            "SELECT DISTINCT tier FROM memory ORDER BY tier"
        )]
        for tier in tiers:
            rows = con.execute(
                "SELECT id,tier,subject,text,summary,source_ids,tags,ts,half_life_days,user_id,scope "
                "FROM memory WHERE tier=? ORDER BY id",
                (tier,),
            ).fetchall()
            with (out / f"{tier.lower()}.jsonl").open("w", encoding="utf-8") as handle:
                for row in rows:
                    item = dict(row)
                    item["source_ids"] = _json(item.get("source_ids"), [])
                    item["tags"] = _json(item.get("tags"), [])
                    handle.write(json.dumps(item, ensure_ascii=False) + "\n")
            counts[tier] = len(rows)
        con.close()
    persona = _persona()
    (out / "persona.json").write_text(
        json.dumps(persona, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    proposals = DSH_HOME / "persona-roles" / "state" / "review-proposals.json"
    if proposals.exists():
        (out / "review-proposals.json").write_text(
            proposals.read_text(encoding="utf-8"), encoding="utf-8"
        )
    manifest = {
        "date": day,
        "exported_at": int(time.time()),
        "git_head": _git_head(),
        "counts": counts,
        "persona_chars": {
            "constitution": len(str(persona.get("constitution") or "")),
            "self_model": len(str(persona.get("self_model") or "")),
            "user_profile": len(str(persona.get("user_profile") or "")),
        },
        "files": ["persona.json", "review-proposals.json"] + [
            f"{tier.lower()}.jsonl" for tier in counts
        ],
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=time.strftime("%Y-%m-%d"))
    args = parser.parse_args()
    out = export(args.date)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
