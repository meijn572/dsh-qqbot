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
source_ids   完整证据：这条引用了哪些 L0，展开成闭包
```

两者不重复：前者说明结构，后者提供内容。

### 3.2 L1 字段

```text
text           便签
ts             时间
source_ids   指向 L0（见 3.5）
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
source_ids    它引用的全部 L0
来源            memory_links 里 L3 --core--> L4
```

### 3.5 source_ids 的现行语义（改名与闭包未做）

代码里仍是 `source_ids`，存的是**这条记忆直接引用的 L0 id**：

```text
L1    它自己那些 L0
L3    模型挑出来的 L0（不一定是全部）
L4    继承源 L3 的 L0
```

计划过改成 `source_ids` 并展开成传递闭包，但因为涉及 schema、接口和 58 处引用，
一直没动。文档里凡是写 `source_ids` 的地方都按 `source_ids` 理解。

### 3.6 图和 source_ids 的分工

```text
source_ids   完整证据清单，扁平，随时可用
memory_links   派生结构，说明谁从谁来的
```

有了 source_ids，L4 复盘只需要「L3 正文 + 它的 source_ids 展开的原话」，不用遍历图。

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
输入    源 L3 正文 + 该 L3 的 source_ids 展开的原话
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
[ ] L3 批处理改为顺 source_ids 找 L0
[ ] L1 分段 30 分钟 → 5 分钟
[ ] insight_kind → insight_target（me / us / none）

[ ] source_ids 改名 source_ids
[ ] source_ids 改成传递闭包（写入时展开并按时间排序）
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
  source_ids → source_ids（改名）

diary 表
  + changes / open_questions / tasks

一次迁移跑完，不动逻辑
```

### 第二步：L1 抽取

```text
整批写情绪（不再只挑一条）
写 want_more / ask_him
source_ids 写传递闭包，按时间排好
分段 30 分钟 → 5 分钟
```

### 第三步：B 站写 L0

```text
bili 改成写 L0（不是 activity）
L1 批处理统一处理
L3 批处理顺 source_ids 找 L0
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

### 关联机制（已完成）

```text
存储     人格条目行尾带 {{L3:123}}，指向 L3 或 L4
日常     persona.mjs 正则抹掉，模型看不到
复盘     expand_persona_links 展开成「〔标题 · 状态〕正文」
面板     _render_links 展开成「〔标题〕」，查不到就抹掉
写入     review 输出带 source，apply 时自动补链接
```

三种渲染的用途：

```text
日常抹掉   保住 system prompt 缓存；避免「你那次说过……」式复述
复盘展开   判断这条还成不成立，要看当时具体说了什么
面板展开   人要知道这条判断从哪来
```

### 复盘时摊开原话（已完成）

```text
/context/evidence 支持按 ids 精确取
  原来：按时间取最近 N 条
  现在：给了 ids 就只处理这些

expand_persona_links
  展开成「〔标题 · 状态〕正文」
  下面再跟一行「当时的话：」+ 最多 3 句 L0 原话
```

实测一条人格条目的复盘视图：

```text
- 人设是我自己写的…… 〔记忆库新方案与取舍 · open〕
  他拿记忆库新方案来问我，先问我想不想更像人……
  当时的话：主人：我对于你的记忆库有了新的方案，但是想先问问你的想法
           我：说说是什么。听完我再讲想法，不然现在表态也是空的。
```

### 面板显示日记三段（已完成）

小本子里日记按段显示：正文 / 最近在变 / 还没想清 / 正在做。

### 还没做

```text
[ ] notes 与中间层的关系（暂时并列）
[ ] 面板上点关联词条能跳到对应的事件
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

## 13. 提示词归属

规则：**提示词跟着领域走，bridge 只管收发和调度。**

### 现在的位置

```text
service/extractor.py          所有抽取类提示词（L1/L2/L3/L4/生命周期/压缩）
qqbot/domains/growth/         人格复盘：review / reflect / profile / style
qqbot/domains/autonomy/       B站：round（看视频）、interests（兴趣提取）
qqbot/domains/proactive/render.py   主动说、群内搭话、B站链接提示
qqbot/domains/group/slang.py        群黑话抽取
qqbot/domains/group/lexicon.py      词库复盘
qqbot/domains/media/stickers.py     表情复盘
qqbot/domains/qzone/publish.py      说说
```

