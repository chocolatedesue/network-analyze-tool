import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
import re
import sys
import os
import math
from typing import Dict, Tuple, Optional, List
from functools import partial

def extract_topology_type(file_path: str) -> str:
    """
    Extract topology type (grid or torus) from the file path using functional approach.
    
    Args:
        file_path (str): The path to the CSV file.
        
    Returns:
        str: The topology type ('Grid' or 'Torus'), defaults to 'Grid' if not found.
    """
    file_name = os.path.basename(file_path).lower()
    topology_map = {'torus': 'Torus', 'grid': 'Grid'}
    return next((topology for keyword, topology in topology_map.items() 
                if keyword in file_name), 'Grid')

def parse_raw_outage_data(raw_data_str: str) -> List[float]:
    """
    Parse comma-separated raw outage data string into sorted list of floats for accurate quantile calculation.
    
    Args:
        raw_data_str (str): Comma-separated string of outage values
        
    Returns:
        List[float]: Sorted list of outage values
    """
    try:
        if not raw_data_str or pd.isna(raw_data_str) or str(raw_data_str).strip() == "":
            return []
        
        # Parse and filter out zeros, then sort for consistent quantile calculation
        values = [float(x.strip()) for x in str(raw_data_str).split(',') if x.strip()]
        non_zero_values = [x for x in values if x > 0]
        return sorted(non_zero_values)  # Return sorted list for consistent index-based calculation
    except (ValueError, AttributeError):
        return []

def calculate_quantiles_by_index(values: List[float], quantiles: List[float] = [0.5, 0.9, 0.99]) -> Tuple[float, ...]:
    """
    Calculate quantiles based on index positions, rounding up to ensure actual measured values.
    
    Args:
        values (List[float]): List of values to calculate quantiles for
        quantiles (List[float]): List of quantile positions (0.0 to 1.0)
        
    Returns:
        Tuple[float, ...]: Calculated quantile values
    """
    if not values:
        return tuple(0.0 for _ in quantiles)
    
    # Sort values
    sorted_values = sorted(values)
    n = len(sorted_values)
    
    results = []
    for q in quantiles:
        if q == 0:
            # Minimum value
            results.append(sorted_values[0])
        elif q == 1:
            # Maximum value
            results.append(sorted_values[-1])
        else:
            # Calculate index position using (n-1) * q, then round up
            index_float = (n - 1) * q
            index = int(math.ceil(index_float))  # Round up to next index
            
            # Ensure index is within bounds
            index = min(index, n - 1)
            results.append(sorted_values[index])
    
    return tuple(results)

def calculate_outage_quantiles(raw_outage_data: List[float]) -> Tuple[float, float, float]:
    """
    Calculate outage quantiles (50%, 90%, 99%) from raw data using index-based method, 
    filtering out zero values for anomaly analysis.
    
    Args:
        raw_outage_data (List[float]): List of outage values
        
    Returns:
        Tuple[float, float, float]: P50, P90, P99 quantiles (only non-zero events)
    """
    if not raw_outage_data:
        return 0.0, 0.0, 0.0
    
    # Filter out zero values to focus on actual outage events
    non_zero_outages = [x for x in raw_outage_data if x > 0]
    
    if not non_zero_outages:
        return 0.0, 0.0, 0.0
    
    # Use index-based quantile calculation
    return calculate_quantiles_by_index(non_zero_outages, [0.5, 0.9, 0.99])

def calculate_avg_outage_for_events(raw_outage_data: List[float]) -> float:
    """
    Calculate average outage time for actual events only (excluding zeros).
    
    Args:
        raw_outage_data (List[float]): List of outage values (already sorted and filtered)
        
    Returns:
        float: Average outage time for non-zero events
    """
    # Since parse_raw_outage_data already filters and sorts, we can directly calculate
    return np.mean(raw_outage_data) if raw_outage_data else 0.0

def validate_quantile_calculation(raw_data: List[float], router_name: str = "") -> None:
    """
    Validate quantile calculations by showing the calculation process.
    
    Args:
        raw_data (List[float]): Sorted list of outage values
        router_name (str): Router name for debugging
    """
    if not raw_data:
        return
    
    n = len(raw_data)
    quantiles = [0.5, 0.9, 0.99]
    
    print(f"Debug: {router_name} - Data: {raw_data} (n={n})")
    for q in quantiles:
        index_float = (n - 1) * q
        index = int(math.ceil(index_float))
        index = min(index, n - 1)
        value = raw_data[index]
        print(f"  {q*100}%: index_float={index_float:.2f}, index={index}, value={value}")

