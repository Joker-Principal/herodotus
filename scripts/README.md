# scripts/ —— 构建 · 起停 · 冒烟

P0 交付物之一（见 `docs/PLAN.md` §2.2 / §7）。统一入口是 **`clioctl.py`**（Python 3.9+，只用标准库）：

```powershell
python scripts/clioctl.py build                # configure + build（llvm preset）
python scripts/clioctl.py start                # 后台启动，写 pid 文件 + 日志
python scripts/clioctl.py stop                 # 停止（读 pid 文件）
python scripts/clioctl.py status               # 探测 /health
python scripts/clioctl.py smoke                # 全自动起停自检
```

## smoke 与 G0

`docs/PLAN.md` 的验收门 **G0「`clio` 起停正常」**由 `smoke` 自动化：

```
起进程（临时数据目录 + 空闲端口）
  → 等 /health 200
  → 校验 protocol == 1、version 非空
  → 校验账本落盘（ledger.db 存在，即 ledger::probe 生效）
  → 校验未注册路径 404（pylai 框架行为）
  → 停止（Windows 强杀 / POSIX SIGINT）
  → 同目录重启 → /health 正常（验证强杀后账本完好、WAL 恢复）
  → 清理临时目录
```

退出码：全过为 0，否则为 1。

## 蒸馏 L1 spike

```powershell
python scripts/distill_spike.py --model qwen3.8-27b-rvn
python scripts/distill_spike.py --model qwen3-14b --json
```

`--model` 用 llama-server 暴露的 id（即 `llama-router.ini` 的 section 名），不是 GGUF 文件名。

- 用例：`clio/tests/data/distill_l1_cases.json`，每个用例带 `mode: chat|work|auto`
- prompt：`scripts/prompts/l1_extraction_<mode>.txt`（移植自 `dsh-layered-memory`，见 NOTICE）
- 指标：覆盖（期望事实是否提取）/ 噪声（不该提取的项）/ 碎片化（强关联是否被拆）/ JSON 合法性
- 依赖本机 llama-server（OpenAI 兼容接口），请求里关闭 `enable_thinking`

## 黄金语料集

```powershell
python scripts/build_golden.py
```

从 `.reference/dsh-layered-memory/bench/scenarios/` 生成 `clio/tests/data/golden/`（语料 + 查询 + 金标），
用于 P3 检索基准。口径与重新生成方式见 `clio/tests/data/golden/README.md`。

## 约定

- **构建一律走 llvm preset（clang-cl）**：MSVC 编不过「C++20 模块 + asio」（C2039 / C2504 /
  C7637，IFC 缺陷），见 `docs/PLAN.md` 与用户工作区说明。
- **运行产物都在 `<repo>/.run/`**（已被 `.gitignore` 的 `/.*/` 覆盖）：
  - `start` 默认数据目录 `.run/data`、pid 文件 `.run/data.pid`、日志 `.run/data.log`；
  - 换数据目录用 `--data-dir`（start 与 stop 须用同一个值）。
