# 情绪与关系指标

状态：方案，未实现。

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
