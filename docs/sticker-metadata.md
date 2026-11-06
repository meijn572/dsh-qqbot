# 表情元数据与定时复盘

状态：方案，未实现。

## 1. 目标

`rel` 是表情的唯一索引。

每次表情出现，记录一段“包含这张表情的对话记忆”，而不是只记同一批的一句文本。

```text
实时
  小模型先填一版
  meta_status=pending_review
  表情马上可搜、可发

定时
  取新出现的表情
  按 rel 去重
  用 rel 周围的记忆文本复盘
```

不设 `provisional_*`，不设 `manual`，不按单条 `review_due` 排队。

## 2. 两个概念

### index entry

一张表情只有一条：

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
  "reviewed_at": 0
}
```

### occurrence

这张表情每出现一次，就有一条。

occurrence 不存语义结论，只存：

```text
rel
出现位置
一段原始记忆文本
```

## 3. occurrence 的结构

```json
{
  "rel": "unsorted/u_xxx.jpg",
  "chat_key": "private:1215258939",
  "anchor": {
    "message_id": "msg-123",
    "ts": 1793890000,
    "image_index": 0
  },
  "window": {
    "start_ts": 1783889820,
    "end_ts": 1783890120
  },
  "messages": [
    {
      "message_id": "msg-120",
      "ts": 1783889990,
      "role": "user",
      "speaker": "九歌",
      "text": "这个是奶龙吗",
      "relation": "before"
    },
    {
      "message_id": "msg-123",
      "ts": 1783890000,
      "role": "user",
      "speaker": "九歌",
      "text": "",
      "relation": "anchor"
    },
    {
      "message_id": "msg-125",
      "ts": 1783890010,
      "role": "assistant",
      "speaker": "洄",
      "text": "原来这个叫奶龙",
      "relation": "after"
    }
  ]
}
```

### anchor

```text
message_id   图片所在消息
ts           出现时间
image_index  一条消息里第几张图
```

这样能表示：

```text
表情出现在这段对话的什么位置
```

### window

按时间取，不按消息条数。

默认：

```text
before_seconds = 180
after_seconds = 120
```

原因：

```text
同样 6 条消息
可能只隔 10 秒
也可能横跨 2 小时
```

时间窗口更接近“当时聊了什么”。

### messages

只存原始对话：

```text
user / assistant
speaker
text
message_id
ts
relation: before | anchor | after
```

不存：

```text
小模型生成的 caption/facets
大模型生成的语义
模型总结
bridge-note
```

### 为什么这比“上下文”纯

这里存的是**原始记忆文本**：

```text
谁在什么时候说了什么
```

不是模型加工后的“上下文摘要”。

模型复盘时自己判断哪些消息相关，代码不预先解释。

## 4. 时间窗口

### 取法

```text
anchor.ts - before_seconds
anchor.ts + after_seconds
```

从 bridge 维护的原始对话窗口取（与 L0 同源，额外保留 message_id）。

### 上限

时间窗口可能太长，需要安全上限：

```text
最多 20 条消息
最多 2000 字
```

超限时优先保留：

```text
1. anchor
2. 离 anchor 最近的消息
3. batch 文本
```

时间仍然是选择依据，消息数/字数只是保险。

### 去重

同一条消息可能进入多个 occurrence。

合并时按：

```text
chat_key + message_id
```

去重。

同一条消息只保留一份。

anchor 独立保存：

```text
occurrence.anchor
```

即使消息文本被合并，也知道表情在哪条消息里出现。

## 5. 实时收藏

```text
图片收藏
  → 小模型给 category/caption/facets
  → meta_status=pending_review
  → meta_source=vision
  → 记录 occurrence
```

occurrence 在图片解析出 rel 后写入。

不依赖模型调用工具。

## 6. 定时复盘

### 窗口

```text
默认每 12 小时一次
可配置
```

取上次复盘后新出现的 occurrence：

```text
按 rel 分组
每张只复盘一次
```

### 选择

```text
pending_review
  未复盘
  模型看不到现有字段

reviewed
  已复盘
  模型可以参考现有字段
```

两种情况都进入复盘。

### prompt

#### pending_review

```text
图片
+ 原始记忆文本
+ anchor 位置

不给：
category / caption / facets / label
```

#### reviewed

```text
图片
+ 现有 category/caption/facets/label
+ 新的原始记忆文本
+ anchor 位置

