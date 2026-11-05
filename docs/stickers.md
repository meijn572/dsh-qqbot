# 表情包系统

表情包有两条独立的描述线：

```text
label       记忆/展示用的短名
facets      检索用的结构化语义
```

不再使用 `tags` / `concepts`。

## 1. 分层

```text
QQ 消息图片
  → bridge / domains/media/download.py
  → vision.py 识别类别、caption、facets
  → stickers.py 收藏、去重
  → library.py 索引、选图、分面匹配
  → bridge 发送 [[meme:...]]

主模型看到图后
  → tools/memes.mjs sticker_meta
  → 写队列
  → bridge sticker_meta_loop
  → media.meta.apply_record
  → library.index_add
```

| 层 | 职责 |
| --- | --- |
| `bridge.py` | 收图、发图、队列轮询、给模型看旧语义 |
| `qqbot/domains/media` | 下载、视觉、收藏、索引、匹配 |
| `plugins/dsh-remembers/tools/memes.mjs` | DSH 工具适配 |
| 面板 | 人工查看、改语义、删除 |

## 2. 数据文件

```text
stickers/
  happy/
    u_xxx.jpg
  ...
  index.json
  meta.json
```

`index.json` 条目：

```json
{
  "file": "happy/u_xxx.jpg",
  "category": "happy",
  "caption": "黄色圆滚小人仰头大笑",
  "label": "大笑奶龙",
  "identity": ["奶龙"],
  "action": ["躺倒"],
  "expression": ["大笑", "开心"],
  "generic": ["搞笑", "可爱"],
  "usage_count": 3,
  "last_used_at": 179...
}
```

### label

- 2–10 字
- 只用于记忆/展示
- 模型看到图后写
- 不从 facets/caption 自动拼
- 空就是空

### caption

- 可选
- 80 字以内
- 只做画面补充和检索兜底
- facets 没有命中时才参与匹配
- 不写进 L0，不进记忆

### facets

```text
identity    角色/IP/人物
action      动作
expression  表情/情绪
generic     泛词
```

检索时加权：

```text
identity   100
action      50
expression  40
generic     10
```

`caption` 只在 facets 没命中时作为兜底（15 分），`label` 不参与检索。

## 3. 收集流程

1. 下载图片，判断是不是表情包
2. 视觉模型输出：

```json
{
  "category": "happy",
  "caption": "黄色圆滚小人仰头大笑",
  "identity": ["奶龙"],
  "action": ["躺倒"],
  "expression": ["大笑", "开心"],
  "generic": ["搞笑", "可爱"]
}
```

3. 按文件 hash 和感知签名去重
4. 写入索引

视觉模型不负责起 `label`；label 由主模型看到图后写。

## 4. 主模型写入

工具：`sticker_meta`

```json
{
  "ref": "source:D:\\...\\xxx.jpg",
  "label": "大笑奶龙",
  "identity": "奶龙, 小恐龙",
  "action": "躺倒",
  "expression": "大笑, 开心",
  "generic": "搞笑, 可爱",
  "caption": "黄色圆滚小人躺着仰头大笑"
}
```

`ref` 支持：

```text
source:<原图路径>
file:<库内相对路径>
query:<关键词>
```

### 旧语义

bridge-note 会带：

```text
[表情包：D:\...\xxx.jpg]
（库里已有：label=...；identity=...；action=...；expression=...；generic=...；caption=...）
```

模型先看旧语义再决定是否改。

### 合并/替换

默认：

```text
旧 facets 保留
新 facets 清洗后追加
label 只有非空才更新
```

要完整替换 facets：

```json
{"replace_facets": true}
```

label 由模型写，不做自动覆盖保护；空 label 不会清空已有值。

## 5. 队列

`sticker_meta` 不直接写库，只追加：

```text
$DSH_HOME/sticker-meta-queue.jsonl
```

bridge 每 3 秒消费：

- 收藏尚未落盘 → 保留，最多 180 秒
- 落盘后 → 解析 `source/file/query`
- 写入索引
- 成功从队列删除

## 6. 选图

`resolve_meme(token)`：

1. 支持 `类别:关键词`
2. 按 facets 加权搜索
3. 类别只作过滤/兜底
4. 没命中就返回 `None`，不硬配

使用习惯：

```text
用得多、最近用得多 → 加分
不是“越新越优先”
```

## 7. 面板

页面：`web/app.js` 的表情包 tab。

每张卡片：

```text
表情图
label
identity / action / expression / generic 分面
```

操作：

```text
[修改语义] [删除]
```

先选中，再操作。

- 修改语义：弹窗编辑 label + 四类分面
- 删除：选中后出现红色 `×`，再点确认
- 表情页不参与 10 秒自动刷新

接口：

```http
GET  /api/stickers
GET  /api/stickers/lookup?ref=...
POST /api/stickers/semantics
POST /api/stickers/delete
```

## 8. 触发

不再逐条加“你应该调用 X”的提示。

- 工具描述说明能力
- `AGENTS.md` 只留一句全局规则
- bridge-note 只提供事实：图片路径、库里已有语义
- 模型自行决定是否调用 `sticker_lookup` / `sticker_meta`

## 9. 记忆里的表情

用户发表情时，L0 只保留一个短标记：

```text
主人：[[sticker:大笑奶龙]]
```

- 有 label 才写 label
- 没有 label 仍写“发来 N 张表情”
- 不写 facets、caption、文件路径
- 不进 L1/L3，不参与召回

## 10. 已知限制

- 视觉模型认不出冷门 IP 时，identity 可能为空
- label 依赖主模型主动写；没写就显示“未命名”
- 同一角色可能有多个写法，需要模型或面板收敛
- 一张图有多个角色时，identity 是列表
- `source` 依赖原图还在；inbox 清理后只能用 `file` / `query`
- `last:` 还没接
- 近似图依赖感知签名，极端裁剪可能匹配不上
- 图片本体不持久化到记忆库，只存引用

