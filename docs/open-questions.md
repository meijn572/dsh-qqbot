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

已确认：重要性是语义判断，不做硬编码阈值。

```text
有前因后果
或之后可能接着提
或出现结果/变化/承诺
```

由模型在 prompt 里判断。

不做：

```text
关键词打分
长度阈值
固定 importance 数值
```

风险仍然存在：

```text
普通但有下文的事会被记
模型可能过度建 L3
```

先观察真实会话，不急着加规则。

## 3. evidence

### 已定：ref 优先，原话兜底

模型输入时把所有可引用来源统一编号，不按层分组：

```text
[1] L0 主人：我牙疼
[2] L0 我：去看看
[3] L1 主人最近在看牙
[4] L2 他可能有点焦虑
```

模型只给编号：

```json
{
  "text": "牙疼，去看了，只是牙龈发炎",
  "source_refs": [1, 2, 3, 4]
}
```

代码维护：

```text
ref 1 → (L0, 708)
ref 2 → (L0, 709)
ref 3 → (L1, 710)
ref 4 → (L2, 711)
```

所以 ref 不只知道 L0，也知道层级。

### 为什么

```text
每次输入条数不多
本地 ref 短、可校验
比让模型抄长数据库 id 稳
比纯语句模糊匹配便宜
```

纯编号就够，不需要模型分类：

```text
模型只负责指“哪几条”
代码负责查“是哪一层”
```

### 怎么落库

```text
source_ids = 所有 L0 ref 的真实 id
memory_links = 全部直接输入（L0/L1/L2/L3）
```

L1：

```text
refs 通常全是 L0
```

L3：

```text
refs 可以混合 L0/L1/L2
source_ids 只取其中的 L0
```

L4：

```text
refs 只取 L3
source_ids 继承 L3 的 L0
```

### 已做

```text
L1 / L3 输入带统一编号
prompt 要求 source_refs
代码按 ref 映射 tier/id
ref 无效回退单条原话
```

### 剩余

```text
L4 仍按标题选，还没有 ref
旧数据没有 ref
```

### L0 仍然是一轮一条

```text
L0#1
主人：我牙疼
我：去看看
```

不需要拆 L0。

跨轮需要多个 ref：

```text
L0#1 → ref 1
L0#2 → ref 2
```

L3 混合来源：

```text
source_refs: [1, 2, 3]
1、2 是 L0
3 是 L1
```

`source_ids` 只取 1、2；`memory_links` 记 1、2、3。

### 多段 evidence

一条 L3 的 evidence 可能来自多个会话段。

当前存 L0 id 并集，没有记录“哪条属于哪一段”。

这是来源分段问题，不是匹配问题，暂时不展开。

## 4. L2 判断层

当前不急。

前提：

```text
L1 只写明确发生/明确说过的
不吸收助手推测
```

那 L2 只装：

```text
主人可能很累
他大概有点焦虑
```

这些是推断，不是主人明说的感受。

还没定：

```text
L2 由谁写
confidence 怎么校准
是否参与默认检索
被证实后怎么升级
是否显示在面板
```

如果以后不需要“推测层”，可以不做 L2；但不要把推测塞回 L1。

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
P1：L3 混写
P2：evidence 跨窗口
P3：L1 寿命
P4：L2 判断层
P5：旧数据回填
```

先记录，不急着改。
