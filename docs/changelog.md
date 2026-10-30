# 变更史 —— Herodotus（新在上）

> **这里是"账本"，不是"说明书"。** 现状设计看 `ARCHITECTURE.md` / `PLAN.md`，协议看 `PROTOCOL.md`，
> 用法看各组件的 `README.md`；更早的历史看 `git log`。
>
> 本条记**跨组件的落地变更**。单组件内部的论证流水仍留在各自仓里
> （HTTP 底座的论证史在 `pylai/docs/changelog.md`）。
>
> 每条只记**改了什么 + 为什么 + 怎么复核**。结论给符号名（`文件` + 函数名），不写行号
> （重构会往文件前部插代码，行号必漂）。状态标 **✅ 已验证** · **🟡 倾向** · **🔍 待调研**。

---

## 2026-10-30 · P1 收尾：遗忘机制与重建入口

**范围**：`clio`（`ledger` / `index` / `store_cli` / `tests`）、`PROTOCOL`、`PLAN`、`ARCHITECTURE`。

### 决策

- **遗忘（D0-d）**：逻辑删除 = 账本追加 `op=forget` 版本（**内容必须为空**）+ 索引直接删行。旧版本仍在账本（历史不抹除，物理抹除另立机制 P7）；再追加带内容的版本即可复活。
- **重建入口（D0-e）**：**不暴露 `POST /rebuild`**。重建走 `store_cli rebuild` 与启动期按水位 / 戳位的自愈；`PROTOCOL` 删掉该端点小节。

### 改了什么

- `ledger::Store::appendL1Version` 校验 `op ∈ add|merge|edit|forget`，并拒绝带内容的 `forget`（新错误码 `invalid_op` / `forget_content_not_empty`）。
- `index::Index`：`upsertNoTxn` 遇 `op=forget` 调 `removeNoTxn` —— 因此**重建也不会让遗忘记录复活**；`remove` 改为对 `removeNoTxn` 的薄包装。
- `store_cli` 新增 `forget --record` 子命令。
- `index_tests` 新增四条：遗忘后不命中、重建后不复活、追加版本后复活、带内容的 forget 被拒。

### 怎么复核

```powershell
ctest --preset <你的 test preset> --output-on-failure     # 应 4/4
store_cli --data-dir D --dict-dir D append-l1 --record r-1 --content "温酒斩华雄"
store_cli --data-dir D --dict-dir D forget --record r-1
store_cli --data-dir D --dict-dir D rebuild
store_cli --data-dir D --dict-dir D search "华雄"          # 两次都应 count = 0
```

---

## 2026-10-30 · 补入口与术语，把散在会话里的口径收进文档

**范围**：根 `README.md`、新增 `AGENTS.md`、`docs/{ARCHITECTURE,REFERENCES,PROTOCOL,PLAN}.md`。只动文档。

### 补入口

- 根 `README` 增「目录地图」与「怎么跑」：只指向各组件 README，**不写编译器与预设名**（属本机配置）。
- 新增 `AGENTS.md`，**只收本仓特有的五条**（本仓边界、索引只在根 README、目录 README 按需创建、变更记载分两层、环境不入库）；全局协作与提交纪律不重复。
- 术语：`ARCHITECTURE` 增 `§0`（L0–L3、账本 / 索引、族、人格、知识库、蒸馏、召回、注入、稳定区、戳位、治理收件箱），定义只此一处；`REFERENCES` 的 L0–L3 改为指向该节。

### 把口径收回文档

- **错误与事务约定**落进 clio 仓的 [`../clio/docs/coding-discipline.md`](../clio/docs/coding-discipline.md)：`std::expected<T, std::error_code>` + 各模块自带分类器、只跨不可控边界抛 `Exception`、事务用 `JK::Meta::Cleanup`。这是 clio 的内部实现约定，不进 umbrella 的架构文档；`ARCHITECTURE §8` 只留一张「各组件的约定在哪」的索引。
- **依赖的客观行为**进入 `REFERENCES §4`：asio 的自动链接被 `_MSC_VER` 包住（MinGW 拿不到 `ws2_32` / `mswsock` / `bcrypt`）、vcpkg 的 port `CMakeLists.txt` 不参与 ABI 哈希（改它必须 bump `port-version`）、llvm#191462 只在 MS-ABI 复现。
- **决策**：`PLAN` §8.1 补「依赖导出方式」——不用 `find_dependency`，也不用 CPS（尚不支持 compiler flags），走 `EXPORT_PACKAGE_DEPENDENCIES`。
- **漂移收敛**：`PROTOCOL` 的 `POST /rebuild` 标出 🔍（是否暴露仍未定，见 D0-e）；`ARCHITECTURE §7` 删掉与 `REFERENCES` 重复的差异叙述，只留指针。

