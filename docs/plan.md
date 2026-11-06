# 当前改动计划

状态：进行中。

最后更新：2026-11-07。

## 1. 已完成

```text
L2 旧用户画像：备份、迁移到 persona、清空
L4 旧规矩：备份、迁移到 persona important、清空
L4 历史核心记忆：4 条，source_status = legacy
B 站历史 L3：57 条迁到 activity_log
B 站新数据：走 activity，不再写 memory
抽取器：只抽 L1 / L3
L1 / L3：evidence 匹配 L0，写 source_ids
source_status：verified / unverified / batch / legacy
日记：情绪事件 + L0 窗口 + L3 旧记忆
情绪：5 分钟空闲复盘
面板：L4 核心记忆可见，L2 按钮移除
```

## 2. 正在进行

```text
L2 判断层：
  文档已定
  代码未接
  L2 只装判断/假设，不装事实

L3 事件线程：
  文档已定
  代码未接
  L3 可跨段/跨天，有 open / closed / dormant

提取时机：
  文档已改为按会话段
  代码仍是按条数/15 分钟
```

## 3. 下一步

### P1 L2 判断层

```text
L2 从 L0 + L1 生成
带 confidence
带 basis / derived_from
默认 hypothesis
7–30 天
不直接当事实注入
```

### P2 L3 事件线程

```text
每段结束：
  续写 open L3
  或新建 L3
  closed 后不再续写

字段：
  title / aliases
  status
  opened_at / last_seen_at / closed_at
  summary
  source_ids / derived_from
```

### P3 提取时机

```text
按最后一条消息后空闲 5 分钟切段
一段可产出多条 L1
L2 跟在 L1 后
L3 根据事件线程续写/新建
不再按 6 条 L1 切
```

### P4 L4 自动提升

```text
每天 04:00
输入：前一天 closed L3 + L0
输出：0–2 条核心记忆
带 derived_from
```

### P5 来源字段

```text
source_ids = 精确 L0 证据
derived_from = L1/L2/L3 输入
```

当前只实现了 `source_ids`，`derived_from` 未加列。

### P6 提取规则细节

```text
L1 只装事实，不装“近况”
max_facts 6 → 动态/12
L1 半衰期 30 天 → 180 天
UPDATE 时合并 source_ids
删掉 keywords 里的「情绪:xxx」
```

## 4. 待验证

```text
23:00 日记是否按新输入生成
L1/L3 新数据的 source_status 是否为 verified
L2 判断层尚未实现
L3 事件线程尚未实现
L4 自动提升尚未实现
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
- [记忆分层](memory-layers.md)
- [提取规则](extraction-rules.md)
- [日记](diary.md)
- [情绪分层](emotion-layers.md)
