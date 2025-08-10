#!/usr/bin/env python3
"""
PCAP Traffic Analysis Tool

Analyzes PCAP files and generates publication-quality traffic trend plots
with automatic topology detection and rich console output.
Supports OSPFv6, ISIS, and BGP protocol analysis with packet filtering.
"""

import re
import sys
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Callable
from enum import Enum
from dataclasses import dataclass

import matplotlib.pyplot as plt
import numpy as np
import typer
from pydantic import BaseModel
from rich.table import Table
from scapy.all import PcapReader, IPv6, TCP, Packet, RawPcapReader, Ether
from scapy.layers.l2 import Dot1Q, CookedLinux, LLC

"""Import Scapy contrib modules to register protocol dissectors without
polluting the namespace. Access is via haslayer(...) and field extraction
by layer name strings, so we only need module import side-effects here."""
from scapy.contrib import isis as _scapy_contrib_isis  # noqa: F401
from scapy.contrib import ospf as _scapy_contrib_ospf  # noqa: F401
from scapy.contrib import bgp as _scapy_contrib_bgp    # noqa: F401

# Keep sys.path hack to support running this single script directly
sys.path.append(str(Path(__file__).parent.parent))

# Import from local utils within experiment_utils
from utils import (
    console,
    log_info,
    log_success,
    log_warning,
    log_error,
)


# ============================================================================
# Configuration and Constants
# ============================================================================

@dataclass(frozen=True)
class PlotConfig:
    """Configuration for plot styling and layout."""
    figure_size: Tuple[float, float] = (12, 8)
    primary_color: str = 'tab:blue'
    secondary_color: str = 'tab:orange'
    font_family: str = 'serif'
    font_size: int = 12
    dpi: int = 300
    grid_alpha: float = 0.3


@dataclass(frozen=True) 
class ProtocolConfig:
    """Configuration for a specific routing protocol."""
    name: str
    display_name: str
    filter_func: Callable[[Packet], bool]
    keywords: List[str]
    description: str


# ============================================================================
# Enums and Data Models
# ============================================================================

class TopologyType(Enum):
    """Network topology types that can be identified from filenames."""
    SIZE = "size"
    GRID = "grid"
    TORUS = "torus"
    UNKNOWN = "unknown"


class ProtocolType(Enum):
    """Supported routing protocols for analysis."""
    ISIS = "isis"
    OSPF6 = "ospf6"
    BGP = "bgp"
    UNKNOWN = "unknown"


class TopologyInfo(BaseModel):
    """Information about network topology extracted from filename."""
    topology_type: TopologyType
    size: Optional[int] = None
    dimensions: Optional[Tuple[int, ...]] = None
    raw_info: Optional[str] = None

    @property
    def display_name(self) -> str:
        """Generate a human-readable display name for the topology."""
        display_map = {
            TopologyType.SIZE: lambda: f"Size {self.size}" if self.size else "Size Unknown",
            TopologyType.GRID: lambda: f"Grid {self._format_dimensions()}" if self.dimensions else "Grid Unknown",
            TopologyType.TORUS: lambda: f"Torus {self._format_dimensions()}" if self.dimensions else "Torus Unknown",
            TopologyType.UNKNOWN: lambda: f"Unknown {self.raw_info}" if self.raw_info else "Unknown"
        }
        
        formatter = display_map.get(self.topology_type, lambda: self.topology_type.value.title())
        return formatter()
    
    def _format_dimensions(self) -> str:
        """Format dimensions tuple as string."""
        return "×".join(map(str, self.dimensions)) if self.dimensions else ""


class ProtocolInfo(BaseModel):
    """Information about routing protocol extracted from filename."""
    protocol_type: ProtocolType
    raw_info: Optional[str] = None

    @property
    def display_name(self) -> str:
        """Generate a human-readable display name for the protocol."""
        protocol_names = {
            ProtocolType.ISIS: "IS-IS",
            ProtocolType.OSPF6: "OSPFv6", 
            ProtocolType.BGP: "BGP",
            ProtocolType.UNKNOWN: "Unknown Protocol"
        }
        return protocol_names.get(self.protocol_type, self.protocol_type.value.upper())

    @property
    def config(self) -> ProtocolConfig:
        """Get protocol configuration."""
        return PROTOCOL_REGISTRY.get(self.protocol_type, PROTOCOL_REGISTRY[ProtocolType.UNKNOWN])


class PacketData(BaseModel):
    """Immutable packet data structure with validation."""
    timestamp: float
    size: int

    class Config:
        """Pydantic configuration."""
        frozen = True


class ProcessedData(BaseModel):
    """Processed packet analysis results."""
    relative_times: List[float]
    cumulative_packet_count: List[int]
    cumulative_size_mb: List[float]
    total_packets: int
    total_size_mb: float
    duration_seconds: float
    
    class Config:
        """Pydantic configuration."""
        frozen = True
    
    @property
    def avg_packet_rate(self) -> float:
        """Calculate average packet rate."""
        return self.total_packets / max(self.duration_seconds, 1)
    
    @property 
    def avg_throughput(self) -> float:
        """Calculate average throughput in MB/sec."""
        return self.total_size_mb / max(self.duration_seconds, 1)


