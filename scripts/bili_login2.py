"""直接走 passport 二维码登录，避开 bilibili_api 的 cookie 解析 bug。"""

import asyncio
import json
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import aiohttp
import qrcode

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from settings import DSH_HOME, QR_FILE

OUT = QR_FILE
CRED = DSH_HOME / "bili-duty" / "bili_credential.json"
GEN = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
POLL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Referer": "https://www.bilibili.com/",
}


def extract_cookie(url: str) -> dict:
    query = parse_qs(urlparse(url).query)
    return {
        "sessdata": (query.get("SESSDATA") or [""])[0],
        "bili_jct": (query.get("bili_jct") or [""])[0],
        "dedeuserid": (query.get("DedeUserID") or [""])[0],
        "buvid3": (query.get("buvid3") or [""])[0],
    }


async def main() -> None:
    async with aiohttp.ClientSession() as sess:
        async with sess.get(GEN, headers=UA) as r:
            data = await r.json()
        payload = data.get("data") or {}
        key = payload.get("qrcode_key") or ""
        url = payload.get("url") or ""
        if not key or not url:
            print("GEN_FAILED", data)
            return
        img = qrcode.make(url)
        img.save(OUT)
        print("QR_SAVED", OUT, OUT.stat().st_size, flush=True)

        started = time.time()
        while time.time() - started < 300:
            await asyncio.sleep(2)
            async with sess.get(POLL, params={"qrcode_key": key}, headers=UA) as r:
                poll = await r.json()
                cookies = {c.key: c.value for c in r.cookies.values()} if r.cookies else {}
            data2 = poll.get("data") or {}
            code = data2.get("code")
            if code == 86101:
                continue
            if code == 86090:
                print("STATE_SCANNED", flush=True)
                continue
            if code == 86038:
                print("TIMEOUT", flush=True)
                return
            if code == 0:
                result = extract_cookie(data2.get("url") or "")
                for name, value in cookies.items():
                    if name == "SESSDATA" and not result["sessdata"]:
                        result["sessdata"] = value
                    elif name == "bili_jct" and not result["bili_jct"]:
                        result["bili_jct"] = value
                    elif name == "DedeUserID" and not result["dedeuserid"]:
                        result["dedeuserid"] = value
                    elif name == "buvid3" and not result["buvid3"]:
                        result["buvid3"] = value
                CRED.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
                print("LOGIN_DONE", {k: len(v) for k, v in result.items()}, flush=True)
                return
            print("UNKNOWN", code, poll, flush=True)
            await asyncio.sleep(2)
        print("TIMEOUT", flush=True)


asyncio.run(main())
