# 记忆的忘记机制

状态：第一版已实现。L3 有 memorability / dominant；召回有 12 小时活跃期和间隔强化。

## 1. 现在的问题

当前忘记机制主要是固定半衰期：

```text
L1  30 天
L3  90 天
L4  不衰减
```

另外：

```text
L1 过期 → stale，不再默认召回
L3 open 太久 → dormant
```

问题：

```text
所有普通记忆按同一个速度衰减
重要的事和普通午饭没有区别
被反复想起的记忆不会变牢
刚聊完的事没有活跃期
未解决的事没有保护
```

## 2. 难忘性：模型只填一个数

### 结论

维度只出现在提示词里，让模型综合判断，输出一个：

```text
memorability  0–1
```

再附一个：

```text
dominant      最强维度
```

不要求模型分别填五个分数。

### 为什么

```text
多分数看起来精确，实际上模型给分不稳定
五个 0.7 和整体 0.7 往往不是一个意思
维度之间有相关性，拆开算会重复加权
单分数更接近人的“这件事我记不记得住”
```

维度仍然有用：

```text
写进提示词，作为判断的锚
存 dominant，方便以后解释和调参
不直接参与公式
```

## 3. 提示词里的维度

```text
importance       对我有多重要
emotion          当时情绪有多强
distinctiveness  有多反常、离奇、跟平时不一样
self_relevance   是否关于“我是谁、我怎么想”
relationship     是否关于我和主人的关系
```

这些只帮助模型判断，不需要逐项输出。

## 4. 评分锚点

```text
0.0–0.2  普通日常，过几天就淡
0.2–0.4  有点印象，但不会主动想起
0.4–0.6  值得留一段时间
0.6–0.8  很难忘，过很久还会提
0.8–1.0  身份、关系、底线级别的记忆
```

例子：

```text
午饭吃了什么
memorability 0.15
dominant none

半夜聊“给自己取名”
memorability 0.9
dominant relationship

刷到一个很离奇的视频
memorability 0.45
dominant distinctiveness

主人说“以后别在群里提我家里的事”
memorability 0.85
dominant importance
```

## 5. 输出

```json
{
  "memorability": 0.9,
  "dominant": "relationship"
}
```

`dominant` 取值：

```text
importance
emotion
distinctiveness
self_relevance
relationship
none
```

`dominant` 不参与衰减公式，只用于：

```text
解释为什么这条留得久
以后调权重
面板展示
```

## 6. 动态衰减

### 初始稳定度

```text
stability_days = 基础半衰期 × (0.5 + memorability)
```

基础：

```text
L1  30 天
L3  90 天
L4  不衰减
```

例子：

```text
L3 memorability 0.2 → 90 × 0.7 = 63 天
L3 memorability 0.9 → 90 × 1.4 = 126 天
```

### 召回后的活跃期

```text
active_until = last_recalled_at + 12 小时
```

活跃期内：

```text
retention = 1
不继续衰减
更容易被再次想起
```

但活跃期不增加长期稳定度。

### 间隔召回

只有满足：

```text
距离上次召回 >= max(6 小时, 0.5 × stability_days)
```

才算一次有效间隔召回。

有效召回：

```text
stability_days *= 1.6 ~ 2.0
recall_count += 1
```

加成递减：

```text
第 1 次 ×1.8
第 2 次 ×1.6
第 3 次 ×1.4
之后最多 ×1.2
```

短时间内反复提：

```text
只更新 active_until
不增加 stability_days
不增加 recall_count
```

这就是“刚聊完印象很热”，但不是“刻进长期记忆”。

### 未解决

```text
unresolved = 1
```

未解决期间：

```text
不归档
stability_days × 2
```

解决后：

```text
unresolved = 0
恢复普通衰减
```

## 7. 字段

先加在 L3：

```sql
memorability      REAL DEFAULT 0
dominant          TEXT DEFAULT ''
last_recalled_at  REAL DEFAULT NULL
active_until      REAL DEFAULT NULL
recall_count      INTEGER DEFAULT 0
stability_days    REAL DEFAULT NULL
unresolved        INTEGER DEFAULT 0
```

L1 可以只加：

```sql
last_recalled_at
recall_count
stability_days
```

L0 不加，原话不参与难忘性。

## 8. 分层

### L0

```text
不参与难忘性
30 天后冷存档
不删除
```

### L1

```text
短期总结
30 天基础
被 L3 引用过 → 延长
短时间反复提 → 只活跃，不续命
```

### L3

```text
主要算 memorability
90 天基础
难忘性高 / 间隔召回多 / 未解决 → 延长
```

### L4

```text
不衰减
但可以重新验证
情绪强、离奇，不等于 L4
```

## 9. 什么时候评分

不要每写一条 L1 都评分，太贵。

建议：

```text
L1 不评分
L1 → L3 时评一次
L3 重大改写时重评
```

B 站感悟也走同一套：

```text
有 insight 的 L3
在写入时给 memorability / dominant
普通 B 站 activity 不评
```

## 10. Prompt

```text
（内部维护，不要回复用户）

判断这条记忆有多难忘，只输出一个 0–1 的分数。

参考维度：
- importance：对我有多重要
- emotion：当时情绪有多强
- distinctiveness：有多反常、离奇、跟平时不一样
- self_relevance：是否关于“我是谁、我怎么想”
- relationship：是否关于我和主人的关系

评分锚点：
0.0–0.2 普通日常
0.2–0.4 有点印象
0.4–0.6 值得留一段时间
0.6–0.8 很难忘
0.8–1.0 身份、关系、底线级别

不要因为“离奇”就直接给高分；
离奇但和我无关，最多中等。

只返回 JSON：
{"memorability": 0.0, "dominant": "importance|emotion|distinctiveness|self_relevance|relationship|none"}
```

## 11. 参考

- 情绪与自传体记忆：[Emotion and Autobiographical Memory](https://pmc.ncbi.nlm.nih.gov/articles/PMC2852439/)
- 独特性 / von Restorff：[The subtlety of distinctiveness](https://reo.nii.ac.jp/oja/ART1002820354/en)
- 自我相关：[Personal relevance modulates encoding and retrieval](https://www.sciencedirect.com/science/article/pii/S1074742726000092)
- 闪回记忆：[Flashbulb memories](https://www.sciencedirect.com/science/article/abs/pii/0010027788900364)
- 间隔与提取练习：[Spacing and Testing Effects](https://www.sciencedirect.com/science/chapter/bookseries/abs/pii/S0079742110530032)

## 12. 开放问题

```text
12 小时活跃期是否合适
有效间隔的 6 小时门槛是否太低
stability 初始倍率 0.5 + memorability 是否合适
L1 要不要也评分
B 站 insight 的 memorability 由谁给
未解决状态从哪里同步
```

## 13. 结论

```text
难忘性维度只进提示词
模型输出一个 memorability + dominant
公式只用一个分数
召回看间隔，不看次数
12 小时内反复提不算强化
未解决单独保护
```
