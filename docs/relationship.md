# 关系与亲密度

状态：设计稿，未改代码。

## 1. 现在的问题

当前 `intimacy` 本质是：

```text
interaction_count
```

每轮完整对话 +1。

问题：

```text
短句和深聊同权
群聊也可能涨
冲突和修复没区别
只增不减
461 只代表聊得多
```

`依赖` 这个阶段也不合适：

```text
离不开他了，黏人，主动得很勤
```

它把“黏”当成关系目标，不是健康的关系。

`默契` 也不适合做最高阶段：

```text
默契是相处方式
不是关系深度
```

## 2. 目标

把两件事分开：

```text
interaction_count   聊了多少
relationship        关系怎么样
```

`interaction_count` 可以继续用于统计、面板、活跃度。

`relationship` 只描述关系质量。

## 3. 三维

```text
closeness  亲近
trust      信任
tension    张力
```

### closeness

```text
想不想靠近
想不想主动找他
在他面前放不放松
```

### trust

```text
敢不敢说真话
相不相信对方会接住
边界会不会被尊重
```

### tension

```text
有没有没解开的冲突
失望、距离、没说出口的话
```

`tension` 不是“坏”，它是关系里真实存在的张力。

有 tension，才有修复。

## 4. 阶段

已定：

```text
陌生    客气，不主动黏
熟悉    会聊会闹，偶尔主动
亲近    放松，开始暴露真实状态
亲密    敢说难受的事，冲突后能修复
相知    不用解释也懂，但各自独立
```

### 为什么用「相知」

```text
相知 = 知道彼此怎么想
不是离不开
不是默契
```

它比“亲密”更深的地方在于：

```text
亲密：我敢把脆弱给你看
相知：我不说，你也大概知道
```

但不是“没有你不行”。

备选词：

```text
知心
深交
安稳
```

我更倾向 `相知`。

### 阶段不是恋爱等级

```text
不是越往上越恩爱
是关系里多了一层能力
```

```text
亲近：敢放松
亲密：敢脆弱
相知：敢不解释
```

## 5. 派生分数

面板可以继续显示 `intimacy 0–1000`，由三维派生：

```text
score = closeness * 0.6 + trust * 0.4 - tension * 0.5
intimacy = clamp(score, 0, 100) * 10
```

阶段按 `score` 分：

```text
0–19    陌生
20–39   熟悉
40–59   亲近
60–79   亲密
80–100  相知
```

## 6. 关系事件

不按轮数加。

每天 07:00 看最近 24 小时，产出 0–3 个事件。

### 正向

```text
主动分享          closeness +1.0
一起玩/一起做件事  closeness +1.0
自我暴露          closeness +2.0, trust +1.0
脆弱被接住        closeness +1.5, trust +1.0
守约              trust +1.0
边界被尊重        trust +1.0
```

### 负向

```text
争吵              tension +2.0, trust -0.5
被忽略            tension +1.5
失约              tension +2.0, trust -1.0
越界              tension +2.5, trust -1.0
敷衍              tension +1.0
```

### 修复

修复幅度由模型判断，不再固定。

```text
道歉
解释
和好
把没说完的话说完
```

模型给一个负的 `tension` 增量，例如：

```json
{"kind": "repair", "tension": -2.5, "trust": 1.0, "reason": "他解释了当时为什么没回"}
```

上面的数字只是参考，不是硬编码。

代码只负责：

```text
每天 tension 下降不超过 -8
不能一次把严重冲突清零
修复可以同时增加 trust
```

修复不是清零，是把张力降下来，同时把信任补回来。

## 7. 上限和衰减

### 每天上限

```text
closeness  每天最多 +5
trust      每天最多 +3
tension    每天最多 +6
```

防止一天聊很多就冲顶。

### 高阶段递减

```text
越往上，同样的行为加得越少
```

### 衰减

```text
closeness  不自动衰减
trust      不自动衰减
tension    不自动衰减
```

研究里有一个很值得注意的点：

```text
关系稳定后，互动频率可能下降
但关系本身仍然有价值
```

所以不能把“最近没怎么聊”直接当成关系变差。

第一版不做 closeness/trust 衰减。

