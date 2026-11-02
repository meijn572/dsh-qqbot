# DSH QQ Bot 整改计划

> 状态：草案 v2（已完成主体重构）  
> 当前阶段：Phase 8 已完成，观察期  
> 下一步：观察真实 QQ 回合、面板、自主刷一天  
> 总结：[refactor-summary.md](refactor-summary.md)  
> 范围：`D:\QQBot\dshbot`、`C:\Users\12152\.dsh-qqbot\remembers-service`、`plugins\dsh-remembers`  
> 原则：不推倒重来；先清边界，再拆模块；每一步可回滚、可验证。

## 0. 非目标

本阶段不做：

- 不重写模型/人格内容
- 不改面板视觉设计
- 不换记忆数据库
- 不引入微服务/消息队列
- 不一次性删除所有旧目录
- 不保证每个模块完美，只保证边界正确、可回滚

---

## 1. 现状基线

### 1.1 体量

| 文件 | 行数 | 问题 |
| --- | ---: | --- |
| `bridge.py` | ~3400 | 网关、媒体、群聊、人格、自主刷、空间全在一起 |
| `service/server.py` | ~3200 | HTTP 路由和业务逻辑混在一起 |
| `plugin/index.mjs` | ~2000 | 人格、捕获、召回、工具、表情包混在一起 |
| `panel.py` | ~1200 | 后端 API 和前端 HTML/CSS/JS 混在一起 |

### 1.2 主要混乱

1. **bridge 不是桥**：它承担了半个应用。
2. **service 没有路由层**：一个 Handler 处理所有领域。
3. **panel 前端不可独立开发**：HTML/JS 是 Python 字符串。
4. **插件职责过多**：persona、capture、recall、tools 没有边界。
5. **遗留链路仍在**：
   - 旧 `memory/memory.db` 双写
   - `persona_apply.py` / 旧角色卡提案
   - `feiyu-mood`、`selfwake`、`memory-hygiene` 旧目录
6. **配置分散**：
   - `config.json`
   - `CMEM_*` 环境变量
   - 插件 `cordis.patch.yml`
   - 启动脚本里的端口/路径

### 1.3 已完成

- 记忆服务与桥接分离
- `/context`、`/persona/context` 统一注入接口
- 存储层去前缀，注入层统一人称提示
- `settings.py` 作为路径/端口/token 入口
- 清理 short-term、recent-summary、旧 section 提案链路

---

## 2. 目标架构

### 2.0 这次审视后的调整

相比上一版，主要改了六件事：

1. **不再叫 `bridge/`**
   整个应用叫 `qqbot/`；桥接只是 `adapters/onebot.py`。
2. **`domains/` 提到顶层**
   媒体、群聊、人格、自主、空间是产品能力，不属于 QQ 协议。
3. **新增 `contracts.py` / `ports.py`**
   跨层传 `InboundBatch`、`ReplyPlan`，不传 OneBot event 或裸 dict。
4. **`jobs/` 统一调度**
   不再每个领域自己 `while True`；统一注册、启停、状态。
5. **`panel/` 只读投影**
   面板不 import 业务，不直接写数据库；只读服务 API/状态文件。
6. **记忆服务按用例拆**
   routes 不写 SQL，`memory/context.py` 只做格式，`memory/batch.py` 只编排。

### 2.1 设计原则

1. **协议和业务分开**：OneBot/DSH 只是适配器，不懂人格、记忆、B 站。
2. **领域是产品能力，不是桥接子模块**：`media`、`group`、`persona`、`autonomy`、`qzone` 独立于消息通道。
3. **一个组装根**：只有 `runtime.py` 知道所有实现，其他模块只依赖接口。
4. **单向依赖**：adapter → conversation → domain → port；jobs 也走 domain/port。
5. **配置只在组装根和 settings**：业务模块不读环境变量、不拼路径。
6. **一个调度器**：所有定时任务注册到 `jobs/registry`，不再散落 `while True`。
7. **接口契约显式**：跨层用 dataclass/Protocol，不传 OneBot event 或裸 dict。

### 2.2 运行时调用关系

```
QQ / OneBot
   │
   ▼
adapters/onebot            收消息、解析成 InboundBatch
   │
   ▼
conversation               合并、门控、决定回不回
   │
   ├── domains/media       看图、收表情包
   ├── domains/group       群黑话、接话判断
   ├── clients/memory      召回/写入记忆
   └── clients/persona     人格段
   │
   ▼
ports/outbound             OutboundPort
   │
   ▼
adapters/onebot            发回 QQ

jobs/registry              定时触发
   ├── domains/growth      复盘、画像、风格
   ├── domains/autonomy    B 站、分享
   ├── domains/qzone       空间
   └── domains/group       群主动
```

`conversation` 只处理“这一批消息怎么回”，不负责“每天几点复盘”。

### 2.3 分层与目录对应

| 层 | 目录 | 职责 | 不允许 |
| --- | --- | --- | --- |
| 契约层 | `qqbot/contracts.py` | InboundBatch、OutboundMessage、ReplyPlan | 依赖任何实现 |
| 端口层 | `qqbot/ports.py` | OutboundPort、MemoryPort、PersonaPort | 依赖具体 adapter |
| 适配层 | `qqbot/adapters/` | OneBot / DSH RPC | 写业务逻辑 |
| 编排层 | `qqbot/conversation/` | 合并、门控、回复 | 直接操作数据库 |
| 领域层 | `qqbot/domains/` | 媒体、群聊、人格、自主、空间 | import adapter/conversation |
| 客户端层 | `qqbot/clients/` | HTTP 调记忆/人格服务 | 拼 prompt、做业务判断 |
| 触发层 | `qqbot/jobs/` | 定时器、循环注册 | 内嵌大段业务 |
| 组装层 | `qqbot/runtime.py` | 实例化、注入、启动 | 被业务模块 import |

