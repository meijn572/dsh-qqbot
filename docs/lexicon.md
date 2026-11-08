# 词库系统

词库统一存梗、黑话、热词、角色/IP、缩写和事件，不再按“群黑话 / 网络梗”拆文件。

核心是三个维度：

```text
kind    类型
scope   作用域
status  生命周期
```

## 1. 存储

主文件：

```text
$DSH_HOME/lexicon.json
```

结构：

```json
{
  "version": 1,
  "legacy_imported": true,
  "entries": [
    {
      "id": "lex:global:yyds",
      "term": "yyds",
      "kind": "buzzword",
      "scope": "global",
      "status": "hot",
      "meaning": "永远的神",
      "aliases": ["永远滴神"],
      "examples": [],
      "count": 3,
      "first_seen": 179...,
      "last_seen": 179...,
      "source": "panel"
    }
  ]
}
```

### kind

```text
slang         群黑话
meme          网络梗
buzzword      热门词
fandom        角色/IP 梗
abbreviation  缩写
emoji         表情/emoji 用法
event         时事/临时梗
```

### scope

```text
global          全局
group:<群号>    某个群
```

群黑话只是 `scope=group:<群号>`，不再单独存文件。

### status

```text
fresh      新词
hot        正在流行
stable     稳定
archived   过气
```

### id

```text
lex:global:yyds
lex:group:1132633236:2G
```

`id` 带 scope，避免不同群的同名词互相覆盖。

## 2. 迁移

首次加载自动导入旧数据：

```text
$DSH_HOME/group-slang/<gid>.json → kind=slang, scope=group:<gid>
$DSH_HOME/network-memes.json     → kind=meme, scope=global
```

旧文件保留，不再作为主存储；新写入只走 `lexicon.json`。

## 3. 工具

### `lexicon_lookup`：只查词

```json
{"q":"2G"}
```

返回：

```json
{
  "terms": [
    {
      "term": "2G",
      "kind": "slang",
      "scope": "group:1132633236",
      "meaning": "说人网速慢、消息过时……"
    }
  ]
}
```

可选过滤：

```text
scope=global / group:<群号>
kind=slang/meme/buzzword/fandom/abbreviation
status=fresh/hot/stable/archived
```

最多返回 20 条词条。

### `lexicon_search`：词 + 表情

```json
{"q":"奶龙"}
```

返回：

```json
{
  "terms": [...],
  "stickers": [...]
}
```

- `terms`：词条解释
- `stickers`：按 `identity/action/expression/generic/caption` 命中的表情

最多各 8 条。

### `learn_word`：唯一写入工具

```json
{
  "phrase": "yyds",
  "meaning": "永远的神",
  "kind": "buzzword",
  "aliases": "永远滴神",
  "status": "hot",
  "context": "主人教的新词"
}
```

`learn_word` 是词库唯一的写入入口。

带 `meaning` 时同时写：

```text
服务端 slang
+ lexicon.json
```

默认：

```text
kind   = slang
scope  = global
status = stable
```

`kind` 可选：

```text
slang / meme / buzzword / fandom / abbreviation
```

不再有 `lexicon_meta`，避免模型在两个写工具之间犹豫。

### 删除

模型没有删除工具，删除只在面板做，并且按 `id` 删。

## 4. 面板

入口：

```text
表情 / 词库
```

筛选：

```text
全部 | 群黑话 | 网络梗 | 热门词 | 角色/IP | 缩写
```

每条显示：

```text
[kind · scope] term [status] ×count
别名：...
解释
```

添加时可选：

- kind
- status
- aliases

删除按 `id`，不会误删别的群同名词。

词库输入框不参与 10 秒自动刷新，避免输入被顶掉。

## 5. bridge 里的使用

### 群黑话

只注入当前消息里实际出现的词或别名：

```text
消息里出现“2G” → 只带 2G 的解释
没出现 → 不注入
```

不再每条群消息都塞前 8 条。

### 网络词

`network_meme_hint` 命中 `term` 或 `aliases` 时，附一句解释。

### 不做的事

- 不按每条消息强制“你应该调用 X”
- 不把词库内容整段塞进系统提示
- 不自动猜测未教过的词

工具描述和 `AGENTS.md` 的一句全局规则负责引导，bridge 只提供事实。

## 6. 和表情的边界

词库负责“词是什么意思”，表情负责“这张图是什么”。

- 词条用 `term/aliases`
- 表情用 `label + identity/action/expression/generic`
- `lexicon_search` 可以同时返回词条和相关表情，但两边各自存储
- 没有共享的 `concept:` 层

详见 [表情包系统](stickers.md)。

## 7. 已知限制

- 群黑话的 scope 用群号；换群后旧 scope 不会自动迁移
- `lexicon_search` 只查词库 + 表情，不查 L0/L1 记忆
- `lexicon_lookup` 是子串匹配，不是语义向量检索
- 别名需要手动维护
- 过气词默认仍可能被查到，只在展示时标 `archived`
- 删除只清 `lexicon.json` 条目，不级联清表情或记忆
- 模型可能漏调工具；面板仍可兜底

## 9. 自动填写：每日词库复盘

2026-11-08 接上。

```text
每天 07:00 一次
输入：最近 24 小时 L0
→ 扫出词库里已经命中的 term / alias
→ 只把这些旧解释一起给模型
→ 问：
   旧词有没有新理解？
   有没有新词？
→ 模型输出 updates / new
→ 后台按 term/alias upsert
```

### 输入

```text
最近 24h L0 原文
本段命中的旧词解释（最多 8 条）
```

不把整个词库塞进去。

### 输出

```json
{
  "updates": [
    {"term": "蛋家军", "meaning": "新的解释", "example": "原话"}
  ],
  "new": [
    {"term": "奶蛙", "meaning": "解释", "kind": "meme", "aliases": [], "example": "原话"}
  ]
}
```

### 规则

```text
旧词没有新理解 → 不输出
新词必须有 meaning → 否则不落库
最多 2 个更新 + 2 个新词
普通词、语气词、地名、游戏名不算
```

### 去重

```text
term 已存在 → 更新
alias 命中已有词 → 归到已有词
meaning 为空 → 补
meaning 已有 → 这次有新理解才覆盖
```

### 工具和面板

```text
learn_word   用户明确教词时仍可写
面板添加     手动兜底
每日复盘     自动补
```

### 群黑话

```text
group_slang.enabled = false
```

群里没人说话，先关着；以后需要再开。

### 当前流程

```text
07:00 词库复盘
→ 有更新/新词才写
→ 没有就跳过
→ 面板下一次读取就能看到
```

## 10. 代码地图

| 文件 | 作用 |
| --- | --- |
| `qqbot/domains/group/lexicon.py` | 统一存储、迁移、upsert、查询 |
| `qqbot/domains/group/slang.py` | bridge 兼容层、群日志、网络梗提示 |
| `bridge.py` | 群黑话匹配注入、网络梗提示 |
| `plugins/dsh-remembers/tools/memes.mjs` | `lexicon_lookup` / `lexicon_search` |
| `panel_readers.py` | 词库投影、增删、搜索 |
| `panel_routes.py` | 面板 API |
| `web/app.js` / `style.css` | 词库页面 |
