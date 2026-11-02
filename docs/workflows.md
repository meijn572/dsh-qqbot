# 工作流与记忆逻辑

本文写清楚当前实际运行的记忆蒸馏、人格复盘、B 站自主等流程。

对应代码：

```
qqbot/domains/growth/       人格工作流
qqbot/domains/autonomy/     B 站工作流
qqbot/domains/group/        群聊工作流
qqbot/domains/qzone/        空间工作流
service/                    记忆引擎
plugins/dsh-remembers/      DSH 适配
bridge.py                   触发与装配
```

---

## 1. 记忆分层

| 层 | 内容 | 默认半衰期 |
| --- | --- | --- |
| L0 | 原话，完整保留 | 不衰减 |
| L1 | 原子事实、近况、细节 | 30 天 |
| L2 | 用户画像 | 180 天 |
| L3 | 事件线、一段经历 | 90 天 |
| L4 | 约定、规矩、关系底线 | 不衰减 |

半衰期在 `service/memory_core.py` 的 `TIER_HALF_LIFE`。

L0 不参与排序衰减，主要作为原文来源和最近上下文。

---

## 2. L0 写入

### 2.1 入口

```
DSH turn/end
  → plugins/dsh-remembers/hooks/turn_end.mjs
  → POST /hook/turn-end
  → service/api/routes/hooks.py :: turn_end()
```

### 2.2 门控

`service/surprisal.py`：

- 寒暄硬否决：嗯、好的、在吗、晚安
- 情绪词加分：累、烦、难过、约定、承诺
- 长度突变加分
- 问句/祈使小幅加分
- 默认阈值 0.35

低于阈值不写。

### 2.3 写入格式

服务把一轮拼成：

```
主人：<用户原话>
我：<鱼的回复>
```

写入 L0：

- `subject=self`
- `tags=["raw", "session:<id>"]`
- `scope` 来自 session 映射
- 有 embedder 时写向量

`internalTurn`、未映射会话、系统提示不写入。

### 2.4 观测

`$DSH_HOME/hook-events.jsonl` 记录：

- `pre_step`：session/scope/system_chars/recall_chars
- `turn_end`：stored/id/reason/surprisal

---

## 3. 批量蒸馏

### 3.1 触发

`bridge.py :: memory_batch_loop` 每 5 分钟：

```
POST /batch/run
```

服务端在 `_batch_run()` 里判断是否真的跑。

### 3.2 L0 → L1

条件：

- 从 `batch_l0_last` 水位线之后取 L0
- 每次最多取 30 条
- 满足任一：
  - 新 L0 ≥ `l1_every`（默认 6）
  - 最新一条 L0 已经 ≥ `idle_minutes`（默认 15 分钟）

执行：

- 取前 `l1_max` 条（默认 12）
- 拼成文本
- 调 `extractor.extract_batch()`
- 只产 **L1**
- 写 `source_ids` 指回 L0
- 成功后推进 `batch_l0_last`
- 把新 L1 id 放入 `batch_l1_pending`

`extract_batch()` 即使上游给了 L2/L3/L4，也会强制改成 L1。

### 3.3 L1 → L3

条件：

- `batch_l1_pending` 里累计 ≥ `l3_every`（默认 6）

执行：

1. 取这些 L1 的 id/text/source_ids
2. 找到对应 L0 原文
3. 拆成 `user` / `assistant` 轮次
4. 调 `extractor.summarize_episode()`
5. 生成一条 L3
6. 清空 `batch_l1_pending`

L3 要求：

- 第一人称
- 150–400 字
- 写主线、情绪走向、转折、承诺、没解决的话头
- 不写寒暄、复述、推测

### 3.4 L1/L3 → L4

条件：

- 距上次 L4 ≥ `l4_hours`（默认 24 小时）

素材：

- 最近 24 小时的 L1/L3，最多 60 条
- 现有 L4 最多 20 条

执行：

- `extractor.extract_rules()`
- 只收明确、长期、以后还要照做的约定/底线/称呼要求
- 最多 5 条
- 与现有 L4 去重
- 写入 L4，`tags=["rule","batch"]`

L4 不衰减。

### 3.5 L2 画像

L2 不走 batch。

走独立画像工作流：