### 2.4 目标目录

```
D:\QQBot\dshbot\
  settings.py                 # 唯一配置入口：路径、端口、token、DSH_HOME
  qqbot/
    __main__.py               # 进程入口，只调 runtime.main()
    runtime.py                # 组装根：adapter/client/domain/jobs 装配
    contracts.py              # 跨层数据契约
    ports.py                  # Protocol 定义
    adapters/
      onebot.py               # OneBot WS/HTTP：连接、收发、重连
      dsh_rpc.py              # DSH RPC：cookie、会话、prompt、projections
      events.py               # OneBot 事件 → InboundBatch
    conversation/
      batch.py                # 防抖/合并：私聊 12s、群聊 20s
      gate.py                 # 回不回：私聊直回、群接话/跟进/插话/跳过
      reply.py                # ReplyPlan → OutboundMessage，分气泡/图片
    domains/
      media/
        download.py           # 下载图片/表情，识别真实格式，落 inbox
        stickers.py           # 表情包分类、去重、收藏、索引、[[meme]]
        vision.py             # 图片预处理、动图拼帧、原生附件、视觉兜底
      group/
        log.py                # 群消息日志
        slang.py              # 群黑话/网络梗读写与匹配
        proactive.py          # 群主动：时机、生成、发送、冷却
      growth/
        reflect.py            # 复盘：完整人格+最近对话+长期记忆 → 自我认知
        profile.py            # 用户画像刷新
        style.py              # 风格复盘提议
        important.py          # 重要的事抽取与同步
      autonomy/
        bili.py               # B 站浏览/字幕/转写
        share.py              # 选题、想法、分享文本、L0 写入
      qzone/
        publish.py            # QQ 空间发布与限制
    clients/
      memory.py               # 实现 MemoryPort：/context /ingest /memories /batch
      persona.py              # 实现 PersonaPort：/persona /persona/context
    jobs/
      registry.py             # 统一调度器：注册、启停、状态
      loops.py                # 各任务的薄封装
  panel/
    __main__.py               # 面板入口
    app.py                    # HTTP 生命周期、静态文件
    routes/                   # 每个领域一个 API 文件
      status.py
      memory.py
      persona.py
      media.py
      group.py
      bili.py
    readers/                  # 只读状态文件/服务投影
  web/
    index.html
    app.js
    style.css
  scripts/                    # 迁移、备份、smoke、一次性修复
  docs/
    refactor-plan.md
```

### 2.5 契约与端口

`contracts.py` 至少定义：

```python
@dataclass
class InboundMessage:
    chat_key: str          # private:123 / group:456
    user_id: int
    nickname: str
    text: str
    images: list[str]
    is_addressed: bool

@dataclass
class InboundBatch:
    chat_key: str
    messages: list[InboundMessage]
    merged_text: str
    images: list[str]

@dataclass
class OutboundMessage:
    chat_key: str
    text: str
    images: list[str]

@dataclass
class ReplyPlan:
    should_reply: bool
    messages: list[str]
    images: list[str]
    reason: str
```

`ports.py` 至少定义：

```python
class OutboundPort(Protocol):
    async def send(self, message: OutboundMessage) -> None: ...

class MemoryPort(Protocol):
    async def context(self, ...) -> str: ...
    async def ingest(self, ...) -> int | None: ...

class PersonaPort(Protocol):
    async def context(self) -> str: ...
```

领域只依赖这些 Protocol，不依赖 OneBot 客户端。

### 2.6 记忆服务目标目录

```
remembers-service/
  app.py                      # HTTP 生命周期、CORS、异常兜底
  api/
    routes/
      memory.py               # /ingest /search /context /memories /forget
      persona.py              # /persona /persona/self /persona/user /persona/important
      profiles.py             # /profiles /affinity /guests
      activity.py             # /activity /notes /tasks /diary
      proactive.py            # /proactive
      bili.py                 # B 站工具
      batch.py                # /batch/run
  memory/
    store.py                  # 表、读写、衰减、索引
    retrieval.py              # BM25/向量/融合
    context.py                # 统一记忆块格式
    extractor.py              # 抽取、判定、事件压缩、规则提炼
    batch.py                  # L0→L1→L3→L4 编排
  persona/
    store.py                  # persona 字段
    profile.py                # 画像生成
    context.py                # 人格块格式
  activity/
    store.py                  # 活动、便签、任务、日记
  proactive/
    scheduler.py              # 唤醒调度，写 qq-inject
  bili/
    client.py                 # B 站接口
  runtime.py                  # 组装 store/LLM/线程
```

依赖方向：

```
routes → memory/persona/activity → store
routes 不写 SQL
store 不拼 prompt
context 只做格式
```

### 2.7 插件目标目录

```
plugins/dsh-remembers/
  index.mjs                   # bootstrap：注册 hooks/tools、读配置
  config.mjs                  # 配置解析
  client.mjs                  # 服务 HTTP 客户端
  hooks/
    pre_step.mjs              # 取消息 → /hook/pre-step → 注入 system/recall
    turn_end.mjs              # 取 user/assistant → /hook/turn-end
  tools/
    emotion.mjs               # schema + 转发
    important.mjs
    activity.mjs
    memes.mjs
    tasks.mjs
    bili.mjs
```

