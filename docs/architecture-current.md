# 当前架构与待办

状态：设计已定，大部分未实现。

最后更新：2026-11-11。

相关文档：

- [人格分层](persona-layers.md)
- [人格与情绪重构](persona-refactor.md)
- [记忆分层](memory-layers.md)
- [L1/L3 写法与例子](memory-writing.md)

---

## 1. 数据分层

```text
【稳定层】人格
  核心设定        手编 + 半自动确认
  用户画像        每 2 天自动重写
  重要标记        优先级标记，不是独立类别

【中间层】最近的我
  日记            今天怎么样了
  （原自我认知的变化、没想清，待并入）

【记忆】
  L0  原话
  L1  这一段发生了什么
  L2  我的判断（暂退）
  L3  为什么值得记久
  L4  核心记忆

【其他】
  activity_log   行为日志
  browse（待建）  B站浏览记录
```

现库量：

```text
L0   551
L1   290
L2    93
L3   130    open 10 / dormant 7 / closed 13 / standalone 84 / archived 16
L4     4
```

## 2. 人格结构

### 2.1 核心设定六小节（已落地）

```text
## 我是谁
## 表现          style 标记在这里
## 价值取向
## 弱点
## 我们怎么对彼此
## 我们之间有什么   important 标记在这里
```

待加：

```text
## 偏好          长期稳定的喜欢/不喜欢
```

即最终七小节，对应「我自己」五格：

```text
我是谁 / 表现 / 偏好 / 价值取向 / 弱点
```

「我眼中的他」同样五格：

```text
他是谁 / 他平时什么样子 / 他的偏好 / 他的价值取向 / 他的软处
```

### 2.2 重要标记

```text
<!-- important:begin -->
- ...
<!-- important:end -->
```

含义只有一条：这几条可以盖过其他条目。

`important.md` 是镜像，服务端靠标记同步。

### 2.3 每条存「成了什么样」

```text
存：     - 被留的时候，我是当真的。
不存：   - 他说想留住我那天，我话说一半就收了。
```

关联事件：

```text
- 被留的时候，我是当真的。{{L3:1245}}
```

三种渲染：

| 场景 | 渲染成 | 用途 |
| --- | --- | --- |
| 面板 | 标题，可点 | 人看依据 |
| 日常对话 | 抹掉 | 保住 system prompt 缓存 |
| 复盘 | 标题 + 状态 + L3 正文 | 判断还成不成立 |

### 2.4 画像与核心设定的关系

```text
存储分开    核心设定手编，画像 2 天一刷
渲染合一    persona.mjs 先核心设定、再画像
```

合并存储会让画像重写把手编内容冲掉。

## 3. 记忆层级边界

### 3.1 判断规则

```text
L1  这一段发生了什么
L3  为什么这件事值得记久
```

判断方法：

```text
这条不写，丢的是经历还是认识？
丢经历 → L1
丢认识 → L3
```

### 3.1b 图结构与证据清单

```text
memory_links   派生关系：谁从谁来的
evidence_ids   完整证据：这条引用了哪些 L0，展开成闭包
```

两者不重复：前者说明结构，后者提供内容。

### 3.2 L1 字段

```text
text           便签
ts             时间
evidence_ids   指向 L0（见 3.5）
tags           来源标记

emotion_label / emotion_valence / emotion_arousal
               当时什么感受

want_more      想自己接着弄明白的
ask_him        想问他的
```

### 3.3 L3 字段

```text
summary / text      重写后的当前状态
thread_*            生命周期

insight_text / insight_kind
                    这件事留下的认识

memorability / dominant
                    为什么难忘

recall_* / lifecycle_*
                    遗忘曲线、复盘状态
```

### 3.4 L4 字段

```text
text            重写后的版本（不是复制 L3）
evidence_ids    它引用的全部 L0
来源            memory_links 里 L3 --core--> L4
```

### 3.5 source_ids 改名 evidence_ids，存传递闭包

语义固定为「这条记忆引用的全部 L0 原话」。

```text
L1    自己的 L0
L3    自己的 L0 + 它 L1 的 L0（展开后全部）
L4    它 L3 的全部 + 自己新增的 L0
```

写入时就排好时间顺序，读的时候直接用，不用再排。

现在各层长度：

```text
L1  平均 3.0   最大 12
L2  平均 1.6   最大 4
L3  平均 3.3   最大 14
```

