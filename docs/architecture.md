# 架构说明

本文描述当前 DSH QQ Bot 的模块、文件职责、调用链和数据流。

> 维护原则：业务实现进 `qqbot/domains`，HTTP/存储策略进记忆服务，DSH 生命周期留在插件，`bridge.py` 只做 QQ 适配和装配。

## 1. 总览

```
QQ
└─ SnowLuma（QQ NT hook）
   ├─ OneBot HTTP 127.0.0.1:3000
   └─ OneBot WS   127.0.0.1:3001
        │
        ▼
  bridge.py（QQ 适配/编排）
   ├─ 消息过滤、合并、群门控
   ├─ 图片/表情下载
   ├─ 主动/群主动/自主刷/空间 定时任务
   └─ DSH RPC + OneBot 发送
        │
        ├──────────────► DSH qqbot2 127.0.0.1:60773
        │                  │
        │                  └─ 插件 dsh-remembers
        │                     ├─ hooks（生命周期）
        │                     └─ tools（模型工具）
        │
        └──────────────► 记忆服务 127.0.0.1:8081
                           ├─ /hook/pre-step
                           ├─ /hook/turn-end
                           ├─ /context /persona
                           ├─ /batch/run
                           └─ SQLite memories.db

面板 127.0.0.1:6080
   └─ 只读投影 + 少量动作，读记忆服务/配置/日志
```

## 2. 分层边界

| 层 | 负责 | 不负责 |
| --- | --- | --- |
| QQ 接入层 | OneBot WS/HTTP、消息解析、发送 | 记忆策略、人格 |
| `bridge.py` | 合并、群门控、会话绑定、定时任务装配 | 存储、抽取、召回格式 |
| `qqbot/domains/*` | 媒体、群、成长、自主、空间业务 | DSH 生命周期 |
| `qqbot/clients/*` | 记忆/人格 HTTP 客户端 | 业务判断 |
| DSH 插件 | hook、注入、tool schema、转发 | query 构造、surprisal、L0 判定 |
| 记忆服务 | 存储、检索、context、batch、hook 策略、人格 | QQ 收发 |
| 面板 | 展示与少量操作 | 后台任务 |

## 3. 目录与文件职责

### 3.1 根目录

| 文件 | 作用 |
| --- | --- |
| `bridge.py` | 当前运行入口。QQ ↔ DSH 桥、消息合并、群逻辑、定时任务装配 |
| `settings.py` | 唯一配置入口。读 `config.json`，暴露路径/端口/token/OWNER_ID/BOT_QQ |
| `panel.py` | 面板 HTTP 生命周期，64 行 |
| `panel_routes.py` | 面板 API 路由 |
| `panel_readers.py` | 面板投影、动作、服务访问 |
| `config.example.json` | 配置模板，无真实账号 |
| `README.md` | 使用/运维说明 |
| `docs/refactor-plan.md` | 重构阶段记录 |
| `docs/refactor-summary.md` | 重构结果总结 |
| `scripts/smoke.py` | 端口 + 接口 smoke |
| `scripts/check.ps1` | 单测 + smoke |
| `tests/` | 单测 |

### 3.2 `qqbot/`

当前是业务域库，不是启动入口。

| 文件 | 作用 |
| --- | --- |
| `qqbot/contracts.py` | `InboundMessage` / `InboundBatch` / `OutboundMessage` / `ReplyPlan` 数据契约 |
| `qqbot/ports.py` | `OutboundPort` / `MemoryPort` / `PersonaPort` / `ConversationPort` 协议 |
| `qqbot/runtime.py` | 目标运行时骨架，尚未接管 `bridge.py` |
| `qqbot/__main__.py` | 预留入口 |
| `qqbot/adapters/` | 预留 QQ/DSH 适配器 |
| `qqbot/conversation/` | 预留合并/门控/回复策略 |
| `qqbot/jobs/` | 预留任务注册 |

> `runtime.py`、`adapters/`、`conversation/`、`jobs/` 目前是骨架，实际运行仍由 `bridge.py` 装配。

### 3.3 `qqbot/clients/`