插件最终只做 DSH 适配：

- 不构造召回 query
- 不判断 surprisal
- 不决定 L0 写不写
- 不拼人格段
- 不拼记忆格式

插件不再自己拼记忆格式，不再自己维护第二套短时缓冲。

### 2.8 数据与脚本

```
C:\Users\12152\.dsh-qqbot\
  remembers-data/
    memories.db               # 主记忆库
    config.json               # 服务端配置
  important/
    important.md              # 手写重要的事，60s 同步
  group-log/                  # 群消息日志
  group-slang/                # 提取出的群黑话
  persona-roles/              # 旧角色卡，只读归档
  bili-autonomy/              # 兴趣、已看、分享状态
  sessions/                   # DSH 会话
  logs/                       # 日志
  backups/                    # 数据库/配置备份
```

`scripts/` 只放迁移、备份、smoke、一次性修复；不放常驻业务。

### 2.9 依赖方向

```
adapters ──► contracts
adapters ──► conversation ──► domains
                         └──► ports
clients ──► ports
jobs ──► domains / ports
runtime ──► 全部
panel ──► 记忆服务 HTTP / readers
plugin ──► 记忆服务 HTTP
```

禁止：

- `domains` import `adapters` / `conversation` / `jobs`
- `clients` import `domains`
- `panel` import `qqbot` 业务
- `contracts` import 任何实现
- 业务模块读环境变量或拼用户路径

### 2.10 迁移策略

`bridge.py` 不直接删，先变成兼容壳：

```python
# bridge.py
from qqbot.runtime import main
if __name__ == "__main__":
    main()
```

然后按领域迁：

1. 新代码只进 `qqbot/`
2. 旧 `bridge.py` 保留入口和未迁函数
3. 每迁一个领域，旧函数改为调用新模块
4. 全部迁完后删除 `bridge.py`

这样启动脚本、看门狗、面板不需要跟着改。

### 2.11 为什么 remember 独立，persona 在内

这里有三个不同的“persona/remember”，不能混为一谈。

#### 1. `dsh-remembers` 插件 = DSH 宿主适配器

它必须独立，因为只有插件能拿到 DSH 的：

- `systemPrompt`
- `agent/pre-step`
- `turn/end`
- 工具注册

桥接只看得到 QQ 消息，看不到 DSH 一轮完整的 user/assistant 和工具调用。
所以 L0 捕获、召回注入、`set_emotion` 这类工具必须留在插件里。

它不拥有记忆，只负责“在 DSH 生命周期里插一脚”。

#### 2. 记忆服务 = 存储与检索

独立进程，拥有：

- `memories.db`
- L0–L4
- `/context`
- `/persona/context`

插件、桥接、面板都通过 HTTP 访问它，避免各自读库。

#### 3. `qqbot/domains/growth` = 成长工作流

它是**定时任务**，不是每轮对话的一部分：

- 人格复盘
- 画像刷新
- 风格提议
- 重要的事

这些任务需要 DSH 的维护会话做 LLM 调用，但不需要挂在每轮消息链上。
放在 `qqbot/domains/` 是因为它们由 `jobs/` 触发，属于应用层编排。

#### 为什么不是全部塞进插件或服务

| 方案 | 问题 |
| --- | --- |
| 全塞插件 | 插件变成应用；定时任务、B 站、面板都要进 DSH |
| 全塞服务 | 服务需要 DSH RPC、维护会话、群聊状态，变成第二个桥接 |
| 当前拆分 | 插件只管宿主钩子，服务只管存储，qqbot 管编排 |

#### 命名建议

为了减少歧义，目标目录里建议改名：

```
qqbot/domains/growth/    → 复盘、画像、风格、重要的事
service/persona/         → 人格存储与格式
plugin/persona.mjs       → 人格提示词适配
```

“persona”只保留给存储和提示词；复盘/画像/风格叫 `growth`。

#### 如果以后要更一致

可以把 `growth` 工作流也搬进服务，qqbot 只留一个触发接口。
代价是服务要拿到 DSH 会话能力；目前没必要，先保持现状。

### 2.12 一次调用的运行流

以一条私聊消息为例。

```
QQ
 │
 ▼
adapters/onebot          收 event，解析 InboundMessage
 │
 ▼
conversation/batch       防抖合并，形成 InboundBatch
 │
 ▼
conversation/gate        私聊直回；群聊判断接不接
 │
 ▼
domains/media            图片下载、表情识别、原生附件
 │
 ▼
conversation/reply       组装文本 + 附件
 │
 ▼
adapters/dsh_rpc         session/prompt
 │
 ▼
DSH 进程
 ├─ pre-step：人格段 + /context 召回
 ├─ 模型生成（可调工具）
 └─ turn/end：surprisal 门控 → 写 L0
 │
 ▼
adapters/dsh_rpc         wait_reply
 │
 ▼
conversation/reply       分气泡、[[meme]] 转图
 │
 ▼
ports/outbound → adapters/onebot → QQ
 │
 ▼
（异步）jobs/loops → /batch/run → L1/L3/L4
```

#### 同步链路

