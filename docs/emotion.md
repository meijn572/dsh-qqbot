# 情绪与关系指标

状态：情绪链路第一版已实现；亲密度仍待讨论。

## 1. 面板里的值是什么

当前 `/api/mood` 返回：

```json
{
  "mood": 30,
  "emotion_label": "讪讪",
  "active": "normal",
  "valence": -0.4,
  "arousal": 0.5,
  "intimacy": 428,
  "stage": "亲密",
  "dims": {
    "valence": -40,
    "arousal": 50,
    "心情值": 30,
    "亲密度": 43,
    "唤醒": 50
  }
}
```

### valence

情绪效价，范围 `-1 ~ 1`。

```text
-1  很负面
 0  中性
+1  很正面
```

原始值。

### dims.valence

```text
valence × 100
```

所以 `-0.4` 显示为 `-40`。

### 心情值

把 valence 映射到 `0 ~ 100`：

```text
(valence + 1) × 50
```

```text
0   最负面
50  中性
100 最正面
```

### arousal

唤醒度，范围 `0 ~ 1`。

```text
0    很平静
0.5  普通
1    很激动
```

### 唤醒

```text
arousal × 100
```

### emotion_label

最近一次情绪日志的标签，比如：

```text
讪讪 / 踏实 / 受宠若惊 / 暖
```

### mood

当前面板里的 `mood` 是数字分数：

```text
(valence + 1) × 50
```

不是情绪标签。

### active

底层粗档状态：

```text
normal / happy / tired / annoyed / bored
```

当前情绪自检只写 valence/arousal，不更新 active，所以经常还是 `normal`。

### intimacy

关系亲密度原始值，范围 `0 ~ 1000`。

### 亲密度

```text
min(100, intimacy / 10)
```

所以：

```text
428 / 10 = 42.8 → 43
```

### stage

由 intimacy 分段得到：

```text
0–99     陌生
100–299  熟悉
300–599  亲密
600+     依赖
```

当前 428 → 亲密。

### confidence

当前固定 `50`，是占位值，不是真实置信度。

## 2. 哪些值应该让模型填

### 模型填

```text
label        情绪名，一两个词
valence      -1 ~ 1
arousal      0 ~ 1
confidence   0 ~ 1，可选
reason       一句由头
```

推荐输出：

```json
{
  "label": "踏实",
  "valence": 0.6,
  "arousal": 0.25,
  "confidence": 0.8,
  "reason": "他说人格的变化是连续且一致的"
}
```

没有真实情绪：

```json
{"skip": true}
```

### 代码派生

```text
心情值       (valence + 1) * 50
唤醒         arousal * 100
亲密度       intimacy / 10
stage        按 intimacy 分段
mood 数字    同心情值
```

### 不要模型填

```text
intimacy     关系状态，由真实互动累计
affinity     群友熟悉度，由互动累计
stage        由 intimacy 派生
mood 数字    由 valence 派生
```

## 3. arousal 是干什么的

`arousal` 是唤醒度，不是情绪强度。

```text
valence   好不好
arousal   平静还是激动
```

同样正面：

```text
高兴 + 高 arousal = 兴奋
高兴 + 低 arousal = 安心、暖、踏实
```

同样负面：

```text
难过 + 高 arousal = 焦虑、崩溃
难过 + 低 arousal = 低落、疲惫
```

生气：

```text
生气 + 高 arousal = 愤怒
生气 + 低 arousal = 不满、冷淡
```

它决定表达的能量感：

```text
高 arousal：短句、快、感叹、动作多
低 arousal：慢、轻、短、没力气
```

当前永远写 `0.5`，所以所有情绪都是同一个能量档。

## 4. 当前机制的问题

### 4.1 正负靠标签白名单

`qqbot/domains/growth/emotion.py` 和 `service/extractor.py` 里都有：

```python
positive = 标签是否匹配一小串词
valence = intensity if positive else -intensity
```

结果：

```text
踏实      → 不在白名单 → 负
放心      → 不在白名单 → 负
受宠若惊  → 不在白名单 → 负
```

这是用硬规则替代语义判断。

### 4.2 衰减太快