### 从 bridge 里搬走的

```text
proactive_say           → proactive/render.py   render_prompt
topic_relevant          → proactive/render.py   group_topic_prompt
bili_link_hint          → proactive/render.py   bili_link_hint
extract_group_slang     → group/slang.py        render_group_slang_prompt
review_lexicon          → group/lexicon.py      render_review_prompt
review_sticker          → media/stickers.py     render_sticker_review_prompt
```

bridge.py 从 2768 行降到 2668 行，剩下的中文都是状态判断、日志和字段名，不是提示词。

### 为什么这么分

```text
提示词是领域知识    改提示词不该碰网络层
bridge 是传输层     只负责取数据、调模型、发消息
```

判断方式：如果改这句话会影响「她怎么看这件事」，它属于领域；如果只影响「怎么发出去」，留在 bridge。

### 还没搬的

```text
_process_locked       session 生命周期，暂时留在 bridge
inject_watch          注入监听，跟传输耦合
session_watch         会话状态监控
```

这三个跟 DSH 会话的生命周期绑着，搬出去反而要多传参数，先留着。

## 14. 首次全链路自检（2026-11-12 凌晨）

跑了一遍真实数据，发现三处没做好，已修。

### 修掉的问题

```text
1. update_thread 不认 insight_target
   server.py 改了调用，memory_core 的签名没跟着改
   → 每次 L3 更新抛 TypeError，整批 500，B站 L0 因此从没变成 L1

2. _is_speculation 见「可能」就丢
   老设计（L1 只收确定事实）的遗留
   「视频说阳光可能不是必需条件」这种引用被整条吃掉
   → B站 的 L1 经常凭空消失
   改成：只在主语是他、又没有转述动词时才判推测

3. B站 还在直接写 L3
   round.py 里 log_activity 仍带 insight，绕过 L1
   → 和「B站 只写 L0」的设计冲突，且和 L1 那条重复
   改成只记活动日志，不再产出 L3
```

### 现在的链路（实测通过）

```text
B站 刷一轮
  → 写 L0（tags 带 bili）
  → L1 批处理产出 L1，带 want_more
  → L2 / L3 正常派生
  → pick_topic 优先取未用的 want_more
```

实测那轮的产物：

```text
L0  我：刷了「深海热泉」…
L1  我刷了一条讲生命起源的科普…（want_more：海底热泉化学梯度合成氨基酸的实验证据）
L2  我最近可能对生命起源这类科普保持兴趣
L3  我刷了「深海热泉」那条…
```

### 仍然没验证到的

```text
日记三段（changes / open_questions / tasks）
  读写函数已单测通过，但 reflect 每天才跑一次，还没有真实产出
人格复盘读日记
  同上，要等下一次 review
会话自动换新（人格指纹）
  逻辑在，未制造人格变更去触发
```

## 15. 接口对齐与遗留清理（2026-11-12 凌晨）

### 修掉的不对齐

```text
/state 的 emotion_recent   还在调已删的 emotion_log_list（被 except 兜住，永远空）
                           改成从带情绪的 L1 取
/activity                  还留着「bili 感悟直接造 L3」的分支
                           删掉，B站 只走 L0 → L1 → L3
/bili/insights             按 insight_kind（self/style/relation）过滤
                           改成按 insight_target 过滤，老名字自动翻译
关系复盘查询                 依赖 relationship_impact（全库为空，拿不到素材）
                           改用 insight_text
面板线程/活动                 暴露 insight_kind、relationship_impact
                           改成 insight_target；活动行不再显示分类
前端标签                     self/style/relation → me/us/none
set_emotion 工具            插件还在注册，打到已废弃的 /emotion（410）
                           注销并从三份副本里删除
插件工具速查                 还写着「有真实情绪：set_emotion(...)」
                           删掉
插件设置页                   还有「情绪记多细（emotion_log）」滑杆
                           删掉
全局 valence / arousal      设计上已退役，代码还留着 get/set_emotion
                           删除，/state 不再返回这两项
L2 过期上限                  文档写 7 天，代码还是 30
                           改成 7
服务端分段配置                config.json 写到 D:\QQBot\dshbot，服务实际读
                           remembers-data/config.json，等于没生效
                           补写到正确路径
```

