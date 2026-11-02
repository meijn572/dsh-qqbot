"""唯一配置入口：路径、端口、token 都从这里来。

其他模块不要再写死本机绝对路径。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

BOT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = Path(os.environ.get("DSHBOT_CONFIG") or (BOT_DIR / "config.json"))
CONFIG = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
DSH_HOME = Path(
    CONFIG.get("dsh_home")
    or os.environ.get("DSH_HOME")
    or (Path.home() / ".dsh-qqbot")
)
WORKSPACE = Path(
    CONFIG.get("cwd")
    or os.environ.get("DSHBOT_WORKSPACE")
    or (BOT_DIR / "workspace")
)
CMEM_BASE = str(CONFIG.get("cmem_base") or "http://127.0.0.1:8081")
PANEL_PORT = int(CONFIG.get("panel_port") or 6080)

TOKEN_OB_HTTP = Path(CONFIG.get("onebot_token_file") or (BOT_DIR / "onebot_token.txt")).read_text(
    encoding="utf-8"
).strip()
TOKEN_OB_WS = Path(CONFIG.get("onebot_ws_token_file") or (BOT_DIR / "onebot_ws_token.txt")).read_text(
    encoding="utf-8"
).strip()
TOKEN_DSH = Path(CONFIG.get("dsh_token_file") or (BOT_DIR / "dsh_token.txt"))
DEEPSEEK_KEY_FILE = Path(CONFIG.get("deepseek_key_file") or (BOT_DIR / "secret" / "deepseek.key"))
SILICONFLOW_KEY_FILE = Path(CONFIG.get("siliconflow_key_file") or (BOT_DIR / "secret" / "siliconflow.key"))

STATE_FILE = Path(CONFIG.get("state_file") or (BOT_DIR / "state.json"))
AGENTS = WORKSPACE / "AGENTS.md"

# 账号/主人不再写死在代码里；运行时从 config.json 读取
OWNER_ID = int((CONFIG.get("allowed_users") or [0])[0])
OWNER_CHAT_KEY = f"private:{OWNER_ID}"
BOT_QQ = int(CONFIG.get("bot_qq") or 0)