让模型决定是否修正
```

### 写回

```text
有效输出
  → 覆盖字段
  → meta_status=reviewed
  → meta_source=model
  → reviewed_at=now

changed=false
  → 不写字段
  → 只更新 reviewed_at
```

## 7. 解释和再次发送

不需要独立的“迟到解释机制”。

所有出现都走 occurrence。

### A. 发完就解释

```text
图 + “这是奶龙”
```

同一时间窗口内，messages 自然包含：

```text
relation=anchor 的图片消息
relation=after 的“这是奶龙”
```

### B. 第一次没解释，后来再次发同一张并解释

第一次：

```text
图片，没解释
```

第二次：

```text
同一张图 + “这是奶龙”
```

hash / 签名命中同一个 rel：

```text
第二条 occurrence 也指向同一个 rel
```

下一次复盘把两条 occurrence 的 messages 合并：

```text
第一条：before / anchor
第二条：before / anchor / after
```

如果已经是 reviewed：

```text
模型参考旧字段
再做增量修正
```

不需要：

```text
last_sticker
30 分钟窗口
状态改回 pending_review
```

### 其他情况

```text
很久以后只发文字，没有再发图
不同图但同一角色
```

不做自动关联。

## 8. 面板

面板修改：

```text
meta_status=reviewed
meta_source=panel
```

不做不可覆盖。

下一轮复盘可以看到并参考面板字段，也可以修改。

## 9. 要改的地方

### 9.1 library.py

index 增加：

```text
meta_status
meta_source
reviewed_at
```

不再在 index 里存 evidence。

新增 occurrence 存储：

```text
append_occurrence(rel, chat_key, anchor, window, messages)
load_occurrences(rel, since)
```

### 9.2 stickers.py

- `collect_sticker` 返回 rel
- 命中已有 rel 也返回
- 收藏成功后触发 occurrence 记录
- occurrence 的 rel 来自 hash / 签名，不由模型提供

### 9.3 bridge.py

- 图片解析出 rel 后记录 occurrence
- 记录 anchor：

```text
message_id
ts
image_index
```

- 按时间窗口取 bridge 原始对话窗口
- 记录 user / assistant 的 message_id
- 在 L0 中保留消息 ID，才能按 ID 去重

### 9.4 复盘 loop

- 新 loop 取代 `sticker_enrich_loop`
- 必须附图片
- pending 不带现有字段
- reviewed 带现有字段
- 按 rel 合并 occurrence
- 合并时按 `chat_key + message_id` 去重

### 9.5 旧 loop

```text
sticker_enrich_loop 废弃
enrich_stickers 不再直接写语义
```

### 9.6 面板

- 显示 `meta_status`
- 编辑后写 `meta_status=reviewed`
- `meta_source=panel`
- 不阻止后续复盘

### 9.7 工具

`sticker_meta` 可以继续实时补写：

```text
meta_status=reviewed
meta_source=model
```

不强制调用。

## 10. 成本

每张独特表情一次调用：

```text
1 张图
+ 原始记忆文本（最多 2000 字）
+ 200 字以内输出
```

默认 12 小时一次，按 rel 去重。

控制：

```text
每轮最多 20 张
同一 rel 只复盘一次
changed=false 不写
```

## 11. 验收

```text
rel 是唯一索引
occurrence 记录 anchor 位置
window 按时间取
messages 只存原始对话
合并 occurrence 时按 message_id 去重
pending_review 看不到现有字段
reviewed 可以看到现有字段
changed=false 不写
面板修改下一轮可参考
```

测试：

```text
1. 发图后 5 秒内说“这是奶龙”
   → before/after 能取到
   → 复盘使用

2. 第一次发图没解释
   中间很多对话
   第二次发同一张并说“这是奶龙”
   → 两条 occurrence 合并
   → 第二条带解释
   → 复盘使用

3. 发图前正在聊 KPL
   → before 里有 KPL 上下文
   → 复盘能看到

4. 同一句话出现在两个 occurrence
   → 合并时只保留一份

5. 很长时间后只发文字
   → 不自动关联

6. 面板改 label
   → 下一轮 reviewed 可参考
```

## 12. 结论

```text
rel 唯一索引
occurrence 记录出现位置
evidence 改成时间窗口内的原始记忆文本
不存模型总结
按 message_id 去重
定时复盘统一处理
不需要独立迟到机制
```
