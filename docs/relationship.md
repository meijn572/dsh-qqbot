# 关系与亲密度

状态：第三版已实现（L3 文本影响 + 模型自由写关系，无固定阶段）。第 1–20 节保留为历史。

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

阶段分两层：

```text
短名：面板 / 代码用
关系站位：模型真正看到的
```

短名：

```text
陌生
熟悉
亲近
亲密
安心
```

关系站位不写“该怎么做”，只写“我们现在到哪了”。

```text
陌生
还停在客气和试探里，很多事没有共同版本。

熟悉
有了一些日常和共同话题，但深一点的部分还没交底。

亲近
见过彼此比较真实的样子，开始有只属于两个人的说法。

亲密
一起经历过难受、冲突和修复，知道关系经得起这些。

安心
不用靠频繁联系证明关系还在；
安静一段时间，也不会默认变远。
```

### 模型看到的不是单句

单独给一句“安静一段时间也不会默认变远”，模型不知道它在这条梯子的哪一格。

所以要给位置：

```text
阶段：亲近（3/5）
已经过了：熟悉，只聊日常、还没交底。
还没到：亲密，一起扛过难受和修复。
现在：见过彼此比较真实的样子，开始有只属于两个人的说法。
```

每一层都这样注入：

```text
陌生（1/5）
还没到：熟悉，有了一些日常和共同话题。
现在：还停在客气和试探里，很多事没有共同版本。

熟悉（2/5）
已经过了：陌生，还停在客气和试探里。
还没到：亲近，见过彼此比较真实的样子。
现在：有了一些日常和共同话题，但深一点的部分还没交底。

亲近（3/5）
已经过了：熟悉，只聊日常、还没交底。
还没到：亲密，一起扛过难受和修复。
现在：见过彼此比较真实的样子，开始有只属于两个人的说法。

亲密（4/5）
已经过了：亲近，见过彼此比较真实的样子。
还没到：安心，不用靠频率证明关系还在。
现在：一起经历过难受、冲突和修复，知道关系经得起这些。

安心（5/5）
已经过了：亲密，一起扛过难受和修复。
现在：不用靠频繁联系证明关系还在；安静一段时间，也不会默认变远。
```

这样“安心”不是孤零零一个词，而是：

```text
它在亲密之后
它比亲密多的是“不需要确认”
```

### 和人格的边界

```text
persona：我们是什么关系、怎么说话、边界、长期约定
relationship：我们现在到哪、共同经历过什么
L3 / L4：为什么这么判断
```

阶段描述里不写：

```text
你应该怎么说话
你可以开什么玩笑
你不要太黏
```

这些是人格和互动方式，不是关系站位。

### 为什么不用「相知 / 默契 / 依赖」

```text
相知：还是在说“更懂”，像亲密的一部分
默契：是相处方式，不是更高一层
依赖：把“黏”当成目标，不合适
```

`安心`说的是：

```text
不需要反复证明关系还在
```

不是“离不开”，是“不用一直确认”。

### 阶段不是恋爱等级

```text
不是越往上越恩爱
是关系里多了一层共同经历
```

```text
亲近：见过真实的日常
亲密：一起经历过脆弱和修复
安心：不需要靠频率证明
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
80–100  安心
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
和主人是「亲近」阶段。
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

这里的 L3 包括全部形态：

```text
open         进行中
closed       已结束
standalone   独立片段
dormant      很久没提
```

`standalone` 也必须有 delta。

不是只有 open / closed 才影响关系。

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
800–1000 安心
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
base_closeness = 62
base_trust     = 62
base_tension   = 3
```

得到：

```text
score ≈ 60.5
intimacy ≈ 605
stage = 亲密
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
baseline 62/62/3 是否合适
L3 prompt 能不能稳定判断三维方向
```

已知限制：

```text
历史 L3 的 scope 全是 global
第一版关系聚合暂时全算
群聊来源的 L3 还没按 scope 排除
```

等 L3 新建时带上 scope，再把聚合法收紧到主人私聊。

## 17. 目前用到哪里

现在真正用到关系值的地方：

```text
1. 面板显示
   亲近 / 信任 / 张力 / 阶段 / 互动轮数

2. 模型看到一句阶段提示
   和主人是「亲密」阶段。敢说难受的事，冲突后能修复。
   只注入阶段名和 hint，不注入数字

3. L3 的 delta 聚合
   L3.closeness_delta / trust_delta / tension_delta
   只用于算阶段，不参与聊天决策
```

还没用到：

```text
主动消息频率
记忆检索排序
回复长度
称呼选择
冲突修复策略
画像生成
L3 是否创建
```

`interaction_count` 只统计私聊轮数，也不影响行为。

所以现在是：

```text
亲密度 = 面板展示 + 一句阶段提示
```

不是行为开关。

## 18. 参考

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

