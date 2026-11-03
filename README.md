# 大肥鱼 QQ Bot

> GitHub: <https://github.com/meijn572/dsh-qqbot>（private）

基于 DSH（DeepSeek Harness）的 QQ 陪伴机器人。QQ 消息经 SnowLuma / OneBot 进入桥接，DSH 负责对话，记忆服务负责长期记忆与人格。

记忆服务和 DSH 插件基于 `dsh-remembers` / `companion-memory`（MIT）修改，来源和改动见 [THIRD_PARTY.md](THIRD_PARTY.md)。

旧 AstrBot 部署保留，可回退。

## 拓扑

```
QQ
└─ SnowLuma
   ├─ OneBot HTTP 3000
   └─ OneBot WS   3001
        │
        ▼
  bridge.py  ──────────────►  DSH qqbot2 127.0.0.1:60773
  消息合并/门控/发送              profile: qqbot2
  主动/群聊/自主刷                插件: dsh-remembers
        │                               │
        │                               ▼
        └──────────────►  记忆服务 127.0.0.1:8081
                          store / context / persona / hook
                                 │
                                 ▼
                     $env:USERPROFILE\.dsh-qqbot\remembers-data

面板 127.0.0.1:6080
```

## 快速启动

首次运行先复制配置模板，填入自己的 QQ 号、群号和路径：

```powershell
Copy-Item D:\path\to\dshbot\config.example.json D:\path\to\dshbot\config.json
```

然后：

```powershell
powershell -ExecutionPolicy Bypass -File D:\path\to\dshbot\start-dshbot.ps1
```

停止：

```powershell
powershell -ExecutionPolicy Bypass -File D:\path\to\dshbot\stop-dshbot.ps1
```

启动脚本读取 `config.json`，按配置启动：

- QQ
- SnowLuma
- 记忆服务 8081
- DSH qqbot2 60773
- 面板 6080
- 桥接

## 目录

| 路径 | 作用 |
| --- | --- |
| `bridge.py` | QQ ↔ DSH 桥：收发、合并、门控、主动、群聊、自主刷 |
| `config.json` | 端口、白名单、行为参数、路径 |
| `qqbot/` | 业务域：media / group / growth / autonomy / qzone |
| `qqbot/clients/` | 记忆、人格服务 HTTP 客户端 |
| `service/` | 记忆服务源码（基于 companion-memory 修改） |
| `plugins/dsh-remembers/` | DSH 插件源码（基于 dsh-remembers 修改） |
| `panel.py` | 面板 HTTP 生命周期 |
| `panel_readers.py` | 面板投影、动作、服务访问 |
| `panel_routes.py` | 面板 API 路由 |
| `web/` | 面板前端 `index.html` / `app.js` / `style.css` |
| `scripts/smoke.py` | 端口 + 核心接口检查 |
| `scripts/check.ps1` | 单测 + smoke |
| `tests/` | 22 条单测 |
| `docs/refactor-plan.md` | 重构计划与阶段记录 |
| `docs/refactor-summary.md` | 重构总结 |
| `docs/architecture.md` | 架构说明 |
| `docs/open-source.md` | 公开与第三方依赖说明 |
| `THIRD_PARTY.md` | 第三方版权/许可证声明 |

## 运行数据

| 路径 | 内容 |
| --- | --- |
| `runtime/state.json` | QQ 会话 → DSH 会话绑定 |
| `runtime/health.json` | 桥接心跳 |
| `runtime/bili_qr.png` | B 站登录二维码 |
| `logs/` | bridge / panel / bili 日志 |
| `secrets/` | OneBot/DSH token（不入库） |
| `$env:USERPROFILE\.dsh-qqbot\remembers-data\memories.db` | 记忆主库 |
| `$env:USERPROFILE\.dsh-qqbot\remembers-service\` | 记忆服务 |
| `$env:USERPROFILE\.dsh-qqbot\hook-events.jsonl` | hook 观测日志 |
| `$env:USERPROFILE\.dsh-qqbot\important\important.md` | 手写重要的事 |
| `$env:USERPROFILE\.dsh-qqbot\bili-autonomy\` | 兴趣、已看、运行状态 |
| `$env:USERPROFILE\.dsh-qqbot\persona-reflect\` | 复盘状态 |
| `$env:USERPROFILE\.dsh-qqbot\archive\legacy-20261102\` | 归档的旧目录 |

## 记忆模型

| 层 | 内容 |
| --- | --- |
| L0 | 原话，完整保留 |
| L1 | 原子事实，约 30 天 |
| L2 | 用户画像，约 180 天 |
| L3 | 事件线，约 90 天 |
| L4 | 人格/关系，不衰减 |

- 存储保持裸文本，不在每条记忆里加“我记得”
- 注入时统一加框架
- 人格分：核心设定、自我认知、身份、自我形象、我眼中的主人
- 重要的事在核心设定里的独立段，最多 8 条
- 批量蒸馏：L0 → L1；L1 + L0 → L3；L1 + L3 → L4
- 用户画像每 2 天刷新
- 情绪由鱼自己用 `set_emotion` 记，不用关键词猜

## DSH 插件

`dsh-remembers` 现在只做 DSH 适配：

```
plugins/dsh-remembers/
  index.mjs      2 行，re-export
  app.mjs        生命周期/装配
  client.mjs     记忆服务 HTTP
  config.mjs     配置
  hooks/
    recall.mjs       /hook/pre-step
    turn_end.mjs     /hook/turn-end
    state.mjs        状态渲染
    persona.mjs      人格渲染
  tools/
    emotion.mjs
    important.mjs
    persona.mjs
    activity.mjs
    memes.mjs
    companion.mjs
