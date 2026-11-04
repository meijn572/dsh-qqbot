# 表情包系统

表情包不是普通图片。它同时有：

- 图片文件
- 语义（名称、标签、描述、分类）
- 使用习惯（发过几次、最近什么时候发）
- 对话里的引用（主人发过、鱼要发）

这套系统把“图片”和“语义”分开：图片放目录，语义放索引，bridge 只负责时机，主模型通过工具补充理解。

## 1. 分层

```text
QQ 消息
  → bridge 下载到 inbox
  → domains/media/stickers.py 收藏 / 去重 / 视觉分类
  → domains/media/library.py 索引 / 选图 / 标签清洗
  → domains/media/meta.py 引用解析 / 查询 / 写语义

DSH 主模型
  → tools/memes.mjs 里的 sticker_lookup / sticker_meta
  → sticker_meta 只写队列
  → bridge 的 sticker_meta_loop 消费队列
  → media.meta.apply_record 落 index
```

职责边界：

| 层 | 负责 |
| --- | --- |
| `bridge.py` | 收图、发图、队列轮询、触发提示 |
| `qqbot/domains/media` | 图片、索引、去重、语义解析、选图 |
| `dsh-remembers` | 只做 DSH 工具适配 |
| 面板 | 人工查看、改标签、删除 |

## 2. 数据文件

```text
stickers/
  happy/
    u_05c84e1c43efe84d.jpg
  confused/
  ...
  index.json      # 语义索引
  meta.json       # OneBot 表情元数据（emoji_id / summary 等）
```

索引条目：

```json
{
  "file": "happy/u_05c84e1c43efe84d.jpg",
  "name": "奶龙举旗",
  "category": "happy",
  "caption": "黄色小恐龙举旗笑",
  "tags": ["奶龙", "小恐龙", "举旗", "开心"],
  "aliases": ["奶龙"],
  "usage_count": 4,
  "last_used_at": 1793710000,
  "w": 500,
  "h": 500,
  "sig": "003c3e3e7e3e3c00"
}
```

字段说明：

- `name`：人类可读的名字
- `category`：粗分类，只做 fallback
- `caption`：一句描述
- `tags`：真正的检索主索引
- `aliases`：用户教过的别名
- `usage_count` / `last_used_at`：使用习惯
- `sig`：感知签名，用于近似图去重

## 3. 收藏流程

入口：`qqbot/domains/media/stickers.py :: collect_sticker`

```text
收到表情
  → 大小检查
  → 规范化格式（GIF 保留，其他转 JPEG 视情况）
  → sha256 前 16 位作为 u_<hash>
  → 已有同名文件？
      是：复用，不重复收藏
  → 感知签名近似匹配？
      是：合并到已有条目
  → 视觉模型 describe_sticker
      category / caption / 3–6 个 tags
  → 落盘 + index_add
```

关键变化：

- **不再把聊天记录里的关键词塞进标签**
- 视觉标签和用户手动标签才是标签来源
- 近似图会走 `find_signature_match`，不会因为重压缩多出一张

## 4. 语义写入

### 4.1 主模型写

工具：`dsh-remembers/tools/memes.mjs :: sticker_meta`

```json
{
  "ref": "source:D:\\...\\inbox\\xxx.jpg",
  "name": "奶龙举旗",
  "tags": "奶龙, 小恐龙, 举旗, 开心",
  "caption": "黄色小恐龙举旗笑"
}
```

`ref` 支持：

```text
source:<原图路径>
file:<库内相对路径>
query:<关键词>
```

默认保留已有标签，只追加新标签。如果模型看过旧标签后要完整改写或删除旧标签，传：

```json
{"replace_tags": true}
```

如果 `bridge-note` 里带了 `（库里已有：...）`，那是在写入前给模型看的旧 name/tags/caption。

工具只写队列：

```text
$DSH_HOME/sticker-meta-queue.jsonl
```

bridge 的 `sticker_meta_loop` 每 3 秒消费一次：

```text
source 未落盘 → 最多重试 180 秒
file / query  → 立即解析
解析成功     → media.meta.apply_record → library.index_add
```

这样不会污染当前对话，也不会强制多跑一次主模型。

### 4.2 主模型查

工具：`sticker_lookup`

```json
{"ref":"source:D:\\...\\inbox\\xxx.jpg"}
```

返回：

```json
{
  "found": true,
  "file": "happy/u_xxx.jpg",
  "name": "奶龙举旗",
  "category": "happy",
  "tags": ["奶龙", "举旗"],
  "caption": "黄色小恐龙举旗笑",
  "usage_count": 4
}
```

查不到：

```json
{"found": false}
```

查询走面板只读接口：

```http
GET /api/stickers/lookup?ref=...
```

### 4.3 解析器

业务逻辑在 `qqbot/domains/media/meta.py`：

```python
resolve_ref(ref)       # source/file/query → 库内相对路径
lookup_ref(ref)        # 只读查询
apply_record(record)   # 写入 name/tags/caption
```

bridge 不再自己解析路径。

### 4.4 概念引用

表情、词条、记忆之间不直接复制内容，而是共享一个轻量 concept id：

```text
concept:奶龙
```

