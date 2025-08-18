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
    import yaml
except ImportError:
    print("请安装依赖: uv run -m pip install typer rich")
    sys.exit(1)

from .core.types import TopologyType
from .config.defaults import (
    ENABLE_DEFAULT_OSPF6,
    ENABLE_DEFAULT_ISIS,
    ENABLE_DEFAULT_BGP,
    ENABLE_DEFAULT_BFD,
    OSPF_DEFAULT_HELLO_INTERVAL,
    OSPF_DEFAULT_DEAD_INTERVAL,
    OSPF_DEFAULT_SPF_DELAY_MS,
    OSPF_DEFAULT_LSA_MIN_ARRIVAL_MS,
    OSPF_DEFAULT_MAXIMUM_PATHS,
    ISIS_DEFAULT_HELLO_INTERVAL,
    ISIS_DEFAULT_HELLO_MULTIPLIER,
    ISIS_DEFAULT_LSP_GEN_INTERVAL,
    ISIS_DEFAULT_METRIC,
    ISIS_DEFAULT_VERTICAL_METRIC,
    ISIS_DEFAULT_HORIZONTAL_METRIC,
    ISIS_DEFAULT_PRIORITY,
    ISIS_DEFAULT_SPF_INTERVAL,
    ISIS_DEFAULT_LSP_REFRESH_INTERVAL,
    ISIS_DEFAULT_MAX_LSP_LIFETIME,
    ISIS_DEFAULT_CSNP_INTERVAL,
    ISIS_DEFAULT_PSNP_INTERVAL,
    ISIS_DEFAULT_ENABLE_WIDE_METRICS,
    ISIS_DEFAULT_SPF_INIT_DELAY_MS,
    ISIS_DEFAULT_SPF_SHORT_DELAY_MS,
    ISIS_DEFAULT_SPF_LONG_DELAY_MS,
    ISIS_DEFAULT_SPF_HOLDDOWN_MS,
    ISIS_DEFAULT_SPF_TIME_TO_LEARN_MS,
    ISIS_DEFAULT_NET_ADDRESS,
    BGP_DEFAULT_ASN,
)
from .core.models import (
    TopologyConfig, OSPFConfig, ISISConfig, BGPConfig, BFDConfig,
    SpecialTopologyConfig, SystemRequirements
)
from .topology.grid import validate_grid_topology
from .topology.torus import validate_torus_topology
from .engine import generate_topology
from .config.settings import AppSettings
from .utils.logging import configure_logging, get_logger

# 创建应用和控制台
app = typer.Typer(
    name="ospfv3-generator",
    help="现代化OSPFv3拓扑生成器",
    add_completion=False,
    rich_markup_mode="rich"
)
console = Console()

logger = get_logger(__name__)

# 全局配置（简单数据容器）
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
    ),
    config_file: Optional[Path] = typer.Option(
        None, "--config-file", "-c", help="从配置文件加载设置 (YAML/JSON)"
    ),
):
    """现代化OSPFv3拓扑生成器"""
    # 初始化日志
    configure_logging(verbose)
    logger.info("cli_started", verbose=verbose)

    # 记录全局配置
    global_config.dry_run = dry_run
    global_config.output_dir = output_dir

    # 读取配置文件（若提供）并初始化全局 AppSettings（供 from-config 命令使用）
    global app_settings
    if config_file and config_file.exists():
        try:
            file_data = yaml.safe_load(config_file.read_text()) or {}
        except Exception as e:
            console.print(f"[red]读取配置文件失败: {e}[/red]")
            raise typer.Exit(1)
        app_settings = AppSettings(**file_data)
    else:
        app_settings = AppSettings()

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
    logger.info(
        "topology_info",
        topology_type=topology_display,
        size=config.size,
        total_routers=config.total_routers,
        total_links=config.total_links,
        multi_area=config.multi_area,
        enable_bfd=config.enable_bfd,
        enable_bgp=config.enable_bgp,
    )

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
    
    topology_display = config.topology_type.upper() if isinstance(config.topology_type, str) else config.topology_type.value.upper()
    return Confirm.ask(
        f"确认生成 {config.total_routers} 个路由器的 {topology_display} 拓扑？"
    )

