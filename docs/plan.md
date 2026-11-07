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
词库：lexicon_meta 加入工具速查；learn_word 同步写词库
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
L2 判断层：
  文档已定
  代码未接
  L2 只装判断/假设，不装事实

真会话验证：
  事件线程跨段续写
  5 分钟分段是否切得自然
  open 索引是否足够
```

## 3. 下一步

### P1 L2 判断层（可选）

```text
如果 L1 不吸收推测，才需要 L2
L2 只装推断，不装主人明说的感受
L2 从 L0 + L1 生成
带 confidence
带 basis（memory_links）
默认 hypothesis
7–30 天
不直接当事实注入
```

不急，先看 L1 够不够用。

### P2 真会话验证

```text
牙疼/看牙这种跨天事件
是否续写同一条 open L3
是否在“没事了”时 closed
```

### P3 来源

```text
evidence 已改为：
  输入 L0/L1/L2/L3 统一编号
  模型输出 source_refs
  代码按 ref 映射 tier/id
  ref 无效才回退单条原话匹配
```

已实现 ref 优先。

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