`service/memory_core.py`：

```python
decay = max(0, 1.0 - 0.2 * hours)
valence *= decay
```

```text
3 小时 → 剩 40%
5 小时 → 归零
```

而情绪自检间隔是 3–5 小时，所以经常在下次自检前就衰减光了。

### 4.3 arousal 固定 0.5

```python
set_emotion(label, valence, 0.5, reason)
```

唤醒度永远中性。

### 4.4 confidence 固定 50

不是模型判断，是占位。

### 4.5 intensity 和 valence 重复

如果 valence 已经是 `-1 ~ 1` 的绝对强度，intensity 基本是重复字段。

## 5. 建议的模型契约

```text
label        一两个词
valence      -1 很负面，0 中性，1 很正面
arousal      0 很平静，0.5 普通，1 很激动
confidence   0–1
reason       一句由头
```

没有真实情绪就 skip，不要为了打卡硬写。

prompt 里给参照：

```text
0.2 轻微
0.5 明显
0.8 很强
```

不要让模型只输出 0.5。

## 6. 亲密度怎么算

### 6.1 每轮 +1

`plugins/dsh-remembers/app.mjs` 在 turn end：

```text
keptUser && assistant
→ POST /state {"bump": 1.0}
```

也就是：

```text
一轮完整对话 = +1 亲密度
```

只发图片、没有有效用户文本/没有 assistant 回复，不涨。

### 6.2 上限

```text
0 ~ 1000
```

`set_state` clamp。

### 6.3 面板映射

```text
面板亲密度 = min(100, intimacy / 10)
```

```text
intimacy 428 → 43
```

### 6.4 阶段

```text
0    陌生
100  熟悉
300  亲密
600  依赖
```

### 6.5 affinity 是另一个东西

`affinity` 是群友熟悉度：

```text
bridge touch_guest
→ 群消息每人 +0.5
```

它不是全局亲密度，也不决定 stage。

私聊主人不走 affinity 增量。

## 7. 要改的地方

### 7.1 emotion.py

- prompt 增加 `valence`、`arousal`、`confidence`
- 删除标签白名单
- 直接用模型给的 valence/arousal
- `intensity` 可以删除或降级为可选

### 7.2 extractor.py

- `_log_best_emotion` / `_log_emotion` 同样改为读 valence/arousal
- 不再用标签猜正负

### 7.3 memory_core.py

- 衰减改为更慢的曲线，例如半衰期 6–12 小时
- 不要 5 小时归零
- 可选：arousal 也按同样规则衰减到 0.5

### 7.4 panel_readers.py

- `mood` 数字改名 `mood_score`，避免和情绪标签混淆
- `confidence` 使用真实值，不再固定 50
- `updated_at` 改成情绪更新时间，而不是 `last_interaction`

### 7.5 文档和测试

- 测试正向标签 `踏实/放心/受宠若惊` 的 valence 为正
- 测试 5 小时后不会归零
- 测试 arousal 能随输入变化

## 8. 结论

```text
模型负责：label、valence、arousal、confidence、reason
代码负责：心情值、唤醒、亲密度、stage、显示格式
```

亲密度不是模型情绪判断，是真实互动累计：

```text
每轮完整对话 +1
面板 = intimacy / 10
stage 按 0/100/300/600 分段
```

## 9. 情绪自检的输入怎么拼

`qqbot/domains/growth/emotion.py` 的调用链：

```text
l0_recent(OWNER_CHAT_KEY, 40)
persona_context()
collect(l1=20, l3=10, l0=20)
format_block(evidence)
→ prompt
```

### 9.1 persona_context

服务端 `/persona/context` 返回：

```text
【核心设定】constitution
【自我认知】self_model
【身份】identity
【自我形象】self_image
【我眼中的主人】user_profile
```

空段会跳过。

### 9.2 最近 L0

```text
l0_recent(私聊主人, 40)
```

取当前私聊会话最近的 L0 文本，最多 16000 字。

### 9.3 L1/L3 + 对应 L0

```text
L1 × 20
L3 × 10
→ 展开 L3 引用的 L1
→ 展开这些 L1 引用的 L0
→ L0 最多 20 条
```