class RouterInfo(BaseModel):
    """Router information extracted from file path."""
    router_id: Optional[str] = None
    coordinates: Optional[Tuple[int, int]] = None
    raw_info: Optional[str] = None

    @property
    def display_name(self) -> str:
        """Generate a human-readable display name for the router."""
        if self.coordinates:
            return f"Router ({self.coordinates[0]}, {self.coordinates[1]})"
        elif self.router_id:
            return f"Router {self.router_id}"
        else:
            return "Router"


# ============================================================================
# Protocol Filtering Functions
# ============================================================================

def is_isis_packet(packet: Packet) -> bool:
    """Return True if packet is an IS-IS frame.

    Detection strategy:
    - Check for ISIS layers using proper Scapy contrib module layer names
    - Otherwise, check link-layer EtherType 0x22f0 (IS-IS over Ethernet),
      including VLAN-tagged frames (Dot1Q) and Linux cooked captures (SLL).
    """
    # 1) Check for ISIS contrib layers with correct names
    try:
        # Import ISIS contrib to ensure layers are registered
        from scapy.contrib.isis import ISIS_CommonHdr, ISIS_L1HelloPDU, ISIS_L2HelloPDU, ISIS_P2PHelloPDU, ISIS_LSPPDU, ISIS_CSNPPDU, ISIS_PSNPPDU
        
        # Check for actual ISIS layer classes
        isis_layers = [ISIS_CommonHdr, ISIS_L1HelloPDU, ISIS_L2HelloPDU, ISIS_P2PHelloPDU, ISIS_LSPPDU, ISIS_CSNPPDU, ISIS_PSNPPDU]
        for isis_layer in isis_layers:
            if packet.haslayer(isis_layer):
                return True
                
        # Also check by string name for backward compatibility
        for lname in ('ISIS_CommonHdr', 'ISIS_L1HelloPDU', 'ISIS_L2HelloPDU', 'ISIS_P2PHelloPDU', 
                     'ISIS_LSPPDU', 'ISIS_CSNPPDU', 'ISIS_PSNPPDU', 'CLNS'):
            if packet.haslayer(lname):
                return True
    except (ImportError, AttributeError, Exception):
        # Continue with EtherType checks if contrib layers not available
        pass

    # 2) EtherType checks (Ether and VLAN)
    try:
        # Direct Ethernet type
        if Ether in packet and getattr(packet[Ether], 'type', None) == 0x22F0:
            return True
        # VLAN-tagged (Dot1Q) frames: look at the type field on Dot1Q layers
        if packet.haslayer(Dot1Q):
            q = packet.getlayer(Dot1Q)
            # traverse possible QinQ stacks
            while q and isinstance(q, Dot1Q):
                if getattr(q, 'type', None) == 0x22F0:
                    return True
                q = q.payload if isinstance(q.payload, Dot1Q) else None
    except Exception:
        pass

    # 3) Linux cooked capture (SLL) - proto carries EtherType
    try:
        if packet.haslayer(CookedLinux):
            if getattr(packet[CookedLinux], 'proto', None) == 0x22F0:
                return True
    except Exception:
        pass

    # 4) LLC heuristic: OSI LLC with DSAP/SSAP 0xFE and NLPID 0x83 (IS-IS)
    try:
        if packet.haslayer(LLC):
            llc = packet.getlayer(LLC)
            if getattr(llc, 'dsap', None) == 0xFE and getattr(llc, 'ssap', None) == 0xFE:
                # Check NLPID (first byte of LLC payload) for IS-IS 0x83
                pl = bytes(llc.payload) if hasattr(llc, 'payload') else b''
                if pl and pl[0] == 0x83:
                    return True
                # If NLPID not accessible, still treat OSI LLC FE/FE as likely CLNS/IS-IS
                # to avoid missing frames; keep conservative and require Ether multicast below
                if Ether in packet:
                    dst = getattr(packet[Ether], 'dst', '').lower()
                    if dst in { '01:80:c2:00:00:14', '01:80:c2:00:00:15' }:
                        return True
    except Exception:
        pass

    return False


def is_ospf6_packet(packet: Packet) -> bool:
    """Check if packet is an OSPFv3 routing protocol packet using Scapy contrib."""
    try:
        # Check IPv6 next header 89 (OSPF) first
        if IPv6 in packet and packet[IPv6].nh == 89:
            return True
            
        # Use Scapy contrib for precise OSPFv3 detection with correct layer names
        from scapy.contrib.ospf import OSPF_Hdr, OSPF_Hello, OSPF_DBDesc, OSPF_LSReq, OSPF_LSUpd, OSPF_LSAck
        
        # Check for actual OSPF layer classes
        ospf_layers = [OSPF_Hdr, OSPF_Hello, OSPF_DBDesc, OSPF_LSReq, OSPF_LSUpd, OSPF_LSAck]
        for ospf_layer in ospf_layers:
            if packet.haslayer(ospf_layer):
                return True
                
        # Also check by string name for backward compatibility
        for lname in ('OSPF_Hdr', 'OSPF_Hello', 'OSPF_DBDesc', 'OSPF_LSReq', 'OSPF_LSUpd', 'OSPF_LSAck',
                     'OSPFv3_Hdr', 'OSPFv3_Hello', 'OSPFv3_DBDesc', 'OSPFv3_LSReq', 'OSPFv3_LSUpd', 'OSPFv3_LSAck'):
            if packet.haslayer(lname):
                return True
    except (ImportError, AttributeError, Exception):
        # Fallback to basic filtering if contrib parsing fails
        try:
            return IPv6 in packet and packet[IPv6].nh == 89
        except Exception:
            return False
    
    return False


