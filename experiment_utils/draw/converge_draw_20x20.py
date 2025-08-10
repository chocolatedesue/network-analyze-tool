import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
import re
import sys
import os
from typing import Tuple, Optional, Dict, Any
from functools import partial

# Since English is supported by default fonts, the Chinese font lookup is no longer needed.
# plt.rcParams['axes.unicode_minus'] = False # This can be kept if you expect negative signs in your data.

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

def validate_csv_columns(df: pd.DataFrame) -> Tuple[bool, list]:
    """
    Validate required columns exist in the CSV file using functional validation.
    
    Args:
        df (pd.DataFrame): Input dataframe
        
    Returns:
        Tuple[bool, list]: (is_valid, missing_columns)
    """
    required_columns = ['total_trigger_events', 'convergence_p50_ms', 'convergence_p75_ms', 'convergence_p95_ms']
    missing_columns = [col for col in required_columns if col not in df.columns]
    return len(missing_columns) == 0, missing_columns

def extract_router_coordinates(log_file_path: str) -> Optional[Tuple[int, int]]:
    """
    Extract router coordinates from log file path using functional pattern matching.
    
    Args:
        log_file_path (str): Log file path containing router coordinates
        
    Returns:
        Optional[Tuple[int, int]]: Coordinates (row, col) or None if not found
    """
    pattern = re.compile(r'router_(\d+)_(\d+)')
    match = pattern.search(log_file_path)
    return (int(match.group(1)), int(match.group(2))) if match else None

def create_metrics_grid(df: pd.DataFrame, grid_size: Tuple[int, int]) -> Dict[str, np.ndarray]:
    """
    Create grids for convergence metrics using functional data processing.
    
    Args:
        df (pd.DataFrame): Input dataframe with convergence data
        grid_size (Tuple[int, int]): Grid dimensions (rows, cols)
        
    Returns:
        Dict[str, np.ndarray]: Dictionary of metric name to 2D arrays
    """
    rows, cols = grid_size
    
    # Initialize empty grids for each metric
    metrics = {
        'total_trigger_events': np.full((rows, cols), np.nan),
        'convergence_p50_ms': np.full((rows, cols), np.nan),
        'convergence_p75_ms': np.full((rows, cols), np.nan),
        'convergence_p95_ms': np.full((rows, cols), np.nan)
    }
    
    # Process each row functionally
    def process_row(row_data):
        coords = extract_router_coordinates(row_data['log_file_path'])
        if not coords:
            return
            
        r, c = coords
        
        # Populate metrics data for valid values
        for metric in metrics.keys():
            if metric in df.columns:
                value = row_data[metric]
                if value != -1:  # Only populate valid values
                    metrics[metric][r, c] = value
    
    # Apply processing to each row
    df.apply(process_row, axis=1)
    
    return metrics

def get_metric_configs() -> Dict[str, Dict[str, Any]]:
    """
    Get metric configurations using functional configuration pattern.
    
    Returns:
        Dict[str, Dict[str, Any]]: Metric configurations
    """
    return {
        'total_trigger_events': {
            'title': 'Trigger Events',
            'cmap': 'Blues',
            'fmt': '.0f',
            'cbar_label': 'Count'
        },
        'convergence_p50_ms': {
            'title': 'Conv. P50 (ms)',
            'cmap': 'Greens',
            'fmt': '.0f',
            'cbar_label': 'ms'
        },
        'convergence_p75_ms': {
            'title': 'Conv. P75 (ms)',
            'cmap': 'YlOrRd',
            'fmt': '.0f',
            'cbar_label': 'ms'
        },
        'convergence_p95_ms': {
            'title': 'Conv. P95 (ms)',
            'cmap': 'Reds',
            'fmt': '.0f',
            'cbar_label': 'ms'
        }
    }

