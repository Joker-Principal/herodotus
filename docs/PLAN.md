# Herodotus · 开发计划

> **状态**：立项阶段。本文件是开发推进的主依据；实现代码分布在三个组件仓库中。
> **命名**：只保留两个专名——项目 **Herodotus**（希罗多德，「历史之父」）、服务 **Clio**（他序言后首先召唤的缪斯，卷一之名；可执行文件就叫 `clio`，不带 `d`）。其余一律术语：`memory` / `knowledge` / `ledger` / `index` / `distill` / `recall` / `persona` / `governance`。

---

## 1. 系统定位与成功标准

**一句话**：Herodotus 是一个**本地、按人格隔离、供多个 AI 客户端共同存取**的记忆与知识服务。

**原始目标**：让 DSH 能在本地建立和使用记忆；能在 DSH 里建立人格，人格也有独立的记忆。

**扩展目标**：记忆与 AstrBot **按人格共享**；另建**知识库**（服务于中西比较历史论文，含经济数据分析）。

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

---

## 2. 架构

### 2.1 进程与边界

```
┌── DSH（dsh-herodotus / TS·Cordis）──┐   ┌── AstrBot（astrbot_plugin_herodotus / Py·Star）─┐
│ 捕获 session/event       → POST /ingest │   │ 捕获 event_message_type(ALL)         → /ingest │
│ 注入 agent/pre-step      → POST /recall │   │ 注入 filter.on_llm_request           → /recall │
│      → 消息侧 prepend（动态）            │   │      → extra_user_content_parts（动态）        │
│ 工具 ctx.tools.register  → MCP          │   │ 工具 add_llm_tools                    → MCP     │
└───────────────────┬─────────────────────┘   └───────────────────┬───────────────────────────┘
                    │ HTTP 127.0.0.1:7788 + MCP                    │
      ┌─────────────▼──────────────────────────────────────────────▼─────────────┐
      │  clio（C++ 独立守护进程；**唯一存储写者**）                                 │
      │   ├ ledger       账本：只增不改，同一 id 多版本                            │
      │   ├ index        索引：FTS5 + USearch，**可整体丢弃并从账本重建**          │
      │   ├ memory       记忆库：per-persona、L0–L3、时效衰减                     │
      │   ├ knowledge    知识库：全局共享、带出处与 char 区间、不衰减              │
      │   ├ distill      蒸馏管线：L1 / 去重合并 / L2 / L3                        │
      │   ├ recall       混合召回：FTS + 向量 + RRF k=60 + 衰减 + 重排            │
      │   ├ persona      人格：personaId 全链路、物理隔离目录                     │
      │   ├ governance   治理：proposed→confirm 收件箱、注入为数据                │
      │   └ serve        HTTP API + MCP server；乐观锁版本 CAS                    │
      └────────────────────────────┬──────────────────────────────────────────────┘
                                   │ OpenAI 兼容
                         ┌─────────▼──────────┐
                         │ llama-server :11434 │  嵌入 / 重排 / 蒸馏
                         │ （已存在，不动）      │
                         └────────────────────┘
```

### 2.2 仓库组织

主仓库 `herodotus` 是 **umbrella**，只承载文档与集成；三个组件是独立仓库，以 **git submodule** 组织。

