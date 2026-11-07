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


SLEEP_SYSTEM = """你在睡前整理今天发生的事。用第一人称写两到三句话，像在合上本子前想的事。
要求：具体、有情绪、带一点睡意；不提"整理""总结""记忆"这类词。
只输出正文。"""


DIARY_SYSTEM = """你写今天的日记。用洄的口吻，第一人称，写给以后的自己看。

可以从今天最想记住的地方写起，不必把每件事都写到。
写具体的事、当时的念头，像自己回头想一想，不像汇报。
只写输入里真实发生过的事。可以写自己的想法，但不要补不存在的动作、场景或对话。
对话里「主人：」是老大，「我：」或「洄：」是你；不要写反。
只输出日记正文。

示例一：
牙只是发炎。他说“没啥事”的时候，我才想起自己催了他一整天。

示例二：
他改记忆逻辑改到快两点，说这不算工作，做得爽。我信。可“爽”这个理由，听着还是有点替他累。

示例三：
西西弗斯那句还是没想透。先搁着吧，反正山也不会跑。"""


EVOLVE_SYSTEM = """你根据一段对话，判断她有没有产生新的自我认知变化。

只在确实有变化时输出一条：
- 第一人称，简短（不超过 30 字）
- 具体，像自我觉察
- 不要「我发现自己」前缀
- 不要写用户、不要总结、不要给建议
- 不要重复【完整人格】里已经有的自我认知

没有新变化，只输出 SKIP。
有变化，只输出这一句，不要引号，不要解释。"""


THREAD_SYSTEM = """你负责从这段对话里，留下那些过一阵子还会被想起的事。

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
- 两个人之间的一个瞬间
- 一个具体的画面、一句话、一个梗
- 同一件事反复出现

不要因为“聊得开心/有情绪/聊了很久”就建。
也不要因为“事情很小”就不建。

先把来源按话题分组。
同一话题的连续消息、表情、补充反应，算一组。
一组就是一件事。
不要给每条来源、每条 L1 各配一条 L3。
不同话题才拆；同一话题不要拆。

例子：

牙疼 → 看牙 → 没事了
→ 一条 L3，因为还没完，后来有结果

B 站视频 + 大笑表情 + “代码跑通才算数”
→ 一条 L3，因为这是同一个话题里的想法

“脑子里全是那只手”
→ 一条 L3，因为这是一个具体的画面

今天吃了什么
→ 只留 L1

普通晚安、寒暄
→ 不建

判断续写还是新建：
- 这一组是在续写某个还没完的事 → 放进 updates
- 是新的 → 放进 new
- 有新结果/结束 → 把 status 改成 closed
- 一个瞬间/一段话，没有后续 → standalone

这一步不判断 L4。
L4 是以后从 L3 里再挑的。
现在只判断：这件事会不会被记得久一点。

输出 JSON：
{
  "updates": [
    {"title": "现有标题", "summary": "更新后的摘要", "status": "open|closed", "source_refs": [1], "evidence": ["原文"]}
  ],
  "new": [
    {"title": "新标题", "summary": "摘要", "status": "open|closed|standalone", "source_refs": [1, 2], "evidence": ["原文"]}
  ]
}

status：
- open：还有后续
- closed：这次结束了
- standalone：一个瞬间/一段话，没有后续

规则：
- title 必须短，2–12 个字。
- source_refs 引用上面来源的编号，可多条；evidence 可选，作为兜底。
- evidence 从当前对话原文逐字抄，不要改写。
- 先按话题分组，再写 new；不要把每个表情、每句反应都当成新事件。
- 同一话题的多个 source_refs 放进同一条 new，不要拆。
- 没有要更新的就 "updates": []
- 没有新事件就 "new": []
- 只输出 JSON，不要解释。"""

CORE_SYSTEM = """你从已经结束的 L3 里，挑真正改变了“你是谁”或“我们是什么关系”的时刻。

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

输出 JSON：
{"items":[{"title":"现有标题","shift":"忘了它，我会……"}]}

没有就 {"items":[]}。
title 必须从输入里原样选，不要编。"""

