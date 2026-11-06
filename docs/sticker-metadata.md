# 表情元数据与定时复盘

状态：方案，未实现。

## 1. 目标

`rel` 是表情的唯一索引。

每次表情出现，记录一段“包含这张表情的原始对话”，不再用 `before / anchor / after` 这类 relation 标签。

```text
实时
  小模型先填一版
  meta_status=pending_review
  表情马上可搜、可发

定时
  取新出现的表情
  按 rel 去重
  用完整的消息流复盘
```

不设 `provisional_*`，不设 `manual`，不按单条 `review_due` 排队。

## 2. index entry

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

## 3. occurrence

occurrence 是“一次表情出现”的记录。

```json
{
  "rel": "unsorted/u_xxx.jpg",
  "chat_key": "private:1215258939",
  "run_id": "bridge-run-xxx",
  "window": {
    "start_ts": 1783889820,
    "end_ts": 1783890120
  },
  "messages": [
    {
      "seq": 11,
      "message_id": "msg-120",
      "ts": 1783889990,
      "role": "user",
      "speaker": "九歌",
      "text": "这个是奶龙吗",
      "images": []
    },
    {
      "seq": 12,
      "message_id": "msg-123",
      "ts": 1783890000,
      "role": "user",
      "speaker": "九歌",
      "text": "",
      "images": [
        {"rel": "unsorted/u_xxx.jpg"}
      ]
    },
    {
      "seq": 13,
      "message_id": "msg-125",
      "ts": 1783890010,
      "role": "assistant",
      "speaker": "洄",
      "text": "原来这个叫奶龙",
      "images": []
    }
  ]
}
```

### 关键点

```text
图片消息本身就在 messages 里
不再有 relation 字段
不再有单独的 anchor 字段
```

图片的位置由它所在的 `seq` 决定。

### occurrence 是存储结构，不是 prompt

occurrence 里的 JSON 只给代码用。

不要直接把这段 JSON 塞给模型：

```json
{
  "messages": [...],
  "seq": 11,
  "images": [...]
}
```

模型看到的应该是拼好的、容易读的时间线：

```text
[#11] 九歌：这个是奶龙吗
[#12] 九歌：[图片：unsorted/u_xxx.jpg]
[#13] 洄：原来这个叫奶龙
[#14] 九歌：那再发一张
[#15] 九歌：[图片：unsorted/u_xxx.jpg]
```

规则：

```text
每条消息一行
显示 seq、说话人、文本
有图片就加 [图片：rel]
没有文本只有图片，就只显示图片行
不显示 message_id
不显示 JSON 字段名
```

如果有缺口：

```text
[#20] 九歌：...
（中间有 8 条消息未纳入）
[#29] 九歌：...
```

模型需要同时看到图片本体和这条时间线：

```text
图片附件
+ 文本时间线
+ 当前是否 reviewed
+ 如果 reviewed，才附现有字段
```

图片本体负责“看清是什么”，时间线负责“出现在什么位置、周围说了什么”。

### 渲染函数

复盘前统一调用：

```text
render_occurrence_timeline(occurrences)
```

职责：

```text
1. 按 chat_key + run_id + seq 去重
2. 按 seq 排序
3. 同一 run 连续/重叠 → 合并
4. 有缺口 → 插入缺口标记
5. 输出纯文本时间线
```

不要把这个渲染逻辑分散在 prompt 字符串里。

### seq

`seq` 是 bridge 自己的消息顺序，不是 QQ 的 `message_id`。

```text
user 消息收进来：seq += 1
assistant 消息发出去：seq += 1
```

`message_id` 只用于入站事件去重和审计，不用于排序，也不作为 occurrence 的唯一键。

### seq 怎么维护

bridge 启动时生成一个：

```text
run_id = uuid()
```

每个 chat 维护自己的计数器：

```text
chat_key -> next_seq
```

规则：