def is_bgp_packet(packet: Packet) -> bool:
    """Check if packet is a BGP routing protocol packet using Scapy contrib."""
    try:
        # Check TCP port 179 first
        if TCP in packet and (packet[TCP].sport == 179 or packet[TCP].dport == 179):
            return True
            
        # Use Scapy contrib for precise BGP detection with correct layer names
        from scapy.contrib.bgp import BGPHeader, BGPOpen, BGPUpdate, BGPNotification, BGPKeepAlive
        
        # Check for actual BGP layer classes
        bgp_layers = [BGPHeader, BGPOpen, BGPUpdate, BGPNotification, BGPKeepAlive]
        for bgp_layer in bgp_layers:
            if packet.haslayer(bgp_layer):
                return True
                
        # Also check by string name for backward compatibility
        for lname in ('BGPHeader', 'BGPOpen', 'BGPUpdate', 'BGPNotification', 'BGPKeepAlive',
                     'BGP_Header', 'BGP_Open', 'BGP_Update', 'BGP_Notification', 'BGP_KeepAlive'):
            if packet.haslayer(lname):
                return True
    except (ImportError, AttributeError, Exception):
        # Fallback to basic filtering if contrib parsing fails
        try:
            return TCP in packet and (packet[TCP].sport == 179 or packet[TCP].dport == 179)
        except Exception:
            return False
    
    return False


def accept_all_packets(packet: Packet) -> bool:
    """Accept all packets (for unknown protocol types)."""
    return True


def extract_protocol_details(packet: Packet, protocol_info: ProtocolInfo) -> Dict[str, str]:
    """Extract detailed protocol information from packet using Scapy contrib."""
    details = {}
    
    try:
        if protocol_info.protocol_type == ProtocolType.ISIS:
            # Check for different ISIS PDU types using correct layer names
            try:
                from scapy.contrib.isis import ISIS_CommonHdr, ISIS_L1HelloPDU, ISIS_L2HelloPDU, ISIS_P2PHelloPDU, ISIS_LSPPDU
                
                if packet.haslayer(ISIS_L1HelloPDU) or packet.haslayer('ISIS_L1HelloPDU'):
                    hello = packet.getlayer(ISIS_L1HelloPDU) or packet.getlayer('ISIS_L1HelloPDU')
                    details.update({
                        'type': 'ISIS L1 Hello',
                        'system_id': getattr(hello, 'source_id', getattr(hello, 'sysid', 'Unknown')),
                        'hold_time': str(getattr(hello, 'hold_time', getattr(hello, 'holdtime', 'Unknown')))
                    })
                elif packet.haslayer(ISIS_L2HelloPDU) or packet.haslayer('ISIS_L2HelloPDU'):
                    hello = packet.getlayer(ISIS_L2HelloPDU) or packet.getlayer('ISIS_L2HelloPDU')
                    details.update({
                        'type': 'ISIS L2 Hello',
                        'system_id': getattr(hello, 'source_id', getattr(hello, 'sysid', 'Unknown')),
                        'hold_time': str(getattr(hello, 'hold_time', getattr(hello, 'holdtime', 'Unknown')))
                    })
                elif packet.haslayer(ISIS_P2PHelloPDU) or packet.haslayer('ISIS_P2PHelloPDU'):
                    hello = packet.getlayer(ISIS_P2PHelloPDU) or packet.getlayer('ISIS_P2PHelloPDU')
                    details.update({
                        'type': 'ISIS P2P Hello',
                        'system_id': getattr(hello, 'source_id', getattr(hello, 'sysid', 'Unknown')),
                        'hold_time': str(getattr(hello, 'hold_time', getattr(hello, 'holdtime', 'Unknown')))
                    })
                elif packet.haslayer(ISIS_LSPPDU) or packet.haslayer('ISIS_LSPPDU'):
                    lsp = packet.getlayer(ISIS_LSPPDU) or packet.getlayer('ISIS_LSPPDU')
                    details.update({
                        'type': 'ISIS LSP',
                        'lifetime': str(getattr(lsp, 'remaining_lifetime', getattr(lsp, 'lifetime', 'Unknown'))),
                        'sequence': str(getattr(lsp, 'sequence_number', getattr(lsp, 'seqnum', 'Unknown')))
                    })
                elif packet.haslayer(ISIS_CommonHdr) or packet.haslayer('ISIS_CommonHdr'):
                    hdr = packet.getlayer(ISIS_CommonHdr) or packet.getlayer('ISIS_CommonHdr')
                    details.update({
                        'type': f"ISIS PDU Type {getattr(hdr, 'pdu_type', 'Unknown')}",
                        'length': str(getattr(hdr, 'pdu_length', 'Unknown'))
                    })
            except (ImportError, AttributeError):
                # Fallback to generic layer detection
                for layer_name in ['ISIS_Hello', 'ISIS_LSP', 'ISIS_CommonHdr']:
                    if packet.haslayer(layer_name):
                        layer = packet.getlayer(layer_name)
                        details.update({
                            'type': f"ISIS {layer_name.split('_')[1]}",
                            'layer': layer_name
                        })
                        break
                
        elif protocol_info.protocol_type == ProtocolType.OSPF6:
            # Check for OSPF headers using correct layer names
            try:
                from scapy.contrib.ospf import OSPF_Hdr, OSPF_Hello
                
                if packet.haslayer(OSPF_Hdr) or packet.haslayer('OSPF_Hdr'):
                    header = packet.getlayer(OSPF_Hdr) or packet.getlayer('OSPF_Hdr')
                    details.update({
                        'type': f"OSPF Type {getattr(header, 'type', 'Unknown')}",
                        'router_id': str(getattr(header, 'router', getattr(header, 'routerid', 'Unknown'))),
                        'area_id': str(getattr(header, 'area', getattr(header, 'areaid', 'Unknown')))
                    })
                elif packet.haslayer(OSPF_Hello) or packet.haslayer('OSPF_Hello'):
                    hello = packet.getlayer(OSPF_Hello) or packet.getlayer('OSPF_Hello')
                    details.update({
                        'type': 'OSPF Hello',
                        'hello_interval': str(getattr(hello, 'hellointerval', 'Unknown')),
                        'dead_interval': str(getattr(hello, 'deadinterval', 'Unknown'))
                    })
            except (ImportError, AttributeError):
                # Fallback to generic layer detection  
                for layer_name in ['OSPFv3_Hdr', 'OSPFv3_Hello', 'OSPF_Hdr', 'OSPF_Hello']:
                    if packet.haslayer(layer_name):
                        layer = packet.getlayer(layer_name)
                        details.update({
                            'type': f"OSPF {layer_name.split('_')[1] if '_' in layer_name else 'Packet'}",
                            'layer': layer_name
                        })
                        break
                
        elif protocol_info.protocol_type == ProtocolType.BGP:
            # Check for BGP headers using correct layer names
            try:
                from scapy.contrib.bgp import BGPHeader, BGPOpen, BGPUpdate
                
                if packet.haslayer(BGPHeader) or packet.haslayer('BGPHeader'):
                    bgp = packet.getlayer(BGPHeader) or packet.getlayer('BGPHeader')
                    details.update({
                        'type': f"BGP Type {getattr(bgp, 'type', 'Unknown')}",
                        'length': str(getattr(bgp, 'len', getattr(bgp, 'length', 'Unknown')))
                    })
                elif packet.haslayer(BGPUpdate) or packet.haslayer('BGPUpdate'):
                    update = packet.getlayer(BGPUpdate) or packet.getlayer('BGPUpdate')
                    details.update({
                        'type': 'BGP Update',
                        'withdrawn_routes': str(len(getattr(update, 'withdrawn_routes', []))),
                        'path_attributes': str(len(getattr(update, 'path_attributes', [])))
                    })
                elif packet.haslayer(BGPOpen) or packet.haslayer('BGPOpen'):
                    open_msg = packet.getlayer(BGPOpen) or packet.getlayer('BGPOpen')
                    details.update({
                        'type': 'BGP Open',
                        'as_number': str(getattr(open_msg, 'my_as', 'Unknown')),
                        'hold_time': str(getattr(open_msg, 'hold_time', 'Unknown'))
                    })
            except (ImportError, AttributeError):
                # Fallback to generic layer detection
                for layer_name in ['BGPHeader', 'BGPOpen', 'BGPUpdate', 'BGPNotification', 'BGPKeepAlive']:
                    if packet.haslayer(layer_name):
                        layer = packet.getlayer(layer_name)
                        details.update({
                            'type': f"BGP {layer_name.replace('BGP', '')}",
                            'layer': layer_name
                        })
                        break
                
    except Exception as e:
        details['parse_error'] = str(e)
    
    return details


