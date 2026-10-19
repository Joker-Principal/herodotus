#!/usr/bin/env python3
"""clioctl —— clio 的构建 / 起停 / 冒烟统一入口。

    python scripts/clioctl.py build [--release]                      # configure + build（llvm preset）
    python scripts/clioctl.py start [--port 7788] [--data-dir ...]   # 后台启动，写 pid 文件 + 日志
    python scripts/clioctl.py stop                                   # 停止（读 pid 文件）
    python scripts/clioctl.py status [--port 7788]                   # 探测 /health
    python scripts/clioctl.py smoke [--release] [--keep]             # 全自动起停自检

P0 验收门 G0「clio 起停正常」由 `smoke` 自动化：
起进程 → 等 /health → 校验 protocol / version / 账本落盘 → 优雅停止 → 退出码汇总。

约定（见 scripts/README.md）：
- 构建一律走 clang-cl 的 llvm preset（MSVC 编不过 C++20 模块 + asio）。
- 运行产物（pid / 日志 / 默认数据目录）都在 <repo>/.run/ 下，已被 .gitignore 覆盖。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # herodotus 主仓库根
CLIO_DIR = ROOT / "clio"
BUILD_DIR = CLIO_DIR / "build-llvm"
RUN_DIR = ROOT / ".run"
IS_WINDOWS = os.name == "nt"

DEFAULT_PORT = 7788
DEFAULT_DATA_DIR = ".run/data"


def exe_path(config: str) -> Path:
    return BUILD_DIR / config / ("clio.exe" if IS_WINDOWS else "clio")


def pid_file(data_dir: Path) -> Path:
    return data_dir.parent / f"{data_dir.name}.pid"


def log_file(data_dir: Path) -> Path:
    return data_dir.parent / f"{data_dir.name}.log"


def read_pid(data_dir: Path) -> int | None:
    pf = pid_file(data_dir)
    if not pf.exists():
        return None
    try:
        return int(pf.read_text(encoding="utf-8").strip())
    except ValueError:
        return None


def process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)  # Windows 上 sig=0 即存在性探测
        return True
    except OSError:
        return False


def health(port: int, timeout: float = 2.0):
    """GET /health；返回解析后的 JSON，失败返回 None。"""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def wait_healthy(port: int, seconds: float):
    """轮询 /health 直到超时（秒）。"""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        body = health(port)
        if body is not None:
            return body
        time.sleep(0.1)
    return None


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    print("+", " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run(cmd, **kw)


def kill_tree(pid: int) -> None:
    if IS_WINDOWS:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True
        )
    else:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def launch(exe: Path, port: int, data_dir: Path, background: bool):
    """起 clio。background=True 用后台旗标（无窗口、新进程组），否则继承控制台（smoke 用，便于 CTRL_C）。"""
    flags = 0
    if IS_WINDOWS:
        flags |= subprocess.CREATE_NEW_PROCESS_GROUP
        if background:
            flags |= subprocess.CREATE_NO_WINDOW
    data_dir.mkdir(parents=True, exist_ok=True)
    log = log_file(data_dir).open("a", encoding="utf-8")
    return subprocess.Popen(
        [
            str(exe),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--data-dir",
            str(data_dir),
        ],
        cwd=ROOT,
        stdout=log,
        stderr=subprocess.STDOUT,
        creationflags=flags,
    )


# ---------------------------------------------------------------------------
# 子命令
# ---------------------------------------------------------------------------

def cmd_build(args: argparse.Namespace) -> int:
    r = run(["cmake", "--preset", "llvm"], cwd=CLIO_DIR)
    if r.returncode:
        return r.returncode
    build_preset = "llvm-release" if args.release else "llvm-debug"
    r = run(["cmake", "--build", "--preset", build_preset], cwd=CLIO_DIR)
    return r.returncode


def cmd_start(args: argparse.Namespace) -> int:
    data_dir = (ROOT / args.data_dir).resolve()
    pid = read_pid(data_dir)
    if pid is not None and process_alive(pid):
        print(f"[start] clio 已在运行（pid={pid}），先 `stop` 再启", file=sys.stderr)
        return 1
    exe = exe_path("Release" if args.release else "Debug")
    if not exe.exists():
        print(f"[start] 找不到 {exe}，先 `python scripts/clioctl.py build`", file=sys.stderr)
        return 1

    proc = launch(exe, args.port, data_dir, background=True)
    if wait_healthy(args.port, 10) is None:
        print(f"[start] 10 秒内 /health 无响应，已终止；日志见 {log_file(data_dir)}", file=sys.stderr)
        kill_tree(proc.pid)
        proc.wait()
        return 1

    pid_file(data_dir).write_text(str(proc.pid), encoding="utf-8")
    print(f"[start] clio pid={proc.pid}  http://127.0.0.1:{args.port}  （日志 {log_file(data_dir)}）")
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    data_dir = (ROOT / args.data_dir).resolve()
    pid = read_pid(data_dir)
    if pid is None:
        print("[stop] 没有 pid 文件——clio 未在运行", file=sys.stderr)
        return 1
    if process_alive(pid):
        print(f"[stop] 停止 clio pid={pid}")
        kill_tree(pid)
    pid_file(data_dir).unlink(missing_ok=True)
    print("[stop] 已停止")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    body = health(args.port)
    if body is None:
        print("[status] 未运行（/health 无响应）", file=sys.stderr)
        return 1
    print(json.dumps(body, ensure_ascii=False, indent=2))
    return 0


def cmd_smoke(args: argparse.Namespace) -> int:
    config = "Release" if args.release else "Debug"
    exe = exe_path(config)
    if not exe.exists():
        print(f"[smoke] 找不到 {exe}，先 `python scripts/clioctl.py build`", file=sys.stderr)
        return 1

    results: list[bool] = []

    def step(name: str, ok: bool, detail: str = "") -> None:
        results.append(ok)
        print(("PASS " if ok else "FAIL ") + name + (f"  — {detail}" if detail else ""), flush=True)

    tmp = Path(tempfile.mkdtemp(prefix="clio-smoke-"))
    port = free_port()
    proc = launch(exe, port, tmp / "data", background=False)

    try:
        body = wait_healthy(port, 15)
        step("启动并响应 /health", body is not None)
        if body is None:
            logf = log_file(tmp / "data")
            print(f"[smoke] 进程输出见 {logf}", file=sys.stderr)
            print(logf.read_text(encoding="utf-8", errors="replace"))
            return 1
        step("protocol == 1", body.get("protocol") == 1, f"protocol={body.get('protocol')}")
        step("version 非空", bool(body.get("version")), f"version={body.get('version')}")
        step("账本已落盘（probe 生效）", (tmp / "data" / "ledger.db").exists())

        # 未注册路径应由 pylai 框架回 404
        code = None
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/nope", timeout=2.0) as resp:
                code = resp.status
        except urllib.error.HTTPError as e:
            code = e.code
        except (urllib.error.URLError, OSError):
            code = None
        step("未注册路径 404", code == 404, f"GET /nope -> {code}")

        # 停止。Windows 下 ConPTY 环境控制台事件不可靠（CTRL_C 发不达进程，
        # 实测日志无 signal 记录），故一律强杀并靠「同目录重启」验证账本可恢复；
        # POSIX 走 SIGINT 优雅路径（pylai 的 run() 收到后退出码 0）。
        if not IS_WINDOWS:
            proc.send_signal(signal.SIGINT)
            try:
                rc = proc.wait(timeout=5)
                step("优雅停止（exit 0）", rc == 0, f"exit={rc}")
            except subprocess.TimeoutExpired:
                kill_tree(proc.pid)
                rc = proc.wait()
                step("优雅停止（exit 0）", False, f"SIGINT 超时已强杀 exit={rc}")
        else:
            kill_tree(proc.pid)
            rc = proc.wait()
            step("停止（强杀，P4 前无管理端点）", rc is not None, f"exit={rc}")

        # 第二轮：同一数据目录重启——验证强杀后账本完好（WAL 恢复），G0 的「起停正常」收口。
        proc2 = launch(exe, port, tmp / "data", background=False)
        body2 = wait_healthy(port, 15)
        step("重启同目录 /health 正常", body2 is not None)
        if body2 is not None:
            step("重启后 protocol 一致", body2.get("protocol") == body.get("protocol"))
        if not IS_WINDOWS:
            proc2.send_signal(signal.SIGINT)
        else:
            kill_tree(proc2.pid)
        try:
            proc2.wait(timeout=5)
        except subprocess.TimeoutExpired:
            kill_tree(proc2.pid)
            proc2.wait()
    finally:
        for p in (proc, locals().get("proc2")):
            if p is not None and p.poll() is None:
                kill_tree(p.pid)
                p.wait()
        if args.keep:
            print(f"[smoke] 临时目录保留：{tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)

    passed = sum(results)
    print(f"[smoke] {'PASS' if passed == len(results) else 'FAIL'}（{passed}/{len(results)}）")
    return 0 if passed == len(results) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="clioctl", description="clio 的构建 / 起停 / 冒烟统一入口（P0）"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("build", help="configure + build（llvm preset，clang-cl）")
    p.add_argument("--release", action="store_true", help="构建 Release 而非 Debug")
    p.set_defaults(fn=cmd_build)

    p = sub.add_parser("start", help="后台启动 clio")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--data-dir", default=DEFAULT_DATA_DIR)
    p.add_argument("--release", action="store_true", help="用 Release 二进制")
    p.set_defaults(fn=cmd_start)

    p = sub.add_parser("stop", help="停止 clio（读 pid 文件）")
    p.add_argument("--data-dir", default=DEFAULT_DATA_DIR)
    p.set_defaults(fn=cmd_stop)

    p = sub.add_parser("status", help="探测 /health")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("smoke", help="全自动起停自检（G0 的自动化形态）")
    p.add_argument("--release", action="store_true", help="用 Release 二进制")
    p.add_argument("--keep", action="store_true", help="保留临时数据目录")
    p.set_defaults(fn=cmd_smoke)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
