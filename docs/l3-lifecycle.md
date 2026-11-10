# L3 生命周期与合并

状态：第一版已实现。候选池带 id，7 天自动复盘，支持 merge_into。

## 1. 要解决的问题

现在 L3 有三个问题。

### 1.1 同一串事件没有合并

```text
第一次说 → 新建 L3
后面再说 → 没有合适的候选
→ 又新建一条
```

原因：

```text
候选只取 open
standalone / closed / dormant 不参与续写
只按标题匹配，阈值 0.6
新建时 aliases 为空
模型只返回 title，不返回 id
```

### 1.2 open 会膨胀

如果“拿不准有没有后续”就标 open：

```text
open 越来越多
上下文放不下
每轮只能看前 8 条
后面的 open 实际上被藏起来
```

### 1.3 结束判断只能靠当下

创建时模型看不到未来，只能猜。

```text
有些事其实结束了
但当时只能说“可能还有后续”
```

只有过一段时间没提，才能判断。

## 2. 状态语义

```text
open        有明确下一步 / 等待结果 / 承诺 / 未解决
dormant     open 很久没提，可能结束，未确认
closed      确认结束，或长期无后续且判断应结束
standalone  单次片段，不等待后续
```

`standalone` 不是“结束”，也不是“没后续”。

它只是：

```text
这件事本身不需要下一步
```

## 3. 创建时怎么标

```text
明确结束 → closed
有明确下一步 / 承诺 / 等待结果 / 未解决 → open
一个瞬间、一次说完、一个想法、日常片段 → standalone
拿不准有没有下一步 → standalone
```

不要因为“以后可能有用”就标 open。

大部分事件应该是 standalone。

例子：

```text
牙疼，准备去看牙 → open
双选协议只打了一份，晚上再去 → open
等考研成绩 → open

半夜聊命名 → standalone
刷到一个讲消寒图的视频 → standalone
主人发了个揉揉肥鱼 → standalone
```

## 4. 每次 L3 提取

输入：

```text
当前对话段
全部 open L3（最多 10 条）
召回的 L3（其他状态，最多 8 条）
```

召回的 L3 包括：

```text
standalone
closed
dormant
```

这样同一件事即使上次是片段/已结束/很久没提，后面再提也能被更新。

## 5. open 超过 10

不要静默截断。

```text
open > 10
→ 先跑一次 lifecycle review
→ 模型对每条选：
   keep_open
   dormant
   close
   merge_into
→ 尽量降到 <= 10
```

如果复盘后还是超过 10：

```text
不硬删
注入时按 last_seen 取最近 10 条
其余在候选池里保留标题
```

不要因为上限把真正还在进行的事藏掉。

## 6. 每 7 天自动复盘

对象：

```text
open + 较老的 dormant
不是所有 L3
```

动作：

```text
open → keep_open / dormant / close / merge_into
dormant → keep_dormant / close / reopen
closed → 一般不动，除非有新证据
```

`closed` 不是永久锁死。

后面新提到，可以：

```text
closed → open
```

## 7. 复盘输入

```text
id
标题
摘要
当前状态
创建时间
最后提及时间
沉默天数
最近有没有相关提及
```

“最近有没有相关提及”：

```text
用标题 + 摘要关键词搜最近 30 天的 L0 / L1 / L3
有 → 给 1–3 条相关片段
没有 → 明确写「最近没有提到」
```

不要把所有记忆都塞进去。

## 8. 复盘输出

```json
{
  "items": [
    {
      "id": 12,
      "action": "keep_open|dormant|close|reopen|merge_into",
      "target_id": null,
      "reason": "为什么",
      "evidence_refs": [1]
    }
  ]
}
```

`merge_into` 时填 `target_id`。

## 9. merge_into

允许自动复盘把重复的 L3 合并。

```json
{
  "id": 456,
  "action": "merge_into",
  "target_id": 123,
  "reason": "同一件事的三个阶段"
}
```

合并动作：

```text
source_ids 合并到 primary
summary 取合并后的摘要
primary 保留
duplicate 标 merged_into=primary
duplicate 不再参与默认检索
```

不要物理删除。

## 10. 状态优先级

```text
1. 有明确结束证据 → close
2. 有新进展 → reopen / keep_open
3. 只是很久没提 → dormant
4. 长期进行中的事 → keep_open，不因为几天沉默就 close
5. standalone 不参与“是否结束”的判断
```

长期进行中的事：

```text
考研、找工作、健康恢复、关系问题
```

可以 dormant，但不要因为几天没提就 close。

## 11. 注入

### open 工作集

```text
最多 10 条
按 last_seen 排
每条：标题 + 一句话摘要 + 最后提及
```

### 召回 L3

```text
最多 8 条
其他状态
只给标题 + 摘要
```

```text
open 全部给
其他状态只给召回的
```

## 12. 数据字段

L3 加：

```sql
lifecycle_reviewed_at REAL DEFAULT NULL
status_reason        TEXT DEFAULT ''
merged_into          INTEGER DEFAULT NULL
```

已有：

```text
thread_status
thread_last_seen_at
thread_closed_at
thread_title
thread_aliases
source_ids
```

## 13. 调度

```text
每 7 天自动复盘一次
时间：07:00
对象：open + 较老 dormant
```

另外：

```text
open > 10 → 提取前先触发一次
```

## 14. Prompt

```text
（内部维护，不要回复用户）

下面是一些还没确认结束的事。请根据最后提及时间和最近有没有相关提及，判断它们现在的状态。

状态：
- open：有明确下一步、等待结果、承诺、未解决
- dormant：很久没提，可能结束，但没确认
- closed：确认结束
- standalone：单次片段，不等待后续，不是“结束”

规则：
- 不要因为几天没提，就结束长期进行中的事。
- 没有明确结束证据时，最多标 dormant，不要硬 close。
- 最近又提到的，标 reopen。
- standalone 不参与“是否结束”的判断。
- 拿不准就 keep_open。
- 同一件事的重复 L3 用 merge_into，target_id 指向保留的那条。

只返回 JSON：
{"items":[{"id":1,"action":"keep_open|dormant|close|reopen|merge_into","target_id":null,"reason":"...","evidence_refs":[1]}]}
```

## 15. 和忘记机制的关系

```text
lifecycle  这件事结束没有
forgetting 这条记忆还留多久
```

一个 `closed` 的 L3 仍然可以因为难忘性高而留很久。

一个 `open` 的 L3 也可以因为不重要而衰减。

不要用 `closed` 直接等于“可以忘”。

## 16. 迁移

```text
1. 加 lifecycle 字段
2. 创建时收紧 open 语义
3. 提取候选池加最近 L3
4. 模型按 id 更新
5. 加 7 天自动复盘
6. 加 open > 10 触发
7. 再跑一次已有重复 L3 的合并
```

## 17. 开放问题

```text
open 上限 10 是否合适
每 7 天一次是否够
dormant 多久转 closed
merge_into 的 primary 怎么选
closed 后多久允许 reopen
旧 L3 的重复怎么一次性合并
```