```text
1. 每条入站用户消息分配一个 seq
2. 一条消息里有多张图，仍然只占一个 seq
3. 每条发出的 assistant 消息分配一个 seq
4. seq 在分配时同步 +1，不等待网络请求
5. 同一 chat 内不重复
6. bridge 重启后 seq 归零，但 run_id 变化
```

伪代码：

```python
def next_seq(chat_key):
    seq = CHAT_SEQ.get(chat_key, 0) + 1
    CHAT_SEQ[chat_key] = seq
    return seq
```

这条赋值中间没有 await，所以同一个事件循环里不会并发拿到同一个 seq。

### 入站重复事件

OneBot 可能重复投递同一条消息。

在分配 seq 之前先按：

```text
chat_key + message_id
```

去重。

通过后再：

```text
seq = next_seq(chat_key)
```

这样：

```text
message_id 负责“这条事件是不是重复”
seq 负责“这条消息在消息流里的位置”
```

### 图片消息

一条图片消息只分配一个 seq。

```json
{
  "seq": 12,
  "message_id": "msg-123",
  "images": [
    {"rel": "happy/a.jpg"},
    {"rel": "sad/b.jpg"}
  ]
}
```

多张图共享同一个 seq，用 `image_index` 区分是哪一张触发的 occurrence。

### 跨 run

```text
run_id 不同
seq 不能直接比较
```

复盘时：

```text
同一 run_id：按 seq 排序、判断连续
不同 run_id：按 ts 排序，作为不同段落
```

### 去重

同一条消息按：

```text
chat_key + run_id + seq
```

去重。

不是按文本去重。

`message_id` 只作为可选审计字段保留。

### run_id

bridge 重启后 `seq` 会重新开始。

occurrence 记录 `run_id`：

```text
不同 run 的 occurrence
不按 seq 直接拼接
```

跨 run 时按时间窗口展示，避免把两次运行的消息错连。

## 4. 时间窗口

每个 occurrence 围绕图片消息取：

```text
before_seconds = 180
after_seconds = 120
```

从同一 `chat_key` 的 bridge 原始对话窗口取。

### 上限

```text
最多 20 条消息
最多 2000 字
```

超限时优先保留：

```text
1. 图片消息
2. 离图片最近的消息
```

### 去重

同一条消息按：

```text
chat_key + run_id + seq
```

去重。

不是按文本去重。

`message_id` 只用于入站事件去重和审计，不参与 occurrence 合并。

### 图片消息

图片消息也进入 messages，`images` 里记录 `rel`。

一条消息多张图：

```json
"images": [
  {"rel": "happy/a.jpg"},
  {"rel": "sad/b.jpg"}
]
```

## 5. 多个 occurrence 合并

定时复盘按 `rel` 分组后，把所有 occurrence 的 messages 合并。

### 合并规则

```text
1. 先按 chat_key + run_id + seq 精确去重
2. 同一 run_id 内按 seq 排序
3. 同一 run_id 内，seq 连续或重叠 → 合并成一条连续时间线
4. seq 有缺口 → 不假装连续，保留缺口标记
5. 不同 run_id → 按时间排序，作为不同段落
```

### 差 1 的情况

你说的“两段没有重合，但正好连起来”：

```text
A 的最后一条 seq = 20
B 的第一条 seq = 21
```

应该合并。

```text
中间没有缺失消息
用户看到的就是连续对话
```

规则：

```text
next.seq <= current.max_seq + 1 → 合并
next.seq > current.max_seq + 1 → 有缺口，不按连续合并
```

注意：

```text
这里的 +/-1 是 bridge 的 seq
不是 QQ 的 message_id
```

QQ 的 `message_id` 不保证递增，不能拿来判断相邻。

### 有缺口时

不要静默拼接成连续对话。

保留：

```text
[seq 20] ...
[... 中间有 8 条未纳入 ...]
[seq 29] ...
```

这样模型知道中间有省略。

## 6. 定时复盘

### 频率

```text
默认每 12 小时一次
可配置
```

每次取上次复盘后新出现的 occurrence。

```text
按 rel 分组
每个 rel 只复盘一次
```

