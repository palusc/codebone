"""A/B benchmark: same messy project, same 3-task prompt, Claude Code without vs. with codebone.

Run with the codebone venv (needs fastapi/uvicorn/mcp):
    ~/Library/Application\\ Support/codebone/venv/bin/python3 benchmark/run_benchmark.py [--runs 3] [--brain fallback|builtin] [--model sonnet]

Per run it: generates a fresh project copy, (with-mode) starts an isolated headless codebone on a free port
and indexes the copy, runs `claude -p` once, then verifies the 3 tasks with check.py.
Records wall time, turns, tokens (input/output/cache) and cost from Claude's JSON result.
Isolated on purpose: it never touches your running menu bar app or your MCP configs.
"""
import argparse
import json
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))

CB_CLAUDE_MD = """# Project guidelines
## Shortcut: `cb`
When the prompt starts with `cb`, first call the MCP tool `cb()` to get the project's live architectural context
(domains, models, routes, events, file summaries). Use it instead of reading many files. For focused context call
`cb(domain=...)`, `cb(file=...)` or `cb(query=...)`.
"""


def make_project(dst: Path):
    subprocess.run([sys.executable, str(HERE / "make_project.py"), str(dst)], check=True)


def start_codebone(project: Path, brain: str, workdir: Path):
    """Headless, isolated codebone: own config/db dir, no MCP-config patching. Returns (port, index_seconds, stop)."""
    import uvicorn
    from src.config import Config, find_free_port
    from src.providers import FastFallbackProvider
    from src.server import create_app
    from src.service import CodeBoneService

    cfg = Config(config_file=workdir / "cb" / "config.json")
    cfg.set("project_path", str(project))
    from src.config import BASE_MODEL_FILE
    cached = Path.home() / "Library" / "Caches" / "codebone-build" / BASE_MODEL_FILE  # left there by build_bundle.sh
    if not Path(cfg.get("model_path", "")).exists() and cached.exists():
        cfg.set("model_path", str(cached))
    service = CodeBoneService(cfg)
    if brain == "fallback" or not service.provider.available:
        service.provider = FastFallbackProvider()
    t0 = time.time()
    service.rescan_all()
    index_s = time.time() - t0

    port = find_free_port(18053)
    cfg.set("active_port", port)
    server = uvicorn.Server(uvicorn.Config(create_app(service), host="127.0.0.1", port=port, log_level="warning", lifespan="off"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.1)

    def stop():
        server.should_exit = True
        service.stop()

    return port, index_s, stop


def run_claude(project: Path, prompt: str, mcp_port, model):
    cmd = ["claude", "-p", prompt, "--output-format", "json", "--no-session-persistence",
           "--permission-mode", "acceptEdits", "--strict-mcp-config"]
    tools = "Read Edit Write Glob Grep Bash(python3:*) Bash(ls:*) Bash(cat:*) Bash(grep:*) Bash(find:*)"
    if mcp_port:
        mcp = {"mcpServers": {"codebone": {
            "command": sys.executable, "args": ["-m", "codebone_mcp.server"],
            "env": {"CODEBONE_PORT": str(mcp_port), "PYTHONPATH": str(REPO)}}}}
        cfg_path = project.parent / "mcp.json"
        cfg_path.write_text(json.dumps(mcp))
        cmd += ["--mcp-config", str(cfg_path)]
        tools += " mcp__codebone"
    cmd += ["--allowedTools", tools]
    if model:
        cmd += ["--model", model]
    t0 = time.time()
    p = subprocess.run(cmd, cwd=project, capture_output=True, text=True, timeout=1200)
    wall = time.time() - t0
    try:
        out = json.loads(p.stdout)
    except json.JSONDecodeError:
        return {"error": (p.stdout + p.stderr)[-500:], "wall_s": wall}
    u = out.get("usage", {})
    fresh_in = u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
    return {
        "wall_s": round(wall, 1),
        "api_s": round(out.get("duration_api_ms", 0) / 1000, 1),
        "turns": out.get("num_turns"),
        "input": u.get("input_tokens", 0),
        "cache_write": u.get("cache_creation_input_tokens", 0),
        "cache_read": u.get("cache_read_input_tokens", 0),
        "output": u.get("output_tokens", 0),
        "fresh_in_plus_out": fresh_in + u.get("output_tokens", 0),
        "cost_usd": round(out.get("total_cost_usd", 0), 4),
    }


def check(project: Path):
    p = subprocess.run([sys.executable, str(HERE / "check.py"), str(project)], capture_output=True, text=True)
    try:
        return json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:
        return {"vat": False, "phone": False, "token": False}


def one_run(mode: str, prompt: str, brain: str, model):
    tmp = Path(tempfile.mkdtemp(prefix=f"cbbench-{mode}-"))
    project = tmp / "shop"
    make_project(project)
    port = stop = None
    index_s = 0.0
    if mode == "with":
        (project / "CLAUDE.md").write_text(CB_CLAUDE_MD)
        port, index_s, stop = start_codebone(project, brain, tmp)
        prompt = "cb: " + prompt
    try:
        res = run_claude(project, prompt, port, model)
    finally:
        if stop:
            stop()
    res["index_s"] = round(index_s, 1)
    res["passed"] = check(project)
    res["tasks_ok"] = sum(res["passed"].values())
    shutil.rmtree(tmp, ignore_errors=True)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--brain", choices=["fallback", "builtin"], default="fallback",
                    help="fallback = regex indexer (fast, reproducible); builtin = local Qwen model")
    ap.add_argument("--model", default=None)
    args = ap.parse_args()
    prompt = (HERE / "prompt.txt").read_text().strip()

    results = {"without": [], "with": []}
    for i in range(args.runs):
        for mode in ("without", "with"):  # interleaved so drift hits both equally
            print(f"[run {i + 1}/{args.runs}] {mode} codebone ...", flush=True)
            r = one_run(mode, prompt, args.brain, args.model)
            print("   ", r, flush=True)
            results[mode].append(r)

    def med(mode, key):
        vals = [r[key] for r in results[mode] if key in r]
        return statistics.median(vals) if vals else float("nan")

    keys = ["wall_s", "turns", "fresh_in_plus_out", "output", "cache_read", "cost_usd", "tasks_ok"]
    print(f"\nMedian over {args.runs} run(s)  (index time with codebone: {med('with', 'index_s')}s, not counted in wall_s)")
    print(f"{'metric':<20}{'without':>12}{'with':>12}{'delta':>10}")
    for k in keys:
        a, b = med("without", k), med("with", k)
        d = f"{(b - a) / a * 100:+.0f}%" if a else "n/a"
        print(f"{k:<20}{a:>12}{b:>12}{d:>10}")
    (HERE / "results.json").write_text(json.dumps(results, indent=2))
    print(f"\nRaw results: {HERE / 'results.json'}")


if __name__ == "__main__":
    main()