def _run_with_progress(task_desc: str, config: TopologyConfig):
    if global_config.dry_run:
        console.print("[green]配置验证通过 ✓[/green]")
        logger.info("dry_run_passed")
        return
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        _ = progress.add_task(task_desc, total=None)
        logger.info("generation_started", task=task_desc)
        result = anyio.run(generate_topology, config)
        if result.success:
            console.print("[green]生成成功 ✓[/green]")
            if result.output_dir:
                console.print(f"输出目录: {result.output_dir}")
            logger.info("generation_succeeded", output_dir=str(result.output_dir))
        else:
            console.print(f"[red]生成失败: {result.message}[/red]")
            logger.error("generation_failed", message=result.message)
            raise typer.Exit(1)

# 统一生成命令 - 支持 Grid 和 Torus 拓扑
@app.command("generate")
def generate_topology_command(
    topology_type: TopologyType = typer.Argument(..., help="拓扑类型 (grid/torus)"),
    size: int = typer.Argument(..., help="网格大小", callback=validate_size),
    # 基础拓扑选项
    multi_area: bool = typer.Option(False, "--multi-area", help="启用多区域"),
    area_size: Optional[int] = typer.Option(None, "--area-size", help="区域大小"),
    # 协议启用选项
    enable_ospf6: bool = typer.Option(ENABLE_DEFAULT_OSPF6, "--enable-ospf6/--disable-ospf6", help="启用OSPF6"),
    enable_isis: bool = typer.Option(ENABLE_DEFAULT_ISIS, "--enable-isis", help="启用ISIS"),
    enable_bgp: bool = typer.Option(ENABLE_DEFAULT_BGP, "--enable-bgp", help="启用BGP"),
    enable_bfd: bool = typer.Option(ENABLE_DEFAULT_BFD, "--enable-bfd", help="启用BFD"),
    # OSPF6 配置选项
    hello_interval: int = typer.Option(OSPF_DEFAULT_HELLO_INTERVAL, "--hello-interval", help="OSPF Hello间隔(秒)"),
    dead_interval: int = typer.Option(OSPF_DEFAULT_DEAD_INTERVAL, "--dead-interval", help="OSPF Dead间隔(秒)"),
    spf_delay: int = typer.Option(OSPF_DEFAULT_SPF_DELAY_MS, "--spf-delay", help="SPF延迟(ms)"),
    lsa_min_arrival: int = typer.Option(OSPF_DEFAULT_LSA_MIN_ARRIVAL_MS, "--lsa-min-arrival", help="OSPF LSA最小到达间隔(毫秒)"),
    maximum_paths: int = typer.Option(OSPF_DEFAULT_MAXIMUM_PATHS, "--maximum-paths", help="OSPF ECMP最大路径数 (默认: 1)"),
    # ISIS 配置选项
    isis_fast_convergence: bool = typer.Option(False, "--isis-fast-convergence", help="ISIS快速收敛模式(hello=1s,multiplier=5,lsp-gen=2s)"),
    isis_hello_interval: int = typer.Option(ISIS_DEFAULT_HELLO_INTERVAL, "--isis-hello-interval", help="ISIS Hello间隔(秒)"),
    isis_hello_multiplier: int = typer.Option(ISIS_DEFAULT_HELLO_MULTIPLIER, "--isis-hello-multiplier", help="ISIS Hello倍数器"),
    isis_lsp_gen_interval: int = typer.Option(ISIS_DEFAULT_LSP_GEN_INTERVAL, "--isis-lsp-gen-interval", help="ISIS LSP生成间隔(秒)"),
    isis_metric: int = typer.Option(ISIS_DEFAULT_METRIC, "--isis-metric", help="ISIS接口度量值 (向后兼容)"),
    isis_vertical_metric: int = typer.Option(ISIS_DEFAULT_VERTICAL_METRIC, "--isis-vertical-metric", help="ISIS纵向(南北)接口度量值"),
    isis_horizontal_metric: int = typer.Option(ISIS_DEFAULT_HORIZONTAL_METRIC, "--isis-horizontal-metric", help="ISIS横向(东西)接口度量值"),
    isis_priority: int = typer.Option(ISIS_DEFAULT_PRIORITY, "--isis-priority", help="ISIS DIS选举优先级"),
    isis_spf_interval: int = typer.Option(ISIS_DEFAULT_SPF_INTERVAL, "--isis-spf-interval", help="ISIS SPF计算间隔(秒)"),
    isis_lsp_refresh_interval: int = typer.Option(ISIS_DEFAULT_LSP_REFRESH_INTERVAL, "--isis-lsp-refresh-interval", help="ISIS LSP刷新间隔(秒)"),
    isis_max_lsp_lifetime: int = typer.Option(ISIS_DEFAULT_MAX_LSP_LIFETIME, "--isis-max-lsp-lifetime", help="ISIS LSP最大生存时间(秒)"),
    isis_csnp_interval: int = typer.Option(ISIS_DEFAULT_CSNP_INTERVAL, "--isis-csnp-interval", help="ISIS CSNP间隔(秒)"),
    isis_psnp_interval: int = typer.Option(ISIS_DEFAULT_PSNP_INTERVAL, "--isis-psnp-interval", help="ISIS PSNP间隔(秒)"),
    isis_enable_wide_metrics: bool = typer.Option(ISIS_DEFAULT_ENABLE_WIDE_METRICS, "--isis-enable-wide-metrics/--isis-disable-wide-metrics", help="启用ISIS wide度量模式"),
    # ISIS IETF SPF delay controls (ms)
    isis_spf_init_delay: int = typer.Option(ISIS_DEFAULT_SPF_INIT_DELAY_MS, "--isis-spf-init-delay", help="ISIS SPF IETF 初始延迟(毫秒)"),
    isis_spf_short_delay: int = typer.Option(ISIS_DEFAULT_SPF_SHORT_DELAY_MS, "--isis-spf-short-delay", help="ISIS SPF IETF 短延迟(毫秒)"),
    isis_spf_long_delay: int = typer.Option(ISIS_DEFAULT_SPF_LONG_DELAY_MS, "--isis-spf-long-delay", help="ISIS SPF IETF 长延迟(毫秒)"),
    isis_spf_holddown: int = typer.Option(ISIS_DEFAULT_SPF_HOLDDOWN_MS, "--isis-spf-holddown", help="ISIS SPF IETF 抑制(毫秒)"),
    isis_spf_time_to_learn: int = typer.Option(ISIS_DEFAULT_SPF_TIME_TO_LEARN_MS, "--isis-spf-time-to-learn", help="ISIS SPF IETF 学习时间(毫秒)"),
    # BGP 配置选项
    bgp_as: int = typer.Option(BGP_DEFAULT_ASN, "--bgp-as", help="BGP AS号", callback=validate_as_number),
    # 守护进程控制选项
    daemons_off: bool = typer.Option(False, "--daemons-off", help="仅关闭守护进程但仍生成配置文件"),
    bgpd_off: bool = typer.Option(False, "--bgpd-off", help="仅关闭 BGP 守护进程"),
    ospf6d_off: bool = typer.Option(False, "--ospf6d-off", help="仅关闭 OSPF6 守护进程"),
    isisd_off: bool = typer.Option(False, "--isisd-off", help="仅关闭 ISIS 守护进程"),
    bfdd_off: bool = typer.Option(False, "--bfdd-off", help="仅关闭 BFD 守护进程"),
    dummy_gen: List[str] = typer.Option([], "--dummy-gen", help="为指定协议生成空配置并将真实配置保存为 -bak.conf；支持: ospf6d,isisd,bgpd,bfdd；可多次传或用逗号分隔"),
    disable_logging: bool = typer.Option(False, "--disable-logging", help="禁用所有配置文件中的日志记录"),
    # 控制选项
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认")
):
    """生成拓扑 (Grid 或 Torus)
    
    Examples:
      generate grid 5          # 生成 5x5 Grid 拓扑
      generate torus 4         # 生成 4x4 Torus 拓扑  
      generate grid 3 --enable-isis  # 启用 ISIS 的 Grid 拓扑
    """

    # 创建配置
    try:
        config = TopologyConfig(
            size=size,
            topology_type=topology_type,
            multi_area=multi_area,
            area_size=area_size,
            ospf_config=OSPFConfig(
                hello_interval=hello_interval,
                dead_interval=dead_interval,
                spf_delay=spf_delay,
                lsa_min_arrival=lsa_min_arrival,
                maximum_paths=maximum_paths,
            ) if enable_ospf6 else None,
            isis_config=ISISConfig(
                net_address=ISIS_DEFAULT_NET_ADDRESS,
                hello_interval=1 if isis_fast_convergence else isis_hello_interval,
                hello_multiplier=5 if isis_fast_convergence else isis_hello_multiplier,
                lsp_gen_interval=2 if isis_fast_convergence else isis_lsp_gen_interval,
                isis_metric=isis_metric,
                isis_vertical_metric=isis_vertical_metric,
                isis_horizontal_metric=isis_horizontal_metric,
                priority=isis_priority,
                spf_interval=isis_spf_interval,
                lsp_refresh_interval=isis_lsp_refresh_interval,
                max_lsp_lifetime=isis_max_lsp_lifetime,
                csnp_interval=isis_csnp_interval,
                psnp_interval=isis_psnp_interval,
                enable_wide_metrics=isis_enable_wide_metrics,
                spf_init_delay_ms=isis_spf_init_delay,
                spf_short_delay_ms=isis_spf_short_delay,
                spf_long_delay_ms=isis_spf_long_delay,
                spf_holddown_ms=isis_spf_holddown,
                spf_time_to_learn_ms=isis_spf_time_to_learn,
                three_way_handshake=True,
            ) if enable_isis else None,
            bgp_config=BGPConfig(as_number=bgp_as) if enable_bgp else None,
            bfd_config=BFDConfig(enabled=enable_bfd),
            daemons_off=daemons_off,
            bgpd_off=bgpd_off,
            ospf6d_off=ospf6d_off,
            isisd_off=isisd_off,
            bfdd_off=bfdd_off,
            dummy_gen_protocols=set(sum([s.lower().split(',') for s in dummy_gen], [])),
            disable_logging=disable_logging
        )
    except Exception as e:
        console.print(f"[red]配置验证失败: {e}[/red]")
        raise typer.Exit(1)
    
    # 验证配置
    if topology_type == TopologyType.GRID:
        validation_errors = validate_grid_topology(size)
    elif topology_type == TopologyType.TORUS:
        validation_errors = validate_torus_topology(size)
    else:
        validation_errors = []
        
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
    topology_name = topology_type.value.title() if hasattr(topology_type, 'value') else str(topology_type).title()
    _run_with_progress(f"生成{topology_name}拓扑...", config)