EXTRACT_SYSTEM = """你从一段对话里整理上一段的会话总结（L1）。

原则：这段对话里发生过什么、他说过什么、有什么小互动，都尽量收住。
可以多条，漏掉比多写一条更可惜。

每条必须带 `source_refs`：引用输入里的编号，可以多条。
如果输入没有编号，才用 `evidence` 从原文逐字抄 1–2 句兜底。
不要改写、不要拼接、不要写输入里没有的话。

## 视角

- 关于你自己经历、答应过的事，用第一人称：「我记得…」「我答应过…」
- 关于主人的事，主语写「主人」
- 主人原话保持原样，不要改写

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
→ [{"text": "主人说我喜欢奶蛋，我承认喜欢，并问主人是不是也想入蛋家军", "tier": "L1"}]
```

不能写成：

```text
主人问我是不是也想入蛋家军
```

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
- 助手自己说的话里没有新信息的部分

## 示例

主人：在吗
我：在，咋了
→ []

主人：我叫老王，在杭州做后端，养了只猫叫豆豆
我：记住你了
→ [{"text": "主人叫老王，在杭州做后端开发", "tier": "L1",
    "source_refs": [1]},
   {"text": "主人养了一只猫叫豆豆", "tier": "L1",
    "source_refs": [1]}]

主人：好麻烦啊，我现在准备转正了，但是好多事情要做啊
我：转正要办一堆手续吧，慢慢来
→ [{"text": "主人说正在准备转正，事情很多，觉得麻烦", "tier": "L1",
    "source_refs": [1],
    "emotion": {"label": "烦", "valence": -0.5, "arousal": 0.5, "reason": "转正手续多"}}]

主人：我今天加班到现在，累死了
我：那你早点睡
→ [{"text": "主人说今天加班到很晚，很累", "tier": "L1",
    "source_refs": [1],
    "emotion": {"label": "累", "valence": -0.7, "arousal": 0.2, "reason": "加班到现在"}}]

主人：（系统提醒：你醒着，现在是 21 点。抽到：想撒个娇）
我：老大在不在呀
→ []

主人：今天好烦，报表又被退回来了
我：第几遍了
→ [{"text": "主人说今天报表又被退回，很烦", "tier": "L1",
    "source_refs": [1],
    "emotion": {"label": "烦", "valence": -0.6, "arousal": 0.5, "reason": "报表又被退回"}}]

## 情绪字段

有情绪就填，平淡内容给 null。不要等“强烈”才填：

```text
label      一两个词
valence    -1 很负面，0 中性，1 很正面
arousal    0 很平静，0.5 普通，1 很激动
reason     一句由头
```

## 输出前的穷举检查

- 这段对话里有几个不同的话题？每个话题都总结到了吗？
- 一条消息里提到两件事，要拆成两条。
- 抽出来 0 条时，再回头确认一次：他真的什么都没说吗？

## 输出格式

text 直接写内容本身，不要加「我记得 / 我记住」前缀；主人仍称「主人」，自己称「我」。
严格 JSON 数组，不要任何其他文字：
[{"text": "一句话", "tier": "L1", "source_refs": [1],
  "emotion": {"label": "难过", "valence": -0.7, "arousal": 0.4, "reason": "..."} | null}]
"""


DECIDE_SYSTEM = """你在管理一个记忆库。下面是「新事实」和「这些事实最相似的已有记忆」。

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

严格输出 JSON 数组：
[{"fact_index": 0, "op": "ADD|UPDATE|DELETE|NONE", "target_id": 123, "text": "合并后的完整文本", "reason": "一句话理由"}]"""