展开后会更长，渲染时按需截断。

### 3.6 图和 evidence_ids 的分工

```text
evidence_ids   完整证据清单，扁平，随时可用
memory_links   派生结构，说明谁从谁来的
```

有了 evidence_ids，L4 复盘只需要「L3 正文 + 它的 evidence_ids 展开的原话」，不用遍历图。

### 3.7 图的传递约简

写边时检查：这条边能不能由已存在的路径到达。

```text
如果 L3 → L1 → L0 已经连通
就不再写 L3 → L0 这条直接边
```

只在写入时做，不做定期全表检查。

实测可约简 245 / 1034 条（23.7%）。

### 3.8 无环

```text
层方向    L0 → L1 → L3 → L4，天然无环
L3 内部   实测无环
```

L3 指向 L3 的 41 条边全部是 `role=legacy`：

```text
#319「旧流水账 · 2026-11-02 凌晨」archived
  → 734《岛夷志略》澳洲记载
```

是旧流水账拆成事件线程留下的，不是来源关系。

处理：

```text
删掉这 41 条 legacy 边
archived 的流水账实体保留
```

现在不再产生这种边。

### 3.9 L4 改为重写

```text
输入    源 L3 正文 + 该 L3 的 evidence_ids 展开的原话
输出    重写后的版本
```

不是复制 L3。

区别：

```text
L3  当时的记录，跟着当时的上下文走
L4  十年后还看得懂，需要补全前因后果
```

允许分叉：L3 关了、合并了，L4 独立存在。

### 3.10 复盘时 L0 按时间正序

```text
L1 批处理     正序（从早到晚）
复盘、重写    正序
对话上下文    倒序（新的在前），这是唯一例外
```

### 3.4 关键约束

```text
insight_* 只在 L3
B站 的 L1 不写感悟
感悟等 L3 批处理时再判断
```

否则两层分不开。

## 4. 提取管线

### 4.1 已定的输入

```text
L1 批处理      L0
L3 批处理      L1 + L2 + 它们的来源 L0
```

L3 顺着 L1 的 `source_ids` 找来源，不需要在字段上标 origin。

### 4.2 现状

```text
L1 批处理   只吃 L0，按时间切段（空闲 300s / 跨度 30min / 80 条）
L3 批处理   只吃本批 L0 + 本批新 L1 + 本批新 L2
```

**B 站内容现在进不来**，因为：

```text
B站 不写 L0
batch_run 只从 L0 取
→ 永远扫不到
```

### 4.3 待改

```text
1. B站 改成写 L0，走同一条链
2. L3 批处理改为顺 source_ids 找 L0
```

## 5. 情绪

### 5.1 已定

```text
情绪跟着 L1 走
memory 表加三个字段：emotion_label / emotion_valence / emotion_arousal
L1 抽取时整批都写
```

模型本来就在每条 L1 上给情绪，代码现在整批只挑一条，改成全写。

### 5.2 emotion_log 删除

功能都能被替代：

```text
最近 3 条明细    → 从最近带情绪的 L1 挑
历史统计         → 从 L1 按字段聚合
复盘素材         → L1 / L3 已经带了
```

「当前心情」那两个数（valence / arousal）也删，那是上一段对话的情绪，挂在全局 state 上是错位。

连带删除：

```text
set_emotion
state.emotion
state.mjs 里「心情（很开心，有点激动）」
qqbot/domains/growth/emotion.py
```

`mood`（happy / tired / annoyed）是另一套，不动。

### 5.3 情绪只在 L1 抽取时写

不每句复盘，不空闲复盘。

L1 抽取本来就在读那段对话，`EXTRACT_SYSTEM` 已经要求判断情绪。

## 6. 兴趣系统

### 6.1 现状

`bili-autonomy/interests.json`，33 个话题：

```json
{"topic": "王者荣耀", "weight": 9.0, "evidence": "...", "source": "chat"}
```

`source` 混着两种：

```text
chat    主人聊出来的
bili    我自己刷出来的
```

### 6.2 问题

```text
1. weight = 被提到的次数，不是兴趣深度
2. 主人提到的话题被直接算成她的兴趣
3. 没有「还想知道什么」，刷完就完了
4. 选材按权重随机抽，会自我强化
```

### 6.3 设计方向：不判阶段，只判要不要回来