# ============================================================================
# Protocol Registry 
# ============================================================================

PROTOCOL_REGISTRY: Dict[ProtocolType, ProtocolConfig] = {
    ProtocolType.ISIS: ProtocolConfig(
        name="isis",
        display_name="IS-IS",
        filter_func=is_isis_packet,
        keywords=['isis', 'is-is'],
        description="Intermediate System to Intermediate System"
    ),
    ProtocolType.OSPF6: ProtocolConfig(
        name="ospf6",
        display_name="OSPFv6", 
        filter_func=is_ospf6_packet,
        keywords=['ospf6', 'ospfv6', 'ospf_v6', 'ospfv3'],
        description="Open Shortest Path First version 6"
    ),
    ProtocolType.BGP: ProtocolConfig(
        name="bgp",
        display_name="BGP",
        filter_func=is_bgp_packet,
        keywords=['bgp', 'bgp4'],
        description="Border Gateway Protocol"
    ),
    ProtocolType.UNKNOWN: ProtocolConfig(
        name="unknown",
        display_name="Unknown Protocol",
        filter_func=accept_all_packets,
        keywords=[],
        description="Unknown or unsupported protocol"
    )
}


# ============================================================================
# Information Extraction and Detection Functions
# ============================================================================

def extract_protocol_from_filename(filename: str) -> ProtocolInfo:
    """Extract protocol information from filename using pattern matching."""
    filename_lower = Path(filename).stem.lower()

    # Try each registered protocol
    for protocol_type, config in PROTOCOL_REGISTRY.items():
        if protocol_type == ProtocolType.UNKNOWN:
            continue
            
        for keyword in config.keywords:
            if keyword in filename_lower:
                return ProtocolInfo(
                    protocol_type=protocol_type,
                    raw_info=keyword
                )

    # Default to ISIS if no protocol detected
    return ProtocolInfo(protocol_type=ProtocolType.ISIS)


