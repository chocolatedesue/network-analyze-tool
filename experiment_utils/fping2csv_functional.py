#!/usr/bin/env python3
"""
简化版 fping 日志汇总到 CSV（仅标准库）。

用法:
  python3 fping2csv_functional.py <基础目录路径> <输出CSV文件>

输出列（满足绘图脚本 experiment_utils/draw/fping_outage_draw_{N}x{N}.py 的要求）:
  - router_name
  - file_path
  - total_records
  - high_loss_records
  - high_loss_rate_percent
  - min_rtt_avg
  - max_rtt_avg
  - avg_rtt_avg
  - min_outage_ms
  - max_outage_ms
  - avg_outage_ms
  - raw_outage_data（逗号分隔的非零 outage 列表）
"""

import re
import math
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Union
import csv

# 确保作为独立脚本运行时可导入 experiment_utils（需在导入前注入）
import os
import sys
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(THIS_DIR, os.pardir))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from experiment_utils.utils import log_info, log_success, log_warning

# ============================================================================
# 配置和数据模型
# ============================================================================

# 常量定义
LOSS_THRESHOLD = 1.0
QUANTILES = [0, 0.5, 0.99]
FPING_PATTERNS = {
    'timestamp': re.compile(r'\[(\d{2}:\d{2}:\d{2})\]'),
    'target_ip': re.compile(r'^([^\s:]+)\s*:'),
    'transmitted': re.compile(r'xmt/rcv/%loss = (\d+)/'),
    'received': re.compile(r'xmt/rcv/%loss = \d+/(\d+)/'),
    'loss_percent': re.compile(r'xmt/rcv/%loss = \d+/\d+/(\d+)%'),
    'outage': re.compile(r'outage\(ms\) = (\d+)'),
    'rtt_min': re.compile(r'min/avg/max = ([\d.]+)/'),
    'rtt_avg': re.compile(r'min/avg/max = [\d.]+/([\d.]+)/'),
    'rtt_max': re.compile(r'min/avg/max = [\d.]+/[\d.]+/([\d.]+)')
}

class FpingRecord:
    def __init__(self, timestamp: str, target_ip: str, transmitted: int, received: int,
                 loss_percent: float, outage_ms: Optional[int] = None,
                 rtt_min: Optional[float] = None, rtt_avg: Optional[float] = None,
                 rtt_max: Optional[float] = None) -> None:
        self.timestamp = timestamp
        self.target_ip = target_ip
        self.transmitted = transmitted
        self.received = received
        self.loss_percent = loss_percent
        self.outage_ms = outage_ms
        self.rtt_min = rtt_min
        self.rtt_avg = rtt_avg
        self.rtt_max = rtt_max

# ============================================================================
# 核心解析函数
# ============================================================================

def safe_extract(pattern: re.Pattern, text: str, converter=str) -> Optional[Union[str, int, float]]:
    """安全提取并转换匹配的内容"""
    match = pattern.search(text)
    return converter(match.group(1)) if match else None

def extract_fping_details(log_line: str, current_timestamp: str = None) -> Dict:
    """从fping日志行中提取详细信息，使用函数式方法"""
    # 如果这行是时间戳行，返回时间戳信息
    timestamp_match = FPING_PATTERNS['timestamp'].search(log_line)
    if timestamp_match:
        return {'timestamp': timestamp_match.group(1), 'is_timestamp_line': True}

    # 如果这行包含fping数据，提取所有信息
    if ':' in log_line and 'xmt/rcv/%loss' in log_line:
        extractors = {
            'target_ip': lambda line: safe_extract(FPING_PATTERNS['target_ip'], line),
            'transmitted': lambda line: safe_extract(FPING_PATTERNS['transmitted'], line, int),
            'received': lambda line: safe_extract(FPING_PATTERNS['received'], line, int),
            'loss_percent': lambda line: safe_extract(FPING_PATTERNS['loss_percent'], line, float),
            'outage_ms': lambda line: safe_extract(FPING_PATTERNS['outage'], line, int),
            'rtt_min': lambda line: safe_extract(FPING_PATTERNS['rtt_min'], line, float),
            'rtt_avg': lambda line: safe_extract(FPING_PATTERNS['rtt_avg'], line, float),
            'rtt_max': lambda line: safe_extract(FPING_PATTERNS['rtt_max'], line, float)
        }

        # 提取基本信息
        details = {key: extractor(log_line) for key, extractor in extractors.items()}

        # 添加当前时间戳
        if current_timestamp:
            details['timestamp'] = current_timestamp

        # 过滤掉None值
        return {k: v for k, v in details.items() if v is not None}

    return {}

