"""一次性迁移：把旧的 L3 日流水账拆成事件线程。

旧 L3 的 source_ids 指向 L1，L1 的 source_ids 指向 L0。
只用已有数据，不重新跑 L1。
"""
from __future__ import annotations

import json
import os
import sys
import time

SERVICE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "service")
sys.path.insert(0, SERVICE)

import memory_core as mc  # noqa: E402
from extractor import Extractor, ExtractConfig, _tier_of_refs  # noqa: E402
from llm import LLM  # noqa: E402

DB = os.environ.get("CMEM_DB", r"C:\Users\12152\.dsh-qqbot\remembers-data\memories.db")
KEY = open(r"D:\QQBot\secret\deepseek.key", encoding="utf-8").read().strip()


def ref_rows_for_legacy(store, old_source_ids):
    l1_rows, l0_rows = [], []
    seen_l0 = set()
    for sid in old_source_ids:
        row = store.conn.execute("SELECT id,tier,text,source_ids FROM memory WHERE id=?", (int(sid),)).fetchone()
        if row is None:
            continue
        tier = str(row["tier"]).upper()
        if tier == "L1":
            l1_rows.append({"id": int(row["id"]), "tier": "L1", "text": str(row["text"])})
            try:
                l0_ids = [int(x) for x in json.loads(row["source_ids"] or "[]")]
            except Exception:  # noqa: BLE001
                l0_ids = []
            for lid in l0_ids:
                if lid in seen_l0:
                    continue
                seen_l0.add(lid)
                r0 = store.conn.execute("SELECT id,text FROM memory WHERE id=? AND tier='L0'", (lid,)).fetchone()
                if r0 is not None:
                    l0_rows.append({"id": int(r0["id"]), "tier": "L0", "text": str(r0["text"])})
        elif tier == "L0":
            if int(row["id"]) not in seen_l0:
                seen_l0.add(int(row["id"]))
                l0_rows.append({"id": int(row["id"]), "tier": "L0", "text": str(row["text"])})
    return l1_rows + l0_rows


def main():
    store = mc.MemoryStore(DB)
    llm = LLM("https://api.deepseek.com", KEY, "deepseek-chat")
    ex = Extractor(llm, store, ExtractConfig(enabled=True))
    legacy = store.conn.execute(
        "SELECT id,text,source_ids,ts FROM memory WHERE tier='L3' AND thread_status='legacy' ORDER BY id"
    ).fetchall()
    mig_open = []
    created = updated = archived = 0
    for old in legacy:
        old_id = int(old["id"])
        old_ts = float(old["ts"] or time.time())
        try:
            old_sources = [int(x) for x in json.loads(old["source_ids"] or "[]")]
        except Exception:  # noqa: BLE001
            old_sources = []
        rows = ref_rows_for_legacy(store, old_sources)
        plan = ex.plan_threads(str(old["text"]), [], mig_open, source_rows=rows) if rows else None
        if isinstance(plan, dict):
            updates = plan.get("updates") if isinstance(plan.get("updates"), list) else []
            for item in updates[:8]:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or "").strip()
                target = store.resolve_thread(title, mig_open)
                if target is None:
                    continue
                summary = str(item.get("summary") or "").strip()[:2000]
                status = str(item.get("status") or "open").lower()
                if status not in ("open", "closed"):
                    status = "open"
                pairs = _tier_of_refs(item.get("source_refs"), rows)
                l0 = [rid for tier, rid in pairs if tier == "L0"]
                if not summary:
                    continue
                store.update_thread(int(target["id"]), summary, status, source_ids=l0, last_seen_at=old_ts)
                for tier, rid in pairs or [("L0", x) for x in l0]:
                    store.link(int(target["id"]), rid, "derived_from", {"L0": "evidence", "L1": "fact", "L2": "judgment"}.get(tier, "evidence"))
                target["summary"] = summary
                target["status"] = status
                target["last_seen_at"] = old_ts
                updated += 1

            news = plan.get("new") if isinstance(plan.get("new"), list) else []
            for item in news[:3]:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or "").strip()[:120]
                summary = str(item.get("summary") or "").strip()[:2000]
                if not title or not summary:
                    continue
                status = str(item.get("status") or "open").lower()
                if status not in ("open", "closed", "standalone"):
                    status = "open"
                pairs = _tier_of_refs(item.get("source_refs"), rows)
                l0 = [rid for tier, rid in pairs if tier == "L0"]
                if not pairs:
                    l0, _ = __import__("evidence_match").match_evidence(item.get("evidence") or [], rows)
                    pairs = [("L0", x) for x in l0]
                mid = store.add(mc.MemoryInput(
                    text=summary, tier="L3", subject="self", summary=summary,
                    tags=["thread", "legacy-reorg"], source_ids=l0 or None,
                    source_status="verified" if l0 else "unverified",
                    thread_status=status, thread_title=title, thread_aliases=[],
                    thread_opened_at=old_ts, thread_last_seen_at=old_ts,
                    thread_closed_at=old_ts if status == "closed" else None,
                    ts=old_ts,
                ))
                store.link(mid, old_id, "derived_from", "legacy")
                for tier, rid in pairs:
                    store.link(mid, rid, "derived_from", {"L0": "evidence", "L1": "fact", "L2": "judgment"}.get(tier, "evidence"))
                mig_open.append({
                    "id": mid, "title": title, "status": status, "summary": summary,
                    "aliases": [], "last_seen_at": old_ts,
                })
                created += 1

        first = str(old["text"] or "").splitlines()[0][:40]
        store.conn.execute(
            "UPDATE memory SET thread_status='archived', thread_title=? WHERE id=?",
            (("旧流水账 · " + first)[:120], old_id),
        )
        store.conn.commit()
        archived += 1
        print(f"old={old_id} created={created} updated={updated} archived={archived}", flush=True)

    print(json.dumps({"created": created, "updated": updated, "archived": archived}, ensure_ascii=False))


if __name__ == "__main__":
    main()
