import argparse
import re
from typing import NamedTuple, Optional, Tuple, List
from enum import Enum

import matplotlib.pyplot as plt
from scapy.all import PcapReader
import numpy as np


class TopologyType(Enum):
    """Network topology types that can be identified from filenames."""
    SIZE = "size"
    GRID = "grid"
    TORUS = "torus"
    UNKNOWN = "unknown"


class TopologyInfo(NamedTuple):
    """Information about network topology extracted from filename."""
    topology_type: TopologyType
    size: Optional[int] = None
    dimensions: Optional[Tuple[int, ...]] = None
    raw_info: Optional[str] = None

    @property
    def display_name(self) -> str:
        """Generate a human-readable display name for the topology."""
        if self.topology_type == TopologyType.SIZE and self.size:
            return f"Size {self.size}"
        elif self.topology_type == TopologyType.GRID and self.dimensions:
            if len(self.dimensions) == 2:
                return f"Grid {self.dimensions[0]}×{self.dimensions[1]}"
            else:
                return f"Grid {' × '.join(map(str, self.dimensions))}"
        elif self.topology_type == TopologyType.TORUS and self.dimensions:
            if len(self.dimensions) == 2:
                return f"Torus {self.dimensions[0]}×{self.dimensions[1]}"
            else:
                return f"Torus {' × '.join(map(str, self.dimensions))}"
        elif self.raw_info:
            return f"{self.topology_type.value.title()} {self.raw_info}"
        else:
            return self.topology_type.value.title()


class PacketData(NamedTuple):
    """Immutable packet data structure."""
    timestamp: float
    size: int


def extract_topology_from_filename(filename: str) -> TopologyInfo:
    """
    Extract topology information from filename using pattern matching.
    Pure function that analyzes filename patterns to identify network topology types.
    """
    filename_lower = filename.lower()

    # Try to identify grid topology
    grid_patterns = [
        r'grid(\d+)x(\d+)(?:x(\d+))?',
        r'(\d+)x(\d+)(?:x(\d+))?.*grid',
        r'grid.*?(\d+)x(\d+)(?:x(\d+))?',
    ]

    for pattern in grid_patterns:
        match = re.search(pattern, filename_lower)
        if match:
            dimensions = tuple(int(d) for d in match.groups() if d is not None)
            return TopologyInfo(
                topology_type=TopologyType.GRID,
                dimensions=dimensions,
                raw_info=match.group(0)
            )

    # Try to identify torus topology
    torus_patterns = [
        r'torus(\d+)x(\d+)(?:x(\d+))?',
        r'(\d+)x(\d+)(?:x(\d+))?.*torus',
        r'torus.*?(\d+)x(\d+)(?:x(\d+))?',
    ]

    for pattern in torus_patterns:
        match = re.search(pattern, filename_lower)
        if match:
            dimensions = tuple(int(d) for d in match.groups() if d is not None)
            return TopologyInfo(
                topology_type=TopologyType.TORUS,
                dimensions=dimensions,
                raw_info=match.group(0)
            )

    # Try to identify size topology
    size_patterns = [
        r'size(\d+)',
        r'(\d+).*size',
        r'size.*?(\d+)',
    ]

    for pattern in size_patterns:
        match = re.search(pattern, filename_lower)
        if match:
            size = int(match.group(1))
            return TopologyInfo(
                topology_type=TopologyType.SIZE,
                size=size,
                raw_info=match.group(0)
            )

    # Default to unknown topology
    return TopologyInfo(topology_type=TopologyType.UNKNOWN)


def read_packets_from_pcap(pcap_path: str) -> List[PacketData]:
    """
    Read packets from PCAP file and return as list of PacketData.
    Pure function for data extraction.
    """
    packets = []
    with PcapReader(pcap_path) as pcap_reader:
        for packet in pcap_reader:
            packets.append(PacketData(
                timestamp=float(packet.time),
                size=len(packet)
            ))
    return packets


def process_packet_data(packets: List[PacketData]) -> dict:
    """
    Process raw packet data into analysis-ready format.
    Pure function that transforms packet data into cumulative statistics.
    """
    if not packets:
        raise ValueError("No packets found in the data")

    timestamps = [p.timestamp for p in packets]
    sizes = [p.size for p in packets]

    start_time = timestamps[0]
    relative_times = [t - start_time for t in timestamps]
    cumulative_packet_count = list(range(1, len(packets) + 1))
    cumulative_size_mb = (np.cumsum(sizes) / (1024 * 1024)).tolist()

    return {
        'relative_times': relative_times,
        'cumulative_packet_count': cumulative_packet_count,
        'cumulative_size_mb': cumulative_size_mb,
        'total_packets': len(packets),
        'total_size_mb': sum(sizes) / (1024 * 1024),
        'duration_seconds': relative_times[-1] if relative_times else 0
    }


