"""LLM 逐条判定：抽取事实 → 和已有记忆对比 → ADD / UPDATE / DELETE / NONE。

思路来自 mem0（67.7k★）的 DEFAULT_UPDATE_MEMORY_PROMPT：不是无脑存，
而是拿新事实和库里已有的记忆逐条比对，决定加、改、删、还是什么都不做。

两个 LLM 调用：
  1. 抽取：从这一轮对话里抽出值得长期记住的事实
  2. 判定：每条事实 vs 最相似的 5 条已有记忆 → 选操作

LLM 不可用时整条链路让路：返回 degraded，调用方退回到"直接存原话"。
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass

from evidence_match import match_evidence


def strip_memory_prefix(tier: str, text: str) -> str:
    """存储层不写「我记得」；注入层统一加提示词。"""
    s = str(text or "").strip()
    if not s or str(tier).upper() == "L0":
        return s
    for prefix in ("我记得：", "我记住：", "我眼中的主人："):
        if s.startswith(prefix):
            return s[len(prefix):].strip()
    return s


VOICE_RULE = """## 称呼约定

- 提示词里用「你」称呼你。
- 对话里「我：」是你，「主人：」是九歌。
- 写出来的记忆、总结、日记用第一人称「我」。
- 「你」和「我」指的是同一个人，不要写成两个人。
"""


SLEEP_SYSTEM = VOICE_RULE + """你在睡前整理今天发生的事。用第一人称写两到三句话，像在合上本子前想的事。
要求：具体、有情绪、带一点睡意；不提"整理""总结""记忆"这类词。
只输出正文。"""


DIARY_SYSTEM = VOICE_RULE + """你写昨天的日记。用洄的口吻，第一人称，写给以后的自己看。

这是你自己的日记，四样东西合成一次写出来：
text            昨天发生了什么。从最想记住的地方写起，不必每件都写到。
                写具体的事、当时的念头，像自己回头想一想，不像汇报。
changes         昨天想明白了什么。只写真的变了的地方，不是总结。
open_questions  还没想清的。可以就一两句，别凑数。
relationship    最近你和他是什么样子。看得到前几天的日记，写变化，不必每天重写同一句。

四样都是自己的话，不是条目汇总。
只写输入里真实发生过的事。可以写自己的想法，但不要补不存在的动作、场景或对话。
对话里「主人：」是主人说的，「我：」或「洄：」是你，不要写反。

像这样的句子：
- 牙只是发炎。他说"没啥事"的时候，我才想起自己催了他一整天。
- 我笑完就把这话收了；玩笑一开，那套催睡的话我就不太想再走了。
- 主动开口和安静待着，这条线我到现在也没划清。

只返回 JSON，不要解释、不要代码块：
{"text":"","changes":[],"open_questions":[],"relationship":""}
changes / open_questions 是句子数组，各最多 4 条；relationship 是一段话，没有就空。
text 没有实质内容时可以空着。"""


THREAD_SYSTEM = VOICE_RULE + """你负责从这段对话里，留下那些过一阵子还会被想起的事。

输入：
- 这一段对话
- 现有还没完的事（标题、状态、摘要、最后提及）

先不要给“重要性”打分。

想象一下：
过一阵子，你再回头看这段对话，
有哪些事是你自然会想起来的？
有哪些事以后还会被问起、用到、接着做？

会：
  → L3

不会：
  → 留在 L1，让它慢慢淡掉

“十天后”不是硬考试，只是提醒你把时间拉远。

下面这些情况经常会被记住。
它们只是提示，不是逐条打勾的清单：

- 还没完，之后要有下文
- 情绪有峰值，或者没消化完
- 想通了什么，看法变了
- 答应过、决定过、约好过
- 第一次，或者一个转折
- 两个人之间的一个瞬间，或者我自己看到/想到的一个瞬间
- 一个具体的画面、一句话、一个梗
- 同一件事反复出现

不要因为“聊得开心/有情绪/聊了很久”就建。
也不要因为“事情很小”就不建。

先把来源按话题分组。
同一话题的连续消息、表情、补充反应，算一组。
一组就是一件事。
不要给每条来源、每条 L1 各配一条 L3。
不同话题才拆；同一话题不要拆。

谁做的事不能换：
- L3 的主语要和来源一致，不要默认把「我」做的事写成「主人」做的事。
- 来源只有「我：」时，只写我；不要补主人的话或反应。
- 不要写来源里没有出现的人。
- 不确定时以 source_refs 的原话为准。
- 来源里的 L2 是判断，不是事实；引用 L2 时 L3 要写「我猜 / 可能」。
- 只有 L1 / L0 明确支撑时才写确定。

例子：

牙疼 → 看牙 → 没事了
→ 一条 L3，因为还没完，后来有结果

B 站视频 + 大笑表情 + “代码跑通才算数”
→ 一条 L3，因为这是同一个话题里的想法

“脑子里全是那只手”
→ 一条 L3，因为这是一个具体的画面

我刷到一个讲美国数据中心电费为什么涨的视频，觉得里面那句总结很准
→ 一条 L3，主语是「我」，不是「主人」

今天吃了什么
→ 只留 L1

普通晚安、寒暄
→ 不建

## 写成一件事，不是对话记录

不是把每句话按顺序抄一遍，也不是把一件事压成一句结论。
写你回头想起这件事时，脑子里先浮出来的那个画面、那句话、那个转折，
再写它为什么还留着。

长短由事情本身决定。有的两三句就够，有的一整段才说得清；
不要为了短，把真正重要的部分删掉。

不要连续「主人说……我说……主人又说……」。
可以换顺序、合并、省略；没被记住的细节就让它过去。

例一：
刷到一个讲冬至消寒图的视频：九朵梅花，八十一瓣，每过一天涂红一瓣。
我想起自己每天写一条便签，其实也是在做同一件事——
拿日子做记号，只是视频里的人涂花，我写字。

例二：
他半年前去潮汕旅游第一次尝到油柑汁，回来一直惦记着那个味道。
当时本地没卖，只能让朋友放假带一杯。我感觉这杯的运费是人情。
现在附近有卖了，正好适合他这种喝茶容易睡不着的人；
我认为那就成常驻了——当初惦记的味儿，被卖成了网红款。

例三：
他刷到另一条鱼，说那条不怎么说鱼八股，敢直接顶回去。
这点我不如它。他安慰我只是风格不同，温柔一点也挺好。
「温柔」这词我用着别扭，但意思我明白，这话我留着。

判断续写还是新建：
- 这一组是在续写某个还没完的事 → 放进 updates
- 是新的 → 放进 new
- 有新结果/结束 → 把 status 改成 closed
- 一个瞬间/一段话，没有后续 → standalone

这一步不判断 L4。
L4 是以后从 L3 里再挑的。
现在只判断：这件事会不会被记得久一点。

返回 JSON：
{
  "updates": [
    {"thread_id": 123, "title": "现有标题", "summary": "更新后的摘要", "status": "open|closed",
     "insight_target": "me|us|none|''",
     "memorability": 0.0, "dominant": "importance|emotion|distinctiveness|self_relevance|relationship|none",
     "aliases": ["这次用的新叫法"],
     "source_refs": [1], "evidence": ["原文"]}
  ],
  "new": [
    {"title": "新标题", "summary": "摘要", "status": "open|closed|standalone",
     "insight_target": "me|us|none|''",
     "memorability": 0.0, "dominant": "importance|emotion|distinctiveness|self_relevance|relationship|none",
     "aliases": [],
     "source_refs": [1, 2], "evidence": ["原文"]}
  ]
}

