# 重构总结（2026-11-02）

## 结果

主体重构完成，真实 QQ 回合验证通过：

```json
{"event":"pre_step","session":"session-***","scope":"private:***","recall_chars":4595}
{"event":"turn_end","session":"session-***","scope":"private:***","stored":true,"id":377,"surprisal":0.8947}
```

回复正常发出，L0 正文包含主人原话和鱼的回复。

## 最终边界

| 层 | 负责 |
| --- | --- |
| `bridge.py` | QQ 消息接入、合并、门控、发送、后台任务装配 |
| `qqbot/domains/*` | media / group / growth / autonomy / qzone |
| `qqbot/clients/*` | 记忆、人格服务 HTTP 客户端 |
| `remembers-service` | 存储、检索、context、batch、人格、hook 策略 |
| `dsh-remembers` 插件 | DSH 生命周期适配、注入、tool schema 转发 |
| `panel.py` | 小面板 HTTP 生命周期 |

## 关键变化

### 记忆

- L0/L1/L2/L3/L4 由记忆服务统一管理
- 召回、写入策略进 `/hook/pre-step`、`/hook/turn-end`
- 插件不再构造 query、不判断 surprisal、不决定 L0 写不写
- 存储保持裸文本，注入时才加“你记得/要记住”的框架
- 未映射 `scope=global` 的会话不再注入召回，避免隐私泄漏

### 插件

```
plugins/dsh-remembers/
  index.mjs          2 行，只 re-export
  app.mjs            941 行，生命周期/装配
  client.mjs
  config.mjs
  hooks/
    recall.mjs
    turn_end.mjs
    state.mjs
    persona.mjs
  tools/
    emotion.mjs
    important.mjs
    persona.mjs
    activity.mjs
    memes.mjs
    companion.mjs
```

旧的 capture/recall fallback、`buildQuery`、`client.search/context/surprisal/ingest`、未启用的 B 站工具组均已删除。

### 桥接

- 媒体下载/视觉/表情库迁到 `qqbot/domains/media`
- 群日志/黑话/群主动迁到 `qqbot/domains/group`
- 复盘/画像/风格/重要的事/情绪迁到 `qqbot/domains/growth`
- B 站、兴趣、自主刷迁到 `qqbot/domains/autonomy`
- 空间发布迁到 `qqbot/domains/qzone`
- 删除旧 `memory.db` 双写，兴趣提取改读服务 L1
- 删除旧 memory-hygiene 循环和 selfwake API

### 面板

```
web/index.html
web/app.js
web/style.css
panel_readers.py
panel_routes.py
panel.py
```

## 行数

| 文件 | 行数 |
| --- | ---: |
| `bridge.py` | 1713 |
| `panel.py` | 64 |
| `panel_readers.py` | 588 |
| `panel_routes.py` | 157 |
| `remembers-service/server.py` | 2709 |
| `plugins/dsh-remembers/index.mjs` | 2 |
| `plugins/dsh-remembers/app.mjs` | 941 |

## 验证

- 单元测试：22 条通过
- smoke：端口 + 核心接口 + 两个 hook 通过
- 真实 QQ：召回、回复、L0 写入正常
- 面板：`/api/status`、`/api/mood`、`/api/style`、`/api/memory` 正常

## 还没做 / 可继续

- `app.mjs` 941 行，profile/state/capture 生命周期还可以继续拆
- `remembers-service/server.py` 2709 行，路由已拆出一部分，仍可继续
- 前端 `app.js` 还没按 tab 拆
- 旧 `memory.db` 文件还在，已不再写；观察期后再决定归档/删除
- 建议观察一天真实 QQ、面板、自主刷/空间

## 回滚

- 重构前备份：
  ```
  D:\path\to\dshbot\backups\refactor-phase0-20261102-163809
  ```
- 插件拆分前备份：
  ```
  C:\Users\<you>\.dsh-qqbot\plugins\dsh-remembers\index.before-*.mjs
  ```
- 旧目录：
  ```
  C:\Users\<you>\.dsh-qqbot\archive\legacy-20261102\
  ```

## 运行开关

- `CMEM_HOOKS` / profile patch `hooks: true`：走服务端 hook
- 插件 `config.hooks` 关闭会回到旧路径，但旧路径已删除；现在 hook 是唯一路径
- 服务不可用时插件 fail-open，不阻塞回复