```
herodotus/                        ← umbrella（文档 + 集成 + 组织）
├─ README.md  LICENSE  NOTICE  .gitignore
├─ docs\  PLAN.md  ARCHITECTURE.md  PROTOCOL.md
├─ reference\                    参考实现清单（实体 clone 不入库）
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

## 3. 技术选型

### 3.1 引擎语言：C++20

| 需要 | C/C++ 方案 | 状态 |
| --- | --- | --- |
| 全文检索 | **Xapian**（CMake/vcpkg 易集成，**已验 jieba 中文方案**，模糊 / 加权 / 范围 / 高亮 / compact / 事务 / 内存模式） | 成熟；**GPL-2+，与我们的 GPL 同向** |
| 向量 ANN | **USearch**（C++11 **header-only**，HNSW + cosine，~800 KB，AVX-512/NEON） | 成熟 |
| 中文分词 | **cppjieba** | 成熟 |
| 关系 / 账本 | **SQLite**（进程内） | 成熟 |
| 本地推理 | **llama.cpp**（以 `llama-server` 独立进程运行） | 成熟 |
| HTTP / JSON | `cpp-httplib` + `nlohmann/json`（均 header-only） | 成熟 |
| 多媒体（后置） | `whisper.cpp` / `ncnn` | 成熟 |

**依据**：

1. 开发者精通 C++、未学 Rust——**开发速度差是决定性的**；
2. 每个关键件在 C/C++ 生态都有成熟且更「原生」的实现，而 Rust 侧最诱人的两项（Tantivy、LanceDB 原生）**只解决我们已用别的手段解决了的两个点**（中文 FTS、向量索引）；
3. Windows 桌面 MSVC + CMake + vcpkg 路径成熟；
4. 可出单文件二进制。

**已记录但不采用的 Rust 优势**：内存安全、cargo 依赖体验、Tantivy 检索质量、LanceDB 原生。

**C++ 风险与对策**：

- 无内存安全网 → 强制 RAII、禁裸指针与 `new`/`delete`、CI 开 **ASan/UBSan**、`clang-tidy`；
- Xapian 未捕获的 `Xapian::Error` 会直接 `terminate` → **所有 Xapian 调用包 `try/catch`**；
- Xapian `WritableDatabase` **非线程安全且为排他写锁** → 单写者 + 加锁；
- Xapian `DB_CREATE_OR_OPEN` **不会递归创建父目录** → 启动期自行递归建目录。

**裁决点**：P0 工具链 spike 若在 MSVC 上装不齐依赖，则重新评估语言——不预设结论。

### 3.2 其余选型

| 层 | 选择 | 备选 / 触发更换条件 |
| --- | --- | --- |
| 检索-关键词 | **SQLite FTS5 + 自定义 cppjieba∪二元组分词** | Xapian：当 FTS5 排序 / 模糊 / 高亮不够用时 |
| 检索-向量 | **USearch（HNSW）** | sqlite-vec（省一引擎）；FAISS（数百万级） |
| 账本 | **SQLite `ledger.db`，INSERT-only + 定期 JSONL 导出** | 见 §4.1 |
| 索引 | **SQLite `index.db`**（FTS5 + 元数据）+ USearch 向量文件 | 可整体 DROP 重建 |
| 分词 | **cppjieba 词 ∪ 拉丁词 ∪ CJK 二元组**（有序去重并集） | — |
| 推理接入 | **llama-server over HTTP（OpenAI 兼容）** | 后续可直接 link llama.cpp |
| 客户端-DSH | **TypeScript / Cordis** | — |
| 客户端-AstrBot | **Python / Star** | — |
| 模型 | **一律可配置槽位**，默认指向本机 llama-server | 绝不硬编码、绝不捆绑 |

---

## 4. 存储

### 4.1 账本 vs 索引

- **账本** = 事实的**历史**，只增不改（事件溯源）；同一 id 可有多行（version 0,1,2…）。
- **索引** = 事实的**当前状态**，可整体丢弃并从账本重建。

**账本格式定案**：**SQLite 账本（INSERT-only）+ 定期/按需 JSONL 导出**。

理由：

1. 「账本无界增长需要 compact / 归档」这一点判断正确——JSONL 只能靠外部工具，SQLite 可 `VACUUM` + 索引化裁剪；
2. 服务是**单写者进程**，SQLite 的 ACID 与并发读是纯收益；
3. 但「灾难恢复时人能读懂、能手工修」这一属性由 **JSONL 导出**补回——`ledger.db` 管运行，JSONL 管可读备份与人工修复。

**铁律**：账本与索引**永不合并为同一 artifact**；「只增」由纪律 + 定期行数 / 哈希校验保证。

### 4.2 表结构要点

**账本侧（只增）**

```sql
l0_ledger(seq INTEGER PK AUTOINCREMENT, record_id TEXT, persona_id TEXT,
          session_id TEXT, role TEXT, content TEXT,
          occurred_at INTEGER, recorded_at TEXT, source TEXT)   -- source: dsh|astrbot|manual

