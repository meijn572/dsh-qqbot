# 表情元数据与定时复盘

状态：方案，未实现。

## 1. 目标

实时只负责“能用”，定时复盘负责“整理好”。

```text
实时
  小模型先填一版
  meta_status=pending_review
  表情马上可搜、可发

定时
  取这段时间新出现的表情
  按 rel 去重
  每张复盘一次
  pending_review → 不看现有字段
  reviewed       → 可以参考现有字段
```

不设 `provisional_*`，不设 `manual`，不按单条 `review_due` 排队。

## 2. 数据结构

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
  "evidence": [
    {"text": "这是奶龙", "ts": 1793890000}
  ],
  "reviewed_at": 0
}
```

### meta_status

```text
pending_review   未复盘
reviewed         已复盘
```

只决定复盘时模型能不能看到现有字段。

### meta_source

```text
vision    小模型实时写的
model     定时复盘写的
panel     面板手写的
```

只用于审计，不阻止后续复盘。

面板手写：

```text
meta_status = reviewed
meta_source = panel
```

下一轮复盘仍然会看到这些字段，并且可以修改。

### evidence

只放用户提供的上下文：

```text
“这是奶龙”
“这张叫...”
“这是刚才那个...”
```

不放：

```text
小模型生成的 category/caption/facets
复盘模型之前生成的字段
```

最多保留 10 条，按 message_id 去重。

### reviewed_at

最后一次复盘时间。

没有 `review_version`，定时窗口本身负责控制复盘次数。

## 3. 实时收藏

```text
图片收藏
  → 小模型给 category/caption/facets
  → 写入普通字段
  → meta_status=pending_review
  → meta_source=vision
  → 立即可搜、可发
```

小模型结果只是初始值。

### 3.1 occurrence 是什么

occurrence 是“一次表情出现”的记录，不是表情索引条目。

```json
{
  "rel": "unsorted/u_xxx.jpg",
  "evidence_text": "这是奶龙",
  "message_id": "msg-123",
  "chat_key": "private:1215258939",
  "ts": 1793890000
}
```

区别：

```text
index entry   一张表情只一条
occurrence    这张表情每出现一次就一条
```

例如同一张图发了三次：

```text
index:
  unsorted/u_xxx.jpg

occurrences:
  u_xxx 第 1 次，无文本
  u_xxx 第 2 次，“这是奶龙”
  u_xxx 第 3 次，无文本
```

定时复盘时：

```text
按 rel 合并
evidence 合并
只复盘一次
```

“普通 occurrence”就是：

```text
不管第一次、第二次还是很久以后
只要是图片出现，就记一条
走同一套定时复盘
```

没有单独的“迟到解释”记录类型。

## 4. 定时复盘

### 窗口

```text
默认每 12 小时一次
可配置
```

每次取上次窗口之后的新表情出现记录：

```text
occurrences since last_review_at
→ 按 rel 去重
→ 每个 rel 只复盘一次
```

不扫全部历史，不重复复盘没有再次出现的表情。

### 选择

```text
pending_review
  未复盘过
  复盘时隐藏现有字段

reviewed
  已复盘过
  复盘时可以参考现有字段
```

两种情况都会进入复盘。

### prompt

#### pending_review

```text
图片
+ evidence 里的用户原话

不给：
category / caption / facets / label
```

#### reviewed

```text
图片
+ 现有 category/caption/facets/label
+ 新的 evidence

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

### 失败

```text
没有有效 JSON
  → 不清空旧字段
  → 保持原状态
  → 下次再试
```

## 5. 状态和可见性

```text
pending_review
  → 模型看不到现有语义
  → 独立看图片判断

reviewed
  → 模型可以看到现有语义
  → 做增量修正
```

搜索不受状态限制：

```text
pending_review 也能搜到
reviewed 优先
```

## 6. 解释和再次发送

不需要独立的“迟到解释机制”。

所有出现都走同一套 occurrence：

```text
图片出现
→ 记录 rel
→ 记录本轮文本
→ 定时窗口统一复盘
```

### A. 发完就解释

合并窗口内：

```text
图 + “这是奶龙”
```

文本和图同批：

```text
occurrence.evidence += “这是奶龙”
```

### B. 第一次没解释，后来再次发同一张并解释