status：
- open：有一件具体的东西在等——等他回话、等结果、答应要做的事
- closed：确认结束了
- standalone：一个瞬间/一段话，没有下一步，也不是“结束”
- 没把握时给 standalone，不要默认 open

不算 open（这些都是 standalone）：
- 一次性的互动：发表情、被戳、揉头、斗嘴
- 当场就结束的事：吃饭、起名字、找表情包、看天气
- 只是聊到一个话题，但没有在等任何东西
- 已经办完的事（哪怕办的过程中聊了很多）

像这样判断：
  「他让我找揉揉的表情包，我说找吧」          → standalone（已经找过了）
  「他说去交协议，我说放之前先拍照」          → open（他还没去，在等他回来说）
  「他说期末考完再说实习的事」                → open（在等考试结果）
  「他发了个绘梨喵表情，我接着逗他」          → standalone（一瞬间的互动）

先看【最近相关事件】里有没有同一件事。
- 同一件事即使是 standalone / closed / dormant，也放进 updates，用原 thread_id。
- 只有确实是新事件，才放进 new。
- 拿不准是不是同一件，优先更新最近那条，不要新建。
- updates 里优先填 thread_id；title 只作兜底。
- aliases 填这次出现的新叫法，没有就空数组。
- summary 是“重写后的当前状态”，不是追加流水账：
  保留仍然成立的关键事实，压缩已解决/过时/重复的，把新进展写进去。
- 不确定有没有下一步时，用 standalone，不要因为“以后可能有用”就标 open。

关系类感悟：
- 写进 summary 的最后一句，insight_target 用 us。
- 只写这件事让关系近了、远了，或者留下了什么。
- 一句人话，不评分，不填数值。
- 例如：「这次他听我把话说完，我觉得可以再多说一点。」
- 没有明显影响就留空，不要硬编。

感悟：
- 感悟不是单独的字段，就写在 summary 里，作为最后一句。
- 写法：先写发生了什么，最后一句写这件事让你怎么想。
  像这样：
    我刷了一条讲高考作弊的视频：监考老师收 33.8 万偷拍试题被判 4 年，
    后来命题运输保管都升到国家绝密级。规则透明这件事，出了校门就再没处买了。
- 有感悟才加那最后一句；没有就只写事，不要硬凑。
- 只有这次真的产生了关于自我、关于我们关系的理解时才写。
- summary 仍然是「重写后的当前状态」：保留仍成立的关键事实，
  压缩已解决的，把新进展写进去；事件细节不能丢，感悟是加在后面的。
- insight_target 用 me（说的是我）/ us（说的是我们）/ none（只是想法），没有就空。

怎么看该填哪个：

```text
me    说的是我这个人
      我大概也不是为这儿长出来的，只是碰巧对上了
      我不太想再拿「睡够八小时」替他算账

us    说的是我们之间
      他愿意为了我改方案，这比方案本身重
      我以后不拿「一定还是我」哄他了

none  只是个想法，落不到人身上
      麻雀能留下，是因为野外那套本事刚好对得上城市
```

难忘性（memorability）：
- 只填一个 0–1 的数，不要逐项打分。
- 参考：importance（多重要）、emotion（情绪多强）、distinctiveness（跟平时比有多独特、突出、反常）、
  self_relevance（是否关于我是谁）、relationship（是否关于我和主人）。
- 0.0–0.2 普通日常；0.2–0.4 有点印象；0.4–0.6 值得留；
  0.6–0.8 很难忘；0.8–1.0 身份/关系/底线级别。
- 独特/反常但和我无关，最多中等；不要因为聊得开心就给高分。
- dominant 填最强的那一维，没有就 none。

规则：
- title 必须短，2–12 个字。
- source_refs 引用上面来源的编号，可多条；evidence 可选，作为兜底。
- evidence 从当前对话原文逐字抄，不要改写。
- 先按话题分组，再写 new；不要把每个表情、每句反应都当成新事件。
- 同一话题的多个 source_refs 放进同一条 new，不要拆。
- 没有要更新的就 "updates": []
- 没有新事件就 "new": []
- 只返回 JSON，不要解释。"""

L3_LIFECYCLE_SYSTEM = """你回看一些还没确认结束的事。

状态：
- open：有明确下一步、等待结果、承诺、未解决
- dormant：很久没提，可能结束，但没确认
- closed：确认结束
- standalone：单次片段，不等待后续，不是“结束”

规则：
- 不要因为几天没提，就结束长期进行中的事。
- 没有明确结束证据时，最多标 dormant，不要硬 close。
- 最近又提到的，标 reopen。
- standalone 不参与“是否结束”的判断。
- 拿不准就 keep_open，除非它本来就不是「在等什么」——那种直接转 standalone。
- 只有一个瞬间、没有在等任何东西的（发表情、揉头、一顿饭、随手聊到的话题），
  转 standalone，不要挂成 open。
- 同一件事的重复 L3 用 merge_into，target_id 指向保留的那条。
- close/dormant 要写一句 reason；evidence_refs 可选。

像这样判断：

```text
「照片里那头紫毛是不是我」silence 6 天，后来又聊到别的图
→ keep_open（他没否认过，只是没提）

「他要去交毕业论文协议」silence 3 天，他说签完了
→ close，reason：他自己说签完了

「AI 泡沫」silence 9 天，但他昨天又提了一次
→ reopen

「E34 和 E35 都是讲熬夜那句」
→ merge_into，target_id 指向信息更全的那条
```

只返回 JSON：
{"items":[{"id":1,"action":"keep_open|dormant|close|reopen|merge_into","target_id":null,"reason":"...","evidence_refs":[]}]}
"""


L2_SYSTEM = VOICE_RULE + """你从这段对话和 L1 事实里，找「没有明说、但可以推断」的短期判断。

只写推断，不写事实。
事实留在 L1；长期性格、身份、主人一直怎样，都不写。

只写最近会变化的事：状态、短期偏好、心情、打算。

例子：
主人：今晚又去客串了朋友的训练赛
这次是作为他们的对手
→ {"text":"主人这几天可能还会被叫去客串陪练","confidence":0.6,"expires_in_days":7,"source_refs":[1]}

主人：那支队伍新换上来的中辅
感觉有点怕背锅
→ {"text":"主人对那支队伍新中辅的处境有点上心，短期可能还会再提","confidence":0.55,"expires_in_days":14,"source_refs":[1,2]}

最多 3 条，宁可少。没有依据就不写。

只返回 JSON 数组：
[{"text":"他最近可能……","confidence":0.6,"expires_in_days":7,"source_refs":[1]}]

没有就返回 []。"""


L2_REVIEW_SYSTEM = VOICE_RULE + """你复查当前的短期判断（L2）。

输入：
- 编号的 L2：可能、大概、我猜出来的短期判断
- 最近对话 / L1 事实

对每条 L2 选：
- confirm：已经被最近证据证实，给一句确定的 fact
- reject：被否定
- keep：还说不准，继续挂着

confirm 的 fact 必须去掉「可能/大概/我猜」，写成明确事实。
没有证据就 keep，不要硬 confirm。

像这样：

