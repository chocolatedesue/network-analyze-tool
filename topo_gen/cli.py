"""
现代化CLI入口
使用 typer 和 rich 提供优雅的命令行界面
"""

from __future__ import annotations

from typing import Optional, List
from pathlib import Path
import anyio
import sys

try:
    import typer
    from rich.console import Console
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.panel import Panel
    from rich.prompt import Confirm
except ImportError:
    print("请安装依赖: uv run -m pip install typer rich")
    sys.exit(1)

from .core.types import TopologyType
from .core.models import (
    TopologyConfig, OSPFConfig, BGPConfig, BFDConfig,
    SpecialTopologyConfig, SystemRequirements
)
from .topology.grid import validate_grid_topology
from .topology.torus import validate_torus_topology
from .topology.special import create_dm6_6_sample
from .engine import generate_topology
# 清理未使用的导入，提升可读性

# 创建应用和控制台
app = typer.Typer(
    name="ospfv3-generator",
    help="现代化OSPFv3拓扑生成器",
    add_completion=False,
    rich_markup_mode="rich"
)
console = Console()

# 全局配置
class GlobalConfig:
    verbose: bool = False
    dry_run: bool = False
    output_dir: Optional[Path] = None

global_config = GlobalConfig()

# 回调函数
def version_callback(value: bool):
    """版本回调"""
    if value:
        console.print("OSPFv3 Generator v2.0.0 - 现代化函数式架构")
        raise typer.Exit()

def verbose_callback(value: bool):
    """详细输出回调"""
    global_config.verbose = value

# 全局选项
@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None, "--version", "-v", 
        callback=version_callback, 
        help="显示版本信息"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", 
        callback=verbose_callback,
        help="详细输出"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="仅验证配置，不生成文件"
    ),
    output_dir: Optional[Path] = typer.Option(
        None, "--output-dir", "-o",
        help="输出目录"
    )
):
    """现代化OSPFv3拓扑生成器"""
    global_config.dry_run = dry_run
    global_config.output_dir = output_dir

# 验证函数
def validate_size(size: int) -> int:
    """验证网格大小"""
    if not (2 <= size <= 100):
        raise typer.BadParameter("网格大小必须在2-100之间")
    return size

def validate_as_number(as_number: int) -> int:
    """验证AS号"""
    if not (1 <= as_number <= 4294967295):
        raise typer.BadParameter("AS号必须在1-4294967295之间")
    return as_number

# 显示函数
def display_topology_info(config: TopologyConfig):
    """显示拓扑信息"""
    table = Table(title="拓扑配置信息")
    table.add_column("属性", style="cyan")
    table.add_column("值", style="green")
    
    # 处理拓扑类型显示（可能是枚举或字符串）
    topology_display = config.topology_type.upper() if isinstance(config.topology_type, str) else config.topology_type.value.upper()
    table.add_row("拓扑类型", topology_display)
    table.add_row("网格大小", f"{config.size}x{config.size}")
    table.add_row("总路由器数", str(config.total_routers))
    table.add_row("总链路数", str(config.total_links))
    table.add_row("多区域", "是" if config.multi_area else "否")
    table.add_row("启用BFD", "是" if config.enable_bfd else "否")
    table.add_row("启用BGP", "是" if config.enable_bgp else "否")
    
    if config.bgp_config:
        table.add_row("BGP AS号", str(config.bgp_config.as_number))
    
    console.print(table)

def display_system_requirements(requirements: SystemRequirements):
    """显示系统需求"""
    panel = Panel(
        f"""
[bold]系统需求[/bold]

• 最小内存: {requirements.min_memory_gb:.1f} GB
• 推荐内存: {requirements.recommended_memory_gb:.1f} GB  
• 配置生成线程: {requirements.max_workers_config}
• 文件系统线程: {requirements.max_workers_filesystem}
        """.strip(),
        title="系统需求",
        border_style="blue"
    )
    console.print(panel)

def confirm_generation(config: TopologyConfig) -> bool:
    """确认生成"""
    if global_config.dry_run:
        console.print("[yellow]干运行模式 - 仅验证配置[/yellow]")
        return True
    
    # 处理拓扑类型显示（可能是枚举或字符串）
    topology_display = config.topology_type.upper() if isinstance(config.topology_type, str) else config.topology_type.value.upper()
    return Confirm.ask(
        f"确认生成 {config.total_routers} 个路由器的 {topology_display} 拓扑？"
    )