| 步骤 | 模块 | 动作 | 写入 |
| --- | --- | --- | --- |
| 1 | `adapters/onebot` | 收消息、重连、heartbeat | 无 |
| 2 | `adapters/events` | 解析 chat_key/文本/图片/@ | 无 |
| 3 | `conversation/batch` | 12s/20s 合并 | pending |
| 4 | `conversation/gate` | 私聊直回；群聊接话/插话/跳过 | 无 |
| 5 | `domains/media` | 下载、格式识别、表情判断 | inbox/索引 |
| 6 | `adapters/dsh_rpc` | 找/建 session，发 prompt | 无 |
| 7 | 插件 pre-step | 人格 + `/context` 召回 | 无 |
| 8 | DSH 模型 | 生成回复、调工具 | 工具自己的写入 |
| 9 | 插件 turn/end | surprisal → `/ingest` L0 | L0 |
| 10 | `adapters/dsh_rpc` | 取最终回复 | 无 |
| 11 | `conversation/reply` | 分气泡、表情转图 | 无 |
| 12 | `adapters/onebot` | 发回 QQ | 无 |

#### 异步链路

| 任务 | 触发 | 输入 | 输出 |
| --- | --- | --- | --- |
| L1 | 每 6 条 L0 或空闲 15 分钟 | L0 批次 | L1 事实 |
| L3 | 每 6 条 L1 | L1 + 对应 L0 | L3 事件 |
| L4 | 每天 | 最近 L1/L3 + 现有 L4 | L4 规则 |
| 人格复盘 | 每 8 小时 | 完整人格 + 最近 80 条 + L1–L4 | 自我认知 |
| 画像 | 每 2 天 | 完整人格 + 最近 60 条 + L1–L4 | 用户画像 |
| 风格 | 每 3 天 | 完整人格 + 最近对话 + 记忆 | 待确认提议 |
| 重要的事 | 每天 2 次 | 原话 + 已有重要的事 | 核心设定段 |

#### 群聊 / 主动

- 群聊多一步 gate 和群黑话注入，其余相同。
- 被跳过时整条链不启动，不写 L0。
- 主动说话、B 站自主刷走 `jobs`，不经过入站消息链。
- 主动说出的话补 L0；浏览过程只写活动日志。

#### 失败边界

| 故障 | 行为 |
| --- | --- |
| 表情分类超时 | 不阻塞回复 |
| 图片视觉超时 | 先按当前画面理解 |
| 召回失败 | 不注入记忆，照常回复 |
| DSH 超时 | 回一句“卡了一下” |
| 记忆写入失败 | 不阻塞回复 |
| 批量蒸馏失败 | 下个周期重试，L0 不丢 |

---

## 3. 配置与数据

### 3.1 配置唯一入口

`settings.py` 负责：

- `BOT_DIR`
- `DSH_HOME`
- `WORKSPACE`
- `CMEM_BASE`
- `PANEL_PORT`
- token 路径
- 状态文件路径

只允许组装根和入口 import：

```python
# qqbot/runtime.py、panel/app.py、scripts/*
from settings import CONFIG, DSH_HOME, CMEM_BASE
```

业务模块（`conversation` / `domains` / `clients`）不允许 import settings；
需要配置时由 `runtime.py` 注入。

配置归属：

| 配置 | 文件 | 所有者 |
| --- | --- | --- |
| QQ/DSH/面板/路径 | `D:\QQBot\dshbot\config.json` | `settings.py` |
| 记忆/人格/批量/主动 | `~/.dsh-qqbot/remembers-data/config.json` | 记忆服务 |
| 插件开关/服务地址 | `profiles/qqbot2/cordis.patch.yml` | DSH 插件 |

环境变量只做覆盖，不做第二套默认值。

### 3.2 数据目录

代码和运行数据分离：

```
D:\QQBot\dshbot\              代码
C:\Users\12152\.dsh-qqbot\    运行数据
  remembers-data/
    memories.db
    config.json
  important/
  group-log/
  group-slang/
  bili-autonomy/
  sessions/
  logs/
  backups/
```

迁移时保留旧路径只读兼容，不再新增写入。

### 3.3 旧数据处置

| 数据 | 处置 |
| --- | --- |
| `memory/memory.db` | 迁移兴趣提取后停止双写，保留备份 |
| `persona-roles/roles/小肥鱼.md` | 只读归档，不再作为人格源 |
| `feiyu-mood` | 评估后归档 |
| `selfwake` | 评估后归档 |
| `memory-hygiene` | 合并到新清理任务后归档 |

---

## 4. 分阶段计划

### Phase 0：保护网

目标：改之前先能发现坏。

- [x] 增加 `scripts/smoke.py`：检查 8081/60773/6080、`/persona/context`、`/context`、面板 API
- [ ] 增加 `pytest`（待补）：
  - `memory/store` 基础 CRUD
  - `extractor.extract_batch`
  - `/context` 分层/配额/scope
- [x] 固化备份：`scripts/backup_state.py` + `backups/refactor-phase0-*`
  - `memories.db`
  - `config.json`
  - 插件 `index.mjs`
- [x] 写回滚步骤到本文档

验收：一条命令能跑完 smoke；失败能指出具体服务。

### Phase 1：配置收口 + qqbot 骨架

目标：路径/端口只有一个来源，并建立不改变行为的 `qqbot/` 骨架。

- [x] 新增 `settings.py`
- [x] bridge/panel 改用 settings
- [x] 去掉 bridge/panel 中硬编码用户路径
- [x] 新建 `qqbot/`：`__main__.py`、`runtime.py`、`contracts.py`、`ports.py`
- [ ] `bridge.py` 变成兼容壳：只转发到 `qqbot.runtime.main()`
- [x] 启动脚本改用 settings 的端口
- [ ] 服务端配置统一为 `remembers-data/config.json`
- [ ] 插件 `cordis.patch.yml` 只保留服务地址和功能开关

