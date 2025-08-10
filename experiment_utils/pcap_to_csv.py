#!/usr/bin/env python3
"""
PCAP → CSV filtering tool

Splits the responsibilities from `experiment_utils/draw/draw_pcap.py` so that this
module only reads PCAP files, filters packets by protocol, and writes a compact CSV
for downstream plotting/analysis.

CSV format (packet-level rows):
- Required header: `timestamp,size_bytes`
- Each row:
  - timestamp: float seconds since epoch (pcap timestamp)
  - size_bytes: integer packet size in bytes (captured length)

Metadata: The first lines may include comments starting with `#` for human-readable
context, e.g. source file, protocol, topology detection results, etc. Readers should
skip lines beginning with `#`.

CLI usage examples:
    uv run experiment_utils/pcap_to_csv.py pcap2csv input.pcap out.csv
    uv run experiment_utils/pcap_to_csv.py pcap2csv input.pcap out.csv --protocol isis
    uv run experiment_utils/pcap_to_csv.py pcap2csv input.pcap out.csv --autodetect
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import sys
from typing import Callable, Dict, List, Optional, Tuple

import typer
from scapy.all import PcapReader, RawPcapReader, Ether, IPv6, TCP, Packet  # type: ignore
from scapy.layers.l2 import Dot1Q, CookedLinux, LLC  # type: ignore

# Ensure contrib dissectors are registered
from scapy.contrib import isis as _scapy_contrib_isis  # noqa: F401
from scapy.contrib import ospf as _scapy_contrib_ospf  # noqa: F401
from scapy.contrib import bgp as _scapy_contrib_bgp  # noqa: F401

"""Allow running as a standalone script by resolving local imports."""
sys.path.append(str(Path(__file__).resolve().parent))

from utils import console, log_info, log_success, log_warning, log_error

app = typer.Typer(name="pcap_to_csv", help="Filter PCAP to CSV packet time/size")


# ==========================
# Protocol types and config
# ==========================

@dataclass(frozen=True)
class ProtocolConfig:
    name: str
    display_name: str
    filter_func: Callable[[Packet], bool]
    keywords: List[str]


class ProtocolType(Enum):
    ISIS = "isis"
    OSPF6 = "ospf6"
    BGP = "bgp"
    UNKNOWN = "unknown"


# ---------------
# Filter functions
# ---------------

def is_isis_packet(packet: Packet) -> bool:
    try:
        from scapy.contrib.isis import (
            ISIS_CommonHdr,
            ISIS_L1HelloPDU,
            ISIS_L2HelloPDU,
            ISIS_P2PHelloPDU,
            ISIS_LSPPDU,
            ISIS_CSNPPDU,
            ISIS_PSNPPDU,
        )
        for layer in (
            ISIS_CommonHdr,
            ISIS_L1HelloPDU,
            ISIS_L2HelloPDU,
            ISIS_P2PHelloPDU,
            ISIS_LSPPDU,
            ISIS_CSNPPDU,
            ISIS_PSNPPDU,
        ):
            if packet.haslayer(layer):
                return True
        for lname in (
            "ISIS_CommonHdr",
            "ISIS_L1HelloPDU",
            "ISIS_L2HelloPDU",
            "ISIS_P2PHelloPDU",
            "ISIS_LSPPDU",
            "ISIS_CSNPPDU",
            "ISIS_PSNPPDU",
            "CLNS",
        ):
            if packet.haslayer(lname):
                return True
    except Exception:
        pass

    try:
        if Ether in packet and getattr(packet[Ether], "type", None) == 0x22F0:
            return True
        if packet.haslayer(Dot1Q):
            q = packet.getlayer(Dot1Q)
            while q and isinstance(q, Dot1Q):
                if getattr(q, "type", None) == 0x22F0:
                    return True
                q = q.payload if isinstance(q.payload, Dot1Q) else None
    except Exception:
        pass

    try:
        if packet.haslayer(CookedLinux):
            if getattr(packet[CookedLinux], "proto", None) == 0x22F0:
                return True
    except Exception:
        pass

    try:
        if packet.haslayer(LLC):
            llc = packet.getlayer(LLC)
            if getattr(llc, "dsap", None) == 0xFE and getattr(llc, "ssap", None) == 0xFE:
                payload_bytes = bytes(llc.payload) if hasattr(llc, "payload") else b""
                if payload_bytes and payload_bytes[0] == 0x83:
                    return True
                if Ether in packet:
                    dst = getattr(packet[Ether], "dst", "").lower()
                    if dst in {"01:80:c2:00:00:14", "01:80:c2:00:00:15"}:
                        return True
    except Exception:
        pass

    return False


def is_ospf6_packet(packet: Packet) -> bool:
    try:
        if IPv6 in packet and packet[IPv6].nh == 89:
            return True
        from scapy.contrib.ospf import (
            OSPF_Hdr,
            OSPF_Hello,
            OSPF_DBDesc,
            OSPF_LSReq,
            OSPF_LSUpd,
            OSPF_LSAck,
        )
        for layer in (OSPF_Hdr, OSPF_Hello, OSPF_DBDesc, OSPF_LSReq, OSPF_LSUpd, OSPF_LSAck):
            if packet.haslayer(layer):
                return True
        for lname in (
            "OSPF_Hdr",
            "OSPF_Hello",
            "OSPF_DBDesc",
            "OSPF_LSReq",
            "OSPF_LSUpd",
            "OSPF_LSAck",
            "OSPFv3_Hdr",
            "OSPFv3_Hello",
            "OSPFv3_DBDesc",
            "OSPFv3_LSReq",
            "OSPFv3_LSUpd",
            "OSPFv3_LSAck",
        ):
            if packet.haslayer(lname):
                return True
    except Exception:
        try:
            return IPv6 in packet and packet[IPv6].nh == 89
        except Exception:
            return False
    return False


def is_bgp_packet(packet: Packet) -> bool:
    try:
        if TCP in packet and (packet[TCP].sport == 179 or packet[TCP].dport == 179):
            return True
        from scapy.contrib.bgp import BGPHeader, BGPOpen, BGPUpdate, BGPNotification, BGPKeepAlive
        for layer in (BGPHeader, BGPOpen, BGPUpdate, BGPNotification, BGPKeepAlive):
            if packet.haslayer(layer):
                return True
        for lname in (
            "BGPHeader",
            "BGPOpen",
            "BGPUpdate",
            "BGPNotification",
            "BGPKeepAlive",
            "BGP_Header",
            "BGP_Open",
            "BGP_Update",
            "BGP_Notification",
            "BGP_KeepAlive",
        ):
            if packet.haslayer(lname):
                return True
    except Exception:
        try:
            return TCP in packet and (packet[TCP].sport == 179 or packet[TCP].dport == 179)
        except Exception:
            return False
    return False


def accept_all_packets(_: Packet) -> bool:
    return True


PROTOCOL_REGISTRY: Dict[ProtocolType, ProtocolConfig] = {
    ProtocolType.ISIS: ProtocolConfig("isis", "IS-IS", is_isis_packet, ["isis", "is-is"]),
    ProtocolType.OSPF6: ProtocolConfig("ospf6", "OSPFv6", is_ospf6_packet, ["ospf6", "ospfv6", "ospf_v6", "ospfv3"]),
    ProtocolType.BGP: ProtocolConfig("bgp", "BGP", is_bgp_packet, ["bgp", "bgp4"]),
    ProtocolType.UNKNOWN: ProtocolConfig("unknown", "Unknown", accept_all_packets, []),
}


# ==========================
# Helpers
# ==========================

def extract_protocol_from_filename(filename: str) -> ProtocolType:
    stem = Path(filename).stem.lower()
    for ptype, cfg in PROTOCOL_REGISTRY.items():
        if ptype == ProtocolType.UNKNOWN:
            continue
        if any(keyword in stem for keyword in cfg.keywords):
            return ptype
    return ProtocolType.ISIS


def detect_protocol_by_content(pcap_path: Path, sample_limit: int = 5000) -> ProtocolType:
    counts: Dict[ProtocolType, int] = {ptype: 0 for ptype in PROTOCOL_REGISTRY if ptype != ProtocolType.UNKNOWN}
    scanned = 0
    try:
        for pkt_data, metadata in RawPcapReader(str(pcap_path)):
            scanned += 1
            if scanned > sample_limit:
                break
            try:
                packet = Ether(pkt_data)
            except Exception:
                continue
            for ptype, cfg in PROTOCOL_REGISTRY.items():
                if ptype == ProtocolType.UNKNOWN:
                    continue
                try:
                    if cfg.filter_func(packet):
                        counts[ptype] += 1
                except Exception:
                    continue
    except Exception:
        return ProtocolType.UNKNOWN
    best_type: Optional[ProtocolType] = None
    best_count = 0
    for ptype, count in counts.items():
        if count > best_count:
            best_type = ptype
            best_count = count
    return best_type if (best_type is not None and best_count > 0) else ProtocolType.UNKNOWN


# ==========================
# Core: read/filter/write CSV
# ==========================

def read_filtered_packets(
    pcap_path: Path,
    protocol_type: ProtocolType,
    use_streaming: bool = True,
) -> List[Tuple[float, int]]:
    """Return list of (timestamp, size_bytes) for packets matching protocol."""
    filter_func = PROTOCOL_REGISTRY[protocol_type].filter_func
    rows: List[Tuple[float, int]] = []

    total_packets = 0
    filtered_packets = 0

    with console.status(f"[bold blue]Reading PCAP: {pcap_path.name}"):
        if use_streaming:
            try:
                for pkt_data, metadata in RawPcapReader(str(pcap_path)):
                    total_packets += 1
                    try:
                        pkt = Ether(pkt_data)
                        if filter_func(pkt):
                            ts = float(metadata.sec + metadata.usec / 1_000_000)
                            rows.append((ts, len(pkt_data)))
                            filtered_packets += 1
                    except Exception:
                        continue
            except Exception as e:
                log_warning(f"Streaming reader failed, fallback to standard reader: {e}")
                use_streaming = False

        if not use_streaming:
            with PcapReader(str(pcap_path)) as r:
                for pkt in r:
                    total_packets += 1
                    try:
                        if filter_func(pkt):
                            rows.append((float(pkt.time), len(pkt)))
                            filtered_packets += 1
                    except Exception:
                        continue

    log_info(
        f"Read {total_packets} packets, matched {filtered_packets} {PROTOCOL_REGISTRY[protocol_type].display_name} packets"
    )

    if filtered_packets == 0:
        log_warning("No matching protocol packets found in PCAP")

    return rows


def write_csv(
    output_csv: Path,
    rows: List[Tuple[float, int]],
    metadata: Optional[Dict[str, str]] = None,
) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        if metadata:
            for k, v in metadata.items():
                f.write(f"# {k}: {v}\n")
        writer = csv.writer(f)
        writer.writerow(["timestamp", "size_bytes"])
        for ts, size in rows:
            writer.writerow([f"{ts:.6f}", int(size)])


def pcap_to_csv(
    pcap_path: Path,
    output_csv: Path,
    forced_protocol: Optional[ProtocolType] = None,
    autodetect: bool = False,
    streaming: bool = True,
) -> None:
    if not pcap_path.exists():
        log_error(f"File not found: {pcap_path}")
        raise typer.Exit(1)

    ptype: Optional[ProtocolType] = forced_protocol
    if ptype is None:
        guess = extract_protocol_from_filename(pcap_path.name)
        ptype = guess
        if autodetect or guess == ProtocolType.UNKNOWN:
            detected = detect_protocol_by_content(pcap_path)
            if detected != ProtocolType.UNKNOWN:
                ptype = detected
                log_info(f"Content-based protocol detection: {PROTOCOL_REGISTRY[ptype].display_name}")

    if ptype is None:
        ptype = ProtocolType.ISIS

    log_info(f"Protocol filter: {PROTOCOL_REGISTRY[ptype].display_name}")

    rows = read_filtered_packets(pcap_path, ptype, use_streaming=streaming)

    metadata = {
        "source_pcap": str(pcap_path),
        "protocol": PROTOCOL_REGISTRY[ptype].name,
    }

    write_csv(output_csv, rows, metadata)
    log_success(f"CSV saved to: {output_csv}")


# =============
# CLI command
# =============

@app.command()
def pcap2csv(
    pcap: Path = typer.Argument(..., exists=True, help="Input PCAP file"),
    output_csv: Path = typer.Argument(..., help="Output CSV file path"),
    protocol: Optional[str] = typer.Option(
        None,
        "--protocol",
        help="Force protocol: isis | ospf6 | bgp",
        case_sensitive=False,
    ),
    autodetect: bool = typer.Option(
        False, "--autodetect", help="Detect protocol by PCAP content"
    ),
    no_streaming: bool = typer.Option(
        False, "--no-streaming", help="Disable RawPcapReader streaming"
    ),
) -> None:
    forced: Optional[ProtocolType] = None
    if protocol:
        normalized = protocol.strip().lower()
        name_to_type = {cfg.name: ptype for ptype, cfg in PROTOCOL_REGISTRY.items()}
        if normalized in name_to_type and name_to_type[normalized] != ProtocolType.UNKNOWN:
            forced = name_to_type[normalized]
        else:
            log_warning(f"Unknown protocol '{protocol}'. Falling back to filename/autodetect.")

    pcap_to_csv(
        pcap_path=pcap,
        output_csv=output_csv,
        forced_protocol=forced,
        autodetect=autodetect,
        streaming=not no_streaming,
    )


if __name__ == "__main__":
    app()
