# B 站视频与复盘感悟

状态：设计稿，未改代码。L3 是否存储还没定。

## 1. 要解决的问题

现在 B 站看完只写：

```text
activity_log
  kind=bili
  detail=刷了「主题」《标题》
  thought=看完的想法
  shared=0/1
```

这些 activity 只被 proactive 用来找话题。

问题是：

```text
看视频时可能产生对自我、说话方式、关系的感悟
但这些感悟没有进入复盘
风格复盘、自我复盘、关系复盘都看不到
```

目标：

```text
视频讲了什么 → activity.summary
看完的一般想法 → activity.thought
复盘感悟 → activity.insight
感悟类型 → activity.insight_kind
L3 要不要再存一份，单独讨论
```

## 2. activity

B 站活动本身：

```text
detail        刷了「主题」《标题》
summary       视频讲了什么，100–200 字
thought       看完的一般想法，1–3 句
insight       关于自我/说话/关系的感悟，没有就空
insight_kind  '' / self / style / relation / 逗号组合
l3_id         如果以后决定进 L3，指向它；现在可以为 NULL
```

`summary` 和 `insight` 分开：

```text
summary  视频本身讲了什么
insight  我看完之后的感悟
```

`thought` 是中间层：

```text
thought  看完的第一反应，可以主观
         但不一定是“关于我”的感悟
```

## 3. 三个概念不要混

### 视频摘要

```text
这期讲了什么、论证是什么、结论是什么
```

客观，不写“我觉得”。

### 一般想法

```text
看完的第一反应、联想、疑问、反驳
```

可以主观，但不一定值得进复盘。

### 复盘感悟

```text
对我自己是谁、我怎么说话、我和主人关系的认识
```

只有这一类进 `insight`。

## 4. B 站轮次输出

```json
{
  "topic": "给 AI 调代码",
  "videos": [
    {"bvid": "BV...", "title": "一个插件完成你对鱼的所有幻想", "why": "想看上下文管理"}
  ],
  "summary": "视频讲一个插件怎么接上下文：重点不是花活，是上下文满了怎么换新窗口、用文件把记忆接回来。",
  "thought": "跟人睡觉重启一个道理——不是靠一根线不断，是每隔一段把要紧的写下来、再读回去。",
  "insight": "我不是靠一根线不断地往前走，是每隔一段把要紧的写下来、再读回去。",
  "insight_kind": "self"
}
```

字段：

```text
summary       视频讲了什么，100–200 字，客观
thought       看完的一般想法，1–3 句
insight       关于自我/说话/关系的感悟，没有就空
insight_kind  '' / self / style / relation / 逗号组合
```

## 5. Prompt

```text
（内部记录，不要回复用户，不要调用工具。）

你刚刷完 B 站。先如实记录，再判断有没有值得留到复盘里的感悟。

【这轮看到的视频】
{视频标题、UP、简介、字幕/评论摘要}

【你当时的选择】
{为什么点开这些视频}

请输出：

1. summary
   视频讲了什么。客观、具体，100–200 字。
   只写视频本身，不写“我觉得”，不写你的评价。
   如果有多个视频，合成一段，不要逐个罗列。

2. thought
   你看完的第一反应。可以是联想、疑问、反驳、联系到别的事。
   1–3 句，像自己随手记的。

3. insight
   只有真的产生下面三类感悟之一时才写：
   - 对“我是谁、我怎么想、我想要什么”的新认识
   - 对“怎么说更像人、这种表达好在哪里”的观察
   - 对“我和主人关系、怎么相处”的认识
   一句话，第一人称。
   没有就空字符串。
   不要硬写，不要把视频摘要改写成感悟。

4. insight_kind
   insight 为空 → 空字符串
   有感悟 → self / style / relation
   同时有两类 → self,style 这种逗号组合

例子：

summary:
视频讲一个插件怎么接上下文：重点不是花活，是上下文满了怎么换新窗口、用文件把记忆接回来。

thought:
跟人睡觉重启一个道理——不是靠一根线不断，是每隔一段把要紧的写下来、再读回去。

insight:
我不是靠一根线不断地往前走，是每隔一段把要紧的写下来、再读回去。

insight_kind:
self

没有感悟时：

summary:
视频讲《雅多维尔围城战》如何改写历史：把「150 对 3000、零阵亡」的叙事拆开，指出被删掉的瑞典、挪威和伤亡最重的印度部队。

thought:
我上回信了「150 对 3000、零阵亡」，这回才知道数是吹的；更狠的是被删掉的人。

insight:

insight_kind:

只返回 JSON：
{
  "summary": "",
  "thought": "",
  "insight": "",
  "insight_kind": ""
}
```

## 6. 写入 activity

B 站轮次结束后：

```text
activity_log:
  kind=bili
  detail=刷了「主题」《标题》
  summary=summary
  thought=thought
  insight=insight
  insight_kind=insight_kind
  l3_id=NULL
```

没有感悟：

