# 主动说

状态：设计稿，未改代码。

## 1. 现在的问题

主动消息有两条路：

```text
autonomy      刷 B 站 → 自己决定分享 → 自己发
proactive     定时主动说 → 自己发
```

结果是：

```text
两个出口
两套频率
两套“没回怎么办”
B 站分享和普通主动容易撞
```

## 2. 统一后的分工

```text
autonomy   只负责看
activity   只负责记
proactive  唯一负责说
```

B 站不再自己发消息。

## 3. activity

加字段：

```sql
shared    INTEGER NOT NULL DEFAULT 0
shared_at REAL DEFAULT NULL
```

活动只记：

```text
kind=bili
detail=刷了「主题」《标题》
thought=当时想法
shared=0
```

共享后：

```text
shared=1
shared_at=时间
```

## 4. autonomy 只负责看

保留：

```text
选主题
看视频
读字幕 / 看画面 / 看评论
写 activity
更新兴趣
写日报
```

删除：

```text
share 判断
send_private
pending_shares
share_max_per_day
max_unanswered_shares
```

## 5. proactive 的输入

每次到点，组装：

```text
当前时间
最近对话（8 条以内）
最近可说的 activity（未 shared，最多 5 条）
上次主动说了什么
上次之后主人有没有回
```

候选示例：

```text
【最近可以说的】
[1] 今天 19:26
    刷了「基础科学停滞」《为什么基础科学很久没有重大突破了？》
    想法：最扎的一句是「不是科学停滞了，是人类大脑裸算科学的时代结束了」……

[2] 今天 18:50
    刷了「末日测人性」《在末日里，有哪些物品最受欢迎？》
    想法：黄金那条最反直觉……
```

## 6. Prompt

```text
（内部主动说，不要回复用户，不要调用工具。）

现在是 {HH:MM}。

最近你们聊过（只作参考，不要逐句复述）：
{最近 8 条对话}

【最近可以说的】
[1] {时间}
    刷了「{主题}」《{标题}》
    想法：{thought}

[2] ...

【上次主动说】
{上次内容 / 无}

规则：
- 你可以从上面的 activity 里挑一条，自然地说一两句。
- 也可以完全不提 activity，说自己想说的。
- 不要逐句复述 thought，像随口聊天。
- 如果选 activity，activity_id 填对应编号；如果不是，填 null。
- 不要重复上次主动说过的内容。
- 真没什么想说的，text 留空，activity_id 填 null。

只输出 JSON：
{"text":"想对主人说的话","activity_id":1或null}
```

## 7. 输出

```json
{
  "text": "今天刷到一个讲基础科学的，里面说不是科学停了，是我们那种裸算科学的方式到头了。听着有点凉。",
  "activity_id": 1
}
```

或者：

```json
{"text": "突然想起你昨天说的那件事，后来怎么样了？", "activity_id": null}
```

不说：

```json
{"text": "", "activity_id": null}
```

## 8. 后台处理

```text
text 为空 → 不发
activity_id 有效 → mark shared=1, shared_at=now
发送 → add_l0
更新 proactive state: last_sent, awaiting_reply=1
```

如果 `activity_id` 无效：

```text
当作 null，不标记
```

## 9. 一条没回就停

统一放在 proactive：

```text
上次主动说之后
主人没有回
→ 后续主动说全部跳过
```

主人回了：

```text
awaiting_reply=0
→ 下一次到点恢复
```

不再分 B 站一套、普通主动一套。

## 10. 频率

```text
proactive 自己的间隔：25–50 分钟
静默时段：0–8 点
```

B 站不再有“每天 3 条分享”限制。

如果一直没回：

```text
不再发
activity 继续攒
```

主人回了以后：

```text
下一轮可以从攒着的 activity 里挑
```

## 11. 和现有代码的对应

```text
activity_log       加 shared / shared_at
memory_core        查询未分享 activity
autonomy/round.py  删掉分享发送
bridge.proactive   改为读 activity + JSON 输出
proactive-state    加 awaiting_reply / last_sent
```

## 12. 迁移

```text
1. activity 加字段
2. autonomy 停止发送
3. proactive 读未分享 activity
4. 旧的 pending_shares / share_* 配置停用
5. 稳定后再删代码
```

## 13. 开放问题

```text
候选 activity 只看 B 站，还是所有 activity
最多 5 条够不够
activity 超过 24h 还要不要候选
模型说“别的”时，怎么避免和最近对话重复
一条没回就停，是否也适用于报告推送
```
