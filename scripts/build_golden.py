#!/usr/bin/env python3
"""从参考实现的 DSH-MemBench 场景库生成 Herodotus 黄金语料集。

口径：
- 语料 = 每个场景的会话消息（teach / reinforce / change），一行一条；
- 查询 = 每个场景的探针（probe），带 gold 要点与 stale（更新题）。
- 只取对话赛道（bench/scenarios/*.json）；工作流场景（任务延续）不进检索基准。

输出（入库，体积小、可复核）：
    clio/tests/data/golden/corpus.jsonl
    clio/tests/data/golden/queries.jsonl

用法：
    python scripts/build_golden.py [--src <dsh-layered-memory>] [--out <dir>]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SRC = ROOT / ".reference" / "dsh-layered-memory"
DEFAULT_OUT = ROOT / "clio" / "tests" / "data" / "golden"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="生成黄金语料集")
    ap.add_argument("--src", default=str(DEFAULT_SRC))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args(argv)

    src = Path(args.src) / "bench" / "scenarios"
    out = Path(args.out)
    if not src.is_dir():
        print(f"找不到场景库：{src}", file=sys.stderr)
        return 1

    corpus, queries = [], []
    for f in sorted(src.glob("*.json")):
        sc = json.loads(f.read_text(encoding="utf-8"))
        sid = sc["id"]
        family = sc.get("family", "")
        for si, sess in enumerate(sc.get("sessions", [])):
            kind = sess.get("kind", "")
            for mi, text in enumerate(sess.get("messages", [])):
                corpus.append(
                    {"id": f"{sid}-{si}-{mi}", "scene": sid, "family": family, "kind": kind, "text": text}
                )
        for qi, p in enumerate(sc.get("probes", [])):
            queries.append(
                {
                    "id": f"{sid}-{qi}",
                    "scene": sid,
                    "type": p.get("type", ""),
                    "query": p.get("q", ""),
                    "gold": p.get("gold", []),
                    "stale": p.get("stale", []),
                }
            )

    out.mkdir(parents=True, exist_ok=True)
    (out / "corpus.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in corpus), encoding="utf-8"
    )
    (out / "queries.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in queries), encoding="utf-8"
    )

    scenes = {r["scene"] for r in corpus}
    types = Counter(r["type"] for r in queries)
    with_gold = sum(1 for r in queries if r["gold"])
    print(f"场景 {len(scenes)} · 语料 {len(corpus)} 条 · 查询 {len(queries)} 条（带 gold {with_gold}）")
    print("题型分布：" + ", ".join(f"{k}={v}" for k, v in sorted(types.items())))
    print(f"输出：{out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
