# 参考实现清单

> **实体 clone 不入库**：参考实现与数据集放在 `.reference/`（`.gitignore` 的 `/.*/` 已忽略）。
> 本文件只记录**去哪找什么**与**移植优先级**；语义细节以参考实现代码为准。
>
> 状态：✅ 已移植 · 🟡 进行中 · ⬜ 未移植

## 1. dsh-layered-memory（语义规格）

| 项 | 值 |
| --- | --- |
| 来源 | https://github.com/JunNanLYS/dsh-layered-memory |
| 许可 | MIT（Copyright (c) JunNanLYS） |
| 上游 | 移植自 TencentDB-Agent-Memory 的 MemoryCore |
| 本地实体 | `.reference/dsh-layered-memory/`（TypeScript / Cordis） |
| 用途 | L0–L3 分层记忆、蒸馏 prompt、存储与召回语义的**逐条对账规格** |

### 关键文件索引

| 主题 | 路径 | 内容 | 状态 |
| --- | --- | --- | --- |
| 领域术语 | `CONTEXT.md` | L0–L3、捕获/蒸馏/召回、会话切片、渐进阈值、档位、族 | ✅（PLAN / ARCHITECTURE 已吸收） |
| src 边界 | `src/AGENTS.md` | 存储双写、检索唯一缝、防反馈循环、L0 捕获 4 类事件 | ✅（ARCHITECTURE §6 已吸收） |
| L1 抽取 prompt | `src/prompts/l1-extraction.ts` | chat / work / auto 三档 | ✅ `scripts/prompts/` |
| L1 去重 prompt | `src/prompts/l1-dedup.ts` | 冲突检测与合并决策 | ⬜ P2 |
| L2 场景 prompt | `src/prompts/scene.ts` | 场景块整合 | ⬜ P7 |
| L3 画像 prompt | `src/prompts/persona.ts` | 分族画像 | ⬜ P7 |
| L1 流程 | `src/pipeline/l1.ts` | 抽取 → 分块 → 去重 → 写入 | 🟡 抽取已 spike（`scripts/distill_spike.py`） |
| L2 / L3 流程 | `src/pipeline/{l2,l3}.ts` | 场景与画像更新 | ⬜ P7 |
| 触发与调度 | `src/pipeline/{runner,trigger}.ts` | 按会话切片、渐进阈值、闲置兜底、退避 | ⬜ P2 |
| 重建 | `src/pipeline/rebuild.ts` | 从 L0 重导全部派生层 | ⬜ P1 / P4 |
| 主存储 | `src/store/sqlite.ts` | node:sqlite + WAL + FTS5 BM25 + sqlite-vec | ⬜ P1 |
| 检索参数 | `src/store/search-utils.ts` | RRF k=60、bm25 归一、查询分词、时效衰减 | ⬜ P3 |
| L0 / L1 存储 | `src/store/{l0,l1}.ts` | JSONL 事实源 + 检索库双写 | ⬜ P1 |
| 场景 / 画像 / 状态 | `src/store/{scenes,persona,state}.ts` | 文件形态、按族拆分 | ⬜ P7 |
| 未蒸馏缓冲 | `src/store/pending.ts` | 重启不丢、按会话切片 | ⬜ P2 |
| L0 捕获 | `src/hooks/capture.ts` | 4 类事件、去噪、召回标签剥离 | ⬜ P5（客户端侧） |
| 消息侧注入 | `src/hooks/recall.ts` | prepend 合成消息 `form:'recall'` | ⬜ P5 |
| 工具面 | `src/tools/index.ts` | memory_search / conversation_search / memory_read_scene | ⬜ P4 |
| 类型与 RPC 契约 | `src/types.ts`、`src/contract.ts` | 记录类型、26 个端点 | ⬜ P4 对照 |
| 用量与成本 | `src/llm-usage.ts`、`src/token-cost.ts` | 分层 token 计量、成本看板 | ⬜ P4 后 |

**从参考实现继承的纪律**：

- 检索只走 `L1Store.search()` 一个缝，别处不另开检索路径。
- 蒸馏任何阶段失败只记日志，绝不阻塞 Agent 循环。
- 召回注入必须可剥离（标签包裹 + 捕获侧剥离），防反馈循环。
- L0 只收 4 类事件（user/assistant message、turn/start/end）；进行中轮次绝不裁剪。
- L0 在 turn/end 即时落盘，不排进蒸馏队列。

## 2. whale-persona（人格治理格式）

| 项 | 值 |
| --- | --- |
| 来源 | https://github.com/shenA2024/whale-persona |
| 许可 | MIT |
| 本地实体 | `.reference/whale-persona/`（JavaScript / 零运行时依赖） |
| 用途 | 人格文件格式、注入文本逐字装配、proposed→confirm 收件箱 |

### 关键文件索引

| 主题 | 路径 | 内容 | 状态 |
| --- | --- | --- | --- |
| 格式规范 | `SPEC.md` | 三层结构（config / preset card / inbox）、文本装配契约 | ⬜ P6 / P8 |
| 配置定位 | `core/store.js`、`core/defaults.js` | config 路径解析与默认值 | ⬜ P6 |
| 渲染 | `core/render.js`、`core/prompt.js` | 注入文本逐字装配 | ⬜ P6 |
| 治理收件箱 | `core/memoryInbox.js` | 只追加事件日志；AI 提议、人确认 | ⬜ P8 |
| 预设卡 | `core/presetStore.js`、`core/presets.js` | 预设卡格式与安装 | ⬜ P6 |
| 酒馆角色卡 | `core/tavernCard.js` | 角色卡 v2/v3 导入导出 | ⬜ P6 |
| 采集 / 编辑 | `core/{capture,edit}.js` | 写入面清单 | ⬜ P6 |

**核心不变量**（来自 `SPEC.md`）：`config.json` 是唯一运行时真源；预设卡是**输入**，第三方实现不得把预设卡当运行时配置直接读。

## 3. 数据集（实体不入库）

| 数据集 | 位置 | 用途 |
| --- | --- | --- |
| UD Chinese-GSD | `.reference/datasets/UD_Chinese-GSD/` | 分词评测（繁体，4 997 句） |
| UD Chinese-GSDSimp | `.reference/datasets/UD_Chinese-GSDSimp/` | 分词评测（简体，4 997 句） |
| UD Chinese-PatentChar | `.reference/datasets/UD_Chinese-PatentChar/` | 分词评测（简体专利，200 句） |

来源、作者与许可见 `NOTICE` §四。评测入口：`clio/tools/tokenize_spike.exe --conllu <file>`。

## 4. 本机模型槽位（D8，未定稿）

| 槽位 | 候选 | 备注 |
| --- | --- | --- |
| 嵌入 | `bge-m3-Q8_0` | 1024 维，多语言 |
| 重排 | `bge-reranker-v2-m3-Q8_0` | cross-encoder |
| 蒸馏 | `RVN-Q3_K_M-multilingual`（Qwen3.8-27B 去审查，16K ctx）或 `Qwen3-14B-abliterated.Q5_K_M` | 16GB 显存下后者更快，前者合并/归类更稳 |

模型文件与 router 配置在本机 `F:\Programma\models\`（`llama-router.ini`，不入库）。

## 5. 尚未 clone 的参考

| 参考 | 用途 | 何时 |
| --- | --- | --- |
| rag-task-service（erishen） | 乐观锁 / RRF / 重排降级的工程做法 | P4 前按需 |
