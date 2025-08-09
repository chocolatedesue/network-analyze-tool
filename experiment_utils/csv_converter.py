#!/usr/bin/env python3
"""
CSV转换工具模块
提供日志文件到CSV格式的转换功能

支持的转换类型:
- log2csv: 收敛日志转CSV
- fping2csv: fping日志转CSV

使用方法:
    uv run experiment_utils/csv_converter.py log2csv <input_dir> <output_file>
    uv run experiment_utils/csv_converter.py fping2csv <input_dir> <output_file>
"""

import json
import re
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Iterator
from dataclasses import dataclass
from datetime import datetime
import csv

import typer
from rich.console import Console
from rich.progress import track

from experiment_utils.utils import log_info, log_success, log_error, log_warning

console = Console()
app = typer.Typer(name="csv_converter", help="日志文件CSV转换工具")


@dataclass
class LogEntry:
    """日志条目数据类"""
    timestamp: str
    router_name: str
    event_type: str
    session_id: Optional[int] = None
    convergence_time: Optional[float] = None
    additional_data: Optional[Dict[str, Any]] = None


@dataclass
class FpingEntry:
    """Fping日志条目数据类"""
    timestamp: str
    target: str
    status: str
    rtt: Optional[float] = None
    loss_rate: Optional[float] = None


def parse_convergence_log_file(file_path: Path) -> Iterator[LogEntry]:
    """解析收敛日志文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                
                try:
                    # 尝试解析JSON格式
                    data = json.loads(line)
                    
                    # 提取基本信息
                    timestamp = data.get('timestamp', data.get('utc_time', ''))
                    router_name = data.get('router_name', '')
                    event_type = data.get('event_type', '')
                    session_id = data.get('session_id')
                    convergence_time = data.get('convergence_time_ms')
                    
                    yield LogEntry(
                        timestamp=timestamp,
                        router_name=router_name,
                        event_type=event_type,
                        session_id=session_id,
                        convergence_time=convergence_time,
                        additional_data=data
                    )
                    
                except json.JSONDecodeError:
                    log_warning(f"跳过无效JSON行 {file_path}:{line_num}: {line[:50]}...")
                    continue
                    
    except Exception as e:
        log_error(f"读取文件失败 {file_path}: {e}")


def parse_fping_log_file(file_path: Path) -> Iterator[FpingEntry]:
    """解析fping日志文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                
                # 解析fping输出格式
                # 示例: [1691234567.123] 2001:db8:1000:0000:0003:0002::1 : [0], 84 bytes, 1.23 ms (1.23 avg, 0% loss)
                timestamp_match = re.match(r'\[(\d+\.\d+)\]', line)
                if not timestamp_match:
                    continue
                
                timestamp = timestamp_match.group(1)
                
                # 提取目标地址
                target_match = re.search(r'\] ([^\s:]+) :', line)
                if not target_match:
                    continue
                
                target = target_match.group(1)
                
                # 检查是否为超时或错误
                if 'timeout' in line.lower() or 'unreachable' in line.lower():
                    yield FpingEntry(
                        timestamp=timestamp,
                        target=target,
                        status='timeout',
                        rtt=None,
                        loss_rate=100.0
                    )
                else:
                    # 提取RTT和丢包率
                    rtt_match = re.search(r'(\d+\.?\d*) ms', line)
                    loss_match = re.search(r'(\d+\.?\d*)% loss', line)
                    
                    rtt = float(rtt_match.group(1)) if rtt_match else None
                    loss_rate = float(loss_match.group(1)) if loss_match else 0.0
                    
                    yield FpingEntry(
                        timestamp=timestamp,
                        target=target,
                        status='success',
                        rtt=rtt,
                        loss_rate=loss_rate
                    )
                    
    except Exception as e:
        log_error(f"读取文件失败 {file_path}: {e}")


def find_log_files(input_dir: Path, pattern: str) -> List[Path]:
    """查找匹配模式的日志文件"""
    log_files = []
    
    if pattern == "route.json":
        # 查找route.json文件
        log_files.extend(input_dir.rglob("route.json"))
    elif pattern == "fping.log":
        # 查找fping.log文件
        log_files.extend(input_dir.rglob("fping.log"))
    elif pattern == "ping.log":
        # 查找ping.log文件
        log_files.extend(input_dir.rglob("ping.log"))
    else:
        # 通用模式匹配
        log_files.extend(input_dir.rglob(pattern))
    
    return sorted(log_files)


@app.command()
def log2csv(
    input_dir: str = typer.Argument(..., help="输入目录路径"),
    output_file: str = typer.Argument(..., help="输出CSV文件路径"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="详细输出")
) -> None:
    """将收敛日志转换为CSV格式"""
    input_path = Path(input_dir)
    output_path = Path(output_file)
    
    if not input_path.exists():
        log_error(f"输入目录不存在: {input_path}")
        raise typer.Exit(1)
    
    # 查找route.json文件
    log_files = find_log_files(input_path, "route.json")
    
    if not log_files:
        log_warning(f"在 {input_path} 中未找到route.json文件")
        return
    
    log_info(f"找到 {len(log_files)} 个日志文件")
    
    # 确保输出目录存在
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 收集所有日志条目
    all_entries = []
    
    for log_file in track(log_files, description="处理日志文件..."):
        if verbose:
            log_info(f"处理文件: {log_file}")
        
        entries = list(parse_convergence_log_file(log_file))
        all_entries.extend(entries)
    
    if not all_entries:
        log_warning("未找到有效的日志条目")
        return
    
    # 写入CSV文件
    with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['timestamp', 'router_name', 'event_type', 'session_id', 'convergence_time_ms']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        for entry in all_entries:
            writer.writerow({
                'timestamp': entry.timestamp,
                'router_name': entry.router_name,
                'event_type': entry.event_type,
                'session_id': entry.session_id,
                'convergence_time_ms': entry.convergence_time
            })
    
    log_success(f"成功转换 {len(all_entries)} 条记录到 {output_path}")


@app.command()
def fping2csv(
    input_dir: str = typer.Argument(..., help="输入目录路径"),
    output_file: str = typer.Argument(..., help="输出CSV文件路径"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="详细输出")
) -> None:
    """将fping日志转换为CSV格式"""
    input_path = Path(input_dir)
    output_path = Path(output_file)
    
    if not input_path.exists():
        log_error(f"输入目录不存在: {input_path}")
        raise typer.Exit(1)
    
    # 查找fping.log文件
    log_files = find_log_files(input_path, "fping.log")
    
    if not log_files:
        log_warning(f"在 {input_path} 中未找到fping.log文件")
        return
    
    log_info(f"找到 {len(log_files)} 个日志文件")
    
    # 确保输出目录存在
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 收集所有日志条目
    all_entries = []
    
    for log_file in track(log_files, description="处理fping日志..."):
        if verbose:
            log_info(f"处理文件: {log_file}")
        
        entries = list(parse_fping_log_file(log_file))
        all_entries.extend(entries)
    
    if not all_entries:
        log_warning("未找到有效的fping条目")
        return
    
    # 写入CSV文件
    with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['timestamp', 'target', 'status', 'rtt_ms', 'loss_rate']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        for entry in all_entries:
            writer.writerow({
                'timestamp': entry.timestamp,
                'target': entry.target,
                'status': entry.status,
                'rtt_ms': entry.rtt,
                'loss_rate': entry.loss_rate
            })
    
    log_success(f"成功转换 {len(all_entries)} 条记录到 {output_path}")


# 移除未实现的ping转换功能


if __name__ == "__main__":
    app()