| 文件 | 作用 |
| --- | --- |
| `memory.py` | `cmem_call`、`persona_context`、`long_term_memory`、`l0_recent`、`recent_dialogue`、`ingest`、`set_emotion` |
| `persona.py` | 人格块端口，当前转调 `persona_context` |

`memory.py` 是桥接和 growth 访问记忆服务的统一出口，避免自己拼 URL。

### 3.4 `qqbot/domains/media/`

| 文件 | 作用 |
| --- | --- |
| `preprocess.py` | `vision_image` 动图拼帧/静态压缩；`native_image` 原生图片附件 |
| `download.py` | OneBot 图片/表情下载，写 `IMAGE_META` |
| `library.py` | 表情元数据、索引、`[[meme]]` 选择、关键词、`category_from_text`、`should_hint` |
| `vision.py` | Qwen3-VL 分类/描述，DeepSeek 兜底 |
| `stickers.py` | 表情去重、分类、收藏入库 |

### 3.5 `qqbot/domains/group/`

| 文件 | 作用 |
| --- | --- |
| `slang.py` | 群日志、群黑话、网络梗、`network_meme_hint` |
| `proactive.py` | 群主动说话：间隔、冷却、每日上限、发送、状态更新 |

群日志路径：`DSH_HOME/group-log/<gid>.jsonl`  
群黑话路径：`DSH_HOME/group-slang/<gid>.json`  
网络梗：`DSH_HOME/network-memes.json`

### 3.6 `qqbot/domains/growth/`

| 文件 | 作用 |
| --- | --- |
| `reflect.py` | 人格复盘：人格 + 最近对话 + 长期记忆 → 自我认知 |
| `profile.py` | 用户画像刷新，写 L2 `user_profile` |
| `style.py` | 表达风格复盘，生成待确认提议 |
| `important.py` | 重要的事自检 + `important.md` 同步 |
| `emotion.py` | 情绪自检 |

growth 只依赖 `qqbot/clients` 和 `settings`，不 import bridge。

### 3.7 `qqbot/domains/autonomy/`

| 文件 | 作用 |
| --- | --- |
| `state.py` | 兴趣、已看、运行状态、`similar_topic`、读服务 L1 |
| `bili.py` | 推荐流、视频详情、选题、兴趣权重、分享文案 |
| `interests.py` | 兴趣提取、合并 |
| `round.py` | 自主刷单轮 + loop：看视频 → 决定分享 → 写 L0/L3/活动 |

### 3.8 `qqbot/domains/qzone/`

| 文件 | 作用 |
| --- | --- |
| `publish.py` | 空间说说生成、校验、定时发布 |

### 3.9 记忆服务

路径：`$DSH_HOME/remembers-service/`

| 文件 | 作用 |
| --- | --- |
| `server.py` | HTTP Handler、启动、存储/LLM/embedder 初始化、剩余路由方法 |
| `memory_core.py` | SQLite schema、增删查、分层、FTS、向量、persona 存储 |
| `extractor.py` | L1/L2/L3/L4 抽取规则、批量抽取 |
| `surprisal.py` | 惊讶度门控 |
| `llm.py` | LLM 客户端 |
| `memory/context.py` | `/context` 格式：分层、配额、scope、人称提示 |
| `persona/context.py` | 人格块格式 |
| `persona/api.py` | 人格返回结构 |
| `api/routes/hooks.py` | `/hook/pre-step`、`/hook/turn-end` |
| `api/routes/memory.py` | ingest / search / forget |
| `api/routes/persona.py` | 人格读写 |
| `api/routes/read.py` | 只读查询 |
| `api/routes/get.py` | 复杂 GET 路由 |
| `api/routes/table.py` | POST 路由表 |

### 3.10 DSH 插件

路径：`plugins/dsh-remembers/`

| 文件 | 作用 |
| --- | --- |
| `index.mjs` | 2 行，re-export |
| `app.mjs` | 生命周期/装配：systemPrompt、profile/person/state 注入、turn end、extract、episode |
| `client.mjs` | 记忆服务 HTTP 客户端 |
| `config.mjs` | 配置解析 |
| `hooks/recall.mjs` | 转发 `/hook/pre-step`，返回 recall |
| `hooks/turn_end.mjs` | 转发 `/hook/turn-end` |
| `hooks/state.mjs` | 状态块渲染 |
| `hooks/persona.mjs` | 人格/profile 渲染 |
| `tools/emotion.mjs` | `set_emotion` |
| `tools/important.mjs` | `remember_important` |
| `tools/persona.mjs` | `persona_update` |
| `tools/activity.mjs` | `set_my_activity` |
| `tools/memes.mjs` | `find_meme` / `learn_meme` / `mark_meme_used` |
| `tools/companion.mjs` | 任务/便签/学词/日记/活动 |

