#!/usr/bin/env python3
"""
Python版本的自动化网络拓扑测试脚本
使用现代Python库提升可读性和交互性

使用方法:
    uv run experiment_utils/auto.py <prefix> <mode>

可用模式:
    auto - 智能工作流 (自动检测拓扑类型)
    full-grid - 完整Grid工作流
    full-torus - 完整Torus工作流
    generate - 生成拓扑
    torus-prep - Torus准备阶段
    torus-collect - Torus收集阶段
    grid-prep - Grid准备阶段
    grid-collect - Grid收集阶段
    emergency - 应急恢复

作者: Augment Agent
日期: 2025-08-09
"""

import os
import re
import shutil
import subprocess
import sys
import time
from enum import Enum
from typing import Optional

# 添加CPU检测
import multiprocessing

import typer
from loguru import logger
from pydantic import BaseModel, Field, field_validator
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm
from rich.table import Table

# 初始化Rich控制台
console = Console()

# 配置日志
logger.remove()
logger.add(sys.stderr, format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")


def get_optimal_workers() -> int:
    """获取最优的并发工作线程数：max(1, CPU核数-1)"""
    cpu_count = multiprocessing.cpu_count()
    optimal_workers = max(1, cpu_count - 1)
    logger.debug(f"检测到CPU核数: {cpu_count}, 设置并发线程数: {optimal_workers}")
    return optimal_workers


class TopologyType(Enum):
    """拓扑类型枚举"""
    TORUS = "torus"
    GRID = "grid"


class Mode(Enum):
    """运行模式枚举"""
    TORUS_PREPARATION = "torus-prep"
    TORUS_COLLECTION = "torus-collect"
    GRID_PREPARATION = "grid-prep"
    GRID_COLLECTION = "grid-collect"
    EMERGENCY_RECOVERY = "emergency"


class Config(BaseModel):
    """配置参数"""
    prefix: str = Field(..., description="节点前缀")
    mode: Mode = Field(..., description="运行模式")
    size: int = Field(..., gt=0, description="网格大小")
    topology_type: TopologyType = Field(..., description="拓扑类型")
    test_dir: str = Field(..., description="测试目录")
    vertical_delay: int = Field(10, ge=0, description="竖直环网卡延迟(ms)")
    horizontal_delay: int = Field(20, ge=0, description="水平环网卡延迟(ms)")
    runtime: Optional[str] = Field(None, description="容器运行时 (docker/podman)")

    @field_validator('size')
    @classmethod
    def validate_size(cls, v):
        if v <= 0:
            raise ValueError("网格大小必须 > 0")
        return v

    @field_validator('vertical_delay', 'horizontal_delay')
    @classmethod
    def validate_delay(cls, v):
        if v < 0:
            raise ValueError("延迟值必须 >= 0")
        return v

    @field_validator('runtime')
    @classmethod
    def validate_runtime(cls, v):
        if v is not None and v not in ['docker', 'podman']:
            raise ValueError("运行时必须是 'docker' 或 'podman'")
        return v


def extract_size_from_prefix(prefix: str) -> Optional[int]:
    """从前缀中提取网格大小"""
    # 匹配格式如: clab-ospfv3-torus20x20 或 clab-ospfv3-grid5x5
    match = re.search(r'(torus|grid)(\d+)x(\d+)$', prefix)
    if match:
        width = int(match.group(2))
        height = int(match.group(3))
        # 假设是正方形网格，返回宽度
        if width == height:
            return width
        else:
            # 如果不是正方形，返回较大的值
            return max(width, height)
    return None


def determine_topology_type(prefix: str) -> Optional[TopologyType]:
    """从前缀确定拓扑类型"""
    if "torus" in prefix:
        return TopologyType.TORUS
    elif "grid" in prefix:
        return TopologyType.GRID
    return None


def parse_mode(mode_input: str) -> Mode:
    """解析模式输入，仅支持字符串格式"""
    # 字符串模式映射
    string_mode_map = {
        "torus-prep": Mode.TORUS_PREPARATION,
        "torus-collect": Mode.TORUS_COLLECTION,
        "grid-prep": Mode.GRID_PREPARATION,
        "grid-collect": Mode.GRID_COLLECTION,
        "emergency": Mode.EMERGENCY_RECOVERY,
    }

    # 解析为字符串
    if mode_input in string_mode_map:
        return string_mode_map[mode_input]

    # 如果不匹配，抛出错误
    valid_modes = list(string_mode_map.keys())
    raise ValueError(f"无效的模式 '{mode_input}'。有效模式: {valid_modes}")


def create_config(prefix: str, mode_input: str, vertical_delay: int = 10, horizontal_delay: int = 20, runtime: Optional[str] = None) -> Config:
    """创建配置对象"""
    size = extract_size_from_prefix(prefix)
    if not size:
        raise ValueError(f"无法从前缀 '{prefix}' 中提取大小。期望格式: clab-ospfv3-torus5x5 或 clab-ospfv3-grid5x5")

    topology_type = determine_topology_type(prefix)
    if not topology_type:
        raise ValueError(f"无法从前缀 '{prefix}' 确定拓扑类型。期望前缀包含 'torus' 或 'grid'")

    # 解析模式
    mode = parse_mode(mode_input)

    test_dir = f"ospfv3_{topology_type.value}{size}x{size}"

    return Config(
        prefix=prefix,
        mode=mode,
        size=size,
        topology_type=topology_type,
        test_dir=test_dir,
        vertical_delay=vertical_delay,
        horizontal_delay=horizontal_delay,
        runtime=runtime
    )


def build_containerlab_command(base_cmd: str, runtime: Optional[str] = None) -> str:
    """构建containerlab命令，可选择添加runtime参数"""
    if runtime:
        # 在containerlab后面插入--runtime参数
        parts = base_cmd.split(' ', 1)  # 分割为 'containerlab' 和剩余部分
        if len(parts) == 2 and parts[0] == 'containerlab':
            return f"containerlab --runtime {runtime} {parts[1]}"
        else:
            # 如果命令格式不符合预期，直接添加到末尾
            return f"{base_cmd} --runtime {runtime}"
    return base_cmd


def run_command(cmd: str, check: bool = True, shell: bool = True, description: str = "") -> subprocess.CompletedProcess:
    """执行命令的通用函数，带有美化输出"""
    if description:
        console.print(f"[bold blue]🔧 {description}[/bold blue]")

    console.print(f"[dim]执行: {cmd}[/dim]")

    try:
        result = subprocess.run(cmd, shell=shell, check=check, capture_output=True, text=True)
        if result.stdout:
            console.print(f"[green]✓ 命令执行成功[/green]")
            logger.debug(f"命令输出: {result.stdout}")
        return result
    except subprocess.CalledProcessError as e:
        console.print(f"[red]✗ 命令执行失败: {e}[/red]")
        if e.stderr:
            console.print(f"[red]错误信息: {e.stderr}[/red]")
        raise


def run_uv_command(script_path: str, *args: str, description: str = "") -> subprocess.CompletedProcess:
    """执行uv run命令的便捷函数"""
    # 使用shlex.quote来正确处理包含特殊字符的参数
    import shlex

    quoted_args = []
    for arg in args:
        # 使用shlex.quote来安全地引用参数，它会正确处理嵌套引号
        quoted_args.append(shlex.quote(arg))

    cmd = f"uv run {script_path} {' '.join(quoted_args)}"
    return run_command(cmd, description=description)


def run_functional_script(script_name: str, *args: str, description: str = "") -> subprocess.CompletedProcess:
    """执行脚本，自动设置最优并发数"""
    import shlex

    # 使用 experiment_utils 目录下的脚本
    script_path = f"experiment_utils/{script_name}.py"

    # 获取最优并发数
    optimal_workers = get_optimal_workers()

    # 构建参数列表
    quoted_args = []
    for arg in args:
        quoted_args.append(shlex.quote(arg))

    # 为支持并发的脚本添加workers参数
    if script_name in ["execute_on_all", "execute_in_batches", "inject"]:
        quoted_args.extend(["--workers", str(optimal_workers)])

    cmd = f"uv run {script_path} {' '.join(quoted_args)}"
    return run_command(cmd, description=description)


def remove_file_if_exists(file_path: str) -> None:
    """如果文件存在则删除"""
    if os.path.exists(file_path):
        os.remove(file_path)
        console.print(f"[yellow]🗑️  删除文件: {file_path}[/yellow]")
        logger.info(f"删除文件: {file_path}")


def remove_directory_if_exists(dir_path: str) -> None:
    """如果目录存在则删除"""
    if os.path.exists(dir_path):
        shutil.rmtree(dir_path)
        console.print(f"[yellow]🗑️  删除目录: {dir_path}[/yellow]")
        logger.info(f"删除目录: {dir_path}")


def show_config_info(config: Config) -> None:
    """显示配置信息的美化表格"""
    table = Table(title="🔧 配置信息", show_header=True, header_style="bold magenta")
    table.add_column("参数", style="cyan", no_wrap=True)
    table.add_column("值", style="green")

    table.add_row("拓扑类型", config.topology_type.value)
    table.add_row("网格大小", f"{config.size}x{config.size}")
    table.add_row("节点前缀", config.prefix)
    table.add_row("测试目录", config.test_dir)
    table.add_row("运行模式", f"{config.mode.value} ({get_mode_description(config.mode)})")
    table.add_row("竖直延迟", f"{config.vertical_delay}ms (链路: {config.vertical_delay*2}ms)")
    table.add_row("水平延迟", f"{config.horizontal_delay}ms (链路: {config.horizontal_delay*2}ms)")
    table.add_row("容器运行时", config.runtime or "默认 (docker)")

    console.print(table)


# 移除智能工作流参数收集功能

def get_mode_description(mode: Mode) -> str:
    """获取模式描述"""
    descriptions = {
        Mode.TORUS_PREPARATION: "Torus准备阶段",
        Mode.TORUS_COLLECTION: "Torus收集阶段",
        Mode.GRID_PREPARATION: "Grid准备阶段",
        Mode.GRID_COLLECTION: "Grid收集阶段",
        Mode.EMERGENCY_RECOVERY: "应急恢复"
    }
    return descriptions.get(mode, "未知模式")


# 移除智能工作流处理函数

# 移除未实现的完整工作流和拓扑生成功能


def handle_torus_preparation(config: Config) -> None:
    """处理Torus准备阶段"""
    console.print(Panel.fit("🔧 Torus准备阶段", style="bold cyan"))

    prefix = config.prefix
    size_str = str(config.size)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:

        # 设置延迟
        task = progress.add_task("设置网络延迟...", total=None)
        delay_args = ["simple_delay", prefix, size_str,
                     "--vertical", str(config.vertical_delay),
                     "--horizontal", str(config.horizontal_delay)]
        if config.runtime:
            delay_args.extend(["--runtime", config.runtime])
        delay_args.append("--execute")
        run_functional_script(*delay_args, description="配置网络延迟")

        # 清理脚本目录
        progress.update(task, description="清理脚本目录...")
        run_functional_script("execute_on_all", prefix, size_str, "rm -rf /opt/scripts", "--detach", "--execute",
                             description="清理容器中的脚本目录")

        # 复制脚本
        progress.update(task, description="复制监控脚本...")
        run_functional_script("copy_to_containers", prefix, size_str, "./scripts", "/opt/scripts", "--execute",
                             description="复制脚本到容器")

        # 启动监控
        progress.update(task, description="启动fping监控...")
        fping_cmd = r'sudo sh -c "fping -6 -l -o -p 10 -r 0 -e -t 160 -Q 1 2001:db8:1000:0000:0003:0002::1 &> /var/log/frr/fping.log"'
        run_functional_script("execute_on_all", prefix, size_str, fping_cmd, "--detach", "--execute",
                             description="启动fping网络监控")

        progress.update(task, description="启动收敛分析器...")
        analyzer_cmd = "/opt/scripts/ConvergenceAnalyzer --threshold 5000 --log-path /var/log/frr/route.json"
        run_functional_script("execute_on_all", prefix, size_str, analyzer_cmd, "--detach", "--execute",
                             description="启动路由收敛分析器")

        progress.update(task, description="启动数据包捕获...")
        pcap_filename = f"ospfv3_{config.topology_type.value}{config.size}x{config.size}.pcap"
        tcpdump_cmd = f"tcpdump -i any -w /var/log/frr/{pcap_filename} ip6 proto 89"
        run_functional_script("execute_on_all", prefix, size_str, tcpdump_cmd, "--detach", "--execute",
                             description="启动OSPFv3数据包捕获")

        progress.update(task, description="✅ Torus监控启动完成")

    console.print("[bold green]🎉 Torus监控启动成功！[/bold green]")


def handle_torus_collection(config: Config) -> None:
    """处理Torus收集阶段 (模式 2)"""
    # 拓扑类型验证已在 validate_config 中完成，这里不需要重复检查
    console.print(Panel.fit("📊 Torus数据收集", style="bold magenta"))
    
    prefix = config.prefix
    size_str = str(config.size)
    size = config.size

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:

        # 停止监控进程
        task = progress.add_task("停止监控进程...", total=None)
        run_functional_script("execute_on_torus", prefix, size_str, "--kill-process", "ConvergenceAnalyzer", "--signal", "INT", "--execute",
                             description="停止收敛分析器")
        run_functional_script("execute_on_torus", prefix, size_str, "--kill-process", "fping", "--signal", "INT", "--execute",
                             description="停止fping监控")
        run_functional_script("execute_on_torus", prefix, size_str, "--kill-process", "tcpdump", "--signal", "INT", "--execute",
                             description="停止数据包捕获")

        # 清理旧数据文件
        progress.update(task, description="清理旧数据文件...")
        remove_file_if_exists(f"./data/converge-ospfv3_torus{size}x{size}.csv")
        remove_file_if_exists(f"./data/ping-ospfv3_torus{size}x{size}.csv")
        remove_file_if_exists(f"./data/fping-ospfv3_torus{size}x{size}.csv")

        # 生成CSV数据
        progress.update(task, description="生成收敛数据CSV...")
        run_uv_command("experiment_utils/csv_converter.py", "log2csv", config.test_dir + "/etc", f"./data/converge-ospfv3_torus{size}x{size}.csv",
                             description="转换收敛日志为CSV")

        progress.update(task, description="生成fping数据CSV...")
        run_uv_command("experiment_utils/csv_converter.py", "fping2csv", config.test_dir + "/etc", f"./data/fping-ospfv3_torus{size}x{size}.csv",
                             description="转换fping日志为CSV")

        # 生成图表
        progress.update(task, description="生成收敛分析图表...")
        run_uv_command("experiment_utils/plotter.py", "converge_draw", f"./data/converge-ospfv3_torus{size}x{size}.csv", f"./results/converge-ospfv3_torus{size}x{size}.png", "--size", f"{size}x{size}",
                      description="生成收敛分析热力图")

        progress.update(task, description="生成中断分析图表...")
        run_uv_command("experiment_utils/plotter.py", "fping_outage_draw", f"./data/fping-ospfv3_torus{size}x{size}.csv", f"./results/fping-ospfv3_torus{size}x{size}.png", "--size", f"{size}x{size}",
                      description="生成中断分析热力图")

        progress.update(task, description="✅ Torus数据收集完成")

    console.print("[bold green]🎉 Torus数据收集和可视化完成！[/bold green]")


def handle_grid_preparation(config: Config) -> None:
    """处理Grid准备阶段"""
    console.print(Panel.fit("🔧 Grid准备阶段", style="bold cyan"))

    prefix = config.prefix
    size_str = str(config.size)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:

        # 设置延迟
        task = progress.add_task("设置网络延迟...", total=None)
        delay_args = ["simple_delay", prefix, size_str,
                     "--vertical", str(config.vertical_delay),
                     "--horizontal", str(config.horizontal_delay)]
        if config.runtime:
            delay_args.extend(["--runtime", config.runtime])
        delay_args.append("--execute")
        run_functional_script(*delay_args, description="配置网络延迟")

        # 清理脚本目录
        progress.update(task, description="清理脚本目录...")
        run_functional_script("execute_on_all", prefix, size_str, "rm -rf /opt/scripts", "--detach", "--execute",
                             description="清理容器中的脚本目录")

        # 复制脚本
        progress.update(task, description="复制监控脚本...")
        run_functional_script("copy_to_containers", prefix, size_str, "./scripts", "/opt/scripts", "--execute",
                             description="复制脚本到容器")

        # 启动监控 (Grid使用更长的超时时间)
        progress.update(task, description="启动fping监控...")
        fping_cmd = r'sudo sh -c "fping -6 -l -o -p 10 -r 0 -e -t 1000 -Q 1 2001:db8:1000:0000:0003:0002::1 &> /var/log/frr/fping.log"'
        run_functional_script("execute_on_all", prefix, size_str, fping_cmd, "--detach", "--execute",
                             description="启动fping网络监控")

        progress.update(task, description="启动收敛分析器...")
        analyzer_cmd = "/opt/scripts/ConvergenceAnalyzer --threshold 5000 --log-path /var/log/frr/route.json"
        run_functional_script("execute_on_all", prefix, size_str, analyzer_cmd, "--detach", "--execute",
                             description="启动路由收敛分析器")

        progress.update(task, description="启动数据包捕获...")
        pcap_filename = f"ospfv3_{config.topology_type.value}{config.size}x{config.size}.pcap"
        tcpdump_cmd = f"tcpdump -i any -w /var/log/frr/{pcap_filename} ip6 proto 89"
        run_functional_script("execute_on_all", prefix, size_str, tcpdump_cmd, "--detach", "--execute",
                             description="启动OSPFv3数据包捕获")

        progress.update(task, description="✅ Grid监控启动完成")

    console.print("[bold green]🎉 Grid监控启动成功！[/bold green]")


def handle_grid_collection(config: Config) -> None:
    """处理Grid收集阶段 (模式 4)"""
    # 拓扑类型验证已在 validate_config 中完成，这里不需要重复检查
    console.print(Panel.fit("📊 Grid数据收集", style="bold magenta"))

    prefix = config.prefix
    size_str = str(config.size)
    size = config.size

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:

        # 停止监控进程
        task = progress.add_task("停止监控进程...", total=None)
        run_functional_script("execute_on_torus", prefix, size_str, "--kill-process", "ConvergenceAnalyzer", "--signal", "INT", "--execute",
                             description="停止收敛分析器")
        run_functional_script("execute_on_torus", prefix, size_str, "--kill-process", "fping", "--signal", "INT", "--execute",
                             description="停止fping监控")
        run_functional_script("execute_on_torus", prefix, size_str, "--kill-process", "tcpdump", "--signal", "INT", "--execute",
                             description="停止数据包捕获")

        # 清理旧数据文件
        progress.update(task, description="清理旧数据文件...")
        remove_file_if_exists(f"./data/converge-ospfv3_grid{size}x{size}.csv")
        remove_file_if_exists(f"./data/fping-ospfv3_grid{size}x{size}.csv")

        # 生成CSV数据
        progress.update(task, description="生成收敛数据CSV...")
        run_uv_command("experiment_utils/csv_converter.py", "log2csv", config.test_dir + "/etc", f"./data/converge-ospfv3_grid{size}x{size}.csv",
                             description="转换收敛日志为CSV")

        progress.update(task, description="生成fping数据CSV...")
        run_uv_command("experiment_utils/csv_converter.py", "fping2csv", config.test_dir + "/etc", f"./data/fping-ospfv3_grid{size}x{size}.csv",
                             description="转换fping日志为CSV")

        # 生成图表
        progress.update(task, description="生成收敛分析图表...")
        run_uv_command("experiment_utils/plotter.py", "converge_draw", f"./data/converge-ospfv3_grid{size}x{size}.csv", f"./results/converge-ospfv3_grid{size}x{size}.png", "--size", f"{size}x{size}",
                      description="生成收敛分析热力图")

        progress.update(task, description="生成中断分析图表...")
        run_uv_command("experiment_utils/plotter.py", "fping_outage_draw", f"./data/fping-ospfv3_grid{size}x{size}.csv", f"./results/fping-ospfv3_grid{size}x{size}.png", "--size", f"{size}x{size}",
                      description="生成中断分析热力图")

        progress.update(task, description="✅ Grid数据收集完成")

    console.print("[bold green]🎉 Grid数据收集和可视化完成！[/bold green]")


def handle_emergency_recovery(config: Config) -> None:
    """处理应急恢复 - 重启监控"""
    console.print(Panel.fit("🚨 应急恢复", style="bold yellow"))

    prefix = config.prefix
    size_str = str(config.size)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:

        # 设置延迟
        task = progress.add_task("设置网络延迟...", total=None)
        delay_args = ["simple_delay", prefix, size_str,
                     "--vertical", str(config.vertical_delay),
                     "--horizontal", str(config.horizontal_delay)]
        if config.runtime:
            delay_args.extend(["--runtime", config.runtime])
        delay_args.append("--execute")
        run_functional_script(*delay_args, description="配置网络延迟")

        # 复制脚本
        progress.update(task, description="复制监控脚本...")
        run_functional_script("copy_to_containers", prefix, size_str, "./scripts", "/opt/scripts", "--execute",
                             description="复制脚本到容器")

        progress.update(task, description="✅ 应急恢复完成")

    console.print("[bold green]🎉 监控脚本复制成功！[/bold green]")


# 模式处理器映射
MODE_HANDLERS = {
    Mode.TORUS_PREPARATION: handle_torus_preparation,
    Mode.TORUS_COLLECTION: handle_torus_collection,
    Mode.GRID_PREPARATION: handle_grid_preparation,
    Mode.GRID_COLLECTION: handle_grid_collection,
    Mode.EMERGENCY_RECOVERY: handle_emergency_recovery,
}


def validate_config(config: Config) -> None:
    """验证配置的有效性，提前检测拓扑兼容性"""
    if config.size <= 0:
        raise ValueError("网格大小必须 > 0")

    # 验证模式与拓扑类型的兼容性 - 提前检测
    torus_modes = {Mode.TORUS_PREPARATION, Mode.TORUS_COLLECTION}
    grid_modes = {Mode.GRID_PREPARATION, Mode.GRID_COLLECTION}

    if config.mode in torus_modes and config.topology_type != TopologyType.TORUS:
        raise ValueError(f"❌ 配置错误: 模式 {config.mode.value} 用于torus拓扑，但检测到 {config.topology_type.value}")

    if config.mode in grid_modes and config.topology_type != TopologyType.GRID:
        raise ValueError(f"❌ 配置错误: 模式 {config.mode.value} 用于grid拓扑，但检测到 {config.topology_type.value}")

    # 验证前缀格式的完整性
    if not re.match(r'^clab-ospfv3-(torus|grid)\d+x\d+$', config.prefix):
        raise ValueError(f"❌ 配置错误: 前缀格式不正确 '{config.prefix}'。期望格式: clab-ospfv3-torus20x20 或 clab-ospfv3-grid5x5")

    # 验证拓扑类型与前缀的一致性
    prefix_topology = determine_topology_type(config.prefix)
    if prefix_topology != config.topology_type:
        raise ValueError(f"❌ 配置错误: 前缀中的拓扑类型 '{prefix_topology.value}' 与检测到的拓扑类型 '{config.topology_type.value}' 不一致")

    # 验证网格大小与前缀的一致性
    prefix_size = extract_size_from_prefix(config.prefix)
    if prefix_size != config.size:
        raise ValueError(f"❌ 配置错误: 前缀中的网格大小 '{prefix_size}' 与检测到的大小 '{config.size}' 不一致")


app = typer.Typer(
    name="auto",
    help="Python版本的自动化网络拓扑测试脚本",
    rich_markup_mode="rich",
    add_completion=False
)


@app.command()
def main(
    prefix: str = typer.Argument(..., help="节点前缀 (如: clab-ospfv3-torus5x5)"),
    mode: str = typer.Argument(..., help="运行模式 (支持数字或字符串)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="启用详细日志输出"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认，直接执行"),
    confirm: bool = typer.Option(True, "--confirm/--no-confirm", help="执行前确认操作 (被 --yes 覆盖)"),
    vertical_delay: int = typer.Option(10, "--vertical-delay", help="竖直环网卡延迟(ms，默认10ms->20ms链路)"),
    horizontal_delay: int = typer.Option(20, "--horizontal-delay", help="水平环网卡延迟(ms，默认20ms->40ms链路)"),
    runtime: Optional[str] = typer.Option(None, "--runtime", help="容器运行时 (docker/podman)")
) -> None:
    """
    自动化网络拓扑测试脚本

    [bold]可用模式:[/bold]

    • [green]torus-prep[/green] - Torus准备阶段 (设置监控)
    • [green]torus-collect[/green] - Torus收集阶段 (收集数据并生成图表)
    • [green]grid-prep[/green] - Grid准备阶段 (设置监控)
    • [green]grid-collect[/green] - Grid收集阶段 (收集数据并生成图表)
    • [yellow]emergency[/yellow] - 应急恢复 (重启监控)

    [bold]示例:[/bold]

    [dim]# 分阶段执行[/dim]
    • [dim]uv run experiment_utils/auto.py clab-ospfv3-torus20x20 torus-prep[/dim]
    • [dim]uv run experiment_utils/auto.py clab-ospfv3-torus20x20 torus-collect[/dim]
    • [dim]uv run experiment_utils/auto.py clab-ospfv3-grid5x5 grid-prep[/dim]
    • [dim]uv run experiment_utils/auto.py clab-ospfv3-grid5x5 grid-collect[/dim]

    [dim]# 容器运行时选择[/dim]
    • [dim]uv run experiment_utils/auto.py clab-ospfv3-torus20x20 torus-prep --runtime docker[/dim]
    • [dim]uv run experiment_utils/auto.py clab-ospfv3-grid5x5 grid-prep --runtime podman[/dim]

    [dim]# 网络延迟配置[/dim]
    • [dim]uv run experiment_utils/auto.py clab-ospfv3-torus20x20 torus-prep --vertical-delay 5 --horizontal-delay 10[/dim]
    • [dim]uv run experiment_utils/auto.py clab-ospfv3-grid8x8 grid-prep --vertical-delay 50 --horizontal-delay 100[/dim]

    [dim]# 应急恢复[/dim]
    • [dim]uv run experiment_utils/auto.py clab-ospfv3-torus20x20 emergency --runtime podman[/dim]

    [bold]选项:[/bold]
    • [green]--yes, -y[/green]              跳过确认，直接执行
    • [green]--verbose, -v[/green]          启用详细日志输出
    • [green]--no-confirm[/green]           禁用确认提示
    • [green]--vertical-delay[/green]       竖直环网卡延迟(ms，默认10ms->20ms链路)
    • [green]--horizontal-delay[/green]     水平环网卡延迟(ms，默认20ms->40ms链路)
    • [green]--runtime[/green]              容器运行时 (docker/podman，默认docker)
    """

    # 配置日志级别
    if verbose:
        logger.add(sys.stderr, level="DEBUG")
    else:
        logger.add(sys.stderr, level="INFO")

    try:
        # 创建配置
        config = create_config(prefix, mode, vertical_delay, horizontal_delay, runtime)

        # 验证配置
        validate_config(config)

        # 显示配置信息
        show_config_info(config)

        # 确认执行 (除非使用 --yes 参数)
        if not yes and confirm:
            if not Confirm.ask(f"\n[bold yellow]确认执行 {get_mode_description(config.mode)} 吗？[/bold yellow]"):
                console.print("[yellow]操作已取消[/yellow]")
                raise typer.Exit(0)
        elif yes:
            console.print(f"[dim]使用 --yes 参数，跳过确认直接执行 {get_mode_description(config.mode)}[/dim]")

        # 获取处理器并执行
        start_time = time.time()

        # 标准模式处理
        handler = MODE_HANDLERS.get(config.mode)
        if not handler:
            raise ValueError(f"无效的模式 '{config.mode.value}'")
        handler(config)

        end_time = time.time()

        # 显示执行时间
        duration = end_time - start_time
        console.print(f"\n[bold green]✅ 任务完成！耗时: {duration:.2f}秒[/bold green]")

    except ValueError as e:
        console.print(f"[bold red]❌ 配置错误: {e}[/bold red]")
        raise typer.Exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️  用户中断操作[/yellow]")
        raise typer.Exit(0)
    except Exception as e:
        console.print(f"[bold red]❌ 未知错误: {e}[/bold red]")
        logger.exception("详细错误信息:")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