- `$DSH_HOME/concepts.json` 保存概念表
- 表情索引可以带 `concepts: ["concept:奶龙"]`
- 词条可以带同名 id
- 以后记忆事实可以带 `links: ["concept:奶龙"]`

`sticker_meta` 支持可选的 `concepts` 参数：

```json
{"ref":"file:happy/u_xxx.jpg","name":"奶龙举旗","concepts":"奶龙"}
```

如果只给 `name` 没给 `concepts`，会按 name 自动建一个明确概念。

当前只做“明确教过/明确给出”的概念，不做自动实体识别。



标签是检索词，不是聊天记录。

自动写入时只清洗**新标签**：

- 超过 12 字丢弃
- 带标点/整句丢弃
- 含“我/你/他/主人/刚才/视频/KPL/token”等场景词丢弃
- 新标签每次最多 8 个

已有标签不再被自动清洗或截断；它们可能是用户手动写的，默认只做追加，最多保留 24 个。模型明确传 `replace_tags=true` 时，才用这次提供的标签完整替换。

手动编辑不受自动清洗限制，但仍建议：

```text
奶龙, 小恐龙, 举旗, 开心, happy
```

不要写：

```text
我刚才在看的那个视频里的小恐龙
```

## 5. 选图

入口：`qqbot/domains/media/library.py :: resolve_meme`

```text
[[meme:happy]]
[[meme:奶龙]]
[[meme:happy:摇旗]]
```

解析顺序：

```text
1. 精确 file / name / alias
2. 标签精确命中
3. 标签包含
4. caption 包含
5. 类别 fallback
```

类别只做兜底，不是主索引。

同分时按“使用习惯”加权：

```text
使用次数 × 1.5
最近 5 分钟发过：+12
最近 1 小时：+8
最近 1 天：+4
```

用户偏好是“常用的、最近常用的优先”，不是“没发过的优先”。

找到具体图后：

- `mark_sticker_used` 增加 usage_count / last_used_at
- bridge 发图

## 6. 发送

模型输出：

```text
[[meme:奶龙]]
```

bridge 的 `OneBot.send`：

```text
MEME_RE 提取 token
  → resolve_meme
  → 读文件
  → 普通图 / 动画表情 / custom_face
  → 发送，并 mark_sticker_used
```

`[[meme:...]]` 不应出现在给用户的文本里。

## 7. 面板

页面：`web/app.js` 的表情包 tab。

每张卡片：

```text
表情图
标签（最多显示 5 个，剩余显示 +N）
概念（如果有）
```

整页顶部只有三个操作：

```text
[修改标签] [修改概念] [删除]
```

先点一张表情选中，再点操作按钮。

- 修改标签：弹窗编辑，保存后只更新标签块，不整页刷新
- 修改概念：弹窗编辑，保存后更新绿色概念块
- 删除：选中卡片下方出现红色 `×`，再点 `×` 才删除
- 删除完成或保存完成，选中状态清除，界面回到干净状态
- 表情页不参与 10 秒自动刷新，避免顶掉编辑

接口：

```http
GET  /api/stickers
GET  /api/stickers/lookup?ref=...
POST /api/stickers/tags
POST /api/stickers/concepts
POST /api/stickers/delete
```

## 8. 触发

不再按消息逐条加“你应该调用 X”的提示。现在的原则是：

- 工具描述负责说明能力
- `AGENTS.md` 只留一句全局规则
- bridge-note 只提供事实，例如 `[表情包：D:\...\xxx.jpg]`
- 如果这张图已经在库里，会再附一条 `（库里已有：name=...；tags=...；caption=...）`
- 不替模型做判断

模型看到图、路径、旧语义和工具描述后自行决定是否调用 `sticker_lookup` / `sticker_meta`。认不出时允许不写，用户也可以在面板手动补。

## 9. 已知限制

- 自动语义依赖视觉模型，冷门 IP 可能认不出
- 主模型可能漏调 `sticker_lookup` / `sticker_meta`
- `source` 依赖原图文件还在；inbox 被清理后只能靠 `file` / `query`
- `last:` 还没有接（需要按会话记录最近表情）
- `query:` 只能命中已有 name/tags/caption，不能凭空理解“奶龙”
- 近似图依赖感知签名，极端裁剪/改色可能匹配不上
- 图片本体不持久化到记忆库，只存引用
- 面板手动标签不经过自动清洗，由用户负责

## 10. 代码地图

| 文件 | 作用 |
| --- | --- |
| `qqbot/domains/media/download.py` | 下载、识别 sticker |
| `qqbot/domains/media/vision.py` | 视觉分类/描述 |
| `qqbot/domains/media/stickers.py` | 收藏、去重 |
| `qqbot/domains/media/library.py` | 索引、选图、标签清洗 |
| `qqbot/domains/media/meta.py` | source/file/query 解析、查/写 |
| `bridge.py` | 队列、发送 |
| `plugins/dsh-remembers/tools/memes.mjs` | `sticker_lookup` / `sticker_meta` |
| `panel_readers.py` / `panel_routes.py` | 面板 API |
| `web/app.js` / `style.css` | 面板交互 |

词库相关见 [词库系统](lexicon.md)。