验收：启动方式不变；smoke 全过；`bridge.py` 不再新增业务。

### Phase 2：拆 media

目标：图片/表情包从旧入口抽离，行为不变。

- [x] 新建 `qqbot/domains/media/`
- [x] 迁移 `vision_image` / `native_image` 到 `preprocess.py`
- [x] 迁移：
  - 图片下载 → `download.py`
  - 表情包分类/收集 → `vision.py` / `stickers.py`
  - 索引/元数据/`[[meme]]` → `library.py`
- [x] `bridge.py` 只保留调用
- [ ] 为 `split_bubbles`、表情选择增加单测
- [x] Phase 2 单测：`tests/test_media.py`
  - 静态图预处理
  - GIF 拼帧
  - 大图压缩
  - 本地图片下载
  - 表情关键词
- [x] 固定检查：`scripts/check.ps1`（unittest + smoke）

验收：发图、发表情包、自动收藏、面板表情页全部正常。

### Phase 3：拆 growth

目标：人格复盘、画像、风格、重要的事各自独立。

- [x] 新建 `qqbot/domains/growth/`
- [x] 迁移：
  - `reflect.py`：人格复盘
  - `profile.py`：画像刷新
  - `style.py`：风格提议
  - `important.py`：重要的事自检 + 文件同步
  - `emotion.py`：情绪自检
- [x] 统一通过 `clients/persona.py`、`clients/memory.py`
- [x] 检查循环依赖：growth 不 import bridge
- [x] 移除旧 `collect_important` / 角色卡重要的事双写
- [x] Phase 3 单测：`tests/test_growth.py`
- [ ] 手动触发一次真实复盘/画像（LLM 端到端）

验收：手动触发一次复盘、画像、风格提议、重要的事均成功。

### Phase 4：拆 group / autonomy

- [x] `qqbot/domains/autonomy/state.py`：兴趣、已看、运行状态、similar_topic
- [x] `qqbot/domains/autonomy/bili.py`：feed/view、pick_topic、apply_interest、compose_share
- [x] `qqbot/domains/autonomy/interests.py`：兴趣提取与合并
- [x] `qqbot/domains/autonomy/round.py`：自主刷轮次 + loop
- [x] `qqbot/domains/qzone/publish.py`：空间发布
- [x] Phase 4 单测：`tests/test_group.py`、`tests/test_phase4_extra.py`、`tests/test_autonomy.py`

验收：群聊接话、群主动、空间发布、B 站自主刷已迁移。

### Phase 5：拆 service 路由

- [x] `api/routes/memory.py`：ingest / search / forget
- [x] `api/routes/persona.py`：人格读写
- [x] `api/routes/read.py`：只读查询
- [x] `api/routes/get.py`：GET 分支
- [x] `api/routes/table.py`：POST 路由表
- [x] `Handler` 只做分发：GET/POST 已收口（health、packs 特例保留）
- [x] `context` / `persona` 格式逻辑进 `memory/context.py`、`persona/context.py`
- [x] 统一错误响应：`_handle` 兜底 + `_guard`
- [x] Phase 5 单测：smoke + 服务重启验证

验收：原有端点路径不变，返回结构不变。

### Phase 6：panel 前后端分离

- [x] `web/index.html`、`web/app.js`、`web/style.css`
- [x] `panel.py` 只做 HTTP 生命周期（64 行）
- [x] `panel_routes.py`：API 路由
- [x] `panel_readers.py`：只读投影/动作/服务访问
- [ ] 前端按 tab 拆模块
- [x] 保留现有 URL（新增 `/static/*`）
- [x] Phase 6 单测：面板 `/`、CSS、JS、API 200 + smoke

验收：面板所有 tab、按钮、编辑框正常。

### Phase 7：插件收薄（拆分 + hook 收口）

目标：插件只做 DSH 协议适配和 IO。
召回策略、写入策略、人格拼装全部进记忆服务；插件不再保留业务判断。

> 原来拆成 Phase 7（插件拆分）和 Phase 8（hook 收口）。
> 合并原因：Phase 8 会删掉 `capture.mjs` / `recall.mjs` / `persona.mjs` 里的大部分逻辑，
> 先按旧边界拆一遍再拆一遍是白做。直接按最终边界拆。

#### 7.1 最终边界

| 层 | 负责 |
| --- | --- |
| 插件 | DSH hook、消息提取、注入、tool schema 注册、HTTP 转发 |
| 记忆服务 | query 构造、召回决策、surprisal、L0 写入、人格块、工具实现 |
| 桥接 | 定时任务、群聊、自主刷、空间 |

插件最终目录：

```
plugins/dsh-remembers/
  index.mjs                   # bootstrap：注册 hooks/tools、读配置
  config.mjs                  # 配置解析
  client.mjs                  # 服务 HTTP 客户端
  hooks/
    pre_step.mjs              # 取消息 → /hook/pre-step → 注入 system/recall
    turn_end.mjs              # 取 user/assistant → /hook/turn-end
  tools/
    emotion.mjs               # schema + 转发
    important.mjs
    activity.mjs
    memes.mjs
    tasks.mjs
    bili.mjs
```

#### 7.2 新增接口

```http
POST /hook/pre-step
{
  "request_id": "...",
  "session": "session-...",
  "scope": "private:...",
  "messages": [...]
}
→ {
  "system": "人格段",
  "recall": "召回块"
}
```