研究依据（Hidi & Renninger 四阶段模型、信息缺口理论）指向一个结论：

```text
好奇不等于兴趣
答完问题，好奇就填平了
有新问题，兴趣才继续
```

所以不问「现在第几阶段」，只问：

```text
还有没有接着想弄明白的？
```

### 6.4 统一的出口

```text
刷完视频  → 问一句
聊完天    → 问一句
```

两种去处：

```text
想问主人的   → ask_him
想自己刷的   → want_more
```

### 6.5 选材顺序

```text
1. 最近 L1 里 want_more 非空且未用的   优先
2. 没有就按兴趣权重抽
3. 权重池也空                          自由探索
```

want_more 用掉后在 L1 上标记，不新建表。

### 6.6 权重只说明「她自己给了意义」

```text
want_more 驱动的轮次    不加权重
chat 来源的话题         被抽中也不加权重
只有她自己在 L1 里写了在意什么的  才加
```

### 6.7 长期兴趣不在这层判

```text
兴趣池只回答「下一轮看什么」
长期兴趣由人格复查判断（review.py）
```

理由：30 天一次的人格复查本来就在读长期记忆，让它顺带看兴趣池，
比在兴趣系统里加一套阶段判断简单。

## 7. B 站

### 7.1 现状

```text
activity_log 里 86 轮
有 summary 的     8 轮
有 insight 的     7 轮
转成 L3 的        7 轮
```

只有 8% 的轮次有 summary，这本身是个问题。

### 7.2 已定的改法

```text
B站 写 L0（不是 activity）
L1 批处理统一处理
L3 批处理顺着 L1 找到它
```

好处：

```text
1. 管线统一，不需要额外入口
2. L1 天然成为筛选层：刷 7 轮 → 只有带感悟的进 L1
3. L3 不再被 B站 稀释
```

### 7.3 感悟的落点

```text
B站 的 L1    只写：看了什么 / 什么感受 / 留下什么问题
感悟         不写
             等 L3 批处理再判断要不要立成 L3
```

### 7.4 ask_him 的消费方

只在日常聊天用，不进主动说。

```text
每轮对话开始
  → 从最近 L1 里挑 0–2 条 ask_him 非空的
  → 混在普通记忆里给模型
```

不单独标注，不加提示词。模型看到自然会问，不问也行。

为什么不用在主动说：

```text
主动说已经有「分享视频 / 闲聊 / 关心」作为平级选项
再加一个「你有问题想问」，会把它挤成只剩问问题
```

## 8. 待办清单

### 8.1 人格

```text
[ ] 核心设定加「偏好」栏
[ ] 画像对齐五格，清掉互动偏好 / 边界
[ ] 自我认知并进中间层（删「我学到的」）
```

### 8.2 记忆

```text
[ ] memory 表加 emotion_label / emotion_valence / emotion_arousal
[ ] memory 表加 want_more / ask_him
[ ] L1 抽取整批写情绪（不再只挑一条）
[ ] 删 emotion_log 表（先导出 93 条历史）
[ ] 删 set_emotion / state.emotion / emotion.py
[ ] state.mjs 去掉情绪段
[ ] B站 改写成 L0
[ ] L3 批处理改为顺 evidence_ids 找 L0
[ ] L1 分段 30 分钟 → 5 分钟
[ ] insight_kind → insight_target（me / us / none）

[ ] source_ids 改名 evidence_ids
[ ] evidence_ids 改成传递闭包（写入时展开并按时间排序）
[ ] 写入时做传递约简（间接可达就不写直接边）
[ ] 删掉 41 条 role=legacy 的 L3→L3 边
[ ] L4 改成重写（输入 L3 正文 + 展开的 L0）
```

### 8.3 兴趣

```text
[ ] 选材顺序改成「L1 里未用的 want_more → 权重 → 自由探索」
[ ] 权重只在「自己写了 care」时增加
[ ] chat 来源的话题只进候选，不直接算她的兴趣
[ ] want_more 用掉后在 L1 上标记（不新建表）
```

不新建 questions 表：

```text
want_more   存在 L1，选材时从最近 L1 里挑未用的
ask_him     存在 L1，对话上下文渲染时挑 0–2 条
用没用      在 L1 上加一个 used 标记
```

兴趣池保持「话题 + 权重」，不加 questions 数组。

### 8.4 人格关联机制

