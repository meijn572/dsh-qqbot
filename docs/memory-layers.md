# 记忆分层

状态：目标框架。

实现进度和下一步见 [当前改动计划](plan.md)。

## 1. 一句话

```text
L0 原话
L1 事实
L2 判断
L3 事件
L4 核心记忆

activity：B 站、自主活动
persona：画像、规矩、关系
```

```text
L1 记“他说过什么”
L2 记“我推测什么”
L3 记“发生了什么”
L4 记“什么忘不掉”
activity 记“今天刷了什么”
persona 记“我是谁、我们是什么关系”
```

## 2. 五个记忆层

| 层 | 内容 | 来源 | 寿命 |
| --- | --- | --- | --- |
| L0 | 原始对话 | 每轮消息 | 永久 |
| L1 | 事实 | L0 | 长期 |
| L2 | 判断 / 假设 | L0 + L1 | 短期，7–30 天 |
| L3 | 事件线程 | L0 + L1 + L2 | 中长，90 天 |
| L4 | 核心记忆 | L3 + L0 | 不衰减 |

另外两个不是记忆层：

```text
activity：行为日志
persona：人格与稳定画像
```

## 3. 分层来源

```text
L0
 ├─ L1 事实
 ├─ L2 判断
 └─ L3 事件
      └─ L4 核心记忆
```

具体输入：

```text
L1 ← L0
L2 ← L0 + L1
L3 ← L0 事件窗口 + L1 + L2
L4 ← L3 + L0 证据
```

### 为什么 L2 不只从 L0

```text
L0 → L1 事实
L1 + L0 → L2 判断
```

先有事实，再判断。

否则模型容易直接从原话猜：

```text
他肯定很焦虑
```

### 为什么 L3 还要 L0

L1/L2 已经是抽象。

没有 L0：

```text
失去时间顺序
失去原话
容易写成“总结的总结”
```

所以 L3 用**这段事件窗口的 L0**，不是整天所有 L0。

### L0 事件窗口是什么

不是按时间范围硬切。

```text
错误：L3.opened_at 到 L3.closed_at 之间的所有 L0
```

这样会把中间无关的聊天也卷进来。

正确：

```text
L3 归属的会话段 L0 集合
```

也就是：

```text
这一段对话被判断为属于这个事件
→ 这一段的 L0 才是事件窗口
```

### 新建 L3

```text
当前会话段的 L0
```

### 续写 L3

```text
当前会话段的 L0
+ 已有 L3 的 summary
+ 最近 2–3 条旧 evidence（保持连续性）
```

不要把整个旧窗口重新塞一遍。

旧细节需要时按 `source_ids` 回查。


### 为什么 L4 从 L3

L4 是“忘不掉的事件”，不是“重要的事实”。

```text
L3 事件
→ 复盘判断“这件事忘不掉”
→ L4
```

不要：

```text
L1 直接升 L4
L2 直接升 L4
```

## 4. L1：事实

只写可指认的事实：

```text
主人教初中数学
主人养了只猫叫豆豆
主人喜欢许嵩
主人说导师还没回消息
```

不写：

```text
主人可能有点焦虑
主人今天大概很累
```

那是 L2。

### 规则

```text
一句话一条
不写判断
不写推测
尽量保留原意
```

## 5. L2：判断 / 假设

L2 是解释，不是事实。

```text
L1：主人说导师还没回消息
L2：他可能有点焦虑（confidence 0.6）

L1：主人今天加班到十点
L2：他今天大概很累（confidence 0.7）
```

### 字段

```json
{
  "text": "他可能有点焦虑",
  "tier": "L2",
  "confidence": 0.6,
  "basis": ["L1 id"],
  "status": "hypothesis",
  "expires_in_days": 14
}
```

### 生命周期

```text
默认 hypothesis
7–30 天衰减

被证实 → 升 L1 / L3 / persona
被否定 → 删除或标 false
```

### 注入

只能带不确定性：

```text
我猜他可能有点焦虑
他今天看起来挺累
```

不能：

```text
他很焦虑
他很累
```

### 风险