l1_ledger(seq INTEGER PK AUTOINCREMENT, record_id TEXT, persona_id TEXT, version INTEGER,
          content TEXT, type TEXT, priority INTEGER, scene_name TEXT,
          timestamps_json TEXT,          -- 合并时取并集
          source_message_ids_json TEXT,  -- 溯源：**仅账本有，索引不存**
          metadata_json TEXT, created_at INTEGER, updated_at INTEGER,
          op TEXT)                       -- add|merge|edit|forget

governance_inbox(seq INTEGER PK AUTOINCREMENT, persona_id TEXT, record_id TEXT,
                 state TEXT,             -- proposed|confirmed|rejected
                 payload_json TEXT, actor TEXT, at INTEGER)   -- actor: ai|human
```

**索引侧（可丢弃）**

```sql
l1_records(record_id TEXT PK, persona_id TEXT, content TEXT, type TEXT, priority INTEGER,
           scene_name TEXT, version INTEGER, session_id TEXT,
           ts_start INTEGER, ts_end INTEGER, created_at INTEGER, updated_at INTEGER,
           metadata_json TEXT, state TEXT)    -- active|superseded|forgotten

l1_fts(...)   -- FTS5：content(分词后) + content_original(UNINDEXED 原文回显) + 其余 UNINDEXED 载荷
l0_fts(...)

embedding_meta(key TEXT PK, value TEXT)       -- provider/model/dims + fts_tokenizer 戳
```

索引另加 `persona_id` 索引；向量按人格分文件存放。

**知识库（全局共享）**

```sql
kb_documents(doc_id TEXT PK, title TEXT, source_uri TEXT, source_type TEXT,
             author TEXT, published_at TEXT, hash TEXT, ingested_at TEXT, meta_json TEXT)

kb_chunks(chunk_id TEXT PK, doc_id TEXT, seq INTEGER, text TEXT, token_count INTEGER,
          char_start INTEGER, char_end INTEGER)   -- 保留字符区间以支持**引用定位**

