# 记忆分层

状态：方案，未实现。

## 1. 结论

不新增 L5，也不把 B 站塞进记忆层。

最终布局：

```text
L0  原话
L1  事实
L2  退役
L3  普通经历
L4  核心记忆

activity：B 站、自主活动
persona：规矩、画像、关系
```

一句话：

```text
L4 记“忘不掉的事”
L3 记“发生过的事”
L1 记“关于他的事实”
L2 不再写新数据
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
他最近在准备转正
```

一句话一条。

稳定事实可以长寿命，不再 30 天就淡掉。

### L2 退役

不再写新数据。

原因：

```text
用户画像归 persona.user_profile
核心记忆归 L4
B 站归 activity
```

L2 没有独立职责了。

现有 L2 数据按迁移方案处理。

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
+ L3 相关经历
+ L4 少量核心记忆（高门槛）
```

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
停止新写入
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
  L2 不再使用
  L4 改为不衰减核心记忆

profile()：
  不再注入 L2
  L4 不再每轮注入

extractor：
  L2 画像改走 persona.user_profile
  L4 不再由抽取器直接写规矩

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
L2 退役：不进 profile()
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
L2 不再写
稳定画像走 persona.user_profile
profiles.profile 只保留历史/停止增长
```

否则清空 L2 后，`profiles.profile` 仍会继续长。

#### 抽取器

现在：

```text
EXTRACT_SYSTEM 输出 L2 / L4
batch_l4 每天从 L1/L3 提炼 L4
```

改成分层后：

```text
不再抽 L2
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
L2 从默认检索移除
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