### 3.11 面板

| 文件 | 作用 |
| --- | --- |
| `web/index.html` | 页面骨架 |
| `web/app.js` | tab、渲染、fetch |
| `web/style.css` | 样式 |
| `panel.py` | HTTP 生命周期、静态文件 |
| `panel_routes.py` | `/api/*` 路由 |
| `panel_readers.py` | 投影/动作：status、mood、memory、persona、guests、notebook、stickers、lexicon、bili、logs 等 |

## 4. QQ 消息主流程

### 4.1 入站

```
OneBot WS message
  → bridge.run() 收到
  → asyncio.create_task(handle(...))
```

`handle`：

1. 校验 `allowed_users` / `allowed_groups`
2. 跳过 `/` 命令
3. 群聊记录发言人、群日志
4. 私聊触发 `touch_guest`
5. 分享反馈 `record_share_feedback`
6. 下载图片/表情
7. 群聊判断：
   - 被 @ 或叫名字 → 接
   - 正在跟聊 → 接
   - 否则按 `interject_probability` 决定插话，不接就静默收集表情
8. 写入 `PENDING[chat_key]`，重置合并窗口

合并窗口：

- 私聊：`merge_seconds`，默认 12 秒
- 群聊：`group_merge_seconds`，默认 20 秒

### 4.2 合并与门控

`schedule_flush`：

1. 等待窗口
2. 窗口内来新消息 → 重新计时
3. 拼文本、图片/表情 note
4. 群聊未被叫到且没插话 → `gate_skip_probability` 或 `topic_relevant`
5. `_process_locked`

### 4.3 请求 DSH

`_process_locked`：

1. 读/建 `state.json` 里的 DSH session
2. 取当前 `asOfSeq` 作为 baseline
3. 组装 `[[bridge-note]]`：
   - 表情库检索提示
   - 群黑话
   - 私聊可复用群黑话
   - B 站链接解析
   - 网络梗
4. `dsh.prompt(session, text, images)`
5. `dsh.wait_reply`
6. 期间来了新消息 → 丢弃过期回复
7. `OneBot.send`：
   - `sanitize_markdown`
   - `split_bubbles`
   - 文本/图片分开发送
8. 更新 `asOfSeq`

### 4.4 DSH 插件 pre-step

`app.mjs` 注册两个 `agent/pre-step`：

第一个：

1. 记录当前发言人昵称
2. 画像块（每 50 轮/首次）
3. 多人画像/群发言人说明
4. 召回：
   - 调 `hooks/recall.mjs`
   - 服务 `/hook/pre-step`
   - 返回 `system` / `recall`
   - 未映射 `global` 会话直接跳过
5. 所有块放进 `extra`，最后合并为一条注入，避免互相顶掉

第二个：

- 状态块（时间/心情/活动/关系阶段等）
- 变化才注入，哈希去重

### 4.5 DSH turn end

`session/event`：

- `user/message` / `assistant/message` 累积到 state
- `turn/end` → `flushTurn`

`flushTurn`：

1. 跳过未登记/内部会话
2. 清洗唤醒片段
3. 亲密度/活动/情绪等轻量副作用
4. `hooks/turn_end.mjs` → `/hook/turn-end`
5. 服务做 surprisal 门控，决定是否写 L0
6. 独立 `extract` 调用结构记忆抽取
7. episode 缓冲

## 5. 记忆服务数据流

### 5.1 pre-step

```
POST /hook/pre-step
{
  request_id, session, scope,
  messages: [...]
}
→ {
  system: 人格块,
  recall: 召回块
}
```

服务：

1. `persona.context.build_persona_context`
2. 从 messages 取最后几条 user/assistant 拼 query
3. `memory.context.build_context`
4. 返回

### 5.2 turn-end