def calculate_outage_event_count(raw_outage_data: List[float]) -> int:
    """
    Calculate the number of non-zero outage events for anomaly analysis.
    
    Args:
        raw_outage_data (List[float]): List of outage values (already filtered)
        
    Returns:
        int: Number of actual outage events (> 0)
    """
    # Since parse_raw_outage_data already filters zeros, we can directly count
    return len(raw_outage_data)

def extract_router_coordinates(router_name: str) -> Optional[Tuple[int, int]]:
    """
    Extract coordinates from router name using functional pattern matching.

    Args:
        router_name (str): Router name in format 'router_xx_yy'

    Returns:
        Optional[Tuple[int, int]]: Coordinates (row, col) or None if not found
    """
    pattern = re.compile(r'router_(\d+)_(\d+)')
    match = pattern.match(router_name)
    return (int(match.group(1)), int(match.group(2))) if match else None

def create_outage_metrics_grid(df: pd.DataFrame, grid_size: Tuple[int, int]) -> Dict[str, np.ndarray]:
    """
    Create grids for different outage metrics focusing on anomaly events analysis.

    Args:
        df (pd.DataFrame): Input dataframe with fping analysis results
        grid_size (Tuple[int, int]): Grid dimensions (rows, cols)

    Returns:
        Dict[str, np.ndarray]: Dictionary of metric name to 2D arrays
    """
    rows, cols = grid_size

    # Initialize empty grids for anomaly-focused metrics (including RTT)
    metrics = {
        'outage_event_count': np.full((rows, cols), np.nan),    # Number of outage events
        'outage_quantile_50': np.full((rows, cols), np.nan),    # P50 of actual events
        'outage_quantile_90': np.full((rows, cols), np.nan),    # P90 of actual events
        'avg_rtt_events': np.full((rows, cols), np.nan)        # Average RTT for comparison
    }

    # Process each router's data functionally
    def process_router_data(row_data):
        coords = extract_router_coordinates(row_data['router_name'])
        if not coords:
            return

        r, c = coords

        # Calculate metrics from raw data for better anomaly analysis using index-based method
        if 'raw_outage_data' in row_data and pd.notna(row_data['raw_outage_data']):
            raw_data = parse_raw_outage_data(str(row_data['raw_outage_data']))

            # Calculate anomaly-focused metrics using index-based quantile calculation
            event_count = calculate_outage_event_count(raw_data)
            p50, p90, p99 = calculate_outage_quantiles(raw_data)  # Now uses index-based method

            metrics['outage_event_count'][r, c] = event_count
            metrics['outage_quantile_50'][r, c] = p50
            metrics['outage_quantile_90'][r, c] = p90

            # Extract RTT data directly from CSV columns
            safe_get = lambda key, default=0.0: row_data.get(key, default) if pd.notna(row_data.get(key, default)) else 0.0
            avg_rtt = safe_get('avg_rtt_avg')
            metrics['avg_rtt_events'][r, c] = avg_rtt if avg_rtt > 0 else np.nan
        else:
            # Fallback to existing columns but still focus on events
            safe_get = lambda key, default=0.0: row_data.get(key, default) if pd.notna(row_data.get(key, default)) else 0.0
            safe_get_quantile = lambda key, default=0.0: max(0.0, safe_get(key, default))  # Ensure non-negative values

            # For event count, we can estimate from high outage records or use max outage
            max_outage = safe_get('max_outage_ms')
            event_count = 1 if max_outage > 0 else 0  # Simple estimation

            metrics['outage_event_count'][r, c] = event_count
            metrics['outage_quantile_50'][r, c] = safe_get_quantile('outage_quantile_50')
            metrics['outage_quantile_90'][r, c] = safe_get_quantile('outage_quantile_90')

            # Extract RTT data
            avg_rtt = safe_get('avg_rtt_avg')
            metrics['avg_rtt_events'][r, c] = avg_rtt if avg_rtt > 0 else np.nan

    # Apply processing to each row
    df.apply(process_router_data, axis=1)

    return metrics