```

召回、写入策略在记忆服务：

```http
POST /hook/pre-step
POST /hook/turn-end
```

插件只传消息，服务返回 `system` / `recall` 或决定 `stored`。

### 已知坑：两个 profile 路径

桥接使用：

```
DSH_HOME=$env:USERPROFILE\.dsh-qqbot
```

但 DSH 实际加载插件目前是：

```
$env:USERPROFILE\.dsh\profiles\qqbot2\node_modules\dsh-remembers
```

改插件后两边都要同步，否则会出现“代码改了但没生效”。

启用 hook 的配置在实际 profile 的：

```
$env:USERPROFILE\.dsh\profiles\qqbot2\cordis.patch.yml
```

确保有：

```yaml
- id: dsh-remembers
  config:
    endpoint: http://127.0.0.1:8081
    hooks: true
```

## 面板

<http://127.0.0.1:6080/>

主要页：

- 概览
- 心与记忆：记忆 / 人格 / 群友 / 小本子 / 心情 · 关系 / 主动
- 表情 · 黑话
- 日志
- 兴趣 · B 站

前端是独立静态文件，后端只提供 API 和 `/static/*`。

人格页可以直接编辑：

- 核心设定
- 自我认知
- 用户画像

自我认知和画像保存后立即写回记忆服务，不会改核心设定。

## 自主能力

- 私聊主动：25–50 分钟随机，静默 0–8
- 群主动：180–360 分钟，空闲 60 分钟，每天最多 1 次
- 群接话：门控跳过 0.45，插话 0.10
- B 站自主刷：10–23 点，35–90 分钟随机，分时段上限，自由探索 0.4
- QQ 空间：每天 1 条，间隔 6 小时，仅好友可见
- 情绪自检：3–5 小时一次，每天最多 5 次
- 重要的事自检：10 点、22 点
- 日记：23 点后自动写，失败每 15 分钟重试

## 测试

```powershell
powershell -ExecutionPolicy Bypass -File D:\path\to\dshbot\scripts\check.ps1
```

包含：

- 22 条单测
- smoke：8081 / 60773 / 6080 / 3001
- `/persona/context`
- `/state`
- 面板核心 API
- `/hook/pre-step`
- `/hook/turn-end`

## 观测

真实 QQ 回合：

```powershell
Get-Content $env:USERPROFILE\.dsh-qqbot\hook-events.jsonl -Tail 20
```

正常应看到：

```json
{"event":"pre_step","session":"session-...","scope":"private:...","recall_chars":...}
{"event":"turn_end","session":"session-...","scope":"private:...","stored":true,"id":...}
```

桥接日志：

```powershell
Get-Content D:\path\to\dshbot\logs\bridge.err -Tail 50
```

## 常见问题

### QQ 不回复

先看：

```powershell
Get-Content D:\path\to\dshbot\logs\bridge.err -Tail 50
```

常见原因：

- `NameError`：重构后漏 import
- `401`：DSH 重启时 `DSH_HOME` 不对，bridge cookie 失效
- OneBot 没连上：检查 3001

### hook 没触发

1. 看 DSH 启动日志有没有：

   ```
   [dsh-remembers] config hooks=true
   ```

2. 看实际 profile 的 `cordis.patch.yml` 是否 `hooks: true`
3. 看 `hook-events.jsonl` 有没有 `pre_step`
4. 确认插件文件已同步到实际 profile 路径

### 插件加载失败

看：

```powershell
Get-Content $env:USERPROFILE\.dsh-qqbot\qqbot2.err -Tail 40
```

常见是 `hooks/` 或 `tools/` 新文件没复制到实际 profile。

## 回滚

重构前备份：

```
D:\path\to\dshbot\backups\refactor-phase0-20261102-163809
```

旧目录：

```
$env:USERPROFILE\.dsh-qqbot\archive\legacy-20261102\
```

AstrBot 旧部署仍在，回退时恢复 AstrBot 白名单/平台开关即可。

## 还没做

- `app.mjs` 941 行，生命周期可继续拆
- `remembers-service/server.py` 2709 行，路由可继续拆
- 前端 `app.js` 还没按 tab 拆
- 旧 `memory.db` 已不再写，观察后归档

## 相关文档

- [架构说明](docs/architecture.md)
- [工作流与记忆逻辑](docs/workflows.md)
- [开源与第三方依赖](docs/open-source.md)
- [重构计划](docs/refactor-plan.md)
- [重构总结](docs/refactor-summary.md)
