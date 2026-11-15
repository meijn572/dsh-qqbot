# 接口契约

写于 2026-11-15。阶段一的产出。

这份文档定义**谁调谁、传什么、返回什么**。
看完应该能判断某段代码该放哪，不需要再问。

对应计划见 [refactor-plan-2026-11.md](refactor-plan-2026-11.md)。

---

## 一、三个进程，只有后端对外

```text
桥接 bridge.py      不对外，只连 OneBot
插件 dsh-remembers  不对外，只连 DSH 和后端
后端 service        对外暴露 HTTP，是唯一有接口的一方
```

**只有后端需要定义接口。** 桥接和插件都是调用方，它们自己不提供接口。

这简化了很多事：接口清单就是后端的路由表。

---

## 二、后端接口分三类

```text
读写原语    /ingest /search /memories /diary …     已有
素材配方    /input/<recipe>                        已有
任务执行    /task/<name>                           阶段二新增
```

### 为什么分这三类

```text
读写原语   不带判断，纯存取
素材配方   取数 + 渲染，不调模型。可以随便调，无副作用
任务执行   会调模型、会写库。要节流、要锁
```

**调用方能选轻的就别选重的。** 比如只想看看模型会收到什么，调 `/input/diary`，
不要调 `/task/diary`（后者会真的写日记）。

---

## 三、接口清单

### 3.1 读写原语（已有，不改）

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| POST | `/ingest` | 写一条记忆 |
| POST | `/search` | 检索 |
| GET | `/memories` | 列表（tier/q/limit/offset） |
| GET | `/diary` | 日记列表 |
| POST | `/diary` | 写日记（`dry_run: true` 只调模型不落库） |
| GET | `/persona` | 人格（含渲染好的 text） |
| POST | `/persona` | 改人格 |
| GET | `/state` | 运行时状态（含渲染好的 render 块） |
| POST | `/state` | 改状态 |
| POST | `/activity` | 活动日志 |
| GET | `/stats` `/health` | 统计 / 健康 |

### 3.2 素材配方（已有，不改）

```text
POST /input/<recipe>
```

| recipe | 产出 | 谁在用 |
| --- | --- | --- |
| `evidence` | L1/L3 + 原话 | 通用 |
| `diary` | 人格 + 昨天便签 + 相关旧事 + 前几天日记 | 写日记 |
| `review` | 人格(展开来源) + 5 天窗口 + 日记 | 人格复盘 |
| `style` | 人格 + 最近 + 证据(带原话) | 风格复盘 |
| `profile` | 人格 + 最近 + 证据 | 画像刷新 |
| `important` | 人格 + 证据 + 最近原话 | 重要事件 |
| `recall` | 带 query 的多层检索 | 对话、主动说 |
| `recent` | 最近 L0 | 会话重建 |
| `batches` | 按空闲切批的 L0 | 会话重建 |

**返回统一结构**：

```json
{
  "ok": true,
  "blocks": {"persona": "...", "evidence": "...", "diary": "..."},
  "text": "拼好的整块",
  "refs": ["L3:1459", "L0:1234"]
}
```

`blocks` 是分块给调用方挑，`text` 是全部拼在一起。
`refs` 是这条输入引用了哪些条目，人格条目挂来源时用。

**参数可覆盖**：

```json
POST /input/review
{
  "since": 1794500000,
  "until": null,
  "limits": {"L1": 300, "L3": 200, "quotes": false, "max_chars": 24000}
}
```

默认值在 `config.json` 的 `budget` 段，`limits` 只覆盖这次调用。

### 3.3 任务执行（阶段二新增）

```text
POST /task/<name>
```

| name | 做什么 | 写哪 |
| --- | --- | --- |
| `profile` | 画像刷新 | `persona.user_profile` |
| `style` | 风格复盘 | 人格「表现」节 |
| `important` | 重要事件检查 | 人格「重要的事」节 |
| `review` | 人格复盘 | 产出提案，等人确认 |
| `diary` | 写昨天的日记 | `diary` 表 |

**请求**：

```json
{ "dry_run": false, "limits": {...} }
```

**返回**：

```json
{
  "ok": true,
  "task": "profile",
  "changed": true,
  "usage": {"prompt": 12000, "cached": 11000, "completion": 800},
  "turns": 7,
  "result": {...}
}
```

**和 `/input/<name>` 的区别**：

```text
/input    只给素材，不调模型，无副作用，可以随便调
/task     调模型、写库、维护会话，有副作用，要节流
```

**会话管理**：