def get_metric_config() -> Dict[str, Dict[str, str]]:
    """
    Get configuration for anomaly-focused outage metrics using functional configuration pattern.

    Returns:
        Dict[str, Dict[str, str]]: Metric configurations for anomaly analysis
    """
    return {
        'outage_event_count': {
            'title': 'Outage Event Count',
            'cmap': 'Reds',
            'fmt': '.0f',
            'cbar_label': 'Events'
        },
        'outage_quantile_50': {
            'title': 'Outage P50 (ms)',
            'cmap': 'YlOrRd',
            'fmt': '.1f',
            'cbar_label': 'ms'
        },
        'outage_quantile_90': {
            'title': 'Outage P90 (ms)',
            'cmap': 'Oranges',
            'fmt': '.1f',
            'cbar_label': 'ms'
        },
        'avg_rtt_events': {
            'title': 'Avg RTT (ms)',
            'cmap': 'Blues',
            'fmt': '.1f',
            'cbar_label': 'ms'
        }
    }

def create_heatmap(data: np.ndarray, config: Dict[str, str], ax, grid_size: Tuple[int, int]) -> None:
    """
    Create a single heatmap using functional styling approach.

    Args:
        data (np.ndarray): 2D array of metric data
        config (Dict[str, str]): Metric configuration
        ax: Matplotlib axis object
        grid_size (Tuple[int, int]): Grid dimensions
    """
    rows, cols = grid_size

    # Configure colormap functionally
    cmap = plt.get_cmap(config['cmap'])
    cmap.set_bad(color='lightgrey')

    # Create heatmap with functional configuration
    heatmap_params = {
        'annot': True,
        'fmt': config['fmt'],
        'cmap': cmap,
        'linewidths': 0.1,
        'linecolor': 'black',
        'cbar_kws': {'label': config['cbar_label'], 'shrink': 0.7},
        'ax': ax,
        'square': True,
        'annot_kws': {'size': 5, 'weight': 'bold'}  # Small font for 10x10
    }

    sns.heatmap(data, **heatmap_params)

    # Apply styling functionally
    styling_functions = [
        lambda: ax.set_title(config['title'], fontsize=12, pad=8, fontweight='bold'),
        lambda: ax.set_xlabel('Column', fontsize=10),
        lambda: ax.set_ylabel('Row', fontsize=10),
        lambda: ax.set_xticklabels(range(cols), fontsize=7),
        lambda: ax.set_yticklabels(range(rows), fontsize=7),
        lambda: ax.tick_params(axis='y', rotation=0)
    ]

    # Apply all styling functions
    list(map(lambda f: f(), styling_functions))

def plot_outage_analysis_heatmaps(file_path: str, output_path: Optional[str] = None,
                                 grid_size: Tuple[int, int] = (10, 10)) -> None:
    """
    Plot anomaly-focused outage analysis heatmaps using functional composition.

    Args:
        file_path (str): Path to the CSV file with fping analysis results
        output_path (Optional[str]): Output path for saving the plot
        grid_size (Tuple[int, int]): Grid dimensions
    """
    try:
        df = pd.read_csv(file_path)
    except FileNotFoundError:
        print(f"Error: File not found. Please check the path '{file_path}'")
        return

    # Create metrics grids using functional approach
    metrics = create_outage_metrics_grid(df, grid_size)

    # Extract topology type
    topology_type = extract_topology_type(file_path)

    # Setup plot with 2x2 layout for anomaly analysis
    fig, axes = plt.subplots(2, 2, figsize=(16, 14))
    fig.suptitle(f'Network Outage Anomaly Analysis - 10×10 {topology_type} Topology',
                fontsize=18, y=0.95, fontweight='bold')

    # Add subtitle
    fig.text(0.5, 0.88, 'Focusing on actual outage events (excluding zero values). Gray cells indicate no anomaly events.',
             ha='center', fontsize=11, style='italic', color='gray')

    # Get metric configurations
    metric_configs = get_metric_config()

    # Define subplot positions for 2x2 layout
    positions = [(0, 0), (0, 1), (1, 0), (1, 1)]

    # Create heatmaps functionally
    metric_items = list(metric_configs.items())
    for idx, ((metric, config), pos) in enumerate(zip(metric_items, positions)):
        if idx < len(positions):
            ax = axes[pos]
            create_heatmap(metrics[metric], config, ax, grid_size)

    # Adjust layout
    plt.subplots_adjust(top=0.79, bottom=0.08, hspace=0.3, wspace=0.15)

    # Save or display
    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"Outage anomaly analysis plot saved to: {output_path}")
        plt.close()
    else:
        plt.show()

