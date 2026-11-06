# 记忆分层

状态：分层第一版已实现；L2 判断层和 L4 自动提升尚未接上。

## 1. 结论

不新增 L5，也不把 B 站塞进记忆层。

最终布局：

```text
L0  原话
L1  事实
L2  判断 / 假设
L3  普通经历
L4  核心记忆

activity：B 站、自主活动
persona：规矩、画像、关系
```

一句话：

```text
L4 记“忘不掉的事”
L3 记“发生过的事”
L2 记“我推测的事”
L1 记“关于他的事实”
activity 记“今天刷了什么”
persona 记“我是谁、我们是什么关系”
```

### 三条原则

```text
1. persona 常驻，L4 按需检索
2. L4 从 L3 反思提升，但必须带证据
3. activity 和 memory 分开
```

这三条优先于具体字段设计。

## 2. 现在的问题

### 2.1 L2 和人格重复

L2 现在是自动用户画像。

它和人格里的：

```text
user_profile
核心设定
```

大量重合。

而且 `profile()` 会把 L2 和 L4 一起每轮注入。

结果是同一件事有两个来源。

### 2.2 L3 混了真实经历和 B 站

L3 现在同时装：

```text
真实经历
B 站浏览
自主活动
```

但这两类东西：

```text
重要性不同
生命周期不同
检索方式不同
```

不该放一张表。

### 2.3 L4 和人格重复

L4 现在装：

```text
关系
规矩
约定
```

人格里已经有：

```text
核心设定：关系、边界、约定
重要约定
用户画像：boundaries
```

两边都注入，就是两个事实源。

### 2.4 没有“忘不掉的事件”

L3 是普通事件，会衰减。

L4 只收规矩。

第一次、承诺、关系转折、真正被击中的时刻，没有稳定位置。

## 3. 新分层

### L0 原话

不变。

```text
原始对话
```

用于回溯、日记对应原话、复盘证据。

### L1 事实

```text
他教初中数学
他养了只猫叫豆豆
他喜欢许嵩
```

一句话一条。

只写事实，不写判断。

稳定事实可以长寿命，不再 30 天就淡掉。

### L2 判断 / 假设

```text
他可能因为导师没回消息有点焦虑
他今天看起来挺累
他大概不太想聊这个
```

不是事实。

必须带：

```text
confidence
basis / source_ids
status = hypothesis
```

默认短寿命：

```text
7–30 天
```

被证实：

```text
升 L1 / L3 / persona
```

被否定：

```text
删除或标 false
```

L2 不能直接当事实注入，只能带不确定性使用。

现有 L2 用户画像已经迁到 persona，新的 L2 只装判断。

### L3 普通经历

```text
今天聊了什么
一起看了什么
发生了什么小事件
```

普通事件线，保留衰减。

B 站、自主活动不默认进这里。

### L4 核心记忆

从 L3 提升上来的少数事件：

```text
第一次见面
他真正把我当“人”看的那晚
一次很重的承诺
关系转折
后来反复想起的事
```

特点：

```text
少
不衰减
不每轮注入
按需召回
由复盘从 L3 提升
```

L4 不再装规矩。

## 4. 人格负责什么

人格仍然是：

```text
我是谁
我的性格
我怎么说话
我眼中的主人
我们是什么关系
```

具体分层见 [人格分层](persona-layers.md)。

人格是稳定配置和长期叙事的唯一来源。

```text
人格：稳定、确认过、可编辑
L4  ：具体事件，不是人格结论
```

### 规矩放哪

```text
明确说过的要求
称呼
边界
禁止事项
相处规则
```

全部归人格：

```text
persona important
核心设定-约定
核心设定-边界
```

不再经过 L4 候选。

### 画像放哪

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

不再写 L2。

## 5. B 站和自主活动

不进 memory。

```text
B 站 / 自主活动 → activity
```

原因：

```text
量大
生命周期短
不是“关系记忆”
会污染 L3 检索
```

只有一种情况进 L3：

```text
刷到的东西引发了真实对话
→ 由对话抽取成普通经历
```

### activity 负责

```text
今天看了什么
刷到什么
做了什么自主活动
```

日记需要时单独读。

面板可以单独展示。

不参与 memory 的 BM25 / 向量检索。

## 6. 数据流