```http
POST /hook/turn-end
{
  "request_id": "...",
  "session": "session-...",
  "scope": "private:...",
  "user": "...",
  "assistant": "..."
}
→ {
  "stored": true,
  "surprisal": 0.42
}
```

工具统一转发：

```http
POST /tool/set_emotion
POST /tool/remember_important
POST /tool/find_meme
```

#### 7.3 实施顺序

1. 服务端先加 `/hook/pre-step`、`/hook/turn-end` 和契约测试；旧插件不动
2. 插件加 feature flag，新旧路径双跑
3. 切换 pre-step / turn-end 到新接口
4. 工具实现改成转发
5. 删除旧 `capture.mjs` / `recall.mjs` / `persona.mjs` 及旧逻辑
6. 按 7.1 的最终目录拆 hooks/tools
7. 灰度一天，确认 fail-open

当前进度：

- [x] 服务端 `/hook/pre-step`、`/hook/turn-end`
- [x] smoke 覆盖两个 hook
- [x] `client.mjs` 增加 `hookPreStep` / `hookTurnEnd`
- [x] `config.mjs` 增加 `hooks` 开关（默认 false）
- [x] `index.mjs` pre-step 支持 hook 分支（开关关闭时走旧路径）
- [x] `index.mjs` turn-end 支持 hook 分支
- [x] 部署到 profile 并灰度（`CMEM_HOOKS=1`）
- [x] `cordis.patch.yml` 持久化 `hooks: true`，重启不再依赖环境变量
- [x] 修正：实际生效的是 profile patch `C:\Users\12152\.dsh-qqbot\profiles\qqbot2\cordis.patch.yml`
- [x] 启动日志确认 `config hooks=true`
- [x] 真实回合 `turn_end` 已走 hook，L0 `id=368`
- [x] 真实回合 `pre_step` 已出现：`recall_chars=4596`
- [x] 修掉未映射会话 `scope=global` 仍注入召回的泄漏：global 非 onebot 会话直接 return
- [x] 修掉 profile/person 注入提前 return 导致同轮召回被跳过：改成 `extra` 累积，最后合并注入
- [x] 真实 QQ `pre_step` 已确认：scope `private:1215258939`，`recall_chars=4197`
- [x] 删除旧 L0 capture fallback
- [x] 删除旧 recall fallback
- [x] 删除 `buildQuery` / `client.search/context/surprisal/ingest`
- [x] 拆 `hooks/recall.mjs`、`hooks/turn_end.mjs`
- [x] 拆 `tools/emotion.mjs`、`tools/important.mjs`
- [x] 拆 `tools/persona.mjs`、`activity.mjs`、`memes.mjs`、`companion.mjs`
- [x] 拆 `hooks/state.mjs`、`hooks/persona.mjs`（render 纯函数）
- [x] 删除 `registerBiliTools` 死代码（B 站工具组未启用）
- [x] `index.mjs` 只留 2 行导出，生命周期进 `app.mjs`
- [x] 真实 QQ 回合：`pre_step recall=4411`、`turn_end stored=true id=376`
- [x] Phase 7 完成（`app.mjs` 941 行，后续可继续拆细）
- [x] hook 写入实测：L0 写入 + `/forget` 清理通过
- [x] hook 召回实测：`system 1623` / `recall 1340`
- [ ] 工具实现改转发（现有工具已直连服务端点）
- [ ] 删除旧 capture/recall/persona
- [ ] 拆 hooks/tools 目录

#### 7.4 插件保留

- DSH hook 注册
- 从 DSH event 提取 user/assistant/session/scope
- 调 `/hook/*` 和 `/tool/*`
- 把返回的 system/recall 注入
- tool schema 定义（实现只转发）
- 服务不可用时 fail-open

#### 7.5 插件不再有

- 召回 query 构造
- recallTopK / 召回阈值
- surprisal 门控
- L0 是否写入的判断
- 人格段拼装
- 记忆格式 `[L1]...`

#### 7.6 测试

- `/hook/pre-step` 契约测试：有命中/无命中/服务失败
- `/hook/turn-end` 契约测试：写/不写/surprisal
- 服务关闭时插件不阻塞回复
- 同一 request id 能串起插件与服务日志
- DSH 重启后召回和 L0 正常
- 插件代码 grep：不出现 query 构造、surprisal 阈值、L0 写入判断

#### 7.7 风险

| 风险 | 处理 |
| --- | --- |
| 同步 HTTP 增加延迟 | 本地服务，设 2–3s 超时 |
| 服务挂掉阻塞聊天 | 插件 fail-open，直接返回空注入 |
| 人格段频繁请求影响缓存 | 服务端缓存 + 版本号 |
| hook DTO 升级不同步 | 契约测试 + 版本字段 |
| 合并阶段范围太大 | 按 7.3 分 7 个小步，每步可回滚 |

验收：插件只依赖 DSH API 和本地 HTTP；业务策略只存在于记忆服务。

### Phase 8：清遗留


- [x] 删除旧 `memory.db` 双写
- [x] 兴趣提取改读服务 L1
- [x] 删除旧 `persona_apply.py` 路由
- [x] 归档 `feiyu-mood`、`selfwake`、`memory-hygiene`
- [x] 更新文档和启动脚本

验收：全库搜索无旧路径；smoke + 一天观察无异常。

---

## 5. 每阶段验收模板

### 5.1 固定命令

每个 Phase 结束必须跑：

```powershell
powershell -ExecutionPolicy Bypass -File D:\QQBot\dshbot\scripts\check.ps1
```