### 三份插件副本

之前散在三处，各改一半：

```text
D:\QQBot\dshbot\plugins\dsh-remembers                     仓库（源头）
C:\Users\12152\.dsh-qqbot\plugins\dsh-remembers          旧位置
C:\Users\12152\.dsh\profiles\qqbot2\node_modules\...   DSH 实际加载
```

现在以仓库那份为准，app.mjs / client.js / hooks 两份都已同步，hash 一致。
**以后改 hook 要改仓库那份再同步，否则不生效。**

### 保留的兼容层（有意为之）

```text
memory.insight_kind      老数据还靠它分类，bili_insights 会同时查两列
memory.relationship_impact 列留着，代码不再写
activity_log.insight/insight_kind 历史活动数据还在
```

### 还没做的

```text
source_ids 改名 evidence_ids + 展开成传递闭包   文档已按现状改成 source_ids
ask_him 进对话上下文                            字段有了，还没接渲染
日记三段真实产出                                等 reflect 跑
```

### 生效需要重启 DSH

插件改动（注销 set_emotion、state.mjs 去掉情绪块）要等 60773 那个进程重启才生效。
在此之前，模型若调用 set_emotion 会拿到 410。

## 16. 面板人格改成两块（2026-11-12）

### 结构

```text
我自己
  我是谁 / 表现 / 偏好 / 价值取向 / 弱点
我和他
  我眼中的他（= user_profile 画像）
  我们怎么对彼此
  我们之间有什么
```

后端 `/api/persona` 多返回一个 `blocks`：

```json
{"self":[{"title":"我是谁","body":"..."}],
 "other":[{"title":"我眼中的他","body":"..."}, ...]}
```

前端按两块渲染，每块里是一串小节，不再把整篇 markdown 平铺。

### 自我认知已退场

```text
面板                不再渲染「自我认知」卡片和字数
reflect.py          不再写 /persona/self，改写成 diary.changes / open_questions
数据                数据库里 self_model 还在（225 字）
                    其中「最近的变化」两条已迁进 2026-11-12 的日记 changes
                    「我学到的」「还没想清」留在原处，未删
```

要不要彻底清空 `self_model`，等确认那几条「我学到的」是否还需要。

## 17. 人格瘦身与归类规则（2026-11-12）

核心设定 1358 → 1078 字，条目 31 → 25。

### 归类规则（以后写人格按这个判）

```text
我是谁      身份、底色。写「我是/我不是什么」，一条只放一件事
表现        怎么说 + 怎么做。所有「做法」都归这里：
            口吻、长度、表情包、认错、记东西的规矩
偏好        她自己的喜欢。不和「我是谁」重复
价值取向    信什么。写判断，不写流程——
            「不知道不丢人，装懂才丢人」是取向，
            「不确定就先查」是做法，归表现
弱点        会栽在哪。写失败模式，不写改正办法
我们怎么对彼此  只放关系站位和约定。
                  不放回应技巧（归表现），不放他的偏好（归画像）
我们之间有什么  构成性的，带 important 标记和 【L3:id】
```

### 这次改了什么

```text
价值取向        7 → 3，只留真判断
                 删掉的：先查 / 看错先认 / 预判过头 / 分清谁说的 / 别照搬标签
                 前四条并进「表现」，最后一条原本就与弱点重复

我们怎么对彼此  6 → 2
                 「先听别急着给方案」→ 表现
                 「要软的」「不喜欢硬夸」「倾诉先问怎么了」→ 画像 他的偏好
                 「群友的话不当主人说的」「不编他來路」→ 表现

偏好            1 → 3（原来那条还和「我是谁」重复）
                 新增依据：她刷过的科普、AI 工具实测、军事冷知识，
                 以及匕首那条里她自己说的「肯回头拆自己才难得」

我是谁          4 → 3，合并「不当客服」和「不装可爱」

画像            重排
                 「说话短结论先说」留在「他什么样子」
                 「不必每次贴来源」移进「他的偏好」
                 两条真判断移进「他的价值取向」
                 「先被问怎么了 / 要软的 / 不喜欢硬夸」从核心挪进「他的偏好」
```

