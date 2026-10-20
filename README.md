# Herodotus

> 本地、**按人格隔离**、供多个 AI 客户端共同存取的**记忆与知识服务**。
>
> 命名取自希罗多德（「历史之父」）：其《历史》开篇即「使已发生之事不致因时间而湮没，使希腊人与异邦人的伟大功业不致失其荣光」。服务名 **Clio** 取自他首先召唤的缪斯、卷一之名。

> **决策状态以 [`docs/PLAN.md`](docs/PLAN.md) 为准**：标 **【定】** 者已确认；**未标注的默认【待考证】**，不可当作约束。

## 这份仓库是什么

Herodotus 是一个 **umbrella 仓库**：本身只承载**文档与集成**，实现分布在三个独立组件仓库中（以 git submodule 组织）。

| 组件 | 语言 | 职责 |
| --- | --- | --- |
| [`clio`](clio/) | C++23 | 引擎库 `herodotus`（库名【待考证】） + 守护进程 `clio`：账本、索引、记忆库、知识库、蒸馏、召回、人格、治理、HTTP/MCP 服务 |
| [`dsh-herodotus`](dsh-herodotus/) | TypeScript (Cordis) | DSH 客户端插件：捕获会话事件、消息侧注入召回、注册记忆工具 |
| [`astrbot_plugin_herodotus`](astrbot_plugin_herodotus/) | Python (Star) | AstrBot 客户端插件：捕获消息事件、`on_llm_request` 注入召回、注册记忆工具 |

三者通过 **`docs/PROTOCOL.md`** 定义的 HTTP + MCP 契约通信。**协议是跨组件的单一事实源**——改协议先改它，两个客户端据此实现。

## 文档

| 文档 | 内容 |
| --- | --- |
| [`docs/PLAN.md`](docs/PLAN.md) | **开发计划**：目标、成功标准、架构、技术选型、schema、里程碑与验收门、开放决策 |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | 进程边界、数据流、**七条不变量**、失败模式与对策 |
| [`docs/PROTOCOL.md`](docs/PROTOCOL.md) | HTTP 端点与 MCP 工具契约 |
| [`docs/REFERENCE.md`](docs/REFERENCE.md) | 参考实现与数据集清单：去哪找什么、移植优先级；实体在 `.reference/`（不入库） |

## 当前状态

**P0 阶段**：`clio` 骨架已落地并可构建运行（协议版本常量 / SQLite+FTS5 账本自检 / pylai HTTP 服务 + `/health` / 守护进程入口），`scripts/` 提供构建·起停·冒烟；蒸馏与中文分词 spike、黄金语料集待推进。

| 仓库 | 远程 | 状态 |
| --- | --- | --- |
| `herodotus` | `github.com:Joker-Principal/herodotus.git` | 本仓库（umbrella） |
| `clio` | `github.com:Joker-Principal/clio.git` | P0 骨架（可构建） |
| `dsh-herodotus` | `github.com:Joker-Principal/dsh-herodotus.git` | 目录骨架 |
| `astrbot_plugin_herodotus` | `github.com:Joker-Principal/astrbot_plugin_herodotus.git` | 目录骨架 |

## submodule 工作流

三个组件是独立仓库，主仓库只记录「一套已知可用的组合」——例如 `clio v0.3.0 + dsh-herodotus v0.1.0 + astrbot_plugin_herodotus v0.1.0`。这对本项目尤为重要：协议演进时，**客户端与引擎必须版本匹配**。

**改组件**：

```bash
# 1. 在组件仓库里开发
cd clio
# ... 编辑 ...
git add -A && git commit -m "feat: ..."
git push

# 2. 回主仓库 bump 指针
cd ..
git add clio
git commit -m "bump clio"
```

**克隆**：

```bash
git clone --recurse-submodules git@github.com:Joker-Principal/herodotus.git
# 已克隆过的：
git submodule update --init --recursive
```

## 两条硬约束【定】

1. **中文检索不可妥协**——关键词腿用 `cppjieba 词 ∪ CJK 二元组` 的有序去重并集，其中**二元组是不可移除的召回底线**。
2. **动态召回绝不进系统提示词**——记忆走消息侧（DSH：消息侧 prepend；AstrBot：`extra_user_content_parts`），只有人格与画像等**稳定内容**才进系统提示词稳定区。破坏 prefix cache 的成本是 **7–20 倍**。

## 许可

本仓库与 `clio` 以 **GPL-3.0** 发布；归属声明见 [`NOTICE`](NOTICE)。

**发布物绝不捆绑任何模型**——嵌入/重排/蒸馏全部是**用户本机的可配置槽位**，默认值只是「本机当前选择」，不是依赖。
