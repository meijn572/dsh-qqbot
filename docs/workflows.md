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
- tiers：L1/L3

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

不是“把所有记忆都塞进去”，而是按块注入：

| 注入块 | 内容 | 来源 | 时机 |
| --- | --- | --- | --- |
| system prompt | 人格、画像、L4 关系约定 | 插件 `client.persona()` + `client.profile()` → `renderPersona()` | 每次组装 system prompt（每个 model step） |
| person | 当前发言人、群友画像、非主人提示 | 插件 `client.profileOf()` → `/profiles` | 每个 model step 前 |
| outbound | 桥接主动发出的私聊/群消息、报告、B 站分享 | 插件 `client.outbound()` → `/outbound` → `createAssistantMessage` | 当前 user 消息之前，按 L0 id 只补一次 |
| recall | L1 事实、L3 事件 | 插件 `hooks/recall.mjs` → `/hook/pre-step` | 每个 model step 前 |
| state | 时间、心情、活动、B 站状态、黑话、关系阶段、颜文字/emoji | 插件 pre-step → `/state` | 每个 model step 前，变化才注入 |
| bridge-note | 表情库提示、群黑话、B 站链接、网络梗、图片/表情路径 | `bridge.py :: _process_locked` | 用户消息进入 DSH 前 |

L4 不再走 profile 块，也不参与 recall。L4 作为「关系约定」进 system prompt。

#### recall 参数

`service/api/routes/hooks.py :: pre_step()`：

| 参数 | 值 |
| --- | --- |
| query | 最近几条 user/assistant，最多 1000 字 |
| tiers | `L1`、`L3` |
| 配额 | `L1=25`、`L3=15`，按层后置截断 |
| scope | 当前会话 + `global` |
| max_chars | 6000 |
| purpose | `recall` |
| 排序 | BM25 + 向量 + 层权重 + 时间衰减 |
| 格式 | `[L1 · 事实] ...` / `[L3 · 事件 · 08-12 20:00] ...` |

不含 L2，也不含 L0。不是固定取满，相关性不够会少取或 0 条。

> 已知隐患：L0 有 private/group scope，但当前 L1/L2/L3/L4 都写成 `global`，私聊蒸馏内容可能被群聊 recall 到。等需要严格隔离时再修，见 `architecture.md` 12。

#### L2 / L0 去哪了

| 层 | 是否进 recall | 实际用途 |
| --- | --- | --- |
| L2 | 否 | 只通过人格 system prompt 的 `user_profile` 注入；仍供画像刷新、面板、fallback |
| L0 | 否 | 批量蒸馏 L1、复盘/画像/情绪/重要的事的最近上下文、面板 |

正常聊天不注入 L0，因为会话上下文已经提供原话，重复注入会浪费 token。

#### 不注入什么

| 不注入 | 原因 |
| --- | --- |
| 数据库 id、检索分数、hook 日志 | 内部信息 |
| 别的私聊 scope | 隐私隔离 |
| 未映射 `global` 会话的召回 | 避免私人记忆泄漏 |
| 内部维护提示、JSON、工具日志 | 不是对话内容 |
| emotion_log / important_check 中间状态 | 只保留结果 |

#### 当前遗留重复

| 块 | 当前状态 | 目标 |
| --- | --- | --- |
| L2 | 已从 recall 移除 | 人格画像唯一来源 |
| L4 | 已从 profile/recall 移除 | system prompt「关系约定」 |
| 人格 system prompt | 服务返回 `system`，插件仍自己渲染 | 插件改为消费服务 `system` |

当前实际注入：

```
插件渲染的人格块（含 L4）
  + person
  + 服务返回的 recall（L1/L3）
  + 插件状态块
  + bridge-note
```

不是服务返回的 `system`。

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

面板可以手动编辑 `self_model` 和 `user_profile`：

```
POST /api/persona/field
  {"field":"self_model","text":"..."}
  {"field":"user_profile","text":"..."}
```

分别写服务 `/persona/self` 和 `/persona/user`，不会改核心设定。

#### growth 的记忆输入

先统一几个说法：

