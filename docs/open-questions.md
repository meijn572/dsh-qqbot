# 未解决问题

状态：持续维护。

只记录还没定或还没做的问题。

已完成的事情去 [当前改动计划](plan.md)；历史决策去 [重构计划](refactor-plan.md)。

## 1. 记忆寿命

### L1

```text
目标：30–90 天
当前代码：180 天
```

需要统一决定：

```text
L1 是会话段总结，不是长期事实
180 天可能太长
```

### L2

```text
目标：7–30 天
当前：未实现
```

### L3

```text
目标：90 天
open 期间是否衰减？
dormant 后多久清理？
```

### L4

```text
不衰减
```

先记录，后面统一调。

## 2. L3 的边界

### 可以跨对话，但不强制

已确认：

```text
单段内完成 → 可以 closed
跨段继续 → open → 后续 closed
```

当前 prompt 没有强制跨对话。

### 一条 L3 只记一件事

已写进 prompt：

```text
一条 new 只能写一件事
多个事件拆多条
```

但还没有代码级校验。

风险：

```text
模型可能把两件事写进一条
title 只覆盖其中一件
evidence 混在一起
```

### L3 重要性

当前是轻门槛：

```text
有前因后果
或之后可能接着提
```

没有硬阈值。

风险：

```text
普通但有下文的事会被记
模型可能过度建 L3
```

需要观察真实会话后再决定是否加门槛。

## 3. evidence

### 跨多条 L0

当前 `match_evidence` 是逐条 L0 匹配。

如果 evidence 跨两条消息：

```text
主人：……
我：……
```

可能匹配失败，变成 unverified。

需要支持窗口拼接匹配。

### 多段 evidence

一条 L3 的 evidence 可能来自多个会话段。

当前存的是 L0 id 并集，但没有记录：

```text
哪条 evidence 属于哪一段
```

## 4. L2 判断层

```text
L2 由谁写
confidence 怎么校准
是否参与默认检索
被证实后怎么升级
是否显示在面板
```

当前未实现。

## 5. L4

```text
每 3 天一次
closed L3 → 0–2 条
```

已定。

还没定：

```text
L4 的 importance 是否需要单独字段
L4 是否要人工确认
L4 和 persona 的边界
```

## 6. memory_links

已建表并自动写入：

```text
L1 → L0
L3 → L1 / L0
L4 → L3
```

未解决：

```text
旧 L1/L3 的 links 没有回填
L3 续写时是否要记录“新增了哪些 evidence”
memory_links 和 source_ids 不一致时如何修复
```

## 7. 旧数据

```text
L1：128 条 legacy
L3：16 条 batch，thread_status = legacy
L4：4 条 legacy，source_ids 空
```

需要决定：

```text
旧 L1 是否重算 source_ids
旧 L3 是否补 thread_title / status
旧 L4 是否补 evidence
```

## 8. 检索与注入

```text
open L3 全量索引，最多 8 条
open 详情 top K
closed 按相关召回
```

未解决：

```text
open 优先级权重
closed 和 open 的分数怎么合并
索引太长时怎么截断（当前靠 open 上限 8）
```

## 9. 优先级

```text
P1：L3 混写 / 重要性
P2：evidence 跨窗口
P3：L1 寿命
P4：L2 判断层
P5：旧数据回填
```

先记录，不急着改。
