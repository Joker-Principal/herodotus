# 参考登记 / REFERENCES

> **这里记的是「某处设计参考了谁」，不是移植清单。**
>
> 本项目不移植任何完整项目：每一条都写明**借鉴了什么**、**哪里刻意做得不一样**、以及**落在本仓库的哪一份文档 / 代码**。
> 因此表里出现「偏离」「不采用」是正常结果，不是欠账。
>
> 适用范围不限于同类记忆库：今后某个子功能自己实现、但借鉴了别人的算法或工程做法，也登记在这里。
>
> 状态标记：**✅ 已验证（代码/实验）** · **🟡 倾向（待评估）** · **🔍 待调研 / ❓ 未定**；
> 「偏离」「不采用」是结论，不是状态。
>
> 本机实体（clone 的源码、下载的数据集）放在 `.reference/`，不入库（`.gitignore` 已忽略 `/.*/`）。
> 本机环境与模型槽位属私有配置，**不写进本仓库**。

---

## 1. dsh-layered-memory —— 分层记忆与蒸馏/召回语义

| 项 | 值 |
| --- | --- |
| 来源 | https://github.com/JunNanLYS/dsh-layered-memory |
| 许可 | MIT |
| 上游 | 其自身移植自 TencentDB-Agent-Memory 的 MemoryCore |
| 形态 | TypeScript / Cordis 插件，跑在宿主进程内 |
| 我们参考的 | L0–L3 的分层语义、蒸馏 prompt 的档位划分、召回的融合与衰减顺序 |

### 1.1 借鉴了什么

| 参考点 | 它的做法 | 我们的处理 | 落点 |
| --- | --- | --- | --- |
| L0–L3 分层 | 消息 / 原子事实 / 场景块 / 画像快照 | **借鉴**：分层保留，「族」用于限定去重候选范围 | `ARCHITECTURE` §3 · 表结构 `l1_ledger.family` |
| 检索唯一缝 | 全部检索走 `L1Store.search()` | **借鉴**：clio 只保留 `Index::search` 一条检索路径 | ✅ `clio/core/index` |
| L1 抽取 prompt 三档 | chat / work / auto | **借鉴**：已改写为三份 prompt | ✅ `scripts/prompts/l1_extraction_*.txt` |
| L0 捕获的 4 类事件 | user/assistant message、turn start/end | **借鉴**：同样只收有限事件，且不裁剪进行中的轮次 | 🟡 `dsh-herodotus`（P5 客户端侧） |
| 消息侧注入形态 | prepend 一条 `form:'recall'` 的合成消息 | **借鉴**：注入位置与标记方式 | 🟡 防回捕细则 🔍 待调研（见 `ARCHITECTURE` §2.5） |
| 蒸馏失败不阻塞 | 各阶段失败只记日志 | **借鉴**：成为硬约束 | ✅ `ARCHITECTURE` §5 |

### 1.2 刻意做得不一样

| 差异 | 它的做法 | 我们的做法 + 理由 |
| --- | --- | --- |
| 存储形态 | `node:sqlite` + `sqlite-vec`，JSONL 是事实源 | **SQLite C API + LanceDB**，JSONL 降级为「可读备份 / 人工修复」。理由：需要 ANN 与 5 万 chunk 以上的实测，且引擎是 C++，直接走 C 绑定比经 Node 桥接简单 |
| JSONL 的地位 | 事实源（JSONL 为真，SQLite 是派生） | **账本是唯一真源**，JSONL 只是导出格式。理由：双写会让「索引 = 账本 + 配置的纯函数」这条不成立 |
| 宿主模型 | 记忆逻辑跑在 DSH 进程内 | **独立守护进程**，多客户端共享。理由：AstrBot 的插件存储是插件私有的，跨系统共享只能靠外部服务 |
| 族（family） | 两族 `chat` / `work` 硬编码 | **任意族**，作为数据字段而非代码分支 |
| 人格 | 不涉及 | 新增；按人格物理隔离目录（`ARCHITECTURE` §3.1） |
| 知识库 | 不涉及 | 新增；全局共享、带 char 区间出处（P10） |
| 端点契约 | 自家 26 个端点 | **只作对照**，不照搬；我们的契约以 `PROTOCOL.md` 为准 |