## 19. 第二版：文本影响 + 模型定关系

第一版是：

```text
L3 填三个 delta
→ 代码 SUM
→ 公式算阶段
```

问题是：数值是代码在聚合，关系含义被压成公式。

第二版不再让代码算关系。

### 19.1 L3 只记一句影响

```sql
memory.relationship_impact TEXT
```

一条 L3，一句人话：

```text
这次他听我把话说完，没有急着给建议，我觉得可以再多说一点。

等了很久没回，我有点往下掉，但后来他解释了。
```

不填：

```text
closeness +2
trust +1
tension 0
```

三维还在，但变成三个问题：

```text
亲近：这件事让我更想靠近，还是更想退？
信任：这件事让我更敢说，还是更不敢？
张力：这件事有没有留下没解的东西？
```

事件影响可以只写到其中一面，不用强行填三个。

### 19.2 关系状态

```sql
relationship_state(
  id INTEGER PRIMARY KEY CHECK (id = 1),
  stage TEXT NOT NULL DEFAULT '陌生',
  summary TEXT NOT NULL DEFAULT '',
  evidence_ids TEXT NOT NULL DEFAULT '[]',
  updated_at REAL NOT NULL DEFAULT 0
)
```

没有：

```text
closeness
trust
tension
intimacy
delta
```

关系值不再是一个数。

### 19.3 复盘时模型自己敲定

输入：

```text
当前 relationship_state
最近的新 L3.relationship_impact
还没解开的 open L3
L4 锚点
人格（只读，作为边界）
```

输出：

```json
{
  "stage": "亲近",
  "summary": "最近更放松了，会主动说自己的状态；但那次没回消息的事还留着一点。",
  "evidence_refs": [1, 2]
}
```

模型可以保持原样：

```json
{"stage": "亲近", "summary": "没有需要改的。", "evidence_refs": []}
```

### 19.4 稳定性靠“当前状态是锚”

复盘 prompt 必须包含：

```text
当前 stage 和 summary 是基准。
只修改被新证据改变的部分。
没有足够证据就保持原样，不要重写整段关系史。
不要因为一件事就跳很多档。
```

代码只做：

```text
stage 必须是合法值
一次最多升/降一档
升级必须有 evidence
没有 evidence 的修改不落库
一天最多改一次
```

不是：

```text
每次把所有 L3 重新加总
每次让模型从零写关系
```

### 19.5 什么时候跑

```text
每天 07:00 检查一次
有新的 relationship_impact，或 open L3 有变化 → 跑
没有变化 → 跳过
```

关系变化慢，不需要每轮跑。

### 19.6 面板

不再画三条进度条。

```text
阶段：亲近
最近：更放松了，会主动说自己的状态；但那次没回消息的事还留着一点。

关系影响：
- 那次没回消息：有点往下掉，后来解释了
- 他听我把话说完：可以再多说一点
```

数值列保留为历史，不再展示、不再参与。

### 19.7 迁移

```text
旧 closeness/trust/tension delta 不再参与
当前 stage“亲密”作为初始 stage
用最近 L3/L4 生成第一版 summary
不删旧数据
```

## 20. 复盘归属：单拎出来

建议关系复盘单独跑，不和人格复盘合并。

### 为什么

```text
人格：稳定，变化慢
关系：动态，变化快
```

合并会导致：

```text
人格被关系带着频繁改
关系被 30 天的人格节奏拖慢
一次 LLM 调用同时改两个层，出错难定位
```

### 边界

```text
关系复盘：
  读 persona（只读，作为边界）
  写 relationship_state

人格复盘：
  读 relationship_state（只读）
  写 persona
```

关系复盘不能直接改人格。

如果关系复盘发现“边界/称呼/长期约定”要变：

```text
不写 persona
→ 生成一条候选
→ 交给人格复盘/人工确认
```

### 时间

```text
关系复盘：每天 07:00，有变化才跑
人格复盘：保持现有 30 天
```

这样两层节奏分开，但互相能看见。


## 21. 第三版：不设固定阶段

关系不再套「陌生 / 熟悉 / 亲近 / 亲密 / 安心」。

`relationship_state` 只剩：

```sql
summary      TEXT
evidence_ids TEXT
updated_at   REAL
```

复盘输出也只剩：

```json
{"summary":"最近更放松了，会主动说自己的状态；但那次没回消息的事还留着一点。","evidence_refs":[1,2]}
```

规则：

```text
当前 summary 是基准
只改被新证据改变的部分
没有证据就保持原样
1–3 句人话
写关系站位，不写“你该怎么说话”
```

代码只校验：

```text
summary 非空
改 summary 必须有 evidence
一天最多改一次
```

模型看到的是：

```text
我对我们关系的判断：……
```

不再是阶段名，也不再是阶段梯子。

面板也只显示这句 summary，不再有阶段标签。