```
POST /hook/turn-end
{
  request_id, session, scope,
  user, assistant, context,
  user_id, nickname
}
→ {
  stored, id, surprisal, reason
}
```

服务：

1. `gate.score(user, context)`
2. 寒暄/低惊讶 → 不写
3. 合并 `主人：...` + `我：...`
4. 写 L0，tags 带 `raw` 和 `session:<id>`
5. 追加 `hook-events.jsonl`

### 5.3 批量蒸馏

`bridge.memory_batch_loop` 每 5 分钟调：

```
POST /batch/run
```

服务按条件生成：

- L0 → L1
- L1 + L0 → L3
- L1 + L3 → L4

L2 由 profile 刷新单独写。

### 5.4 引擎、工作流、注入的边界

当前记忆和人格不是完全对称的。先把边界写清楚，暂时不搬代码。

#### 定义

| 类型 | 判断标准 | 例子 |
| --- | --- | --- |
| 引擎 | 确定性数据变换、事务、检索、格式 | SQL、FTS/向量、CRUD、context 拼装、persona 存储、facts apply |
| 工作流 | 需要 LLM 提示词、时间窗口、上限、业务判断、重试 | batch 何时跑、抽什么、L1/L3/L4 接受规则、复盘/画像 |
| 注入 | 决定文本怎么进宿主 | DSH 消息追加、systemPrompt |
| 触发 | 谁在什么时候调用 | bridge 定时器、QQ 事件、hook |

#### 当前分布

记忆：

```
service       memory_core / 检索 / context / surprisal / extractor
bridge        memory_batch_loop 定时触发
plugin        recall 注入
```

人格：

```
service       persona 存储 / persona 文本格式 / API
growth        复盘、画像、风格、重要的事工作流
plugin        systemPrompt / profile / person 注入
```

#### 已知混层

`extractor.py` 同时包含：

- 引擎部分：候选查询、去重、写库、source_ids
- 工作流部分：抽取提示词、接受规则、L1/L3/L4 编排

`server.py /batch/run` 也是控制面编排。

所以“记忆逻辑全在 service”并不准确。更准确是：

> 记忆引擎在 service，记忆工作流部分在 service、部分在 bridge，注入在 plugin。

#### 为什么现在不搬

- `extractor.py` 和 `memory_core.py` 共享候选集、去重、事务、source_ids
- 拆开需要新增内部 API、幂等、半成功回滚
- 当前 batch 在服务进程内跑，事务简单
- 这不是文件位置问题，是事务边界问题

#### 如果以后要统一

目标：

```
service
  memory_core
  检索 / context
  persona 存储
  facts apply（事务/去重/校验）

memory-workflows
  定时 batch
  抽取提示词
  L1/L3/L4 编排
  接受/拒绝策略

plugin
  注入

bridge
  触发/装配
```

原则：

- 需要 LLM 提示词、时间窗口、每日上限、业务判断的 → workflow
- 只做确定性数据变换、事务、检索的 → engine
- 注入永远在 plugin
- 触发永远在 bridge/jobs

不要为了目录统一，把 `memory_core.py`、检索、context、persona 存储搬出去。

## 6. 主动与自主

### 6.1 私聊主动

`inject_watch`：

- 监听 `DSH_HOME/qq-inject.jsonl`
- 服务 `/proactive` 写入
- 桥接读取并发送

`proactive_loop`：

- 25–50 分钟随机
- 静默 0–8
- 让 DSH 生成，SKIP 不发

### 6.2 群主动

`group_proactive_loop` → `qqbot/domains/group/proactive.py`

- 180–360 分钟
- 空闲 60 分钟
- 每天最多 1 次

### 6.3 B 站自主刷

`autonomy_loop` → `qqbot/domains/autonomy/round.py`

一轮：

1. 选题（兴趣/自由探索）
2. 拉推荐流
3. DSH 活动会话里调用 bili-scroll 工具看视频
4. 解析视频/想法
5. 二次判断要不要分享
6. 分享则写 L0，活动写 L3
7. 更新兴趣/已看/状态
8. 写报告 `bili-autonomy/out/YYYY-MM-DD.md`

### 6.4 QQ 空间

`qzone_loop` → `qzone/publish.py`

