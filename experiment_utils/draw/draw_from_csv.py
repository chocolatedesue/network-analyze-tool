#!/usr/bin/env python3
"""
Draw plots from filtered CSV (time/size) produced by `experiment_utils/pcap_to_csv.py`.

This decouples visualization from PCAP parsing. It accepts the simple CSV schema:
- Comments starting with # are ignored
- Header: timestamp,size_bytes
- Rows: timestamp (float seconds), size_bytes (int)

It reuses the same visual style as `draw_pcap.py` and produces a dual-axis figure:
- Left Y: cumulative size in MB
- Right Y: cumulative packet count

Usage:
    uv run experiment_utils/draw/draw_from_csv.py draw out.csv plot.png \
      --title "Network Traffic Analysis - IS-IS - Grid 5x5" --dpi 300 --width 12 --height 8
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import List, Tuple, Optional

import numpy as np
import matplotlib.pyplot as plt
import typer

"""Allow running as a standalone script by resolving local imports."""
sys.path.append(str(Path(__file__).resolve().parent.parent))
from utils import console, log_info, log_success, log_warning, log_error

@dataclass(frozen=True)
class PlotConfig:
    figure_size: Tuple[float, float] = (12.0, 8.0)
    primary_color: str = "tab:blue"
    secondary_color: str = "tab:orange"
    font_family: str = "serif"
    font_size: int = 12
    dpi: int = 300
    grid_alpha: float = 0.3


@dataclass(frozen=True)
class ProcessedData:
    relative_times: List[float]
    cumulative_packet_count: List[int]
    cumulative_size_mb: List[float]
    total_packets: int
    total_size_mb: float
    duration_seconds: float

    @property
    def avg_packet_rate(self) -> float:
        return self.total_packets / max(self.duration_seconds, 1)

    @property
    def avg_throughput(self) -> float:
        return self.total_size_mb / max(self.duration_seconds, 1)


app = typer.Typer(name="draw_from_csv", help="Draw network traffic plots from CSV")


def read_time_size_csv(csv_path: Path) -> List[Tuple[float, int]]:
    rows: List[Tuple[float, int]] = []
    with open(csv_path, "r", encoding="utf-8") as f:
        # Skip commented metadata lines
        first_non_comment = None
        pos = f.tell()
        while True:
            line = f.readline()
            if not line:
                break
            if line.startswith("#"):
                pos = f.tell()
                continue
            else:
                first_non_comment = line
                break
        f.seek(pos)
        reader = csv.DictReader(f)
        if reader.fieldnames is None or set(reader.fieldnames) < {"timestamp", "size_bytes"}:
            raise ValueError("CSV schema must include 'timestamp' and 'size_bytes' columns")
        for row in reader:
            try:
                ts = float(row["timestamp"])  # seconds
                size = int(row["size_bytes"])  # bytes
            except Exception:
                continue
            rows.append((ts, size))
    return rows


def process(rows: List[Tuple[float, int]]) -> ProcessedData:
    if not rows:
        raise ValueError("No data rows in CSV")
    rows_sorted = sorted(rows, key=lambda r: r[0])
    timestamps = [r[0] for r in rows_sorted]
    sizes = [r[1] for r in rows_sorted]
    start_time = timestamps[0]
    rel = [t - start_time for t in timestamps]
    cum_sizes_mb = (np.cumsum(sizes) / (1024 * 1024)).tolist()
    cum_count = list(range(1, len(rows_sorted) + 1))
    return ProcessedData(
        relative_times=rel,
        cumulative_packet_count=cum_count,
        cumulative_size_mb=cum_sizes_mb,
        total_packets=len(rows_sorted),
        total_size_mb=sum(sizes) / (1024 * 1024),
        duration_seconds=rel[-1] if rel else 0.0,
    )


def configure_plot_style(config: PlotConfig) -> None:
    plt.rcParams.update(
        {
            "font.family": config.font_family,
            "font.size": config.font_size,
            "axes.labelsize": config.font_size + 2,
            "xtick.labelsize": config.font_size,
            "ytick.labelsize": config.font_size,
            "legend.fontsize": config.font_size,
            "figure.dpi": 100,
            "savefig.dpi": config.dpi,
            "savefig.bbox": "tight",
        }
    )


def draw_plot(processed: ProcessedData, title: str, config: PlotConfig, output_path: Path) -> None:
    fig, ax1 = plt.subplots(figsize=config.figure_size)

    line1 = ax1.plot(
        processed.relative_times,
        processed.cumulative_size_mb,
        color=config.primary_color,
        linewidth=2,
        label="Cumulative Size (MB)",
    )

    ax1.set_xlabel("Time (s)")
    ax1.set_ylabel("Cumulative Size (MB)", color=config.primary_color)
    ax1.tick_params(axis="y", labelcolor=config.primary_color)
    ax1.grid(True, alpha=config.grid_alpha)

    ax2 = ax1.twinx()
    line2 = ax2.plot(
        processed.relative_times,
        processed.cumulative_packet_count,
        color=config.secondary_color,
        linestyle="--",
        linewidth=2,
        label="Cumulative Packet Count",
    )
    ax2.set_ylabel("Cumulative Packet Count", color=config.secondary_color)
    ax2.tick_params(axis="y", labelcolor=config.secondary_color)

    fig.suptitle(title, fontsize=config.font_size + 4, fontweight="bold")

    for spine in ["top"]:
        ax1.spines[spine].set_visible(False)
        ax2.spines[spine].set_visible(False)

    lines = line1 + line2
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc="upper left", framealpha=0.9)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)


@app.command()
def draw(
    csv_path: Path = typer.Argument(..., exists=True, help="Input CSV file"),
    output_path: Path = typer.Argument(..., help="Output image path (.png/.pdf/.svg)"),
    title: Optional[str] = typer.Option(None, "--title", help="Plot title"),
    dpi: int = typer.Option(300, "--dpi", help="Output DPI"),
    width: float = typer.Option(12.0, "--width", help="Figure width inches"),
    height: float = typer.Option(8.0, "--height", help="Figure height inches"),
) -> None:
    try:
        rows = read_time_size_csv(csv_path)
        processed = process(rows)
        if not title:
            title = "Network Traffic Analysis"
        cfg = PlotConfig(figure_size=(width, height), dpi=dpi)
        configure_plot_style(cfg)
        draw_plot(processed, title, cfg, output_path)
        log_success(f"Plot saved to: {output_path}")
        console.print(
            f"Total={processed.total_packets}, Duration={processed.duration_seconds:.2f}s, Size={processed.total_size_mb:.2f}MB"
        )
    except FileNotFoundError:
        log_error(f"File not found: {csv_path}")
        raise typer.Exit(1)
    except ValueError as e:
        log_error(f"CSV error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        log_error(f"Unexpected error: {e}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