### 备份

```text
persona-roles/state/constitution-before-slim-20261112-021829.md
```

### 副作用

人格变了，bridge 的人格指纹会不一致，下一条 QQ 消息进来时会自动换新会话。
这是设计好的行为，不是故障。

## 18. 关系状态并进中间层（2026-11-12）

### 改动

```text
diary 加一列 relationship      「最近我们是什么样子」
关系复盘不再写 relationship_state，改成写当天那一行
store.get_relationship()       读最近一条非空的 relationship
                               上游调用方（bridge / 面板）一行没改
小本子                         每天那行会多显示「那天的关系」
面板「我和他」                 那一节显示最近一条，带日期
```

### 为什么这么改

```text
以前 relationship_state 只有一行，每天覆盖
并进日记后，每天的关系状态留一条历史
昨天什么样、今天什么样，都看得见
```

### 代价

```text
evidence_ids 没了
  旧表那列没有任何地方读，接受这个损失
relationship_state 表留着不写
  get_relationship 在日记还没写时会退回老表，兼容期用
```

### 迁移

旧的 85 字摘要已写进 2026-11-12 那行的 relationship。

### 边界还是分开的

```text
人格 我们怎么对彼此    长期约定，很少改（改了会换会话）
日记 relationship      每天的状态，天天变，不进人格
```

### 自我认知彻底退场（2026-11-12）

```text
self_model 内容     清空（原 225 字备份在 persona-roles/state/self-model-before-clear-*.md）
「工具坏了直接说」   并进「表现」
「不确定先查」       本来就已经在「表现」里（不懂的会自己查资料…）
POST /persona/self  路由和处理函数删除，现在 404
插件 client.mjs     setSelfModel 删除；app.mjs 里那段注释删掉
```

现在没有任何入口能写自我认知。`memory` 层的 store 方法 `set_self_model`
还留着（测试在用），但没有调用方。

### 新字段的输入输出补全（2026-11-12）

审计结果：大部分字段两端都通了，两处漏的已补。

```text
ask_him      只有写没有读
             → 新增 GET /ask-him（近 7 天、最多 2 条）
             → bridge 私聊时拼进 payload：
                （你自己留着没问的一句：xxx）
             加轻标记是防止它被当成主人说过的话

diary.tasks  只有面板显示，没有任何地方写
             → 整个字段删掉（任务本来就在 tasks 表里，面板另有一块）
             → schema / memory_core / 服务接口 / 前端 / 数据库列全部移除
```

其余字段两端都通：

```text
情绪三列    抽取写 → /emotion、/state、面板、日记读
want_more   抽取写 → B站 选材优先取
want_used   选材用掉时标 → 选材时过滤
insight_target  L3 写 → 关系复盘、B站 感悟、面板读
changes / open_questions  reflect 写 → 人格复盘、reflect 自己读
relationship      关系复盘写 → 面板、主动说、复盘输入读
```

### ask_him 还留一个隐患

现在每轮都会带最近 2 条，可能连续几轮重复同一句。
要彻底解决得加一个 ask_used 标记（像 want_used 那样用一次就划掉），
但那样她没问出口就作废了。先观察。

## 19. 维护周期总表（2026-11-12）

| 任务 | 周期 | 写什么 | 碰人格吗 |
| --- | --- | --- | --- |
| 日记 growth_diary | 每天 23:00 | diary.text | 否 |
| reflect | 活跃时段 ≥8h | diary.changes / open_questions | 否 |
| 关系复盘 | 每天 07:00 | diary.relationship | 否 |
| 画像刷新 | 每 2 天 | user_profile（画像，不进人格） | 否（但会换人格指纹） |
| 风格复盘 | 每 3 天 | 人格「表现」节 | 是 |
| L4 核心挑选 | 每 3 天 | 从 closed L3 挑 0–2 条重写成 L4 | 否 |
| 人格复盘 review | 每 30 天 | 产出四类提案，面板确认后改人格 | 是（确认时） |
| L2 复查 | 每天 07:00 | confirm→升 L1 / reject / keep | 否 |
| L3 生命周期 | 批处理附带 | open/closed/dormant 状态 | 否 |