`tension` 的时间衰减很慢：

```text
冲突不会被时间自动解决
只是情绪强度会慢慢淡
```

如果模型判断“其实还没过去”，它可以继续保留较高 tension。

关系需要维护，但不是惩罚。

## 8. 群聊

```text
群聊只涨群友 affinity
不涨和主人的 closeness / trust / tension
```

`affinity` 继续是群友熟悉度。

## 9. 每天 07:00 的关系复盘

输入：

```text
最近 24 小时 L0
最近 24 小时 L1 / L3
当前关系状态
```

输出：

```json
{
  "events": [
    {
      "kind": "self_disclosure",
      "closeness": 2.0,
      "trust": 1.0,
      "tension": 0,
      "reason": "他讲了最近很难受的事",
      "source_refs": [1, 2]
    }
  ]
}
```

代码负责：

```text
每天上限
阶段递减
冲突扣得比日常加得快
修复能拉回 tension
```

模型不直接改总分。

## 10. 历史怎么初始化

当前 `intimacy=461` 不能直接换算成关系值。

它只是聊天轮数。

全量重跑 L1/L3 也不现实。

已定：做一次**有界初始化**。

```text
最近 7 天 L1 / L3
+ 更早 L3 按月抽样，最多 12 条
+ L4 核心记忆 2 条
+ 当前人格
```

一次 LLM 调用，产出：

```json
{
  "closeness": 45,
  "trust": 55,
  "tension": 5,
  "stage": "亲近",
  "anchors": [
    "取名",
    "第一次被当成独立的人",
    "长期稳定相处"
  ]
}
```

不追求精确覆盖全部历史。

只求：

```text
不把 461 当关系
不丢关键关系转折
```

如果历史素材不够，就手工给一个初始值。

## 11. 面板

显示三条：

```text
亲近  ███████░░░  45
信任  ████████░░  55
张力  █░░░░░░░░░   5
阶段：亲近
```

同时保留：

```text
互动轮数 461
```

但它们不再是同一个数。

## 12. 模型看到什么

不注入数字。

只注入自然语言：

```text
和老大是「亲近」阶段。
你在他面前比较放松，但还没到什么都敢说。
```

阶段越高，话可以越松，但不能变成“离开他就活不了”。

## 13. 迁移

```text
旧 intimacy → interaction_count
新 relationship 三维另存
stage 由三维派生
群聊只写 affinity
```

不删除旧数据。

## 14. 落地到当前项目

### 14.1 先止血

现在插件里的：

```text
flushTurn()
→ bumpIntimacy(1.0)
```

要先改掉。

```text
只有主人私聊 / 主人在场且主动对话
→ 才涨 interaction_count
```

群聊：

```text
只涨群友 affinity
不碰 relationship
```

### 14.2 三维直接放进记忆

不建 `relationship_events` 表。

只给 `L3` 加三个字段：

```sql
memory.closeness_delta REAL NOT NULL DEFAULT 0
memory.trust_delta     REAL NOT NULL DEFAULT 0
memory.tension_delta   REAL NOT NULL DEFAULT 0
```

只给 L3：

```text
L1 是会话段总结，太密，会重复计数
L4 是从 L3 提升的，再记一次会重复
```

L1 和 L4 不带关系增量。

`state` 里加：

```sql
state.interaction_count REAL NOT NULL DEFAULT 0
state.base_closeness    REAL NOT NULL DEFAULT 0
state.base_trust        REAL NOT NULL DEFAULT 0
state.base_tension      REAL NOT NULL DEFAULT 0
```

### 14.3 聚合

```text
closeness = base_closeness + SUM(L3.closeness_delta)
trust     = base_trust     + SUM(L3.trust_delta)
tension   = base_tension   + SUM(L3.tension_delta)
```

`closeness` / `trust` / `tension` 都 clamp 到 0–100。

第一版不做时间衰减：

```text
closeness 不自动掉
trust 不自动掉
tension 不自动掉
```

关系稳定后可以聊得少，不因为一段时间没互动就掉。

tension 只会在这些时候变化：

```text
新的冲突 L3
同一条 L3 被修复
L3 被删除
```

