#!/usr/bin/env python3
"""
PCAP Traffic Analysis Tool

Analyzes PCAP files and generates publication-quality traffic trend plots
with automatic topology detection and rich console output.
"""

import re
from pathlib import Path
from typing import Optional, Tuple, List
from enum import Enum

import matplotlib.pyplot as plt
import numpy as np
import typer
from loguru import logger
from pydantic import BaseModel, Field, validator
from rich.console import Console
from rich.progress import track
from rich.table import Table
from scapy.all import PcapReader

# Initialize rich console
console = Console()

# Configure loguru
logger.remove()
logger.add(
    lambda msg: console.print(f"[dim]{msg}[/dim]", markup=True),
    level="INFO",
    format="{message}"
)


class TopologyType(Enum):
    """Network topology types that can be identified from filenames."""
    SIZE = "size"
    GRID = "grid"
    TORUS = "torus"
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
        if self.topology_type == TopologyType.SIZE and self.size:
            return f"Size {self.size}"
        elif self.topology_type == TopologyType.GRID and self.dimensions:
            dims = "×".join(map(str, self.dimensions))
            return f"Grid {dims}"
        elif self.topology_type == TopologyType.TORUS and self.dimensions:
            dims = "×".join(map(str, self.dimensions))
            return f"Torus {dims}"
        elif self.raw_info:
            return f"{self.topology_type.value.title()} {self.raw_info}"
        else:
            return self.topology_type.value.title()


class PacketData(BaseModel):
    """Immutable packet data structure with validation."""
    timestamp: float = Field(..., gt=0, description="Packet timestamp")
    size: int = Field(..., gt=0, description="Packet size in bytes")


class ProcessedData(BaseModel):
    """Processed packet analysis results."""
    relative_times: List[float]
    cumulative_packet_count: List[int]
    cumulative_size_mb: List[float]
    total_packets: int = Field(..., gt=0)
    total_size_mb: float = Field(..., gt=0)
    duration_seconds: float = Field(..., ge=0)


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


def read_packets_from_pcap(pcap_path: Path) -> List[PacketData]:
    """Read packets from PCAP file with progress tracking."""
    packets = []

    with console.status(f"[bold blue]Reading PCAP file: {pcap_path.name}"):
        with PcapReader(str(pcap_path)) as pcap_reader:
            for packet in pcap_reader:
                packets.append(PacketData(
                    timestamp=float(packet.time),
                    size=len(packet)
                ))

    logger.info(f"Read {len(packets)} packets from {pcap_path.name}")
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
    router_info: RouterInfo,
    base_title: str = "Network Traffic Analysis"
) -> str:
    """Create a comprehensive title incorporating topology and router information."""
    title_parts = [base_title]

    # Add topology information
    if topology_info.topology_type != TopologyType.UNKNOWN:
        title_parts.append(topology_info.display_name)

    # Add router information
    if router_info.router_id or router_info.coordinates:
        title_parts.append(router_info.display_name)

    return " - ".join(title_parts)


def configure_plot_style() -> None:
    """Configure matplotlib with publication-quality settings."""
    plt.rcParams.update({
        'font.family': 'serif',
        'font.size': 12,
        'axes.labelsize': 14,
        'xtick.labelsize': 12,
        'ytick.labelsize': 12,
        'legend.fontsize': 12,
        'figure.dpi': 100,
        'savefig.dpi': 300,
        'savefig.bbox': 'tight',
    })


def create_traffic_plot(processed_data: ProcessedData, topology_info: TopologyInfo,
                       router_info: RouterInfo, figure_size: Tuple[float, float] = (10, 6)) -> plt.Figure:
    """Create a traffic analysis plot with dual y-axes."""
    fig, ax1 = plt.subplots(figsize=figure_size)

    # Define colors
    color1, color2 = 'tab:blue', 'tab:orange'

    # Plot cumulative size on primary axis
    line1 = ax1.plot(
        processed_data.relative_times,
        processed_data.cumulative_size_mb,
        color=color1,
        linewidth=2,
        label='Cumulative Size (MB)'
    )

    ax1.set_xlabel('Time (s)')
    ax1.set_ylabel('Cumulative Size (MB)', color=color1)
    ax1.tick_params(axis='y', labelcolor=color1)
    ax1.grid(True, alpha=0.3)

    # Create secondary axis for packet count
    ax2 = ax1.twinx()
    line2 = ax2.plot(
        processed_data.relative_times,
        processed_data.cumulative_packet_count,
        color=color2,
        linestyle='--',
        linewidth=2,
        label='Cumulative Packet Count'
    )

    ax2.set_ylabel('Cumulative Packet Count', color=color2)
    ax2.tick_params(axis='y', labelcolor=color2)

    # Set comprehensive title with topology and router info
    title = create_comprehensive_title(topology_info, router_info)
    fig.suptitle(title, fontsize=16, fontweight='bold')

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


