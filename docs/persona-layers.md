# 人格分层

人格不是一个自由文本大块，而是几层不同生命周期的数据。

## 1. 层

```text
AGENTS.md              接口契约
核心设定               稳定人格
自我认知               动态叙事
用户画像               关于主人的事实
重要约定               长期承诺
L0–L4                  经历与事实
```

### AGENTS

只放：

- QQ 消息条数
- 群聊昵称
- `[[meme:...]]`
- `[[sticker:...]]`
- 输出格式

不放人格、行为政策、画像。

### 核心设定

固定七块：

```text
身份
性格
判断
说话
关系
边界
约定
```

只允许面板半自动维护：

```text
人工编辑
+ 风格提议
+ 复盘候选
+ 人工确认
```

模型没有写核心设定的工具。

`<!-- important:begin -->` / `<!-- important:end -->` 必须保留，服务端靠它同步 `important.md`。

### 自我认知

只写：

```text
changes
learned
open_questions
```

服务端渲染为：

```text
## 最近的变化
## 我学到的
## 还没想清
```

不允许规则、用户事实、工具说明、消息格式。

### 用户画像

只写：

```text
stable_facts
preferences
values
interaction
boundaries
```

服务端渲染为固定 section。不允许“回答时应该……”这类指令。

### 画像里的偏好只放长期

```text
长期稳定：一直如此 / 反复出现 / 明确说过「我就是这样」
→ preferences

短时：最近 / 这几天 / 今天 / 这一阵才有的
→ 留在最近对话 / 当前段的 L1
→ 不要求跨段总结
→ 不写进画像
```

例子：

```text
主人一直不吃香菜
→ 画像 preferences

主人最近不想吃辣
→ 最近对话 / 当前段 L1，不进画像

主人今天不想出门
→ 当次对话，不进画像

主人说「我这个人就是怕麻烦」
→ 画像 preferences
```

短时偏好不是不重要，是它会过期。

L1 是“一小段对话”的总结，不适合硬承担“跨好几天的短期偏好”。
它只在该段里出现过就记；没出现就不强求。

画像每 2 天重写一次，把短时偏好写进去，过几天就会变成假的长期画像。

### 重要约定

只追加列表。不混进核心设定和画像。

### 记忆

L0–L4 仍然只负责经历和事实，不承担人格规则。新的分层见 [记忆分层](memory-layers.md)。

## 2. 写入路径

| 层 | 写入接口 | 模型权限 |
| --- | --- | --- |
| 核心设定 | 面板 `/persona` | 无 |
| 自我认知 | `/persona/self` + `persona_update` | 只能写三块 |
| 用户画像 | `/persona/user` | 只能写五块 |
| 重要约定 | `/persona/important` | 只能追加 |
| 记忆 | 现有 ingest/extract | 只能写记忆 |

## 3. 校验

`service/persona/schema.py`：

- 只允许固定字段
- 数组 + 字符串
- 单条长度限制
- 禁止跨层关键词
- 服务端渲染，不信任模型输出的标题

核心设定由 `scripts/check_persona_boundaries.py` 做只读检查。

## 4. 边界检查

```bash
python scripts/check_persona_boundaries.py
```

检查：

- 核心设定七个 section
- important 块完整
- 自我认知没有规则/事实
- 画像没有指令/人格
- AGENTS 没有人格/行为政策

## 5. 流程输入不变

自我演化、画像生成、风格提议的输入仍然使用原来的上下文，只改输出结构和校验。

## 6. 复盘

当前实际周期：

| 复盘 | 周期 | 模式 | 写哪 |
| --- | --- | --- | --- |
| 自我认知增量 | 每日 07:00 | 服务端自动 | `self_model` 的 changes |
| 自我认知整理 | 暂无独立任务 | — | 目前只做增量，不做整篇重写 |
| 用户画像 | 每 2 天 07:00 | 自动 | `user_profile` 五块 |
| 说话风格 | 每 3 天 07:00 | 半自动 | 核心 `说话` |
| 人格复盘 | 每 30 天 07:00 | 半自动 | `判断` / `关系` / `约定` 候选 |
| 重要的事 | 每日 / 工具触发 | 半自动 | 候选，人工应用 |
| 性格 / 身份 | 90 天 | 手写 | 核心 |
| 边界 | 事件触发 | 手写 | 核心 |

自我认知增量输入最近 24 小时的 L0；没有素材就跳过。

人格复盘输入：

```text
constitution
self_model
user_profile
recent_dialogue(30)
collect(L1=50, L3=30, L0=50)
最近 30 天、每个 target 最近 5 条候选
```

候选存于：

```text
persona-roles/state/review-proposals.json
```

状态：

```text
pending / applied / rejected
```

## 7. 参考

- [Character Card V2](https://github.com/malfoyslastname/character-card-spec-v2/blob/main/spec_v2.md)：角色描述、示例、系统指令、世界书分开
- [Letta Memory Blocks](https://docs.letta.com/v1-sdk/memory/memory-blocks/)：system instructions 与 memory blocks 分开