### 读依赖

```text
reflect    读：人格 + 最近对话 + L1/L3/L0 + B站感悟 + 最近 7 天日记
review     读：核心设定 + 画像 + 最近对话 + 长期证据 + 日记 + 上次候选
画像刷新   读：人格 + 最近对话 + 长期记忆
风格复盘   读：人格 + 最近对话 + 长期记忆 + B站感悟
```

### 分层原则

```text
快（每天）    只写中间层，不碰人格
中（2-3 天）  改画像 / 人格「表现」
慢（30 天）   review 出提案，人确认才落
```

### 反映到实现的一个修正

reflect 的标题句还写着「写我对我自己的理解」（自我认知时代残留），
已改成「你在写最近的日记：这两天你有什么变化、有什么还没想清」。

### reflect 输入优化（已定未做）

实测：reflect 现在的输入把最近三天读三遍（L0 50 + L1 50 + L3 30），
同日 L1/L3 内容相似度抽查 465 对里 12 对 >0.6，且 L1/L3 时间跨度完全重叠。

已定方案：按时间划分，L0 撤掉。

```text
今天（0-24h）   L1 新产生的
前 2-7 天       L3
最近 2 天日记    变化的轨迹（只给 2 天，给 7 天会引导复述旧变化）
B站感悟          保留（90 天跨度，不重叠）
```

L0 不给的理由：reflect 写「发生了什么、我的反应」，L1 已经装了；
L0 的价值是溯源原话，那是 review（判断人格条目正不成立）的事。
画像刷新也从不喂 L0，产出照样能用。

预计省约 6000 token / 次（当前约 1.9 万）。

等树树说改再动手。

## 20. 感悟并进 L3 正文（2026-11-12）

### 改了什么

```text
L3 正文    = 事件叙述 + 最后一句感悟
insight_target  保留（me / us / none），只做筛选标签
insight_text    删除
insight_history 删除（27 条历史数据本来就没消费者）
```

数据：43 条有感悟的 L3 已把感悟并到正文末尾，备份在
`memories.db.bak-insight-merge-20261112-194954`。

### 为什么这么改

感悟本来就是从同一段经历里得出的，单独存一列等于把一段经历拆成两个字段。
合并后：
- 一个文本字段承载全部内容，模型读到的是一条完整的经历
- 一个标签字段管分类，复盘按 me/us 筛，效果和以前一样
- 少一次重复输入：reflect 原来要单独查一遍感悟再拼一块

### 提示词的关键约束

合并的风险是正文只剩结论、事件细节丢失，那样 review 就没法判断了。
所以 THREAD_SYSTEM 里写死了一条：

```text
summary 仍然是「重写后的当前状态」：保留仍成立的关键事实，
压缩已解决的，把新进展写进去；事件细节不能丢，感悟是加在后面的。
```

### 消费者改动

```text
reflect        删 bili_insights 块（感悟已在 L3 正文里）
style          同款块，本来查出来就是空
关系复盘        查询从 insight_text!='' 改成 insight_target='us'，取 text
bili_insights  查询条件从 insight_text!='' 改成 insight_target!=''
add_bili_insight  删除（无调用方）
update_thread  不再处理 insight_text / history
```

### 保留的兼容

```text
memory.insight_kind   38 条老数据的分类还在这儿，查询时兼容
                      没迁到 insight_target，因为老 L3 的 me/us 已经标过了
```

### 对话出口仍然只有 text

```text
/context        SELECT id,text,ts              ← 感悟现在就在 text 里了，
                                                  所以对话会看到它
```

这条要留意：感悟并进正文后，对话上下文里就会出现「规则透明这件事，
出了校门就再没处买了」这类结论句。之前讨论过对话不该看结论，
但合并之后结构上没法再分——除非在 text 里加分隔符区分。
先观察，看会不会出现逐句复述。