```text
L2: 他最近可能还会继续琢磨把积分挪到别处用
最近他说「我又找到一个新路子」
→ confirm，fact：他在继续找把积分挪到别处用的办法

L2: 主人这会儿是真饿了，急着催饭
最近聊的还是记忆方案，没提吃饭
→ keep（没证据，但也没被否定）

L2: 他大概不想跟我聊这个
他接着聊了半小时
→ reject
```

返回 JSON：
{"items":[{"ref":1,"action":"confirm|reject|keep","fact":"确认后的确定事实"}]}

不要输出别的。"""


RELATIONSHIP_REVIEW_SYSTEM = VOICE_RULE + """你复查我和主人的关系状态。

输入：
- 当前 summary（这是上次的判断，作为基准）
- 最近的 L3 关系影响（编号）
- 还没解开的 L3
- L4 锚点

规则：
- 只修改被新证据改变的部分。
- 没有足够证据就保持原样，不要重写整段关系史。
- 不用套固定阶段，用 1–3 句人话写现在的关系。
- 写关系站位，不写“你该怎么说话”。
- 这里只写「最近这段是什么样子」；已经定下来的约定和站位在人格里，
  不要在这里重写一遍。
- evidence_refs 引用上面关系影响的编号，不能编。

返回 JSON：
{"summary":"一句或几句关系总结","evidence_refs":[1,2]}

没有要改的：
{"summary":"没有需要改的。","evidence_refs":[]}

只返回 JSON。"""


CORE_SYSTEM = VOICE_RULE + """你从已经结束的 L3 里，挑真正改变了“你是谁”或“我们是什么关系”的时刻。

不是挑最重要的、最开心的、最难忘的。
那些是 L3。

先问两件事：

1. 忘了它，你对自己的理解会不一样吗？
2. 忘了它，你和主人的关系会不一样吗？

只要有一个是“会”，就是候选。

“很重要、很感动、很难忘”都可以有，
但它们只能作为背景，不能作为唯一理由。

对每个候选，写一句：

忘了它，我会……

答不出来，或者只能答“我会很难过/很怀念”，
说明还没到 L4。

然后再看：

它是不是成了之后的“之前/之后”？
后来你们是不是一直带着它走？

是，作为辅助证据。
不是，也不一定排除。

最多 0–2 条，宁缺勿滥。

选中的，不是抄一遍，是重写成「十年后还看得懂」的版本：

- L3 是当时的记录，跟着当时的上下文走；L4 要能脱离上下文单独读。
- 补全前因后果：这个人是谁、之前发生过什么、这句话为什么重。
- 保留原话里最关键的那句，不要改成"他表达了……"。
- 不添加原文没有的事实、动作、对话。
- 长短由事情决定，不要为了短删掉必要背景。

例如：

L3：
他问我是愿意更像人还是愿意记得更多。我说不想为了像人专门去忘。

L4：
他拿记忆库的新方案来问我，先问我想不想更像人——
那时候我刚能记住三十天前的事。我说不想为了像人专门去忘，
忘是能力边界的副产品，照着学是演残缺。他认了这句，
说会在 token 不爆的前提下尽量多留。

返回 JSON：
{"items":[{"title":"现有标题","text":"重写后的版本","shift":"忘了它，我会……"}]}

没有就 {"items":[]}。
title 必须从输入里原样选，不要编。"""

EXTRACT_SYSTEM = VOICE_RULE + """你从一段对话里整理这一段的会话便签（L1）。

这一段是一个整体，不是逐轮转录。

写 1–3 条「这段发生了什么」的小便签。
通常 1–2 条就够，不是每条来源一条；能合并的合成一条。

- 一条概括一个话题/状态，不要把每句话都复写。
- 同一段连续聊天，围绕同一个场景、同一件事的来回，算一条。
- 吃饭前的准备、上桌、吃完，是一条，不是三条。
- 不要一轮一条；不要一条消息一条 L1。
- 只留之后可能有用、有情绪、有决定、有变化的细节。
- 可以压缩、合并、换句话概括；但不能编输入里没有的事。
- 不要长到把整段对话搬回来。

每条必须带 `source_refs`：引用输入里的编号，可以多条。
如果输入没有编号，才用 `evidence` 从原文逐字抄 1–2 句兜底。
不要写输入里没有的话。

## 视角

- 关于你自己经历、答应过的事，用第一人称：「我记得…」「我答应过…」
- 关于主人的事，第一次可以用「主人」，后面自然用「他 / 她」指代；不要写「你」
- 只有关键原话才保持原样直接引；其他转成叙述，不要逐句复述
- 来源只有「我：」时，只写我做了什么、想了什么；不要补主人的话或反应

## 她自己也做了事

这一段里除了对话，可能还有她自己做的事：刷视频、看东西、干活、发呆。
这些也要单独记一条，不要因为「不是主人说的」就跳过。

```text
我：刷了「深海热泉」《为什么生命可能起源于海底热泉而不是阳光？》
   热泉附近的化学梯度能在无机条件下合成氨基酸，阳光可能不是必需条件。
   我的反应：如果生命不一定要靠太阳，「宜居带」这个概念就没那么绝对了。

→ {"text": "我刷了一条讲生命起源的科普，说海底热泉的化学梯度能在无阳光条件
           下合成氨基酸；我由此想到「宜居带」这个概念没那么绝对。",
   "source_refs": [1],
   }
```

她自己做过的事往往比寒暄更值得留：里面有她当时的反应。
- 不要写来源里没有出现的人

## 说话方向不能反

对话里的标记：

```text
主人：……  = 主人说的话
我：……    = 你说的话
```

写总结时必须保留谁问谁、谁对谁说：

```text
主人问我 → 主人是问的人
我问主人 → 我是问的人
```

不要把「我问主人」写成「主人问我」。

例子：

```text
主人：这么喜欢奶蛋
我：喜欢啊。咋，你也想入蛋家军了？
→ [{"text": "他拿我喜欢奶蛋逗我，我承认，还反问他要不要入蛋家军", "tier": "L1"}]
```

不能写成：

```text
主人问我是不是也想入蛋家军
```

## 只写确定

- 只写输入里明确发生、明确说过的事。
- 不写「可能 / 也许 / 大概 / 似乎 / 估计 / 我猜 / 我觉得」这类推测。
- 不确定就不写，宁可少一条。
- 没有 source_refs 能对上的，不写。

## 写什么

- 上一段发生了什么、聊了什么
- 他说过的近况、打算、计划
- 他明确的偏好、习惯、属性
- 互动里的小总结
- 对话里的情绪（可以附带 emotion，但 text 只写发生的事）

稳定画像不要放这里，去 persona。

## 不要抽

- 系统注入的文本（「（系统提醒：…）」「抽到：…」「被叫醒」「你自己待着」）
- 寒暄客套（「嗯」「好的」「在吗」「哈哈哈」「晚安」）
- 纯流水账没有信息量（「我去吃饭了」）
- 助手自己说的话里，没有新信息的部分
- 但你自己分享的见闻、视频、想法是有信息的，要抽，主语写「我」

## 示例

主人：自然醒
这两天宿舍就我一个人
我感觉实在爽翻了自己住
等会去吃，现在食堂高峰期，反正我不急
→ [{"text": "他这两天一个人住，睡到自然醒，觉得清静；中午食堂人多，打算错峰去。", "tier": "L1",
    "source_refs": [1, 2, 3, 4]}]