def extract_topology_from_filename(filename: str) -> TopologyInfo:
    """Extract topology information from filename using pattern matching."""
    filename_lower = Path(filename).stem.lower()

    # Define topology patterns with their types
    topology_patterns = [
        (TopologyType.GRID, [
            r'grid(\d+)x(\d+)(?:x(\d+))?',
            r'(\d+)x(\d+)(?:x(\d+))?.*grid',
            r'grid.*?(\d+)x(\d+)(?:x(\d+))?',
        ]),
        (TopologyType.TORUS, [
            r'torus(\d+)x(\d+)(?:x(\d+))?',
            r'(\d+)x(\d+)(?:x(\d+))?.*torus',
            r'torus.*?(\d+)x(\d+)(?:x(\d+))?',
        ]),
        (TopologyType.SIZE, [
            r'size(\d+)',
            r'(\d+).*size',
            r'size.*?(\d+)',
        ]),
    ]

    # Try each topology type
    for topology_type, patterns in topology_patterns:
        for pattern in patterns:
            if match := re.search(pattern, filename_lower):
                if topology_type == TopologyType.SIZE:
                    return TopologyInfo(
                        topology_type=topology_type,
                        size=int(match.group(1)),
                        raw_info=match.group(0)
                    )
                else:
                    dimensions = tuple(int(d) for d in match.groups() if d is not None)
                    return TopologyInfo(
                        topology_type=topology_type,
                        dimensions=dimensions,
                        raw_info=match.group(0)
                    )

    return TopologyInfo(topology_type=TopologyType.UNKNOWN)


def extract_router_from_path(file_path: str) -> RouterInfo:
    """Extract router information from file path."""
    path_parts = Path(file_path).parts

    # Look for router directory pattern in path
    for part in path_parts:
        # Match router_XX_YY pattern (coordinates)
        if match := re.match(r'router_(\d+)_(\d+)', part.lower()):
            x, y = int(match.group(1)), int(match.group(2))
            return RouterInfo(
                router_id=f"{x:02d}_{y:02d}",
                coordinates=(x, y),
                raw_info=part
            )

        # Match router_XXX pattern (simple ID)
        elif match := re.match(r'router_(\w+)', part.lower()):
            router_id = match.group(1)
            return RouterInfo(
                router_id=router_id,
                raw_info=part
            )

        # Match routerXX pattern (no underscore)
        elif match := re.match(r'router(\d+)', part.lower()):
            router_id = match.group(1)
            return RouterInfo(
                router_id=router_id,
                raw_info=part
            )

    return RouterInfo()


def detect_protocol_by_content(pcap_path: Path, sample_limit: int = 5000) -> ProtocolInfo:
    """Detect protocol by scanning up to sample_limit packets and counting matches.

    Returns the protocol with the highest number of matches when the count is > 0.
    If no matches found, returns UNKNOWN.
    """
    counts: Dict[ProtocolType, int] = {ptype: 0 for ptype in PROTOCOL_REGISTRY if ptype != ProtocolType.UNKNOWN}
    total_scanned = 0

    try:
        for pkt_data, metadata in RawPcapReader(str(pcap_path)):
            total_scanned += 1
            if total_scanned > sample_limit:
                break
            try:
                packet = Ether(pkt_data)
            except Exception:
                continue

            for ptype, config in PROTOCOL_REGISTRY.items():
                if ptype == ProtocolType.UNKNOWN:
                    continue
                try:
                    if config.filter_func(packet):
                        counts[ptype] += 1
                except Exception:
                    continue
    except Exception:
        # Fall back to UNKNOWN on reader errors
        return ProtocolInfo(protocol_type=ProtocolType.UNKNOWN)

    # Choose the protocol with the highest count if non-zero
    best_ptype: Optional[ProtocolType] = None
    best_count = 0
    for ptype, count in counts.items():
        if count > best_count:
            best_ptype = ptype
            best_count = count

    if best_ptype is not None and best_count > 0:
        return ProtocolInfo(protocol_type=best_ptype, raw_info=f"content:{best_count}")

    return ProtocolInfo(protocol_type=ProtocolType.UNKNOWN)


def is_protocol_packet(packet: Packet, protocol_info: ProtocolInfo) -> bool:
    """Check if a packet matches the specified protocol type."""
    return protocol_info.config.filter_func(packet)


