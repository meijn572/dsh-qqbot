"""自主刷轮次：看视频 → 决定分不分享 → 写活动/L0/L3。"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Awaitable, Callable

from qqbot.domains.autonomy.bili import (
    apply_interest,
    compose_share_text,
    decay_interests,
    fetch_bili_feed,
    pick_topic,
)
from qqbot.domains.autonomy.state import (
    AUT_REPORT_DIR,
    aut_seen_set,
    autonomy_cfg,
    load_aut_seen,
    load_aut_state,
    load_interests,
    mark_aut_seen,
    save_aut_state,
    similar_topic,
)

log = logging.getLogger("qqbot.autonomy.round")


@dataclass
class Deps:
    users: list[int]
    activity_sid: Callable[[], Awaitable[str]]
    internal_turn: Callable[[str, str, str], Awaitable[str]]  # sid, chat_key, prompt
    maintenance_turn: Callable[[str], Awaitable[str]]
    recent_scene: Callable[[str], Awaitable[str]]
    recent_text: dict[str, str]
    last_share: dict[str, dict]
    add_l0: Callable[[str, str], None]
    add_event: Callable[[str], None]
    log_activity: Callable[[str, str, str], None]
    send_private: Callable[[int, str], Awaitable[None]]
    lock: asyncio.Lock
    consolidate: Callable[[str], Awaitable[None]]


def _quiet_now(cfg: dict) -> bool:
    try:
        start_s, _, end_s = str(cfg.get("quiet_hours") or "0-8").partition("-")
        start, end = int(start_s), int(end_s)
    except (TypeError, ValueError):
        start, end = 0, 8
    hour = time.localtime().tm_hour
    if start <= end:
        return start <= hour < end
    return hour >= start or hour < end


def note_user_reply(chat_key: str) -> None:
    """主人回消息了：解除「连续分享没人理」的暂停。"""
    state = load_aut_state()
    state["last_user_reply"] = int(time.time())
    if int(state.get("unanswered_shares") or 0):
        state["unanswered_shares"] = 0
    save_aut_state(state)


async def run_round(deps: Deps) -> dict | None:
    cfg = autonomy_cfg()
    if not deps.users:
        return None
    uid = int(deps.users[0])
    chat_key = f"private:{uid}"
    sid = await deps.activity_sid()
    topic, mode = pick_topic(cfg)
    interests = load_interests()[:8]
    listing = "\n".join(f"- {i.get('topic')}（权重 {i.get('weight')}）" for i in interests) or "（清单还是空的）"
    recent = deps.recent_text.get(chat_key, "")[:300]
    max_videos = int(cfg.get("max_videos_per_round", 3))
    seen = aut_seen_set()
    feed = [it for it in await fetch_bili_feed(12) if it["bvid"] not in seen]
    feed_lines = "\n".join(f"- {it['bvid']}｜{it['title']}｜{it['up']}" for it in feed) or "（没拿到新的）"
    seen_lines = "、".join(str(i.get("bvid")) for i in load_aut_seen()[-15:]) or "（无）"
    prompt = (
        "（内部探索，不要回复用户、不要把结果直接发出去）现在是 " + time.strftime("%Y-%m-%d %H:%M") + "。\n"
        f"你的兴趣清单：\n{listing}\n"
        f"最近聊天里出现过：{recent or '（没有）'}\n"
        f"最近已经看过的 BV（不要重复看）：{seen_lines}\n"
        f"首页推荐流（可能是你没接触过的领域）：\n{feed_lines}\n"
        f"这一轮的方向：{('自由探索，挑一个跟兴趣清单无关、你真好奇的领域' if mode == 'explore' else f'优先看「{topic}」')}。\n"
        "请按真实好奇心走，来源可以自己选：\n"
        f"1) 用 bili_search 搜最多 {max_videos} 条（关键词自定，近期的）；或者直接从推荐流里挑 1-2 条\n"
        "2) 用 bili_subtitle 读其中 1 条的字幕原文（太长就只看关键部分）；画面/动作很重要的视频，可以再调 bili_frames 看 3-6 帧\n"
        "   没字幕但像是在讲话的视频，可以用 bili_transcribe 试着转写；它最多等 25 秒，跑不完会给你 job_id，先记下，别在一轮里死等。\n"
        "这一轮只是看，发不发之后再决定。\n"
        "只输出 JSON：{\"topic\":\"这轮主题（短标签，≤12 字；若属于清单里已有方向，直接沿用清单里的名字）\","
        "\"videos\":[{\"bvid\":\"\",\"title\":\"\",\"why\":\"为什么点开\"}],"
        "\"thought\":\"看完的想法（一两句，第一人称）\"}\n"
        "不要输出 JSON 以外的内容。"
    )
    async with deps.lock:
        reply = await deps.internal_turn(sid, chat_key, prompt)
        match = re.search(r"\{.*\}", reply, re.S)
        if not match:
            log.info("自主刷：没拿到 JSON，跳过")
            return None
        try:
            data = json.loads(match.group(0))
        except Exception:  # noqa: BLE001
            log.warning("自主刷 JSON 解析失败")
            return None
        round_topic = str(data.get("topic") or topic or "自由探索")
        thought = str(data.get("thought") or "").strip()
        videos = data.get("videos") if isinstance(data.get("videos"), list) else []
        mark_aut_seen([v for v in videos if isinstance(v, dict)], round_topic)
        scene = await deps.recent_scene(chat_key)
        video_lines = "\n".join(
            f"- 《{v.get('title', '')}》" for v in videos[:max_videos] if isinstance(v, dict)
        ) or "（没有具体视频）"
        decide_prompt = (
            "（内部判断，不要回复用户）刚才你看完了这些：\n"
            f"主题：{round_topic}\n视频：\n{video_lines}\n想法：{thought or '（没写）'}\n\n"
            f"{scene}\n\n"
            "现在要跟主人说吗？这一轮也可以什么都不做，刷到的东西可以只自己留着。\n"
            "如果决定说，先写 why_now：为什么是现在。写不出来，就把 share 设为 false。\n"
            "只输出 JSON：{\"share\":true或false,\"why_now\":\"为什么现在说\","
            "\"line\":\"想对主人说的话（share=true 才写；像随口聊天，不要罗列数据）\","
            "\"links\":[\"值得贴出来时才填 BV 号，通常留空\"]}\n"
            "不要输出 JSON 以外的内容。"
        )
        decision_reply = await deps.internal_turn(sid, chat_key, decide_prompt)
        decision_match = re.search(r"\{.*\}", decision_reply or "", re.S)
        decision: dict = {}
        if decision_match:
            try:
                decision = json.loads(decision_match.group(0))
            except Exception:  # noqa: BLE001
                decision = {}
        data["share"] = bool(decision.get("share"))
        data["why_now"] = str(decision.get("why_now") or "").strip()
        data["line"] = str(decision.get("line") or "").strip()
        data["links"] = decision.get("links") if isinstance(decision.get("links"), list) else []
        if not data["share"]:
            log.info("自主刷：这轮决定不说（%s）", data.get("why_now") or "没写理由")
    AUT_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = AUT_REPORT_DIR / f"{time.strftime('%Y-%m-%d')}.md"
    lines = [f"\n## {time.strftime('%H:%M')} · {round_topic}（{'自由探索' if mode == 'explore' else '兴趣驱动'}）"]
    links: list[str] = []
    for video in videos[:max_videos]:
        if isinstance(video, dict):
            bvid = str(video.get("bvid") or "").strip()
            link = f"https://www.bilibili.com/video/{bvid}" if bvid else ""
            if link:
                links.append(link)
            lines.append(f"- {video.get('title', '')} {link or bvid} — {video.get('why', '')}")
    if thought:
        lines.append(f"\n> {thought}")
    with report.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    if mode == "explore":
        if not any(similar_topic(round_topic, str(i.get("topic", ""))) for i in load_interests()):
            apply_interest(round_topic, 0.2, "自由探索发现", "bili")
    state = load_aut_state()
    today = time.strftime("%Y-%m-%d")
    if state.get("date") != today:
        state.update({"date": today, "rounds": 0, "shares": 0})
    state["rounds"] = int(state.get("rounds", 0)) + 1
    state["last_run"] = int(time.time())
    recent_topics = list(state.get("recent_topics") or [])
    recent_topics.append(round_topic)
    state["recent_topics"] = recent_topics[-6:]
    share_line = str(data.get("line") or "").strip()
    raw_links = data.get("links") if isinstance(data.get("links"), list) else []
    chosen: list[str] = []
    for item in raw_links:
        value = str(item).strip()
        if not value:
            continue
        url = value if value.startswith("http") else f"https://www.bilibili.com/video/{value}"
        if url not in chosen:
            chosen.append(url)

    max_unanswered = max(1, int(cfg.get("max_unanswered_shares", 2)))
    pending = list(state.get("pending_shares") or [])
    recent_reply = float(state.get("last_user_reply") or 0)
    idle_minutes = ((time.time() - recent_reply) / 60) if recent_reply else 9999
    deferred_idle = float(cfg.get("deferred_min_idle_minutes", 30))
    share_idle = float(cfg.get("share_min_idle_minutes", 20))
    deferred_sent = False
    # 主人刚聊完先不急着补；等对话空下来再发攒下的
    if (pending
            and int(state.get("unanswered_shares", 0)) == 0
            and recent_reply
            and idle_minutes >= deferred_idle
            and time.time() - recent_reply <= float(cfg.get("deferred_share_hours", 6)) * 3600
            and int(state.get("shares", 0)) < int(cfg.get("share_max_per_day", 3))):
        item = pending.pop(0)
        text = compose_share_text(str(item.get("line") or ""), item.get("links") or [])
        if text:
            await deps.send_private(uid, text)
            deps.add_l0(chat_key, text)
            state["pending_shares"] = pending
            state["unanswered_shares"] = 1
            deps.last_share[chat_key] = {
                "topic": item.get("topic") or "",
                "text": text,
                "links": item.get("links") or [],
                "ts": time.time(),
            }
            state["shares"] = int(state.get("shares", 0)) + 1
            deferred_sent = True
            log.info("自主刷补发攒下的分享：%s", text[:160])

    if data.get("share") and share_line and not deferred_sent and int(state.get("shares", 0)) < int(cfg.get("share_max_per_day", 3)):
        if int(state.get("unanswered_shares", 0)) >= max_unanswered:
            pending.append({"topic": round_topic, "line": share_line, "links": chosen, "ts": int(time.time())})
            state["pending_shares"] = pending[-max(1, int(cfg.get("pending_share_max", 5))):]
            log.info("自主刷分享暂存：连续 %s 条没人回，先攒着", max_unanswered)
        elif idle_minutes < share_idle:
            pending.append({"topic": round_topic, "line": share_line, "links": chosen, "ts": int(time.time())})
            state["pending_shares"] = pending[-max(1, int(cfg.get("pending_share_max", 5))):]
            log.info("自主刷分享暂存：主人还在聊，先不打断（空闲 %.0f 分钟）", idle_minutes)
        else:
            text = compose_share_text(share_line, chosen)
            await deps.send_private(uid, text)
            deps.add_l0(chat_key, text)
            deps.last_share[chat_key] = {
                "topic": round_topic,
                "text": text,
                "links": chosen,
                "ts": time.time(),
            }
            state["unanswered_shares"] = int(state.get("unanswered_shares", 0)) + 1
            state["shares"] = int(state.get("shares", 0)) + 1
            log.info("自主刷分享：%s", text[:160])
    save_aut_state(state)
    titles = "、".join(f"《{v.get('title')}》" for v in videos[:3] if isinstance(v, dict) and v.get("title"))
    deps.log_activity("bili", f"刷了「{round_topic}」{titles}", thought)
    if thought:
        deps.add_event(f"事件：{time.strftime('%m-%d %H:%M')} 刷到「{round_topic}」{titles}；想法：{thought[:100]}")
    log.info("自主刷完成：%s（%s 条视频）", round_topic, len(videos))
    return data


async def loop(deps: Deps) -> None:
    await asyncio.sleep(30)
    while True:
        try:
            cfg = autonomy_cfg()
            if cfg.get("enabled", True) and not _quiet_now(cfg):
                state = load_aut_state()
                today = time.strftime("%Y-%m-%d")
                if state.get("date") != today:
                    state.update({"date": today, "rounds": 0, "shares": 0})
                    save_aut_state(state)
                if deps.users and state.get("interest_consolidated_date") != today:
                    await deps.consolidate(f"private:{int(deps.users[0])}")
                    state["interest_consolidated_date"] = today
                    save_aut_state(state)
                due = (
                    int(state.get("rounds", 0)) < int(cfg.get("daily_max", 10))
                    and time.time() - float(state.get("last_run") or 0) >= float(cfg.get("min_gap_minutes", 45)) * 60
                )
                if due:
                    decay_interests()
                    await run_round(deps)
        except Exception as exc:  # noqa: BLE001
            log.warning("autonomy_loop err: %s", exc)
        await asyncio.sleep(300)
