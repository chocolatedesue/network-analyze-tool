#!/usr/bin/env python3
"""
Python版本的自动化网络拓扑测试脚本
使用现代Python库提升可读性和交互性，保持与bash版本相同的交互方式

使用方法:
    python3 auto.py <prefix> <mode>

可用模式:
    -2 - 完整Grid工作流 (重置, 生成, 部署, 监控, 收集)
    -1 - 完整Torus工作流 (重置, 生成, 部署, 监控, 收集)
    0  - 生成拓扑 (torus和grid)
    1  - Torus准备阶段 (设置监控)
    2  - Torus收集阶段 (收集数据并生成图表)
    3  - Grid准备阶段 (设置监控)
    4  - Grid收集阶段 (收集数据并生成图表)
    5  - 应急恢复 (重启监控)

作者: Augment Agent
日期: 2025-08-07
"""

import os
import re
import shutil
import subprocess
import sys
import time
from enum import Enum
from pathlib import Path
from typing import List, Optional

# 添加CPU检测
import multiprocessing

import typer
from loguru import logger
from pydantic import BaseModel, Field, field_validator
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, Prompt, IntPrompt
from rich.table import Table
from rich.text import Text

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
    AUTO_WORKFLOW = "auto"
    FULL_GRID = "full-grid"
    FULL_TORUS = "full-torus"
    GENERATE_TOPOLOGIES = "generate"
    TORUS_PREPARATION = "torus-prep"
    TORUS_COLLECTION = "torus-collect"
    GRID_PREPARATION = "grid-prep"
    GRID_COLLECTION = "grid-collect"
    EMERGENCY_RECOVERY = "emergency"

    # 保持向后兼容的数字模式
    AUTO_WORKFLOW_NUM = -3
    FULL_GRID_NUM = -2
    FULL_TORUS_NUM = -1
    GENERATE_NUM = 0
    TORUS_PREPARATION_NUM = 1
    TORUS_COLLECTION_NUM = 2
    GRID_PREPARATION_NUM = 3
    GRID_COLLECTION_NUM = 4
    EMERGENCY_RECOVERY_NUM = 5


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
    match = re.search(r'x(\d+)', prefix)
    return int(match.group(1)) if match else None


def determine_topology_type(prefix: str) -> Optional[TopologyType]:
    """从前缀确定拓扑类型"""
    if "torus" in prefix:
        return TopologyType.TORUS
    elif "grid" in prefix:
        return TopologyType.GRID
    return None


def parse_mode(mode_input: str) -> Mode:
    """解析模式输入，支持数字和字符串两种格式"""
    # 数字模式映射
    number_mode_map = {
        -3: Mode.AUTO_WORKFLOW,
        -2: Mode.FULL_GRID,
        -1: Mode.FULL_TORUS,
        0: Mode.GENERATE_TOPOLOGIES,
        1: Mode.TORUS_PREPARATION,
        2: Mode.TORUS_COLLECTION,
        3: Mode.GRID_PREPARATION,
        4: Mode.GRID_COLLECTION,
        5: Mode.EMERGENCY_RECOVERY,
    }

    # 字符串模式映射
    string_mode_map = {
        "auto": Mode.AUTO_WORKFLOW,
        "full-grid": Mode.FULL_GRID,
        "full-torus": Mode.FULL_TORUS,
        "generate": Mode.GENERATE_TOPOLOGIES,
        "torus-prep": Mode.TORUS_PREPARATION,
        "torus-collect": Mode.TORUS_COLLECTION,
        "grid-prep": Mode.GRID_PREPARATION,
        "grid-collect": Mode.GRID_COLLECTION,
        "emergency": Mode.EMERGENCY_RECOVERY,
    }

    # 尝试解析为数字
    try:
        mode_num = int(mode_input)
        if mode_num in number_mode_map:
            return number_mode_map[mode_num]
    except ValueError:
        pass

    # 尝试解析为字符串
    if mode_input in string_mode_map:
        return string_mode_map[mode_input]

    # 如果都不匹配，抛出错误
    valid_modes = list(number_mode_map.keys()) + list(string_mode_map.keys())
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
    """执行函数式版本的脚本，自动设置最优并发数"""
    import shlex

    # 检查是否有函数式版本
    functional_script = f"setup/{script_name}_functional.py"
    if os.path.exists(functional_script):
        # 使用函数式版本
        script_path = functional_script
        console.print(f"[dim]使用函数式版本: {script_path}[/dim]")
    else:
        # 回退到原版本
        script_path = f"setup/{script_name}.py"
        console.print(f"[dim]使用原版本: {script_path}[/dim]")

    # 获取最优并发数
    optimal_workers = get_optimal_workers()

    # 构建参数列表，添加并发数参数
    quoted_args = []
    for arg in args:
        quoted_args.append(shlex.quote(arg))

    # 不需要workers参数的脚本列表（CSV处理和绘图相关的脚本）
    scripts_without_workers = {
        "log2csv", "fping2csv", "ping2csv", "rawping2csv",  # CSV处理脚本
        "converge_draw", "fping_outage_draw", "ping_analysis_draw",  # 绘图脚本
        "draw", "plot", "visualize", "chart", "csv"  # 通用关键词
    }

    # 为函数式脚本添加并发数参数（排除CSV和绘图相关脚本）
    if "_functional.py" in script_path:
        # 检查脚本名是否包含CSV或绘图相关关键词
        needs_workers = not any(keyword in script_name.lower() for keyword in scripts_without_workers)
        if needs_workers:
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