```text
L0
 ├─ L1 事实
 ├─ L2 判断 / 假设（从 L1/L3 推出）
 ├─ L3 普通经历
 │    └─ 复盘提升 → L4 核心记忆
 └─ 人格写入路径（规矩/画像）

B 站 / 自主活动
 └─ activity
```

## 7. L4 提升标准

不是“重要一点的 L3”。

候选条件：

```text
第一次
承诺
关系转折
强烈情绪
后来反复被提起
对之后的行为有持续影响
```

数量控制：

```text
初期最多 20 条
稳定后最多 50 条
```

L4 记录应该带：

```text
为什么留下
来源 L3 / L0
发生时间
```

提升由复盘完成，不由每轮抽取器直接写。

如果让抽取器自己写 L4，它会觉得每件事都“忘不掉”，很快泛滥。

## 8. 检索与注入

### 默认对话

```text
人格
+ L1 相关事实
+ L2 相关判断（高门槛，带不确定性）
+ L3 相关经历
+ L4 少量核心记忆（高门槛）
```

L2 不常驻，不能当事实注入。

只有明显相关时才召回，并且用「我猜」「可能」这种口吻。

L4 不常驻。

只有明显相关、或者被明确问起时才召回。

### 规矩

```text
persona important / 核心设定
```

L4 不参与。

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

## 9. 迁移

### L2

现在 L2 是用户画像。

步骤：

```text
备份现有 L2
仍然有效的稳定事实迁到 persona.user_profile
清空 L2
旧画像停止写入
以后 L2 只写判断 / 假设
```

### L4

现有 L4 分两类：

```text
明确规矩 → 迁到 persona important / 核心-约定 / 核心-边界
关系叙事 → 迁到 L4 核心记忆，或交给人格
```

迁移后 L4 清空，重新由 L3 提升。

### L3

现有 L3 里的 B 站/自主活动：

```text
历史数据可以保留
新数据不再写 L3
```

需要时按 tags 或来源单独标记。

### activity

B 站新数据写这里。

不参与 memory 索引。

## 10. 需要改的代码点

```text
TIER_HALF_LIFE：
  L2 = 判断层，默认 7–30 天
  L4 = 不衰减核心记忆

profile()：
  不再注入 L2
  L4 不再每轮注入

extractor：
  旧 L2 画像改走 persona.user_profile
  新 L2 只写判断 / 假设
  L4 不再由抽取器直接写规矩

检索：
  L2 默认不召回
  显式查判断时才召回

bili / autonomy：
  add_l3_event 改为 activity

检索：
  默认排除 L2
  L4 只在高相关时召回
```

## 11. 还没定的问题

```text
L4 由谁提升：人格复盘还是独立复盘
L4 召回阈值
L4 最多保留多少条
现有 L4 关系叙事怎么分类
历史 B 站 L3 是否清理
activity 保留多久
```

## 12. 一句话

```text
L4 记“忘不掉的事”
L3 记“发生过的事”
L1 记“关于他的事实”
L2 退役
activity 记“今天刷了什么”
persona 记“我是谁、我们是什么关系”
```

一个事实只在一个地方生效。

## 13. 参考架构

看了几类常见 agent memory 架构，和当前方案对照如下。

### 13.1 CoALA：语义 / 情景 / 程序记忆

