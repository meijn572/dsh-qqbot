# 当前改动计划

状态：进行中。

最后更新：2026-11-07。

## 1. 已完成

```text
L2 旧用户画像：备份、迁移到 persona、清空
L4 旧规矩：备份、迁移到 persona important、清空
L4 历史核心记忆：2 条，source_status = legacy
L4 非核心：2 条降级为 L3 standalone
B 站历史 L3：57 条迁到 activity_log
B 站新数据：走 activity，不再写 memory
抽取器：只抽 L1 / L3
L1 / L3：evidence 匹配 L0，写 source_ids
evidence：ref 优先，原话兜底
source_status：verified / unverified / batch / legacy
L1：会话段总结（可多条，互动允许）；max_facts 20
L1：30 天后标 stale，不删除；默认不召回
L3：open 超过 14 天标 dormant，不删除
L3：标题支持模糊匹配
旧 L3：16 条旧流水账 archived，拆成 41 条事件线程
旧 L1：保留 legacy，不重算 source_ids
旧提示词审计：L1 抽取只产 L1；上下文标签自然语言；batch 不再带 L4
说话方向：L1 prompt 明确「主人问我 / 我问主人」；蛋家军已修正
词库：只剩 learn_word 一个写工具，同时写 slang + lexicon
词库自动流程：07:00 每日词库复盘已接；群黑话 22:00 仍关闭
复盘合并：不合并；只新增词库复盘
主动说：已统一到 proactive（完整人格 + L0/L1/L3 + activity）；活跃 9:00–次日 2:00
B站：autonomy 只负责看，分享由 proactive 决定（已接）
B站感悟：已接（activity 存 summary/insight，L3 存 insight + 类型 + 短上下文）
关系系统：v3 已上线（L3 文本影响 + 模型自由写关系，无固定阶段）
短时偏好：明说→L1，推断→L2，长期→画像；L2 第一版已接
L2：字段/生成/confirmed 升 L1/面板已接
L3：输入改为 L0 + L1 + L2
L1：只写确定事实，推测词过滤
人格旧提示词：EVOLVE 不再写「我发现自己」；无变化输出 SKIP
自我认知：去重；set_emotion 工具提示改成 valence/arousal
人格旧字段：self_image / identity 已从代码、面板、数据库删除
自我认知复盘：从每 20 轮改为每天 07:00
其他复盘：画像 / 风格 / 人格 / 核心记忆统一 07:00
旧 episode 链路：插件默认关闭
便签旧作者：已统一为「洄」
UPDATE：合并 source_ids
去掉 keywords 里的「情绪:xxx」
memory_links：建表，L1/L3 写依赖边
L3 事件线程：thread_* 字段、open/closed/dormant
按会话段提取：空闲 5 分钟 + 30 分钟 / 80 条安全边界
open L3：全部进索引，最多 8 条
open 查询工具：get_open_thread / list_open_threads
L4 复盘：每 3 天，closed / standalone L3 → 0–2 条核心记忆
日记：情绪事件 + L0 窗口 + L3 旧记忆
情绪：5 分钟空闲复盘
面板：L4 核心记忆可见，L2 按钮移除
小本子：open L3 / 便签 / 任务 / 日记
```

## 2. 正在进行

```text
真会话验证：
  事件线程跨段续写
  5 分钟分段是否切得自然
  open 索引是否足够
```

L2 代码未接，待做清单见下。

## 3. 改动待做清单

### P0 L1 严格确定

```text
L1 只写已经确定发生的事
不写“可能 / 也许 / 大概 / 我猜”
推测一律去 L2
不确定就留空，不要补
每条的 source_refs 必须能对上原话
```

需要改：

```text
EXTRACT_SYSTEM：明确“只写确定事实”
L1 输出校验：含推测词的不收，或要求模型重写
测试：确定性 + 不补人物
```

### P1 L2 恢复

```text
新增字段：
  confidence
  expires_at
  status
  promoted_to
  basis

状态：
  hypothesis
  promoted
  rejected
  expired
  superseded

写入：
  从 L0 + L1 生成
  只写推断，不写明说事实

召回：
  只召回 hypothesis
  且未过期
  高门槛

注入：
  带“可能 / 我猜”
  不当事实

确认：
  模型复盘输出 confirmed
  → 同一事务创建 L1
  → L2.status = promoted
  → L2.promoted_to = L1.id
  → 失败回滚，保持 hypothesis

面板：
  L2 列表 / 状态 / confidence / 过期时间
```

### P2 L3 同时吃 L1 + L2

```text
plan_threads 输入：
  L0 原话
  L1 确定事实
  L2 判断

L3 引用 L2 时：
  link.role = judgment
  不能把 L2 当事实抄进 summary

L3 prompt：
  L1 是事实
  L2 是判断
  只有 L2 时，L3 写成“我猜 / 可能”
  有 L1 支撑时才写确定

测试：
  L2 参与建 L3
  L3 的 source_refs 能指到 L2
```

### P3 其他

```text
L2 晋级要幂等：同一条 L2 不能重复生成 L1
L1 升级后，原 L2 不再召回
L2 过期任务：每天 07:00 扫一次
L2 面板筛选：hypothesis / promoted / rejected / expired
文档同步：memory-layers / persona-layers / plan
```

### 暂不做

```text
不恢复 L2 用户画像
不单独加“短期偏好层”
不让 L2 直接升 L4
不让 L1 吸收推测
```

### 顺序

```text
1. L1 严格确定
2. L2 字段 + 状态 + 召回
3. L2 confirmed 自动升 L1
4. L3 输入加 L2
5. 面板 + 测试
```

## 4. 待验证

```text
23:00 日记是否按新输入生成
L1/L3 新数据的 source_status 是否为 verified
旧 L3 的 thread_status 是否为 legacy
memory_links 是否按预期写入
L4 复盘是否只在 3 天后触发
```

## 5. 不在当前范围

```text
图数据库
自动 self-editing
把 B 站塞回 memory
恢复 L2 用户画像
```

## 6. 相关文档

- [文档地图](README.md)
- [未解决问题](open-questions.md)
- [记忆分层](memory-layers.md)
- [提取规则](extraction-rules.md)
- [日记](diary.md)
- [情绪分层](emotion-layers.md)