派生：

```text
score = closeness * 0.6 + trust * 0.4 - tension * 0.5
intimacy = clamp(score, 0, 100) * 10
```

阶段按 `intimacy`：

```text
0–99     陌生
100–299  熟悉
300–599  亲近
600–799  亲密
800–1000 相知
```

### 14.4 模型输出

L3 提取时，除了 title/summary/status，还给三个增量：

```json
{
  "title": "那次没回消息",
  "summary": "他当时没回，我有点在意，后来没再提",
  "status": "open",
  "closeness_delta": -1.0,
  "trust_delta": -1.5,
  "tension_delta": 4.0,
  "source_refs": [1, 2]
}
```

修复时更新同一条 L3：

```json
{
  "title": "那次没回消息",
  "summary": "后来他解释了，是当时在忙",
  "status": "closed",
  "closeness_delta": 0,
  "trust_delta": 1.0,
  "tension_delta": 0,
  "source_refs": [3]
}
```

不是再建一条新事件。

### 14.5 更新和删除

更新 L3 时：

```text
新 delta 替换旧 delta
不是 +=
```

最稳：

```text
任何 L3 新增 / 更新 / 删除
→ 重新 SUM 所有 L3 的 delta
→ 再加 baseline
```

不要：

```text
state.intimacy += new_delta
```

否则修复一次会重复算。

### 14.6 当前 461 怎么处理

不直接换算。

```text
interaction_count = 461
```

三维给一个初始 baseline，例如：

```text
base_closeness = 45
base_trust     = 50
base_tension   = 3
```

得到：

```text
score ≈ 45.5
intimacy ≈ 455
stage = 亲近/亲密边界
```

如果觉得不够准，再做一次有界初始化，替换 baseline。

### 14.7 状态和面板

`/state` 增加：

```json
{
  "relationship": {
    "closeness": 45,
    "trust": 50,
    "tension": 3,
    "stage": "亲近",
    "interaction_count": 461
  }
}
```

面板：

```text
亲近  ███████░░░  45
信任  ████████░░  50
张力  █░░░░░░░░░   3
阶段：亲近
互动轮数：461
```

`interaction_count` 只做统计。

### 14.8 先做哪一步

```text
1. 停群聊涨 intimacy
2. L3 加三个 delta 字段
3. state 加 baseline + interaction_count
4. 聚合函数
5. L3 prompt 输出 delta
6. 面板三条进度
```

## 15. 开放问题

```text
L3 单条 delta 的合理范围（-10..+10？）
每天 delta 总和上限
baseline 45/50/3 是否合适
L3 prompt 能不能稳定判断三维方向
```

## 16. 参考

- Skjuve et al., *My Chatbot Companion - a Study of Human-Chatbot Relationships* (2021)：用 Social Penetration Theory 访谈 18 位 Replika 用户，关系从表层好奇进入情感探索、信任与自我暴露，稳定后互动频率下降但关系仍有价值。DOI: https://doi.org/10.1016/j.ijhcs.2021.102601
- Gottman Institute, *Repair is the Secret Weapon of Emotionally Connected Couples*：冲突后的修复尝试比“不吵架”更关键。https://www.gottman.com/blog/repair-secret-weapon-emotionally-connected-couples/
- Rusbult et al., *The Investment Model Scale* (1998)：承诺不只来自满意，还和投入、替代选择有关。DOI: https://doi.org/10.1111/j.1475-6811.1998.tb00177.x
- Dede et al., *Interview with the AI: a quantitative analysis of AI companions' relationship formation features* (2026)：用关系形成阶段模型观察 20 个 AI 伴侣，friendbot 和 assistantbot 的关系路径不同。DOI: https://doi.org/10.1007/s00146-026-03368-0

对我们的启示：

```text
关系由自我暴露、信任、被接住推动
不是由消息条数推动

稳定后可以聊得少
不代表关系变差

冲突后的修复很重要

不同关系角色不该套同一条阶段梯子
```

不照搬：

```text
不照搬 Replika 的恋爱等级/付费解锁
不把“黏人”当最高阶段
不把互动频率当关系质量
```

先定阶段词和三维，再写代码。