# Grid命令
@app.command("grid")
def generate_grid(
    size: int = typer.Argument(..., help="网格大小", callback=validate_size),
    multi_area: bool = typer.Option(False, "--multi-area", help="启用多区域"),
    area_size: Optional[int] = typer.Option(None, "--area-size", help="区域大小"),
    enable_bfd: bool = typer.Option(False, "--enable-bfd", help="启用BFD"),
    enable_bgp: bool = typer.Option(False, "--enable-bgp", help="启用BGP"),
    enable_ospf6: bool = typer.Option(True, "--enable-ospf6/--disable-ospf6", help="启用OSPF6"),
    bgp_as: int = typer.Option(65000, "--bgp-as", help="BGP AS号", callback=validate_as_number),
    hello_interval: int = typer.Option(2, "--hello-interval", help="OSPF Hello间隔"),
    dead_interval: int = typer.Option(10, "--dead-interval", help="OSPF Dead间隔"),
    spf_delay: int = typer.Option(20, "--spf-delay", help="SPF延迟"),
    daemons_off: bool = typer.Option(False, "--daemons-off", help="仅关闭守护进程但仍生成配置文件"),
    bgpd_off: bool = typer.Option(False, "--bgpd-off", help="仅关闭 BGP 守护进程"),
    ospf6d_off: bool = typer.Option(False, "--ospf6d-off", help="仅关闭 OSPF6 守护进程"),
    bfdd_off: bool = typer.Option(False, "--bfdd-off", help="仅关闭 BFD 守护进程"),
    dummy_gen: List[str] = typer.Option([], "--dummy-gen", help="为指定协议生成空配置并将真实配置保存为 -bak.conf；支持: ospf6d,bgpd,bfdd；可多次传或用逗号分隔"),
    disable_logging: bool = typer.Option(False, "--disable-logging", help="禁用所有配置文件中的日志记录"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认")
):
    """生成Grid拓扑"""

    # 创建配置
    try:
        config = TopologyConfig(
            size=size,
            topology_type=TopologyType.GRID,
            multi_area=multi_area,
            area_size=area_size,
            ospf_config=OSPFConfig(
                hello_interval=hello_interval,
                dead_interval=dead_interval,
                spf_delay=spf_delay
            ) if enable_ospf6 else None,
            bgp_config=BGPConfig(as_number=bgp_as) if enable_bgp else None,
            bfd_config=BFDConfig(enabled=enable_bfd),
            daemons_off=daemons_off,
            bgpd_off=bgpd_off,
            ospf6d_off=ospf6d_off,
            bfdd_off=bfdd_off,
            dummy_gen_protocols=set(sum([s.lower().split(',') for s in dummy_gen], [])),
            disable_logging=disable_logging
        )
    except Exception as e:
        console.print(f"[red]配置验证失败: {e}[/red]")
        raise typer.Exit(1)
    
    # 验证配置
    validation_errors = validate_grid_topology(size)
    if validation_errors:
        console.print("[red]配置验证失败:[/red]")
        for error in validation_errors:
            console.print(f"  • {error}")
        raise typer.Exit(1)
    
    # 显示信息
    display_topology_info(config)
    
    # 计算系统需求
    requirements = SystemRequirements.calculate_for_topology(config)
    display_system_requirements(requirements)
    
    # 确认生成
    if not yes and not confirm_generation(config):
        console.print("[yellow]已取消[/yellow]")
        raise typer.Exit()
    
    # 生成拓扑
    if global_config.dry_run:
        console.print("[green]配置验证通过 ✓[/green]")
    else:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            _ = progress.add_task("生成Grid拓扑...", total=None)
            
            # 调用实际的生成逻辑
            result = anyio.run(generate_topology, config)
            
            if result.success:
                console.print(f"[green]Grid拓扑生成成功 ✓[/green]")
                console.print(f"输出目录: {result.output_dir}")
            else:
                console.print(f"[red]生成失败: {result.message}[/red]")
                raise typer.Exit(1)

# Torus命令
@app.command("torus")
def generate_torus(
    size: int = typer.Argument(..., help="网格大小", callback=validate_size),
    multi_area: bool = typer.Option(False, "--multi-area", help="启用多区域"),
    area_size: Optional[int] = typer.Option(None, "--area-size", help="区域大小"),
    enable_bfd: bool = typer.Option(False, "--enable-bfd", help="启用BFD"),
    enable_bgp: bool = typer.Option(False, "--enable-bgp", help="启用BGP"),
    enable_ospf6: bool = typer.Option(True, "--enable-ospf6/--disable-ospf6", help="启用OSPF6"),
    bgp_as: int = typer.Option(65000, "--bgp-as", help="BGP AS号", callback=validate_as_number),
    hello_interval: int = typer.Option(2, "--hello-interval", help="OSPF Hello间隔"),
    dead_interval: int = typer.Option(10, "--dead-interval", help="OSPF Dead间隔"),
    spf_delay: int = typer.Option(20, "--spf-delay", help="SPF延迟"),
    daemons_off: bool = typer.Option(False, "--daemons-off", help="仅关闭守护进程但仍生成配置文件"),
    bgpd_off: bool = typer.Option(False, "--bgpd-off", help="仅关闭 BGP 守护进程"),
    ospf6d_off: bool = typer.Option(False, "--ospf6d-off", help="仅关闭 OSPF6 守护进程"),
    bfdd_off: bool = typer.Option(False, "--bfdd-off", help="仅关闭 BFD 守护进程"),
    dummy_gen: List[str] = typer.Option([], "--dummy-gen", help="为指定协议生成空配置并将真实配置保存为 -bak.conf；支持: ospf6d,bgpd,bfdd；可多次传或用逗号分隔"),
    disable_logging: bool = typer.Option(False, "--disable-logging", help="禁用所有配置文件中的日志记录"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认")
):
    """生成Torus拓扑"""

    # 创建配置
    try:
        config = TopologyConfig(
            size=size,
            topology_type=TopologyType.TORUS,
            multi_area=multi_area,
            area_size=area_size,
            ospf_config=OSPFConfig(
                hello_interval=hello_interval,
                dead_interval=dead_interval,
                spf_delay=spf_delay
            ) if enable_ospf6 else None,
            bgp_config=BGPConfig(as_number=bgp_as) if enable_bgp else None,
            bfd_config=BFDConfig(enabled=enable_bfd),
            daemons_off=daemons_off,
            bgpd_off=bgpd_off,
            ospf6d_off=ospf6d_off,
            bfdd_off=bfdd_off,
            dummy_gen_protocols=set(sum([s.lower().split(',') for s in dummy_gen], [])),
            disable_logging=disable_logging
        )
    except Exception as e:
        console.print(f"[red]配置验证失败: {e}[/red]")
        raise typer.Exit(1)
    
    # 验证配置
    validation_errors = validate_torus_topology(size)
    if validation_errors:
        console.print("[red]配置验证失败:[/red]")
        for error in validation_errors:
            console.print(f"  • {error}")
        raise typer.Exit(1)
    
    # 显示信息
    display_topology_info(config)
    
    # 计算系统需求
    requirements = SystemRequirements.calculate_for_topology(config)
    display_system_requirements(requirements)
    
    # 确认生成
    if not yes and not confirm_generation(config):
        console.print("[yellow]已取消[/yellow]")
        raise typer.Exit()
    
    # 生成拓扑
    if global_config.dry_run:
        console.print("[green]配置验证通过 ✓[/green]")
    else:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            _ = progress.add_task("生成Torus拓扑...", total=None)
            
            # 调用实际的生成逻辑
            result = anyio.run(generate_topology, config)
            
            if result.success:
                console.print(f"[green]Torus拓扑生成成功 ✓[/green]")
                console.print(f"输出目录: {result.output_dir}")
            else:
                console.print(f"[red]生成失败: {result.message}[/red]")
                raise typer.Exit(1)

# Special命令
@app.command("special")
def generate_special(
    base_topology: TopologyType = typer.Option(TopologyType.TORUS, "--base-topology", help="基础拓扑类型"),
    include_base: bool = typer.Option(True, "--include-base/--no-include-base", help="包含基础连接"),
    enable_bgp: bool = typer.Option(False, "--enable-bgp", help="启用BGP"),
    enable_ospf6: bool = typer.Option(True, "--enable-ospf6/--disable-ospf6", help="启用OSPF6"),
    bgp_as: int = typer.Option(65000, "--bgp-as", help="BGP基础AS号", callback=validate_as_number),
    hello_interval: int = typer.Option(2, "--hello-interval", help="OSPF Hello间隔"),
    dead_interval: int = typer.Option(10, "--dead-interval", help="OSPF Dead间隔"),
    spf_delay: int = typer.Option(20, "--spf-delay", help="SPF延迟"),
    enable_bfd: bool = typer.Option(False, "--enable-bfd", help="启用BFD"),
    daemons_off: bool = typer.Option(False, "--daemons-off", help="仅关闭守护进程但仍生成配置文件"),
    bgpd_off: bool = typer.Option(False, "--bgpd-off", help="仅关闭 BGP 守护进程"),
    ospf6d_off: bool = typer.Option(False, "--ospf6d-off", help="仅关闭 OSPF6 守护进程"),
    bfdd_off: bool = typer.Option(False, "--bfdd-off", help="仅关闭 BFD 守护进程"),
    dummy_gen: List[str] = typer.Option([], "--dummy-gen", help="为指定协议生成空配置并将真实配置保存为 -bak.conf；支持: ospf6d,bgpd,bfdd；可多次传或用逗号分隔"),
    disable_logging: bool = typer.Option(False, "--disable-logging", help="禁用所有配置文件中的日志记录"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认")
):
    """生成Special拓扑（6x6 DM示例）"""
    
    # 创建Special配置
    special_config = create_dm6_6_sample()
    # 由于Pydantic模型是frozen的，需要创建新实例
    special_config = SpecialTopologyConfig(
        source_node=special_config.source_node,
        dest_node=special_config.dest_node,
        gateway_nodes=special_config.gateway_nodes,
        internal_bridge_edges=special_config.internal_bridge_edges,
        torus_bridge_edges=special_config.torus_bridge_edges,
        base_topology=base_topology,
        include_base_connections=include_base
    )
    
    # 创建拓扑配置
    try:
        config = TopologyConfig(
            size=6,
            topology_type=TopologyType.SPECIAL,
            multi_area=False,
            ospf_config=OSPFConfig(
                hello_interval=hello_interval,
                dead_interval=dead_interval,
                spf_delay=spf_delay
            ) if enable_ospf6 else None,
            bgp_config=BGPConfig(as_number=bgp_as) if enable_bgp else None,
            bfd_config=BFDConfig(enabled=enable_bfd),
            daemons_off=daemons_off,
            bgpd_off=bgpd_off,
            ospf6d_off=ospf6d_off,
            bfdd_off=bfdd_off,
            dummy_gen_protocols=set(sum([s.lower().split(',') for s in dummy_gen], [])),
            disable_logging=disable_logging,
            special_config=special_config
        )
    except Exception as e:
        console.print(f"[red]配置验证失败: {e}[/red]")
        raise typer.Exit(1)
    
    # 显示信息
    display_topology_info(config)
    
    # 显示Special配置详情
    special_table = Table(title="Special拓扑详情")
    special_table.add_column("属性", style="cyan")
    special_table.add_column("值", style="green")
    
    # 处理基础拓扑显示（可能是枚举或字符串）
    base_topology_display = base_topology.upper() if isinstance(base_topology, str) else base_topology.value.upper()
    special_table.add_row("基础拓扑", base_topology_display)
    special_table.add_row("包含基础连接", "是" if include_base else "否")
    special_table.add_row("源节点", str(special_config.source_node))
    special_table.add_row("目标节点", str(special_config.dest_node))
    special_table.add_row("网关节点数", str(len(special_config.gateway_nodes)))
    special_table.add_row("内部桥接边数", str(len(special_config.internal_bridge_edges)))
    special_table.add_row("Torus桥接边数", str(len(special_config.torus_bridge_edges)))
    
    console.print(special_table)
    
    # 计算系统需求
    requirements = SystemRequirements.calculate_for_topology(config)
    display_system_requirements(requirements)
    
    # 确认生成
    if not yes and not confirm_generation(config):
        console.print("[yellow]已取消[/yellow]")
        raise typer.Exit()
    
    # 生成拓扑
    if global_config.dry_run:
        console.print("[green]配置验证通过 ✓[/green]")
    else:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            _ = progress.add_task("生成Special拓扑...", total=None)
            
            # 调用实际的生成逻辑
            result = anyio.run(generate_topology, config)
            
            if result.success:
                console.print(f"[green]Special拓扑生成成功 ✓[/green]")
                console.print(f"输出目录: {result.output_dir}")
            else:
                console.print(f"[red]生成失败: {result.message}[/red]")
                raise typer.Exit(1)





# 主入口
if __name__ == "__main__":
    app()
