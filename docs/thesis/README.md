# 论文素材积累

题目还没定。当前只积累原始数据和观察，不提前锁定研究问题。

## 现在保留什么

```text
data/raw/YYYY-MM-DD/     每天导出的原始数据（本地，不进 git）
docs/thesis/observations.md  观察记录
docs/thesis/decisions.md     设计决策
docs/thesis/data.md          数据说明与隐私
```

## 导出

```bash
python scripts/archive_observations.py
```

可选指定日期：

```bash
python scripts/archive_observations.py --date 2026-11-05
```

导出内容：

- L0–L4 原始记录
- 当前 persona
- 复盘候选
- 当天 manifest（git commit、数量、字数）

## 原则

- 先积累，不急着定题
- 原始数据只留本地
- 论文/公开仓库只放匿名化样例和汇总指标
- 失败、返工、纠正和成功一样重要
