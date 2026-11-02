# 公开与第三方依赖说明

本文说明项目定位、公开到 GitHub 时怎么写、以及第三方依赖/版权要注意什么。

> 不是法律意见。真正公开前，建议按下面清单逐项确认。

## 1. 项目定位

这个项目不是“从零写的完整 QQ 机器人框架”，而是：

> 基于 DSH 宿主，自建 QQ 桥、记忆/人格工作流，并编排现成 B 站工具的个人陪伴机器人。

更具体：

| 类型 | 内容 |
| --- | --- |
| 自己写 | `bridge.py`、`qqbot/domains/*`、`qqbot/clients/*`、面板、启动/观测脚本 |
| 自己改/维护 | 记忆服务的 hook、context、persona 格式、batch 控制；插件 hooks/tools 适配层 |
| 直接依赖 | DSH 宿主、SnowLuma/OneBot、`dsh-bili-scroll` 工具、DeepSeek/SiliconFlow |
| 不使用/已禁用 | `dsh-memewiki`、旧 AstrBot 链路（保留回退） |

注意：当前 GitHub 仓库主要包含 `bridge.py`、`qqbot/`、面板和文档。

`remembers-service` 和 `dsh-remembers` 插件源码在 `$DSH_HOME` 下，**不在当前仓库里**。

如果要把完整系统公开，需要单独决定是否把这两部分也放进来，并做同样的许可证检查。

## 2. GitHub 简介怎么写

### 短描述

中文：

> 基于 DSH 的 QQ 陪伴机器人：自建 QQ 桥、记忆/人格工作流，以及 B 站自主浏览。

English：

> A DSH-based QQ companion bot with a custom QQ bridge, memory/persona workflows, and Bilibili autonomy.

### 长描述

```markdown
一个跑在 DSH 上的 QQ 陪伴机器人。

包含：
- 自建 QQ ↔ DSH 桥：消息合并、群聊门控、主动说话、QQ 空间
- 记忆服务集成：L0-L4、召回、hook 写入、人格存储
- 人格工作流：复盘、画像、风格提议、重要的事、情绪自检
- B 站自主浏览工作流：选题、观看、判断、分享
- 自建只读面板

依赖：
- DSH（宿主）
- SnowLuma / OneBot（QQ 接入）
- dsh-bili-scroll（B 站工具）
- DeepSeek / SiliconFlow（模型）

说明：
- 本仓库不包含记忆服务、DSH 插件源码和运行数据
- 不含 QQ 号、群号、token、密钥、记忆库、日志
```

### Topics

```
dsh qqbot onebot snowluma memory persona bilibili chatbot
```

## 3. 当前仓库包含什么

会公开：

- `bridge.py`
- `qqbot/`
- `panel*.py`
- `web/`
- `scripts/`
- `tests/`
- `docs/`
- `README.md`
- `config.example.json`
- 启停/看门狗脚本

不会公开：

- `config.json`
- `secrets/`
- `runtime/`
- `logs/`
- `stickers/`
- `backups/`
- `archive/`
- 记忆数据库
- DSH 插件源码
- 记忆服务源码

## 4. 许可证现状

当前仓库没有 `LICENSE` 文件。

GitHub 上没有许可证默认是“保留所有权利”，别人可以看，但不能合法复制、修改、再分发。

如果想让别人复用，建议二选一：

- MIT：简单、宽松，适合个人项目
- Apache-2.0：宽松 + 专利条款，适合更正式的项目

如果只想让人看、不想让人复用，就不加许可证，并在 README 写清楚。

## 5. 第三方依赖

### dsh-remembers

- 包元数据：`license = MIT`
- 当前仓库不包含它的源码
- 如果以后把它的代码/修改版放进仓库：
  - 保留 MIT 许可证和版权声明
  - 标明哪些文件是修改过的

### dsh-bili-scroll

- 包元数据：`license = MIT`
- 仓库：`https://github.com/c1overzz/dsh-bili-scroll`
- 当前仓库只调用它的工具，不复制它的代码
- 如果以后复制代码，保留 MIT 声明

### SnowLuma

- `package.json` 写的是 `SEE LICENSE IN LICENSE`
- 目录里有 `EULA.md` / `PRIVACY.md`
- 这是 QQ 接入运行时，不是本仓库代码
- **不要**把 `node.exe`、`index.mjs`、native 文件打进本仓库
- 用户需要自行安装并接受它的 EULA

### DSH

- DSH 是宿主运行时，不是本仓库代码
- 不要把 `app.asar`、安装包、运行时二进制打进仓库
- 用户需要自行安装 DSH，并遵守其许可/服务条款

### 模型/API

- DeepSeek / SiliconFlow 的 API key 不进仓库
- 模型输出、人格文本是否可再分发，取决于服务条款和内容来源
- 不要把真实对话、记忆、日志当示例上传

### 人格/角色/表情包

- `大肥鱼` 的角色设定如果是自己写的，可以作为项目内容
- 不要上传来源不明的表情包、角色图、第三方 IP 素材
- 当前仓库的 `stickers/` 已被忽略

## 6. 公开前检查清单

- [ ] `git grep` 无 QQ 号、群号、session、token、密钥
- [ ] 无 `config.json`
- [ ] 无 `secrets/`
- [ ] 无 `runtime/`
- [ ] 无 `logs/`
- [ ] 无 `memories.db`
- [ ] 无 `stickers/` 第三方图片
- [ ] 无 `backups/`
- [ ] `config.example.json` 全是占位符
- [ ] README 写明“依赖外部 DSH/SnowLuma”
- [ ] 决定是否加 `LICENSE`
- [ ] 如果复制 MIT 代码，保留版权声明
- [ ] 不打包 DSH/SnowLuma 二进制

## 7. 建议的公开方式

如果只是想给人看架构和实现：

- 保持 private，发链接/加 collaborator
- 或者 public，但不加 LICENSE，README 写“仅供学习参考”

如果想让别人复用：

- 加 MIT 或 Apache-2.0
- 写 `THIRD_PARTY.md` 列依赖和许可证
- 不打包第三方运行时
- 不公开个人数据

## 8. 一句话结论

当前仓库公开**基本没有第三方代码版权问题**，因为：

- 不包含 DSH/SnowLuma 二进制
- 不包含 `dsh-remembers` / `dsh-bili-scroll` 源码
- 不包含记忆数据、日志、密钥

真正要注意的是：

1. 公开前确认没有个人信息
2. 决定自己代码的许可证
3. 如果以后把记忆服务/插件源码放进来，逐个核对 MIT/EULA
4. 不要打包 SnowLuma/DSH 运行时