| 名称 | 实际层 | 获取方式 | 说明 |
| --- | --- | --- | --- |
| 最近对话 | L0 | `recent_dialogue()` / `l0_recent()` | 补最新，条数按任务 |
| 长期记忆 | L1 + L3 | `/context/evidence` | 蒸馏后的 L1/L3，配额按任务 |
| 对应原话 | L0 | `/context/evidence` 的 `l0` | 由 L1/L3 的 `source_ids` 展开，按 id/文本去重 |
| 完整人格 | persona | `/persona/context` | 核心设定、自我认知、身份、形象、画像 |

注意：

- 长期记忆不含 L0、L2、L4
- L0 分两部分：最近对话补最新，对应原话做证据
- L2 画像已经在完整人格的 `user_profile` 里，不再重复取
- L4 关系约定已经在 system prompt 里，不再重复取
- 长期记忆与对应原话组成一个证据块，总长最多 16000 字，超了截断

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

| 输入 | 层 | 量 |
| --- | --- | --- |
| 完整人格 | persona | `/persona/context` |
| 最近对话 | L0 | 30 条，补最新 |
| 长期记忆 | L1/L3 | L1 50 / L3 30 |
| 对应原话 | L0 | 50 条，来自 L1/L3 的 source_ids |

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

| 输入 | 层 | 量 |
| --- | --- | --- |
| 完整人格 | persona | `/persona/context` |
| 最近对话 | L0 | 20 条，补最新 |
| 长期记忆 | L1/L3 | L1 50 / L3 30 |
| 对应原话 | L0 | 50 条，来自 L1/L3 的 source_ids |

要求：

- 300–600 字
- 用第二人称“你”称呼主人，每条都带“你/你的”，不写无人称条目，也不写成“我”或“他”
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

输入：

| 输入 | 层 | 量 |
| --- | --- | --- |
| 完整人格数据 | persona | `/persona` |
| 完整人格文本 | persona | `/persona/context` |
| 当前风格段 | constitution | `<!-- style:begin -->` 到 `<!-- style:end -->` |
| 最近对话 | L0 | 60 条，主样本 |
| 长期记忆 | L1/L3 | L1 30 / L3 20 |
| 对应原话 | L0 | 30 条，来自 L1/L3 的 source_ids |

不是只看“当前风格”这一小段；完整人格、最近相处和长期记忆都在输入里。

要求：

- 4–10 条短句
- 120–500 字
- 只改真正有变化的
- 不新增身份/事实/关系
- 输出 JSON：`{"style":"...","reason":"..."}`

为什么输出比复盘/画像短：

- 复盘改的是「自我认知」，400–900 字
- 画像改的是「我眼中的主人」，300–600 字
- 风格只改「表达风格」这一小段，120–500 字是刻意的
- 输入不寒酸，输出范围小是因为职责小

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

- 完整人格（`/persona/context`）
- 当前 important 段
- 最近 L1 15 条、L3 10 条
- 这些 L1/L3 引用的 L0 原文（按 id 去重，最多 50 条，单条截 400 字）

L3 的 `source_ids` 指向 L1，所以要先展开 L3 → L1 → L0；L1 直接指向 L0。L1 和 L3 引用同一句原话时只保留一次。

接口：

```
POST /context/evidence
```

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

输入：

| 输入 | 层 | 量 |
| --- | --- | --- |
| 完整人格 | persona | `/persona/context` |
| 最近对话 | L0 | 40 条 |
| 长期记忆 | L1/L3 | L1 20 / L3 10 |
| 对应原话 | L0 | 20 条，来自 L1/L3 的 source_ids |

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

### 5.7 日记

文件：`qqbot/domains/growth/diary.py`

触发：

```
bridge 启动 growth_diary.loop
  - 23 点后
  - 每 15 分钟检查一次
  - diary-state.json 记录 last_date
```

执行：

```
POST /diary
  {"date":"YYYY-MM-DD"}
```

输入：