包含：

1. `python -m unittest discover -s tests`
2. `python scripts/smoke.py`

没跑过这两项，不算完成。

### 5.2 改动说明模板

每个 PR/改动必须写：

```markdown
### 改了什么
- …

### 怎么验证
- [ ] check.ps1
- [ ] 本阶段单测
- [ ] 手动路径

### 回滚
- 备份文件：
- 回滚命令/步骤：

### 风险
- …
```

---

## 6. 目标指标

| 指标 | 目标 |
| --- | --- |
| `bridge.py` | 最终删除；迁移期只做兼容壳，< 30 行 |
| `qqbot/runtime.py` | < 150 行（只做装配） |
| `qqbot/adapters/*` | 每个 < 500 行 |
| `qqbot/conversation/*` | 每个 < 400 行 |
| `qqbot/domains/*` | 每个领域 < 600 行 |
| `panel.py` / `panel/` | 后端 < 400 行（只保留 API） |
| `service/server.py` | 最终拆成 `app.py` + routes，每个 < 500 行 |
| `plugins/dsh-remembers/index.mjs` | < 200 行（只注册） |
| `plugins/dsh-remembers/hooks/*` | 每个 < 120 行（只做协议适配） |
| 插件业务规则 | 0：不出现 query 构造、surprisal 阈值、L0 写入判断 |
| 硬编码路径 | 0（配置值除外） |
| 领域间反向依赖 | 0 |
| smoke 覆盖 | 核心端口 + 5 个接口 |
| 单测 | store / extractor / context 至少各 3 条 |

---

## 7. 风险与回滚

### 风险

1. 后台 loop 迁移后重复启动
2. 群聊合并/门控行为回归
3. 插件召回格式变化导致人设漂移
4. 旧数据双写停止后兴趣提取失效
5. Windows 路径/编码问题

### 回滚

- 每个 Phase 开始前备份：
  - `bridge.py`
  - `panel.py`
  - `service/server.py`
  - `plugin/index.mjs`
  - `memories.db`
- 保留上一版可执行文件在 `backups/`
- 回滚只切文件，不反向迁移数据

---

## 8. 执行顺序

```
Phase 0  保护网
Phase 1  配置收口 + qqbot 骨架
Phase 2  media
Phase 3  persona
Phase 4  group / autonomy
Phase 5  service 路由
Phase 6  panel 前后端
Phase 7  插件收薄（拆分 + hook 收口）
Phase 8  清遗留
```

原则：

- 一次只拆一个领域
- 先加 facade，再搬实现
- 旧入口保留到新路径验证通过
- 每阶段结束更新本文档状态

---

## 9. 变更记录