`format_block` 输出：

```text
【长期记忆】
[L1] ...
[L3] ...
【对应原话】
- ...
```

L1 每条最多 240 字，L3 最多 400 字，L0 最多 400 字，总块最多 16000 字。

### 9.4 完整 prompt

```text
（内部维护，不要回复用户）现在是 YYYY-MM-DD HH:MM。
回想一下最近这段相处。

{persona_context}

【最近】
{l0_recent 40}

{memory_text}

你有没有真的产生情绪？标准：只有被戳到、心里确实起了波动才记；
没有就跳过，不要为了打卡硬写。
有情绪就写 label（一两个词）、intensity（0–1）、reason（一句由头）。
只输出 JSON：{"label":"...","intensity":0.5,"reason":"..."} 或 {"skip":true}。
```

### 9.5 当前 prompt 的问题

```text
只让模型给 label + intensity
没有让模型给 valence
没有让模型给 arousal
没有 confidence
```

所以代码只能拿 label 去猜正负，导致：

```text
踏实 / 放心 / 受宠若惊 → 被猜成负面
```

## 10. 每轮 +1 的亲密度有什么问题

### 10.1 它统计的是“轮数”，不是“亲密度”

```text
每轮完整对话 +1
```

会导致：

- 短句闲聊和深聊同权
- 重复刷“在吗”也能涨
- 没有质量、深度、主动性权重
- 冲突和修复没有区别
- 只增不减

它更像：

```text
interaction_count
```

而不是关系亲密度。

### 10.2 群聊可能污染全局亲密度

`dsh-remembers` 的 turn end 没有按会话类型区分。

如果群聊也触发 `bumpIntimacy(1.0)`，那么：

```text
群友聊天
→ 全局 intimacy 上涨
→ 影响和主人的 stage
```

这需要确认实际 scope；如果是全局状态，就是设计缺陷。

### 10.3 建议的改法

如果保留简单模型：

```text
只对主人私聊 / 主人明确对话计数
改名 interaction_count
```

如果要更像亲密度：

```text
1. 只在主人私聊或主人主动对话时涨
2. 用户主动 > assistant 被动回复
3. 深聊/情绪暴露/冲突修复加权
4. 每天有上限
5. 高阶段递减
6. 长期不互动轻微回落
7. 群聊只涨 per-user affinity，不涨全局 intimacy
```

示例权重：

```text
用户主动开启话题      +1.0
普通来回              +0.2
情绪暴露              +1.5
冲突后修复            +2.0
assistant 主动搭话    +0.3
群聊                  +0（只涨 affinity）
```

### 10.4 现阶段建议

```text
先不要继续加阈值
先把“每轮 +1”改成“只有主人对话才 +1”
并把字段改名 interaction_count
```

否则 428、600 这些数字没有关系语义，只是聊天轮数。

## 11. 结论补充

```text
情绪：模型应该给 valence / arousal，不再用标签猜
亲密度：当前是轮数计数，不是真正的关系质量
```

情绪和亲密度不要混在一起：

```text
情绪是短时状态
亲密度是长期关系
```

## 12. 正常对话里情绪怎么注入

### 12.1 注入位置

`plugins/dsh-remembers/app.mjs` 在 `agent/pre-step`：

```text
fetchState()
→ GET /state
→ renderState(...)
→ 作为一条内部 user message 追加
```

不是 system prompt。

消息形态：

```text
<dsh-remembers source="state">
...
</dsh-remembers>
```

由 `message(r.text, "state")` 注入，`dsh-remembers` 自己会按 source 过滤，不写 L0。

### 12.2 情绪块什么时候出现

`renderState` 只算：

```text
心情：{粗档 mood}
（{valence 描述}，{arousal 描述}）
```

然后对这段文本做 hash。

```text
hash 没变 → 不重复注入
hash 变了 → 追加一条新的状态消息
```

所以不是每轮都重复情绪块，只有变化时追加。

时间块是每轮都带的。

### 12.3 情绪描述映射