- 完整人格（`/persona/context`）
- 当天 L0 原话，保留「主人：」「我：」标签和时间顺序
- 当天活动时间线
- 用当天内容做 query，召回 L1/L3 旧记忆（最多 8/6 条，3000 字）
- 只取当天最活跃的 private scope + global，避免串会话

服务端用这些素材生成一篇第一人称日记，写入 `diary` 表。提示词明确要求：按原顺序理解，不要把主人做的事写成自己做的，也不要把自己说的话写成主人说的。旧记忆只在对得上时自然联想，不强制每篇都回忆。

读取：

- 面板「小本子」
- 鱼主动调用 `read_diary`
- `read_diary date=YYYY-MM-DD` 可看某天

之前日记一直没写，是因为：

- `scheduler._tick_diary` 只在 23 点写一条 **silent** 唤醒事件
- `bridge.inject_watch` 明确跳过 silent 事件
- 插件也没有 `write_diary` 工具

所以“提醒”发出来了，但没人真正写。

### 5.8 人格注入

当前：

```
service /persona/context
  → 纯文本人格块

plugin client.persona()
  → hooks/persona.mjs renderPersona()

plugin client.profile()
  → persona.l4
  → renderPersona() 的「关系约定」段
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
- 活跃 10–23 点
- 时段上限：
  - 10–13 点最多 2 轮
  - 13–18 点最多 4 轮
  - 18–23 点最多 4 轮
- 每轮间隔随机 35–90 分钟
- 开始后第一轮随机延迟 0–35 分钟
- 每天最多 `daily_max`（默认 16，实际受时段上限约束）

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
   - 这轮看了几帧 `frames`
   - 想法

抽帧策略：

- 不固定 3 帧
- 按时长和内容判断
- 短视频少量看
- 长视频先从字幕找关键时间点，用 `bili_frames` 的 `at` 定点看
- 纯口播/有字幕且画面不重要可以不抽
- 不限制总帧数，但每帧要有理由；单次工具最多 6 帧，需要更多就分次看关键段

工具本身来自 `dsh-bili-scroll`，不是本仓库实现。

### 6.4 判断分享

同一轮再问一次：

- 要不要说
- `why_now`
- `line`
- `links`

不分享就只留记录。

### 6.4.1 连续分享没人回

默认连续分享 2 条主人都不回：

- 不再继续发
- 后续想分享的内容写进 `state.json` 的 `pending_shares`
- 最多攒 5 条

主人回消息后：

- `unanswered_shares` 归零
- 不立刻补发
- 等主人空闲 `deferred_min_idle_minutes`（默认 30 分钟）后的下一轮，再补一条攒下的分享
- 补发也计入当天分享数

正常新分享也要主人空闲 `share_min_idle_minutes`（默认 20 分钟），否则先攒着，避免打断正在聊的话题。

配置：

```
bili_autonomy.max_unanswered_shares   # 默认 2
bili_autonomy.pending_share_max       # 默认 5
bili_autonomy.deferred_share_hours    # 默认 6
bili_autonomy.deferred_min_idle_minutes # 默认 30
bili_autonomy.share_min_idle_minutes   # 默认 20
```

效果：

```
8:00 发一条 → 没回
8:25 发一条 → 没回
8:50 想发 → 攒着，不发了
...
11:00 主人回消息
11:05 想补发 → 主人才刚回，先不补
11:30 之后 → 补一条
```

### 6.4.2 主动发出的话进入上下文

桥接主动发出的内容都会写 L0，并带：

```json
["raw", "outbound"]
```

包括：

- 私聊主动
- 报告推送
- B 站分享
- 群主动

插件 pre-step：

1. 调 `/outbound?scope=当前scope`
2. 取最近 5 条未注入过的
3. 用 `createAssistantMessage` 构造 **assistant 消息**
4. 插到当前 user 消息之前
5. 每个进程内按 L0 id 去重，只补一次

所以模型看到的是：

```text
assistant: 刚刷到一个视频……
user: 这个不错
```

不是把分享塞进 user 的 bridge-note。

注意：这是每轮临时注入，不写进 DSH session log；补过一次就停。

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
| `$DSH_HOME/diary-state.json` | 最近一次成功写日记的日期 |
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