```text
模型判断可能错
confidence 可能虚高
判断会自我强化
判断可能污染事实和人格
```

所以 L2 必须单独存、带依据、默认短寿命、不直接当事实用。

## 6. L3：事件线程

L3 不是单段总结，是一条有生命周期的事件线程。

### 跨段

```text
晚上：牙疼
第二天：去排队看牙
看完：只是牙龈发炎，没啥事
→ 这时事件才结束
```

如果每段一条 L3：

```text
L3-1 牙疼
L3-2 去看牙
L3-3 没事了
```

事件被切碎。

### 状态

```text
open     还在进行
closed   已经结束
dormant  很久没提
```

### 字段

```json
{
  "tier": "L3",
  "title": "牙疼看牙",
  "aliases": ["看牙", "牙龈发炎"],
  "status": "open",
  "opened_at": 1793970000,
  "last_seen_at": 1793970000,
  "closed_at": null,
  "summary": "牙疼，准备去看牙",
  "source_ids": ["L0 id"],
  "derived_from": ["L1 id", "L2 id"]
}
```

### 每段结束后

```text
L1/L2 完成
→ 读取 open L3
→ 判断：
   续写已有事件
   开启新事件
   和事件无关
```

续写：

```text
追加 evidence
更新 summary
更新 last_seen_at
```

### 关闭

```text
明确结果
“没事了”“看完了”“解决了”“确定了”

承诺/决定已经落地

话题被明确收尾
```

不能因为：

```text
5 分钟没说话
单段结束
```

就关闭。

很久没提：

```text
超过 N 天没有续写 → dormant
```

不是删除。

## 7. L4：核心记忆

L4 是“忘不掉的事件”。

```text
第一次
承诺
关系转折
强烈情绪
后来反复想起
对之后的行为有持续影响
```

数量：

```text
初期最多 20 条
稳定后最多 50 条
```

来源：

```text
L3 + L0 证据
```

### L4 的 L0 证据怎么取

不重新匹配，也不重新检索。

直接继承被提升 L3 的 `source_ids`：

```text
L4.source_ids = union(l3.source_ids)
L4.derived_from = [l3.id]
```

合并多条 L3：

```text
L4.source_ids = union(l3_a.source_ids, l3_b.source_ids, ...)
L4.derived_from = [l3_a.id, l3_b.id, ...]
```

L3 没有 source_ids：

```text
L4.source_ids = []
L4.source_status = unverified
```

不要用时间窗口硬猜。

不要重新让模型编 evidence。

### L4 的 L0 证据怎么用

```text
存储：保留全部 source_ids
展示：可以选 1–3 条代表性原话
溯源：按 source_ids 回查 L0
```

`source_ids` 是完整证据，展示可以摘要。

不要：

```text
L1 直接升 L4
L2 直接升 L4
open L3 提前封成 L4
```

## 8. activity：B 站与自主活动

不是记忆层。

```text
B 站
刷视频
自主活动
```

写入：

```text
activity_log
```

不参与 memory 检索。

只有引发真实对话才：

```text
activity + chat → L3
```

## 9. persona：人格与稳定画像

人格负责：

```text
我是谁
我的性格
我怎么说话
我眼中的主人
我们是什么关系
```

规矩：

```text
明确说过的要求
称呼
边界
禁止事项
相处规则
```

归：

```text
persona important
核心设定-约定
核心设定-边界
```

稳定画像：

```text
stable_facts
preferences
values
interaction
boundaries
```

归：

```text
persona.user_profile
```

## 10. 提取时机

不按条数切。

按会话段：

```text
最后一条消息
→ 空闲 5 分钟
→ 这一段结束
→ 对整段提取
```

5 分钟内又来消息：

```text
并入同一段
```

### 一段可以产出多条

```text
L1：0..N 条
L2：0..M 条
L3：0..K 条
```

安全上限：

```text
每段 L1 最多 20 条
单段最多 30 分钟 / 80 条消息
```

### 顺序

```text
L0 整段
→ L1 事实
→ L2 判断
→ L3 事件线程
→ L4 每日复盘
```

### L4