def collect_auto_workflow_parameters(config: Config, yes: bool = False) -> dict:
    """
    收集智能工作流的参数，支持交互式和非交互式模式

    Args:
        config: 配置对象
        yes: 是否跳过交互，使用默认值

    Returns:
        dict: 包含所有参数的字典
    """
    if yes:
        # 非交互模式，使用默认值
        return {
            "max_executions": 2,
            "min_interval": 20,
            "max_interval": 30,
            "fault_type": "link",
            "skip_deploy": False,
            "skip_fault_injection": False
        }

    # 交互模式
    console.print(Panel.fit("🔧 智能工作流参数配置", style="bold cyan"))
    console.print(f"[dim]拓扑: {config.topology_type.value} {config.size}x{config.size}[/dim]\n")

    # 故障注入参数
    console.print("[bold]故障注入配置:[/bold]")

    max_executions = IntPrompt.ask(
        "最大故障注入次数",
        default=2,
        show_default=True
    )

    fault_type = Prompt.ask(
        "故障类型",
        choices=["link", "node"],
        default="link",
        show_default=True
    )

    min_interval = IntPrompt.ask(
        "最小故障间隔 (秒)",
        default=20,
        show_default=True
    )

    max_interval = IntPrompt.ask(
        "最大故障间隔 (秒)",
        default=30,
        show_default=True
    )

    # 工作流控制参数
    console.print("\n[bold]工作流控制:[/bold]")

    skip_deploy = Confirm.ask(
        "跳过容器部署阶段？(如果容器已经运行)",
        default=False
    )

    skip_fault_injection = Confirm.ask(
        "跳过故障注入阶段？(仅设置监控)",
        default=False
    )

    # 显示参数摘要
    console.print("\n[bold]参数摘要:[/bold]")
    table = Table(show_header=False, box=None)
    table.add_column("参数", style="cyan")
    table.add_column("值", style="green")

    table.add_row("故障类型", fault_type)
    table.add_row("注入次数", str(max_executions))
    table.add_row("故障间隔", f"{min_interval}-{max_interval}秒")
    table.add_row("跳过部署", "是" if skip_deploy else "否")
    table.add_row("跳过故障注入", "是" if skip_fault_injection else "否")

    console.print(table)

    return {
        "max_executions": max_executions,
        "min_interval": min_interval,
        "max_interval": max_interval,
        "fault_type": fault_type,
        "skip_deploy": skip_deploy,
        "skip_fault_injection": skip_fault_injection
    }

def get_mode_description(mode: Mode) -> str:
    """获取模式描述"""
    descriptions = {
        Mode.AUTO_WORKFLOW: "智能工作流 (自动检测拓扑类型)",
        Mode.FULL_GRID: "完整Grid工作流",
        Mode.FULL_TORUS: "完整Torus工作流",
        Mode.GENERATE_TOPOLOGIES: "生成拓扑",
        Mode.TORUS_PREPARATION: "Torus准备阶段",
        Mode.TORUS_COLLECTION: "Torus收集阶段",
        Mode.GRID_PREPARATION: "Grid准备阶段",
        Mode.GRID_COLLECTION: "Grid收集阶段",
        Mode.EMERGENCY_RECOVERY: "应急恢复"
    }
    return descriptions.get(mode, "未知模式")


