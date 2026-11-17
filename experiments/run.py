"""Run the agent on every puzzle and write experiments/results/results.csv.

Owner: Lead.

Columns: id, rows, cols, primary_vars, aux_vars, clauses, sat_calls, decisions,
propagations, backtracks, steps, waves, time, status (OK / STUCK / TIMEOUT / ERROR).
Failures and timeouts stay in the table.

Usage: python experiments/run.py [--timeout 60]
"""


def main() -> None:
    raise NotImplementedError


if __name__ == "__main__":
    main()