- 每天 1 条
- 间隔 6 小时
- 静默 0–8
- 好友可见 `ugc_right=4`
- 禁止链接、私密词、广告

## 7. 成长任务

| 循环 | 模块 | 频率 |
| --- | --- | --- |
| 人格复盘 | `growth/reflect.py` | 8 小时 + 8–24 点 |
| 画像刷新 | `growth/profile.py` | 2 天 |
| 风格复盘 | `growth/style.py` | 3 天 |
| 情绪自检 | `growth/emotion.py` | 3–5 小时，最多 5 次/天 |
| 重要的事 | `growth/important.py` | 10/22 点 |
| 重要文件同步 | `growth/important.py` | 60 秒 |

## 8. 面板

```
浏览器
  → panel.py（静态 + HTTP）
  → panel_routes.py（/api/*）
  → panel_readers.py（cmem_get / 本地配置 / 日志）
  → 记忆服务 / DSH / 文件
```

页面：

- 概览
- 心与记忆：记忆/人格/群友/小本子/心情·关系/主动
- 表情·黑话
- 日志
- 兴趣·B 站

面板只读为主；动作有：

- 主动开关
- 风格应用/忽略
- 人格核心设定保存
- 表情/黑话增删
- 桥接重启
- B 站扫码

## 9. 配置文件

`config.json` 不入库，模板是 `config.example.json`。

关键字段：

| 字段 | 作用 |
| --- | --- |
| `onebot_http` / `onebot_ws` | OneBot |
| `dsh_base` | DSH 端口 |
| `cmem_base` | 记忆服务 |
| `panel_port` | 面板 |
| `allowed_users` | 主人白名单 |
| `allowed_groups` | 群白名单 |
| `bot_qq` | bot QQ，用于 @/戳一戳判断 |
| `dsh_home` | 数据目录 |
| `cwd` | 工作目录 |
| `merge_seconds` / `group_merge_seconds` | 合并窗口 |
| `group_activity` | 群门控/插话 |
| `group_proactive` | 群主动 |
| `bili_autonomy` | 自主刷 |
| `qzone` | 空间 |
| `emotion_check` | 情绪自检 |
| `important_check` | 重要的事 |
| `persona_reflect` | 复盘 |

`settings.py` 读取后暴露：

```python
OWNER_ID
OWNER_CHAT_KEY
BOT_QQ
CMEM_BASE
DSH_HOME
```

## 10. 观测点

| 位置 | 内容 |
| --- | --- |
| `bridge.err` | 桥接收发/异常 |
| `hook-events.jsonl` | pre-step/turn-end 事件 |
| `cmem.err` | 记忆服务错误 |
| `qqbot2.err` | DSH/插件错误 |
| 面板“日志” | bridge/selfwake/bili 日志 |
| `/health` | 记忆服务状态 |
| `/api/status` | 面板概览 |

## 11. 扩展方式

### 加一个业务域

1. 新建 `qqbot/domains/<name>/`
2. 不 import bridge
3. 依赖通过参数或 client 传入
4. 在 bridge 只做装配/定时任务
5. 加测试

### 加一个工具

1. 新建 `plugins/dsh-remembers/tools/<name>.mjs`
2. 导出 `registerXTool({ registerTool, log, endpoint, ... })`
3. 在 `app.mjs` 调用
4. 只做 schema + HTTP 转发

### 加一个服务路由

1. `api/routes/` 加处理函数
2. GET 加 `get.py` / `read.py`
3. POST 加 `table.py`
4. 加 smoke

### 加一个面板页

1. `web/` 加 HTML/JS
2. `panel_readers.py` 加投影
3. `panel_routes.py` 加路由
4. 不改 `panel.py`

## 12. 已知限制

- `app.mjs` 941 行，生命周期还能继续拆
- `remembers-service/server.py` 2709 行，路由已拆一部分
- 前端 `app.js` 还没按 tab 拆
- `qqbot/adapters`、`conversation`、`jobs`、`runtime.py` 仍是骨架
- `extractor.py` 混合引擎与工作流，边界见 5.4；当前不搬
- DSH 实际加载 profile 有两个路径，改插件要同步
- 旧 `memory.db` 已不写，文件还在；旧目录已归档
