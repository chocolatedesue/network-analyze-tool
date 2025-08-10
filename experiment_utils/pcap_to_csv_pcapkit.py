#!/usr/bin/env python3
"""
PCAP → CSV (PyPCAPKit)

Minimal tool to export packet timestamps and sizes to CSV, with simple
protocol filtering (isis | ospf6 | bgp). Designed to be short and easy to use.

Examples:
    uv run experiment_utils/pcap_to_csv_pcapkit.py pcap2csv input.pcap out.csv
    uv run experiment_utils/pcap_to_csv_pcapkit.py pcap2csv input.pcap out.csv --protocol isis
    uv run experiment_utils/pcap_to_csv_pcapkit.py pcap2csv input.pcap out.csv --protocol auto
"""
from __future__ import annotations

import csv
from enum import Enum
from pathlib import Path
import sys
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import typer

# Install with: uv add pypcapkit
from pcapkit import extract  # type: ignore

# Allow running as standalone script by resolving local imports
sys.path.append(str(Path(__file__).resolve().parent))
from utils import log_info, log_success, log_warning, log_error  # type: ignore


app = typer.Typer(name="pcap_to_csv_pcapkit", help="Filter PCAP to CSV using PyPCAPKit")


class ProtocolType(str, Enum):
    ISIS = "isis"
    OSPF6 = "ospf6"
    BGP = "bgp"
    AUTO = "auto"


def _frame_protocols_str(frame) -> str:
    try:
        protocols = getattr(getattr(frame, "frame_info", None), "protocols", "")
        return str(protocols).lower()
    except Exception:
        return ""


def _is_isis(frame) -> bool:
    protos = _frame_protocols_str(frame)
    # match on dissector name; also include clns as many ISIS pkts show up this way
    return ("isis" in protos) or ("clns" in protos)


def _is_ospf6(frame) -> bool:
    protos = _frame_protocols_str(frame)
    # simple heuristic: both ospf and ipv6 present in protocol chain
    return ("ospf" in protos) and ("ipv6" in protos)


def _is_bgp(frame) -> bool:
    protos = _frame_protocols_str(frame)
    if "bgp" in protos:
        return True
    # fallback to TCP/179 port check if available
    try:
        if "TCP" in frame:  # PyPCAPKit mapping-like access
            tcp = frame["TCP"]
            sport = getattr(tcp, "srcport", None) or getattr(tcp, "sport", None)
            dport = getattr(tcp, "dstport", None) or getattr(tcp, "dport", None)
            return sport == 179 or dport == 179
    except Exception:
        pass
    return False


FILTERS: Dict[ProtocolType, Callable[[object], bool]] = {
    ProtocolType.ISIS: _is_isis,
    ProtocolType.OSPF6: _is_ospf6,
    ProtocolType.BGP: _is_bgp,
}


def _iter_frames(pcap_path: Path):
    extraction = extract(fin=str(pcap_path), nofile=True, store=False)
    # extraction.frame is an Iterable of frame objects
    return getattr(extraction, "frame", [])


def _detect_protocol_by_content(pcap_path: Path, sample_limit: int = 3000) -> Optional[ProtocolType]:
    counts: Dict[ProtocolType, int] = {ProtocolType.ISIS: 0, ProtocolType.OSPF6: 0, ProtocolType.BGP: 0}
    scanned = 0
    try:
        for frame in _iter_frames(pcap_path):
            scanned += 1
            if scanned > sample_limit:
                break
            for ptype, func in FILTERS.items():
                try:
                    if func(frame):
                        counts[ptype] += 1
                except Exception:
                    continue
    except Exception as e:
        log_warning(f"Protocol autodetect failed: {e}")
        return None

    best: Optional[ProtocolType] = None
    best_count = 0
    for ptype, cnt in counts.items():
        if cnt > best_count:
            best = ptype
            best_count = cnt
    return best if best_count > 0 else None


def _read_filtered_rows(pcap_path: Path, protocol: ProtocolType) -> List[Tuple[float, int]]:
    rows: List[Tuple[float, int]] = []
    match_func = FILTERS[protocol]

    total_packets = 0
    matched_packets = 0
    for frame in _iter_frames(pcap_path):
        total_packets += 1
        try:
            if not match_func(frame):
                continue
            fi = getattr(frame, "frame_info", None)
            if fi is None:
                continue
            ts = float(getattr(fi, "time_epoch", 0.0) or 0.0)
            size_val = getattr(fi, "len", None) or getattr(fi, "cap_len", None) or 0
            size_int = int(size_val)
            if ts and size_int:
                rows.append((ts, size_int))
                matched_packets += 1
        except Exception:
            continue

    log_info(f"Read {total_packets} packets, matched {matched_packets} {protocol.value} packets")
    if matched_packets == 0:
        log_warning("No matching protocol packets found in PCAP")
    return rows


def _write_csv(output_csv: Path, rows: Iterable[Tuple[float, int]], metadata: Optional[Dict[str, str]] = None) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        if metadata:
            for k, v in metadata.items():
                f.write(f"# {k}: {v}\n")
        writer = csv.writer(f)
        writer.writerow(["timestamp", "size_bytes"])
        for ts, size in rows:
            writer.writerow([f"{ts:.6f}", int(size)])


def pcap_to_csv_pcapkit(
    pcap: Path,
    output_csv: Path,
    protocol: ProtocolType = ProtocolType.AUTO,
) -> None:
    if not pcap.exists():
        log_error(f"File not found: {pcap}")
        raise typer.Exit(1)

    selected: Optional[ProtocolType] = None
    if protocol == ProtocolType.AUTO:
        selected = _detect_protocol_by_content(pcap)
        if selected is None:
            log_warning("Autodetect failed; defaulting to isis")
            selected = ProtocolType.ISIS
        else:
            log_info(f"Content-based protocol detection: {selected.value}")
    else:
        selected = protocol

    rows = _read_filtered_rows(pcap, selected)
    _write_csv(
        output_csv,
        rows,
        metadata={
            "source_pcap": str(pcap),
            "protocol": selected.value,
        },
    )
    log_success(f"CSV saved to: {output_csv}")


@app.command()
def pcap2csv(
    pcap: Path = typer.Argument(..., exists=True, help="Input PCAP file"),
    output_csv: Path = typer.Argument(..., help="Output CSV file"),
    protocol: ProtocolType = typer.Option(ProtocolType.AUTO, "--protocol", case_sensitive=False),
) -> None:
    """Convert PCAP to CSV using PyPCAPKit, with basic protocol filtering."""
    pcap_to_csv_pcapkit(pcap, output_csv, protocol)


if __name__ == "__main__":
    app()


