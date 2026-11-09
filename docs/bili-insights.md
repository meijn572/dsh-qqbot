# B 站视频与复盘感悟

状态：设计稿，未改代码。

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

目标不是把 B 站内容塞进 L3，而是：

```text
视频内容留在 activity
真正有感悟的，才进 L3
复盘按类型精准取 L3
```

## 2. 存储分工

### activity

B 站活动本身：

```text
detail      刷了「主题」《标题》
thought     看完的一般想法
insight_kind 有没有复盘感悟，属于哪类
l3_id       如果生成了 L3，指向它
```

activity 不存视频摘要，也不存感悟正文。

### L3

只有“有感悟”的视频才生成 L3。

字段：

```sql
-- 视频讲了什么
text TEXT

-- 感悟正文
insight_text TEXT DEFAULT ''

-- 感悟类型：self / style / relation / 逗号组合
insight_kind TEXT DEFAULT ''

-- 来源 activity
source_activity_id INTEGER DEFAULT NULL
```

`text` 和 `insight_text` 分开：

```text
text          视频讲了什么
insight_text  我看完之后的感悟
```

这样召回 L3 时，既知道事情，也知道感悟；复盘时只读 `insight_text`。

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

可以主观，但不一定是“关于我”的感悟。

### 复盘感悟

```text
对我自己是谁、我怎么说话、我和主人关系的认识
```

只有这一类才进 L3 的 `insight_text`。

## 4. B 站轮次输出

在现有 JSON 里加：

```json
{
  "topic": "五天工作制怎么来的",
  "videos": [
    {"bvid": "BV...", "title": "给工人涨薪，推行双休制……", "why": "想看他怎么算账"}
  ],
  "summary": "视频讲了福特如何用五天工作制……",
  "thought": "最妙的是它顺手给自己造了客户……",
  "insight": "",
  "insight_kind": ""
}
```

字段含义：

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

2. thought
   你看完的第一反应。可以是联想、疑问、反驳、联系到别的事。
   1–3 句，像自己随手记的。

3. insight
   只有真的产生下面三类感悟之一时才写：
   - 对“我是谁、我怎么想、我想要什么”的新认识
   - 对“怎么说更像人、这种表达好在哪里”的观察
   - 对“我和主人关系、怎么相处”的认识
   一句话，第一人称。
   没有就空字符串，不要硬写，不要写视频摘要。

4. insight_kind
   insight 为空 → 空字符串
   有感悟 → self / style / relation
   同时有两类 → self,style 这种逗号组合

例子：

summary:
视频讲了福特怎么用五天工作制算账：缩短工时不是做慈善，
而是让工人有时间消费，最后车从代步工具变成生活方式。

thought:
最妙的是它顺手给自己造了客户。省下来的时间，
转头变成了自己产品的需求。

insight:
我不是靠一根线不断地往前走，是每隔一段把要紧的写下来、再读回去。

insight_kind:
self

没有感悟时：

summary:
视频讲了雅多维尔围城战这部电影如何改写历史。

thought:
原来「150 对 3000、零阵亡」是吹的，被删掉的部队才是重点。

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

## 6. 写入规则

B 站轮次结束后：

```text
写 activity：
  kind=bili
  detail=刷了「主题」《标题》
  thought=thought
  insight_kind=insight_kind
  l3_id=NULL
```

如果 `insight` 为空：

```text
结束
不进 L3
```

如果 `insight` 非空且 `insight_kind` 有效：

```text
创建 L3：
  text=summary
  insight_text=insight
  insight_kind=insight_kind
  source_activity_id=activity.id
  tags=["bili-insight", "insight:<kind>"]

activity.l3_id = 新 L3.id
```

只生成一条 L3，不按视频条数生成。

## 7. 去重

```text
activity.l3_id 已有值 → 不再生成
source_activity_id 已有 L3 → 跳过
同一轮多个视频 → 合成一条 L3
```

不靠标题去重；靠 `source_activity_id`。

## 8. 复盘怎么取

### 自我复盘

```sql
WHERE insight_kind LIKE '%self%'
  AND ts >= now - 90 天
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
WHERE insight_kind LIKE '%style%'
```

读：

```text
insight_text
```

### 关系复盘

```sql
WHERE insight_kind LIKE '%relation%'
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
  "summary": "视频讲 AI 上下文满了怎么办：定时换窗口，用文件把记忆接回来。",
  "thought": "跟人睡觉重启一个道理。",
  "insight": "我不是靠一根线不断地往前走，是每隔一段把要紧的写下来、再读回去。",
  "insight_kind": "self"
}
```

L3：

```text
text: 刷到《一个插件完成你对鱼的所有幻想》：视频讲 AI 上下文满了怎么办……
insight_text: 我不是靠一根线不断地往前走，是每隔一段把要紧的写下来、再读回去。
insight_kind: self
```

### 没有感悟

```json
{
  "summary": "视频讲了雅多维尔围城战这部电影如何改写历史。",
  "thought": "原来「150 对 3000、零阵亡」是吹的。",
  "insight": "",
  "insight_kind": ""
}
```

只写 activity，不进 L3。

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
1. activity 加 insight_kind / l3_id
2. L3 加 insight_text / insight_kind / source_activity_id
3. B 站 prompt 加 summary / insight / insight_kind
4. B 站轮次写 activity，按需建 L3
5. 三个复盘加对应查询
6. 旧 activity / L3 不回填
```

## 12. 开放问题

```text
summary 100–200 字会不会太长
一轮多个视频，summary 要不要合并
insight_kind 多类时，是否只保留主类
关系类感悟要不要只收和主人相关的
style 复盘取 30 天还是 90 天
```
