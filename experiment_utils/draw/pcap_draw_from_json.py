#!/usr/bin/env python3
"""
Draw plots from TShark/PCAP-derived JSON (time/size), e.g. `res.json`.

This mirrors the visual style and stats of `draw_from_csv.py`, but reads
JSON arrays of packet objects exported by Wireshark/TShark (or similar),
where each item typically looks like:

[
  {
    "_source": {
      "layers": {
        "frame": {
          "frame.time_epoch": "1754818935.052857000",
          "frame.len": "9520",
          ...
        },
        ...
      }
    }
  }
]

Required fields per packet:
- time: prefer `frame.time_epoch` (float seconds); fallback to `frame.time_relative`
- size: prefer `frame.len`; fallback to `frame.cap_len`

Usage:
    uv run experiment_utils/draw/draw_from_json.py draw res.json plot.png \
      --title "Network Traffic Analysis - IS-IS - Grid 5x5" --dpi 300 --width 12 --height 8
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import List, Tuple, Optional, Any, Dict

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator, StrMethodFormatter
import typer

# Allow running as a standalone script by resolving local imports.
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


app = typer.Typer(name="draw_from_json", help="Draw network traffic plots from JSON")


def _get_nested(d: Dict[str, Any], *keys: str) -> Any:
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def _coerce_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            return float(value)
    except Exception:
        return None
    return None


def _coerce_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            # Some JSON exports use strings for numbers
            return int(value)
    except Exception:
        return None
    return None


def read_time_size_json(json_path: Path) -> List[Tuple[float, int]]:
    rows: List[Tuple[float, int]] = []
    with open(json_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except Exception as e:
            raise ValueError(f"Invalid JSON: {e}")

    # Support either a list at root or wrapped dict with a known key
    items: List[Any]
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        # Try common wrappers (Elasticsearch-like, etc.)
        for key in ("hits", "packets", "data", "_source"):
            cand = data.get(key)
            if isinstance(cand, list):
                items = cand
                break
        else:
            # If dict but not a list container, try to treat as single record
            items = [data]
    else:
        raise ValueError("Unsupported JSON structure: expected list or dict")

    for item in items:
        try:
            # Typical structure: item["_source"]["layers"]["frame"]["frame.time_epoch"], ["frame.len"]
            if isinstance(item, dict) and "_source" in item:
                layers = _get_nested(item, "_source", "layers")
            else:
                layers = _get_nested(item, "layers") if isinstance(item, dict) else None

            frame_layer = None
            if isinstance(layers, dict):
                frame_layer = layers.get("frame")

            # Some exports place fields directly under layers
            time_candidate = None
            size_candidate = None

            if isinstance(frame_layer, dict):
                time_candidate = (
                    frame_layer.get("frame.time_epoch")
                    or frame_layer.get("frame.time_relative")
                )
                size_candidate = frame_layer.get("frame.len") or frame_layer.get("frame.cap_len")
            elif isinstance(layers, dict):
                # Fallback: try directly under layers
                time_candidate = layers.get("frame.time_epoch") or layers.get("frame.time_relative")
                size_candidate = layers.get("frame.len") or layers.get("frame.cap_len")

            ts = _coerce_float(time_candidate)
            size = _coerce_int(size_candidate)

            if ts is None or size is None:
                # As a last resort, allow alternative placements
                # e.g., item["frame"]["frame.time_epoch"]
                frame_alt = _get_nested(item, "frame") if isinstance(item, dict) else None
                if isinstance(frame_alt, dict):
                    ts = ts or _coerce_float(
                        frame_alt.get("frame.time_epoch") or frame_alt.get("frame.time_relative")
                    )
                    size = size or _coerce_int(frame_alt.get("frame.len") or frame_alt.get("frame.cap_len"))

            if ts is None or size is None:
                continue

            rows.append((ts, size))
        except Exception:
            continue

    return rows


def process(rows: List[Tuple[float, int]]) -> ProcessedData:
    if not rows:
        raise ValueError("No data rows in JSON")
    rows_sorted = sorted(rows, key=lambda r: r[0])
    timestamps = [r[0] for r in rows_sorted]
    sizes = [r[1] for r in rows_sorted]

    # If timestamps look like relative times (start near 0), the subtraction is harmless.
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
    # Force integer ticks and integer formatting for packet counts
    ax2.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax2.yaxis.set_major_formatter(StrMethodFormatter("{x:.0f}"))

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
    json_path: Path = typer.Argument(..., exists=True, help="Input JSON file"),
    output_path: Path = typer.Argument(..., help="Output image path (.png/.pdf/.svg)"),
    title: Optional[str] = typer.Option(None, "--title", help="Plot title"),
    dpi: int = typer.Option(300, "--dpi", help="Output DPI"),
    width: float = typer.Option(12.0, "--width", help="Figure width inches"),
    height: float = typer.Option(8.0, "--height", help="Figure height inches"),
    use_cap_len: bool = typer.Option(False, "--use-cap-len", help="Prefer frame.cap_len over frame.len"),
):
    try:
        rows = read_time_size_json(json_path)
        if not rows:
            raise ValueError("No valid packets found in JSON")

        # If requested, re-map sizes to cap_len when both are present in source JSON.
        # Note: Our extractor already prefers frame.len. For cap_len preference, we
        # re-read quickly and replace when possible.
        if use_cap_len:
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Build a secondary pass attempting to pick cap_len; fallback to original size
                new_rows: List[Tuple[float, int]] = []
                items = data if isinstance(data, list) else [data]
                for i, item in enumerate(items):
                    if i >= len(rows):
                        break
                    ts, size = rows[i]
                    cap_len_val: Optional[int] = None
                    try:
                        layers = _get_nested(item, "_source", "layers") or _get_nested(item, "layers")
                        frame_layer = layers.get("frame") if isinstance(layers, dict) else None
                        cap_len_val = _coerce_int(
                            (frame_layer.get("frame.cap_len") if isinstance(frame_layer, dict) else None)
                            or (layers.get("frame.cap_len") if isinstance(layers, dict) else None)
                        )
                    except Exception:
                        cap_len_val = None
                    new_rows.append((ts, cap_len_val if cap_len_val is not None else size))
                rows = new_rows
            except Exception:
                pass

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
        log_error(f"File not found: {json_path}")
        raise typer.Exit(1)
    except ValueError as e:
        log_error(f"JSON error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        log_error(f"Unexpected error: {e}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()