def display_analysis_summary(processed_data: ProcessedData, topology_info: TopologyInfo, router_info: RouterInfo) -> None:
    """Display analysis summary using rich table."""
    table = Table(title="📊 PCAP Analysis Summary", show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Value", style="green")

    # Add router information if available
    if router_info.router_id or router_info.coordinates:
        table.add_row("Router", router_info.display_name)

    table.add_row("Topology", topology_info.display_name)
    table.add_row("Total Packets", f"{processed_data.total_packets:,}")
    table.add_row("Duration", f"{processed_data.duration_seconds:.2f} seconds")
    table.add_row("Total Size", f"{processed_data.total_size_mb:.2f} MB")
    table.add_row("Avg Packet Rate", f"{processed_data.total_packets / max(processed_data.duration_seconds, 1):.1f} packets/sec")
    table.add_row("Avg Throughput", f"{processed_data.total_size_mb / max(processed_data.duration_seconds, 1):.2f} MB/sec")

    console.print(table)


def generate_default_output_name(pcap_path: Path, topology_info: TopologyInfo, router_info: RouterInfo) -> str:
    """Generate a descriptive default output filename based on topology and router."""
    base_name = pcap_path.stem
    name_parts = ["traffic_analysis", base_name]

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


def analyze_and_plot_traffic(pcap_path: Path, output_path: Path, use_auto_name: bool = False) -> None:
    """Analyze PCAP file and generate traffic plot with rich output."""
    try:
        # Extract topology and router information
        topology_info = extract_topology_from_filename(str(pcap_path))
        router_info = extract_router_from_path(str(pcap_path))

        # Generate auto filename if requested
        if use_auto_name:
            auto_name = generate_default_output_name(pcap_path, topology_info, router_info)
            output_path = output_path.parent / auto_name

        console.print(f"🔍 [bold blue]Analyzing:[/bold blue] {pcap_path.name}")
        console.print(f"🏗️  [bold yellow]Topology:[/bold yellow] {topology_info.display_name}")
        if router_info.router_id or router_info.coordinates:
            console.print(f"🖥️  [bold cyan]Router:[/bold cyan] {router_info.display_name}")

        # Functional pipeline: read -> process -> visualize
        packets = read_packets_from_pcap(pcap_path)
        processed_data = process_packet_data(packets)

        # Display summary
        display_analysis_summary(processed_data, topology_info, router_info)

        # Configure plot style and create visualization
        with console.status("[bold green]Generating plot..."):
            configure_plot_style()
            fig = create_traffic_plot(processed_data, topology_info, router_info)
            fig.savefig(output_path, bbox_inches='tight')
            plt.close(fig)

        console.print(f"✅ [bold green]Success![/bold green] Plot saved to: {output_path}")

    except FileNotFoundError:
        console.print(f"❌ [bold red]Error:[/bold red] File not found: {pcap_path}")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"❌ [bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"❌ [bold red]Unexpected error:[/bold red] {e}")
        raise typer.Exit(1)


def main(
    pcap_path: Path = typer.Argument(..., help="Path to the PCAP file to be analyzed", exists=True),
    output_path: Optional[Path] = typer.Argument(
        None,
        help="Output file path for the plot (supports .png, .pdf, .svg, etc.). If not provided, auto-generates based on topology."
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging")
) -> None:
    """
    🚀 PCAP Traffic Analysis Tool

    Analyzes PCAP files and generates publication-quality traffic trend plots
    with automatic topology detection and rich console output.

    If no output path is provided, automatically generates a descriptive filename
    based on the detected topology (e.g., traffic_analysis_myfile_grid5x5.png).
    """
    if verbose:
        logger.remove()
        logger.add(
            lambda msg: console.print(f"[dim]{msg}[/dim]", markup=True),
            level="DEBUG",
            format="{time:HH:mm:ss} | {level} | {message}"
        )

    # Handle auto-naming if no output path provided
    if output_path is None:
        topology_info = extract_topology_from_filename(str(pcap_path))
        router_info = extract_router_from_path(str(pcap_path))
        auto_name = generate_default_output_name(pcap_path, topology_info, router_info)
        output_path = Path(".") / auto_name
        use_auto_name = False  # Already generated
    else:
        use_auto_name = False

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Run analysis
    analyze_and_plot_traffic(pcap_path, output_path, use_auto_name)


if __name__ == "__main__":
    typer.run(main)