## 11. 代码地图

| 文件 | 作用 |
| --- | --- |
| `qqbot/domains/media/download.py` | 下载、识别 sticker |
| `qqbot/domains/media/vision.py` | 视觉分类、caption、facets |
| `qqbot/domains/media/stickers.py` | 收藏、去重 |
| `qqbot/domains/media/library.py` | 索引、分面匹配、选图 |
| `qqbot/domains/media/meta.py` | source/file/query 解析、读写 |
| `bridge.py` | 队列、旧语义提示、发送 |
| `plugins/dsh-remembers/tools/memes.mjs` | `sticker_lookup` / `sticker_meta` |
| `panel_readers.py` / `panel_routes.py` | 面板 API |
| `web/app.js` / `style.css` | 面板交互 |

词库见 [词库系统](lexicon.md)。

## 12. 历史方案：category 保留（已被新方案替代）

> 本节记录早期方案，最终实现以 [表情元数据与离线复盘](sticker-metadata.md) 为准。
> 新方案：小模型实时写待整理值，大模型离线独立复盘，reviewed 可被迟到解释重新打开。

### 决策

```text
保留 category
category 不再由视觉小模型分类
由主模型在 sticker_meta 里顺手填写
不加硬规则
示例从大类换成具体标签
```

### 依据

2026-11-01 到 2026-11-06 的 QQ 日志里，`[[meme:...]]` 共 24 次：

```text
具体标签/关键词：15 次
category 大类： 9 次
```

标签查找已经比 category 用得多，不需要再加“必须用标签”的硬规则。

category 仍有价值：

- 标签没命中时兜底
- 模型不知道具体词时能发一张
- 兼容 `[[meme:happy]]` 等旧写法

### category 来源

不再走：

```text
视觉小模型 classify_sticker / describe_sticker
  → category
```

改成：

```text
主模型看到图
  → sticker_meta
  → category + label + facets
```

`sticker_meta` 增加可选 `category`：

```json
{
  "ref": "file:unsorted/u_xxx.jpg",
  "category": "happy",
  "label": "大笑奶龙",
  "caption": "黄色圆滚小人躺着大笑",
  "identity": ["奶龙"],
  "action": ["躺倒"],
  "expression": ["大笑", "开心"]
}
```

可选大类保持现有枚举：

```text
happy / angry / sad / confused / surprised / shy
sleep / affection / food / money / greeting / work
entertainment / teasing / reply
```

不填就留空，不强制。

### 文件放哪

category 后填，所以不能让目录先等它。

```text
新表情 → stickers/unsorted/u_xxx.jpg
category 只写索引
```

旧文件不移动，旧目录只当历史存储。

```text
目录 = 存储
category = 语义
```

不再把目录名当语义来源。

### 为什么会偏向 category

不是标签不能用，是示例一直在教 category：

```text
[[meme:angry]]
[[meme:confused]]
[[meme:teasing]]
```

模型会优先模仿示例。

### 示例改动

只改 `AGENTS.md` 的表情示例，把示例从大类换成具体标签：

```text
[[meme:发懵]]
[[meme:坏笑]]
[[meme:躺倒]]
[[meme:奶龙]]
```

保留一句兜底说明：

```text
优先写具体角色/动作/感觉；
实在不知道写什么，才写大类。
```

不增加：

```text
必须用标签
禁止 category
关键词白名单
命中率阈值
```

### 行为

```text
具体标签命中 → 用标签匹配
具体标签没命中 → 回退 category
category 也没命中 → 不发图
```

不改 `resolve_meme` 的现有优先级。

### 待整理

如果大模型没调用 `sticker_meta`：

```text
category 空
label 空
facets 可能空
```

需要：

```text
needs_meta = true
```

bridge-note 或面板提示：

```text
这张还没整理，调用 sticker_meta 补语义
```

不让未整理的表情静默变成“没有分类”。

### 命名时序

当前自动流程和先后顺序：

```text
先说“这是奶龙”，再发图
  同一条合并窗口内 → context_text 包含“奶龙”
  → 但 enrich_stickers 的 JSON 不要求 label
  → 仍然不会自动写名字

先发图，再说“这是奶龙”
  图在合并窗口内 → 文本和图合并，context_text 也可能包含“奶龙”
  图已经先处理 → 后续文本不会重新触发这张图的 enrich
  → 更不会自动写名字
```

当前实际：

```text
merge_seconds = 12 秒（私聊）
group_merge_seconds = 20 秒（群聊）
```

在窗口内，先图后字和先字后图都会合并到同一批。

但：

```text
enrich_stickers 只写 description + facets
不写 label
不写 category
```

所以“先说什么”只影响上下文，不影响是否写名字。

日志里 `表情语义已补` 只有少量记录，绝大多数还是测试或面板操作；自动收藏基本没有写 label。

### 如果要做“先图后名”自动补

需要 bridge 保存最近一张待整理表情：

```text
pending_sticker[chat_key] = source path / rel
```

下一轮用户说“这是奶龙”时，bridge-note 带上：

```text
（上一张待整理表情：source:D:\...）
```

模型再调用：

```text
sticker_meta(ref="source:...", label="奶龙", category="...")
```

否则后续文本没有可靠方式指向刚才那张图。

### 验收

```text
AGENTS 示例改成具体标签
sticker_meta 支持 category
新收藏进 unsorted
category 由大模型填
不新增硬提示
观察接下来 50 次表情使用
```

看四个数：

- 具体标签占比
- category 占比
- 未整理数量
- 找不到图的比例

如果标签占比上升、未整理没有持续堆积，就保持这一版。
