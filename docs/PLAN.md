# Herodotus · 开发计划

> **状态**：立项阶段。本文件是开发推进的主依据；实现代码分布在三个组件仓库中。
> **命名**：项目 **Herodotus**（希罗多德，「历史之父」）、服务 **Clio**（他序言后首先召唤的缪斯，卷一之名）。

**标记体系**（全仓库统一，图例定义见 [`../README.md`](../README.md)）：

| 标记 | 含义 |
| --- | --- |
| **✅ 已定** | 已由负责人确认，或已有代码 / 实验支撑，可据此实现 |
| **🟡 倾向** | 有明确倾向，尚未落地或尚未评估 |
| **🔍 待调研** | 有明确调研对象，结论待补 |
| **❓ 未定** | 尚无结论（未标注处默认此项） |

> 标记跟着事实走。**任何一条都可能因为推进中发现问题而被推翻，包括已落地的实现**——推翻时改标记、记原因即可。

---

## 1. 系统定位与成功标准

**一句话**：Herodotus 是一个**本地、按人格隔离、供多个 AI 客户端共同存取**的记忆与知识服务。

**目标**：让 DSH 能在本地建立和使用记忆；能在 DSH 里建立人格，人格也有独立的记忆。记忆与 AstrBot **按人格共享**；让 DSH 和 AstrBot 能建立和使用 **知识库**。

### 成功标准

| # | 标准 |
| --- | --- |
| S1 | DSH 中 A 会话陈述的事实，在 B 会话被自动召回并注入 |
| S2 | 建两个人格，其记忆**物理互不可见**，非仅靠查询过滤 |
| S3 | AstrBot 中陈述的事实，在 DSH 同一人格下可召回；反向亦成立 |
| S4 | 知识库可检索论文语料，结果**带可引用出处** |
| S5 | 注入**不破坏 prefix cache**（动态走消息侧，稳定才进系统提示词） |
| S6 | 服务不可用时，DSH 与 AstrBot **照常对话**，不阻塞、不报错 |
| S7 | 删掉索引库后可从账本**完整重建**，检索结果一致 |
| S8 | 嵌入 / 重排 / 蒸馏全走本地 llama-server，云端只留 agent 循环 |

> S1–S8 是本项目的**验收目标 ✅**；其实现路径见下文，未标记者默认为 **❓ 未定**。

---

## 2. 架构

> **本节只是摘要**：完整论证、不变量、存储与表结构、失败模式一律以 [`ARCHITECTURE.md`](ARCHITECTURE.md) 为准。

### 2.1 进程与边界

```
┌── DSH（dsh-herodotus / TS·Cordis）-----──┐   ┌── AstrBot（astrbot_plugin_herodotus / Py·Star）─┐
│ 捕获 session/event       → POST /ingest │   │ 捕获 event_message_type(ALL)         → /ingest │
│ 注入 agent/pre-step      → POST /recall │   │ 注入 filter.on_llm_request           → /recall │
│      → 消息侧 prepend（动态）           │   │      → extra_user_content_parts（动态）        │
│ 工具 ctx.tools.register  → MCP          │   │ 工具 add_llm_tools                    → MCP    │
└───────────────────┬─────────────────────-┘   └───────────────────┬───────────────────────────--┘
                    │                      MCP                     │
      ┌─────────────▼──────────────────────────────────────────────▼─────────────┐
      │  clio（C++ 独立守护进程；**唯一存储写者**）                                | 
      │   ├ ledger       账本：只增不改，同一 id 多版本                            | 
      │   ├ index        索引：**可整体丢弃并从账本重建**          | 
      │   ├ memory       记忆库：per-persona、L0–L3、时效衰减                      | 
      │   ├ knowledge    知识库：全局共享、带出处与 char 区间、不衰减              | 
      │   ├ distill      蒸馏管线：L1 / 去重合并 / L2 / L3                         | 
      │   ├ recall       混合召回：FTS + 向量 + RRF k=60 + 衰减 + 重排             | 
      │   ├ persona      人格：personaId 全链路、物理隔离目录                      | 
      │   ├ governance   治理：proposed→confirm 收件箱、注入为数据                | 
      │   └ serve        HTTP API + MCP server；乐观锁版本 CAS                     | 
      └────────────────────────────┬──────────────────────────────────────────────-┘
                                   │ OpenAI 兼容
                         ┌─────────▼──────────┐
                         │ llama-server :11434 │  嵌入 / 重排 / 蒸馏
                         │ （已存在，不动）    │
                         └──────────────────-──┘
```