[CoALA](https://arxiv.org/abs/2309.02427) 把语言 agent 的记忆分成：

```text
working memory
episodic memory
semantic memory
procedural memory
```

对应到我们：

```text
L0 / 当前上下文     working
L1 事实             semantic
L3 / L4 经历        episodic
persona 人格/规矩   procedural
```

值得借鉴：

```text
先按“记忆类型”分清职责
再谈寿命和检索
```

不照搬：

```text
不需要把四个词直接做成四张表
```

### 13.2 Generative Agents：记忆流 + 反思

[Generative Agents](https://arxiv.org/abs/2304.03442) 的核心是：

```text
memory stream：完整记录经历
retrieval：recency + importance + relevance
reflection：把经历总结成更高层认识
```

对应到我们：

```text
L0 = memory stream
L3 = 普通经历
L4 = reflection 后的核心记忆
persona = 更高层自我认知
```

值得借鉴：

```text
L4 不是“重要一点的 L3”
而是从多条 L3 里提炼出来的、少量、稳定的记忆
```

也要注意：

```text
反思可以生成新认识
但不能生成没发生过的动作和场景
```

所以 L4 必须带 `source_ids` / L0 证据，避免日记式的虚构。

### 13.3 Letta / MemGPT：core memory 与 archival memory

[Letta 的 context hierarchy](https://docs.letta.com/v1-sdk/memory/context-hierarchy) 把上下文分成：

```text
始终在上下文里的 core memory
按需检索的 archival memory
```

对应到我们：

```text
persona = core memory
L4      = archival memory
L1/L3   = 检索层
```

值得借鉴：

```text
常驻的归 core
不常驻的归 archival
```

这正好支持一个决定：

```text
L4 核心记忆不每轮注入
persona 才常驻
```

### 13.4 Mem0：会话 / 用户 / 组织分层

[Mem0 的记忆类型](https://docs.mem0.com.cn/core-concepts/memory-types) 强调：

```text
conversation memory
session memory
user memory
organizational memory
```

以及：

```text
capture → promote → retrieve
```

对应到我们：

```text
L0 = conversation
activity = session/activity
L1 = user facts
L4 = 长期核心记忆
persona = 组织级/角色级配置
```

值得借鉴：

```text
不同生命周期分开
短期的东西不要直接进长期层
```

这也是 B 站不进 memory、L2 退役的依据。

### 13.5 Zep / Graphiti：时间与事实失效

[Zep 的 Context Graph](https://help.getzep.com/concepts) 把事实、关系、来源 episode 和时间放在一起，并支持 fact invalidation。

值得借鉴：

```text
事实需要有效期
旧事实不是删除，而是失效
来源要能追溯
```

我们可以先轻量做：

```text
L1 / L4 增加 valid_from / valid_to
或者用 status = active / superseded
source_ids 指回 L0
```

不急着上图数据库。

### 13.6 记忆压缩：可逆性比摘要技巧更重要

[What to Keep, What to Forget](https://ar5iv.labs.arxiv.org/html/2607.08032) 的核心观点：

```text
压缩是有损的
不可逆摘要会反复丢信息
可检索的原始记录更稳
```

对应到我们：

```text
L0 永远保留
L3 可以摘要，但要能回溯 L0
L4 只做少量提炼，不替代 L0
```

这支持：

```text
不要把所有 L3 都压成 L4
L4 是索引，不是替代品
```

### 13.7 对我们最有用的三条

```text
1. persona 常驻，L4 按需检索
2. L4 从 L3 反思提升，但必须带证据
3. activity 和 memory 分开，短期行为不进长期记忆
```

### 13.8 不需要照搬的

```text
不需要图数据库
不需要全自动 self-editing
不需要 OS 式分页
不需要把每个认知类型都做成一张表
```

我们的层级已经够用，缺的是职责边界。

## 14. 图数据库是什么

图数据库不是“把事件画成图”，而是把**关系**作为一等数据。

普通表：

```text
一行 = 一条记忆
关系靠 text 里的描述
```

图：

```text
节点 = 事件 / 人 / 话题 / 情绪 / 承诺
边   = 它们之间的关系
属性 = 时间、来源、置信度
```

### 14.1 节点

```text
事件：11-06 他说牙只是发炎
人物：主人
话题：牙
情绪：放心
承诺：以后少发点图
```

### 14.2 边

```text
主人 --经历--> 牙发炎
牙发炎 --引发--> 放心
牙发炎 --发生在--> 11-06
牙发炎 --之前--> 11-05 牙疼
放心 --属于--> 情绪
```

边也可以带属性：

```text
valid_from
valid_to
source_id
weight
```

### 14.3 能实现什么

#### 多跳召回

```text
“他上次牙疼是什么时候？后来好了吗？”
```

图可以走：

```text
主人 → 牙疼事件 → 后续牙发炎事件 → 结果
```

普通向量检索只能找“牙疼”相似文本，接不上“后来好了”。

#### 时间线 / 因果链

```text
牙疼
→ 去看牙
→ 牙龈发炎
→ 放心
```

图能把事件按 `before/after/caused` 串起来。

#### 实体视角

```text
这个人的所有事件
这个人的所有承诺
这个人的所有情绪节点
```

不用每次靠关键词搜。

#### 关系发现

```text
他每次提到工作，后面都跟着“累”
```

图可以做聚合和路径查询。

#### 事实失效

```text
旧事实 --valid_to--> 新事实
```

不是删除，而是标记失效。

#### 核心记忆证据链

```text
L4 核心记忆 → 来源 L3 → 来源 L0
```

可以一直回溯到原话。

### 14.4 对我们的意义

现在不需要上 Neo4j / Graphiti。

因为：

```text
数据量不大
大部分查询是相关性检索
引入图数据库会增加同步和运维成本
```

但可以轻量做一张边表：

```sql
memory_links(
  source_id,
  target_id,
  relation,
  weight,
  valid_from,
  valid_to,
  source_ids
)
```

先支持：

```text
事件 → 来源 L0
L4 → 来源 L3
事件 → 同一话题
事件 → 前后事件
```

也就是一到两跳。

### 14.5 什么时候值得上图数据库

```text
需要多跳关系查询
需要时间图 / 事实失效
需要大量实体和关系
需要图算法
```

在这之前，SQLite + 边表 + 向量检索够用。

### 14.6 结论

```text
图数据库解决的是“关系查询”
不是“记忆分层”
```

我们的分层先做干净。

图能力以后可以作为 L3/L4 的查询层，不需要现在改存储。

## 15. 改分层后的连带改动

不是“几乎没有”。

L4 现在会进人格 system prompt，L2 会进自动画像和 person 消息块，所以影响面比看起来大。

### 15.1 影响面分级

| 级别 | 内容 |
| --- | --- |
| P0 运行时 | L4 人格注入、L2 自动画像、profile()/检索、抽取器、批量 L4 |
| P1 数据 | L2/L4 迁移、B 站历史 L3 |
| P2 接口 | MCP、面板、测试、文档 |

### 15.2 P0：必须一起改

#### dsh-remembers 插件

现在：

```text
client.profile() → persona.l4 → renderPersona()
```

L4 被当成“关系/规矩”塞进系统提示词。

改成分层后：

```text
L4 = 核心记忆
不再进 renderPersona 的规矩段
改为按需召回
```

需要动：

```text
app.mjs: persona.l4 / refreshPersona / buildPersonaText
hooks/persona.mjs: renderPersona 的 l4 参数
client.mjs: profile() 的语义
```

#### MemoryStore.profile()

现在：

```text
SELECT L4 + L2
每轮必带
```

改成分层后：

```text
L4 核心记忆：不进 profile()
L2 判断层：也不进 profile()
profile() 只保留真正常驻的人格块，或直接废弃
```

#### L2 自动画像

现在：

```text
_touch_profile()
L2 文本追加到 profiles.profile
```

改成分层后：

```text
旧 L2 画像不再写
稳定画像走 persona.user_profile
新 L2 只写判断，不进 profiles.profile
profiles.profile 只保留历史/停止增长
```

否则清空 L2 后，`profiles.profile` 仍会继续长。

#### 抽取器

现在：

```text
EXTRACT_SYSTEM 只输出 L1 / L3
L2 判断层尚未接入
```

目标：

```text
L1 事实
L2 判断 / 假设（从 L1/L3 推导）
L3 事件
规矩直接进 persona important 候选
L4 只由复盘从 L3 提升
```

#### 检索

现在：

```text
search 排除 L4
默认 tiers 含 L2/L4
```

改成分层后：

```text
L2 判断不默认召回，只在显式查判断时召回
L4 允许高门槛召回
L4 不再每轮注入
```

#### B 站

现在：

```text
add_l1_event() → L3
```

改成分层后：

```text
B 站/自主活动 → activity
```

### 15.3 P1：数据迁移

```text
L2 用户画像 → persona.user_profile
L4 规矩 → persona important / 核心设定
L4 关系叙事 → 核心记忆或人格
L3 里的 B 站历史 → 保留或标记
```

迁移前必须备份。

### 15.4 P2：接口和外围

#### MCP

`service/mcp_server.py`：

```text
memory_ingest 的 tier enum
profile 工具描述
```

要同步改，否则模型还会以为 L2/L4 是画像/规矩。

#### 面板

`service/server.py`：

```text
tier IN ('L1','L2','L3','L4')
L4 规则列表
batch l4 统计
```

要改标签和统计。

#### 测试

```text
service/test_core.py
  L4 永远注入
  L2 画像

service/test_gating.py
  L2 更新

service/test_transfer.py
  tiers 列表
```

这些测试现在验证的是旧语义，必须改。

#### 文档

```text
memory-layers.md
persona-layers.md
workflows.md
architecture.md
```

### 15.5 不需要改的

```text
DSH 会话/消息链路
情绪 5 分钟复盘
日记的当天情绪事件输入
bridge 的 prompt 主流程
```

### 15.6 建议实施顺序

```text
1. 备份 L2/L4
2. 迁移 L4 规矩到 persona important
3. 迁移 L2 画像到 persona.user_profile
4. 停 L2/L4 新写入
5. 改插件不再注入 L4 规矩
6. 改 profile()/检索
7. 接 L4 核心记忆召回
8. 最后改 MCP/面板/测试
```

## 16. 第一版实现状态

已完成：

```text
旧 L2 画像停止写入并清空
L2 从 profile()/默认检索移除
L4 从“关系/规矩”改为核心记忆槽位
profile() 不再每轮返回 L2/L4
dsh-remembers 不再把 L4 当规矩注入
B 站/自主活动改走 activity
抽取器只抽 L1/L3
批量任务不再生成 L4 规矩
MCP 的 tier 说明已更新
```

数据迁移：

```text
L2 7 条：备份后清空，画像已在 persona.user_profile
L4 5 条：备份后清空
L4 中 3 条未覆盖的规矩补进 persona important.self
L3 57 条 B 站/自主活动：迁到 activity_log
L3 4 条 curated 真实事件：提升为 L4 核心记忆
L3 剩余 15 条 episode：普通经历
```

当前：

```text
L0 308
L1 125
L3 15
L4 4
activity_log 625
```

还没做：

```text
L2 判断层接入
L4 核心记忆自动提升
L4 核心记忆召回 UI/工具
历史 B 站 L3 清理
service/test_core 等旧测试同步
```

所以现在 L4 有 4 条历史核心记忆，自动提升还没接上。

## 17. source_ids 约定

`source_ids` 不是自动推导的，是写入时由生产者带上的。

2026-11-07 修订：`source_ids` 统一表示**精确 L0 证据 id**；直接输入层用 `derived_from`，详见第 20 节。

```text
L1 事实   → source_ids = L0 id
L2 判断   → source_ids = L0 证据；derived_from = L1 id
L3 经历   → source_ids = L0 证据；derived_from = L1/L2 id
L4 核心   → source_ids = L0 证据；derived_from = L3 id
```

### L4 提升时怎么填

从 L3 提升一条核心记忆时：

```text
source_ids = 那条 L3 指向的 L0 证据
derived_from = [l3.id]
```

如果要保留完整证据链：

```text
source_ids = l3.source_ids
derived_from = [l3.id]
```

### 现有 4 条 L4

它们是历史迁移数据，原 L3 没有 `source_ids`，所以现在是：

```json
"source_ids": []
```

不要用时间窗口硬猜，也不要伪造来源。

可以标记为：

```text
tags = ["core", "migration"]
```

表示“核心记忆，来源链缺失”。

### 空 source_ids 的含义

```text
空 = 来源未知 / 历史迁移
不是“没有来源”
```

面板只显示来源数量，不直接展示 id。

### 以后要补什么

```text
复盘提升 L4 时写 source_ids
L4 详情页显示来源 L3/L0
历史 4 条保持空，不补假数据
```

## 18. evidence 与精确 source_ids

状态：L1 和 L3 的 evidence 匹配与 source_status 第一版已实现；L4 自动提升未接。

### 18.1 决定

模型不填数据库 id。

模型只给**短原话**，代码负责匹配和写 `source_ids`。

```text
模型：这段记忆来自哪句话
代码：这句话对应哪条 L0/L1
```

### 18.2 输入格式

给模型一批带局部序号的原文，不暴露数据库 id：

```text
[1] 主人：你给自己取个名字吧
[2] 我：叫洄，洄游的洄
[3] 主人：为什么
```

批次控制：

```text
L0 → L1：6–12 条
L1 → L3：6–10 条
```

太大模型抄不准。

### 18.3 输出格式

```json
{
  "text": "主人让她给自己取名字，她取名为「洄」",
  "tier": "L1",
  "evidence": [
    "主人：你给自己取个名字吧",
    "我：叫洄，洄游的洄"
  ]
}
```

不输出：

```text
source_ids
数据库 id
批次序号
```

### 18.4 代码匹配

流程：

```text
evidence 逐条
→ 在当前批次原文里找
→ 命中哪条，就取哪条的 id
→ source_ids = 命中的 id 列表
```

匹配顺序：

```text
1. 精确子串
2. 去空白/标点/大小写后精确
3. 模糊相似度
```

模糊匹配可以容错：

```text
标点差异
空白差异
全角/半角
模型少抄一两个字
```

但不能接受：

```text
整句改写
把两句话拼成一句
从上下文补一句没出现的
```

建议阈值：

```text
相似度 >= 0.85
短于 4 个字的 evidence 不做模糊匹配
```

同一句话命中多条原文时：

```text
优先时间最近
或同一轮
无法区分就标记 ambiguous
```

### 18.5 source_ids

匹配成功后：

```text
source_ids = 命中的 L0/L1 id
source_status = verified
```

匹配失败：

```text
source_ids = []
source_status = unverified
```

历史迁移：

```text
source_ids = []
source_status = legacy
```

### 18.6 删除粗粒度来源

有 evidence 后，不再保留：

```text
source_batch_ids
批次级 source_ids
```

只保留一个字段：

```text
source_ids = 精确来源
source_status = verified / unverified / legacy
```

不退回批次 id。

### 18.7 L4 的来源

L4 从 L3 提升时：

```text
derived_from = [l3.id]
source_ids   = l3.source_ids（L0 证据）
source_status = verified
```

合并多条 L3：

```text
derived_from = [l3_a, l3_b, ...]
source_ids   = 这些 L3 指向的 L0 证据
```

如果 L3 自己没有 source_ids：

```text
source_ids = []
source_status = unverified
```

不要伪造 L0 来源。

### 18.8 失败处理

```text
evidence 匹配失败
→ 记忆仍然保留
→ source_ids 空
→ source_status 标记 unverified
```

不要因为来源没匹配上就丢记忆。

也不要伪造 id。

### 18.9 现有数据

4 条历史 L4：

```text
source_ids = []
source_status = legacy
tags = ["core", "migration"]
```

不补假来源。

L1/L3 现有批次级 source_ids 可以保留为历史，不重写。

### 18.10 还需要定

```text
模糊匹配具体用 difflib 还是编辑距离
相似度阈值 0.85 是否合适
同一句命中多条时怎么选
evidence 是否要单独存原文
source_status 是否加列
```

### 18.11 一句话

```text
模型负责指认原话
代码负责把它变成 id
匹配不上就 unverified，不猜
```

### 18.12 第一版实现

已加：

```text
service/evidence_match.py
  normalize
  match_evidence
```

匹配：

```text
精确子串
去标点/空白/大小写
difflib 最长公共片段覆盖 >= 0.85
```

已加列：

```sql
source_status TEXT NOT NULL DEFAULT 'legacy'
```

状态：

```text
verified
unverified
batch
legacy
```

当前实现：

```text
L1 批次抽取：
  模型输出 evidence
  extract_batch 取回 L0 原文
  match_evidence 映射 id
  写 source_ids + source_status

L3 episode：
  模型输出 text + evidence
  evidence 匹配输入 L0
  source_ids = 命中的 L0 id
  source_status = verified / unverified

L4 核心：
  历史 4 条 source_status = legacy
```

已回填：

```text
L1 128 条 legacy
L3 16 条 batch
L4 4 条 legacy
```

还没做：

```text
L4 提升时写 source_ids
面板显示 source_status
```

测试：

```text
tests/test_evidence_match.py
  精确命中
  标点容错
  轻微漏字
  无命中
  空 evidence
```

## 19. L2 判断层

状态：方案，未实现。

### 19.1 定位

```text
L1 = 他说过什么
L2 = 我推测什么
L3 = 发生了什么
L4 = 什么忘不掉
```

L2 不是事实，是解释。

### 19.2 例子

```text
L1：主人说导师还没回消息
L2：他可能有点焦虑（confidence 0.6）

L1：主人今天加班到十点
L2：他今天大概很累（confidence 0.7）
```

### 19.3 字段

```json
{
  "text": "他可能有点焦虑",
  "tier": "L2",
  "confidence": 0.6,
  "basis": ["L1 id 或 L3 id"],
  "status": "hypothesis",
  "expires_in_days": 14
}
```

### 19.4 生命周期

```text
默认 hypothesis
7–30 天衰减

被证实 → 升 L1 / L3 / persona
被否定 → 删除或标 false
```

### 19.5 注入

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

### 19.6 检索

```text
默认对话不召回 L2
需要判断/猜测时显式查
高相关才召回
```

### 19.7 风险

```text
模型判断可能错
confidence 可能虚高
判断会自我强化
判断污染事实和人格
```

所以 L2 必须：

```text
单独存
带依据
带置信度
默认短寿命
不直接当事实注入
```

## 20. 分层来源

状态：方案，未实现。

### 20.1 数据流

```text
L0 原话
 ├─ L1 事实
 ├─ L2 判断
 └─ L3 事件
      └─ L4 核心记忆
```

但不是简单的一条线。

### 20.2 各层输入

```text
L1 ← L0
L2 ← L0 + L1
L3 ← L0 事件窗口 + L1 + L2
L4 ← L3 + L0 证据
```

### 20.3 为什么 L2 不只从 L0

如果 L2 只看 L0：

```text
模型直接从原话猜“他焦虑”
```

没有事实层约束，容易过度推断。

更稳的顺序：

```text
L0 → L1 事实
L1 + L0 → L2 判断
```

L2 的解释必须能指回具体事实。

### 20.4 L3 要不要带 L0

要。

但只带**这段事件窗口的 L0**，不是整天 L0。

原因：

```text
L1/L2 已经是抽象
没有 L0 就失去时间顺序和原话
容易把“总结的总结”写成空话
```

L3 输入：

```text
最近一段 L0（按时间）
+ 这段 L0 抽出的 L1
+ 这段 L0 产生的 L2
```

### 20.5 L4 从哪来

L4 主要从 L3 来。

```text
L3 事件
→ 复盘判断“这件事忘不掉”
→ L4 核心记忆
```

L0 作为证据保留。

L1 可以提供人物/事实背景，但不是 L4 的主要来源。

L2 可以作为“这件事为什么重要”的信号，但不是来源。

```text
L4 ← L3（主）
   ← L0（证据）
   ← L1（背景）
   ← L2（重要性信号，可选）
```

不要：

```text
L1 直接升 L4
L2 直接升 L4
```

那会变成“事实/猜测变核心记忆”。

### 20.6 来源字段

建议拆成两个：

```text
source_ids    = 精确 L0 证据 id
derived_from  = 直接输入层 id（L1/L2/L3）
```

对应：

| 层 | source_ids | derived_from |
| --- | --- | --- |
| L1 | L0 | 空 |
| L2 | L0 证据 | L1 |
| L3 | L0 证据 | L1 / L2 |
| L4 | L0 证据 | L3 |

这样：

```text
source_ids 回答“哪句原话”
derived_from 回答“从哪些记忆推出来”
```

### 20.7 例子

```text
L0：主人说导师还没回消息
L1：主人说导师还没回消息
L2：他可能有点焦虑（basis = L1）
L3：等导师回复的这段时间，他反复看手机，后来干脆不看了
L4：那晚他第一次说“我是不是不适合读研”
```

对应：

```text
L2.source_ids = 那条 L0
L2.derived_from = [L1 id]

L3.source_ids = 这段 L0 的多条 id
L3.derived_from = [L1, L2]

L4.source_ids = 那晚的 L0
L4.derived_from = [L3]
```

### 20.8 一句话

```text
L1 记事实
L2 记解释
L3 记故事
L4 记故事里忘不掉的那一段
```

越往上，越依赖下层，但不能脱离 L0 证据。

## 21. L3 是事件线程，不是单段总结

状态：方案，未实现。

### 21.1 问题

5 分钟空闲适合切 L1/L2。

但 L3 可能跨段、跨天：

```text
晚上：牙疼
第二天：去排队看牙
看完：只是牙龈发炎，没啥事
→ 这时事件才结束
```

如果每段产一条 L3：

```text
L3-1 牙疼
L3-2 去看牙
L3-3 没事了
```

事件被切碎，失去前因后果。

### 21.2 定义

```text
L3 = 一条有生命周期的事件线程
不是“某段对话的总结”
```

状态：

```text
open     还在进行
closed   已经结束
dormant  很久没提
```

### 21.3 字段

```json
{
  "tier": "L3",
  "title": "牙疼看牙",
  "status": "open",
  "opened_at": 1793970000,
  "last_seen_at": 1793970000,
  "closed_at": null,
  "summary": "牙疼，准备去看牙",
  "source_ids": ["L0 id"],
  "derived_from": ["L1 id", "L2 id"]
}
```

### 21.4 每段结束后的处理

```text
L1/L2 完成
→ 读取 open 的 L3 候选
→ 判断这一段：
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

开启：

```text
只有事件值得跟踪时才新建 L3
```

无关：

```text
不产生 L3
```

### 21.5 关闭条件

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

就关闭 L3。

很久没提：

```text
超过 N 天没有续写 → dormant
```

不是删除。

### 21.6 检索与优先级

不是“少量注入”。

少量注入的问题是：

```text
没被选中的 open L3 就完全消失
模型不知道还有这件事没完
```

更合理的做法：

```text
全量进入候选
→ 按相关性和优先级排序
→ 选 top K 注入详情
→ 其余 open 只注入标题索引
```

#### 候选

```text
所有 open L3
+ 相关 closed L3
```

open 不是无条件注入，closed 也不是无条件排除。

#### 硬门槛

先看相关性：

```text
和当前话题 / 用户消息相关
```

不相关的 open L3，即使没关闭，也不该塞进这一轮。

#### 排序因素

```text
相关性
open 状态加成
last_seen_at 新鲜度
importance / 情绪重量
是否悬而未决
```

大致：

```text
score = relevance
      + open_boost
      + freshness
      + importance
```

权重先不定，但 open 应该比同等相关性的 closed 优先。

#### 预算

```text
top K 详情：按当前 token 预算
其余 open：标题 + 一句话状态
```

索引例子：

```text
【还没完的事】
- 牙疼看牙 · 等结果 · 11-06
- 导师回复 · 还没回 · 11-05
```

索引规则：

```text
包含全部 open L3
每条只留 标题 / 一句话状态 / 最后提及
不暴露数据库 id
不写 summary
不写 evidence
不写完整经过
```

标题就是模型侧的操作句柄。

需要细节时：

```text
get_open_thread(query="牙疼看牙")
```

服务端负责：

```text
标题精确匹配
别名匹配
去标点/空白匹配
模糊匹配
```

匹配不到：

```text
返回候选标题，不猜
```

匹配到多条：

```text
返回 ambiguous + 候选标题
```

标题可以重复，所以 L3 内部保存：

```text
title
aliases
last_seen_at
```

模型调用时可以再带一个时间提示：

```text
get_open_thread(query="导师回复", around="11-05")
```

模型不接触 id。

#### 索引会不会太长

全部 open 都进索引，但 open 数量本身要有上限：

```text
最多 30 条 open
超过 → 合并 / 关闭 / dormant
```

不是截断索引，是控制 open 数量。

一条索引约 1 行，30 条约几百 token，可接受。

#### 工具

可以加：

```text
list_open_threads()
```

用来列出全部 open L3，避免索引截断后彻底看不到。

#### 原则

```text
open 优先，但不是无条件优先
相关才注入
不相关也要在索引里可见
```

不要把 open L3 全部每轮注入详情。

### 21.7 L4

L4 只从：

```text
closed / 有结论的 L3
```

提升。

不要把 open 的事件提前封成“核心记忆”。

### 21.8 例子

```text
段 1：
主人说牙疼
→ L3 open：牙疼/看牙

段 2：
主人去排队，结果是牙龈发炎，没啥事
→ 续写同一 L3
→ status = closed
```

最终：

```text
牙疼 → 去看牙 → 牙龈发炎 → 没事
```

### 21.9 还需要定

```text
thread_key 怎么生成
怎么判断“同一事件”
open L3 最多保留多少条
dormant 多少天
open L3 是否注入 state
L3 续写时 summary 重写还是追加
open_boost / freshness / importance 的权重
索引最多列几条 open L3
list_open_threads 是否给模型
```

先记录，不改代码。