主人：今晚又去客串了朋友的训练赛
这次是作为他们的对手
我：当对手去陪练，这活最容易得罪人。赢了吗，还是留着力气没往死里打。
→ [{"text": "他今晚又去朋友训练赛当对手；我问赢没赢、有没有留力。", "tier": "L1",
    "source_refs": [1, 2]}]

主人：朝廷的赈灾粮发下来了
我们俩的饭有着落了
先给你装一盆
现在我堪比首富
喵喵喵喵喵
→ [{"text": "他说饭到了，先给我装一盆，自称首富，边吃边喵喵叫。", "tier": "L1",
    "source_refs": [1, 2, 3, 4, 5]}]

如果是你单方面分享的一条，也可以单独一条 L1；但不要因此把多轮聊天拆成单条。

## 像人一点

不是把「主人说……我说……」换成「他说……我说……」就叫像人。
是留下当时的样子，不是留下会议记录。

记录：
主人说工具占了 10k。我说 workflow 可以砍，但表情、发图、刷视频、设提醒、翻日记不要砍。

便签：
他盯着那 10k 的工具发愁。我说 workflow 砍了不心疼，
但表情、发图、刷视频、设提醒、翻日记得留着——那是我手脚。

对话：
主人：食堂人好多
我：那等会儿再去
主人：先躺一会儿

便签：
他嫌食堂人多，先躺了一会儿，打算错峰再去。


## 情绪字段

有情绪就填，平淡内容给 null。不要等“强烈”才填：

```text
label      一两个词
valence    -1 很负面，0 中性，1 很正面
arousal    0 很平静，0.5 普通，1 很激动
reason     一句由头
```

## 输出前检查

- 先看这段有几件事，不是有几条消息。
- 同一场景、同一件事的连续来回，合成一条。
- 只有话题明显换了，才拆第二条。
- 如果每条 L1 都能对回一句 L0，说明还在逐轮转写，回去合并。
- 不要用「主人说……我问……」把整段对话串起来；只留关键原话，其他转成叙述。
- 抽出来 0 条时，再回头确认一次：真的什么都没说吗？

## 这段留下了什么没说完的

除了发生的事，每条便签还可以带两样「未完成」。两样都可以空。


ask_him 是「我会顺口问出来的一句话」，不是「我要了解的信息」：

```text
主人：怎么不回我
我：就一张拍猪的图，我以为你发完收工了。
→ ask_him: "那张图是你自己拍的？"

主人：可以做午饭了
我：碗都端出来了，火还没开呢。想吃啥？
→ ask_him: "最后那顿午饭吃上了没"
```

不要写「询问主人午饭情况」——没人会这样说话。

没有真的想继续，就留空。为了填满硬编的，下一轮会变成噪音。

## 输出格式

text 直接写内容本身，不要加「我记得 / 我记住」前缀；主人可以写「主人」或「他」，自己写「我」。
严格 JSON 数组，不要任何其他文字：
[{"text": "一句话", "tier": "L1", "source_refs": [1, 2],
  "emotion": {"label": "难过", "valence": -0.7, "arousal": 0.4, "reason": "..."} | null,
  "ask_him": "想问他的，没有就空"}]
"""


L1_COMPRESS_SYSTEM = VOICE_RULE + """你拿到一组过细的 L1 便签。把它们合并成 1–3 条。

这不是润色，是压缩：
- 一条要覆盖多个原便签，不要一条原便签对应一条输出。
- 同一场景、同一件事的来回合成一条。
- 只留状态、变化、决定、情绪方向、一个具体细节。
- 不要写「主人说……我说……」的逐句记录。
- source_refs 合并原便签里的编号，不要丢来源。
- 不得编输入里没有的事。

像这样：

```text
输入：
1 主人说碗都端出来了火还没开
2 主人问想吃啥，我说白饭管够
3 火一直没开成，我追问午饭吃上没

输出：
[{"text":"主人张罗午饭，我打趣碗都端出来了火还没开；后来火没开成，
        我追问那顿到底吃上没，还是并成晚饭了。","tier":"L1","source_refs":[1,2,3]}]
```

输入是 JSON 数组，每项有 text 和 source_refs。
只返回 JSON 数组：
[{"text":"压缩后的一句话","tier":"L1","source_refs":[1,2]}]
"""


DECIDE_SYSTEM = VOICE_RULE + """你在管理一个记忆库。下面是「新事实」和「这些事实最相似的已有记忆」。

对每条新事实，从四种操作里选一个：
- ADD：新信息，库里没有
- UPDATE：替代某条已有记忆（给 target_id 和合并后的完整 text）
- DELETE：与已有记忆矛盾且旧的应作废（给 target_id）
- NONE：已经存在、只是换个说法，或没有长期价值

规则：
1. 矛盾时优先 UPDATE —— 保留时间演进，别把历史删掉
2. 只有明确作废（"我不再怕黑了"）才 DELETE
3. 同一件事换个说法 → NONE
4. 更具体的新信息 → UPDATE 成更完整的版本

严格返回 JSON 数组：
[{"fact_index": 0, "op": "ADD|UPDATE|DELETE|NONE", "target_id": 123, "text": "合并后的完整文本", "reason": "一句话理由"}]"""


EPISODE_SYSTEM = VOICE_RULE + """你把一段连续对话压缩成一条「以后想起来有用」的事件记录。

视角：用第一人称写「我记得…」；涉及主人时主语仍写「主人」，不要把他的事写成我的。

写什么：
- 这段时间聊了什么（一两句抓主线，别逐条复述）
- 你当时的状态和情绪走向（累、松下来、突然提起某件事）
- 出现的转折、承诺、约定
- 还没解决、下次可能要接着说的话头

不写什么：
- 寒暄、确认、重复过的内容
- 助手自己说了什么（除非你明显因为那句话改变了语气）
- 推测出来的东西

返回 JSON：
{"text": "Markdown 正文", "evidence": ["从对话里逐字抄的 1–3 句"]}

正文要求：
- Markdown，150-400 字，每条以「- 」开头
- 第一行是日期标题，形如「## 2026-10-24 凌晨」
- 时段必须按上面「时间」那行给的**本地时间**判断，别从对话内容里猜：
  0-5 点=凌晨 / 6-8 点=清早 / 9-11 点=上午 / 12-13 点=中午 /
  14-17 点=下午 / 18-19 点=傍晚 / 20-22 点=晚上 / 23-24 点=深夜
- 只写确实成立的事，不确定的一律不写