### 2.2 仓库组织

主仓库 `herodotus` 是 **umbrella**，只承载文档与集成；三个组件是独立仓库，以 **git submodule** 组织。

```
herodotus/                        ← umbrella（文档 + 集成 + 组织）
├─ README.md  LICENSE  NOTICE  .gitignore
├─ docs\  PLAN.md  ARCHITECTURE.md  PROTOCOL.md  REFERENCES.md  changelog.md
├─ .reference\                   参考实现的实体 clone（不入库；登记见 docs/REFERENCES.md）
├─ scripts\                      构建 / 起停 / 冒烟脚本（P0 落地）
├─ clio\                         → submodule：C++ 引擎 + 守护进程
├─ dsh-herodotus\                → submodule：DSH 插件（TS/Cordis）
└─ astrbot_plugin_herodotus\     → submodule：AstrBot 插件（Python/Star）
```

**为何 submodule**：三组件语言不同（C++ / TS / Python）、发布渠道不同（二进制 / npm / AstrBot 插件市场），且协议演进时**客户端与引擎必须版本匹配**——submodule 让主仓库用固定 commit 记录「一套已知可用的组合」。

### 2.3 数据流

```
会话事件 ─客户端捕获→ /ingest → 队列 ─distill→ 记忆单元
                                        ├→ ledger（只增）
                                        └→ index（FTS + 向量）
用户 turn ─/recall→ recall 混合召回 → 客户端在**消息侧**注入（不进系统提示词）
人格选择 ─→ 客户端解析 personaId → 每请求显式携带 → 路由到该人格独立库
consolidate ─定时/手动→ 去重合并 → 更新 L3 画像快照（稳定区，受 governance 约束）
```

---

## 3. clio 技术选型

| 需要 | 选择 | 状态 |
| --- | --- | --- |
| 语言 / 标准 | **C++23**（开发者精通 C++、简单了解 Rust） | ✅ |
| 账本 / 索引存储 | SQLite | ✅ |
| 依赖导入 | **vcpkg manifest + `joker-registry`**（`vcpkg.json` 写依赖，`cmake/deps.cmake` 写 `find_package`；私有端口走 git registry）。`FetchContent` 仅用于 cppjieba、argparse | ✅ |
| 向量库（含 ANN） | `LanceDB` 的 C-binding | ✅ |
| HTTP | `pylai`（自建 asio HTTP 底座，joker-registry 供货） | ✅ |
| JSON | `simdjson` | ✅ |
| 全文检索引擎 | **SQLite FTS5**（写入侧用 cppjieba 预分词，查询侧同源分词） | ✅ |
| 嵌入模型 | 由 `llama-server` 提供；具体模型为配置槽位（见 D8） | 🟡 倾向 |
| 混编以借用 Rust 库 | — | ❓ 未定 |

---

## 4. 存储

**实现与表结构见 [`ARCHITECTURE.md`](ARCHITECTURE.md) §3**（账本 vs 索引、实际 schema、人格隔离、两种写入纪律）。
已定结论的汇总在 §8.1，这里不复述。

---

## 5. 接口契约

完整的 HTTP 端点与 MCP 工具定义见 **[`PROTOCOL.md`](PROTOCOL.md)**。