```
bridge.profile_refresh_loop
  → qqbot/domains/growth/profile.py
  → POST /persona/user
```

间隔由 `profile_refresh_days` 控制，默认 2 天。

### 3.6 蒸馏失败

- LLM 不可用：`extract_batch` 返回 degraded，不推进水位
- L3 失败：保留 pending，下次再试
- L4 失败：不更新 `batch_l4_at`

不会静默丢 L0。

---

## 4. 召回

### 4.1 入口

```
DSH agent/pre-step
  → plugins/dsh-remembers/hooks/recall.mjs
  → POST /hook/pre-step
  → service/api/routes/hooks.py :: pre_step()
```

### 4.2 查询

服务从 messages 里取最近几条 user/assistant，拼成 query。

检索：

- `store.search()`
- BM25 + 向量 + 层权重 + 时间衰减
- scope 过滤：当前场景 + global
- tiers：L1/L2/L3/L4

### 4.3 格式

`service/memory/context.py`：

- 按层配额
- 按层/时间排序
- 输出：

```
[L1 · 事实] ...
[L3 · 事件 · 08-12 20:00] ...
```

`purpose=recent` 时按时间正序，并加“以下是最近的对话原话”。

### 4.4 注入

插件把 recall 作为一条额外消息追加，不写进 system prompt。

未映射 `scope=global` 的会话直接跳过，避免私人记忆泄漏。

### 4.5 一轮对话实际注入什么

不是“把所有记忆都塞进去”，而是几类块分别注入。

| 块 | 来源 | 内容 | 限制 |
| --- | --- | --- | --- |
| system prompt 人格 | 插件 `client.persona()` + `hooks/persona.mjs` | 核心设定、自我认知、身份、自我形象、我眼中的主人 | `personaMaxChars` 默认 4000 |
| person | 插件 `client.profileOf()`，服务 `/profiles` | 当前发言人是谁、群友画像、非主人提示 | 群聊/私聊别人 |
| recall | 插件 `hooks/recall.mjs`，服务 `/hook/pre-step` | L1/L3/L4 召回块 | 见下 |
| state | 插件 pre-step，服务 `/state` | 时间、心情、亲密度、活动、B 站状态、自我认知、群黑话、关系阶段、颜文字/emoji 提示 | 变化才注入，哈希去重 |
| bridge-note | `bridge.py :: _process_locked` | 表情库检索提示、群黑话、私聊可复用黑话、B 站链接信息、网络梗、图片/表情路径 | 拼在用户消息里，不进 system prompt |

L4 不再走 profile 块。L4 现在只通过 recall 注入。

#### recall 具体取什么

`service/api/routes/hooks.py :: pre_step()`：

- 从 messages 取最近几条 user/assistant，最多 1000 字，作为 query
- tiers：`L1`、`L3`、`L4`
- 配额：`L1=20`、`L3=10`、`L4=4`
- scope：当前会话 + `global`
- `max_chars=6000`
- `purpose=recall`
- 排序：BM25 + 向量 + 层权重 + 时间衰减
- 格式化：`[L1 · 事实] ...` / `[L3 · 事件 · 08-12 20:00] ...`

不含 **L2**，也不含 **L0**。

L2 只通过人格 system prompt 里的 `user_profile` 注入。L2 仍保留在库里，供画像刷新、面板和 fallback 使用。

L0 只在这些地方用：

- 批量蒸馏 L1
- 复盘/画像/情绪/重要的事的最近上下文
- 面板记忆展示

正常聊天的 recall 不注入 L0。主要是因为会话上下文已经提供了原话；同时 L0 信息密度低、重复注入会浪费上下文。它仍然用于蒸馏、复盘和面板。

#### 不注入什么

- 不注入数据库 id、检索分数、hook 日志
- 不注入别的私聊 scope
- 不注入未映射 `global` 会话的召回
- 不注入内部维护提示、JSON、工具日志
- 不把 emotion_log / important_check 的中间状态塞进对话

#### 当前遗留的重复

服务 `/hook/pre-step` 已经返回 `system`，但插件实际仍用 `hooks/persona.mjs` 自己渲染 system prompt。

所以当前实际注入的是：