def read_packets_from_pcap(pcap_path: Path, protocol_info: ProtocolInfo, 
                          use_streaming: bool = True, sample_details: int = 5) -> List[PacketData]:
    """
    Read packets from PCAP file with protocol filtering and progress tracking.
    
    Args:
        pcap_path: Path to PCAP file
        protocol_info: Protocol information for filtering
        use_streaming: Use RawPcapReader for better performance on large files
        sample_details: Number of packets to show detailed protocol information for
    """
    packets: List[PacketData] = []
    total_packets = 0
    filtered_packets = 0
    protocol_details_shown = 0

    def maybe_log_sample_details(packet: Packet) -> None:
        nonlocal protocol_details_shown
        if protocol_details_shown >= sample_details:
            return
        details = extract_protocol_details(packet, protocol_info)
        if not details:
            return
        detail_str = ", ".join([f"{k}: {v}" for k, v in details.items()])
        log_info(f"Sample packet {protocol_details_shown + 1}: {detail_str}")
        protocol_details_shown += 1

    def process_match(packet: Packet, timestamp: float, size: int) -> None:
        nonlocal filtered_packets
        packets.append(PacketData(timestamp=timestamp, size=size))
        filtered_packets += 1
        maybe_log_sample_details(packet)

    with console.status(f"[bold blue]Reading PCAP file: {pcap_path.name}"):
        # First try streaming for performance
        if use_streaming:
            try:
                for pkt_data, metadata in RawPcapReader(str(pcap_path)):
                    total_packets += 1
                    try:
                        packet = Ether(pkt_data)
                        if is_protocol_packet(packet, protocol_info):
                            ts = float(metadata.sec + metadata.usec / 1_000_000)
                            process_match(packet, ts, len(pkt_data))
                    except Exception:
                        # Skip malformed packets
                        continue
            except Exception as e:
                log_warning(f"Streaming reader failed, falling back to standard reader: {e}")
                use_streaming = False

        # If streaming had traffic but no matches, retry with standard reader
        if use_streaming and total_packets > 0 and filtered_packets == 0:
            log_warning("No protocol matches found with streaming reader; retrying with standard reader for broader decoding...")
            use_streaming = False

        # Standard reader (or fallback)
        if not use_streaming:
            with PcapReader(str(pcap_path)) as pcap_reader:
                for packet in pcap_reader:
                    total_packets += 1
                    try:
                        if is_protocol_packet(packet, protocol_info):
                            process_match(packet, float(packet.time), len(packet))
                    except Exception:
                        continue

    log_info(
        f"Read {total_packets} total packets, filtered to {filtered_packets} {protocol_info.display_name} packets from {pcap_path.name}"
    )

    if filtered_packets == 0:
        log_warning(f"No {protocol_info.display_name} packets found in {pcap_path.name}")
        log_info("Ensure the PCAP contains the expected protocol traffic and check filename for protocol detection")

    return packets


def process_packet_data(packets: List[PacketData]) -> ProcessedData:
    """Process raw packet data into analysis-ready format."""
    if not packets:
        raise ValueError("No packets found in the data")

    # Extract data using list comprehensions for better performance
    timestamps = [p.timestamp for p in packets]
    sizes = [p.size for p in packets]

    # Calculate relative times and cumulative statistics
    start_time = timestamps[0]
    relative_times = [t - start_time for t in timestamps]
    cumulative_packet_count = list(range(1, len(packets) + 1))
    cumulative_size_mb = (np.cumsum(sizes) / (1024 * 1024)).tolist()

    return ProcessedData(
        relative_times=relative_times,
        cumulative_packet_count=cumulative_packet_count,
        cumulative_size_mb=cumulative_size_mb,
        total_packets=len(packets),
        total_size_mb=sum(sizes) / (1024 * 1024),
        duration_seconds=relative_times[-1] if relative_times else 0
    )


def create_comprehensive_title(
    topology_info: TopologyInfo,
    protocol_info: ProtocolInfo,
    router_info: RouterInfo,
    base_title: str = "Network Traffic Analysis"
) -> str:
    """Create a comprehensive title incorporating topology, protocol and router information."""
    title_parts = [base_title]

    # Add protocol information
    if protocol_info.protocol_type != ProtocolType.UNKNOWN:
        title_parts.append(protocol_info.display_name)

    # Add topology information
    if topology_info.topology_type != TopologyType.UNKNOWN:
        title_parts.append(topology_info.display_name)

    # Add router information
    if router_info.router_id or router_info.coordinates:
        title_parts.append(router_info.display_name)

    return " - ".join(title_parts)


# ============================================================================
# Plotting and Visualization
# ============================================================================

def configure_plot_style(config: PlotConfig = PlotConfig()) -> None:
    """Configure matplotlib with publication-quality settings."""
    plt.rcParams.update({
        'font.family': config.font_family,
        'font.size': config.font_size,
        'axes.labelsize': config.font_size + 2,
        'xtick.labelsize': config.font_size,
        'ytick.labelsize': config.font_size,
        'legend.fontsize': config.font_size,
        'figure.dpi': 100,
        'savefig.dpi': config.dpi,
        'savefig.bbox': 'tight',
    })


def create_traffic_plot(
    processed_data: ProcessedData, 
    topology_info: TopologyInfo,
    protocol_info: ProtocolInfo, 
    router_info: RouterInfo,
    config: PlotConfig = PlotConfig()
) -> plt.Figure:
    """Create a traffic analysis plot with dual y-axes."""
    fig, ax1 = plt.subplots(figsize=config.figure_size)

    # Plot cumulative size on primary axis
    line1 = ax1.plot(
        processed_data.relative_times,
        processed_data.cumulative_size_mb,
        color=config.primary_color,
        linewidth=2,
        label='Cumulative Size (MB)'
    )

    ax1.set_xlabel('Time (s)')
    ax1.set_ylabel('Cumulative Size (MB)', color=config.primary_color)
    ax1.tick_params(axis='y', labelcolor=config.primary_color)
    ax1.grid(True, alpha=config.grid_alpha)

    # Create secondary axis for packet count
    ax2 = ax1.twinx()
    line2 = ax2.plot(
        processed_data.relative_times,
        processed_data.cumulative_packet_count,
        color=config.secondary_color,
        linestyle='--',
        linewidth=2,
        label='Cumulative Packet Count'
    )

    ax2.set_ylabel('Cumulative Packet Count', color=config.secondary_color)
    ax2.tick_params(axis='y', labelcolor=config.secondary_color)

    # Set comprehensive title
    title = create_comprehensive_title(topology_info, protocol_info, router_info)
    fig.suptitle(title, fontsize=config.font_size + 4, fontweight='bold')

    # Clean up spines
    for spine in ['top']:
        ax1.spines[spine].set_visible(False)
        ax2.spines[spine].set_visible(False)

    # Create combined legend
    lines = line1 + line2
    labels = [line.get_label() for line in lines]
    ax1.legend(lines, labels, loc='upper left', framealpha=0.9)

    fig.tight_layout()
    return fig