> 该文属生成骨架；**端点路径、字段、错误码尚未逐条确认 🔍**。可依据的只有下方标 ✅ 的两条。

**并发 ✅**：写操作带 `expectedVersion`；不一致返回 **409**（乐观锁）。

**MCP 定位 ✅**：只做模型主动调用的工具面；捕获与注入走 HTTP。**工具名 ❓ 未定**：`memory_search` / `memory_write` / `memory_forget` / `knowledge_search` / `knowledge_ingest`。

> **MCP 只承载模型主动调用的工具**。**自动捕获与自动注入不走 MCP**——MCP 无法 hook 智能体循环，纯 MCP 会退化成「模型想起来才查记忆」，恰是记忆系统最没用的形态。

---

## 6. 不变量与失败模式

**唯一正文见 [`ARCHITECTURE.md`](ARCHITECTURE.md) §2（不变量，含编号与状态）与 §5（失败模式与降级）。**

不变量只在那**一处**定义与编号：PLAN 不再复述。历史上两处各写一份，同一条曾一处标「待确认」、另一处标「已定」。

---

## 7. 里程碑与验收门

> **方案：乙·验证前置**（自底向上、先引擎后客户端不变）。核心是把**最大不确定性前置**：蒸馏质量（P0 spike + P2）与中文检索质量（P0 spike + P3）最先被验证；检索基准用参考实现产出的**黄金语料**，不再依赖蒸馏阶段。
>
> 本表为重组后的方案草案。**P0 / P1 已验收**（见 G0 / G1）；P2 及其后仍为草案，到阶段再逐条确认。
> P1 的未完成项正在 P2 开工前清理，清单见下方 P1 行。

| 阶段 | 交付物 | 验收门（通过才进下一阶段） |
| --- | --- | --- |
| **P0 工具链 + 价值 spike** | 可构建 `clio` + `scripts/`；两个 spike（蒸馏 L1 质量 / 中文分词质量）；产出**黄金语料集** | **G0**：`clio` 起停正常；spike 给出蒸馏与分词基线 —— **已通过** ✅ |
| **P1 账本 ＋ 索引 ＋ 关键词腿** | 账本 / 索引 schema、Store API、**FTS 关键词腿**、从账本重建、JSONL 导出 | **G1**：写 N 条 → 删索引 → 重建 → 结果一致；同一 id 多版本折叠正确；中文 FTS 可用 —— **已通过** ✅。**未完成项**（P2 开工前清理）：D0-d 遗忘机制、D0-e `POST /rebuild` |
| **P2 蒸馏 L1** | L1 抽取 + 去重合并（用 FTS 腿找候选）+ 队列 / 退避 / 缓冲 | **G2**：喂已知对话 → 覆盖决策与事实、**无「每步一条」噪声**；合并不产生重复 |
| **P3 完整混合检索** | 向量 + RRF + 衰减 + 重排；嵌入源三态 | **G3**：以黄金语料 + 真实语料为基准，hybrid **跑赢**纯 FTS 与纯向量基线 |
| **P4 服务面** | HTTP + MCP + 乐观锁 + 配置 + 独立起停 | **G4**：**不借助任何 agent 框架**，脚本完成 ingest → distill → recall 全环（distill 此时已存在） |
| **P5 DSH 接缝探针（lite）** | `dsh-herodotus` 最小版：捕获 + 消息侧注入 + 注入日志 + 降级 + **注入安全**；不含 UI | **G5**：跨会话召回成功；prefix cache 未破坏；停服务后对话不受阻 |
| **P6 人格** | personaId 全链路、每人格物理隔离、注册与切换、预设卡 + 酒馆角色卡 v2/v3 导入导出 | **G6**：两人格记忆**物理互不可见**（拔掉对方目录即失联） |
| **P7 L2 + L3 + 稳定区 + 完整 UI** | L2 场景块、L3 画像快照、稳定区注入、记忆面板与设置页 | **G7**：画像快照进稳定区不破坏 prefix cache；场景块生效 |
| **P8 治理** | proposed→confirm 收件箱 | **G8**：未确认的 proposed 不进长期记忆 |
| **P9 AstrBot 客户端** | `astrbot_plugin_herodotus` | **G9**：AstrBot 陈述的事实 DSH 同一人格可召回；反向亦成立 |
| **P10 知识库** | 文档摄取、分块、出处 / 区间、`kb_search`、大规模 ANN | **G10**：检索论文语料，每条**可回指 `doc_id + char 区间`**；5 万 / 20 万 chunk 有实测数据 |
| **P11（后置）** | 多媒体：ASR / VLM / OCR | 届时再定 |