```text
[ ] {{L3:id}} 存储
[ ] 三层渲染（面板可点 / 日常抹掉 / 复盘带正文）
[ ] 面板跳转
```

### 8.5 复盘模块分工

```text
[ ] important.py   只管新增带重要标记的条目
[ ] review.py      一次判断四类：价值取向 / 偏好 / 我们怎么对彼此 / 弱点
                   不再产出约定
[ ] style.py       只改「表现」
[ ] reflect.py     只写中间层
[ ] profile.py     只写画像（他的偏好，不是她的）
```

review.py 为什么一次判断四类：

```text
它本来就在读「最近对话 + 长期记忆，判断人格要不要改」
偏好和价值取向是同一个判断的产物
分两个入口会重复读同样的素材
```

四类的区别要写进 prompt：

```text
我是谁        身份、性格
表现          怎么说
偏好          喜欢什么
价值取向      相信什么
弱点          会栽在哪
我们怎么对彼此
我们之间有什么
```

### 8.6 中间层

现在 diary 表：`date / text / mood / created_at`，每天一条，200–400 字。

**没有任何复盘在读它**，`growth/*.py` 都是直接 `collect(l1=50, l3=30, l0=50)`。

全部放 diary，加字段，不单开表：

```text
text            今天怎么样了（已有）
mood            心情（已有，一直空着）
changes         最近在变什么（新增，原自我认知的「最近的变化」）
open_questions  还没想清（新增，原自我认知的「还没想清」）
tasks           正在做的事（新增，可选）
```

```text
[ ] diary 加 changes / open_questions / tasks 三列
[ ] review.py 读最近 7 天日记，作为判断依据
[ ] reflect.py 从日记提炼「变化」，写回 changes
[ ] tasks 并入 diary
```

notes 保留独立，作为「随手记」，跟 diary 并列。四条现有内容不是「今天怎么样了」，硬并会把日记变长。

消费方定的是：

```text
review.py     读日记 → 补判断依据
reflect.py    写日记的「变化」段
主动说        暂不读，容易变成汇报
```

### 8.7 主动说

```text
[ ] B站 改成写 L0 后，主动说的「最近 L0」会混进视频内容
[ ] 保留，但 prompt 里别让它变成「今天看了什么」的汇报
```

不读 ask_him：主动说已有分享 / 闲聊 / 关心三个平级选项，再加「你有问题想问」会挤掉它们。

## 9. 已完成的代码改动

```text
人格
  panel_readers.py            STYLE_HEADING → ## 表现
                              段落正则同步
                              review_apply heading 映射改新四段
  style.py                    style_block 正则同步
  check_persona_boundaries.py CORE_HEADINGS 改六段
  核心设定本身                  已重排并写入

提示词
  qzone/publish.py            九项禁令 → 用途说明 + 三个真实例子
  growth/emotion.py           加两条真实例子（此文件待删）

运维
  panel_routes.py             重启前杀光所有 bridge 实例
  SnowLuma runtime.json       hookAutoLoad: true（开机自动挂 hook）
  维护会话                    按流程分会话，占用 30k 换新
```

备份：

```text
persona-roles/state/constitution-before-struct-20261110-204634.md
D:\QQBot\SnowLuma\config\runtime.json.bak-20261111-123100
```

## 10. 参考

