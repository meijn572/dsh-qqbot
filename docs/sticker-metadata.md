# 表情元数据与离线复盘

状态：方案，未实现。

## 1. 目标

实时流程只保证表情“能用”，离线复盘负责把语义整理好。

```text
实时
  小模型先填一版
  标记待整理
  表情马上可搜、可发

离线
  大模型看图片 + 用户原话
  不看小模型已填的语义
  重写正式语义
  标记已整理
```

不引入 `provisional_*` 字段。

## 2. 数据结构

沿用原来的字段：

```json
{
  "file": "unsorted/u_xxx.jpg",
  "category": "happy",
  "caption": "卡通角色躺着笑",
  "identity": ["卡通角色"],
  "action": ["躺着"],
  "expression": ["大笑"],
  "generic": ["搞笑"],

  "meta_status": "pending_review",
  "meta_source": "vision",
  "review_version": 0,
  "evidence": [
    {"text": "这是奶龙", "ts": 1793890000}
  ],
  "last_review_at": 0
}
```

### meta_status

```text
pending_review   待整理
reviewed         已整理
```

不设 `manual` 状态。

### meta_source

```text
vision    小模型实时写的初始值
model     离线大模型整理
panel     面板人工修改
```

面板改了字段时：

```text
meta_source = panel
meta_status = reviewed
```

离线复盘跳过 `meta_source=panel`，避免覆盖人工结果。

### evidence

只放用户提供的上下文：

```text
用户说“这是奶龙”
用户说“这张叫..."
用户对这张图的补充描述
```

不放：

```text
小模型生成的 category/caption/facets
大模型之前生成的语义
```

离线复盘只读 `evidence`，不读已填语义字段。

### review_version

每收到一次新 evidence 就加一。

用于判断：

```text
这条 reviewed 之后有没有新信息
有新信息 → 重新进入 pending_review
```

## 3. 实时收藏

```text
图片收藏
  → 小模型给 category/caption/facets
  → 写入普通字段
  → meta_status=pending_review
  → meta_source=vision
  → 表情立即可搜、可发
```

小模型只是初始值，不是最终语义。

## 4. 离线复盘

```text
选 meta_status=pending_review
  → 取图片本体
  → 取 evidence 里的用户原话
  → 不把现有 category/caption/facets/label 放进 prompt
  → 大模型独立判断
  → 写正式字段
  → meta_status=reviewed
  → meta_source=model
  → last_review_at=now
```

### 为什么不让大模型看已填字

如果小模型把图认成“普通卡通角色”，大模型看到这个描述后可能被锚定，不再认真看图。

所以：

```text
小模型结果只用于实时兜底
离线复盘从图片重新判断
```

### 复盘失败

```text
没有有效 JSON
  → 不清空旧字段
  → 保持 pending_review
  → 下次再试
```

## 5. 迟到的解释

问题：

```text
先发图
  → 小模型先填
  → 离线复盘可能已经跑完，status=reviewed

后来说“这是奶龙”
  → 如果 reviewed 是终态
  → 新信息就丢了
```

所以 `reviewed` 不能是终态。

### 关联最近表情

bridge 保存：

```text
last_sticker[chat_key] = {
  ref: "file:unsorted/u_xxx.jpg",
  ts: ...
}
```

图片收藏后写入，过期时间建议 30 分钟。

后续用户发文字时，如果存在未过期的 `last_sticker`：

```text
把文字追加到该表情的 evidence
review_version += 1
meta_status = pending_review
```

即使它之前是 `reviewed`，也要重新打开。

### 不重复消费同一句话

同一条用户消息只追加一次：

```text
message_id / seq 去重
```

### 不覆盖面板结果

```text
meta_source=panel
  → 追加 evidence 可以
  → 不自动重新排队
  → 不覆盖人工字段
```

否则人工改完会被离线模型改回去。

### 超出窗口

```text
last_sticker 已过期
  → 不自动关联
  → 用户明确说“刚才那张/叫奶龙的那张”时，由模型或面板处理
```

不做无限期自动猜测。

## 6. 实时和离线的边界

```text
实时小模型
  只负责“先有一版”
  不负责最终命名

离线大模型
  只负责“最终语义”
  不看小模型结果

面板
  人工覆盖
  优先级最高
```

搜索时：

```text
pending_review 也参与搜索
reviewed 优先
panel 最高
```

## 7. 要改的地方

### 7.1 索引

`qqbot/domains/media/library.py`：

- 新增 `meta_status`
- 新增 `meta_source`
- 新增 `review_version`
- 新增 `evidence`
- 新增 `last_review_at`
- `index_add` 保留已有状态，不被自动收藏重置
- 提供两个显式操作：

```text
mark_pending(rel, evidence)
mark_reviewed(rel, fields, source="model")
```

### 7.2 实时收藏

`qqbot/domains/media/stickers.py`：

- 小模型结果继续写入普通字段
- 写入时设置：

```text
meta_status = pending_review
meta_source = vision
```

- 不要求小模型写 label

### 7.3 复盘写入

`qqbot/domains/media/meta.py`：

- `apply_record` 写字段后设置：

```text
meta_status = reviewed
meta_source = model
```

- 如果 `meta_source=panel`，拒绝自动覆盖

### 7.4 bridge

`bridge.py`：

- 收藏图片后记录 `last_sticker[chat_key]`
- 后续文本追加到对应表情的 `evidence`
- 有新 evidence 时：

```text
review_version += 1
meta_status = pending_review
```

- 新复盘 loop 取代 `sticker_enrich_loop`
- 复盘 prompt 必须附图片
- 复盘 prompt 不能带现有语义字段

### 7.5 废弃旧 loop

当前 `sticker_enrich_loop`：

- 只处理 caption 为空
- 只给文本，不给图片
- 会把旧语义拼进 prompt

新工作流启用后废弃。

`enrich_stickers` 也不能再直接写语义；它最多负责收集 evidence，或整个移除。

### 7.6 面板

`panel_readers.py` / `web/app.js`：

- 显示 `meta_status`
- 待整理 / 已整理
- 面板编辑设置：

```text
meta_source = panel
meta_status = reviewed
```

### 7.7 工具

`plugins/dsh-remembers/tools/memes.mjs`：

- `sticker_meta` 可以继续支持实时补写
- 写回时标记 `meta_source=model`
- 不强制实时调用

## 8. 验收

```text
发图后立刻能搜到
待整理数量可统计
离线复盘不看已填语义
复盘后 reviewed
迟到解释能把 reviewed 重新打开
重复消息不重复追加 evidence
面板修改不被离线覆盖
```

测试场景：

```text
1. 先发图，后说“这是奶龙”
   → 复盘能拿到“这是奶龙”

2. 先发图，不说
   → 先 pending，复盘后 reviewed

3. 复盘后再说“这是奶龙”
   → evidence 增加，status 回到 pending
   → 再次复盘使用新解释

4. 面板改 label
   → source=panel
   → 离线不覆盖

5. 同一条“这是奶龙”重复送到
   → evidence 只追加一次
```

## 9. 结论

```text
不需要 provisional
状态用 pending_review / reviewed
reviewed 可因新 evidence 重新打开
复盘不看已填语义，只看图片 + 用户原话
```

这样实时性和离线整理可以共存，也不会因“已经整理过”丢掉后来的解释。