### 1.3 待评估

| 参考点 | 位置 | 状态 |
| --- | --- | --- |
| 检索参数（RRF k=60、bm25 归一、衰减地板 0.5） | `src/store/search-utils.ts` | 🔍 P3 实测（决策 D10） |
| FTS 形态：双列覆盖索引 vs 主表 + 回表 | `src/store/sqlite.ts` | 🔍 P3（决策 D11） |
| L1 去重 prompt（冲突检测与合并决策） | `src/prompts/l1-dedup.ts` | 🟡 P2 借鉴后改写 |
| 触发与调度（会话切片、渐进阈值、闲置兜底、退避） | `src/pipeline/{runner,trigger}.ts` | 🟡 P2 |
| 未蒸馏缓冲（重启不丢、按会话切片） | `src/store/pending.ts` | 🟡 P2 |
| L2 场景 / L3 画像 prompt | `src/prompts/{scene,persona}.ts` | 🟡 P7 |
| 从 L0 重导全部派生层 | `src/pipeline/rebuild.ts` | 🟡 与我们的 `rebuild` 对照（P1 / P4） |

---

## 2. whale-persona —— 人格格式与治理收件箱

| 项 | 值 |
| --- | --- |
| 来源 | https://github.com/shenA2024/whale-persona |
| 许可 | MIT |
| 形态 | JavaScript，零运行时依赖 |
| 我们参考的 | 人格文件的三层结构、注入文本的逐字装配、proposed→confirm 收件箱 |

| 参考点 | 它的做法 | 我们的处理 | 落点 |
| --- | --- | --- | --- |
| `config.json` 是唯一运行时真源 | 预设卡、画像都指向它 | **借鉴** | 🟡 P6 |
| 预设卡是**输入**不是运行时配置 | 第三方实现不得直接读预设卡当配置 | **借鉴**：成为一条不变量 | 🟡 P6 |
| 治理收件箱只追加事件日志 | AI 提议、人确认 | **借鉴**：`governance_inbox` 只追加，未确认的不进长期记忆 | 🟡 P8（表结构已在 `ARCHITECTURE` §3.4 预留） |
| 酒馆角色卡 v2 / v3 导入导出 | 自家格式映射 | **借鉴格式，不借鉴实现**（语言不同） | 🟡 P6 |

> 差异：它把人格当**宿主插件的配置文件**；我们把人格当**服务端一等实体**（目录隔离 + 全链路 personaId），客户端只负责解析与携带。

---

## 3. 评测语料与数据集

| 数据集 | 用途 | 来源 / 许可 | 存放 |
| --- | --- | --- | --- |
| 黄金语料集（20 场景 / 65 语料 / 140 查询） | P3 检索基准 | 由 `scripts/build_golden.py` 从 §1 参考实现的 bench 场景生成 | 入库：`clio/tests/data/golden/` |
| UD Chinese-GSD | 分词评测（繁体，4 997 句） | Universal Dependencies，见 `NOTICE` §四 | `.reference/datasets/` |
| UD Chinese-GSDSimp | 分词评测（简体，4 997 句） | 同上 | `.reference/datasets/` |
| UD Chinese-PatentChar | 分词评测（简体专利，200 句） | 同上 | `.reference/datasets/` |

评测入口：`clio/tools/tokenize_spike --conllu <file>`。

---

## 4. 待评估的来源

| 来源 | 可能参考的点 | 何时看 |
| --- | --- | --- |
| rag-task-service（erishen） | 乐观锁 / RRF / 重排降级的工程做法 | 🟡 P4 前按需 |

---

## 5. 记录纪律

- 一条参考只在**真正读进代码或文档**时登记；没读过的不写，避免制造「欠账清单」的错觉。
- 每个来源必须写许可，并同步到 `NOTICE`。
- 状态跟事实走：代码已按它实现 → ✅；只是打算 → 🟡；只在评估 → 🔍。
- 本机环境、模型槽位、具体路径**不登记在这里**（属私有配置，不进仓库）。
