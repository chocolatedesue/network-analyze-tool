import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
import re
import sys
import os

# Since English is supported by default fonts, the Chinese font lookup is no longer needed.
# plt.rcParams['axes.unicode_minus'] = False # This can be kept if you expect negative signs in your data.

def extract_topology_type(file_path: str) -> str:
    """
    Extract topology type (grid or torus) from the file path.
    
    Args:
        file_path (str): The path to the CSV file.
        
    Returns:
        str: The topology type ('Grid' or 'Torus'), defaults to 'Grid' if not found.
    """
    file_name = os.path.basename(file_path).lower()
    if 'torus' in file_name:
        return 'Torus'
    elif 'grid' in file_name:
        return 'Grid'
    else:
        return 'Grid'  # Default to Grid if neither is found

def plot_convergence_metrics_heatmaps(file_path: str, output_path: str = None, grid_size: tuple = (6, 6)):
    """
    Reads routing convergence data from a CSV file and plots multiple heatmaps 
    representing different convergence metrics.

    Args:
        file_path (str): The path to the CSV file.
        output_path (str): The path to save the output image. If None, displays the plot.
        grid_size (tuple): The grid dimensions of the topology (rows, cols).
    """
    try:
        # 1. Read the CSV file using pandas
        df = pd.read_csv(file_path)
    except FileNotFoundError:
        print(f"Error: File not found. Please check the path '{file_path}'")
        return

    # Check for required percentile columns
    required_columns = ['total_trigger_events', 'convergence_p50_ms', 'convergence_p75_ms', 'convergence_p95_ms']
    available_columns = df.columns.tolist()
    
    missing_columns = [col for col in required_columns if col not in available_columns]
    if missing_columns:
        print(f"Error: Missing required columns: {missing_columns}")
        print(f"Available columns: {available_columns}")
        return
    
    print("Using percentile convergence metrics (P50, P75, P95)")
    
    # Create empty grids for each metric
    rows, cols = grid_size
    metrics = {
        'total_trigger_events': np.full((rows, cols), np.nan),
        'convergence_p50_ms': np.full((rows, cols), np.nan),
        'convergence_p75_ms': np.full((rows, cols), np.nan),
        'convergence_p95_ms': np.full((rows, cols), np.nan)
    }
    
    # Regular expression to extract coordinates from log file path 'router_xx_yy'
    pattern = re.compile(r'router_(\d+)_(\d+)')

    # 3. Iterate over each row of the DataFrame to populate the heatmap data
    for index, row_data in df.iterrows():
        log_file_path = row_data['log_file_path']
        
        # Extract router coordinates from the log file path
        match = pattern.search(log_file_path)
        if match:
            # Parse coordinates from the log file path
            r, c = int(match.group(1)), int(match.group(2))
            
            # Populate metrics data
            for metric in metrics.keys():
                if metric in available_columns:
                    value = row_data[metric]
                    # Only populate if the value is valid (not -1)
                    if value != -1:
                        metrics[metric][r, c] = value

    # Extract topology type from file path
    topology_type = extract_topology_type(file_path)

    # 4. Create subplots for all metrics
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    fig.suptitle(f'Network Convergence Analysis - 6×6 {topology_type} Topology', fontsize=16, y=0.95, fontweight='bold')

    # Add subtitle with explanation
    fig.text(0.5, 0.88, 'Each cell represents a router position (row, col). Gray cells indicate no data.',
             ha='center', fontsize=10, style='italic', color='gray')

    # Define metric titles and colormaps for percentile metrics
    metric_configs = {
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

    # Plot positions for 2x2 subplot grid
    positions = [(0, 0), (0, 1), (1, 0), (1, 1)]
    
    for idx, (metric, config) in enumerate(metric_configs.items()):
        ax = axes[positions[idx]]
        
        # Get the colormap object and set color for NaN values
        cmap = plt.get_cmap(config['cmap'])
        cmap.set_bad(color='lightgrey')
        
        # Create heatmap
        sns.heatmap(
            metrics[metric],
            annot=True,
            fmt=config['fmt'],
            cmap=cmap,
            linewidths=.2,
            linecolor='black',
            cbar_kws={'label': config['cbar_label'], 'shrink': 0.7},
            ax=ax,
            square=True,
            annot_kws={'size': 7, 'weight': 'bold'}  # Slightly smaller font for 6x6
        )
        
        # Set title and labels
        ax.set_title(config['title'], fontsize=11, pad=8, fontweight='bold')
        ax.set_xlabel('Column', fontsize=9)
        ax.set_ylabel('Row', fontsize=9)

        # Set axis ticks
        ax.set_xticklabels(range(grid_size[1]), fontsize=8)
        ax.set_yticklabels(range(grid_size[0]), fontsize=8)
        ax.tick_params(axis='y', rotation=0)

    # Adjust layout to prevent overlap
    plt.subplots_adjust(top=0.79, bottom=0.08, hspace=0.3, wspace=0.15)

    # plt.tight_layout()
    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"Plot saved to: {output_path}")
        plt.close()
    else:
        plt.show()

