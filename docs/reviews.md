# 复盘与合并

状态：合并方案暂缓（2026-11-08）。当前只新增词库复盘，其余复盘保持独立。

## 1. 现有复盘

| 复盘 | 时间 | 输入 | 输出 |
| --- | --- | --- | --- |
| 自我认知 | 每天 07:00 | 最近 24h L0、人格 | 一条自我变化或 SKIP |
| L2 复查 | 每天 07:00 | active L2 + 最近 L0/L1 | confirm / reject / keep |
| 关系复盘 | 每天 07:00 | L3 impact、open L3、L4、人格 | 一段关系 summary |
| 用户画像 | 每 2 天 07:00 | 50 L1 + 30 L3 + 50 L0 + 最近对话 | 画像五块 |
| 说话风格 | 每 3 天 07:00 | 最近对话、人格 | 风格提议 |
| L4 核心记忆 | 每 3 天 07:00 | closed / standalone L3 | 0–2 条核心记忆 |
| 人格复盘 | 每 30 天 07:00 | 人格、L3、画像 | 判断/关系/约定候选 |
| 日记 | 每天 23:00 | 当天 L0/L3/情绪 | 日记 |
| 情绪回看 | 私聊空闲 5 分钟 | 刚结束的一段 | emotion_log |
| 表情复盘 | 每 12h | 新表情图 | 表情语义 |
| 群黑话 | 已关闭 | 群日志 | 词库 |

## 2. 合并原则

只合并同时满足的：

```text
输入窗口相同
输出都很短
模块之间不需要互相引用
单个模块失败可以单独跳过
```

不满足的继续独立。

## 3. 合并成 daily reflection

每天 07:00 一次，包含四个模块：

```text
self_change     自我认知增量
relationship    关系 summary
l2              L2 复查
lexicon         词库增量
```

不合并：

```text
用户画像
说话风格
L4 核心记忆
人格复盘
日记
情绪回看
表情复盘
```

## 4. 输入

一次组装：

```text
最近 24h L0 / L1
最近 L3（含 relationship_impact）
open L3
active L2
当前 relationship summary
本段命中的旧词解释
人格（只读）
```

统一编号，给模型看自然语言：

```text
[1] 原话：……
[2] 你记得的事实：……
[3] 之前的事：……
[4] 你的判断：……
```

旧词单独列，不占编号：

```text
【本段出现的旧词】
蛋家军：喜欢奶蛋的人站队用的梗
```

## 5. Prompt 结构

先给证据，再给四个模块。

每个模块前写：

```text
只根据证据判断这个模块。
不要引用其他模块的结论。
没有内容就留空，不要为了填满 JSON 硬写。
```

### self_change

```text
只看：最近 24h 里有没有新的自我认知变化。
输出一条，或 SKIP。
不要总结关系，不要写用户。
```

### relationship

```text
只看：L3 relationship_impact + open L3 + 当前 summary。
输出 1–3 句关系站位。
没有新证据就保持原样。
```

### l2

```text
只看：active L2 + 最近证据。
confirm / reject / keep。
confirm 必须给确定的 fact。
```

### lexicon

```text
只看：本段命中的旧词 + 新出现的词。
旧词有新理解才 update；没有就空。
新词必须有 meaning，否则不进。
```

## 6. 输出

```json
{
  "self_change": "……或 SKIP",
  "relationship": {
    "summary": "……",
    "evidence_refs": [1, 2]
  },
  "l2": [
    {"ref": 1, "action": "confirm", "fact": "……"}
  ],
  "lexicon": {
    "updates": [
      {"term": "蛋家军", "meaning": "……", "example": "……"}
    ],
    "new": [
      {"term": "奶蛙", "meaning": "……", "kind": "meme"}
    ]
  }
}
```

## 7. 后台处理

按模块独立校验：

```text
self_change 空或 SKIP → 跳过
relationship 没 evidence → 不改
relationship summary 空 → 不改
l2 ref 无效 → 忽略该条
lexicon 新词没 meaning → 不新增
lexicon 旧词没新解释 → 只更新 last_seen
```

一个模块失败，不影响其他模块。

## 8. 会不会互相污染

输出短，污染概率比“画像 + 风格 + 核心记忆”混在一起小，但不是零。

主要风险：

```text
self_change 抄 relationship 的结论
relationship 被 self_change 的措辞带偏
lexicon 把关系判断当词义
```

控制：

```text
每个模块写“只根据……”
明确“不要引用其他模块的结论”
模块输出长度限制
后台分模块校验
发现漂移就拆出来
```

## 9. 什么时候跑

```text
每天 07:00 一次
没有新 L0/L1/L3 且没有 active L2/词库候选 → 跳过
```

关系模块没 impact 时，其他模块仍可跑。

## 10. 成本

现在：

```text
自我认知 1 次
L2 1 次
关系 1 次
词库 1 次（如果加）
= 4 次
```

合并后：

```text
1 次
```

输入会变长，但省掉 3 次调用和重复上下文。

## 11.  rollout

先合并四个，观察一周：

```text
self_change 是否有内容、是否漂
relationship 是否稳定
l2 是否漏判/硬判
lexicon 是否重复/乱收
```

如果某个模块明显变差：

```text
单独拆出来
其余继续合并
```

## 12. 不合并的理由

### 用户画像

```text
每 2 天
输出五块，很大
输入要 50 L1 + 30 L3 + 50 L0
```

容易抢注意力，也容易被当天情绪带偏。

### 说话风格

```text
每 3 天
输出是一份完整提议
```

和每天的四模块节奏不同。

### L4 核心记忆

```text
高 stakes
宁缺勿滥
```

不能为了“有输出”硬挑。

### 人格复盘

```text
30 天一次
改核心设定
```

必须单独、慢、可审。

### 日记

```text
23:00
第一人称、带情绪
```

时间、语气、目的都不同。

### 表情复盘

```text
要看图
```

不能和文本合并。

## 13. 开放问题

```text
daily reflection 的输出 token 上限
四个模块的先后顺序
关系模块没 impact 时是否还跑
词库旧词解释最多注入几条
合并后 self_change 是否更容易漂
```