```text
每个 task 一个持久会话（task_session 表）
超过 30000 token 换新
超过 12 轮砍最早，保留最近 6 轮
同一个 task 加锁，不能并发
```

---

## 四、插件只调三类

```text
GET  /persona          →  hooks/persona.mjs  包成 <dsh-remembers source="persona">
GET  /state            →  hooks/state.mjs    包成 <dsh-remembers source="state">
POST /input/recall     →  hooks/recall.mjs   直接返回文本
POST /input/evidence   →  hooks/turn_end.mjs 落库前的素材
```

**插件不调 `/task/*`。** 任务是桥接或服务端调度层的事，插件只负责注入。

### 插件的工具注册

```text
tools/*.mjs 每个工具 10-30 行：解析参数 → 调后端 → 返回
不在本地做匹配、判断、状态管理
```

---

## 五、桥接调什么

```text
DSH 的 RPC            发消息、建会话、收回复
后端 /input/*         取素材（黑话匹配、ask_him、召回）
后端 /task/*          触发复盘（阶段三之后）
```

**桥接不直接读写 SQLite。**

---

## 六、数据流

### 一条用户消息

```text
OneBot
  ↓
桥接  去重、合并、决定要不要回
  ↓
DSH  插件注入人格+状态 → 召回 → 模型 → 工具调用
  ↓
桥接  气泡切分、发出去
  ↓
后端  /ingest 写 L0
```

### 一次日记（07:00）

```text
服务端 scheduler 触发
  ↓
后端 /task/diary
  ↓
inputs.run("diary")  取素材
  ↓
extractor.write_diary  调模型（带历史会话）
  ↓
diary_add  落库
```

### 一次人格复盘（5 天）

阶段三之前：

```text
桥接 persona_review_loop
  ↓
maintenance_turn（DSH 会话，缓存命中 90%）
  ↓
产出提案 → 面板确认
```

阶段三之后：

```text
服务端 scheduler 触发
  ↓
后端 /task/review
  ↓
inputs.run("review") → extractor 调模型（task_session，缓存命中）
  ↓
产出提案 → 面板确认
```

**两边行为一样，区别只是谁维护会话。**

---

## 七、判断"这段代码该放哪"的规则

### 三个问题

**一、它需要跨次记忆吗？**

```text
需要  →  DSH 会话（有历史、有缓存）
不需要 →  后端（无状态，每次都从素材重来）
```

**二、它需要调工具吗？**

```text
需要  →  DSH（只有它能调工具）
不需要 →  后端
```

**三、它独占什么资源？**

```text
SQLite       →  后端
DSH 注入点    →  插件
OneBot 连接   →  桥接
```

### 常见误判

```text
"复盘读的是记忆，所以该在后端"
  错在只看数据归属，没看执行特征。
  复盘输入长、频率低，正需要会话缓存。

"人格注入顺手在桥接拼一下就行"
  错在没看缓存。
  人格进 user 消息 = 每轮都变 = 前缀缓存全废。

"插件里算一下表情匹配更快"
  错在没看职责。
  匹配逻辑挪走后端，插件才能只剩下转发。
```

---

## 八、错误处理约定

```text
所有接口返回 {"ok": bool}
失败时带 {"ok": false, "error": "原因"}

/input/*     失败返回 ok:false + 空 blocks（调用方降级）
/task/*      失败返回 ok:false + error，调用方记录日志不重试
             重试由调度层按 next_run 决定
```

**不抛异常穿透协议层。** 服务端内部错误一律转成 `ok: false`。

---

## 九、还没定的

```text
一、/task/review 的产出格式（提案存哪、面板怎么读）
二、任务会话的裁剪策略细节（现在抄 DSH 的 30k / 12 轮）
```

这两条在阶段三会遇到，到时候补进这份文档。

### 曾经想加、后来否掉的

```text
原本想加 GET /prompt/common，让桥接拉跨进程共用的规则。

否掉的理由：那 96 字的 VOICE_RULE 拆开看，大部分不需要共享。

  「提示词里用『你』称呼你」        事实描述，删
  「对话里『我：』是你，『主人：』是九歌」 格式自解释，删
  「写出来用第一人称『我』」        产出要求，每个提示词开头加一句
  「『你』和『我』是同一个人」      防错，同上

真正起作用的不是「这个符号代表谁」，而是「别把谁的事写成谁的」。
后者依赖具体任务对「我做的」和「他做的」的定义，不同任务不一样，
本来就该跟着任务走，不是通用规则。
```