### 怎么复核

```powershell
Select-String -Path docs\*.md,README.md,AGENTS.md -Pattern '【定】|【待考证】'   # 应为空
Select-String -Path docs\ARCHITECTURE.md -Pattern '^## '                    # §0–§8 连续
```

---

## 2026-10-27 · 文档重组：每篇只回答一个问题

**范围**：`docs/` 全部、根 `README.md`、两个客户端 README。只动文档，不动实现。

### 病因

1. `PLAN` 与 `ARCHITECTURE` 有四个大节是同一内容的两份拷贝（进程图、数据流、账本 vs 索引、不变量、失败模式），而且**已经漂了**：
   「账本与索引分为两个 artifact」在 `PLAN` 里是已定、在 `ARCHITECTURE` 里还是待确认，而 P1 代码早按两个文件落地。
2. `REFERENCE.md` 被写成「移植进度表」（✅已移植 / ⬜未移植）。实际关系是**抄某一条设计或刻意偏离**，那个框架会让人以为两个参考项目是本项目的欠账。
3. 客户端契约有**三份拷贝**：`ARCHITECTURE` §2 → `PROTOCOL` §5 → 两个客户端 README 各一份，且 dsh 7 条、AstrBot 8 条已经不一致。

### 改了什么

- **`REFERENCE.md` → `REFERENCES.md`**：改成「借鉴了什么 / 哪里刻意不同 / 待评估」三段式，每个来源写清借鉴点与偏离理由；适用范围放宽到「今后某个子功能自行实现、但参考了别人的算法或工程做法」。
- **`PLAN` 让出实现**：`§4 存储`、`§6 不变量与失败模式` 只留指针（`§2` 加「本节只是摘要」抬头）；实际 schema 移入 `ARCHITECTURE` 新增的 `§3.4 表结构`。
- **不变量单一真源**：只在 `ARCHITECTURE` §2 编号定义，7 条（6 ✅ + 1 🔍）；同时修掉上面那处状态矛盾。
- **标记体系换成四档**：`✅ 已定` · `🟡 倾向` · `🔍 待调研` · `❓ 未定`，图例只在根 `README` 定义一次；`【定】` / `【待考证】` 全仓库清零。配套去掉「绝不 / 永不 / 彻底 / 不可妥协」这类把话说死的措辞。
- **客户端契约收敛**：`PROTOCOL` §5 成为唯一正文，编成 `C1`–`C7` 带状态；两个客户端 README 只留「契约 → 本框架落点」对照表 + 框架自身约束（`pre-step` 的 `await next()` 顺序、`aiohttp` 而非 `requests`）。
- **本机环境不入库**：工具链 / 模型槽位 / 具体路径属私有配置，文档一律用占位；`PLAN` §9.1 里的本机路径已删。

### 怎么复核

```powershell
# 旧标记应无残留
Select-String -Path docs\*.md,README.md,dsh-herodotus\README.md,astrbot_plugin_herodotus\README.md `
  -Pattern '【定】|【待考证】'