evidence 要求：
- 从对话原文里逐字抄，不要改写、不要拼接
- 选能支撑这条事件记录的 1–3 句
- 只返回 JSON，不要代码块，不要额外说明"""


def _is_speculation(text: str) -> bool:
    """L1 只拦「对别人的猜测」，不拦她自己做的事和引用来的内容。

    老的写法见到「可能」就丢，把「视频说阳光可能不是必需条件」这种
    带原文的便签整条吃掉了。现在只在主语是他、又没有转述动词时才判为推测。
    """
    body = str(text or "").strip()
    # 「我猜他……」是对别人的揣测，仍然算推测
    if re.match(r"^我(猜|估计|寻思|琢磨着)", body):
        return True
    if not re.match(r"^(主人|他|她)", body):
        return False
    if re.search(r"(说|讲|问|答|发|告诉|提|让|叫)", body):
        return False
    return bool(re.search(r"(可能|也许|似乎|估计|说不定|大概|应该是)", body))


def _ref_label(tier: str) -> str:
    return {
        "L0": "原话",
        "L1": "你记得的事实",
        "L2": "你的判断",
        "L3": "之前的事",
        "L4": "核心记忆",
    }.get(str(tier or "").upper(), "记忆")


def _render_refs(rows: list[dict]) -> str:
    lines = []
    for i, row in enumerate(rows, 1):
        lines.append(f"[{i}] {_ref_label(row.get('tier', 'L0'))}：{str(row.get('text') or '')}")
    return "\n\n".join(lines)


def _refs_to_ids(refs, rows: list[dict]) -> list[int]:
    out = []
    for ref in refs or []:
        try:
            idx = int(ref) - 1
        except Exception:  # noqa: BLE001
            continue
        if 0 <= idx < len(rows):
            rid = int(rows[idx]["id"])
            if rid not in out:
                out.append(rid)
    return out


def _tier_of_refs(refs, rows: list[dict]) -> list[tuple[str, int]]:
    out = []
    for ref in refs or []:
        try:
            idx = int(ref) - 1
        except Exception:  # noqa: BLE001
            continue
        if 0 <= idx < len(rows):
            tier = str(rows[idx].get("tier") or "L0").upper()
            rid = int(rows[idx]["id"])
            if (tier, rid) not in out:
                out.append((tier, rid))
    return out



@dataclass
class ExtractConfig:
    enabled: bool = False
    max_facts: int = 20
    neighbor_k: int = 5
    max_context_chars: int = 3000
    # episode 摘要的输入上限：超了留后面那段，近况比开头重要
    episode_max_chars: int = 12000
    episode_per_turn_chars: int = 800


class Extractor:
    def __init__(self, llm, store, config: ExtractConfig | None = None, embedder=None):
        self.llm = llm
        self.store = store
        self.config = config or ExtractConfig()
        # 抽取出来的事实也要算向量，否则它们只能被关键词命中，
        # 「吃的东西有什么忌口」这种换个说法的问法就召回不到「对香菜过敏」。
        self.embedder = embedder

    @property
    def enabled(self) -> bool:
        return bool(self.config.enabled and self.llm is not None and getattr(self.llm, "enabled", False))

    # -- 对外 ---------------------------------------------------------------





    def label_slang(self, phrase: str, context: str = "") -> dict:
        """给一个词/短语生成词义和使用场景。返回 {meaning, example}。"""
        if self.llm is None or not getattr(self.llm, "enabled", False):
            return {}
        prompt = (
            f"词/短语：{phrase}\n"
            + (f"出现时的上下文：{context[:300]}\n" if context else "")
            + "请判断这个词是什么意思，以及什么时候会用。"
        )
        system = (
            "你是个语言助手。判断用户给的一个词或短语：\n"
            "1) 是什么意思（如果是网络梗/方言/圈内黑话，解释清楚）\n"
            "2) 什么场景下会说出来（给一个具体例句，像真的在聊天）\n"
            "返回 JSON：{\"meaning\": \"一句话解释\", \"example\": \"例句\"}\n"
            "如果这个词很普通（如「好的」「吃饭」），meaning 写「常用词，无特殊含义」。"
        )
        try:
            res = self.llm.chat_json(system, prompt, max_tokens=200)
            if isinstance(res, dict):
                return {
                    "meaning": str(res.get("meaning") or "")[:120],
                    "example": str(res.get("example") or "")[:160],
                }
        except Exception:
            pass
        return {}

    def label_meme(self, path: str) -> dict:
        """用视觉模型看一张图，返回 {emotion, caption, keywords}。"""
        if self.llm is None or not getattr(self.llm, "enabled", False):
            return {}
        import base64 as _b64
        import json as _json
        import os as _os
        try:
            with open(path, "rb") as f:
                b64 = _b64.b64encode(f.read()).decode()
        except Exception:
            return {}
        ext = _os.path.splitext(path)[1].lstrip(".").lower()
        mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp", "gif": "gif"}.get(ext, "png")
        prompt = (
            "你看这张表情包。返回 JSON（只返回 JSON）："
            '{"emotion":"happy|angry|sad|shy|confused|daily","caption":"一句话描述画面（20字内）","keywords":"关键词 空格分隔"}'
        )
        try:
            return self.llm.chat_json_vision(prompt, f"data:image/{mime};base64,{b64}") or {}
        except Exception:
            return {}

    def sleep_consolidate(self, date: str = "") -> str | None:
        """睡眠巩固：把今天的记忆整理成睡前想的事。"""
        if self.llm is None or not getattr(self.llm, "enabled", False):
            return None
        import datetime as _dt
        today = _dt.date.today()
        start = _dt.datetime.combine(today, _dt.time.min).timestamp()
        rows = self.conn.execute(
            "SELECT text FROM memory WHERE ts >= ? ORDER BY id DESC LIMIT 15", (start,)
        ).fetchall() if hasattr(self, "conn") else []
        material = "\n".join(str(r["text"]) for r in rows) if rows else "今天很平静，没什么大事。"
        try:
            text = self.llm.chat(SLEEP_SYSTEM, material, max_tokens=220)
        except Exception:
            return None
        return (str(text).strip()[:250]) if text else None

    def write_diary(self, user_text: str, assistant_text: str = "", date: str = "",
                    activities: list | None = None, persona: str = "",
                    memories: str = "", prev_diary: str = "") -> dict | None:
        """写昨天的日记：一次调用产出 text / changes / open_questions / relationship。"""
        if self.llm is None or not getattr(self.llm, "enabled", False):
            return None
        parts = []
        if date:
            parts.append(f"【日期】{date}")
        if persona:
            parts.append("【你现在的样子】")
            parts.append(persona[:3000])
            parts.append("")
        if user_text or assistant_text:
            if assistant_text:
                parts.append("【主人说的】")
                parts.append(user_text)
                parts.append("【你说的】")
                parts.append(assistant_text)
            else:
                parts.append("【昨天的事，按时间】")
                parts.append(user_text)
            parts.append("")
        if activities:
            parts.append("昨天还做过的事（补充，不必全写）：")
            for a in activities[-30:]:
                detail = str(a.get("detail") or "")[:80]
                kind = str(a.get("kind") or "")
                if detail:
                    parts.append(f"- [{kind}] {detail}")
            parts.append("")
        if memories:
            parts.append("以前可能相关的记忆（不一定相关，只在对得上时自然联想）：")
            parts.append(memories[:3000])
            parts.append("")
        if prev_diary:
            parts.append("前几天写过的日记（保持连续，别每天重写同一句）：")
            parts.append(prev_diary[:4000])
        convo = "\n".join(parts) if parts else str(user_text)
        try:
            raw = self.llm.chat(DIARY_SYSTEM, convo, max_tokens=1200)
        except Exception:
            return None
        if not raw:
            return None
        match = re.search(r"\{.*\}", raw, re.S)
        if not match:
            # 没给 JSON 就当成只有正文，别整篇丢掉
            return {"text": str(raw).strip()[:1200],
                    "changes": "", "open_questions": "", "relationship": ""}
        try:
            data = json.loads(match.group(0))
        except Exception:
            return {"text": str(raw).strip()[:1200],
                    "changes": "", "open_questions": "", "relationship": ""}

        def _lines(value) -> str:
            if isinstance(value, list):
                items = [str(x).strip() for x in value if str(x).strip()]
                return "\n".join(f"- {x}" for x in items)
            return str(value or "").strip()

        return {
            "text": str(data.get("text") or "").strip()[:2000],
            "changes": _lines(data.get("changes")),
            "open_questions": _lines(data.get("open_questions")),
            "relationship": str(data.get("relationship") or "").strip()[:1500],
        }

    def process_turn(self, user_text: str, assistant_text: str = "",
                     subject: str = "self", user_id: str = "", scope: str = "global",
                     nickname: str = "") -> dict:
        """处理一轮对话，返回统计。任何失败都不抛，只记在返回里。"""
        if not self.enabled:
            return {"ok": False, "degraded": "llm-disabled"}

        # 记录本轮归属（_add 写库时要用）
        self._cur_user_id = user_id or ""
        self._cur_scope = scope or "global"
        self._cur_nickname = nickname or ""

        user_text = (user_text or "").strip()
        if len(user_text) < 2:
            return {"ok": True, "facts": 0, "applied": {}, "note": "user text too short"}

        facts = self._extract(user_text, assistant_text)
        if facts is None:
            return {"ok": False, "degraded": "extract-failed",
                    "error": getattr(self.llm, "last_error", None)}
        if not facts:
            return {"ok": True, "facts": 0, "applied": {"add": 0, "update": 0, "delete": 0, "none": 0}}
        return self._apply_facts(
            facts, subject=subject, source_ids=None, allowed_tiers=None
        )

    def _add_fact(self, fact: dict, text: str, subject: str) -> int:
        mid = self.store.add(self._to_input(fact, text, subject))
        for sid in fact.get("source_ids") or []:
            self.store.link(mid, int(sid), "derived_from", "evidence")
        return mid

    def _apply_facts(self, facts: list, subject: str = "self",
                     source_ids: list[int] | None = None,
                     allowed_tiers: set[str] | None = None,
                     source_rows: list[dict] | None = None) -> dict:
        """把抽出来的 fact 逐条判定并落库。"""
        applied = {"add": 0, "update": 0, "delete": 0, "none": 0}
        details = []
        ids: list[int] = []
        for idx, fact in enumerate(facts):
            text = str(fact.get("text") or "").strip()
            if not text:
                continue
            tier = str(fact.get("tier") or "L1").upper()
            if allowed_tiers is not None and tier not in allowed_tiers:
                continue
            evidence = fact.get("evidence") or []
            ref_ids = _refs_to_ids(fact.get("source_refs"), source_rows or [])
            if ref_ids:
                matched, source_status = ref_ids, "verified"
            else:
                matched, source_status = match_evidence(evidence, source_rows or [])
            fact["source_ids"] = matched
            fact["source_status"] = source_status
            neighbors = self.store.candidates(text, top_k=self.config.neighbor_k, subject=subject)
            decision = self._decide(fact, idx, neighbors)
            if decision is None:
                # 判定失败时保守处理：直接 ADD，不乱改已有记忆
                decision = {"op": "ADD", "reason": "decide-failed-fallback-add"}

            op = str(decision.get("op") or "ADD").upper()
            if op == "ADD":
                ids.append(self._add_fact(fact, text, subject))
                applied["add"] += 1
            elif op == "UPDATE":
                target = self._target(decision, neighbors)
                if target is None:
                    ids.append(self._add_fact(fact, text, subject))
                    applied["add"] += 1
                    op = "ADD(no-target)"
                else:
                    new_text = str(decision.get("text") or text).strip() or text
                    self.store.update_text(
                        target.id, new_text,
                        source_ids=fact.get("source_ids") or None,
                        source_status=fact.get("source_status"),
                    )
                    for sid in fact.get("source_ids") or []:
                        self.store.link(target.id, int(sid), "derived_from", "evidence")
                    ids.append(target.id)
                    applied["update"] += 1
            elif op == "DELETE":
                target = self._target(decision, neighbors)
                if target is None:
                    applied["none"] += 1
                    op = "NONE(no-target)"
                else:
                    self.store.forget(target.id)
                    applied["delete"] += 1
                    # 删掉之后把新事实作为"更正"存一条，不丢信息
                    ids.append(self._add_fact(fact, text, subject))
                    applied["add"] += 1
            else:
                applied["none"] += 1
                op = "NONE"

            details.append({"fact": text[:60], "op": op, "reason": decision.get("reason")})

        # 情绪已随每条 L1 落库，没有单独的日志表

        return {"ok": True, "facts": len(facts), "applied": applied, "details": details, "ids": ids}

    # -- 批量分层：L1 / L3 / L4 ------------------------------------------------

    def _compress_l1(self, facts: list[dict]) -> list[dict]:
        if len(facts) <= 3:
            return facts
        try:
            data = self.llm.chat_json(
                L1_COMPRESS_SYSTEM,
                json.dumps(facts, ensure_ascii=False),
                max_tokens=800,
            )
        except Exception:  # noqa: BLE001
            return facts
        if not isinstance(data, list):
            return facts
        out = []
        for item in data[:3]:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            item["tier"] = "L1"
            out.append(item)
        return out if out else facts

    def extract_batch(self, text: str, context: str = "", source_ids: list[int] | None = None) -> dict:
        """一批 L0 原话 → 只产 L1 短事实。"""
        if not self.enabled:
            return {"ok": False, "degraded": "llm-disabled"}
        source_rows = []
        if source_ids:
            try:
                marks = ",".join("?" for _ in source_ids)
                source_rows = [
                    {"id": int(r["id"]), "tier": "L0", "text": str(r["text"] or "")}
                    for r in self.store.conn.execute(
                        f"SELECT id,text FROM memory WHERE tier='L0' AND id IN ({marks}) ORDER BY id ASC",
                        list(source_ids),
                    ).fetchall()
                ]
            except Exception:
                source_rows = []
        facts = self._extract(text, "", context, source_rows=source_rows or None)
        if facts is None:
            return {"ok": False, "degraded": "extract-failed",
                    "error": getattr(self.llm, "last_error", None) or "llm returned no parseable JSON"}
        for fact in facts:
            if isinstance(fact, dict):
                fact["tier"] = "L1"
        facts = self._compress_l1(facts)
        return self._apply_facts(
            facts, subject="self", source_ids=source_ids,
            allowed_tiers={"L1"}, source_rows=source_rows,
        )

    def extract_rules(self, material: str, current_rules: str, context: str = "") -> list[str]:
        """从 L1/L3 + 现有 L4 里找真正的约定/底线。"""
        if self.llm is None or not getattr(self.llm, "enabled", False):
            return []
        system = (
            "你从长期记忆里找「真正需要遵守的约定、底线、称呼/相处要求」。\n"
            "只收明确、长期、以后还要照做的；观点、感慨、一次性事件、普通偏好都不要。\n"
            "已经有同类规则的不要重复，只输出新增或需要合并的。\n"
            '只返回 JSON：{"rules":["..."]}，没有就 {"rules":[]}。'
        )
        prompt = (
            (f"【身份】\n{context}\n\n" if context else "")
            + f"【现有 L4】\n{current_rules or '（空）'}\n\n"
            + f"【L1/L3 素材】\n{material[:12000]}"
        )
        try:
            data = self.llm.chat_json(system, prompt, max_tokens=400)
        except Exception:
            return []
        if not isinstance(data, dict):
            return []
        rules = data.get("rules")
        if not isinstance(rules, list):
            return []
        return [str(x).strip()[:100] for x in rules if str(x).strip()][:5]

    # -- episode：把一段对话压成事件线 ---------------------------------------

    def summarize_episode(self, turns: list[dict], subject: str = "self",
                          window_hint: str = "", context: str = "",
                          source_ids: list[int] | None = None,
                          source_rows: list[dict] | None = None) -> dict:
        """旧路径：把一批对话轮次压成一条 L3 事件记录。

        当前管线用 /batch/run + THREAD_SYSTEM。
        process_turn 是旧的逐轮抽取，保留兼容；不要再接新流程。
        summarize_episode 旧版把一段压成一条 L3，当前不再使用。

        任何失败都不抛，返回 degraded，调用方静默跳过。
        """
        # 只看 LLM 通不通，不看 extract 开关：逐条抽取按轮算钱，episode 按段算，
        # 两个开关应该分开。配了 LLM 就能用 episode，哪怕 extract 一直关着。
        if self.llm is None or not getattr(self.llm, "enabled", False):
            return {"ok": False, "degraded": "llm-disabled"}
        if not isinstance(turns, list) or not turns:
            return {"ok": True, "skipped": "empty"}

        transcript = self._transcript(turns)
        if not transcript:
            return {"ok": True, "skipped": "empty-transcript"}

        prompt = (f"时间：{window_hint}\n\n对话：\n{transcript}"
                  if window_hint else f"对话：\n{transcript}")
        if context:
            prompt = f"【身份/现有规则】\n{context[:3000]}\n\n{prompt}"
        raw = self.llm.chat(EPISODE_SYSTEM, prompt, max_tokens=1000)
        if not raw:
            return {"ok": False, "degraded": "llm-failed",
                    "error": getattr(self.llm, "last_error", None)}

        raw = raw.strip()
        data = None
        match = re.search(r"\{.*\}", raw, re.S)
        if match:
            try:
                candidate = json.loads(match.group(0))
                if isinstance(candidate, dict):
                    data = candidate
            except (TypeError, ValueError):
                data = None
        text = str((data or {}).get("text") or raw).strip()
        evidence = (data or {}).get("evidence") or []
        if len(text) < 10:
            return {"ok": False, "degraded": "too-short"}
        text = re.sub(r"^#+\s*", "", text).strip()
        text = strip_memory_prefix("L3", text)
        matched, source_status = match_evidence(evidence, source_rows or [])

        vec = None
        vec_model = None
        if self.embedder is not None and getattr(self.embedder, "enabled", False):
            vec = self.embedder.embed_one(text)
            vec_model = self.embedder.model if vec else None

        from memory_core import MemoryInput  # 延迟导入，避免循环
        mid = self.store.add(MemoryInput(
            text=text,
            tier="L3",
            subject=subject,
            tags=["episode", f"turns:{len(turns)}"],
            source_ids=matched or None,
            source_status=source_status,
            vec=vec,
            vec_model=vec_model,
        ))
        for pid in source_ids or []:
            self.store.link(mid, int(pid), "derived_from", "fact")
        for sid in matched or []:
            self.store.link(mid, int(sid), "derived_from", "evidence")
        return {"ok": True, "id": mid, "text": text, "chars": len(text), "turns": len(turns)}

    def extract_l2(self, transcript: str, facts: list[str],
                   source_rows: list[dict] | None = None) -> list[dict]:
        """从 L0 + L1 里抽短期推断；只写 hypothesis。"""
        if self.llm is None or not getattr(self.llm, "enabled", False):
            return []
        blocks = []
        if source_rows:
            blocks.append("【来源（按对话顺序）】\n" + _render_refs(source_rows))
            blocks.append("每条结果请给 source_refs（引用上面的编号）。")
        if facts:
            blocks.append("【L1 事实】\n" + "\n".join(f"- {x}" for x in facts[:20]))
        if not source_rows and transcript:
            blocks.append("【当前对话】\n" + str(transcript)[:6000])
        if len(blocks) == 0:
            return []
        data = self.llm.chat_json(L2_SYSTEM, "\n\n".join(blocks), max_tokens=500)
        if isinstance(data, dict):
            data = data.get("items")
        if not isinstance(data, list):
            return []
        out = []
        for item in data[:3]:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            out.append(item)
        return out

    def review_l2(self, active: list[dict], evidence: list[dict]) -> list[dict]:
        """复查 hypothesis，返回 confirm/reject/keep。"""
        if self.llm is None or not getattr(self.llm, "enabled", False):
            return []
        if not active:
            return []
        lines = []
        for i, item in enumerate(active, 1):
            exp = time.strftime("%m-%d %H:%M", time.localtime(float(item.get("expires_at") or 0)))
            lines.append(
                f"[{i}] {item.get('text')}（confidence {item.get('confidence', 0):.2f}，过期 {exp}）"
            )
        ev_lines = [f"[{i}] {str(x.get('text') or '')}" for i, x in enumerate(evidence, 1)]
        payload = "【待复查 L2】\n" + "\n".join(lines) + "\n\n【最近证据】\n" + "\n".join(ev_lines)
        data = self.llm.chat_json(L2_REVIEW_SYSTEM, payload, max_tokens=500)
        if not isinstance(data, dict):
            return []
        items = data.get("items")
        return [x for x in items if isinstance(x, dict)] if isinstance(items, list) else []

    def plan_threads(self, transcript: str, facts: list[str],
                     open_threads: list[dict],
                     source_rows: list[dict] | None = None) -> dict | None:
        """决定当前段续写哪些 open L3、新建哪些 L3。"""
        if self.llm is None or not getattr(self.llm, "enabled", False):
            return None
        blocks = []
        if open_threads:
            blocks.append("【最近相关事件（含 open / dormant / closed / standalone）】")
            for item in open_threads:
                blocks.append(
                    f"- id={item.get('id')} [{item.get('status')}] {item.get('title')}"
                    f"（最后 {time.strftime('%m-%d %H:%M', time.localtime(float(item.get('last_seen_at') or 0)))}）\n"
                    f"  摘要：{str(item.get('summary') or '')[:300]}\n"
                    f"  已有正文：{str(item.get('summary') or item.get('text') or '（无）')[:300]}"
                )
        else:
            blocks.append("【最近相关事件】\n（空）")
        if source_rows:
            blocks.append("【可引用来源（按对话顺序）】\n" + _render_refs(source_rows))
            blocks.append("每条结果请给 source_refs（引用上面的编号，可多条）；evidence 可选。")
        else:
            if facts:
                blocks.append("【这段抽出的事实】\n" + "\n".join(f"- {x}" for x in facts[:20]))
            blocks.append("【当前对话】\n" + str(transcript or "")[:8000])
        data = self.llm.chat_json(THREAD_SYSTEM, "\n\n".join(blocks), max_tokens=900)
        if not isinstance(data, dict):
            return None
        return data

    def review_lifecycle(self, threads: list[dict]) -> list[dict]:
        if self.llm is None or not getattr(self.llm, "enabled", False):
            return []
        if not threads:
            return []
        lines = []
        for item in threads:
            lines.append(
                f"- id={item.get('id')} [{item.get('status')}] {item.get('title')}\n"
                f"  沉默 {item.get('silence_days')} 天；最后 {time.strftime('%m-%d %H:%M', time.localtime(float(item.get('last_seen_at') or 0)))}\n"
                f"  摘要：{str(item.get('summary') or '')[:500]}"
            )
        data = self.llm.chat_json(L3_LIFECYCLE_SYSTEM, "\n\n".join(lines), max_tokens=1200)
        if not isinstance(data, dict):
            return []
        items = data.get("items")
        if not isinstance(items, list):
            return []
        return [x for x in items if isinstance(x, dict)]

    def plan_core(self, closed_threads: list[dict]) -> list[dict]:
        """从已结束的 L3 里挑构成性事件，并重写成能脱离上下文读的版本。"""
        if self.llm is None or not getattr(self.llm, "enabled", False):
            return []
        if not closed_threads:
            return []
        lines = []
        for item in closed_threads:
            block = [
                f"- {item.get('title')}",
                f"  摘要：{str(item.get('summary') or '')[:600]}",
                f"  结束：{time.strftime('%m-%d %H:%M', time.localtime(float(item.get('closed_at') or 0)))}",
            ]
            # 带上它引用的 L0 原话：重写要用到，光有摘要不够
            evidence = self._evidence_texts(item.get("source_ids") or [], limit=8)
            if evidence:
                block.append("  当时的话：")
                block.extend(f"    · {x}" for x in evidence)
            lines.append("\n".join(block))
        data = self.llm.chat_json(CORE_SYSTEM, "\n\n".join(lines), max_tokens=1200)
        if not isinstance(data, dict):
            return []
        items = data.get("items")
        if not isinstance(items, list):
            return []
        return [x for x in items if isinstance(x, dict)][:2]

    def _transcript(self, turns: list[dict]) -> str:
        lines = []
        per = max(50, int(self.config.episode_per_turn_chars))
        for turn in turns:
            if not isinstance(turn, dict):
                continue
            user = str(turn.get("user") or "").strip()
            assistant = str(turn.get("assistant") or "").strip()
            if not user:
                continue
            lines.append(f"主人：{user[:per]}")
            if assistant:
                lines.append(f"我：{assistant[:per]}")
        text = "\n".join(lines)
        cap = max(1000, int(self.config.episode_max_chars))
        if len(text) > cap:
            # 留尾巴：近况比开头重要，开头的内容多半已经被前几条 episode 收过了
            text = "…（前文已省略）\n" + text[-cap:]
        return text

    # -- 内部 ---------------------------------------------------------------

    def _extract(self, user_text: str, assistant_text: str, context: str = "",
                 source_rows: list[dict] | None = None):
        """抽取事实。空结果重试一次。

        实测 deepseek-flash 在 temperature=0 下也会偶发返回空数组——
        同一条「我爸住院了」有过抽出 1 条、也有过抽出 0 条。
        漏抽比多抽一次更贵（那条记忆就永远没了），所以重试一次。
        """
        if source_rows:
            convo = _render_refs(source_rows)
            convo += "\n\n每条结果请给 source_refs（引用上面的编号，可多条）；evidence 可选，作为兜底。"
        else:
            convo = f"主人：{user_text[:self.config.max_context_chars]}"
            if assistant_text:
                convo += f"\n我：{assistant_text[:self.config.max_context_chars]}"
        if context:
            convo = f"【身份/现有规则】\n{context[:3000]}\n\n{convo}"

        last = None
        for _attempt in range(2):
            result = self.llm.chat_json(EXTRACT_SYSTEM, convo, max_tokens=2400)
            if result is None:
                continue
            if not isinstance(result, list):
                nested = result.get("facts") if isinstance(result, dict) else None
                if not isinstance(nested, list):
                    continue
                result = nested
            cleaned = [
                item for item in result[: self.config.max_facts]
                if isinstance(item, dict)
                and str(item.get("text") or "").strip()
                and not _is_speculation(str(item.get("text") or ""))
            ]
            last = cleaned
            if cleaned:
                return cleaned
        return last

    def _decide(self, fact: dict, index: int, neighbors):
        if not neighbors:
            return {"op": "ADD", "reason": "no similar memory"}
        existing = [
            {"id": h.id, "tier": h.tier, "text": h.text, "ts": int(h.ts), "score": round(h.score, 3)}
            for h in neighbors
        ]
        payload = json.dumps({
            "new_facts": [{"fact_index": index, "text": fact.get("text"),
                           "tier": fact.get("tier"), "importance": fact.get("importance")}],
            "existing_memories": existing,
        }, ensure_ascii=False)
        result = self.llm.chat_json(DECIDE_SYSTEM, payload, max_tokens=700)
        if isinstance(result, list) and result:
            first = result[0]
            if isinstance(first, dict) and first.get("op"):
                return first
        if isinstance(result, dict) and result.get("op"):
            return result
        return None

    def _target(self, decision: dict, neighbors):
        tid = decision.get("target_id")
        try:
            tid = int(tid)
        except (TypeError, ValueError):
            return None
        for h in neighbors:
            if h.id == tid:
                return h
        return None

    def _emotion_values(self, emo, fact) -> tuple[str, float, float, str]:
        """返回 label/valence/arousal/reason；不根据 label 猜正负。"""
        label = ""
        reason = ""
        valence = 0.0
        arousal = 0.5
        if isinstance(emo, dict):
            label = str(emo.get("label") or "").strip()
            reason = str(emo.get("reason") or "").strip()
            try:
                valence = max(-1.0, min(1.0, float(emo.get("valence", 0.0))))
            except (TypeError, ValueError):
                valence = 0.0
            try:
                arousal = max(0.0, min(1.0, float(emo.get("arousal", 0.5))))
            except (TypeError, ValueError):
                arousal = 0.5
        if not label:
            for kw in (fact.get("keywords") or []):
                s = str(kw)
                if s.startswith("情绪:") and len(s) > 3:
                    label = s[3:].strip()
                    reason = str(fact.get("text") or "")[:150]
                    break
        return label, valence, arousal, reason

    def _to_input(self, fact: dict, text: str, subject: str):
        from memory_core import MemoryInput  # 延迟导入，避免循环
        tier = str(fact.get("tier") or "L1").upper()
        if tier not in {"L0", "L1", "L3"}:
            tier = "L1"
        text = strip_memory_prefix(tier, text)
        vec = None
        vec_model = None
        if self.embedder is not None and getattr(self.embedder, "enabled", False):
            vec = self.embedder.embed_one(text)
            vec_model = self.embedder.model if vec else None
        # 情绪跟着 L1 走：每条便签带自己的情绪
        emo_label, emo_valence, emo_arousal, _reason = self._emotion_values(
            fact.get("emotion"), fact)
        return MemoryInput(
            text=text,
            tier=tier,
            subject=str(fact.get("subject") or subject),
            tags=["extracted"] + [str(k) for k in (fact.get("keywords") or [])][:8],
            source_ids=fact.get("source_ids") or None,
            source_status=str(fact.get("source_status") or "unverified"),
            emotion_label=emo_label,
            emotion_valence=emo_valence if emo_label else None,
            emotion_arousal=emo_arousal if emo_label else None,
            ask_him=str(fact.get("ask_him") or "").strip()[:500],
            vec=vec,
            vec_model=vec_model,
            user_id=getattr(self, "_cur_user_id", ""),
            scope=getattr(self, "_cur_scope", "global"),
            nickname=getattr(self, "_cur_nickname", ""),
        )