```
插件渲染的人格块
  + person
  + 服务返回的 recall
  + 插件状态块
  + bridge-note
```

不是服务返回的 `system`。

L2 已经不从 recall 取，L4 已经不从 profile 块取；这里剩下的重复只有“人格块由插件渲染”这一处。

---

## 5. 人格工作流

### 5.1 人格字段

| 字段 | 写入方 |
| --- | --- |
| `constitution` | 面板、手动 |
| `self_model` | 复盘、`persona_update` 工具 |
| `identity` | 面板 |
| `self_image` | 面板 |
| `user_profile` | 画像刷新、面板 |
| important 段 | 重要的事自检、`remember_important`、手动 |

### 5.2 人格复盘

文件：`qqbot/domains/growth/reflect.py`

触发：

```
bridge.persona_reflect_loop
  - 启动等 60 秒
  - 每 30 分钟检查
  - enabled
  - active_hours 默认 8-24
  - 距上次 ≥ min_gap_hours 默认 8 小时
```

输入：

- `/persona/context` 完整人格
- 最近对话 80 条
- 长期记忆 160

提示词要求：

- 只重写“自我认知”
- 400–900 字
- 第一人称
- 合并当前自我认知 + 最近经历 + 长期记忆
- 保留仍成立的变化，压缩过时/重复/琐碎
- 不改身份、底线、说话风格、相处原则
- 不新增事实设定
- 只输出正文

写入：

```
POST /persona/self
```

成功后写 `persona-reflect/state.json`：

- `last_run_date`
- `last_run_at`

失败不推进状态。

### 5.3 画像刷新

文件：`qqbot/domains/growth/profile.py`

触发：

```
bridge.profile_refresh_loop
  - 启动等 120 秒
  - 每 6 小时检查
  - 距上次 ≥ profile_refresh_days（默认 2 天）
```

输入：

- 完整人格
- 最近对话 60
- 长期记忆 160

要求：

- 300–600 字
- 用“你”称呼主人
- 只写长期稳定：身份、习惯、偏好、在意的事、雷区、相处方式
- 不写一次性事件、猜测、自己
- 不写插件/权重/提示词/模型
- 群友不是主人
- 有明确依据才写

写入：

```
POST /persona/user
```

### 5.4 风格复盘

文件：`qqbot/domains/growth/style.py`

触发：

```
bridge.style_review_loop
  - 启动等 300 秒
  - 每 6 小时检查
  - 没有待确认提议
  - 距上次 ≥ style_review_days（默认 3 天）
```

读取：

- `/persona`
- 核心设定里的 `<!-- style:begin -->` 段

要求：

- 4–8 条短句
- 120–500 字
- 只改真正有变化的
- 不新增身份/事实/关系
- 输出 JSON：`{"style":"...","reason":"..."}`

结果：

- 只写 `style-proposal.json`
- 不自动改核心设定
- 面板点“应用”才写回

### 5.5 重要的事

文件：`qqbot/domains/growth/important.py`

自检触发：

```
important_check.hours
默认 [10, 22]
每个小时槽只跑一次
```

输入：

- 当前 important 段
- 最近 L0 80 条

要求：

- 只收约定、底线、身份、关系里最关键的事
- 日常小事、情绪、一次性经历、称呼纠正、角色名不算
- 最多补一条
- 不重复
- 输出 JSON：`{"item":"..."}` 或 `{"skip":true}`

写入：

```
POST /persona/important
```

同步：

- 服务写回核心设定 important 段
- 同时更新 `$DSH_HOME/important/important.md`

文件同步循环每 60 秒检查 `important.md`，手写内容会 replace 到核心设定。

### 5.6 情绪自检

文件：`qqbot/domains/growth/emotion.py`

触发：

- 3–5 小时随机
- 每天最多 5 次
- 静默 0–8

判断：

- 只有真的被戳到、情绪有波动才记
- 没情绪跳过

写入：

```
POST /state
POST /emotion
```

字段：

- `label`
- `intensity`
- `reason`
- `valence`
- `arousal`
- `source=self-check`

### 5.7 人格注入

当前：

```
service /persona/context
  → 纯文本人格块

plugin client.persona()
  → hooks/persona.mjs renderPersona()
  → DSH systemPrompt
```