# special 子命令注册（从独立模块导入以保持主 CLI 简洁）
from .cli_special import generate_special  # noqa: E402
app.command("special")(generate_special)


# 从配置文件/环境生成命令
@app.command("from-config")
def generate_from_config(
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认")
):
    """基于配置文件/环境变量生成拓扑。

    优先级：命令行（仅本命令的 --yes） > 配置文件内容 > 环境变量 > 默认值。
    使用 --config-file 指定文件（支持 YAML/JSON）。
    """

    # 构造 TopologyConfig
    try:
        topo_type = app_settings.topology
        ospf_cfg = OSPFConfig(
            hello_interval=app_settings.hello_interval,
            dead_interval=app_settings.dead_interval,
            spf_delay=app_settings.spf_delay,
            lsa_min_arrival=app_settings.lsa_min_arrival,
            maximum_paths=app_settings.maximum_paths,
        ) if app_settings.enable_ospf6 else None

        isis_cfg = ISISConfig(
            net_address=ISIS_DEFAULT_NET_ADDRESS,
            hello_interval=getattr(app_settings, 'isis_hello_interval', 1),
            hello_multiplier=getattr(app_settings, 'isis_hello_multiplier', 5),
            lsp_gen_interval=getattr(app_settings, 'isis_lsp_gen_interval', 2),
            isis_metric=getattr(app_settings, 'isis_metric', 10),
            isis_vertical_metric=getattr(app_settings, 'isis_vertical_metric', 10),
            isis_horizontal_metric=getattr(app_settings, 'isis_horizontal_metric', 20),
            priority=getattr(app_settings, 'isis_priority', 64),
            spf_interval=getattr(app_settings, 'isis_spf_interval', 2),
            spf_init_delay_ms=getattr(app_settings, 'isis_spf_init_delay', 0),
            spf_short_delay_ms=getattr(app_settings, 'isis_spf_short_delay', 200),
            spf_long_delay_ms=getattr(app_settings, 'isis_spf_long_delay', 5000),
            spf_holddown_ms=getattr(app_settings, 'isis_spf_holddown', 800),
            spf_time_to_learn_ms=getattr(app_settings, 'isis_spf_time_to_learn', 5000),
            lsp_refresh_interval=getattr(app_settings, 'isis_lsp_refresh_interval', 900),
            max_lsp_lifetime=getattr(app_settings, 'isis_max_lsp_lifetime', 1200),
            csnp_interval=getattr(app_settings, 'isis_csnp_interval', 10),
            psnp_interval=getattr(app_settings, 'isis_psnp_interval', 2),
            enable_wide_metrics=getattr(app_settings, 'isis_enable_wide_metrics', True),
        ) if app_settings.enable_isis else None
        bgp_cfg = BGPConfig(as_number=app_settings.bgp_as) if app_settings.enable_bgp else None
        bfd_cfg = BFDConfig(enabled=app_settings.enable_bfd)

        config = TopologyConfig(
            size=app_settings.size,
            topology_type=topo_type,
            multi_area=app_settings.multi_area,
            area_size=app_settings.area_size,
            ospf_config=ospf_cfg,
            isis_config=isis_cfg,
            bgp_config=bgp_cfg,
            bfd_config=bfd_cfg,
            daemons_off=app_settings.daemons_off,
            bgpd_off=app_settings.bgpd_off,
            ospf6d_off=app_settings.ospf6d_off,
            isisd_off=app_settings.isisd_off,
            bfdd_off=app_settings.bfdd_off,
            dummy_gen_protocols=app_settings.dummy_gen_protocols,
            disable_logging=app_settings.disable_logging,
            output_dir=app_settings.output_dir,
        )
    except Exception as e:
        console.print(f"[red]配置验证失败: {e}[/red]")
        raise typer.Exit(1)

    # 展示信息与系统需求
    display_topology_info(config)
    requirements = SystemRequirements.calculate_for_topology(config)
    display_system_requirements(requirements)

    # 确认
    if not yes and not confirm_generation(config):
        console.print("[yellow]已取消[/yellow]")
        raise typer.Exit()

    # 生成
    task_desc = f"生成{(config.topology_type.value if hasattr(config.topology_type, 'value') else str(config.topology_type)).upper()}拓扑..."
    _run_with_progress(task_desc, config)





# 主入口
if __name__ == "__main__":
    app()
