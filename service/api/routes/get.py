"""GET 路由逻辑：只做协议适配，返回是否已处理。"""
from __future__ import annotations


def handle_get(handler, path: str, query: dict, store) -> bool:
        if path.startswith("/memes/file/"):
            import urllib.parse as _up
            name = _up.unquote(path.rsplit("/", 1)[-1])
            import os as _os
            meme_dir = _os.environ.get("CMEM_MEME_DIR", "/home/ubuntu/.dsh/media/onebot/memes")
            fp = _os.path.join(meme_dir, _os.path.basename(name))
            if not _os.path.exists(fp):
                handler._json(404, {"ok": False, "error": "not found"})
                return True
            ext = _os.path.splitext(fp)[1].lstrip(".").lower()
            ctype = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                     "webp": "image/webp", "gif": "image/gif"}.get(ext, "application/octet-stream")
            with open(fp, "rb") as f:
                data = f.read()
            handler._responded = True
            handler.send_response(200)
            handler.send_header("Content-Type", ctype)
            handler.send_header("Content-Length", str(len(data)))
            handler.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            handler.end_headers()
            handler.wfile.write(data)
        elif path == "/bili/qr":
            handler._json(200, handler._bili_qr())
        elif path == "/bili/qr/poll":
            key = (query.get("key") or [""])[0]
            handler._json(200, handler._bili_qr_poll(key))
        elif path == "/bili/tools":
            handler._json(200, handler._bili_tools())
        elif path == "/public/status":
            # 这条原来是 _public_status()，但那个函数从来没定义过（NameError 必崩），
            # 而且前端没有任何调用方。2026-10-27 直接摘掉，别留一个必然报错的接口。
            handler._json(404, {"ok": False, "error": "not found"})
        elif path == "/bili/cfg":
            handler._json(200, handler._load_bili_whale())
        elif path == "/bili/status":
            handler._json(200, handler._bili_status())
        elif path == "/bili/feed":
            handler._json(200, handler._bili_feed((query.get("thought") or [""])[0]))
        elif path == "/bili/debrief":
            bv = (query.get("bv") or [""])[0]
            handler._json(200, handler._bili_debrief(bv))
        elif path == "/proactive":
            handler._json(200, handler._get_proactive())
        elif path == "/profiles":
            # 标出哪个人是「主人」——主人画像走 persona.user_profile，不走 profiles
            admins = handler._qq_admin_users()
            rows = store.profile_list()
            for r in rows:
                r["is_owner"] = str(r.get("user_id") or "") in admins
            handler._json(200, {"ok": True, "profiles": rows, "admins": sorted(admins)})
        elif path == "/memes/seen":
            handler._json(200, store.seen_liked())
        elif path == "/memes/packs":
            handler._json(200, store.meme_pack_stats())
        elif path == "/memes":
            emotion = (query.get("emotion") or [""])[0]
            q = (query.get("q") or [""])[0]
            pack = (query.get("pack") or [""])[0]
            try:
                limit = int((query.get("limit") or ["20"])[0])
            except Exception:
                limit = 20
            handler._json(200, store.meme_list(emotion, q, limit, pack))
        elif path == "/slang":
            handler._json(200, store.slang_list())
        elif path == "/affinity":
            uid = (query.get("user") or [""])[0]
            handler._json(200, {"user": uid, "score": store.affinity_get(uid) if uid else 0})
        elif path == "/threads/open":
            items = store.open_threads(8)
            handler._json(200, {"ok": True, "items": [
                {"title": x["title"], "status": x["status"],
                 "summary": x["summary"], "last_seen_at": x["last_seen_at"]}
                for x in items
            ]})
        elif path == "/threads/get":
            q = (query.get("q") or [""])[0].strip()
            items = store.find_threads(q, limit=8)
            handler._json(200, {"ok": True, "items": items})
        elif path == "/profile":
            subject = (query.get("subject") or [None])[0]
            handler._guard(lambda: handler._json(200, {
                "ok": True,
                "items": [h.to_dict() for h in store.profile(subject)],
            }))
        elif path == "/log":
            limit = int((query.get("limit") or ["50"])[0])
            handler._guard(lambda: handler._json(200, {"ok": True, "items": handler._recent_log(limit)}))
        elif path == "/qq/session-history":
            handler._guard(lambda: handler._get_qq_session_history())
        elif path == "/qq/chat-map":
            handler._guard(lambda: handler._get_qq_chat_map())
        elif path == "/qq/sessions":
            handler._guard(lambda: handler._get_qq_sessions())
        elif path == "/fs/list":
            handler._guard(lambda: handler._get_fs_list())
        elif path == "/qq/config":
            handler._guard(lambda: handler._get_qq_config())
        elif path == "/state":
            st = store.get_state()
            try:
                # 多取几条：渲染时要滤掉「没标签又中性」的记录，
                # 只取 3 条的话过滤完可能一条不剩。
                st["emotion_recent"] = store.emotion_log_list(limit=10, days=7)
            except Exception:
                st["emotion_recent"] = []
            try:
                st["affinity"] = float(store.affinity_get("owner") or 0)
            except Exception:
                st["affinity"] = 0.0
            try:
                st["open_threads"] = [
                    {"title": x["title"], "status": x["status"],
                     "last_seen_at": x["last_seen_at"]}
                    for x in store.open_threads(8)
                ]
            except Exception:
                st["open_threads"] = []
            try:
                # 只给「说了 6 次以上」或「她主动学的」——一两次的碎句不算口头禅
                st["slang_learned"] = store.slang_list(
                    limit=6, only_repeated=True, min_count=6, require_meaning=True)
            except Exception:
                st["slang_learned"] = []
            try:
                # 够 6 次但还没搞懂意思的，提示她去问
                st["slang_pending"] = store.slang_pending(6, 4)
            except Exception:
                st["slang_pending"] = []
            hour = None
            try:
                raw_hour = (query.get("hour") or [None])[0]
                if raw_hour not in (None, ""):
                    hour = int(raw_hour) % 24
            except Exception:
                hour = None
            st["activity"] = store.current_activity(hour)
            fetch_weather = str((query.get("weather") or ["0"])[0]).lower() in ("1", "true", "yes")
            st["weather"] = store.current_weather(fetch=fetch_weather)
            st["stage"] = store.current_stage()
            st["emotion"] = store.get_emotion()
            try:
                st["slang"] = store.slang_list(8)
                st["affinity"] = store.affinity_get("owner")
                st["open_tasks"] = len([x for x in store.task_list(include_done=False)])
                st["seen_liked"] = store.seen_liked()
                # 昨天留下的东西（日记 / 便签），她今天可以自然提起
                import datetime as _dt
                yday = (_dt.date.today() - _dt.timedelta(days=1)).isoformat()
                ymd = yday[5:] if len(yday) >= 10 else yday
                yd = []
                try:
                    d = store.diary_get(yday)
                    if d and d.get("text"):
                        yd.append(f"昨天（{ymd}）的日记：" + d["text"][:80])
                except Exception:
                    pass
                try:
                    for n in store.note_list(5):
                        if n.get("date") == yday and n.get("text"):
                            yd.append(f"昨天（{ymd}）的便签：" + n["text"][:60])
                            break
                except Exception:
                    pass
                st["yesterday"] = yd
                st["browsed"] = store.browsed_list(3)
                all_memes = store.meme_list(limit=50)
                st["meme_total"] = len(all_memes)
                st["meme_emotions"] = sorted({m["emotion"] for m in all_memes if m["emotion"]})
            except Exception:
                st["slang"] = []
                st["affinity"] = 0
                st["open_tasks"] = 0
            st["view_hour"] = hour
            handler._json(200, st)
        elif path == "/persona/context":
            handler._guard(handler._persona_context)
        elif path == "/persona":
            handler._guard(handler._get_persona)
        elif path == "/export":
            handler._guard(handler._export)
        elif path == "/config":
            handler._guard(handler._get_config)
        else:
            return False
        return True