```text
每天 04:00 左右
输入：前一天 closed L3 + L0
输出：0–2 条核心记忆
```

## 11. 来源与证据

### source_ids

精确 L0 证据 id。

```text
L1 → L0
L2 → L0
L3 → L0
L4 → L0
```

### derived_from

直接输入层 id。

```text
L1 → 空
L2 → L1
L3 → L1 / L2
L4 → L3
```

### 当前实现

现在只实现了 `source_ids`，而且重点是直达 L0：

```text
L1.source_ids = L0
L3.source_ids = L0（evidence 改造后）
L4.source_ids = 空 / legacy
```

`derived_from` 还没加列。

所以当前不是树形逐层找：

```text
L1 / L3 直接指向原话
```

代价是：

```text
丢了“这条 L3 由哪些 L1/L2 推出来”的中间依赖
```

### 目标

```text
source_ids   = 叶子（L0）
derived_from = 父节点（直接输入层）
```

这样既能直接回到原话，也能沿依赖关系往上/往下查。

是 DAG，不是严格树：

```text
一个 L3 可以依赖多个 L1/L2
一个 L4 可以依赖多个 L3
```

### evidence

模型不填数据库 id。

模型只给原话：

```json
{
  "text": "主人让她给自己取名字，她取名为「洄」",
  "evidence": ["主人：你给自己取个名字吧"]
}
```

代码匹配：

```text
精确子串
去标点/空白/大小写
模糊匹配，阈值 0.85
```

匹配成功：

```text
source_ids = 命中的 L0 id
source_status = verified
```

匹配失败：

```text
source_ids = []
source_status = unverified
```

历史数据：

```text
source_status = legacy / batch
```

## 12. 检索与注入

### 默认对话

```text
人格
+ L1 相关事实
+ L2 相关判断（高门槛，带不确定性）
+ L3 相关经历
+ L4 少量核心记忆（高门槛）
```

L4 不常驻。

### open L3

不“少量注入”。

```text
全部 open L3 进入候选
→ 按相关性排序
→ top K 注入详情
→ 其余 open 注入标题索引
```

索引：

```text
【还没完的事】
- 牙疼看牙 · 等结果 · 11-06
- 导师回复 · 还没回 · 11-05
```

每条只有：

```text
标题
一句话状态
最后提及
```

不暴露 id。

需要细节：

```text
get_open_thread(query="牙疼看牙")
```

服务端负责标题、别名、模糊匹配。

匹配不到或多条：

```text
返回候选，不猜
```

### 规矩

```text
persona important / 核心设定
```

L3/L4 不参与。

### B 站

```text
activity
```

不参与 memory 检索。

### 日记

```text
当天情绪事件
+ 对应 L0
+ L3 旧记忆
+ activity 补充
```

## 13. 迁移原则

```text
旧 L2 用户画像 → persona.user_profile
旧 L4 规矩 → persona important / 核心设定
旧 L4 关系叙事 → L4 核心记忆或人格
B 站/自主活动 → activity
```

迁移前必须备份。

历史迁移记录见 [当前改动计划](plan.md) 和 [重构计划](refactor-plan.md)。

## 14. 参考架构

简版：

```text
CoALA：语义 / 情景 / 程序记忆
Generative Agents：记忆流 + importance/recency/relevance + reflection
Letta：core memory / archival memory
Mem0：会话 / 用户 / 组织分层
Zep：时间图、事实失效、来源
```

对我们的影响：

```text
1. persona 常驻，L4 按需检索
2. L4 从 L3 反思提升，但必须带证据
3. activity 和 memory 分开
4. source_ids 和 derived_from 分开
```

不照搬：

```text
图数据库
全自动 self-editing
OS 式分页
```

## 15. 非目标

```text
不新增 L5
不把 B 站塞进 memory
不恢复 L2 用户画像
不让 L1 直接升 L4
不让 L2 直接升 L4
不让 open L3 提前封成 L4
不让模型填数据库 id
```

## 16. 一句话

```text
L1 记事实
L2 记解释
L3 记故事
L4 记故事里忘不掉的那一段
```

越往上，越依赖下层，但不能脱离 L0 证据。
