# B 站视频与复盘感悟

状态：第一版已实现。activity 存全量；L3 存短上下文、感悟和类型；summary 不进 L3。

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
L3 存短上下文 + 感悟 + 类型
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
  "insight_kind": "self",
  "insight_context": "刷到《一个插件完成你对鱼的所有幻想》，里面讲 AI 上下文满了怎么换窗口、把记忆接回来。",
  "memorability": 0.82,
  "dominant": "self_relevance"
}
```

字段：

```text
summary          视频讲了什么，100–200 字，客观
thought          看完的一般想法，1–3 句
insight          关于自我/说话/关系的感悟，没有就空
insight_kind     '' / self / style / relation / 逗号组合
insight_context  这条感悟从哪来的，40–80 字；没有感悟就空
memorability     0–1，只填一个数
dominant         importance/emotion/distinctiveness/self_relevance/relationship/none
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

5. insight_context
   insight 非空时写 40–80 字：这条感悟从哪个视频、哪个点来。
   只留能定位的上下文，不要复述 summary。
   insight 为空 → 空字符串。

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
  "insight_kind": "",
  "insight_context": ""
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

## 7. L3：存什么

已定：

```text
activity 存全量 summary
L3 不存 full summary
L3 存短上下文 + 感悟 + 类型
```

字段：

```sql
-- 短上下文，来自 insight_context
text TEXT

-- 感悟正文
insight_text TEXT DEFAULT ''

-- self / style / relation / 逗号组合
insight_kind TEXT DEFAULT ''

-- 来源 activity
source_activity_id INTEGER DEFAULT NULL
```

为什么 `summary` 不整个进 L3：

```text
L3 是“可能记得较久的感触”，不是视频笔记
full summary 会把 L3 撑成 B 站内容库
但完全不进又会让感悟悬空
所以只进一句 40–80 字的来源上下文
```

例子：

```text
activity.summary:
视频讲一个插件怎么接上下文：重点不是花活，是上下文满了怎么换新窗口、用文件把记忆接回来。

L3.text:
刷到《一个插件完成你对鱼的所有幻想》，里面讲 AI 上下文满了怎么换窗口、把记忆接回来。

L3.insight_text:
我不是靠一根线不断地往前走，是每隔一段把要紧的写下来、再读回去。

L3.insight_kind:
self
```

## 8. 复盘怎么取

### 自我复盘

```sql
WHERE tier='L3'
  AND insight_kind LIKE '%self%'
  AND insight_text != ''
ORDER BY ts DESC
LIMIT 20
```

读：

```text
insight_text
text（只作上下文）
```

### 风格复盘

```sql
WHERE tier='L3'
  AND insight_kind LIKE '%style%'
  AND insight_text != ''
```

读：

```text
insight_text
```

### 关系复盘

```sql
WHERE tier='L3'
  AND insight_kind LIKE '%relation%'
  AND insight_text != ''
```

读：

```text
insight_text
text
```

只取有感想的 L3，不翻全部 B 站 activity。

## 9. 例子

### 有自我认知

```json
{
  "summary": "视频讲一个插件怎么接上下文：重点不是花活，是上下文满了怎么换新窗口、用文件把记忆接回来。",
  "thought": "跟人睡觉重启一个道理——不是靠一根线不断，是每隔一段把要紧的写下来、再读回去。",
  "insight": "我不是靠一根线不断地往前走，是每隔一段把要紧的写下来、再读回去。",
  "insight_kind": "self",
  "insight_context": "刷到《一个插件完成你对鱼的所有幻想》，里面讲 AI 上下文满了怎么换窗口、把记忆接回来。"
}
```

activity：

```text
detail: 刷了「给 AI 调代码」《一个插件完成你对鱼的所有幻想》
summary: 视频讲一个插件怎么接上下文：重点不是花活，是上下文满了怎么换新窗口、用文件把记忆接回来。
thought: 跟人睡觉重启一个道理——不是靠一根线不断，是每隔一段把要紧的写下来、再读回去。
insight: 我不是靠一根线不断地往前走，是每隔一段把要紧的写下来、再读回去。
insight_kind: self
insight_context: 刷到《一个插件完成你对鱼的所有幻想》，里面讲 AI 上下文满了怎么换窗口、把记忆接回来。
```

### 没有感悟

```json
{
  "summary": "视频讲《雅多维尔围城战》如何改写历史：把「150 对 3000、零阵亡」的叙事拆开，指出被删掉的瑞典、挪威和伤亡最重的印度部队。",
  "thought": "我上回信了「150 对 3000、零阵亡」，这回才知道数是吹的；更狠的是被删掉的人。",
  "insight": "",
  "insight_kind": "",
  "insight_context": ""
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
2. L3 加 insight_text / insight_kind / source_activity_id
3. B 站 prompt 加 summary / thought / insight / insight_kind / insight_context
4. B 站轮次写 activity；有感悟就建 L3
5. 三个复盘从 L3 读 insight
6. 旧 activity / L3 不回填
```

## 12. 开放问题

```text
summary 100–200 字会不会太长
一轮多个视频，summary 怎么合并
insight_kind 多类时，是否只保留主类
关系类感悟要不要只收和主人相关的
style 复盘取 30 天还是 90 天
```