def create_heatmap(data: np.ndarray, config: Dict[str, Any], ax, grid_size: Tuple[int, int]) -> None:
    """
    Create a single heatmap using functional styling approach optimized for 20x20.
    
    Args:
        data (np.ndarray): 2D array of metric data
        config (Dict[str, Any]): Metric configuration
        ax: Matplotlib axis object
        grid_size (Tuple[int, int]): Grid dimensions
    """
    rows, cols = grid_size
    
    # Configure colormap functionally
    cmap = plt.get_cmap(config['cmap'])
    cmap.set_bad(color='lightgrey')
    
    # Create heatmap with optimized parameters for 20x20
    heatmap_params = {
        'annot': True,
        'fmt': config['fmt'],
        'cmap': cmap,
        'linewidths': 0.05,  # Thinner lines for 20x20
        'linecolor': 'black',
        'cbar_kws': {'label': config['cbar_label'], 'shrink': 0.7},
        'ax': ax,
        'square': True,
        'annot_kws': {'size': 3, 'weight': 'bold'}  # Very small font for 20x20
    }
    
    sns.heatmap(data, **heatmap_params)
    
    # Apply styling functionally
    styling_functions = [
        lambda: ax.set_title(config['title'], fontsize=12, pad=8, fontweight='bold'),
        lambda: ax.set_xlabel('Column', fontsize=10),
        lambda: ax.set_ylabel('Row', fontsize=10),
        lambda: ax.set_xticklabels(range(cols), fontsize=5),  # Smaller font for 20x20
        lambda: ax.set_yticklabels(range(rows), fontsize=5),  # Smaller font for 20x20
        lambda: ax.tick_params(axis='y', rotation=0)
    ]
    
    # Apply all styling functions
    list(map(lambda f: f(), styling_functions))

def read_and_validate_csv(file_path: str) -> Optional[pd.DataFrame]:
    """
    Read and validate CSV file using functional error handling.
    
    Args:
        file_path (str): Path to CSV file
        
    Returns:
        Optional[pd.DataFrame]: DataFrame if successful, None otherwise
    """
    try:
        df = pd.read_csv(file_path)
        is_valid, missing_columns = validate_csv_columns(df)
        
        if not is_valid:
            print(f"Error: Missing required columns: {missing_columns}")
            print(f"Available columns: {df.columns.tolist()}")
            return None
            
        print("Using percentile convergence metrics (P50, P75, P95)")
        return df
        
    except FileNotFoundError:
        print(f"Error: File not found. Please check the path '{file_path}'")
        return None

def plot_convergence_metrics_heatmaps(file_path: str, output_path: Optional[str] = None, 
                                    grid_size: Tuple[int, int] = (20, 20)) -> None:
    """
    Plot convergence metrics heatmaps using functional composition optimized for 20x20.
    
    Args:
        file_path (str): The path to the CSV file.
        output_path (Optional[str]): The path to save the output image. If None, displays the plot.
        grid_size (Tuple[int, int]): The grid dimensions of the topology (rows, cols).
    """
    # Read and validate data
    df = read_and_validate_csv(file_path)
    if df is None:
        return
    
    # Create metrics grids
    metrics = create_metrics_grid(df, grid_size)
    
    # Extract topology type
    topology_type = extract_topology_type(file_path)
    
    # Setup plot with 2x2 layout
    fig, axes = plt.subplots(2, 2, figsize=(20, 18))  # Larger figure for 20x20
    fig.suptitle(f'Network Convergence Analysis - 20×20 {topology_type} Topology', 
                fontsize=20, y=0.95, fontweight='bold')
    
    # Add subtitle with explanation
    fig.text(0.5, 0.88, 'Each cell represents a router position (row, col). Gray cells indicate no data.',
             ha='center', fontsize=12, style='italic', color='gray')
    
    # Get metric configurations
    metric_configs = get_metric_configs()
    
    # Define subplot positions for 2x2 layout
    positions = [(0, 0), (0, 1), (1, 0), (1, 1)]
    
    # Create heatmaps functionally
    metric_items = list(metric_configs.items())
    for idx, ((metric, config), pos) in enumerate(zip(metric_items, positions)):
        ax = axes[pos]
        create_heatmap(metrics[metric], config, ax, grid_size)
    
    # Adjust layout to prevent overlap
    plt.subplots_adjust(top=0.79, bottom=0.08, hspace=0.3, wspace=0.15)
    
    # Save or display
    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"Plot saved to: {output_path}")
        plt.close()
    else:
        plt.show()