# 模式处理函数
def handle_auto_workflow(config: Config, max_executions: int = 2, min_interval: int = 20, max_interval: int = 30,
                        fault_type: str = "link", skip_deploy: bool = False, skip_fault_injection: bool = False) -> None:
    """
    处理智能工作流 (模式 -3/auto) - 根据拓扑类型自动选择相应的完整工作流

    Args:
        config: 配置对象
        max_executions: 最大故障注入次数
        min_interval: 最小故障间隔 (秒)
        max_interval: 最大故障间隔 (秒)
        fault_type: 故障类型 (link/node)
        skip_deploy: 跳过部署阶段
        skip_fault_injection: 跳过故障注入阶段
    """
    topology_name = f"{config.topology_type.value.title()}"
    console.print(Panel.fit(f"🤖 智能工作流 - {topology_name} 拓扑", style="bold magenta"))

    console.print(f"[dim]检测到拓扑类型: {config.topology_type.value}[/dim]")
    console.print(f"[dim]网格大小: {config.size}x{config.size}[/dim]")
    console.print(f"[dim]故障注入配置: 类型={fault_type}, 次数={max_executions}, 间隔={min_interval}-{max_interval}秒[/dim]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:

        # 清理并重新生成
        task = progress.add_task("清理旧数据...", total=None)
        test_dir = f"ospfv3_{config.topology_type.value}{config.size}x{config.size}"
        remove_directory_if_exists(test_dir)

        progress.update(task, description="生成拓扑...")
        handle_generate_topologies(config)

        # 部署阶段
        if not skip_deploy:
            progress.update(task, description="部署容器...")
            deploy_cmd = build_containerlab_command(f"containerlab deploy -t {test_dir}/ --reconfigure", config.runtime)
            run_command(deploy_cmd, description=f"部署{topology_name}拓扑")

            progress.update(task, description="等待容器启动...")
            time.sleep(10)
        else:
            console.print("[yellow]⚠️  跳过部署阶段[/yellow]")

        # 准备阶段 - 根据拓扑类型选择
        progress.update(task, description="设置监控...")
        if config.topology_type == TopologyType.TORUS:
            handle_torus_preparation(config)
        else:
            handle_grid_preparation(config)

        # 故障注入阶段
        if not skip_fault_injection:
            progress.update(task, description="注入故障...")
            run_functional_script("inject", config.prefix, "--max-executions", str(max_executions),
                                 "-t", fault_type, "--min-interval", str(min_interval),
                                 "--max-interval", str(max_interval),
                                 description=f"执行{fault_type}故障注入")
        else:
            console.print("[yellow]⚠️  跳过故障注入阶段[/yellow]")

        # 收集阶段 - 根据拓扑类型选择
        progress.update(task, description="收集数据...")
        if config.topology_type == TopologyType.TORUS:
            handle_torus_collection(config)
        else:
            handle_grid_collection(config)

        progress.update(task, description=f"✅ {topology_name}智能工作流完成")

    console.print(f"[bold green]🎉 {topology_name}智能工作流执行完成！[/bold green]")

def handle_full_grid_workflow(config: Config) -> None:
    """处理完整Grid工作流 (模式 -2)"""
    console.print(Panel.fit("🚀 运行完整Grid工作流", style="bold green"))

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:

        # 清理并重新生成
        task = progress.add_task("清理旧数据...", total=None)
        remove_directory_if_exists("ospfv3_grid5x5")
        progress.update(task, description="生成拓扑...")
        handle_generate_topologies(config)

        # 部署
        progress.update(task, description="部署容器...")
        deploy_cmd = build_containerlab_command("containerlab deploy -t ospfv3_grid5x5/ --reconfigure", config.runtime)
        run_command(deploy_cmd, description="部署Grid拓扑")
        progress.update(task, description="等待容器启动...")
        time.sleep(10)

        # 准备阶段
        progress.update(task, description="设置监控...")
        handle_grid_preparation(config)

        # 故障注入
        progress.update(task, description="注入故障...")
        run_functional_script("inject", "clab-ospfv3-grid5x5", "--max-executions", "2",
                             "-t", "link", "--min-interval", "20", "--max-interval", "30",
                             description="执行故障注入")

        # 收集阶段
        progress.update(task, description="收集数据...")
        handle_grid_collection(config)

        progress.update(task, description="✅ Grid工作流完成")

    console.print("[bold green]🎉 完整Grid工作流执行完成！[/bold green]")


def handle_full_torus_workflow(config: Config) -> None:
    """处理完整Torus工作流 (模式 -1)"""
    console.print(Panel.fit("🚀 运行完整Torus工作流", style="bold green"))

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:

        # 清理并重新生成
        task = progress.add_task("清理旧数据...", total=None)
        remove_directory_if_exists("ospfv3_torus5x5")
        progress.update(task, description="生成拓扑...")
        handle_generate_topologies(config)

        # 部署
        progress.update(task, description="部署容器...")
        deploy_cmd = build_containerlab_command("containerlab deploy -t ospfv3_torus5x5/ --reconfigure", config.runtime)
        run_command(deploy_cmd, description="部署Torus拓扑")
        progress.update(task, description="等待容器启动...")
        time.sleep(10)

        # 准备阶段
        progress.update(task, description="设置监控...")
        handle_torus_preparation(config)

        # 故障注入
        progress.update(task, description="注入故障...")
        run_functional_script("inject", "clab-ospfv3-torus5x5", "--max-executions", "2",
                             "-t", "link", "--min-interval", "20", "--max-interval", "30",
                             description="执行故障注入")

        # 收集阶段
        progress.update(task, description="收集数据...")
        handle_torus_collection(config)

        progress.update(task, description="✅ Torus工作流完成")

    console.print("[bold green]🎉 完整Torus工作流执行完成！[/bold green]")


def handle_generate_topologies(config: Config) -> None:
    """处理生成拓扑 (模式 0)"""
    console.print(Panel.fit("🏗️  生成网络拓扑", style="bold blue"))

    size_str = str(config.size)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("生成Grid拓扑...", total=None)
        run_functional_script("generate_ospfv3_grid", "--size", size_str, "--yes",
                             description=f"生成 {config.size}x{config.size} Grid拓扑")

        progress.update(task, description="生成Torus拓扑...")
        run_functional_script("generate_ospfv3_torus", "--size", size_str, "--yes",
                             description=f"生成 {config.size}x{config.size} Torus拓扑")

        progress.update(task, description="✅ 拓扑生成完成")

    console.print("[bold green]🎉 拓扑生成成功！[/bold green]")


def handle_torus_preparation(config: Config) -> None:
    """处理Torus准备阶段 (模式 1)"""
    # 拓扑类型验证已在 validate_config 中完成，这里不需要重复检查
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
        run_functional_script("execute_on_torus", prefix, size_str, "rm -rf /opt/scripts", "--detach", "--execute",
                             description="清理容器中的脚本目录")

        # 复制脚本
        progress.update(task, description="复制监控脚本...")
        run_functional_script("copy_to_containers", prefix, size_str, "./scripts", "/opt/scripts", "--execute",
                             description="复制脚本到容器")

        # 启动监控
        progress.update(task, description="启动fping监控...")
        fping_cmd = r'sudo sh -c "fping -6 -l -o -p 10 -r 0 -e -t 160 -Q 1 2001:db8:1000:0000:0003:0002::1 &> /var/log/frr/fping.log"'
        run_functional_script("execute_on_torus", prefix, size_str, fping_cmd, "--detach", "--execute",
                             description="启动fping网络监控")

        progress.update(task, description="启动收敛分析器...")
        analyzer_cmd = "/opt/scripts/ConvergenceAnalyzer --threshold 5000 --log-path /var/log/frr/route.json"
        run_functional_script("execute_on_torus", prefix, size_str, analyzer_cmd, "--detach", "--execute",
                             description="启动路由收敛分析器")

        progress.update(task, description="启动数据包捕获...")
        pcap_filename = f"ospfv3_{config.topology_type.value}{config.size}x{config.size}.pcap"
        tcpdump_cmd = f"tcpdump -i any -w /var/log/frr/{pcap_filename} ip6 proto 89"
        run_functional_script("execute_on_torus", prefix, size_str, tcpdump_cmd, "--detach", "--execute",
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
        run_functional_script("log2csv", config.test_dir + "/etc", f"./data/converge-ospfv3_torus{size}x{size}.csv",
                             description="转换收敛日志为CSV")

        progress.update(task, description="生成fping数据CSV...")
        run_functional_script("fping2csv", config.test_dir + "/etc", f"./data/fping-ospfv3_torus{size}x{size}.csv",
                             description="转换fping日志为CSV")

        # 生成图表
        progress.update(task, description="生成收敛分析图表...")
        run_uv_command(f"setup/draw/converge_draw_{size}x{size}.py", f"./data/converge-ospfv3_torus{size}x{size}.csv", f"./results/converge-ospfv3_torus{size}x{size}.png",
                      description="生成收敛分析热力图")

        progress.update(task, description="生成中断分析图表...")
        run_uv_command(f"setup/draw/fping_outage_draw_{size}x{size}.py", f"./data/fping-ospfv3_torus{size}x{size}.csv", f"./results/fping-ospfv3_torus{size}x{size}.png",
                      description="生成中断分析热力图")

        progress.update(task, description="✅ Torus数据收集完成")

    console.print("[bold green]🎉 Torus数据收集和可视化完成！[/bold green]")


def handle_grid_preparation(config: Config) -> None:
    """处理Grid准备阶段 (模式 3)"""
    # 拓扑类型验证已在 validate_config 中完成，这里不需要重复检查
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
        run_functional_script("execute_on_torus", prefix, size_str, "rm -rf /opt/scripts", "--detach", "--execute",
                             description="清理容器中的脚本目录")

        # 复制脚本
        progress.update(task, description="复制监控脚本...")
        run_functional_script("copy_to_containers", prefix, size_str, "./scripts", "/opt/scripts", "--execute",
                             description="复制脚本到容器")

        # 启动监控
        progress.update(task, description="启动fping监控...")
        fping_cmd = r'sudo sh -c "fping -6 -l -o -p 10 -r 0 -e -t 1000 -Q 1 2001:db8:1000:0000:0003:0002::1 &> /var/log/frr/fping.log"'
        run_functional_script("execute_on_torus", prefix, size_str, fping_cmd, "--detach", "--execute",
                             description="启动fping网络监控")

        progress.update(task, description="启动收敛分析器...")
        analyzer_cmd = "/opt/scripts/ConvergenceAnalyzer --threshold 5000 --log-path /var/log/frr/route.json"
        run_functional_script("execute_on_torus", prefix, size_str, analyzer_cmd, "--detach", "--execute",
                             description="启动路由收敛分析器")

        progress.update(task, description="启动数据包捕获...")
        pcap_filename = f"ospfv3_{config.topology_type.value}{config.size}x{config.size}.pcap"
        tcpdump_cmd = f"tcpdump -i any -w /var/log/frr/{pcap_filename} ip6 proto 89"
        run_functional_script("execute_on_torus", prefix, size_str, tcpdump_cmd, "--detach", "--execute",
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
        run_functional_script("log2csv", config.test_dir + "/etc", f"./data/converge-ospfv3_grid{size}x{size}.csv",
                             description="转换收敛日志为CSV")

        progress.update(task, description="生成fping数据CSV...")
        run_functional_script("fping2csv", config.test_dir + "/etc", f"./data/fping-ospfv3_grid{size}x{size}.csv",
                             description="转换fping日志为CSV")

        # 生成图表
        progress.update(task, description="生成收敛分析图表...")
        run_uv_command(f"setup/draw/converge_draw_{size}x{size}.py", f"./data/converge-ospfv3_grid{size}x{size}.csv", f"./results/converge-ospfv3_grid{size}x{size}.png",
                      description="生成收敛分析热力图")

        progress.update(task, description="生成中断分析图表...")
        run_uv_command(f"setup/draw/fping_outage_draw_{size}x{size}.py", f"./data/fping-ospfv3_grid{size}x{size}.csv", f"./results/fping-ospfv3_grid{size}x{size}.png",
                      description="生成中断分析热力图")

        progress.update(task, description="✅ Grid数据收集完成")

    console.print("[bold green]🎉 Grid数据收集和可视化完成！[/bold green]")


def handle_emergency_recovery(config: Config) -> None:
    """处理应急恢复 (模式 5)"""
    console.print(Panel.fit("🚨 应急恢复 - 重启监控", style="bold yellow"))

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
    Mode.AUTO_WORKFLOW: None,  # 特殊处理，需要参数
    Mode.FULL_GRID: handle_full_grid_workflow,
    Mode.FULL_TORUS: handle_full_torus_workflow,
    Mode.GENERATE_TOPOLOGIES: handle_generate_topologies,
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
    torus_modes = {Mode.TORUS_PREPARATION, Mode.TORUS_COLLECTION, Mode.FULL_TORUS}
    grid_modes = {Mode.GRID_PREPARATION, Mode.GRID_COLLECTION, Mode.FULL_GRID}
    # AUTO_WORKFLOW 模式兼容所有拓扑类型

    if config.mode in torus_modes and config.topology_type != TopologyType.TORUS:
        raise ValueError(f"❌ 配置错误: 模式 {config.mode.value} 用于torus拓扑，但检测到 {config.topology_type.value}")

    if config.mode in grid_modes and config.topology_type != TopologyType.GRID:
        raise ValueError(f"❌ 配置错误: 模式 {config.mode.value} 用于grid拓扑，但检测到 {config.topology_type.value}")

    # 验证前缀格式的完整性
    if not re.match(r'^clab-ospfv3-(torus|grid)\d+x\d+$', config.prefix):
        raise ValueError(f"❌ 配置错误: 前缀格式不正确 '{config.prefix}'。期望格式: clab-ospfv3-torus5x5 或 clab-ospfv3-grid5x5")

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

    [bold]可用模式 (数字格式):[/bold]

    • [magenta]-3[/magenta] - 智能工作流 (自动检测拓扑类型并执行完整流程)
    • [red]-2[/red] - 完整Grid工作流 (重置, 生成, 部署, 监控, 收集)
    • [red]-1[/red] - 完整Torus工作流 (重置, 生成, 部署, 监控, 收集)
    • [blue]0[/blue]  - 生成拓扑 (torus和grid)
    • [green]1[/green]  - Torus准备阶段 (设置监控)
    • [green]2[/green]  - Torus收集阶段 (收集数据并生成图表)
    • [green]3[/green]  - Grid准备阶段 (设置监控)
    • [green]4[/green]  - Grid收集阶段 (收集数据并生成图表)
    • [yellow]5[/yellow]  - 应急恢复 (重启监控)

    [bold]可用模式 (字符串格式，推荐):[/bold]

    • [magenta]auto[/magenta] - 智能工作流 (自动检测拓扑类型)
    • [red]full-grid[/red] - 完整Grid工作流
    • [red]full-torus[/red] - 完整Torus工作流
    • [blue]generate[/blue] - 生成拓扑
    • [green]torus-prep[/green] - Torus准备阶段
    • [green]torus-collect[/green] - Torus收集阶段
    • [green]grid-prep[/green] - Grid准备阶段
    • [green]grid-collect[/green] - Grid收集阶段
    • [yellow]emergency[/yellow] - 应急恢复

    [bold]示例:[/bold]

    [dim]# 基础使用 - 智能工作流 (推荐)[/dim]
    • [dim]python3 auto.py clab-ospfv3-torus5x5 auto[/dim]
    • [dim]python3 auto.py clab-ospfv3-grid3x3 auto --yes[/dim]

    [dim]# 分阶段执行[/dim]
    • [dim]python3 auto.py clab-ospfv3-torus5x5 generate[/dim]
    • [dim]python3 auto.py clab-ospfv3-torus5x5 torus-prep[/dim]
    • [dim]python3 auto.py clab-ospfv3-torus5x5 torus-collect[/dim]

    [dim]# 容器运行时选择[/dim]
    • [dim]python3 auto.py clab-ospfv3-torus5x5 auto --runtime docker[/dim]
    • [dim]python3 auto.py clab-ospfv3-grid5x5 auto --runtime podman[/dim]

    [dim]# 网络延迟配置[/dim]
    • [dim]python3 auto.py clab-ospfv3-torus5x5 auto --vertical-delay 5 --horizontal-delay 10[/dim]   # 低延迟
    • [dim]python3 auto.py clab-ospfv3-grid8x8 auto --vertical-delay 50 --horizontal-delay 100[/dim]  # 高延迟

    [dim]# 组合配置示例[/dim]
    • [dim]python3 auto.py clab-ospfv3-torus10x10 auto --runtime podman --vertical-delay 25 --horizontal-delay 50 --yes[/dim]
    • [dim]python3 auto.py clab-ospfv3-grid6x6 full-grid --runtime docker --vertical-delay 15 --horizontal-delay 30 -y[/dim]

    [dim]# 数字模式 (向后兼容)[/dim]
    • [dim]python3 auto.py clab-ospfv3-torus5x5 0[/dim]    # 生成拓扑
    • [dim]python3 auto.py clab-ospfv3-grid5x5 -- -2[/dim] # 完整Grid工作流

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

        if config.mode == Mode.AUTO_WORKFLOW:
            # 智能工作流需要特殊处理
            params = collect_auto_workflow_parameters(config, yes)

            # 最终确认
            if not yes:
                console.print(f"\n[bold yellow]确认执行智能工作流吗？[/bold yellow]")
                if not Confirm.ask("继续执行"):
                    console.print("[yellow]操作已取消[/yellow]")
                    raise typer.Exit(0)

            handle_auto_workflow(config, **params)
        else:
            # 其他模式的标准处理
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
