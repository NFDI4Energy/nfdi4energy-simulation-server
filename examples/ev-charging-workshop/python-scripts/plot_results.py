#!/usr/bin/env python3
"""
Visualizes the results of the SimaaS EV-charging co-simulation.

Takes trafo_p_mw.csv and charging_log.csv from one or more runs and
turns them into charts that make the difference between controller
modes visible - instead of raw columns of numbers.

USAGE

  A single run:
      python plot_results.py --run results/uncontrolled

  Comparing multiple runs (the actual workshop use case):
      python plot_results.py \\
          --run results/uncontrolled \\
          --run results/safe_mode \\
          --run results/heuristic

  Each --run folder must contain trafo_p_mw.csv and charging_log.csv.
  Alternatively, pass the files individually:
      python plot_results.py --files uncontrolled:trafo1.csv:log1.csv \\
                             --files safe_mode:trafo2.csv:log2.csv

OTHER OPTIONS
  --step-seconds N   Seconds per simulation step (default 50, matching
                     stepLength=50000 ms). Needed to show the x-axis in
                     seconds instead of raw step numbers.
  --capacity N       Transformer capacity in kW for the limit line (default 160)
  --out FILE         Output file (default: results.png)
  --show             Open a window instead of only saving

INSTALLATION
  pip install matplotlib
"""

import argparse
import csv
import os
import sys

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:
    print("Error: matplotlib is missing.  ->  pip install matplotlib")
    sys.exit(1)


# Fixed colors per controller mode, so the mapping stays consistent
# across all charts.
MODE_COLORS = {
    "uncontrolled": "#e07a3f",
    "safe_mode": "#2d8f8f",
    "heuristic": "#7a5bbd",
}
FALLBACK_COLORS = ["#4a7ebb", "#b55d8a", "#6f9e4c", "#c0a33e"]


def read_trafo(path, step_seconds):
    """Reads trafo_p_mw.csv -> (times_in_s, power_in_kW)."""
    times, power = [], []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            step = int(row["step"])
            # Column names are trafo_0, trafo_1, ... - we take every
            # column except 'step' and sum across all transformers.
            mw = sum(float(v) for k, v in row.items() if k != "step" and v)
            times.append(step * step_seconds)
            power.append(mw * 1000.0)
    return times, power


