#!/usr/bin/env python3
"""
绘图工具模块
提供网络分析数据的可视化功能

支持的绘图类型:
- converge_draw: 收敛分析热力图
- fping_outage_draw: 中断分析热力图

使用方法:
    uv run experiment_utils/plotter.py converge_draw <csv_file> <output_file> --size 5x5
    uv run experiment_utils/plotter.py fping_outage_draw <csv_file> <output_file> --size 5x5
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from typing import Tuple, Optional, Dict, Any
import re

import typer
from rich.console import Console

from experiment_utils.utils import log_info, log_success, log_error, log_warning

console = Console()
app = typer.Typer(name="plotter", help="网络分析数据可视化工具")

# 设置matplotlib中文字体支持
plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'SimHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False


def parse_size(size_str: str) -> Tuple[int, int]:
    """解析尺寸字符串 (如 '5x5') 为元组"""
    match = re.match(r'(\d+)x(\d+)', size_str)
    if not match:
        raise ValueError(f"无效的尺寸格式: {size_str}，期望格式如 '5x5'")
    return int(match.group(1)), int(match.group(2))


def setup_plot_style():
    """设置绘图样式"""
    plt.style.use('default')
    sns.set_palette("husl")
    
    # 设置图形参数
    plt.rcParams.update({
        'figure.figsize': (12, 8),
        'figure.dpi': 100,
        'savefig.dpi': 300,
        'savefig.bbox': 'tight',
        'axes.titlesize': 14,
        'axes.labelsize': 12,
        'xtick.labelsize': 10,
        'ytick.labelsize': 10,
        'legend.fontsize': 10,
        'font.size': 10
    })


def create_router_position_map(width: int, height: int) -> Dict[str, Tuple[int, int]]:
    """创建路由器名称到位置的映射"""
    position_map = {}
    
    for row in range(height):
        for col in range(width):
            # 生成路由器名称 (格式: router_XX_YY)
            router_name = f"router_{row:02d}_{col:02d}"
            position_map[router_name] = (row, col)
    
    return position_map


def load_convergence_data(csv_file: Path) -> pd.DataFrame:
    """加载收敛数据CSV文件"""
    try:
        df = pd.read_csv(csv_file)
        log_info(f"加载了 {len(df)} 条收敛数据记录")
        return df
    except Exception as e:
        log_error(f"加载CSV文件失败: {e}")
        raise


def load_fping_data(csv_file: Path) -> pd.DataFrame:
    """加载fping数据CSV文件"""
    try:
        df = pd.read_csv(csv_file)
        log_info(f"加载了 {len(df)} 条fping数据记录")
        return df
    except Exception as e:
        log_error(f"加载CSV文件失败: {e}")
        raise


@app.command()
def converge_draw(
    csv_file: str = typer.Argument(..., help="输入CSV文件路径"),
    output_file: str = typer.Argument(..., help="输出图片文件路径"),
    size: str = typer.Option("5x5", "--size", help="网格尺寸 (如 5x5)"),
    title: Optional[str] = typer.Option(None, "--title", help="图表标题"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="详细输出")
) -> None:
    """生成收敛分析热力图"""
    csv_path = Path(csv_file)
    output_path = Path(output_file)
    
    if not csv_path.exists():
        log_error(f"CSV文件不存在: {csv_path}")
        raise typer.Exit(1)
    
    # 解析网格尺寸
    try:
        width, height = parse_size(size)
    except ValueError as e:
        log_error(str(e))
        raise typer.Exit(1)
    
    # 设置绘图样式
    setup_plot_style()
    
    # 加载数据
    df = load_convergence_data(csv_path)
    
    if df.empty:
        log_warning("CSV文件为空，无法生成图表")
        return
    
    # 确保输出目录存在
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 创建路由器位置映射
    position_map = create_router_position_map(width, height)
    
    # 创建热力图数据矩阵
    heatmap_data = np.zeros((height, width))
    
    # 计算每个路由器的平均收敛时间
    if 'convergence_time_ms' in df.columns and 'router_name' in df.columns:
        convergence_stats = df.groupby('router_name')['convergence_time_ms'].agg(['mean', 'count']).reset_index()
        
        for _, row in convergence_stats.iterrows():
            router_name = row['router_name']
            avg_convergence = row['mean']
            
            if router_name in position_map and not pd.isna(avg_convergence):
                pos_row, pos_col = position_map[router_name]
                heatmap_data[pos_row, pos_col] = avg_convergence
    
    # 创建图表
    fig, ax = plt.subplots(figsize=(10, 8))
    
    # 生成热力图
    im = ax.imshow(heatmap_data, cmap='YlOrRd', aspect='equal')
    
    # 设置标题
    if title:
        ax.set_title(title, fontsize=16, fontweight='bold')
    else:
        ax.set_title(f'网络收敛时间热力图 ({size})', fontsize=16, fontweight='bold')
    
    # 设置坐标轴
    ax.set_xlabel('列', fontsize=12)
    ax.set_ylabel('行', fontsize=12)
    
    # 添加颜色条
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label('平均收敛时间 (ms)', fontsize=12)
    
    # 在每个格子中显示数值
    for i in range(height):
        for j in range(width):
            if heatmap_data[i, j] > 0:
                text = ax.text(j, i, f'{heatmap_data[i, j]:.1f}',
                             ha="center", va="center", color="black", fontsize=8)
    
    # 保存图表
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    log_success(f"收敛分析热力图已保存到: {output_path}")


@app.command()
def fping_outage_draw(
    csv_file: str = typer.Argument(..., help="输入CSV文件路径"),
    output_file: str = typer.Argument(..., help="输出图片文件路径"),
    size: str = typer.Option("5x5", "--size", help="网格尺寸 (如 5x5)"),
    title: Optional[str] = typer.Option(None, "--title", help="图表标题"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="详细输出")
) -> None:
    """生成中断分析热力图"""
    csv_path = Path(csv_file)
    output_path = Path(output_file)
    
    if not csv_path.exists():
        log_error(f"CSV文件不存在: {csv_path}")
        raise typer.Exit(1)
    
    # 解析网格尺寸
    try:
        width, height = parse_size(size)
    except ValueError as e:
        log_error(str(e))
        raise typer.Exit(1)
    
    # 设置绘图样式
    setup_plot_style()
    
    # 加载数据
    df = load_fping_data(csv_path)
    
    if df.empty:
        log_warning("CSV文件为空，无法生成图表")
        return
    
    # 确保输出目录存在
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 分析中断数据
    if 'status' in df.columns and 'timestamp' in df.columns:
        # 计算中断率
        timeout_count = len(df[df['status'] == 'timeout'])
        total_count = len(df)
        outage_rate = (timeout_count / total_count * 100) if total_count > 0 else 0
        
        # 创建时间序列图
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
        
        # 转换时间戳
        df['timestamp'] = pd.to_numeric(df['timestamp'])
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
        
        # 按时间窗口统计中断
        df_sorted = df.sort_values('datetime')
        window_size = '10S'  # 10秒窗口
        
        outage_stats = df_sorted.set_index('datetime').groupby(pd.Grouper(freq=window_size)).agg({
            'status': lambda x: (x == 'timeout').sum(),
            'rtt_ms': 'mean'
        }).reset_index()
        
        # 绘制中断次数时间序列
        ax1.plot(outage_stats['datetime'], outage_stats['status'], 'r-', linewidth=2)
        ax1.set_title(f'网络中断时间序列 (总中断率: {outage_rate:.2f}%)', fontsize=14)
        ax1.set_ylabel('中断次数', fontsize=12)
        ax1.grid(True, alpha=0.3)
        
        # 绘制RTT时间序列
        valid_rtt = outage_stats.dropna(subset=['rtt_ms'])
        if not valid_rtt.empty:
            ax2.plot(valid_rtt['datetime'], valid_rtt['rtt_ms'], 'b-', linewidth=2)
            ax2.set_title('网络延迟时间序列', fontsize=14)
            ax2.set_ylabel('RTT (ms)', fontsize=12)
            ax2.set_xlabel('时间', fontsize=12)
            ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
    else:
        # 简单的统计图表
        fig, ax = plt.subplots(figsize=(10, 6))
        
        if 'status' in df.columns:
            status_counts = df['status'].value_counts()
            ax.pie(status_counts.values, labels=status_counts.index, autopct='%1.1f%%')
            ax.set_title('网络状态分布', fontsize=16)
        else:
            ax.text(0.5, 0.5, '数据格式不支持', ha='center', va='center', fontsize=16)
            ax.set_title('无法生成图表', fontsize=16)
    
    # 保存图表
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    log_success(f"中断分析图表已保存到: {output_path}")


# 移除未实现的ping分析绘图功能


if __name__ == "__main__":
    app()