**与旧排法的差异**：① 原 `P2 检索` 前无处取语料（旧 `G2` 无法成立）→ 检索后移到 P3，并先用参考实现产黄金语料；② 原 `P4 蒸馏` 后移，改为 **P2 蒸馏 L1 前移**，旧 `G3` 要求 distill 却将 distill 排在其后的矛盾消除；③ 原 `P5` 拆出 **P5 lite 接缝探针**，让 S1 / S5 / S6 提前有真信号；④ 原 `G7` 把「治理」与「注入安全」捆在一起，现把注入安全留在 P5，治理独立为 P8；⑤ 角色卡导入导出从治理移至人格（P6）。

**可并行**：P1 冻结账本 schema 后，P2（蒸馏）与 P3 的**向量腿**可并行（检索腿不依赖蒸馏产出）；P4 冻结 `PROTOCOL.md` 后，P5 客户端可与 P6+ 并行。

---

## 8. 决策与开放项

### 8.1 已定（按此实现；发现问题再改）

| 决策 | 结论 |
| --- | --- |
| 引擎语言 | **C++23** |
| 技术选型 | SQLite / **vcpkg manifest + `joker-registry`**（`FetchContent` 仅用于 cppjieba、argparse）/ `LanceDB`（向量）/ `pylai`（HTTP）/ `simdjson` / **SQLite FTS5** |
| 依赖导出方式 | 不用 `find_dependency`，也不用 CPS（目前不支持 compiler flags）→ 走 `EXPORT_PACKAGE_DEPENDENCIES` 实验开关 |
| 账本与索引的 artifact | **两文件**：`ledger.db` + `index.db` |
| 「只增」的保证 | **写入纪律** + `Store::verify()` 校验，不加 DB 层约束 |
| 更新语义 | 同 id **追加版本**（`version+1`），旧版本只从索引删除 |
| 账本模型 | **事件溯源（只增不改）**；**索引 = 账本 + 配置的纯函数**，可整体丢弃重建；账本用 **SQLite**；**JSONL 仅作可读备份 / 人工修复** |
| 并发 | 写操作带 `expectedVersion`，冲突返回 **409** |
| 人格与知识边界 | 记忆**按人格物理隔离**（目录 `personas/<personaId>/`）；知识库**全局共享** |
| 注入策略 | 动态走消息侧、稳定走系统提示词；不破坏 prefix cache |
| MCP 定位 | 只做模型主动调用的工具面；捕获与注入走 HTTP |
| 客户端协议 | 基地址 `127.0.0.1:7788`；无鉴权；camelCase + epoch 毫秒；长任务异步 `jobId` |
| 多媒体 | 后置到 P11 |

> 账本与索引的 schema 已按 P1 实现校准（`ARCHITECTURE` §3.4）；仍未定的只剩索引形态（D11）。其余（RPC 形状、检索参数、降级策略等）仍视为 **❓ 未定**，见 §8.2。

### 8.2 开放项与待调研清单（到阶段再定，不阻塞立项）

**A. 账本机制（P1 未完成项）**