kb_ledger(seq PK AUTOINCREMENT, chunk_id TEXT, op TEXT, payload_json TEXT, at INTEGER)
```

不衰减；修订走新版本 + `superseded_by`；检索结果必须能回指 `doc_id + char_start/char_end`。

### 4.3 人格隔离

**物理隔离**：每人格一套

```
personas/<personaId>/
├─ ledger.db          账本
├─ index.db           索引（可删可重建）
├─ vectors.usearch    向量索引
├─ scenes/            L2 场景块
└─ persona.md         L3 画像快照
```

索引缺失时从该人格账本重建。

**知识库全局唯一**，不随人格分裂——这是「知识共享、记忆私有」的结构表达。

**升级路径**：先在单人格（`default`）跑通，P6 再启用多目录。

---

## 5. 接口契约

完整的 HTTP 端点与 MCP 工具定义见 **[`PROTOCOL.md`](PROTOCOL.md)**（跨组件的单一事实源）。

摘要：

```
GET  /health
POST /ingest       POST /recall      POST /write      POST /forget
POST /consolidate  GET|POST /snapshot
GET|POST /personas
GET  /jobs         DELETE /jobs/{id}
POST /rebuild
GET  /governance   POST /governance/{id}/{confirm|reject}
POST /kb/ingest    POST /kb/search
```

**并发**：写操作带 `expectedVersion`；不一致返回 **409**（乐观锁）。

**MCP 工具**：`memory_search` / `memory_write` / `memory_forget` / `knowledge_search` / `knowledge_ingest`。

> **MCP 只承载模型主动调用的工具**。**自动捕获与自动注入绝不走 MCP**——MCP 无法 hook 智能体循环，纯 MCP 会退化成「模型想起来才查记忆」，恰是记忆系统最没用的形态。

---

## 6. 不变量与失败模式

### 6.1 七条不变量（不可违反）

1. **只有 `clio` 写存储**；客户端永不打开数据库。
2. `clio` **只监听 127.0.0.1**。
3. `clio` **由我们自己启动，不作为 DSH 子进程**（规避 DSH 把 `[::1]` 强塞 `NO_PROXY` 的历史坑）。
4. **动态召回只进消息侧 / 用户内容块**；只有稳定内容（人格、画像）进系统提示词稳定区。
5. 注入内容**标记为「数据非指令」**且**不被回捕**（DSH 用 `source.form='recall'` 过滤；AstrBot 用 `.mark_as_temp()`）。
6. **账本与索引永不合并**；索引必须能从账本重建。
7. **中文检索不可妥协**：二元组并集是不可移除的召回底线。

> 详细论证与实测依据见 [`ARCHITECTURE.md`](ARCHITECTURE.md)。

### 6.2 失败模式与对策

| 失败 | 对策 |
| --- | --- |
| 服务未启动 / 崩溃 | 客户端全路径降级 no-op，**绝不阻塞对话**；告警一次 |
| 蒸馏 LLM 不可用 | 指数退避（60s 起翻倍封顶 30min），成功清零；不堆积重试风暴 |
| 嵌入服务不可用 | 单次降级纯 FTS，不上抛；后台补齐 |
| 索引写入失败 | 账本已先行落盘 → 记忆暂不可检索，提示「重建」；**数据不丢** |
| 账本损坏 | JSONL 导出人工修复；`PRAGMA integrity_check` + 行数 / 哈希校验 |
| 版本冲突（双客户端同写） | 409 + 客户端重读重试 |
| 分词器 / 嵌入模型变更 | 戳（stamp）不一致 → DROP 派生表 + 从账本回灌 |
| 磁盘满 / 权限不足 | 启动期探测，降级为只读 / 停用并明确报错，不崩 |

---

## 7. 里程碑与验收门

| 阶段 | 交付物 | 验收门（通过才进下一阶段） |
| --- | --- | --- |
| **P0 工具链** | vcpkg 全量依赖（SQLite / cppjieba / USearch / httplib / json）+ 可构建 `clio` + `scripts/` | **G0**：MSVC 装齐依赖；cppjieba 切中文、USearch 建查索引、`clio` 起停正常 |
| **P1 账本＋索引** | 账本 / 索引 schema、Store API、从账本重建、JSONL 导出 | **G1**：写 N 条 → 删 `index.db` → 重建 → 结果一致；同一 id 多版本折叠正确 |
| **P2 检索** | 混合召回（FTS + 向量 + RRF + 衰减 + 重排）、嵌入源三态 | **G2**：固定中文查询集达标；hybrid **跑赢**纯 FTS 与纯向量基线 |
| **P3 服务面** | HTTP + MCP + 乐观锁 + 配置 + 独立起停 | **G3**：**不借助任何 agent 框架**，脚本完成 ingest → distill → recall 全环 |
| **P4 蒸馏** | L1 抽取 / 去重合并、L2 场景、L3 画像、Prompt 移植、队列 / 退避 / 缓冲 | **G4**：喂已知对话 → 覆盖决策与事实、**无「每步一条」噪声**；合并不产生重复 |
| **P5 DSH 客户端** | `dsh-herodotus`：捕获 + 消息侧注入 + 工具 + 稳定区 + 客户端 UI + 降级 | **G5**：跨会话召回成功；注入日志可见；prefix cache 未破坏；停服务后对话不受阻 |
| **P6 人格** | personaId 全链路、每人格物理隔离、注册与切换、L3 快照 | **G6**：两人格记忆**物理互不可见**（拔掉对方目录即彻底失联） |
| **P7 治理** | proposed→confirm 收件箱、注入为数据、预设卡 + 酒馆角色卡 v2/v3 导入导出 | **G7**：注入含「忽略以上指令」的记忆**不被执行**；未确认的 proposed **永不**进长期记忆 |
| **P8 AstrBot 客户端** | `astrbot_plugin_herodotus` | **G8**：AstrBot 陈述的事实 DSH 同一人格可召回；反向亦成立 |
| **P9 知识库** | 文档摄取、分块、出处 / 区间、`kb_search`、大规模 ANN | **G9**：检索论文语料，每条**可回指 `doc_id + char 区间`**；5 万 / 20 万 chunk 有实测数据 |
| **P10（后置）** | 多媒体：ASR / VLM / OCR | 届时再定 |

**可并行**：P3 冻结 `PROTOCOL.md` 后，P4（引擎侧）与 P5（客户端侧）可并行推进；P8 依赖 P3 与 P6。

---

## 8. 已定决策与开放项

### 8.1 已定（不再讨论）

| 决策 | 结论 |
| --- | --- |
| 引擎语言 | **C++20**（P0 spike 为最终裁决点） |
| 账本格式 | **SQLite INSERT-only + JSONL 导出** |
| 人格与知识边界 | 记忆**按人格物理隔离**；知识库**全局共享** |
| 注入策略 | 动态走消息侧、稳定走系统提示词；不破坏 prefix cache |
| MCP 定位 | 只做模型主动调用的工具面；捕获与注入走 HTTP |
| 多媒体 | 后置到 P10 |
| 许可 | **GPL-3.0**；发布**绝不捆绑模型**；模型一律可配置槽位 |
| 命名 | 只保留 **Herodotus**（项目）与 **Clio**（服务） |

### 8.2 开放项（到阶段再定，不阻塞立项）

| # | 决策 | 倾向 | 何时定 |
| --- | --- | --- | --- |
| D1 | FTS 用 SQLite FTS5 还是 Xapian | 先 FTS5（少一引擎），不够再换 | P2 实测 |
| D2 | 蒸馏模型 8B vs 14B | 先 8B，真实会话对比 | P4 |
| D3 | L3 快照更新时机（定时 / 会话结束 / 阈值） | 真实数据调 | P6 |
| D4 | 跨人格共享记忆边界（画像是否全局） | 画像算共享，其余私有 | P6 |
| D5 | 是否直连 llama.cpp 取代 HTTP | 先 HTTP，有需求再直连 | P2 后 |
| D6 | 账本 compact / 归档阈值 | 需实测增长曲线 | P1 后 |
| D7 | 知识库与 AstrBot **内置知识库**的关系 | 自建（否则 DSH 侧访问不到） | P9 |

---

## 9. 风险与假设

### 9.1 假设

- DSH 与 AstrBot 运行于**同一台机器**（服务走回环）；
- `P:\herodotus\` 可写；
- `llama-server` 在 `127.0.0.1:11434` 提供 OpenAI 兼容端点（嵌入 / 重排 / 蒸馏）。

### 9.2 风险与缓解

| 风险 | 缓解 |
| --- | --- |
| 从零写引擎比 fork TS 版慢 | TS 版作**语义规格**逐条对账（`reference/` + `prompts/` 移植）；P0 spike 尽早暴露工具链问题 |
| cppjieba 分词质量不及 `@node-rs/jieba` | 二元组并集保底；P2 用同一查询集与 TS 版对比 |
| USearch 与 FTS5 双引擎一致性 | 二者都只是**索引**，账本为唯一真相；不一致即整体重建 |
| 双客户端并发写 | 版本 CAS + 409；服务是单写者 |
| 物理分人格产生 N 个数据库句柄 | 人格是「个位数」量级；需要时改按需打开 / 关闭 |
| 中文路径 / 权限（若启用 Xapian） | 一律英文路径；启动期递归建目录 |

---

## 10. 许可与合规

- 主仓库与 `clio` 均以 **GPL-3.0** 发布。
- `NOTICE` 须保留：`dsh-layered-memory`（MIT）、`whale-persona`（MIT）与 TencentDB-Agent-Memory 的 MemoryCore 上游归属。
- 若采用 Xapian：**GPL-2+**，与 GPL-3 兼容，须在 `NOTICE` 标注。
- **绝不捆绑模型**；jina-reranker（CC BY-NC）仅作为本机可配置槽位的可选默认建议，不出现在发布物中。
