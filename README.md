# Herodotus

> 本地、**按人格隔离**、供多个 AI 客户端共同存取的**记忆与知识服务**。
>
> 命名取自希罗多德（「历史之父」）：其《历史》开篇即「使已发生之事不致因时间而湮没，使希腊人与异邦人的伟大功业不致失其荣光」。服务名 **Clio** 取自他首先召唤的缪斯、卷一之名。
>
> **文档标记**（全仓库统一）：**✅ 已定**（经代码/实验验证，或由负责人确认）· **🟡 倾向**（有倾向，尚未落地）· **🔍 待调研**（有明确调研对象）· **❓ 未定**（尚无结论）。
> 标记跟着事实走：任何一条都可能因为推进中发现问题而改标，**包括已落地的实现**。未标注处默认 **❓ 未定**，不可当作约束。

## 这份仓库是什么

Herodotus 是一个 **umbrella 仓库**：本身只承载**文档与集成**，实现分布在三个独立组件仓库中（以 git submodule 组织）。

| 组件 | 语言 | 职责 |
| --- | --- | --- |
| [`clio`](clio/) | C++23 | 引擎库 `herodotus`（库名 ❓ 未定） + 守护进程 `clio`：账本、索引、记忆库、知识库、蒸馏、召回、人格、治理、HTTP/MCP 服务 |
| [`dsh-herodotus`](dsh-herodotus/) | TypeScript (Cordis) | DSH 客户端插件：捕获会话事件、消息侧注入召回、注册记忆工具 |
| [`astrbot_plugin_herodotus`](astrbot_plugin_herodotus/) | Python (Star) | AstrBot 客户端插件：捕获消息事件、`on_llm_request` 注入召回、注册记忆工具 |

三者通过 **`docs/PROTOCOL.md`** 定义的 HTTP + MCP 契约通信。**协议是跨组件的单一事实源**——改协议先改它，两个客户端据此实现。

## 目录地图

| 路径 | 放什么 |
| --- | --- |
| `docs/` | 全部跨组件文档（索引见下方「文档」表） |
| `scripts/` | 构建 / 起停 / 冒烟 / 评测脚本（见 [`scripts/README.md`](scripts/README.md)） |
| `clio/` | submodule：C++ 引擎 + 守护进程（**唯一存储写者**） |
| `dsh-herodotus/` | submodule：DSH 客户端插件 |
| `astrbot_plugin_herodotus/` | submodule：AstrBot 客户端插件 |
| `pylai/` | submodule：HTTP 底座，`clio` 的依赖 |
| `.reference/` | 参考实现的实体 clone（不入库） |

本仓特有的约定（边界、索引位置、目录 README、变更记载、环境不入库）见 [`AGENTS.md`](AGENTS.md)；协作与提交的通用纪律不在此重复。

## 怎么跑

本仓**不固化编译器与路径**：工具链与预设名属本机配置，仓库只保证“用对应组件的 preset 构建”。

1. **构建引擎**：见 [`clio/README.md`](clio/README.md) 的「构建与工具链」
2. **跑测试**：用 test preset（`ctest --preset <你的 test preset>`）。裸 `ctest --test-dir …` 缺工具链的运行时 DLL 路径，会以 `0xc0000135` 全部失败。
3. **验收 / 冒烟 / 评测**：见 [`scripts/README.md`](scripts/README.md)
4. **客户端**：`dsh-herodotus` / `astrbot_plugin_herodotus` 各自的 README

服务端口与协议见 [`docs/PROTOCOL.md`](docs/PROTOCOL.md)。

## 文档

| 文档 | 只回答 |
| --- | --- |
| [`docs/PLAN.md`](docs/PLAN.md) | **为什么做 + 做到哪**：目标与成功标准、技术选型、里程碑与验收门、决策清单（含状态）、风险 |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | **怎么搭**：术语、进程边界、不变量（唯一编号处）、存储与表结构、数据流、失败模式 |
| [`docs/PROTOCOL.md`](docs/PROTOCOL.md) | **对外契约**：HTTP 端点、MCP 工具面、并发语义、客户端实现要求 |
| [`docs/REFERENCES.md`](docs/REFERENCES.md) | **参考了什么、哪里刻意不同**：每个来源的借鉴点与偏离理由（不是移植清单） |
| [`docs/changelog.md`](docs/changelog.md) | **改了什么**：跨组件落地的变更与复现方式 |

## 许可

本仓库与 `clio` 以 **GPL-3.0** 发布；归属声明见 [`NOTICE`](NOTICE)。