| 日期 | 阶段 | 内容 |
| --- | --- | --- |
| 2026-11-02 | 计划 | 初版 |
| 2026-11-02 | Phase 1 | settings.py、bridge/panel 配置收口、死代码清理 |
| 2026-11-02 | 架构审视 | 去掉 bridge 容器；改为 qqbot/adapters、conversation、domains、clients、jobs；补 contracts/ports；统一 jobs；panel 只读投影 |
| 2026-11-02 | Phase 0 开始 | smoke.py、backup_state.py、Phase 0 备份 |
| 2026-11-02 | Phase 1 开始 | qqbot 包骨架、contracts.py、ports.py；启动脚本读 config 端口/路径 |
| 2026-11-02 | Phase 2 完成 | 图片下载、视觉、表情包收集/索引/meme 迁入 `qqbot/domains/media`；bridge 只保留调用 |
| 2026-11-02 | 测试规则 | 每阶段固定跑 `scripts/check.ps1`；Phase 2 新增 `tests/test_media.py` |
| 2026-11-02 | Phase 3 代码完成 | growth/reflect、profile、style、important、emotion；clients/memory；移除旧重要的事双写；bridge 2645 行 |
| 2026-11-02 | Phase 3 测试 | `tests/test_growth.py` 5 条 + 全量 10 条通过；smoke 通过 |
| 2026-11-02 | Phase 4 开始 | group 日志/黑话/网络梗迁入 `qqbot/domains/group/slang.py`；bridge 2319 行 |
| 2026-11-02 | Phase 4 group | group proactive、qzone 迁入 domains；bridge 2166 行 |
| 2026-11-02 | Phase 4 测试 | `tests/test_phase4_extra.py` 3 条；全量 16 条通过；smoke 通过 |
| 2026-11-02 | Phase 4 autonomy 状态 | 兴趣/已看/运行状态/similar_topic 迁入 `autonomy/state.py`；bridge 2077 行 |
| 2026-11-02 | Phase 4 autonomy 测试 | `tests/test_autonomy.py`；全量 17 条通过；smoke 通过 |
| 2026-11-02 | Phase 4 autonomy Bili | feed/view、pick_topic、apply_interest、compose_share 迁入 `autonomy/bili.py`；全量 18 条通过 |
| 2026-11-02 | Phase 4 完成 | interests、round、loop 迁入 autonomy；bridge 1717 行；全量 18 条 + smoke 通过 |
| 2026-11-02 | Phase 5 开始 | `/context` 格式进 `memory/context.py`，人格块进 `persona/context.py`；服务重启通过 |
| 2026-11-02 | Phase 5 persona | 人格读写路由逻辑进 `api/routes/persona.py`；`/persona`、`/persona/context` 200；smoke 通过 |
| 2026-11-02 | Phase 5 memory | ingest/search/forget 进 `api/routes/memory.py`；`/search` 200；server 3213 行 |
| 2026-11-02 | Phase 5 只读路由 | `read.py` 收 stats/activity/emotion/memories/tasks/notes/diary；`table.py` 收 POST 分发；server 3106 行 |
| 2026-11-02 | Phase 5 完成 | GET 分支进 `api/routes/get.py`，GET/POST 都走路由表；server 2946 行；smoke 通过 |
| 2026-11-02 | Phase 6 前端 | 面板拆成 `web/index.html`、`app.js`、`style.css`；`/static/*` 可访问；panel.py 881 行 |
| 2026-11-02 | Phase 6 readers | 投影/动作/服务访问迁到 `panel_readers.py`；panel.py 232 行；面板接口 200 |
| 2026-11-02 | Phase 6 routes | API 路由迁到 `panel_routes.py`；panel.py 64 行；`/api/*` 200；smoke 通过 |
| 2026-11-02 | Phase 7 hook 起点 | 服务加 `/hook/pre-step`、`/hook/turn-end`；插件加 client 方法和 `hooks` 开关；smoke 通过 |
| 2026-11-02 | Phase 7 turn-end | 插件 turn-end 支持 hook 分支；JS 语法检查通过；开关默认关 |
| 2026-11-02 | Phase 7 灰度 | 插件部署到 profile，`CMEM_HOOKS=1` 重启；8081/60773/6080 正常，smoke 通过 |
| 2026-11-02 | Phase 7 hook 实测 | 修复 `MemoryInput` 参数错误；L0 写入 200、`/forget` 清理；pre-step system/recall 正常 |
| 2026-11-02 | Phase 7 持久化 | `cordis.patch.yml` 写入 `hooks: true`；重启不依赖环境变量；smoke 通过 |
| 2026-11-02 | Phase 7 观测 | hook 事件写入 `hook-events.jsonl`：pre_step 的 system/recall 长度、turn_end 的 stored/reason |
| 2026-11-02 | 修复 | DSH 重启漏了 `DSH_HOME=.dsh-qqbot`，bridge cookie 401；补齐后 `projections` 正常 |
| 2026-11-02 | 修复 | Phase 2 搬 library 时漏 import `category_from_text` / `should_hint`，bridge 处理图片消息崩溃；补回并加回归测试 |
| 2026-11-02 | 修复 | 同批漏了 `sanitize_markdown` / `split_bubbles` / `persona_reflect_cfg` / `record_share_feedback`；补回，pyflakes 无 undefined，22 条测试通过 |
| 2026-11-02 | 修复 | `hooks: true` 要写在 profile 的 `cordis.patch.yml`，不是插件目录；已改并重启 |
| 2026-11-02 | 确认 | DSH 启动日志 `[dsh-remembers] config hooks=true`；bridge 重连；等真实 QQ 回合 |
| 2026-11-02 | 真实回合 | `turn_end` 已走 hook，scope=private:1215258939，small_talk 正常跳过；pre_step 待下一轮 |
| 2026-11-02 | 安全修复 | pre_step hook 对未映射 `scope=global` 会话也注入了 4596 字召回；加 guard：global 非 onebot 直接跳过 |
| 2026-11-02 | 修复 | profile/person 注入提前 return 会跳过同轮召回；改为 `extra` 累积后统一注入 |
| 2026-11-02 | 清理 | 真实 `pre_step recall=4197` / `turn_end stored=true`；删除旧 L0 capture 和旧 recall fallback |
| 2026-11-02 | 清理 | 删除 `buildQuery`、`client.search/context/surprisal/ingest`；index 2099 行、client 141 行 |
| 2026-11-02 | 拆分 | hook 调用拆到 `hooks/recall.mjs`、`hooks/turn_end.mjs`；DSH 重启无报错 |
| 2026-11-02 | 拆分 | `set_emotion`、`remember_important` 拆到 `tools/`；index 1999 行；启动无报错 |
| 2026-11-02 | 拆分 | persona/activity/memes/companion 工具全部拆出；删除 B 站死代码；index 1406 行；顺带修复 companion 缺失 `get` |
| 2026-11-02 | 拆分 | `renderState` / `renderPersona` 等纯函数拆到 hooks；index 1017 行；修复 state 模块误带 bootstrap 的 `log` 错误；同时部署 `.dsh` 和 `.dsh-qqbot` 两个 profile |
| 2026-11-02 | 拆分 | 生命周期移到 `app.mjs`，`index.mjs` 只剩 2 行 re-export；DSH 启动正常；22 tests + smoke 通过 |
| 2026-11-02 | Phase 7 完成 | 真实 QQ：`pre_step recall=4411`、`turn_end id=376`；工具/hook 全部模块化 |
| 2026-11-02 | Phase 8 完成 | 旧 memory.db 双写删除；兴趣读服务 L1；persona_apply/selfwake 路由删除；旧目录归档 |
| 2026-11-02 | 最终验证 | 真实 QQ：`pre_step recall=4595`、`turn_end id=377`；回复正常；22 tests + smoke 通过；总结见 `refactor-summary.md` |
| 2026-11-02 | README | 重写根目录 `README.md`：当前拓扑、端口、启动、记忆模型、插件 hook、面板、测试、排障、回滚 |
| 2026-11-02 | 上传 | 初始化 git，仅提交源码/文档/测试；创建 private repo `meijn572/dsh-qqbot` 并推送 main |

| 2026-11-02 | 计划 | 合并 Phase 7/8 为“插件收薄（拆分 + hook 收口）”；清遗留改为 Phase 8 |