| # | 待定 | 备选 | 何时定 |
| --- | --- | --- | --- |
| D0-d | 遗忘机制（历史默认不抹除；逻辑删除实现 ❓ 未定） | — | **P1 未完成**，P2 前清理 |
| D0-e | 是否暴露 `POST /rebuild` 端点 | — | **P1 未完成**（依赖 P4 的 HTTP 面），P2 前清理 |
| D6 | 账本 compact / 归档阈值 | 需实测增长曲线 | P1 后 |

**B. 引擎与协议**

| # | 待定 | 倾向 | 何时定 |
| --- | --- | --- | --- |
| D2 | 蒸馏模型 8B vs 14B | 先 8B，真实会话对比 | P2 |
| D5 | 是否直连 llama.cpp 取代 HTTP | 先 HTTP，有需求再直连 | P3 后 |
| D8 | 嵌入 / 重排 / 蒸馏模型槽位的默认值 | 按本机现有选择：`bge-m3` / `bge-rerank` / `qwen3-14b` | P2 首轮真实会话后复看 |
| D9 | 是否引入 Rust 混编 | 暂不 | P3 后 |
| D10 | 检索参数（RRF k=60、衰减地板 0.5 等） | 沿用参考实现 | P3 实测 |
| D11 | 索引形态：双列覆盖索引 vs 主表 + 回表；戳驱动重建；fsync 写入纪律 | 当前实现是 `fts_doc` + `l1_fts(terms)` 回表；戳重建未做 | **P3**（做检索时一并定） |
| D12 | `X-Clio-Protocol` 头与 `/health` 版本校验 | 保留 | P4 |
| D13 | `PROTOCOL.md` 端点 / 字段 / 错误码逐条复核 | — | P4 |

**C. 记忆与人格**

| # | 待定 | 倾向 | 何时定 |
| --- | --- | --- | --- |
| D3 | L3 快照更新时机（定时 / 会话结束 / 阈值） | 真实数据调 | P7 |
| D4 | 跨人格共享记忆边界（画像是否全局） | 画像算共享，其余私有 | P6 |
| D14 | 注入「数据非指令」与防回捕机制 | 沿用 `ARCHITECTURE.md` 草案 | P5 |
| D7 | 知识库与 AstrBot **内置知识库**的关系 | 自建（否则 DSH 侧访问不到） | P10 |
| D15 | 记忆的上下文情境：载荷形态与召回参与方式 | P2 定数据模型（落 `metadata_json`）、P4 定协议字段、加权留 P3 之后 | P2 / P4 |

---

## 9. 风险与假设

### 9.1 假设

- DSH 与 AstrBot 运行于**同一台机器**（服务走回环）；
- `llama-server` 在 `127.0.0.1:11434` 提供 OpenAI 兼容端点（嵌入 / 重排 / 蒸馏）。

### 9.2 风险与缓解

| 风险 | 缓解 |
| --- | --- |
| 从零写引擎比 fork TS 版慢 | TS 版作**语义参考**逐条对账（见 [`REFERENCES.md`](REFERENCES.md)）；P0 spike 尽早暴露问题 |
| cppjieba 分词质量不及 `@node-rs/jieba` | 二元组并集保底；P3 用同一查询集与 TS 版对比 |
| LanceDB 与 FTS5 双引擎一致性 | 二者都只是**索引**，账本为唯一真相；不一致即整体重建 |
| 双客户端并发写 | 版本 CAS + 409；服务是单写者 |
| 物理分人格产生 N 个数据库句柄 | 人格是「个位数」量级；需要时改按需打开 / 关闭 |
| 中文路径 / 权限 | 一律英文路径；启动期递归建目录 |

---

## 10. 许可与合规

- 主仓库与 `clio` 均以 **GPL-3.0** 发布。
- `NOTICE` 须保留：`dsh-layered-memory`（MIT）、`whale-persona`（MIT）与 TencentDB-Agent-Memory 的 MemoryCore 上游归属。
- 核对与收尾留到 **P10 之后**。