def create_topology_title(topology_info: TopologyInfo, base_title: str = "Network Traffic Analysis") -> str:
    """
    Create a descriptive title incorporating topology information.
    Pure function that generates plot titles based on topology info.
    """
    if topology_info.topology_type == TopologyType.UNKNOWN:
        return base_title
    return f"{base_title} - {topology_info.display_name}"


def configure_plot_style() -> None:
    """Configure matplotlib with publication-quality settings."""
    plt.rcParams.update({
        'font.family': 'serif',
        'font.size': 12,
        'axes.labelsize': 14,
        'xtick.labelsize': 12,
        'ytick.labelsize': 12,
        'legend.fontsize': 12,
    })


def create_traffic_plot(processed_data: dict, topology_info: TopologyInfo, figure_size: Tuple[float, float] = (8, 5)) -> plt.Figure:
    """
    Create a traffic analysis plot with dual y-axes.
    Pure function (except for matplotlib state) that creates a publication-quality plot.
    """
    fig, ax1 = plt.subplots(figsize=figure_size)

    color1 = 'tab:blue'
    color2 = 'tab:orange'

    # Plot cumulative size on primary axis
    line1 = ax1.plot(
        processed_data['relative_times'],
        processed_data['cumulative_size_mb'],
        color=color1,
        linestyle='-',
        label='Cumulative Size (MB)'
    )

    ax1.set_xlabel('Time (s)')
    ax1.set_ylabel('Cumulative Size (MB)', color=color1)
    ax1.tick_params(axis='y', labelcolor=color1)
    ax1.grid(True, which='both', linestyle='--', linewidth=0.5)

    # Create secondary axis for packet count
    ax2 = ax1.twinx()
    line2 = ax2.plot(
        processed_data['relative_times'],
        processed_data['cumulative_packet_count'],
        color=color2,
        linestyle='--',
        label='Cumulative Packet Count'
    )

    ax2.set_ylabel('Cumulative Packet Count', color=color2)
    ax2.tick_params(axis='y', labelcolor=color2)

    # Create title with topology information
    title = create_topology_title(topology_info)
    fig.suptitle(title, fontsize=16)

    # Configure aesthetics
    ax1.spines['top'].set_visible(False)
    ax2.spines['top'].set_visible(False)

    # Create combined legend
    lines = line1 + line2
    labels = [line.get_label() for line in lines]
    ax1.legend(lines, labels, loc='upper left')

    fig.tight_layout()
    return fig


def analyze_and_plot_traffic(pcap_path, output_path):
    """
    Analyzes a PCAP file and saves a single, academic-style plot showing
    cumulative traffic size and packet count over time with topology recognition.

    Args:
        pcap_path (str): The path to the PCAP file to be analyzed.
        output_path (str): The path where the output plot image will be saved.
    """
    # Extract topology information from filename
    topology_info = extract_topology_from_filename(pcap_path)

    print(f"[INFO] Starting analysis for file: {pcap_path}...")
    print(f"[INFO] Detected topology: {topology_info.display_name}")

    try:
        # Functional pipeline: read -> process -> visualize
        packets = read_packets_from_pcap(pcap_path)
        processed_data = process_packet_data(packets)

        print(f"[INFO] Analysis complete. Processed {processed_data['total_packets']} packets.")
        print(f"[INFO] Duration: {processed_data['duration_seconds']:.2f} seconds")
        print(f"[INFO] Total size: {processed_data['total_size_mb']:.2f} MB")

        # Configure plot style and create visualization
        print(f"[INFO] Generating plot and saving to {output_path}...")
        configure_plot_style()

        fig = create_traffic_plot(processed_data, topology_info)

        # Save the figure
        fig.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"[SUCCESS] Plot saved successfully to {output_path}")

        # Close the plot to free up memory
        plt.close(fig)

    except FileNotFoundError:
        print(f"[ERROR] File not found: '{pcap_path}'")
        return
    except ValueError as e:
        print(f"[ERROR] {e}")
        return
    except Exception as e:
        print(f"[ERROR] Failed to read or parse PCAP file: {e}")
        return


if __name__ == "__main__":
    # --- Command-Line Argument Parsing ---
    parser = argparse.ArgumentParser(
        description="Analyzes a PCAP file and generates a traffic trend plot.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    parser.add_argument(
        "pcap_path",
        type=str,
        help="Path to the PCAP file to be analyzed."
    )
    
    parser.add_argument(
        "-o", "--output",
        type=str,
        default="traffic_analysis_plot.png",
        help="Output file path for the plot.\n"
             "Supported formats depend on your matplotlib backend (e.g., .pdf, .png, .svg).\n"
             "Default: traffic_analysis_plot.png"
    )

    args = parser.parse_args()

    # Run the analysis and plotting function
    analyze_and_plot_traffic(args.pcap_path, args.output)