def read_charging(path):
    """Reads charging_log.csv -> list of dicts."""
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def to_float(value, fallback=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def plot_trafo(ax, runs, capacity_kW):
    for idx, run in enumerate(runs):
        color = MODE_COLORS.get(run["label"], FALLBACK_COLORS[idx % len(FALLBACK_COLORS)])
        ax.plot(run["times"], run["power"], label=run["label"],
                color=color, linewidth=2.2)

    ax.axhline(capacity_kW, color="#c0392b", linestyle="--", linewidth=1.6)
    ax.text(ax.get_xlim()[1], capacity_kW, f"  Transformer limit {capacity_kW:.0f} kW",
            color="#c0392b", va="bottom", ha="right", fontsize=9)

    ax.set_title("Transformer Load Over Time", fontsize=13, fontweight="bold")
    ax.set_xlabel("Simulation time (s)")
    ax.set_ylabel("Active power (kW)")
    ax.grid(alpha=0.3)
    ax.legend(loc="upper right", frameon=False)


def plot_soc(ax, runs):
    """Final charge level per station, grouped bars per run."""
    stations = sorted({r["station"] for run in runs for r in run["charging"]})
    n = len(runs)
    width = 0.8 / max(n, 1)

    for idx, run in enumerate(runs):
        color = MODE_COLORS.get(run["label"], FALLBACK_COLORS[idx % len(FALLBACK_COLORS)])
        by_station = {r["station"]: r for r in run["charging"]}
        xs, ys = [], []
        for s_idx, station in enumerate(stations):
            row = by_station.get(station)
            soc = to_float(row["final_soc"], 0.0) if row else 0.0
            xs.append(s_idx + idx * width - 0.4 + width / 2)
            ys.append(soc * 100.0)
        ax.bar(xs, ys, width=width * 0.92, label=run["label"], color=color)

    ax.axhline(80, color="#555555", linestyle=":", linewidth=1.4)
    ax.text(len(stations) - 0.5, 80, " Charging target 80%", va="bottom", ha="right",
            fontsize=9, color="#555555")

    ax.set_title("Final Charge Level per Station", fontsize=13, fontweight="bold")
    ax.set_xlabel("Charging station")
    ax.set_ylabel("Charge level at end of simulation (%)")
    ax.set_xticks(range(len(stations)))
    ax.set_xticklabels(stations)
    ax.set_ylim(0, 100)
    ax.grid(alpha=0.3, axis="y")
    ax.legend(loc="lower right", frameon=False)


def plot_duration(ax, runs):
    """Charging duration per station; unfinished ones are marked."""
    stations = sorted({r["station"] for run in runs for r in run["charging"]})
    n = len(runs)
    width = 0.8 / max(n, 1)
    max_dur = 0

    for idx, run in enumerate(runs):
        color = MODE_COLORS.get(run["label"], FALLBACK_COLORS[idx % len(FALLBACK_COLORS)])
        by_station = {r["station"]: r for r in run["charging"]}
        xs, ys, unfinished = [], [], []
        for s_idx, station in enumerate(stations):
            row = by_station.get(station)
            x = s_idx + idx * width - 0.4 + width / 2
            arrival = to_float(row["arrival_time"]) if row else None
            done = to_float(row["charge_complete_time"]) if row else None
            if arrival is not None and done is not None:
                dur = done - arrival
                max_dur = max(max_dur, dur)
            else:
                dur = 0.0
                unfinished.append(x)
            xs.append(x)
            ys.append(dur)
        ax.bar(xs, ys, width=width * 0.92, label=run["label"], color=color)
        # Mark stations that never reached the charging target with an X
        for x in unfinished:
            ax.plot([x], [max_dur * 0.05 if max_dur else 1], marker="x",
                    color=color, markersize=9, markeredgewidth=2.2)

    ax.set_title("Charging Duration per Station  (\u00d7 = target not reached)",
                 fontsize=13, fontweight="bold")
    ax.set_xlabel("Charging station")
    ax.set_ylabel("Time to 80% (s)")
    ax.set_xticks(range(len(stations)))
    ax.set_xticklabels(stations)
    ax.grid(alpha=0.3, axis="y")
    ax.legend(loc="upper left", frameon=False)


def load_run(label, trafo_path, log_path, step_seconds):
    times, power = read_trafo(trafo_path, step_seconds)
    charging = read_charging(log_path)
    # If the log itself carries a controller_mode, prefer that as the label
    if charging and charging[0].get("controller_mode"):
        label = charging[0]["controller_mode"]
    return {"label": label, "times": times, "power": power, "charging": charging}


def main():
    p = argparse.ArgumentParser(
        description="Plots the results of the EV-charging co-simulation.")
    p.add_argument("--run", action="append", default=[], metavar="FOLDER",
                   help="Folder containing trafo_p_mw.csv and charging_log.csv "
                        "(repeatable, to compare multiple runs)")
    p.add_argument("--files", action="append", default=[], metavar="LABEL:TRAFO:LOG",
                   help="Alternative: pass label and both files directly")
    p.add_argument("--step-seconds", type=float, default=50.0,
                   help="Seconds per simulation step (default 50)")
    p.add_argument("--capacity", type=float, default=160.0,
                   help="Transformer capacity in kW for the limit line (default 160)")
    p.add_argument("--out", default="results.png", help="Output file")
    p.add_argument("--show", action="store_true", help="Open a window")
    args = p.parse_args()

    runs = []

    for folder in args.run:
        trafo = os.path.join(folder, "trafo_p_mw.csv")
        log = os.path.join(folder, "charging_log.csv")
        for path in (trafo, log):
            if not os.path.exists(path):
                p.error(f"File not found: {path}")
        runs.append(load_run(os.path.basename(folder.rstrip("/")),
                             trafo, log, args.step_seconds))

    for spec in args.files:
        parts = spec.split(":")
        if len(parts) != 3:
            p.error(f"--files expects LABEL:TRAFO:LOG, got: {spec}")
        label, trafo, log = parts
        runs.append(load_run(label, trafo, log, args.step_seconds))

    if not runs:
        p.error("At least one --run or --files is required. See --help.")

    fig, axes = plt.subplots(3, 1, figsize=(11, 13))
    plot_trafo(axes[0], runs, args.capacity)
    plot_soc(axes[1], runs)
    plot_duration(axes[2], runs)

    fig.suptitle("Grid-Aware EV Charging \u2014 Co-Simulation Results",
                 fontsize=15, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.98])

    if args.show:
        matplotlib.use("TkAgg")
        plt.show()
    fig.savefig(args.out, dpi=150)
    print(f"Charts saved: {args.out}")

    # Short text summary in addition to the charts
    print()
    print(f"{'Mode':<16}{'Peak kW':>11}{'Utilization':>13}{'Finished':>10}")
    for run in runs:
        peak = max(run["power"]) if run["power"] else 0.0
        done = sum(1 for r in run["charging"]
                   if to_float(r["charge_complete_time"]) is not None)
        total = len(run["charging"])
        print(f"{run['label']:<16}{peak:>11.1f}{peak / args.capacity * 100:>12.1f}%"
              f"{done:>6}/{total}")


if __name__ == "__main__":
    main()