第一次：

```text
图，没解释
```

第二次：

```text
同一张图 + “这是奶龙”
```

hash / 感知签名命中已有 rel：

```text
occurrence 指向同一个 rel
evidence += “这是奶龙”
```

下一轮复盘会看到这条新 occurrence。

如果之前已经是 `reviewed`：

```text
可以看到旧字段
参考旧字段做增量修正
```

不需要 `last_sticker`，不需要把状态改回 `pending_review`。

### 其他情况

```text
很久以后只发文字，没有再发图
不同图但同一角色
```

不做自动关联。

交给模型明确引用或面板处理。

### 重复

同一条消息只追加一次 evidence：

```text
message_id 去重
```

## 7. 面板

面板修改后：

```text
meta_status=reviewed
meta_source=panel
```

不需要“不可覆盖”。

下一轮复盘：

```text
可以看到面板写的字段
可以作为参考
可以修改
```

如果担心手工结果被改，应该在面板里再改一次，不引入新的保护状态。

## 8. 要改的地方

### 8.1 library.py

新增字段：

```text
meta_status
meta_source
evidence
reviewed_at
```

新增操作：

```text
attach_evidence(rel, text, message_id)
mark_reviewed(rel, fields, source)
```

`index_add` 保留已有状态，不因为自动收藏重置。

### 8.2 stickers.py

- `collect_sticker` 接收本轮 evidence 文本和 message_id
- 命中已有 rel 时调用 `attach_evidence`
- 新图返回 rel
- 新图初始状态：

```text
meta_status=pending_review
meta_source=vision
```

### 8.3 meta.py

`apply_record` 写回时：

```text
meta_status=reviewed
meta_source=model
reviewed_at=now
```

不再有 panel 保护分支。

### 8.4 bridge.py

- 收藏图片 / 再次发送时记录 occurrence
- occurrence 至少包含：

```text
rel
evidence_text
message_id
ts
```

- 新增定时复盘 loop
- 复盘时必须附图片
- pending_review 不带现有字段
- reviewed 带现有字段

### 8.5 废弃旧 loop

```text
sticker_enrich_loop 废弃
enrich_stickers 不再直接写语义
```

旧 loop 的问题：

- 只处理 caption 为空
- 不给图片
- 会把旧语义拼进 prompt

### 8.6 面板

- 显示 `meta_status`
- 编辑后写 `meta_status=reviewed`
- 写 `meta_source=panel`
- 不阻止后续复盘

### 8.7 工具

`sticker_meta` 可以继续实时补写：

```text
写回 meta_status=reviewed
meta_source=model
```

不强制在聊天里调用。

## 9. 成本

每张独特表情一次调用：

```text
1 张图
+ 少量 evidence
+ 200 字以内输出
```

默认 12 小时一次，按 rel 去重。

控制项：

```text
每轮最多 20 张
reviewed 且 changed=false 不写
同一 rel 只复盘一次
```

如果一天新增 10–20 张独特表情，成本很小。

## 10. 验收

```text
实时收藏后能搜到
定时窗口按 rel 去重
pending_review 看不到现有字段
reviewed 可以看到现有字段
复盘后 reviewed
changed=false 不写字段
再次发送的解释能进入 evidence
同一条消息 evidence 不重复
面板修改后下一轮仍可被参考
```

测试：

```text
1. 发图后紧接着说“这是奶龙”
   → evidence 带上
   → 复盘使用

2. 第一次发图没解释
   第二次发同一张并说“这是奶龙”
   → 命中原 rel
   → evidence 带上
   → 复盘使用

3. 很久以后只发文字
   → 不自动关联

4. 不同图但同一角色
   → 只处理当前图

5. 面板改 label
   → meta_source=panel
   → 下一轮 reviewed 可参考

6. 同一张图在窗口内出现多次
   → 按 rel 去重，只复盘一次
```

## 11. 结论

```text
唯一复盘方式：定时窗口 + rel 去重
不管复盘过没有，都进入复盘
状态只控制模型能不能看现有字段
再次发送的解释走普通 occurrence
不需要独立迟到机制
面板修改只标 reviewed，不做不可覆盖
```

实时性由小模型和意图明显时的工具调用保证，复盘低频运行即可。
