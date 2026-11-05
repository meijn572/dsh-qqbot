# 原始数据说明

## 位置

```text
D:\QQBot\dshbot\data\raw\YYYY-MM-DD\
```

不进 git。

## 每天归档

bridge 每天 04:00 自动跑一次；也可以手动：

```bash
python scripts/archive_observations.py
```

指定日期：

```bash
python scripts/archive_observations.py --date 2026-11-05
```

## 文件

| 文件 | 内容 |
| --- | --- |
| `l0.jsonl` | 原话 |
| `l1.jsonl` | 事实 |
| `l2.jsonl` | 画像 |
| `l3.jsonl` | 事件 |
| `l4.jsonl` | 规矩 |
| `persona.json` | 当时的核心设定 / 自我认知 / 用户画像 |
| `review-proposals.json` | 当时待确认/历史候选 |
| `manifest.json` | git commit、导出时间、各层数量 |

## 隐私

- 原始数据只留本地
- 论文、公开仓库只放脱敏样例和汇总指标
- QQ 号、昵称、私聊内容在导出后仍需脱敏
- 不把 `memories.db` 原文件交上去

## 为什么按天导出

- 数据库会继续增长，后面无法还原“当时看到的是什么”
- 人格/候选会变化，需要时间切片
- 观察记录可以引用具体日期，不用靠回忆