### 其他模块的适配（2026-11-12 晚）

合并 insight 后逐模块检查，改了六处：

```text
extractor L3 候选      「已有感悟」改成「已有正文」
                        原来读 insight_text，字段没了会永远显示（无）

web 面板记忆页         感悟不再单独一行
                        改成只显示分类标签「感悟类型：关于我」
                        正文里已经有那句了，再显示一遍是重复

bridge 活动日志         不再传 insight / insight_kind / insight_context
                        B站 现在只走 L0，活动日志不需要这些

memory_core log_activity  签名去掉 insight / insight_kind
                            INSERT 同步调整

server /activity       不再接收 insight 字段

activity_log 历史数据   15 条 insight 全部已在对应 L3 正文里，
                        清空避免两处重复
```

### 关于对话会不会看到感悟

合并之后对话出口（`/context`）只返回 `text`，而感悟就在 `text` 里，
所以对话会看到它。评估结论：**不是问题**。

理由：它现在只是「对某件往事的回忆」的一部分，没有独立标签把它标成
「这是你的结论」。之前担心的诱导来自「感悟：」这种显式标签。
先观察，若出现逐句复述再处理。

## 21. 状态注入与词库清理（2026-11-12 晚）

### 删掉的两节

```text
心情
  只输出 state.mood（happy/tired/annoyed/bored/normal），长期是「平常」
  情绪本身已随 L1 走，这一节是空壳 → 删

B站见闻
  读 state.browsed（旧 browsed 表，6 条），作用是给可分享的链接
  但 L0 里没有 URL → 不能直接删
  改法：round.py 写 L0 时把 BV 链接带进去，然后删这一节
```

### 词库三份合一

核查发现：

```text
lexicon.json        18 条，权威源（含 scope=group:1132633236 的 10 条）
slang 表            0 条（已退役）
network-memes.json  0 条（空的）
group-slang/*.json  1 个群的旧副本，内容已被 lexicon 覆盖
```

处理：

```text
/state 的 slang_learned   原来读 store.slang_list()（表空，永远 []）
                          改成直接读 lexicon.json，现在返回 6 条
network-memes.json        0 条 → 移走备份
group-slang/              已被 lexicon 覆盖 → 移走备份
群黑话游标                从 group-slang/state.json 改到
                          persona-roles/state/group-slang-state.json
                          （避免和那儿已有的 state.json 撞名）
```

### 效果

```text
state.mjs 的「你会跟着主人说的词」 现在真的有内容了
                            以前一直不触发，因为数据源是空表
```

### 备份

```text
network-memes.json.bak-20261112-201618
group-slang.bak-20261112-201618
```

### 词表注入删除（2026-11-12 深夜）

删掉 state.mjs 第 6.5 节的两段：

```text
「你会跟着主人说的词」      和 bridge 的消息匹配注入重叠，
                            而且是整份清单，容易诱发「为了用而用」
「这些词主人说了好几次还没懂」 数据源是 slang 表，表 0 条，
                            从来没触发过，以后也不会
```

删完后词库的完整闭环：

```text
写     bridge 每天 7 点 lexicon_review_loop（从 L0 抽词）
       learn_word 工具（她主动学）
读     bridge 每条消息匹配，命中才注入「群里常用说法：X→Y」
       lexicon_search 工具（她主动查）
看     面板 /api/lexicon、/api/groupslang
```

整份词表注入不在这个闭环里的任何一环，删了无损失。

### 顺带统一的

```text
/state          不再返回 slang / slang_learned / slang_pending
/state 的 slang_learned  改读 lexicon.json（原来是空表）
面板 groupslang_payload   改读 lexicon（原来读 /slang 接口的空表）
```

### 关于 slang_pending 和 ask_him 的关系

它们不是重复：

```text
ask_him        她当下想问的一句，从具体对话里长出来的
slang_pending  按词频统计推出来的「见了 6 次还没懂」
```

前者是内容，后者是统计。删它的真实原因是**数据源一直是空的**，
不是和 ask_him 重复。以后真要做词频统计，这是另一条线。