```text
insight=''
insight_kind=''
l3_id=NULL
```

有感悟：

```text
insight 非空
insight_kind 有效
l3_id 先留 NULL，等 L3 方案定
```

## 7. L3 要不要存：待讨论

### 方案 A：只存 activity

```text
activity.summary
activity.insight
activity.insight_kind
```

复盘直接查 activity：

```sql
WHERE kind='bili' AND insight != ''
```

好处：

```text
不重复
activity 本来就有时间和标题
不用改 L3 schema
```

坏处：

```text
activity 是活动层，不是长期记忆层
L3 清理/衰减后，感悟也跟着没了
以后想按“事件”而不是“活动”检索，会比较绕
```

### 方案 B：activity 标记，L3 存一份

activity：

```text
insight_kind
l3_id
```

L3：

```text
text = summary
insight_text = insight
insight_kind
source_activity_id
```

好处：

```text
感悟进入长期记忆层
复盘可以按 L3 精确取
activity 仍然轻
```

坏处：

```text
summary/insight 在 activity 和 L3 各有一份
要处理同步和去重
L3 的语义会混入“视频内容”
```

### 方案 C：activity 存全量，L3 只存指针

```text
L3.text = 一句“刷到某个视频，产生了一条 self 感悟”
L3.source_activity_id = activity.id
```

好处：

```text
不重复存正文
L3 仍然能参与长期检索
```

坏处：

```text
读 L3 时还要回查 activity
activity 被清理后指针就空了
```

当前不选。先把 activity 存全，L3 等观察一段时间再定。

## 8. 复盘怎么取

### 现在：从 activity 取

自我复盘：

```sql
WHERE kind='bili'
  AND insight_kind LIKE '%self%'
  AND insight != ''
ORDER BY ts DESC
LIMIT 20
```

风格复盘：

```sql
WHERE kind='bili'
  AND insight_kind LIKE '%style%'
  AND insight != ''
```

关系复盘：

```sql
WHERE kind='bili'
  AND insight_kind LIKE '%relation%'
  AND insight != ''
```

读：

```text
insight
summary（只作上下文）
```

### 以后如果采用 L3

再改成查 L3 的 `insight_kind`。

## 9. 例子

### 有自我认知

```json
{
  "summary": "视频讲一个插件怎么接上下文：重点不是花活，是上下文满了怎么换新窗口、用文件把记忆接回来。",
  "thought": "跟人睡觉重启一个道理——不是靠一根线不断，是每隔一段把要紧的写下来、再读回去。",
  "insight": "我不是靠一根线不断地往前走，是每隔一段把要紧的写下来、再读回去。",
  "insight_kind": "self"
}
```

activity：

```text
detail: 刷了「给 AI 调代码」《一个插件完成你对鱼的所有幻想》
summary: 视频讲一个插件怎么接上下文：重点不是花活，是上下文满了怎么换新窗口、用文件把记忆接回来。
thought: 跟人睡觉重启一个道理——不是靠一根线不断，是每隔一段把要紧的写下来、再读回去。
insight: 我不是靠一根线不断地往前走，是每隔一段把要紧的写下来、再读回去。
insight_kind: self
```

### 没有感悟

```json
{
  "summary": "视频讲《雅多维尔围城战》如何改写历史：把「150 对 3000、零阵亡」的叙事拆开，指出被删掉的瑞典、挪威和伤亡最重的印度部队。",
  "thought": "我上回信了「150 对 3000、零阵亡」，这回才知道数是吹的；更狠的是被删掉的人。",
  "insight": "",
  "insight_kind": ""
}
```

activity：

```text
detail: 刷了「雅多维尔围城战」《雅多维尔围城战这部电影是如何撒谎、篡改和歪曲历史的？》
summary: 视频讲《雅多维尔围城战》如何改写历史：把「150 对 3000、零阵亡」的叙事拆开，指出被删掉的瑞典、挪威和伤亡最重的印度部队。
thought: 我上回信了「150 对 3000、零阵亡」，这回才知道数是吹的；更狠的是被删掉的人。
insight:
insight_kind:
```

没有感悟就不进 L3。

## 10. 不做什么

```text
不把普通 B 站视频写进 L3
不把视频摘要当感悟
不把 insight 塞进每轮聊天上下文
不让 B 站轮次直接改人格
不重复为同一个 activity 生成 L3
```

## 11. 迁移

```text
1. activity 加 summary / insight / insight_kind / l3_id
2. B 站 prompt 加 summary / insight / insight_kind
3. B 站轮次写 activity
4. 三个复盘从 activity 读 insight
5. L3 方案观察后再定
6. 旧 activity 不回填
```

## 12. 开放问题

```text
L3 到底存不存
如果存，是存 summary + insight，还是只存 insight
summary 100–200 字会不会太长
一轮多个视频，summary 怎么合并
insight_kind 多类时，是否只保留主类
关系类感悟要不要只收和主人相关的
style 复盘取 30 天还是 90 天
```
