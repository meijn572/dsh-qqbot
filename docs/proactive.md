# 主动说

状态：第一版已实现（完整人格 + L0/L1/L3 + activity，统一由 proactive 发送）。

## 1. 现在的问题

主动消息有两条路：

```text
autonomy      刷 B 站 → 自己决定分享 → 自己发
proactive     定时主动说 → 自己发
```

结果是：

```text
两个出口
两套频率
两套“没回怎么办”
B 站分享和普通主动容易撞
```

## 2. 统一后的分工

```text
autonomy   只负责看
activity   只负责记
proactive  唯一负责说
```

B 站不再自己发消息。

## 3. activity

加字段：

```sql
shared    INTEGER NOT NULL DEFAULT 0
shared_at REAL DEFAULT NULL
```

活动只记：

```text
kind=bili
detail=刷了「主题」《标题》
thought=当时想法
shared=0
```

共享后：

```text
shared=1
shared_at=时间
```

## 4. autonomy 只负责看

保留：

```text
选主题
看视频
读字幕 / 看画面 / 看评论
写 activity
更新兴趣
写日报
```

删除：

```text
share 判断
send_private
pending_shares
share_max_per_day
max_unanswered_shares
```

## 5. proactive 的输入

每次到点，组装：

```text
0. 时间
   现在几点
   距离主人最后一条消息多久
   距离你最后一条消息多久
   上一条是不是你主动说的、主人还没回

1. 完整人格
   constitution + self_model + user_profile

2. 当前关系
   relationship.summary

3. 最近 L0
   最近 12 条对话

4. 最近 L3
   最近 8 条事件/片段，带标题、状态、摘要

5. 相关 L1
   用最近 L0 + 候选 activity 当 query
   检索 8–12 条相关旧事

6. 未分享的 activity
   最近 7 天内，最多 5 条
```

不是把所有记忆都塞进去，是给模型足够的“现在”和“过去”。

上次主动说的话不单独给；它已经在最近 L0 里。

## 6. 相关 L1 / 最近 L3 怎么取

```text
query = 最近 6 条 L0 + 候选 activity 的标题和想法
```

调记忆服务：

```text
L1：query + 最近时间加权，取 8–12 条
L3：最近 8 条 + 和 query 相关的 4 条
```

返回给人看的自然语言：

```text
【最近发生的事】
- 那次没回消息：后来他解释了，是当时在忙
- 美国数据中心电费视频：我看了，觉得总结挺准

【和这些相关的旧事】
- 主人一直晚睡，凌晨写代码最顺
- 主人不喜欢被追问，先问一句怎么了
```

## 7. Prompt

```text
（内部主动说，不要回复用户，不要调用工具。）

你是大肥鱼，现在想主动找主人说句话。

【时间】
现在是 {HH:MM}。
主人最后一条消息：{X 分钟前}
你最后一条消息：{Y 分钟前}
{上一条主动说之后主人还没回 / 最近是主人在说}

【你是谁】
{完整人格}

【我们现在的关系】
{relationship.summary}

【最近你们聊过（带时间）】
{最近 12 条 L0}

【最近发生的事】
{最近 L3，8 条}

【和这些相关的旧事】
{相关 L1，8–12 条}

【最近可以说的】
[1] {时间}
    刷了「{主题}」《{标题}》
    想法：{thought}

[2] ...

规则：
- 时间是重要信息，自己判断现在开口合不合适。
- 刚发完不久可以等；隔了很久可以关心、问一句，或者犯个欠。
- 也可以不追问，换个话题，或者只说说你自己。
- 怎么开口、开不开口，由你判断，不要机械地连续追问。
- 最近 L0 里有你刚主动说过的话，别重复。
- 像人一样主动开口，不是汇报记忆。
- 可以从 activity 里挑一条自然地说，也可以不提 activity。
- 可以接最近聊过的话题，但不要逐句复述。
- 不要一次讲很多件事，最多一个主题。
- 不要逐字复述 L1/L3，像自己想起来一样。
- 不要为了用记忆而硬提旧事。
- 真没什么想说的，text 留空，activity_id 填 null。

只输出 JSON：
{"text":"想对主人说的话","activity_id":1或null}
```

## 8. 输出

```json
{
  "text": "今天刷到一个讲基础科学的，里面说不是科学停了，是我们那种裸算科学的方式到头了。听着有点凉。",
  "activity_id": 1
}
```

或者：

```json
{"text": "突然想起你昨天说的那件事，后来怎么样了？", "activity_id": null}
```

不说：

```json
{"text": "", "activity_id": null}
```

## 9. 后台处理

```text
text 为空 → 不发
activity_id 有效 → mark shared=1, shared_at=now
发送 → add_l0
```

如果 `activity_id` 无效：

```text
当作 null，不标记
```

## 10. 不硬性规定“没回就停”

代码不判断“该不该追”。

只负责给模型这些事实：

```text
现在几点
主人最后一条消息多久前
你最后一条消息多久前
上一条是不是你主动说的、主人还没回
最近 L0 原文
```

模型自己决定：

```text
等一等
关心一句
轻轻催一下
犯个欠
换个话题
说自己的事
什么都不说
```

不设：

```text
一条没回 → 全部跳过
followups 计数
只能补一次
选一种
```

主动说的基础间隔仍然保留，避免每分钟都跑；但这一次说不说、说什么，不写死。

不再分 B 站一套、普通主动一套。

## 11. 频率

```text
proactive 自己的间隔：25–50 分钟
活跃时段：9:00–次日 2:00
静默时段：2:00–9:00
```

B 站不再有“每天 3 条分享”限制。

如果一直没回：

```text
模型看时间和最近 L0 自己决定：
等、关心、催、换话题、不说
activity 继续攒
```

主人回了以后：

```text
下一轮可以从攒着的 activity 里挑
```

## 12. 成本

完整人格 + 最近 L0 + L3 + L1 + activity：

```text
一次大约 8–16k 输入
每天 20–30 次
```

这是主动说变贵的主要原因。

优化：

```text
人格放固定前缀，走 prompt cache
L1 只取相关，不取全量
L3 最多 8 条
activity 最多 5 条
候选没变化时少跑
```

## 13. 和现有代码的对应

```text
activity_log       加 shared / shared_at
memory_core        查询未分享 activity
autonomy/round.py  删掉分享发送
bridge.proactive   改为读 activity + JSON 输出
proactive-state    只保留 next_at
```

## 14. 迁移

```text
1. activity 加字段
2. autonomy 停止发送
3. proactive 读未分享 activity
4. 旧的 pending_shares / share_* 配置停用
5. 稳定后再删代码
```

## 15. 开放问题

```text
完整人格是否每次都全量注入
L1 8–12 条够不够
候选 activity 只看 B 站，还是所有 activity
最多 5 条够不够
activity 超过 24h 还要不要候选
模型说“别的”时，怎么避免和最近对话重复
模型会不会因为“没回”追得太频繁
```