def plot_single_convergence_metric_heatmap(file_path: str, metric: str, output_path: str = None, grid_size: tuple = (6, 6)):
    """
    Plots a single convergence metric heatmap.

    Args:
        file_path (str): The path to the CSV file.
        metric (str): The metric to plot ('total_trigger_events', 'convergence_p50_ms',
                     'convergence_p75_ms', 'convergence_p95_ms')
        output_path (str): The path to save the output image. If None, displays the plot.
        grid_size (tuple): The grid dimensions of the topology (rows, cols).
    """
    try:
        # Read the CSV file
        df = pd.read_csv(file_path)
    except FileNotFoundError:
        print(f"Error: File not found. Please check the path '{file_path}'")
        return

    # Validate metric
    valid_metrics = ['total_trigger_events', 'convergence_p50_ms', 'convergence_p75_ms', 'convergence_p95_ms']
    if metric not in valid_metrics:
        print(f"Error: Invalid metric '{metric}'. Valid metrics: {valid_metrics}")
        return

    # Check if the metric exists in the CSV file
    try:
        df = pd.read_csv(file_path)
        if metric not in df.columns:
            print(f"Error: Metric '{metric}' not found in CSV file. Available columns: {df.columns.tolist()}")
            return
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        return

    # Create empty grid
    rows, cols = grid_size
    heatmap_data = np.full((rows, cols), np.nan)

    # Regular expression to extract coordinates from log file path
    pattern = re.compile(r'router_(\d+)_(\d+)')

    # Populate the heatmap data
    for index, row_data in df.iterrows():
        log_file_path = row_data['log_file_path']
        value = row_data[metric]

        # Extract router coordinates from the log file path
        match = pattern.search(log_file_path)
        if match:
            r, c = int(match.group(1)), int(match.group(2))
            # Only populate if the value is valid (not -1)
            if value != -1:
                heatmap_data[r, c] = value

    # Plot configuration - support percentile metrics only
    configs = {
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

    config = configs[metric]

    # Extract topology type from file path
    topology_type = extract_topology_type(file_path)

    # Create the plot
    plt.style.use('default')
    plt.figure(figsize=(8, 7))

    # Get colormap and set color for NaN values
    cmap = plt.get_cmap(config['cmap'])
    cmap.set_bad(color='lightgrey')

    ax = sns.heatmap(
        heatmap_data,
        annot=True,
        fmt=config['fmt'],
        cmap=cmap,
        linewidths=.2,
        linecolor='black',
        cbar_kws={'label': config['cbar_label'], 'shrink': 0.7},
        square=True,
        annot_kws={'size': 9, 'weight': 'bold'}  # Adjusted for 6x6
    )

    # Set title and labels
    ax.set_title(f'Network Convergence Analysis: {config["title"]} - 6×6 {topology_type} Topology', fontsize=14, pad=15, fontweight='bold')
    ax.set_xlabel('Column', fontsize=11)
    ax.set_ylabel('Row', fontsize=11)

    # Add subtitle with explanation
    plt.figtext(0.5, 0.02, f'Each cell represents a router position in 6×6 {topology_type.lower()} topology. Gray cells indicate no data.',
                ha='center', fontsize=9, style='italic', color='gray')

    # Set axis ticks
    ax.set_xticklabels(range(cols), fontsize=9)
    ax.set_yticklabels(range(rows), fontsize=9)
    plt.yticks(rotation=0)

    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"Plot saved to: {output_path}")
        plt.close()
    else:
        plt.show()

# --- Usage Examples ---
if __name__ == "__main__":
    # Check if command line arguments are provided
    if len(sys.argv) == 3:
        # Use command line arguments: csv_file_path and output_image_path
        csv_file_path = sys.argv[1]
        output_image_path = sys.argv[2]

        # Ensure the CSV file path is absolute
        if not os.path.isabs(csv_file_path):
            csv_file_path = os.path.abspath(csv_file_path)

        # Ensure output directory exists
        output_dir = os.path.dirname(output_image_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
    else:
        # Default behavior - use hardcoded paths
        csv_file_path = r'D:\work\ppt\domainDiv\exp\converge_result.csv'
        output_image_path = None  # Will display instead of save

        print("Usage: python converge_draw_6x6.py <csv_file_path> <output_image_path>")
        print("Using default paths and displaying plot...")

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

    # Example: Plot individual metrics
    # print("Plotting total trigger events...")
    # plot_single_convergence_metric_heatmap(csv_file_path, 'total_trigger_events', output_image_path)

    # print("Plotting P50 convergence time...")
    # plot_single_convergence_metric_heatmap(csv_file_path, 'convergence_p50_ms', output_image_path)