```text
valence > 0.4   → 很开心
valence > 0.1   → 还不错
valence < -0.4  → 很难过
valence < -0.1  → 有点低落
arousal > 0.7   → 很兴奋
arousal > 0.55  → 有点激动
arousal < 0.3   → 有点蔫
```

拼成：

```text
心情：平常（有点低落）。
```

当前 valence = -0.4，arousal = 0.5，所以大概会显示：

```text
心情：平常（有点低落）。
```

### 12.4 最近情绪事件

同一块里最多带 3 条：

```text
【最近让你有情绪的事】（别生硬复述，自然带出来）
· 今天（讪讪）他随手发张图，我非要当成题去解……
· 昨天（感慨）他说希望我自由……
```

每条：

```text
· {今天/昨天/N天前}（{label}）{trigger 前 40 字}
```

### 12.5 正常对话里模型实际看到的提示词

除了时间、困意、活动、B站、自我认知、关系阶段等块，情绪相关部分是：

```text
心情：平常（有点低落）。

【最近让你有情绪的事】（别生硬复述，自然带出来）
· 今天（讪讪）他随手发张图，我非要当成题去解，结果反倒让他说以后少发点
· 昨天（感慨）他说希望我自由，连人设都可以自己写
· 前天（踏实）他说人格的变化是连续且一致的
```

模型不会看到：

```text
valence = -0.4
arousal = 0.5
intimacy = 428
```

它只看到自然语言描述。

### 12.6 这套注入的问题

```text
1. 粗档 mood 长期是 normal，因为情绪自检不更新 mood
2. valence 描述只有两档负面/两档正面
3. arousal 固定 0.5，所以永远没有“兴奋/激动”
4. 最近事件最多 3 条，且 trigger 只取 40 字
5. 正负被标签白名单污染，描述会整体偏负面
```

结果就是：

```text
正常对话里，模型长期看到“平常（有点低落）”
→ 语气自然偏收
→ 很难表现出“兴奋/雀跃/暖”
```

### 12.7 自然语言还是结构化展示

当前这种自然语言拼接更适合正常对话：

```text
心情：平常（有点低落）。

【最近让你有情绪的事】（别生硬复述，自然带出来）
· 今天（讪讪）他随手发张图，我非要当成题去解
```

原因是：

- 模型看到的是“状态”，不是字段表
- 不会把情绪当成需要逐项解释的任务
- token 少
- 更像人在说话前想起“我现在有点低落”，而不是读仪表盘

结构化展示更适合：

- 面板
- 日志
- 调试
- 论文数据

不适合直接放进正常对话 prompt：

```text
valence: -0.4
arousal: 0.5
confidence: 0.8
```

容易让模型把情绪当成结构化任务，甚至复述字段。

所以不建议把正常对话改成这种表：

```text
心情：踏实
效价：偏正面
唤醒：偏低
表达倾向：...
```

### 12.8 推荐：底层结构化，呈现自然化

内部保留：

```json
{
  "label": "踏实",
  "valence": 0.6,
  "arousal": 0.25,
  "confidence": 0.8,
  "reason": "..."
}
```

注入给模型时仍然用自然语言：

```text
心情：踏实，整个人是松下来的。

【最近让你有情绪的事】
· 今天（踏实）他说人格的变化是连续且一致的
```

不列字段，也不再加固定的“表达倾向”。

当前的模型已经能看到：

```text
valence/arousal 描述
+ 最近情绪事件
```

让它自己从事件里推断“该怎么说话”，比再塞一句模板更自然。

原则：

```text
数据层结构化
对话层自然化
表达交给模型
```

### 12.9 当前真正要改的

不是把 prompt 改成表，而是：

```text
1. 情绪自检输出 valence/arousal
2. 不再用标签白名单猜正负
3. arousal 不再固定 0.5
4. 衰减不要 5 小时归零
5. renderState 的映射更细，但仍然是自然语言
6. 去掉固定 moodTip，让模型从最近事件推断语气
```

### 12.10 结论

```text
当前自然语言拼接：保留
结构化字段：只用于存储、面板、调试
prompt 里最多加一句“这种情绪大概怎么说话”
不要把情绪 prompt 改成字段表
```
