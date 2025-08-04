import argparse
import matplotlib.pyplot as plt
from scapy.all import PcapReader
import numpy as np

def analyze_and_plot_traffic(pcap_path, output_path):
    """
    Analyzes a PCAP file and saves a single, academic-style plot showing
    cumulative traffic size and packet count over time.

    Args:
        pcap_path (str): The path to the PCAP file to be analyzed.
        output_path (str): The path where the output plot image will be saved.
    """
    timestamps = []
    packet_sizes = []

    print(f"[INFO] Starting analysis for file: {pcap_path}...")
    try:
        with PcapReader(pcap_path) as pcap_reader:
            for packet in pcap_reader:
                timestamps.append(float(packet.time))
                packet_sizes.append(len(packet))
    except FileNotFoundError:
        print(f"[ERROR] File not found: '{pcap_path}'")
        return
    except Exception as e:
        print(f"[ERROR] Failed to read or parse PCAP file: {e}")
        return

    if not timestamps:
        print("[ERROR] No packets found in the PCAP file.")
        return

    print(f"[INFO] Analysis complete. Processed {len(timestamps)} packets.")

    # --- Data Processing ---
    start_time = timestamps[0]
    relative_times = [t - start_time for t in timestamps]
    cumulative_packet_count = np.arange(1, len(timestamps) + 1)
    cumulative_size_mb = np.cumsum(packet_sizes) / (1024 * 1024)

    # --- Publication-Quality Visualization ---
    print(f"[INFO] Generating plot and saving to {output_path}...")

    plt.rcParams.update({
        'font.family': 'serif',
        'font.size': 12,
        'axes.labelsize': 14,
        'xtick.labelsize': 12,
        'ytick.labelsize': 12,
        'legend.fontsize': 12,
    })

    fig, ax1 = plt.subplots(figsize=(8, 5))
    color1 = 'tab:blue'
    color2 = 'tab:orange'

    # Plot Cumulative Size (Primary Axis)
    line1 = ax1.plot(relative_times, cumulative_size_mb, color=color1, linestyle='-', label='Cumulative Size (MB)')
    ax1.set_xlabel('Time (s)')
    ax1.set_ylabel('Cumulative Size (MB)', color=color1)
    ax1.tick_params(axis='y', labelcolor=color1)
    ax1.grid(True, which='both', linestyle='--', linewidth=0.5)

    # Create and Plot Cumulative Count (Secondary Axis)
    ax2 = ax1.twinx()
    line2 = ax2.plot(relative_times, cumulative_packet_count, color=color2, linestyle='--', label='Cumulative Packet Count')
    ax2.set_ylabel('Cumulative Packet Count', color=color2)
    ax2.tick_params(axis='y', labelcolor=color2)

    # Aesthetics and Legend
    ax1.spines['top'].set_visible(False)
    ax2.spines['top'].set_visible(False)
    lines = line1 + line2
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc='upper left')

    fig.tight_layout()

    # --- Save the Figure ---
    try:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"[SUCCESS] Plot saved successfully to {output_path}")
    except Exception as e:
        print(f"[ERROR] Failed to save the plot: {e}")
    
    # Close the plot to free up memory
    plt.close(fig)


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