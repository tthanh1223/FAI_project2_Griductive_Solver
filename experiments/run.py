"""Run the agent on every puzzle and write experiments/results/results.csv.

Owner: Lead.

Columns: id, rows, cols, agent, primary_vars, aux_vars, clauses, sat_calls, decisions,
propagations, backtracks, steps, waves, time, status (OK / STUCK / INCONSISTENT / TIMEOUT / ERROR).
agent = "optimized" (LogicAgent()) or "baseline" (LogicAgent(optimized=False)).
waves = generator difficulty (puzzles/generate.py), empty for hand-written puzzles.
time = seconds spent by the agent (encoder + DPLL), from SolveResult["stats"].
Failures and timeouts stay in the table.

Also writes experiments/results/summary.md (mean per board size and agent) and
two charts: sat_calls.png, time.png.

Usage: python experiments/run.py [--timeout 60] [--agent both|optimized|baseline] [puzzle.json ...]
Input / output of every function: docs/INTERFACES.md.
"""
import argparse
import csv
import multiprocessing as mp
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "experiments" / "results"
COLUMNS = ["id", "rows", "cols", "agent", "primary_vars", "aux_vars", "clauses", "sat_calls",
           "decisions", "propagations", "backtracks", "steps", "waves", "time", "status"]
STATUS = {"SOLVED": "OK", "STUCK": "STUCK", "INCONSISTENT": "INCONSISTENT"}


def solve_one(path: str, optimized: bool) -> dict:
    """One puzzle, one agent -> one CSV row (runs inside a worker process)."""
    sys.path.insert(0, str(ROOT))
    import json
    from agent import LogicAgent
    from engine import GameEngine
    from model import load_puzzle

    puzzle = load_puzzle(path)
    engine = GameEngine(puzzle, LogicAgent(optimized=optimized))
    agent = engine.agent                      # engine.submit reuses this agent's classify
    agent.reset_stats()
    result = agent.solve(engine)
    st, kb = result["stats"], result["kb_stats"]
    difficulty = json.loads(Path(path).read_text(encoding="utf-8")).get("difficulty") or {}
    return {
        "primary_vars": kb["primary"], "aux_vars": kb["aux"], "clauses": kb["clauses"],
        "sat_calls": st["sat_calls"], "decisions": st["decisions"],
        "propagations": st["propagations"], "backtracks": st["backtracks"],
        "steps": len(result["steps"]), "waves": difficulty.get("waves", ""),
        "time": round(st["time"], 4), "status": STATUS[result["status"]],
    }


def run_with_timeout(path: Path, optimized: bool, timeout: float) -> dict:
    """solve_one in a separate process, so a slow puzzle can be stopped."""
    with mp.get_context("spawn").Pool(1) as pool:
        job = pool.apply_async(solve_one, (str(path), optimized))
        try:
            return job.get(timeout)
        except mp.TimeoutError:
            pool.terminate()
            return {"status": "TIMEOUT", "time": timeout}
        except Exception as e:                # loading / engine / agent error: keep the row
            return {"status": "ERROR", "error": f"{type(e).__name__}: {e}"}


def board_info(path: Path) -> tuple[str, int, int]:
    import json
    p = json.loads(path.read_text(encoding="utf-8"))
    return p.get("id", path.stem), p.get("rows", p.get("size")), p.get("cols", p.get("size"))


def summarize(rows: list[dict]) -> str:
    """Markdown table: mean of every number per (board size, agent), OK rows only."""
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        if r["status"] == "OK":
            groups.setdefault((r["primary_vars"], f'{r["cols"]}x{r["rows"]}', r["agent"]), []).append(r)
    keys = ["aux_vars", "clauses", "steps", "sat_calls", "decisions", "propagations", "backtracks", "time"]
    lines = ["| size | agent | n | " + " | ".join(keys) + " |", "|" + "---|" * (len(keys) + 3)]
    for (_, size, agent), rs in sorted(groups.items()):
        cells = []
        for k in keys:
            mean = sum(float(r[k]) for r in rs) / len(rs)
            cells.append(f"{mean:.3f}" if k == "time" else f"{mean:.1f}")
        lines.append(f"| {size} | {agent} | {len(rs)} | " + " | ".join(cells) + " |")
    bad = [r for r in rows if r["status"] != "OK"]
    lines.append("")
    lines.append(f"Not OK: {len(bad)}" + "".join(f"\n- {r['id']} ({r['agent']}): {r['status']}" for r in bad))
    return "\n".join(lines) + "\n"


def plot(rows: list[dict]) -> list[Path]:
    """sat_calls and time against the number of cells, one series per agent."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed: no charts")
        return []
    out = []
    for key, label, log in (("sat_calls", "SAT calls per puzzle", False),
                            ("time", "agent time per puzzle (s)", True)):
        fig, ax = plt.subplots(figsize=(6, 4))
        for agent, marker in (("baseline", "o"), ("optimized", "s")):
            pts = [(r["primary_vars"], float(r[key])) for r in rows if r["agent"] == agent and r["status"] == "OK"]
            if pts:
                ax.scatter(*zip(*pts), label=agent, marker=marker, alpha=0.75)
        ax.set_xlabel("cells (primary variables)")
        ax.set_ylabel(label)
        if log:
            ax.set_yscale("log")
        ax.grid(alpha=0.3)
        ax.legend()
        fig.tight_layout()
        path = RESULTS / f"{key}.png"
        fig.savefig(path, dpi=150)
        plt.close(fig)
        out.append(path)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("puzzles", nargs="*", help="puzzle files (default: puzzles/*.json)")
    ap.add_argument("--timeout", type=float, default=60, help="seconds per puzzle and agent")
    ap.add_argument("--agent", choices=["both", "optimized", "baseline"], default="both")
    args = ap.parse_args()

    paths = [Path(p) for p in args.puzzles] or sorted((ROOT / "puzzles").glob("*.json"))
    agents = {"both": [True, False], "optimized": [True], "baseline": [False]}[args.agent]
    RESULTS.mkdir(parents=True, exist_ok=True)

    rows = []
    for path in paths:
        pid, r, c = board_info(path)
        for optimized in agents:
            row = {"id": pid, "rows": r, "cols": c, "agent": "optimized" if optimized else "baseline"}
            row.update(run_with_timeout(path, optimized, args.timeout))
            rows.append(row)
            note = f"  {row['error']}" if "error" in row else ""
            print(f"{pid:14} {row['agent']:9} {row['status']:12} sat_calls={row.get('sat_calls', '-'):>5} "
                  f"time={row.get('time', '-')}{note}", flush=True)

    with open(RESULTS / "results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    (RESULTS / "summary.md").write_text(summarize(rows), encoding="utf-8")
    charts = plot(rows)
    print(f"\nWrote {RESULTS / 'results.csv'}, summary.md" + "".join(f", {p.name}" for p in charts))


if __name__ == "__main__":
    main()