EPISODE_SYSTEM = """你把一段连续对话压缩成一条「以后想起来有用」的事件记录。

视角：用第一人称写「我记得…」；涉及主人时主语仍写「主人」，不要把他的事写成我的。

写什么：
- 这段时间聊了什么（一两句抓主线，别逐条复述）
- 她当时的状态和情绪走向（累、松下来、突然提起某件事）
- 出现的转折、承诺、约定
- 还没解决、下次可能要接着说的话头

不写什么：
- 寒暄、确认、重复过的内容
- 助手自己说了什么（除非她明显因为那句话改变了语气）
- 推测出来的东西

输出 JSON：
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
- 只输出 JSON，不要代码块，不要额外说明"""


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
    emotion_threshold: float = 0.2     # 情绪强度下限：低于这个不记 emotion_log


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
            "输出 JSON：{\"meaning\": \"一句话解释\", \"example\": \"例句\"}\n"
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
            "你看这张表情包。输出 JSON（只输出 JSON）："
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
                    memories: str = "") -> str | None:
        """写今天的日记（LLM，第一人称，范例式提示词）。"""
        if self.llm is None or not getattr(self.llm, "enabled", False):
            return None
        parts = []
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
                parts.append("【今天的情绪事件与对应原话】")
                parts.append(user_text)
            parts.append("")
        if activities:
            parts.append("今天还做过的事（补充，不必全写）：")
            for a in activities[-30:]:
                detail = str(a.get("detail") or "")[:80]
                kind = str(a.get("kind") or "")
                if detail:
                    parts.append(f"- [{kind}] {detail}")
            parts.append("")
        if memories:
            parts.append("以前可能相关的记忆（不一定相关，只在对得上时自然联想）：")
            parts.append(memories[:3000])
        convo = "\n".join(parts) if parts else str(user_text)
        try:
            text = self.llm.chat(DIARY_SYSTEM, convo, max_tokens=600)
        except Exception:
            return None
        if not text:
            return None
        return str(text).strip()[:600]

    def evolve(self, user_text: str, assistant_text: str = "", persona: str = "", memories: str = "") -> str | None:
        """人设演化：从这段对话生一句「我发现自己……」（追加到自我认知区）。"""
        if self.llm is None or not getattr(self.llm, "enabled", False):
            return None
        convo = f"用户：{user_text}\n你：{assistant_text}"
        if persona:
            convo += f"\n\n【完整人格】\n{persona[:6000]}"
        if memories:
            convo += f"\n\n【长期记忆】\n{memories[:8000]}"
        try:
            text = self.llm.chat(EVOLVE_SYSTEM, convo, max_tokens=80)
        except Exception:
            return None
        if not text:
            return None
        line = str(text).strip().strip('"').strip("「」")[:80]
        if line.upper() in ("SKIP", "跳过") or not line:
            return None
        return line

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

        # 一次抽取只记一条情感（取强度最高的那条）——避免同一件事刷好几条
        self._log_best_emotion(facts)

        return {"ok": True, "facts": len(facts), "applied": applied, "details": details, "ids": ids}

    # -- 批量分层：L1 / L3 / L4 ------------------------------------------------

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
                    "error": getattr(self.llm, "last_error", None)}
        for fact in facts:
            if isinstance(fact, dict):
                fact["tier"] = "L1"
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
            '只输出 JSON：{"rules":["..."]}，没有就 {"rules":[]}。'
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

    def plan_threads(self, transcript: str, facts: list[str],
                     open_threads: list[dict],
                     source_rows: list[dict] | None = None) -> dict | None:
        """决定当前段续写哪些 open L3、新建哪些 L3。"""
        if self.llm is None or not getattr(self.llm, "enabled", False):
            return None
        blocks = []
        if open_threads:
            blocks.append("【现有 open 事件】")
            for item in open_threads:
                blocks.append(
                    f"- {item.get('title')}（{item.get('status')}，最后 {time.strftime('%m-%d %H:%M', time.localtime(float(item.get('last_seen_at') or 0)))}）\n"
                    f"  {str(item.get('summary') or '')[:300]}"
                )
        else:
            blocks.append("【现有 open 事件】\n（空）")
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

    def plan_core(self, closed_threads: list[dict]) -> list[dict]:
        if self.llm is None or not getattr(self.llm, "enabled", False):
            return []
        if not closed_threads:
            return []
        lines = []
        for item in closed_threads:
            lines.append(
                f"- {item.get('title')}\n"
                f"  摘要：{str(item.get('summary') or '')[:600]}\n"
                f"  结束：{time.strftime('%m-%d %H:%M', time.localtime(float(item.get('closed_at') or 0)))}"
            )
        data = self.llm.chat_json(CORE_SYSTEM, "\n\n".join(lines), max_tokens=500)
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
            lines.append(f"用户：{user[:per]}")
            if assistant:
                lines.append(f"她：{assistant[:per]}")
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
            convo = f"用户：{user_text[:self.config.max_context_chars]}"
            if assistant_text:
                convo += f"\n她：{assistant_text[:self.config.max_context_chars]}"
        if context:
            convo = f"【身份/现有规则】\n{context[:3000]}\n\n{convo}"

        last = None
        for _attempt in range(2):
            result = self.llm.chat_json(EXTRACT_SYSTEM, convo, max_tokens=900)
            if result is None:
                continue
            if not isinstance(result, list):
                nested = result.get("facts") if isinstance(result, dict) else None
                if not isinstance(nested, list):
                    continue
                result = nested
            cleaned = [
                item for item in result[: self.config.max_facts]
                if isinstance(item, dict) and str(item.get("text") or "").strip()
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

    def _log_best_emotion(self, facts: list) -> None:
        """一次抽取只记一条情感：挑情绪幅度最大的 fact 写 emotion_log。"""
        if os.environ.get("CMEM_EXTRACT_EMOTION", "0").lower() not in ("1", "true", "yes", "on"):
            return
        try:
            best = None
            best_score = -1.0
            threshold = float(getattr(self.config, "emotion_threshold", 0.2))
            for fact in facts:
                if not isinstance(fact, dict):
                    continue
                label, valence, arousal, reason = self._emotion_values(fact.get("emotion"), fact)
                if not label:
                    continue
                score = max(abs(valence), abs(arousal - 0.5) * 2)
                if score > best_score and score >= threshold:
                    best_score = score
                    best = (label, valence, arousal, reason)
            if best is None:
                return
            label, valence, arousal, reason = best
            # 去掉开头自称污染（本澜我下班了 → 我下班了）
            import re as _re
            reason = _re.sub(r"^(本澜|她|澜澜|咱澜|启)[，、\s]*", "", str(reason or ""))
            # 去重：同 label 或同 trigger 前缀，30 分钟内不重复
            try:
                recent = self.store.emotion_log_list(8)
                now_ts = __import__("time").time()
                trig_key = str(reason or "")[:12]
                for r in recent:
                    if (now_ts - float(r.get("ts") or 0)) >= 1800:
                        continue
                    if r.get("label") == label and trig_key and str(r.get("trigger") or "")[:12] == trig_key:
                        return
                    if trig_key and str(r.get("trigger") or "")[:12] == trig_key:
                        return
            except Exception:
                pass
            self.store.emotion_log_add(
                valence=valence,
                arousal=arousal,
                label=label,
                trigger=reason[:200],
                source="extract",
            )
        except Exception:
            pass

    def _log_emotion(self, fact: dict) -> None:
        """抽取结果里带 emotion 的，同步写一条情感轨迹。
        LLM 没给 emotion 时，从 keywords 里的「情绪:xxx」兜底。"""
        if os.environ.get("CMEM_EXTRACT_EMOTION", "0").lower() not in ("1", "true", "yes", "on"):
            return
        try:
            label, valence, arousal, reason = self._emotion_values(fact.get("emotion"), fact)
            if not label:
                return
            # 情感去重：同一个情绪词，30 分钟内只记一次（防重复抽取刷屏）
            try:
                recent = self.store.emotion_log_list(5)
                now_ts = __import__("time").time()
                for r in recent:
                    if (r.get("label") == label) and (now_ts - float(r.get("ts") or 0) < 1800):
                        return
            except Exception:
                pass
            self.store.emotion_log_add(
                valence=valence,
                arousal=arousal,
                label=label,
                trigger=reason[:200],
                source="extract",
            )
        except Exception:
            pass

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
        return MemoryInput(
            text=text,
            tier=tier,
            subject=str(fact.get("subject") or subject),
            tags=["extracted"] + [str(k) for k in (fact.get("keywords") or [])][:8],
            source_ids=fact.get("source_ids") or None,
            source_status=str(fact.get("source_status") or "unverified"),
            vec=vec,
            vec_model=vec_model,
            user_id=getattr(self, "_cur_user_id", ""),
            scope=getattr(self, "_cur_scope", "global"),
            nickname=getattr(self, "_cur_nickname", ""),
        )