def plot_single_outage_metric_heatmap(file_path: str, metric: str,
                                     output_path: Optional[str] = None,
                                     grid_size: Tuple[int, int] = (10, 10)) -> None:
    """
    Plot a single outage metric heatmap using functional approach.

    Args:
        file_path (str): Path to the CSV file
        metric (str): Metric to plot
        output_path (Optional[str]): Output path for saving
        grid_size (Tuple[int, int]): Grid dimensions
    """
    try:
        df = pd.read_csv(file_path)
    except FileNotFoundError:
        print(f"Error: File not found. Please check the path '{file_path}'")
        return

    # Validate metric
    valid_metrics = list(get_metric_config().keys())
    if metric not in valid_metrics:
        print(f"Error: Invalid metric '{metric}'. Valid metrics: {valid_metrics}")
        return

    # Create metrics grid and extract specific metric
    metrics = create_outage_metrics_grid(df, grid_size)
    heatmap_data = metrics[metric]

    # Get configuration and topology type
    config = get_metric_config()[metric]
    topology_type = extract_topology_type(file_path)

    # Create single plot
    plt.style.use('default')
    plt.figure(figsize=(12, 10))

    # Create heatmap
    cmap = plt.get_cmap(config['cmap'])
    cmap.set_bad(color='lightgrey')

    ax = sns.heatmap(
        heatmap_data,
        annot=True,
        fmt=config['fmt'],
        cmap=cmap,
        linewidths=0.1,
        linecolor='black',
        cbar_kws={'label': config['cbar_label'], 'shrink': 0.7},
        square=True,
        annot_kws={'size': 6, 'weight': 'bold'}  # Small font for 10x10
    )

    # Apply styling
    rows, cols = grid_size
    ax.set_title(f'Network Outage Analysis: {config["title"]} - 10×10 {topology_type} Topology',
                fontsize=16, pad=15, fontweight='bold')
    ax.set_xlabel('Column', fontsize=12)
    ax.set_ylabel('Row', fontsize=12)
    ax.set_xticklabels(range(cols), fontsize=8)
    ax.set_yticklabels(range(rows), fontsize=8)
    plt.yticks(rotation=0)

    # Add subtitle
    plt.figtext(0.5, 0.02,
               f'Each cell represents a router position in 10×10 {topology_type.lower()} topology. Gray cells indicate no data.',
               ha='center', fontsize=10, style='italic', color='gray')

    # Save or display
    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"Single outage metric plot saved to: {output_path}")
        plt.close()
    else:
        plt.show()

def main() -> None:
    """
    Main function with functional command line argument processing.
    """
    # Define default behavior functionally
    default_behavior = lambda: (
        print("Usage: python fping_outage_draw_10x10.py <csv_file_path> <output_image_path>"),
        print("Using default display mode...")
    )

    # Process command line arguments functionally
    if len(sys.argv) == 3:
        csv_file_path, output_image_path = sys.argv[1], sys.argv[2]

        # Ensure absolute path
        if not os.path.isabs(csv_file_path):
            csv_file_path = os.path.abspath(csv_file_path)

        # Create output directory if needed
        output_dir = os.path.dirname(output_image_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
    else:
        default_behavior()
        csv_file_path = 'test_fping_enhanced.csv'  # Default to enhanced fping results
        output_image_path = None

    # Validate file existence
    if not os.path.exists(csv_file_path):
        print(f"Error: CSV file not found at '{csv_file_path}'")
        sys.exit(1)

    # Plot outage analysis
    print(f"Plotting outage analysis from: {csv_file_path}")
    if output_image_path:
        print(f"Saving plot to: {output_image_path}")
    else:
        print("Displaying plot...")

    plot_outage_analysis_heatmaps(csv_file_path, output_image_path)

if __name__ == "__main__":
    main()