### 可见性

```text
pending_review
  未复盘
  模型看不到现有字段

reviewed
  已复盘
  模型可以参考现有字段
```

两种情况都进入复盘。

### prompt 里的时间线

不再显示 `[之前/之后]`，由 `render_occurrence_timeline` 生成消息流：

```text
[#11] 九歌：这个是奶龙吗
[#12] 九歌：[图片：happy/xxx.jpg]
[#13] 洄：原来这个叫奶龙
[#14] 九歌：那再发一张
[#15] 九歌：[图片：happy/xxx.jpg]
```

模型自己看图片和消息流判断。

不要把 occurrence 的 JSON 原样放进 prompt。

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

两条消息在同一时间窗口内，自然进入 messages。

### B. 第一次没解释，后来再次发同一张并解释

第一次 occurrence 只有图片和周围消息。

第二次发送时 hash / 签名命中同一个 rel，产生第二条 occurrence。

复盘时按 rel 合并：

```text
两条 occurrence 的消息按 seq 合并
中间有缺口就标出来
```

如果之前已经 reviewed：

```text
模型参考旧字段
再做增量修正
```

不需要 `last_sticker`，不需要状态改回 `pending_review`。

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

occurrence 存储：

```text
append_occurrence
update_occurrence_messages
pending_occurrences
mark_occurrences_reviewed
```

occurrence 里每个 message 必须有：

```text
seq
message_id
ts
role
speaker
text
images
```

### 9.2 bridge.py

- `CHAT_MEMORY` 记录 bridge 自己的 `seq`
- 图片消息也记录进 `CHAT_MEMORY`
- 收藏后按时间窗口取 messages
- occurrence 只保存原始消息流
- 移除 `before / anchor / after` 字段
- 合并时按 `seq` 判断连续/缺口
- 不同 `run_id` 不直接按 seq 拼

### 9.3 复盘 loop

- 新 loop 取代 `sticker_enrich_loop`
- 必须附图片
- pending 不带现有字段
- reviewed 带现有字段
- 按 rel 合并 occurrence
- 合并时按 `chat_key + run_id + seq` 去重
- 不再生成 relation 标签
- 新增 `render_occurrence_timeline`：结构化 occurrence → 纯文本时间线
- prompt 里放渲染后的文本，不放 occurrence JSON
- 图片附件单独传给模型

### 9.4 面板

- 显示 `meta_status`
- 编辑后写 `meta_status=reviewed`
- 写 `meta_source=panel`
- 不阻止后续复盘

## 10. 成本

每张独特表情一次调用：

```text
1 张图
+ 原始消息流（最多 2000 字）
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
图片消息本身在 messages 里
没有 relation 字段
按 seq 排序
按 chat_key + run_id + seq 精确去重
同 run 且 seq 连续 → 合并
seq 有缺口 → 保留缺口标记
不同 run 不直接拼接
pending_review 看不到现有字段
reviewed 可以看到现有字段
changed=false 不写
面板修改下一轮可参考
```

测试：

```text
1. 发图后 5 秒内说“这是奶龙”
   → 图片消息和文本在同一时间线
   → 复盘使用

2. 第一次发图没解释
   中间很多对话
   第二次发同一张并说“这是奶龙”
   → 两条 occurrence 合并
   → 中间缺口标记
   → 复盘使用

3. 两段窗口刚好首尾相接
   → seq 连续
   → 合并成一条时间线

4. 两段窗口中间少消息
   → 不假装连续
   → 保留缺口标记

5. 同一句话出现在两个 occurrence
   → 按 chat_key + run_id + seq 只保留一份

6. 面板改 label
   → 下一轮 reviewed 可参考
```

## 12. 结论

```text
rel 唯一索引
图片消息进入完整消息流
去掉 before / anchor / after
用 bridge seq 排序
用 chat_key + run_id + seq 精确去重
seq 连续或重叠 → 合并
seq 有缺口 → 保留缺口
不同 run → 不直接拼接
定时复盘统一处理
```
