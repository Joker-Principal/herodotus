#!/usr/bin/env python3
"""P0 蒸馏 L1 spike：用 llama-server 的 OpenAI 兼容接口跑 L1 抽取，并对标注用例打分。

评测口径（对应 PLAN G2）：
- 覆盖：标注的期望事实是否出现在抽取结果中（must_contain 全部命中）
- 噪声：不应提取的内容是否被提取（forbid）
- 碎片化：强关联事实是否被拆成多条（max_matched）
- JSON 合法性：模型输出能否被解析为情境数组

用法：
    python scripts/distill_spike.py --model Qwen3-14B-abliterated.Q5_K_M
    python scripts/distill_spike.py --model RVN-Q3_K_M-multilingual --json
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ROOT / "clio" / "tests" / "data" / "distill_l1_cases.json"
DEFAULT_PROMPT = ROOT / "scripts" / "prompts" / "l1_extraction.txt"


def format_user_prompt(messages):
    """与参考实现 formatExtractionPrompt 同格式（背景为空）。"""
    lines = []
    for m in messages:
        iso = _iso(m["timestamp"])
        lines.append(f"[{m['id']}] [{m['role']}] [{iso}]: {m['content']}")
    return (
        '**输出语言**：根据下方"待提取的新消息"中 user 发言的主导语言书写 `scene_name` 和 memory `content`。\n\n'
        "【上一个情境】：无\n\n"
        "【背景对话】（仅供理解上下文推断关系/时间，严禁从中提取记忆）：\n无\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "【待提取的新消息】（务必结合 timestamp 推算时间，只从这里提取记忆！）：\n" + "\n\n".join(lines)
    )


def _iso(ms):
    from datetime import datetime, timezone

    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def call_llm(base_url, model, system, user, temperature, max_tokens, timeout):
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    req = urllib.request.Request(
        base_url.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def parse_scenes(raw):
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("```")[1]
        if s.startswith("json"):
            s = s[4:]
    start, end = s.find("["), s.rfind("]")
    if start < 0 or end < 0:
        raise ValueError("输出中找不到 JSON 数组")
    return json.loads(s[start : end + 1])


def main(argv=None):
    ap = argparse.ArgumentParser(description="P0 蒸馏 L1 spike")
    ap.add_argument("--base-url", default="http://127.0.0.1:11434")
    ap.add_argument("--model", required=True, help="llama-server 的模型 id（见 /v1/models）")
    ap.add_argument("--cases", default=str(DEFAULT_CASES))
    ap.add_argument("--prompt", default=None, help="覆盖所有档位的 system prompt 路径")
    ap.add_argument("--prompt-dir", default=str(DEFAULT_PROMPT.parent), help="按 mode 取 l1_extraction_<mode>.txt")
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--max-tokens", type=int, default=2048)
    ap.add_argument("--timeout", type=float, default=300)
    ap.add_argument("--json", action="store_true", help="输出机器可读汇总")
    args = ap.parse_args(argv)

    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    prompt_cache = {}

    def load_prompt(mode):
        if mode not in prompt_cache:
            path = Path(args.prompt) if args.prompt else Path(args.prompt_dir) / f"l1_extraction_{mode}.txt"
            prompt_cache[mode] = path.read_text(encoding="utf-8")
        return prompt_cache[mode]

    total_expect = total_hit = total_noise = total_parse_fail = 0
    report = []

    for case in cases:
        mode = case.get("mode", "chat")
        raw = ""
        try:
            raw = call_llm(
                args.base_url,
                args.model,
                load_prompt(mode),
                format_user_prompt(case["messages"]),
                args.temperature,
                args.max_tokens,
                args.timeout,
            )
            scenes = parse_scenes(raw)
            parse_ok = True
        except Exception as e:  # noqa: BLE001
            scenes, parse_ok = [], False
            total_parse_fail += 1
            err = str(e)

        memories = [m for sc in scenes for m in sc.get("memories", []) if isinstance(m, dict)]
        contents = [str(m.get("content", "")) for m in memories]

        expect_rows = []
        for e in case.get("expect", []):
            hit = any(all(k in c for k in e["must_contain"]) for c in contents)
            expect_rows.append({"key": e["key"], "hit": hit})
            total_expect += 1
            total_hit += hit

        noise = []
        for f in case.get("forbid", []):
            if any(all(k in c for k in f["must_contain"]) for c in contents):
                noise.append(f["desc"])
        total_noise += len(noise)

        problems = []
        if not parse_ok:
            problems.append(f"JSON 解析失败: {err}")
        if "min_scenes" in case and len(scenes) < case["min_scenes"]:
            problems.append(f"情境数 {len(scenes)} < {case['min_scenes']}")
        if "max_total" in case and len(memories) > case["max_total"]:
            problems.append(f"记忆数 {len(memories)} > {case['max_total']}")
        for e in case.get("expect", []):
            if "max_matched" in case:
                n = sum(1 for c in contents if all(k in c for k in e["must_contain"]))
                if n > case["max_matched"]:
                    problems.append(f"{e['key']} 被拆成 {n} 条（> {case['max_matched']}）")

        report.append(
            {
                "case": case["name"],
                "mode": mode,
                "parse_ok": parse_ok,
                "scenes": len(scenes),
                "memories": len(memories),
                "memories_detail": [
                    {"type": str(m.get("type", "")), "content": str(m.get("content", ""))} for m in memories
                ],
                "expect": expect_rows,
                "noise": noise,
                "problems": problems,
                "raw": raw if not parse_ok else None,
            }
        )

    if args.json:
        print(
            json.dumps(
                {
                    "model": args.model,
                    "cases": report,
                    "summary": {
                        "expect_total": total_expect,
                        "expect_hit": total_hit,
                        "noise": total_noise,
                        "parse_fail": total_parse_fail,
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for r in report:
            status = "OK" if not (r["problems"] or r["noise"]) and all(e["hit"] for e in r["expect"]) else "CHECK"
            print(f"[{status}] {r['case']} ({r['mode']}) · 情境 {r['scenes']} · 记忆 {r['memories']}")
            for m in r["memories_detail"]:
                print(f"    · [{m['type']}] {m['content'][:110]}")
            for e in r["expect"]:
                print(f"    {'✓' if e['hit'] else '✗'} {e['key']}")
            if r["noise"]:
                print(f"    噪声: {', '.join(r['noise'])}")
            for p in r["problems"]:
                print(f"    ! {p}")
            if r["raw"]:
                print(f"    原始输出: {r['raw'][:500]}")
        print()
        pct = total_hit / total_expect * 100 if total_expect else 0
        print(
            f"汇总：覆盖 {total_hit}/{total_expect} ({pct:.0f}%) · 噪声 {total_noise} · "
            f"JSON 失败 {total_parse_fail}/{len(cases)}"
        )

    ok = total_hit == total_expect and total_noise == 0 and total_parse_fail == 0
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
