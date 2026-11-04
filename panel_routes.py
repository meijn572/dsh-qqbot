"""面板 API 路由：只做请求解析和响应。"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from panel_readers import (
    BILI,
    BOT,
    HOME,
    STICKERS,
    apply_style,
    bili_feed_payload,
    bili_payload,
    dismiss_style,
    groupslang_payload,
    guests_payload,
    health,
    interests_payload,
    lexicon_add,
    lexicon_delete,
    lexicon_payload,
    lexicon_lookup_payload,
    lexicon_search_payload,
    memory_payload,
    mood_payload,
    notebook_payload,
    persona_payload,
    proactive_payload,
    qr_status,
    save_core_setting,
    save_persona_field,
    set_proactive,
    status_payload,
    sticker_payload,
    sticker_lookup_payload,
    sticker_delete,
    sticker_update_semantics,
    style_payload,
    tail,
)
from settings import CONFIG, LOGIN_OUT, QR_FILE, SCRIPTS_DIR


def _body(handler) -> dict:
    try:
        length = int(handler.headers.get("Content-Length") or 0)
        return json.loads(handler.rfile.read(length).decode("utf-8") or "{}")
    except Exception:  # noqa: BLE001
        return {}


def handle_get(handler, path: str, parsed) -> None:
    query = parse_qs(parsed.query)
    if path == "/api/status":
        handler._json(status_payload())
    elif path == "/api/mood":
        handler._json(mood_payload())
    elif path == "/api/memory":
        handler._json(memory_payload())
    elif path == "/api/proactive":
        handler._json(proactive_payload())
    elif path == "/api/style":
        handler._json(style_payload())
    elif path == "/api/persona":
        handler._json(persona_payload())
    elif path == "/api/guests":
        handler._json(guests_payload())
    elif path == "/api/notebook":
        handler._json(notebook_payload())
    elif path == "/api/interests":
        handler._json(interests_payload())
    elif path == "/api/groupslang":
        handler._json(groupslang_payload())
    elif path == "/api/lexicon":
        handler._json(lexicon_payload())
    elif path == "/api/lexicon/lookup":
        handler._json(lexicon_lookup_payload(
            (query.get("q") or [""])[0],
            (query.get("scope") or [""])[0],
            (query.get("kind") or [""])[0],
            (query.get("status") or [""])[0],
        ))
    elif path == "/api/lexicon/search":
        handler._json(lexicon_search_payload((query.get("q") or [""])[0]))
    elif path == "/api/stickers":
        handler._json(sticker_payload())
    elif path == "/api/stickers/lookup":
        ref = (query.get("ref") or [""])[0]
        handler._json(sticker_lookup_payload(ref))
    elif path == "/api/logs":
        name = (query.get("name") or ["bridge"])[0]
        files = {
            "bridge": BOT / "bridge.log",
            "bili": BILI / "duty.log",
            "dsh": Path(CONFIG.get("dsh_log_file") or (BOT.parent / "logs" / "qqbot-boot19.err")),
        }
        handler._json({"text": tail(files.get(name, BOT / "bridge.log"), 150)})
    elif path == "/api/bili":
        handler._json(bili_payload())
    elif path == "/api/bili/feed":
        handler._json(bili_feed_payload())
    elif path == "/api/bili/qr/status":
        handler._json(qr_status())
    elif path == "/api/bili/qr.png":
        handler._file(QR_FILE)
    elif path == "/api/sticker":
        rel = (query.get("file") or [""])[0]
        candidate = (STICKERS / rel).resolve()
        if STICKERS.resolve() in candidate.parents:
            handler._file(candidate)
        else:
            handler.send_error(403)
    else:
        handler.send_error(404)


def start_qr() -> dict:
    out_file = LOGIN_OUT
    vpy = HOME / "bili-duty" / ".venv" / "Scripts" / "python.exe"
    if not vpy.exists():
        return {"ok": False, "error": "找不到 bili-duty 的 venv"}
    subprocess.Popen(
        [str(vpy), str(SCRIPTS_DIR / "bili_login2.py")],
        cwd=str(BOT),
        stdout=open(out_file, "w", encoding="utf-8"),
        stderr=subprocess.DEVNULL,
        creationflags=0x08000000,
    )
    time.sleep(4)
    return {"ok": True, "status": qr_status()}


def restart_bridge() -> dict:
    pid = health().get("pid")
    if pid:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, timeout=15)
        time.sleep(2)
    py = CONFIG.get("bridge_python") or "python"
    subprocess.Popen(
        [str(py), str(BOT / "bridge.py")],
        cwd=str(BOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=0x08000000,
    )
    time.sleep(6)
    return {"ok": True, "status": health()}


def handle_post(handler, path: str, parsed) -> None:
    if path == "/api/bili/qr/start":
        handler._json(start_qr())
    elif path == "/api/proactive":
        handler._json(set_proactive(_body(handler)))
    elif path == "/api/style/apply":
        handler._json(apply_style())
    elif path == "/api/style/dismiss":
        handler._json(dismiss_style())
    elif path == "/api/persona/save":
        handler._json(save_core_setting(str(_body(handler).get("constitution") or "")))
    elif path == "/api/persona/field":
        body = _body(handler)
        handler._json(save_persona_field(
            str(body.get("field") or ""), str(body.get("text") or "")))
    elif path == "/api/stickers/semantics":
        body = _body(handler)
        handler._json(sticker_update_semantics(
            str(body.get("file") or ""),
            str(body.get("label") or ""),
            body.get("identity") or [],
            body.get("action") or [],
            body.get("expression") or [],
            body.get("generic") or [],
        ))
    elif path == "/api/stickers/delete":
        body = _body(handler)
        handler._json(sticker_delete(str(body.get("file") or "")))
    elif path in ("/api/lexicon/add", "/api/lexicon/delete"):
        body = _body(handler)
        if path.endswith("/add"):
            handler._json(lexicon_add(
                str(body.get("kind") or body.get("category") or "meme"),
                str(body.get("term") or ""),
                str(body.get("meaning") or ""),
                str(body.get("example") or ""),
                body.get("aliases") or "",
                str(body.get("status") or "stable"),
                str(body.get("scope") or ""),
            ))
        else:
            handler._json(lexicon_delete(
                str(body.get("id") or ""),
                str(body.get("category") or ""),
                str(body.get("term") or ""),
            ))
    elif path == "/api/bridge/restart":
        handler._json(restart_bridge())
    else:
        handler.send_error(404)