def plot_single_convergence_metric_heatmap(file_path: str, metric: str,
                                         output_path: Optional[str] = None,
                                         grid_size: Tuple[int, int] = (20, 20)) -> None:
    """
    Plot a single convergence metric heatmap using functional approach optimized for 20x20.

    Args:
        file_path (str): The path to the CSV file.
        metric (str): The metric to plot ('total_trigger_events', 'convergence_p50_ms',
                     'convergence_p75_ms', 'convergence_p95_ms')
        output_path (Optional[str]): The path to save the output image. If None, displays the plot.
        grid_size (Tuple[int, int]): The grid dimensions of the topology (rows, cols).
    """
    # Validate metric
    valid_metrics = list(get_metric_configs().keys())
    if metric not in valid_metrics:
        print(f"Error: Invalid metric '{metric}'. Valid metrics: {valid_metrics}")
        return

    # Read and validate data
    df = read_and_validate_csv(file_path)
    if df is None:
        return

    if metric not in df.columns:
        print(f"Error: Metric '{metric}' not found in CSV file. Available columns: {df.columns.tolist()}")
        return

    # Create metrics grid and extract specific metric
    metrics = create_metrics_grid(df, grid_size)
    heatmap_data = metrics[metric]

    # Get configuration and topology type
    config = get_metric_configs()[metric]
    topology_type = extract_topology_type(file_path)

    # Create single plot
    plt.style.use('default')
    plt.figure(figsize=(16, 14))  # Larger figure for 20x20

    # Get colormap and set color for NaN values
    cmap = plt.get_cmap(config['cmap'])
    cmap.set_bad(color='lightgrey')

    ax = sns.heatmap(
        heatmap_data,
        annot=True,
        fmt=config['fmt'],
        cmap=cmap,
        linewidths=0.05,  # Thinner lines for 20x20
        linecolor='black',
        cbar_kws={'label': config['cbar_label'], 'shrink': 0.7},
        square=True,
        annot_kws={'size': 4, 'weight': 'bold'}  # Small font for 20x20
    )

    # Set title and labels
    rows, cols = grid_size
    ax.set_title(f'Network Convergence Analysis: {config["title"]} - 20×20 {topology_type} Topology',
                fontsize=18, pad=15, fontweight='bold')
    ax.set_xlabel('Column', fontsize=14)
    ax.set_ylabel('Row', fontsize=14)

    # Add subtitle with explanation
    plt.figtext(0.5, 0.02, f'Each cell represents a router position in 20×20 {topology_type.lower()} topology. Gray cells indicate no data.',
                ha='center', fontsize=11, style='italic', color='gray')

    # Set axis ticks with smaller font for 20x20
    ax.set_xticklabels(range(cols), fontsize=6)
    ax.set_yticklabels(range(rows), fontsize=6)
    plt.yticks(rotation=0)

    # Save or display
    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"Plot saved to: {output_path}")
        plt.close()
    else:
        plt.show()

def main() -> None:
    """
    Main function with functional command line argument processing.
    """
    # Define default behavior functionally
    default_behavior = lambda: (
        print("Usage: python converge_draw_20x20.py <csv_file_path> <output_image_path>"),
        print("Using default paths and displaying plot...")
    )

    # Process command line arguments functionally
    if len(sys.argv) == 3:
        csv_file_path, output_image_path = sys.argv[1], sys.argv[2]

        # Ensure the CSV file path is absolute
        if not os.path.isabs(csv_file_path):
            csv_file_path = os.path.abspath(csv_file_path)

        # Ensure output directory exists
        output_dir = os.path.dirname(output_image_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
    else:
        default_behavior()
        csv_file_path = r'D:\work\ppt\domainDiv\exp\converge_result.csv'
        output_image_path = None  # Will display instead of save

    # Verify the CSV file exists
    if not os.path.exists(csv_file_path):
        print(f"Error: CSV file not found at '{csv_file_path}'")
        sys.exit(1)

    # Plot all metrics in a 2x2 grid
    if output_image_path:
        print(f"Plotting convergence metrics from: {csv_file_path}")
        print(f"Saving plot to: {output_image_path}")
    else:
        print(f"Displaying convergence metrics from: {csv_file_path}")

    plot_convergence_metrics_heatmaps(csv_file_path, output_image_path)

if __name__ == "__main__":
    main()
