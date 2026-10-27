"""P1 / G1 验收：账本 → 索引 → 重建一致性。

判据（docs/PLAN.md 的 G1）：
  1. 写 N 条 → 删索引 → 重建 → 检索结果一致
  2. 同一 record_id 多版本折叠正确（只留最新，旧内容不再命中）
  3. 中文 FTS 可用
另外顺带验证：增量重建只处理新增版本、JSONL 导出行数与账本一致、账本自检通过。

用法：
    python scripts/p1_check.py
    python scripts/p1_check.py --data-dir .tmp/p1_check --json
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "clio" / "build-llvm"
DEFAULT_DICT = BUILD / "_deps" / "cppjieba-src" / "dict"


def default_cli() -> Path:
    """优先用 Release：Debug 下 jieba 词典加载要 3 秒，Release 约 0.7 秒。"""
    for config in ("Release", "RelWithDebInfo", "Debug"):
        candidate = BUILD / config / "store_cli.exe"
        if candidate.exists():
            return candidate
    return BUILD / "Debug" / "store_cli.exe"


class Checker:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.passed = 0

    def check(self, ok: bool, what: str) -> None:
        if ok:
            self.passed += 1
            print(f"  PASS  {what}")
        else:
            self.failures.append(what)
            print(f"  FAIL  {what}")


def run_cli(exe: Path, args: list[str], expect: int = 0) -> dict:
    proc = subprocess.run(
        [str(exe), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != expect:
        raise RuntimeError(
            f"store_cli 退出码 {proc.returncode}（期望 {expect}）\n"
            f"args: {args}\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
        )
    out = proc.stdout.strip()
    return json.loads(out) if out else {}


Hits = list[tuple[str, int]]


def search_batch(exe: Path, base: list[str], queries: list[str], persona: str) -> dict[str, Hits]:
    """一次进程查多个词（store_cli 每次启动都要加载分词词典，是主要耗时）。"""
    result = run_cli(exe, [*base, "--persona", persona, "search", *queries])
    return {
        item["query"]: [(hit["record_id"], hit["version"]) for hit in item["hits"]]
        for item in result["results"]
    }


def search_one(exe: Path, base: list[str], query: str, persona: str) -> Hits:
    return search_batch(exe, base, [query], persona)[query]


def snapshot(
    exe: Path,
    base: list[str],
    queries: list[str],
    personas: tuple[str, ...] = ("p-a", "p-b"),
) -> dict[tuple[str, str], Hits]:
    """并发查多个 persona，返回 {(persona, query): hits}。"""
    with ThreadPoolExecutor(max_workers=len(personas)) as pool:
        tables = list(pool.map(lambda p: search_batch(exe, base, queries, p), personas))
    return {
        (persona, query): hits
        for persona, table in zip(personas, tables)
        for query, hits in table.items()
    }


SEED = [
    ("p-a", "r-1", "温酒斩华雄"),
    ("p-a", "r-2", "革故鼎新，FTS5 关键词检索"),
    ("p-a", "r-3", "项目决定多媒体后置到 P4"),
    ("p-b", "r-4", "华雄是三国人物"),
    ("p-b", "r-5", "账本只增不可删"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="P1 / G1 验收")
    parser.add_argument("--store-cli", type=Path, default=None, help="默认取 Release，缺失时退回 Debug")
    parser.add_argument("--dict-dir", type=Path, default=DEFAULT_DICT)
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--json", action="store_true", help="末尾输出机器可读摘要")
    args = parser.parse_args()

    exe: Path = args.store_cli or default_cli()
    if not exe.exists():
        print(f"找不到 store_cli：{exe}", file=sys.stderr)
        return 2
    if not args.dict_dir.exists():
        print(f"找不到词典目录：{args.dict_dir}", file=sys.stderr)
        return 2

    data_dir: Path = args.data_dir or Path(tempfile.mkdtemp(prefix="clio-p1-check-"))
    if args.data_dir is not None:
        shutil.rmtree(data_dir, ignore_errors=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    base = ["--data-dir", str(data_dir), "--dict-dir", str(args.dict_dir)]
    c = Checker()

    print(f"data-dir: {data_dir}")

    # 1. 写入种子数据（串行：多进程同时写同一账本会 database is locked）
    print("\n[1] 写入种子数据")

    def seed(item: tuple[str, str, str]) -> dict:
        persona, record, content = item
        return run_cli(
            exe,
            [*base, "--persona", persona, "append-l1", "--record", record, "--content", content],
        )

    for item in SEED:
        seed(item)

    stats = run_cli(exe, [*base, "stats"])
    c.check(stats["l1_rows"] == len(SEED), f"账本 L1 行数 = {len(SEED)}")
    c.check(stats["docs"] == len(SEED), f"索引文档数 = {len(SEED)}")

    # 2/3 共用一次快照：重建前的检索结果就是「结果一致」的基线
    queries = ["华雄", "温酒", "FTS5", "账本", "多媒体"]
    before = snapshot(exe, base, queries)

    print("\n[2] 中文关键词检索")
    found = sorted([r for r, _ in before[("p-a", "华雄")]] + [r for r, _ in before[("p-b", "华雄")]])
    c.check(found == ["r-1", "r-4"], "中文词「华雄」在 p-a / p-b 各命中一条")
    c.check(before[("p-a", "华雄")] == [("r-1", 0)], "persona 隔离：p-a 只看到 r-1")
    c.check(before[("p-b", "温酒")] == [], "persona 隔离：p-b 搜不到 p-a 的「温酒」")

    # 3. 删索引 → 全量重建
    print("\n[3] 删索引 → 重建 → 结果一致")
    for suffix in ("", "-wal", "-shm"):
        (data_dir / f"index.db{suffix}").unlink(missing_ok=True)

    rebuilt = run_cli(exe, [*base, "rebuild"])
    c.check(rebuilt["docs"] == len(SEED), f"重建后文档数 = {len(SEED)}")

    after = snapshot(exe, base, queries)
    c.check(before == after, "重建前后五组查询结果完全一致")

    # 4. 多版本折叠
    print("\n[4] 同 record_id 多版本折叠")
    run_cli(exe, [*base, "--persona", "p-a", "append-l1", "--record", "r-1", "--content", "华雄被关羽斩杀", "--op", "edit"])
    folded = search_batch(exe, base, ["温酒", "关羽"], "p-a")
    c.check(folded["温酒"] == [], "旧版本内容「温酒」不再命中")
    c.check(folded["关羽"] == [("r-1", 1)], "新版本内容「关羽」命中 r-1 v1")
    stats = run_cli(exe, [*base, "stats"])
    c.check(stats["docs"] == len(SEED), "折叠后文档数不变")

    # 5. 增量重建
    print("\n[5] 增量重建")
    run_cli(exe, [*base, "--persona", "p-c", "append-l1", "--record", "r-6", "--content", "增量写入的测试记录", "--skip-index"])
    inc = run_cli(exe, [*base, "rebuild", "--incremental"])
    c.check(inc["processed"] == 1, f"只处理 1 条新增版本（实际 {inc['processed']}）")
    c.check(search_one(exe, base, "增量", "p-c") == [("r-6", 0)], "增量写入可检索")

    inc2 = run_cli(exe, [*base, "rebuild", "--incremental"])
    c.check(inc2["processed"] == 0, "再次增量重建无新版本")

    # 6. JSONL 导出
    print("\n[6] JSONL 导出")
    dump = run_cli(exe, [*base, "dump", "--out", str(data_dir / "dump")])
    c.check(dump["l1_rows"] == len(SEED) + 2, f"l1.jsonl 行数 = {len(SEED) + 2}")
    lines = (data_dir / "dump" / "l1.jsonl").read_text(encoding="utf-8").splitlines()
    c.check(len(lines) == len(SEED) + 2, "导出行数与账本一致")
    c.check(all(json.loads(line) for line in lines), "每行都是合法 JSON")

    # 7. 账本自检
    print("\n[7] 账本自检")
    report = run_cli(exe, [*base, "verify"])
    c.check(report["ok"] is True, "integrity_check 通过")
    c.check(report["l1_rows"] == len(SEED) + 2, "L1 行数一致")

    # 8. 导出 → 导入另一个账本 → 重建索引 → 检索一致
    print("\n[8] 导出 → 导入往返")
    restored_dir = data_dir / "restored"
    restored_base = ["--data-dir", str(restored_dir), "--dict-dir", str(args.dict_dir)]

    loaded = run_cli(exe, [*restored_base, "load", "--in", str(data_dir / "dump")])
    c.check(loaded["l1_rows"] == len(SEED) + 2, f"导入 L1 行数 = {len(SEED) + 2}")

    rebuilt = run_cli(exe, [*restored_base, "rebuild"])
    c.check(rebuilt["docs"] == len(SEED) + 1, f"导入后重建文档数 = {len(SEED) + 1}（r-1 两版本折叠）")

    restored = snapshot(exe, restored_base, ["关羽", "温酒"], personas=("p-a",))
    c.check(restored[("p-a", "关羽")] == [("r-1", 1)], "导入后版本链与检索结果一致")
    c.check(restored[("p-a", "温酒")] == [], "导入后旧版本内容仍不命中")

    run_cli(exe, [*restored_base, "load", "--in", str(data_dir / "dump")], expect=3)
    c.check(True, "导入: 非空目标拒绝 emptyOnly")

    # 汇总
    total = c.passed + len(c.failures)
    print(f"\n{'-' * 50}")
    print(f"{c.passed}/{total} 项通过")
    if c.failures:
        for item in c.failures:
            print(f"  FAILED: {item}")
        if args.json:
            print(json.dumps({"ok": False, "passed": c.passed, "failed": c.failures}, ensure_ascii=False))
        return 1

    if args.json:
        print(json.dumps({"ok": True, "passed": c.passed, "data_dir": str(data_dir)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