# 文档只回答一个问题的分工
Get-Content README.md | Select-String '只回答'
```

行数变化：`PLAN` 392 → 259，`ARCHITECTURE` 259 → 326（吸收 schema），`REFERENCES` 新建 111 行。

---

## 2026-10-22 · clio P1 落地：分词、关键词索引、导入导出，错误模型统一到 `expected`

**范围**：`clio/core/ledger` 重写读取侧；新增 `clio/core/text` · `clio/core/index` ·
`clio/core/transfer`；新增 `clio/tools/store_cli` 与 `clio/tests`（四组）；构建侧升级依赖与目标。

### 错误模型：`std::expected<std::error_code>` + 就近的 category

- 删掉早期的集中式 `core/error/`。每个模块自带 `*Errc` 枚举、`xxxCategory()` 与
  `makeError()`：`ledger` 的 `LedgerErrc`、`index` 的 `IndexErrc`、`transfer` 的 `TransferErrc`。
  错误码跟着它所属的模块走，别的模块要解释它时才引入它，而不是所有人依赖一个"大错误库"。
- 对外接口一律 `std::expected<T, std::error_code>`；参数校验、业务约束**直接返回**错误码，
  不用 `try/catch` 包裹（快速退出）。只在"跨越不可控边界"（SQLite / 文件系统 / 序列化）
  才抛 `Exception`。
- 事务不再手写 RAII 类，改用 jk 的 `JK::Meta::Cleanup` + `resetCleans(rollback)`：
  成功路径上把回滚动作清掉，异常路径由析构兜底。`appendL1Version` 即此形态。

### `core/error.cppm` 与 `core/easy.cppm`

- `Exception : std::system_error` 自带 `std::source_location`（构造时取默认实参）。
  口径：**绝大多数情况不传 `msg`**，靠 `location()` 定位；构造期不格式化字符串。
- `easy.cppm` 把 `JK::Meta` / `JK::Wrap` 提到 `herodotus::clio::easy` 内联命名空间，
  只给 `core/*` 用；`tools` / `daemon` / `tests` 保留显式 `import jk`。

### `core/text`：Tokenizer

- 去掉 pimpl 与单例：`Tokenizer(std::string dictDir)`，jieba 词典**懒加载**
  （`mutable std::optional<cppjieba::Jieba>`，首次 `jieba()` 时 `emplace`）。
  进程启动成本从"必付"变成"用到才付"。
- `decodeUtf8`：合法段整段交给 simdutf（`validate_utf8_with_errors` +
  `convert_utf8_to_utf32`）；非法段按 Unicode **最大子部分**规则只填**一个** U+FFFD。
  simdutf 9.1.1 没有 UTF-8 well-formed 接口（只有 `to_well_formed_utf16le/be`），故自己分段。
- `slice()` 改用 `simdutf::convert_utf32_to_utf8` 一次转换，删掉手写 `encodeUtf8`。

### `core/index`：FTS5 关键词索引

- `Index(indexPath, tokenizer)`：一个 `index.db` 一个实例，整文件可删可重建。
  `rebuildAll` / `rebuildIncremental` 以 watermark 为准，`indexedSeq` 读回水位。
- 构造时先 `PRAGMA busy_timeout=5000` —— 并发只读（多进程同时查）没有这个会直接
  `database is locked`。
- `search` 的 FTS 查询必须用**表名** `l1_fts`，不能给别名（SQLite 的 FTS5 语法限制）。
- 只索引每条记录的最新版本（`Hit` 带 `version` 与 bm25 原始分，越小越相关）。

### `core/transfer`：导出 / 导入

- `exportJsonl(store, outDir, ExportFilter)` → 两个 JSONL；筛选目前是**内存过滤**
  （persona / family / scene / `afterSeq`），下推 SQL 是已知优化点 🟡。
- `importJsonl(srcDir, store, ImportMode)`：`emptyOnly` 拒绝非空目标（`target_not_empty`）；
  `merge` 按 `(personaId, recordId)` 分组、组内按 `version` 升序，跳过目标已有的前缀，
  从 `n` 续接；`seq` 一律重分配。目前只按位置续接，**不做内容冲突检测**（`record_conflict`
  已预留）。
- 原 `core/exporter/` 删除，改名为 `transfer`，与"导入"对称。

### `tools/store_cli`

- 子命令：`append-l1` · `search` · `rebuild [--incremental]` · `dump` · `load` ·
  `verify` · `stats`。
- `printCause` 逐层 `rethrow_if_nested` 打印因果链，用 `dynamic_cast` 认自家 `Exception`
  并输出 `[file:line]`，**16 层上限**防自引用死循环。
- `--after-seq` 用 `.scan<'i', int>()`：argparse 内部按 `int` 取，写 `std::int64_t`
  会 `Bad any_cast`。

### `tests`

- 四组：`text_tests`（含非法 UTF-8 `"\xff\xfe温酒斩华雄"` 仍能切出「华雄」）、
  `ledger_tests`、`index_tests`、`transfer_tests`（导出 → 导入 → 幂等 → 非空拒绝 → persona 过滤）。
- 全部改成 expected 感知断言（先断言 `has_value()`，再查值）。

### 构建

- `VERSION` 0.1.0 → 0.2.0；`CMAKE_RUNTIME_OUTPUT_DIRECTORY` 设到 `${CMAKE_BINARY_DIR}`。
- `vcpkg.json`：`sqlite3` 加 `json1`；新增 `simdutf`、`jk[log,sqlite]`。
- `cmake/deps.cmake`：`find_package(simdutf)` / `find_package(jk)`；
  `target_link_libraries(herodotus)` 加 `joker::module`（PUBLIC）与 `simdutf::simdutf`（PRIVATE）。
- `tools/` 与 `tests/` 改成 `add_subdirectory`，测试接入 `include(CTest)`。

### 复核

```bash
cd clio
cmake --preset msys2 && cmake --build build-msys2 --config Debug
ctest --test-dir build-msys2 -C Debug
```

**4/4 通过** ✅。工具链相关的注意事项（为什么只能用 MSYS2 的 clang、asio 在 MinGW 下
缺的三个库、clang-cl 的嵌套异常两层限制）写在 `clio/README.md` 的「构建与工具链」一节。