def create_fping_record(details: Dict) -> Optional[FpingRecord]:
    """创建FpingRecord实例（标准库版本）。"""
    try:
        return FpingRecord(
            timestamp=details.get('timestamp', '00:00:00'),
            target_ip=details.get('target_ip', ''),
            transmitted=details.get('transmitted', 0),
            received=details.get('received', 0),
            loss_percent=details.get('loss_percent', 0.0),
            outage_ms=details.get('outage_ms'),
            rtt_min=details.get('rtt_min'),
            rtt_avg=details.get('rtt_avg'),
            rtt_max=details.get('rtt_max'),
        )
    except Exception:
        return None

def extract_router_name(file_path: str) -> str:
    """从文件路径中提取路由器名称"""
    return next((part for part in Path(file_path).parts if part.startswith("router_")), "")

def read_lines_safely(file_path: str) -> Tuple[List[str], Optional[str]]:
    """安全读取文件行，返回(行列表, 错误信息)"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.readlines(), None
    except FileNotFoundError:
        return [], f"文件 '{file_path}' 未找到"
    except Exception as e:
        return [], f"读取文件时发生错误: {e}"

# ============================================================================
# 数据处理和分析函数
# ============================================================================

def parse_raw_data_string(raw_data_string: str) -> List[float]:
    """从逗号分隔的原始数据字符串中解析出数值列表"""
    if not raw_data_string or raw_data_string.strip() == "":
        return []

    try:
        # 分割字符串并转换为浮点数
        values = [float(x.strip()) for x in raw_data_string.split(',') if x.strip()]
        return values
    except ValueError:
        return []

def calculate_quantiles_from_raw_data(raw_data_string: str, quantiles: List[float] = [0, 0.5, 0.99]) -> Dict[str, float]:
    """从原始数据字符串计算分位数，使用pandas或numpy优化"""
    values = parse_raw_data_string(raw_data_string)

    if not values:
        return {}

    # 仅使用标准库计算分位数
    sorted_values = sorted(values)
    n = len(sorted_values)

    result = {}
    quantile_names = {
        0: "0% 分位点",
        0.5: "50% 分位点 (中位数)",
        0.99: "99% 分位点"
    }

    for q in quantiles:
        if q == 0:
            result[quantile_names[q]] = sorted_values[0]
        elif q == 1:
            result[quantile_names[q]] = sorted_values[-1]
        else:
            index_float = (n - 1) * q
            index = int(math.ceil(index_float))
            index = min(index, n - 1)
            result[quantile_names[q]] = sorted_values[index]

    return result

def calculate_quantiles_by_index(values: List[float], quantiles: List[float] = [0, 0.5, 0.99]) -> Dict[str, float]:
    """基于下标位置计算分位数，向后近似确保返回实际测量值"""
    if not values:
        return {}

    # 排序数据
    sorted_values = sorted(values)
    n = len(sorted_values)

    result = {}
    quantile_names = {
        0: "0% 分位点",
        0.5: "50% 分位点 (中位数)",
        0.99: "99% 分位点"
    }

    for q in quantiles:
        if q == 0:
            # 最小值
            result[quantile_names[q]] = sorted_values[0]
        elif q == 1:
            # 最大值
            result[quantile_names[q]] = sorted_values[-1]
        else:
            # 计算分位点对应的下标位置
            # 使用 (n-1) * q 的公式，然后向上取整确保向后近似
            index_float = (n - 1) * q
            index = int(math.ceil(index_float))  # 向上取整，向后近似

            # 确保下标在有效范围内
            index = min(index, n - 1)
            result[quantile_names[q]] = sorted_values[index]

    return result

def calculate_quantiles(values: List[float]) -> Dict[str, float]:
    """计算分位数 - 使用基于下标的方法"""
    return calculate_quantiles_by_index(values)

def parse_fping_log_lines(lines: List[str], show_progress: bool = True) -> List[Dict]:
    """解析fping日志行，处理时间戳和数据行的关系"""
    parsed_entries = []
    current_timestamp = None

    # 静默解析，不显示进度条
    for line in lines:
        line = line.strip()
        if not line:
            continue

        details = extract_fping_details(line, current_timestamp)

        if details.get('is_timestamp_line'):
            current_timestamp = details['timestamp']
        elif details and 'target_ip' in details:
            parsed_entries.append(details)

    return parsed_entries

def analyze_high_loss_quantiles_from_raw_data(raw_loss_data: str, raw_outage_data: str) -> Tuple[Dict[str, float], Dict[str, float]]:
    """从原始数据字符串分析高丢包率和中断时间的分位数"""
    # 从原始数据计算分位数
    loss_quantiles = calculate_quantiles_from_raw_data(raw_loss_data)
    outage_quantiles = calculate_quantiles_from_raw_data(raw_outage_data)

    return loss_quantiles, outage_quantiles

def analyze_high_loss_quantiles(file_path: str) -> Tuple[List[Dict], Dict[str, float], Dict[str, float], Optional[str]]:
    """分析高丢包率记录并计算分位数，同时计算outage时间分位数"""
    lines, error = read_lines_safely(file_path)
    if error:
        return [], {}, {}, error

    # 解析所有fping记录
    all_entries = parse_fping_log_lines(lines[2:-3])

    # 过滤高丢包率记录
    high_loss_entries = [entry for entry in all_entries
                        if entry.get('loss_percent', 0) > LOSS_THRESHOLD]

    # 提取非零丢包率和中断时间值，构建原始数据字符串
    non_zero_loss_values = [entry['loss_percent'] for entry in all_entries
                           if 'loss_percent' in entry and entry['loss_percent'] > 0]
    non_zero_outage_values = [entry['outage_ms'] for entry in all_entries
                             if 'outage_ms' in entry and entry['outage_ms'] > 0]

    # 转换为原始数据字符串格式
    raw_loss_data = ','.join(map(str, non_zero_loss_values))
    raw_outage_data = ','.join(map(str, non_zero_outage_values))

    # 使用原始数据字符串计算分位数
    loss_quantiles, outage_quantiles = analyze_high_loss_quantiles_from_raw_data(raw_loss_data, raw_outage_data)

    return high_loss_entries, loss_quantiles, outage_quantiles, None

def analyze_file_statistics(file_path: str, show_progress: bool = True) -> Dict:
    """分析单个fping日志文件的统计信息，使用pandas优化"""
    lines, error = read_lines_safely(file_path)
    if error:
        return {}

    # 解析所有fping记录
    all_entries = parse_fping_log_lines(lines[2:-3], show_progress)

    if not all_entries:
        return {}

    # 仅使用标准库
    loss_values = [e['loss_percent'] for e in all_entries if 'loss_percent' in e]
    rtt_values = [e['rtt_avg'] for e in all_entries if 'rtt_avg' in e]
    transmitted_values = [e['transmitted'] for e in all_entries if 'transmitted' in e]
    received_values = [e['received'] for e in all_entries if 'received' in e]
    outage_values = [e['outage_ms'] for e in all_entries if 'outage_ms' in e]
    high_loss_count = len([e for e in all_entries if e.get('loss_percent', 0) > LOSS_THRESHOLD])

    timestamps = [e['timestamp'] for e in all_entries if 'timestamp' in e]
    target_ips = list(set([e['target_ip'] for e in all_entries if 'target_ip' in e]))

    return {
        'file_path': file_path,
        'router_name': extract_router_name(file_path),
        'target_ips': target_ips,
        'total_records': len(all_entries),
        'high_loss_records': high_loss_count,
        'high_loss_rate': (high_loss_count / len(all_entries) * 100) if all_entries else 0,
        'loss_threshold': LOSS_THRESHOLD,
        'all_loss_values': loss_values,
        'all_rtt_values': rtt_values,
        'all_transmitted_values': transmitted_values,
        'all_received_values': received_values,
        'all_outage_values': outage_values,
        'start_time': timestamps[0] if timestamps else '',
        'end_time': timestamps[-1] if timestamps else ''
    }

def create_csv_fieldnames() -> List[str]:
    """定义CSV字段名"""
    return [
        'router_name', 'file_path', 'target_ips', 'total_records', 'high_loss_records',
        'high_loss_rate_percent', 'loss_threshold', 'min_loss_percent',
        'max_loss_percent', 'avg_loss_percent', 'min_rtt_avg', 'max_rtt_avg',
        'avg_rtt_avg', 'rtt_std_deviation', 'min_transmitted', 'max_transmitted',
        'avg_transmitted', 'min_received', 'max_received', 'avg_received',
        'min_outage_ms', 'max_outage_ms', 'avg_outage_ms', 'outage_std_deviation',
        'high_loss_quantile_0', 'high_loss_quantile_50', 'high_loss_quantile_99',
        'outage_quantile_0', 'outage_quantile_50', 'outage_quantile_99',
        'raw_loss_data', 'raw_outage_data', 'start_time',
        'end_time', 'duration_records', 'analysis_timestamp', 'extracted_by'
    ]

def calculate_statistics(values: List[Union[int, float]]) -> Dict[str, float]:
    """计算统计值，使用pandas或numpy优化"""
    if not values:
        return {'min': 0, 'max': 0, 'mean': 0, 'std': 0}

    # 仅使用标准库
    n = len(values)
    mean_val = sum(values) / n
    variance = sum((x - mean_val) ** 2 for x in values) / n
    return {
        'min': min(values),
        'max': max(values),
        'mean': mean_val,
        'std': variance ** 0.5
    }

def filter_non_zero_values(values: List[Union[int, float]]) -> List[Union[int, float]]:
    """过滤掉0值，只保留实际的中断/丢包事件"""
    return [v for v in values if v > 0]

def create_csv_row(file_stats: Dict, loss_quantiles: Dict, outage_quantiles: Dict) -> Dict:
    """创建CSV行数据"""
    loss_stats = calculate_statistics(file_stats['all_loss_values'])
    rtt_stats = calculate_statistics(file_stats['all_rtt_values'])
    transmitted_stats = calculate_statistics(file_stats['all_transmitted_values'])
    received_stats = calculate_statistics(file_stats['all_received_values'])
    outage_stats = calculate_statistics(file_stats['all_outage_values'])

    # 过滤掉0值的原始数据，只记录实际的中断/丢包事件
    non_zero_loss_values = filter_non_zero_values(file_stats['all_loss_values'])
    non_zero_outage_values = filter_non_zero_values(file_stats['all_outage_values'])

    # 将过滤后的原始数据转换为逗号分隔的字符串
    raw_loss_data = ','.join(map(str, non_zero_loss_values))
    raw_outage_data = ','.join(map(str, non_zero_outage_values))

    return {
        'router_name': file_stats['router_name'],
        'file_path': file_stats['file_path'],
        'target_ips': ', '.join(file_stats.get('target_ips', [])),
        'total_records': file_stats['total_records'],
        'high_loss_records': file_stats['high_loss_records'],
        'high_loss_rate_percent': round(file_stats['high_loss_rate'], 4),
        'loss_threshold': file_stats['loss_threshold'],
        'min_loss_percent': loss_stats['min'],
        'max_loss_percent': loss_stats['max'],
        'avg_loss_percent': loss_stats['mean'],
        'min_rtt_avg': rtt_stats['min'],
        'max_rtt_avg': rtt_stats['max'],
        'avg_rtt_avg': rtt_stats['mean'],
        'rtt_std_deviation': rtt_stats['std'],
        'min_transmitted': transmitted_stats['min'],
        'max_transmitted': transmitted_stats['max'],
        'avg_transmitted': transmitted_stats['mean'],
        'min_received': received_stats['min'],
        'max_received': received_stats['max'],
        'avg_received': received_stats['mean'],
        'min_outage_ms': outage_stats['min'],
        'max_outage_ms': outage_stats['max'],
        'avg_outage_ms': outage_stats['mean'],
        'outage_std_deviation': outage_stats['std'],
        'high_loss_quantile_0': loss_quantiles.get("0% 分位点", -1),
        'high_loss_quantile_50': loss_quantiles.get("50% 分位点 (中位数)", -1),
        'high_loss_quantile_99': loss_quantiles.get("99% 分位点", -1),
        'outage_quantile_0': outage_quantiles.get("0% 分位点", -1),
        'outage_quantile_50': outage_quantiles.get("50% 分位点 (中位数)", -1),
        'outage_quantile_99': outage_quantiles.get("99% 分位点", -1),
        'raw_loss_data': raw_loss_data,
        'raw_outage_data': raw_outage_data,
        'start_time': file_stats['start_time'],
        'end_time': file_stats['end_time'],
        'duration_records': file_stats['total_records'],
        'analysis_timestamp': '',
        'extracted_by': 'fping2csv_analyzer'
    }

def export_aggregated_csv(file_stats: Dict, loss_quantiles: Dict, outage_quantiles: Dict, output_file: str = "fping_file_analysis.csv") -> None:
    """导出聚合分析结果到CSV，支持多种格式"""
    try:
        row = create_csv_row(file_stats, loss_quantiles, outage_quantiles)
        file_path = Path(output_file)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # 仅使用标准库CSV导出
        fieldnames = create_csv_fieldnames()
        file_exists = file_path.exists()

        with open(file_path, 'a' if file_exists else 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)
    except Exception as e:
        print(f"导出CSV文件时发生错误: {e}")

def find_fping_log_files(base_directory: str) -> List[Path]:
    """查找fping.log文件"""
    return list(Path(base_directory).glob("**/fping.log"))

def process_single_file(fping_file: Path, output_file: str, show_progress: bool = True) -> bool:
    """处理单个fping文件，静默处理"""
    file_stats = analyze_file_statistics(str(fping_file), show_progress)
    if not file_stats:
        return False

    _, loss_quantiles, outage_quantiles, error = analyze_high_loss_quantiles(str(fping_file))

    if error:
        return False

    export_aggregated_csv(file_stats, loss_quantiles, outage_quantiles, output_file)
    return True

def batch_analyze_files(base_directory: str, output_file: str = "batch_fping_analysis.csv") -> None:
    """批量分析fping日志文件，带美观的进度显示"""
    fping_log_files = find_fping_log_files(base_directory)
    if not fping_log_files:
        log_warning(f"在目录 {base_directory} 中未找到任何 fping.log 文件")
        return

    # 删除旧输出文件
    output_path = Path(output_file)
    if output_path.exists():
        output_path.unlink()

    # 静默处理所有文件
    success_count = sum(1 for fping_file in fping_log_files if process_single_file(fping_file, output_file, show_progress=False))
    log_success(f"批量分析完成：成功处理 {success_count}/{len(fping_log_files)} 个文件，结果 -> {output_file}")

def get_cli_arguments() -> Tuple[str, str]:
    """获取命令行参数（简化）。"""
    if len(sys.argv) < 2:
        print("用法: python fping2csv_functional.py <基础目录路径> [输出CSV文件名]")
        print("\n参数说明:")
        print("  基础目录路径: 包含fping.log文件的基础目录路径")
        print("  输出CSV文件名: 可选，默认为 'fping_analysis_results.csv'")
        print("\n示例:")
        print("  python fping2csv_functional.py /path/to/etc")
        print("  python fping2csv_functional.py /path/to/etc custom_fping_output.csv")
        print("\n使用默认路径进行演示...")
        return '/home/ccds/work/AutoNetTest/ospfv3_grid5x5_test/etc', "fping_analysis_results.csv"

    base_dir = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else "fping_analysis_results.csv"
    return base_dir, output_file

def print_csv_format_help() -> None:
    """打印CSV格式帮助信息"""
    help_sections = [
        ("CSV输出格式说明 (每个fping.log文件对应一行汇总数据):", "="*80),
        ("字段说明:", [
            "- router_name: 路由器名称 (从文件路径中提取)",
            "- file_path: fping日志文件的完整路径",
            "- target_ips: 目标IP地址列表 (多个IP用逗号分隔)",
            "- total_records: 日志文件中的总记录数",
            "- high_loss_records: 丢包率 > 1% 的记录数量",
            "- high_loss_rate_percent: 高丢包率记录占总记录的百分比",
            "- loss_threshold: 高丢包率阈值 (固定为 1.0%)",
            "- min_loss_percent: 所有记录中的最小丢包率",
            "- max_loss_percent: 所有记录中的最大丢包率",
            "- avg_loss_percent: 所有记录的平均丢包率",
            "- min_rtt_avg: 所有记录中的最小平均RTT",
            "- max_rtt_avg: 所有记录中的最大平均RTT",
            "- avg_rtt_avg: 所有记录的平均RTT的平均值",
            "- rtt_std_deviation: RTT的标准差",
            "- min_transmitted: 最小发送包数",
            "- max_transmitted: 最大发送包数",
            "- avg_transmitted: 平均发送包数",
            "- min_received: 最小接收包数",
            "- max_received: 最大接收包数",
            "- avg_received: 平均接收包数",
            "- min_outage_ms: 最小中断时间(毫秒)",
            "- max_outage_ms: 最大中断时间(毫秒)",
            "- avg_outage_ms: 平均中断时间(毫秒)",
            "- outage_std_deviation: 中断时间的标准差",
            "- high_loss_quantile_0: 高丢包率记录的0%分位点 (最小值)",
            "- high_loss_quantile_50: 高丢包率记录的50%分位点 (中位数)",
            "- high_loss_quantile_99: 高丢包率记录的99%分位点",
            "- outage_quantile_0: 中断时间的0%分位点 (最小值)",
            "- outage_quantile_50: 中断时间的50%分位点 (中位数)",
            "- outage_quantile_99: 中断时间的99%分位点",
            "- raw_loss_data: 非零丢包率的原始数据 (逗号分隔，过滤0值)",
            "- raw_outage_data: 非零中断时间的原始数据 (逗号分隔，过滤0值)",
            "- start_time: 日志记录的开始时间",
            "- end_time: 日志记录的结束时间",
            "- duration_records: 日志持续的记录数 (等同于total_records)",
            "- analysis_timestamp: 执行分析的时间戳",
            "- extracted_by: 分析工具标识 ('fping2csv_analyzer')"
        ]),
        ("注意事项:", [
            "- 如果某个文件没有高丢包率记录，高丢包分位点值将设置为 -1",
            "- 如果某个文件没有中断时间记录，中断时间分位点值将设置为 -1",
            "- 本工具专门分析fping输出格式: '[时间] IP : xmt/rcv/%loss = X/Y/Z%, outage(ms) = N, min/avg/max = A/B/C'",
            "- 时间戳和数据行分别处理，确保每条数据记录都有对应的时间戳",
            "- 支持IPv6地址格式的fping日志分析",
            "- raw_loss_data 和 raw_outage_data 字段只包含非零值，忽略0值事件",
            "- 自动过滤最后两条记录（全局总结和INT信号中断），避免业务数据污染",
            "- 原始数据过滤确保只记录实际的网络中断和丢包事件"
        ])
    ]

    print(f"\n{'='*80}")
    for title, content in help_sections:
        print(title)
        if isinstance(content, str):
            print(content)
        else:
            print('\n'.join(content))
        print()

# ============================================================================
# CLI接口 - 使用Click优化
# ============================================================================

if False:
    # 已移除 click 依赖的 CLI 分支
    pass

def main() -> None:
    """主函数（简化）。"""
    base_dir, output_file = get_cli_arguments()
    log_info(f"开始批量分析 fping 日志: {base_dir}")
    batch_analyze_files(base_dir, output_file)
    log_success("完成")

if __name__ == "__main__":
    main()
