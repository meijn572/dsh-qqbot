# 观察记录

只记原始观察，不急着上升成结论。

建议格式：

```text
## YYYY-MM-DD
### 场景
### 看到什么
### 为什么意外
### 证据
### 可以往哪个方向想
```

---

## 2026-11-04：KPL 对话里先猜后查

### 场景

主人发表情包，提到比赛；模型先回“是翻盘了吧”，被纠正后才去查。

### 看到什么

- 对实时比分/赛程先给猜测
- 被指出后才搜索
- 搜索后能给出准确结果和来源

### 为什么意外

模型不是没有搜索工具，而是没有先查的默认动作。

### 证据

bridge.log 22:15–22:17；L0 对话。

### 可以往哪个方向想

- “不确定先查”是判断层规则，不是接口
- 需要区分“闲聊接话”和“事实断言”
- 可以比较：有这条规则 vs 没有时的硬猜率

---

## 2026-11-04：表情标签被自动清洗/路径重复

### 场景

用户手动给表情写“奶龙”，模型写入后标签消失；同一张图出现两条索引。

### 看到什么

- 自动清洗把旧标签截掉
- Windows `\` 与 `/` 被当成两个文件
- 模型写入没有先读旧语义

### 为什么意外

不是模型“覆盖”，是写入层和清洗规则共同造成的。

### 证据

stickers/index.json 重复条目；bridge.log 表情写入记录。

### 可以往哪个方向想

- 结构化 label/facets 是否比 tags 更稳
- 写入前展示旧语义是否减少信息丢失
- 路径规范化属于工程细节，但会直接影响数据质量

---

## 2026-11-05：concept 层被删除

### 场景

最初给表情/词库/记忆设计了 `concept:` 统一实体层。

### 看到什么

- 查询实际只靠 tags/name/caption
- 没有跨库聚合
- concept 成了额外维护成本

### 为什么意外

概念层在架构上“看起来正确”，但没有真实查询依赖。

### 证据

`qqbot/domains/concepts.py` 删除；相关字段清空。

### 可以往哪个方向想

- 结构化不等于有价值
- 论文里“失败/删除的设计”可以作为负结果
- 先问查询路径，再决定实体层

---

## 2026-11-05：角色卡与记忆服务人格不是同一个源

### 场景

面板/文件里看到的角色卡，和实际注入的 `constitution` 不是同一份。

### 看到什么

- 角色卡只是归档
- 真正生效的是记忆服务 `constitution`
- 修改角色卡不会改变说话

### 为什么意外

文件名和内容都像“人格源”，但实际注入链不同。

### 证据

`persona-roles/roles/小肥鱼.md` 删除；`/persona` 生效。

### 可以往哪个方向想

- 多源人格会造成排障和实验污染
- 论文系统设计里必须写清单一来源
- 需要一个人格写入权限矩阵

---

## 2026-11-05：来源提示过度

### 场景

查资料后每次都附来源链接，用户明确说不需要每次都贴。

### 看到什么

工具说明要求引用 URL，模型把它当固定输出格式。

### 为什么意外

不是人格提示词，而是工具级指令在塑造输出。

### 可以往哪个方向想

- 工具说明也是提示词
- “给事实”与“给输出格式”要分开
- 可以比较：默认引用 vs 仅在用户要求时引用

---

## 2026-11-06：推理语言、推理强度和角色语气

### 场景

讨论推理过程用中文还是英文、是否影响说话风格；顺带查了当前鱼会话的推理设置。

### 看到什么

当前 QQ 鱼会话的 request header：

```text
provider: deepseek-official
model: deepseek-flash
reasoningEffort: high
```

当前没有显式控制推理语言，也没有在 reasoning 开头注入角色风格。

外部实践里有一种说法：

- 在 reasoning 开头注入人格/风格种子
- 后续不重复注入
- 模型会沿这个方向继续推理
- 最终回答更有角色味

有人把这种方法叫 `reasoning intro` / `reasoning scaffold`。

### 为什么意外

如果风格种子能影响 reasoning 的“思考方式”，而不只是最终措辞，那就不是简单的提示词后缀，而是对推理过程本身的诱导。

但这也可能只是模型对开头 token 的自回归延续，不保证长期稳定。

### 证据

- 当前 request header：`reasoningEffort: high`
- [reasoning intro 实践文章](https://zenn.dev/cardy0828/articles/reasoning-intro-persona-control)
- 该实践基于 llama.cpp 的 draft PR，不是标准 API；作者也说明没有统计基准

### 可以往哪个方向想

- 区分三种东西：
  - System Prompt 里的语气
  - reasoning 开头的风格种子
  - 最终回答的语言/口吻
- 比较：
  - reasoning high vs medium
  - 有风格种子 vs 无风格种子
  - 中文推理 vs 英文推理
- 观察指标：
  - 角色一致性
  - 自然度/人味
  - 事实正确性
  - 是否出现语气泄漏或过度扮演
- 当前 DSH / DeepSeek provider 是否支持 reasoning 前缀注入，需要单独确认；不能把“system prompt 写喵”当成同一件事。

### 外部检索

找到几类相关工作，但没有完全等同于“reasoning 开头只注入一个喵”的受控研究。

1. [System Prompts as Runtime Priors](https://zenodo.org/records/20835691)
   - 预印本，认为 system prompt 像运行时先验，会影响模型后续的解释状态和行为稳定性。
   - 不是专门研究 reasoning 语言或角色语气，且是预印本，不能当强结论。

2. [Persona is a Double-Edged Sword](https://aclanthology.org/2025.findings-ijcnlp.51/)
   - 研究 role-play persona 对 zero-shot reasoning 的影响。
   - 结论不是“加人格一定更好”：persona 可能提升，也可能损害推理；数据集对齐的 persona 不一定稳定。
   - 支持“system prompt / persona 会影响推理”，但不支持“加了角色就一定更有味道”。

3. [What Effort Level Should I Choose?](https://arxiv.org/abs/2610.34491)
   - 研究 reasoning effort 的经济学。
   - 更高 effort 不保证 instance-level 更好，可能在某些低 effort 能做的题上失败，成本可高很多。
   - 高 effort 还会改变 agent 的行为轨迹，比如更多自检和搜索。

4. [GLM 5.3 roleplay thinking mode 讨论](https://bestairoleplay.com/glm-5-3-for-ai-roleplay-should-you-enable-thinking-mode-or-not/)
   - 社区经验，不是论文。
   - 支持方认为 thinking 能提升角色准确性和连续性；反对方认为会变慢、更保守、减少即兴。
   - 可作为“高推理可能让闲聊变正式”的旁证，但不能当实验证据。

5. [reasoning intro 实践](https://zenn.dev/cardy0828/articles/reasoning-intro-persona-control)
   - 最接近“在 reasoning 开头注入人格/风格”的实践。
   - 依赖 llama.cpp 的 draft PR，不是标准 API，也没有统计基准。

目前没有找到：

```text
在 DeepSeek 官方 API 上
只对 reasoning 开头注入一个“喵”
并做严格控制实验
```

所以当前可做的是：

```text
system prompt 风格对比
reasoning high / low / off 对比
```

不能声称复现 reasoning prefix 注入。

### 当前操作

2026-11-06：

```text
当前鱼会话：session/selectModel → reasoningEffort=low
qqbot2 默认 model：deepseek-flash, reasoningEffort=low
```

当前会话的 `lastUsed` 仍是 high，`next` 已变 low；下一条消息开始用 low。

system prompt 风格实验暂时不做。