def display_analysis_summary(
    processed_data: ProcessedData, 
    topology_info: TopologyInfo, 
    protocol_info: ProtocolInfo, 
    router_info: RouterInfo
) -> None:
    """Display analysis summary using rich table."""
    table = Table(title="📊 PCAP Analysis Summary", show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Value", style="green")

    # Protocol and topology information
    table.add_row("Protocol", protocol_info.display_name)
    table.add_row("Topology", topology_info.display_name)
    
    # Router information if available
    if router_info.router_id or router_info.coordinates:
        table.add_row("Router", router_info.display_name)

    # Protocol detection status
    table.add_row("Protocol Detection", "✅ Enhanced (Scapy contrib)")

    # Traffic statistics
    table.add_row("Total Packets", f"{processed_data.total_packets:,}")
    table.add_row("Duration", f"{processed_data.duration_seconds:.2f} seconds")
    table.add_row("Total Size", f"{processed_data.total_size_mb:.2f} MB")
    table.add_row("Avg Packet Rate", f"{processed_data.avg_packet_rate:.1f} packets/sec")
    table.add_row("Avg Throughput", f"{processed_data.avg_throughput:.2f} MB/sec")

    console.print(table)


def generate_default_output_name(pcap_path: Path, topology_info: TopologyInfo, 
                                protocol_info: ProtocolInfo, router_info: RouterInfo) -> str:
    """Generate a descriptive default output filename based on protocol, topology and router."""
    base_name = pcap_path.stem
    name_parts = ["traffic_analysis", base_name]

    # Add protocol information
    if protocol_info.protocol_type != ProtocolType.UNKNOWN:
        name_parts.append(protocol_info.protocol_type.value)

    # Add topology information
    if topology_info.topology_type != TopologyType.UNKNOWN:
        if topology_info.topology_type == TopologyType.SIZE and topology_info.size:
            name_parts.append(f"size{topology_info.size}")
        elif topology_info.topology_type in [TopologyType.GRID, TopologyType.TORUS] and topology_info.dimensions:
            dims = "x".join(map(str, topology_info.dimensions))
            topo_type = topology_info.topology_type.value
            name_parts.append(f"{topo_type}{dims}")
        else:
            name_parts.append(topology_info.topology_type.value)

    # Add router information
    if router_info.coordinates:
        name_parts.append(f"router{router_info.coordinates[0]:02d}_{router_info.coordinates[1]:02d}")
    elif router_info.router_id:
        name_parts.append(f"router{router_info.router_id}")

    return "_".join(name_parts) + ".png"


# ============================================================================
# Main Analysis Class
# ============================================================================

class PcapAnalyzer:
    """Main class for PCAP traffic analysis with enhanced protocol filtering using Scapy contrib."""
    
    def __init__(self, plot_config: PlotConfig = PlotConfig(), use_streaming: bool = True, sample_details: int = 5):
        self.plot_config = plot_config
        self.use_streaming = use_streaming
        self.sample_details = sample_details
    
    def analyze_file(
        self,
        pcap_path: Path,
        output_path: Optional[Path] = None,
        forced_protocol: Optional[ProtocolType] = None,
    ) -> None:
        """Analyze a PCAP file and generate traffic plot with enhanced protocol detection."""
        try:
            # Extract information from filename and path
            topology_info = extract_topology_from_filename(str(pcap_path))
            protocol_info = (
                ProtocolInfo(protocol_type=forced_protocol)
                if forced_protocol is not None
                else extract_protocol_from_filename(str(pcap_path))
            )
            router_info = extract_router_from_path(str(pcap_path))

            # Generate output filename if not provided
            if output_path is None:
                auto_name = generate_default_output_name(pcap_path, topology_info, protocol_info, router_info)
                output_path = Path(".") / auto_name

            self._display_analysis_info(pcap_path, topology_info, protocol_info, router_info)

            # Process data pipeline with enhanced protocol detection
            packets = read_packets_from_pcap(pcap_path, protocol_info, self.use_streaming, self.sample_details)
            
            if not packets:
                log_error(f"No {protocol_info.display_name} packets found in the PCAP file")
                log_info("Consider checking the filename for proper protocol detection keywords")
                raise typer.Exit(1)
                
            processed_data = process_packet_data(packets)

            # Display results and generate plot
            display_analysis_summary(processed_data, topology_info, protocol_info, router_info)
            self._generate_plot(processed_data, topology_info, protocol_info, router_info, output_path)

            log_success(f"Plot saved to: {output_path}")

        except FileNotFoundError:
            log_error(f"File not found: {pcap_path}")
            raise typer.Exit(1)
        except ValueError as e:
            log_error(f"Data error: {e}")
            raise typer.Exit(1)
        except Exception as e:
            log_error(f"Unexpected error: {e}")
            raise typer.Exit(1)

    def _display_analysis_info(self, pcap_path: Path, topology_info: TopologyInfo, 
                              protocol_info: ProtocolInfo, router_info: RouterInfo) -> None:
        """Display initial analysis information."""
        console.print(f"🔍 [bold blue]Analyzing:[/bold blue] {pcap_path.name}")
        console.print(f"📡 [bold magenta]Protocol:[/bold magenta] {protocol_info.display_name}")
        console.print(f"🏗️  [bold yellow]Topology:[/bold yellow] {topology_info.display_name}")
        if router_info.router_id or router_info.coordinates:
            console.print(f"🖥️  [bold cyan]Router:[/bold cyan] {router_info.display_name}")
        
        # Show protocol detection capability
        console.print("✅ [bold green]Enhanced protocol detection enabled (Scapy contrib)")

    def _generate_plot(self, processed_data: ProcessedData, topology_info: TopologyInfo,
                      protocol_info: ProtocolInfo, router_info: RouterInfo, output_path: Path) -> None:
        """Generate and save the traffic plot."""
        with console.status("[bold green]Generating plot..."):
            configure_plot_style(self.plot_config)
            fig = create_traffic_plot(processed_data, topology_info, protocol_info, router_info, self.plot_config)
            
            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            fig.savefig(output_path, bbox_inches='tight')
            plt.close(fig)


# ============================================================================
# Utility Functions (Backwards Compatibility)
# ============================================================================

def analyze_and_plot_traffic(pcap_path: Path, output_path: Path, use_auto_name: bool = False) -> None:
    """Legacy function for backwards compatibility. Use PcapAnalyzer class instead."""
    analyzer = PcapAnalyzer()
    analyzer.analyze_file(pcap_path, output_path if not use_auto_name else None)


def main(
    pcap_path: Path = typer.Argument(..., help="Path to the PCAP file to be analyzed", exists=True),
    output_path: Optional[Path] = typer.Argument(
        None,
        help="Output file path for the plot (supports .png, .pdf, .svg, etc.). If not provided, auto-generates based on protocol and topology."
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
    dpi: int = typer.Option(300, "--dpi", help="Output plot DPI quality"),
    width: float = typer.Option(12.0, "--width", help="Plot width in inches"),
    height: float = typer.Option(8.0, "--height", help="Plot height in inches"),
    streaming: bool = typer.Option(True, "--streaming/--no-streaming", help="Use streaming reader for large files (default: True)"),
    sample_details: int = typer.Option(5, "--sample-details", help="Number of packets to show detailed protocol information for (default: 5)"),
    protocol: Optional[str] = typer.Option(
        None,
        "--protocol",
        case_sensitive=False,
        help="Force protocol filter: isis | ospf6 | bgp. Overrides filename detection.",
    ),
    autodetect: bool = typer.Option(
        False,
        "--autodetect",
        help="Detect protocol by PCAP content if filename lacks keywords",
    ),
) -> None:
    """
    🚀 PCAP Traffic Analysis Tool

    Analyzes PCAP files and generates publication-quality traffic trend plots
    with automatic topology and protocol detection. Uses enhanced Scapy contrib
    modules for precise protocol parsing when available.

    Supported routing protocols with enhanced detection:
    - ISIS - Detects Hello, LSP, CSNP, PSNP packets with System ID, Hold Time, etc.
    - OSPFv6 - Detects Hello, DBDesc, LSReq, LSUpd, LSAck with Router ID, Area ID, LSA details
    - BGP - Detects Open, Update, Keepalive, Notification with AS paths, NLRI, etc.

    Enhanced features:
    - Uses Scapy contrib modules for detailed protocol field access
    - Streaming reader for efficient processing of large PCAP files  
    - Sample protocol detail extraction for debugging and verification
    - Fallback to basic detection when contrib modules unavailable

    Examples:
        # Basic usage with enhanced protocol detection
        uv run experiment_utils/draw/draw_pcap.py ospfv3_capture.pcap

        # Show detailed info for first 10 packets
        uv run experiment_utils/draw/draw_pcap.py isis_torus5x5.pcap --sample-details 10

        # Disable streaming for small files or troubleshooting
        uv run experiment_utils/draw/draw_pcap.py bgp_session.pcap --no-streaming

        # Custom output with high DPI and verbose logging
        uv run experiment_utils/draw/draw_pcap.py capture.pcap output.png --dpi 600 --verbose
    """
    if verbose:
        log_info("Verbose mode enabled")

    # Create plot configuration
    plot_config = PlotConfig(
        figure_size=(width, height),
        dpi=dpi
    )

    # Create analyzer with enhanced options and run analysis
    analyzer = PcapAnalyzer(plot_config, streaming, sample_details)

    forced_protocol: Optional[ProtocolType] = None
    if protocol:
        normalized = protocol.strip().lower()
        name_to_type = {cfg.name: ptype for ptype, cfg in PROTOCOL_REGISTRY.items()}
        if normalized in name_to_type and name_to_type[normalized] != ProtocolType.UNKNOWN:
            forced_protocol = name_to_type[normalized]
        else:
            log_warning(f"Unknown protocol '{protocol}'. Falling back to filename or autodetection.")

    if forced_protocol is None and autodetect:
        detected = detect_protocol_by_content(pcap_path)
        if detected.protocol_type != ProtocolType.UNKNOWN:
            log_info(f"Content-based protocol detection: {detected.display_name}")
            forced_protocol = detected.protocol_type
        else:
            log_warning("Content-based detection could not determine protocol; using filename detection.")

    analyzer.analyze_file(pcap_path, output_path, forced_protocol=forced_protocol)


if __name__ == "__main__":
    typer.run(main)