- [Character Card V2](https://github.com/malfoyslastname/character-card-spec-v2)：角色描述与示例分开
- [Letta Memory Blocks](https://docs.letta.com/v1-sdk/memory/memory-blocks/)：常驻片段与长期记忆分开
- [Fate Core: Your Character Idea](https://fate-srd.com/fate-core/your-character-idea)：High Concept 与 Trouble
- [SEP: Friendship](https://plato.stanford.edu/entries/friendship/)：关心、亲密、共同活动
- [SEP: Love](https://plato.stanford.edu/entries/love/)：appraisal / bestowal
- [OISE: Hidi 的兴趣研究](https://www.oise.utoronto.ca/about/news/08-05-24-exploring-interest-education-understanding-core-dr-suzanne-hidis-psychological)：四阶段模型
- [OISE: 兴趣的应用](https://www.oise.utoronto.ca/about/news/08-05-24-application-interest-suzanne-hidis-educational-research-sparks-questions)：好奇 ≠ 兴趣
- [APS: 好奇的刚好区间](https://www.psychologicalscience.org/news/to-spark-curiosity-dont-tell-preschoolers-too-much-or-too-little.html)

## 11. 实现顺序

依赖关系决定顺序，前三步铺完，后面才能动。

### 第一步：数据库

```text
memory 表
  + emotion_label / emotion_valence / emotion_arousal
  + want_more / ask_him / want_used
  source_ids → evidence_ids（改名）

diary 表
  + changes / open_questions / tasks

一次迁移跑完，不动逻辑
```

### 第二步：L1 抽取

```text
整批写情绪（不再只挑一条）
写 want_more / ask_him
evidence_ids 写传递闭包，按时间排好
分段 30 分钟 → 5 分钟
```

### 第三步：B 站写 L0

```text
bili 改成写 L0（不是 activity）
L1 批处理统一处理
L3 批处理顺 evidence_ids 找 L0
```

前三步做完，B 站内容才算真的进了记忆。

### 第四步：L3 / L4

```text
insight_kind → insight_target
写入时做传递约简
L4 改成重写（输入 L3 正文 + 展开的 L0）
删 41 条 legacy 边
```

### 第五步：清理

```text
删 emotion_log（先导出 93 条）
删 set_emotion / state.emotion / emotion.py
state.mjs 去掉情绪段
```

### 第六步：中间层

```text
review.py 读最近 7 天日记
reflect.py 写 diary.changes
```

### 第七步：兴趣

```text
选材顺序改「want_more → 权重 → 自由探索」
权重只在写了 care 时增加
```

### 第八步：人格

```text
核心设定加「偏好」栏
review.py 一次判断四类
画像对齐五格
关联机制 {{L3:id}}
```

### 为什么这个顺序

```text
1-3 都在数据层，一次迁移铺开
4-5 依赖 1-3 的字段
6-7 依赖 4-5 的数据
8 最后做，因为要在真数据上验证
```

## 12. 实现进度

最后更新：2026-11-11 21:15。

### 已完成

```text
第一步 数据库
  memory + emotion_label / emotion_valence / emotion_arousal
         + want_more / ask_him / want_used / insight_target
  diary  + changes / open_questions / tasks
  insight_kind 的存量数据回填到 insight_target（me 10 / us 26 / none 1）

第二步 L1
  每条便签带自己的情绪，不再整批只挑一条
  prompt 加 want_more / ask_him
  分段 30 分钟 → 10 分钟

第三步 B 站
  bili 改成写 L0（tags 带 bili），走统一管线
  对话上下文排除 bili 的 L0

第四步 L3 / L4
  insight_kind → insight_target
  写入时做传递约简（_reaches 检查）
  删掉 41 条 role=legacy 的 L3→L3 边
  L4 改成重写：输入 L3 正文 + 展开的 L0

第五步 清理
  emotion_log 表删除（94 条导出到 docs/emotion-log-archive.json）
  set_emotion / emotion_log_add / emotion_log_list 删除
  qqbot/domains/growth/emotion.py 删除
  state.mjs 去掉情绪段（mood 保留）
  emotion_idle_loop 删除

第六步 中间层
  diary 加三段，diary_add 只更新传了的字段
  reflect.py 读日记、写 changes / open_questions
  review.py 读最近 7 天日记

第七步 兴趣
  选材顺序：L1 未用的 want_more → 权重 → 自由探索
  权重只在自由探索撞到新话题时 +0.2

第八步 人格
  核心设定加「偏好」段（七小节）
  画像改四段：他是谁 / 他平时什么样子 / 他的偏好 / 他的价值取向
  review.py 一次判断四类：preference / judgment / relationship / weakness
  「约定」不再由 review 产出，只由 important.py 新增
```

### 还没做

```text
[ ] {{L3:id}} 关联机制（存储 / 三层渲染 / 面板跳转）
[ ] 复盘时带 L3 正文（人格条目 → source L3 → 全部 L0）
[ ] notes 与中间层的关系（暂时并列）
[ ] 面板显示 diary 的 changes / open_questions / tasks
```

### 验证过的

```text
66 → 60 个测试全过（删掉 emotion idle 那个）
人格边界检查 OK
B 站 L0 写入后，对话上下文仍只含聊天 L0
want_more 选材实测：优先级生效，用掉后标记 want_used
L4 重写实测：输出比原 L3 完整，带了前因和落点
传递约简实测：冗余边被拒，真需要的边照写
```