这是当前重复点：

- 服务已能返回 `system`
- 插件仍自己渲染
- 实际注入走插件

目标：插件只消费 `/hook/pre-step` 的 `system`。

---

## 6. B 站自主工作流

### 6.1 触发

`bridge.autonomy_loop`：

- 启动等 30 秒
- 每 5 分钟检查
- enabled
- 静默 0–8
- 每天最多 `daily_max`（默认 16）
- 距上次 ≥ `min_gap_minutes`（默认 25）

### 6.2 选题

`qqbot/domains/autonomy/bili.py :: pick_topic`

- 最近 2 个话题排除
- 按兴趣权重加权
- `free_explore_ratio`（默认 0.4）概率自由探索

### 6.3 看视频

`qqbot/domains/autonomy/round.py`

1. 拉推荐流
2. 排除已看 BV
3. 在 DSH 活动会话里让模型调用：
   - `bili_search`
   - `bili_subtitle`
   - `bili_frames`
   - `bili_transcribe`
4. 模型输出：
   - 主题
   - 视频列表
   - 想法

工具本身来自 `dsh-bili-scroll`，不是本仓库实现。

### 6.4 判断分享

同一轮再问一次：

- 要不要说
- `why_now`
- `line`
- `links`

不分享就只留记录。

### 6.5 落库

- 每次写 `bili-autonomy/out/YYYY-MM-DD.md`
- 分享时写 L0
- 想法写 L3
- 活动写 activity
- 自由探索发现新主题 → `apply_interest(..., +0.2)`

### 6.6 兴趣反馈

用户回复分享后：

`bridge.record_share_feedback`

- 不感兴趣/别发 → -0.8
- 短确认 → 0
- 提问/延伸 → +1.5
- 正常回应 ≥6 字 → +0.5

反馈写回兴趣权重。

---

## 7. 群聊和主动工作流

### 7.1 私聊主动

`bridge.proactive_loop`：

- 25–50 分钟随机
- 静默 0–8
- 让 DSH 生成
- SKIP 不发

### 7.2 群主动

`qqbot/domains/group/proactive.py`：

- 180–360 分钟
- 空闲 60 分钟
- 每天最多 1 次
- SKIP 不发

### 7.3 群接话

`bridge.handle` / `schedule_flush`：

- @ 或叫名字 → 必接
- 正在跟聊 → 接
- 否则：
  - 插话概率 0.10
  - 不插话就跳过
  - 群体门控概率 0.45
  - 话题相关性兜底

### 7.4 QQ 空间

`qqbot/domains/qzone/publish.py`：

- 每天 1 条
- 间隔 6 小时
- 静默 0–8
- 好友可见
- 禁止链接/私密词/广告

---

## 8. 状态文件

| 路径 | 内容 |
| --- | --- |
| `$DSH_HOME/persona-reflect/state.json` | 复盘时间 |
| `$DSH_HOME/persona-roles/state/profile-refresh-state.json` | 画像时间 |
| `$DSH_HOME/persona-roles/state/style-review-state.json` | 风格复盘时间 |
| `$DSH_HOME/persona-roles/state/style-proposal.json` | 待确认风格 |
| `$DSH_HOME/important-check-state.json` | 重要的事小时槽 |
| `$DSH_HOME/emotion-check-state.json` | 情绪自检时间和次数 |
| `$DSH_HOME/bili-autonomy/state.json` | 自主刷轮次/分享 |
| `$DSH_HOME/bili-autonomy/interests.json` | 兴趣权重 |
| `$DSH_HOME/bili-autonomy/seen.json` | 已看 BV |
| `$DSH_HOME/hook-events.jsonl` | hook 观测 |

---

## 9. 设计不变量

- L0 完整保留，不先摘要
- 存储裸文本，注入时才加“你记得”
- 第一人称视角：自己用“我”，主人称“主人/你”
- 不用向量单独断言“我记得”
- 召回只取当前 scope + global
- 人格写入必须经过服务，不直接改库
- 风格只生成提议，不自动应用
- 重要的事有上限，不无限堆
- 自动任务失败不推进状态，下次重试
- 记忆工作流目前部分在 service、部分在 bridge；边界见 `architecture.md` 5.4
