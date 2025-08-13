"""
Special topology CLI commands extracted from the main CLI.

This keeps topo_gen/cli.py focused on common commands while preserving
the same behavior for the `special` command.
"""

from __future__ import annotations

from typing import List

import sys

try:
    import typer
    from rich.table import Table
except ImportError:
    print("请安装依赖: uv run -m pip install typer rich")
    sys.exit(1)

from .core.types import TopologyType
from .core.models import (
    TopologyConfig,
    OSPFConfig,
    ISISConfig,
    BGPConfig,
    BFDConfig,
    SpecialTopologyConfig,
    SystemRequirements,
)
from .topology.special import create_dm6_6_sample


def generate_special(
    base_topology: TopologyType = typer.Option(TopologyType.TORUS, "--base-topology", help="基础拓扑类型"),
    include_base: bool = typer.Option(True, "--include-base/--no-include-base", help="包含基础连接"),
    # 协议启用选项
    enable_ospf6: bool = typer.Option(True, "--enable-ospf6/--disable-ospf6", help="启用OSPF6"),
    enable_isis: bool = typer.Option(False, "--enable-isis", help="启用ISIS"),
    enable_bgp: bool = typer.Option(False, "--enable-bgp", help="启用BGP"),
    enable_bfd: bool = typer.Option(False, "--enable-bfd", help="启用BFD"),
    # OSPF6 配置
    hello_interval: int = typer.Option(2, "--hello-interval", help="OSPF Hello间隔(秒)"),
    dead_interval: int = typer.Option(10, "--dead-interval", help="OSPF Dead间隔(秒)"),
    spf_delay: int = typer.Option(20, "--spf-delay", help="SPF延迟(ms)"),
    lsa_min_arrival: int = typer.Option(1000, "--lsa-min-arrival", help="OSPF LSA最小到达间隔(毫秒)"),
    maximum_paths: int = typer.Option(1, "--maximum-paths", help="OSPF ECMP最大路径数"),
    # ISIS 配置
    isis_fast_convergence: bool = typer.Option(False, "--isis-fast-convergence", help="ISIS快速收敛模式(hello=1s,multiplier=5,lsp-gen=2s)"),
    isis_hello_interval: int = typer.Option(1, "--isis-hello-interval", help="ISIS Hello间隔(秒)"),
    isis_hello_multiplier: int = typer.Option(5, "--isis-hello-multiplier", help="ISIS Hello倍数器"),
    isis_lsp_gen_interval: int = typer.Option(2, "--isis-lsp-gen-interval", help="ISIS LSP生成间隔(秒)"),
    isis_metric: int = typer.Option(10, "--isis-metric", help="ISIS接口度量值 (向后兼容)"),
    isis_vertical_metric: int = typer.Option(10, "--isis-vertical-metric", help="ISIS纵向(南北)接口度量值"),
    isis_horizontal_metric: int = typer.Option(20, "--isis-horizontal-metric", help="ISIS横向(东西)接口度量值"),
    isis_priority: int = typer.Option(64, "--isis-priority", help="ISIS DIS选举优先级"),
    isis_spf_interval: int = typer.Option(2, "--isis-spf-interval", help="ISIS SPF计算间隔(秒)"),
    isis_lsp_refresh_interval: int = typer.Option(900, "--isis-lsp-refresh-interval", help="ISIS LSP刷新间隔(秒)"),
    isis_max_lsp_lifetime: int = typer.Option(1200, "--isis-max-lsp-lifetime", help="ISIS LSP最大生存时间(秒)"),
    isis_csnp_interval: int = typer.Option(10, "--isis-csnp-interval", help="ISIS CSNP间隔(秒)"),
    isis_psnp_interval: int = typer.Option(2, "--isis-psnp-interval", help="ISIS PSNP间隔(秒)"),
    isis_enable_wide_metrics: bool = typer.Option(True, "--isis-enable-wide-metrics/--isis-disable-wide-metrics", help="启用ISIS wide度量模式"),
    # ISIS IETF SPF delay controls (ms)
    isis_spf_init_delay: int = typer.Option(50, "--isis-spf-init-delay", help="ISIS SPF IETF 初始延迟(毫秒)"),
    isis_spf_short_delay: int = typer.Option(200, "--isis-spf-short-delay", help="ISIS SPF IETF 短延迟(毫秒)"),
    isis_spf_long_delay: int = typer.Option(5000, "--isis-spf-long-delay", help="ISIS SPF IETF 长延迟(毫秒)"),
    isis_spf_holddown: int = typer.Option(800, "--isis-spf-holddown", help="ISIS SPF IETF 抑制(毫秒)"),
    isis_spf_time_to_learn: int = typer.Option(5000, "--isis-spf-time-to-learn", help="ISIS SPF IETF 学习时间(毫秒)"),
    # BGP 配置
    bgp_as: int = typer.Option(65000, "--bgp-as", help="BGP AS号"),
    # 守护进程控制
    daemons_off: bool = typer.Option(False, "--daemons-off", help="仅关闭守护进程但仍生成配置文件"),
    bgpd_off: bool = typer.Option(False, "--bgpd-off", help="仅关闭 BGP 守护进程"),
    ospf6d_off: bool = typer.Option(False, "--ospf6d-off", help="仅关闭 OSPF6 守护进程"),
    isisd_off: bool = typer.Option(False, "--isisd-off", help="仅关闭 ISIS 守护进程"),
    bfdd_off: bool = typer.Option(False, "--bfdd-off", help="仅关闭 BFD 守护进程"),
    dummy_gen: List[str] = typer.Option([], "--dummy-gen", help="为指定协议生成空配置并将真实配置保存为 -bak.conf；支持: ospf6d,isisd,bgpd,bfdd；可多次传或用逗号分隔"),
    disable_logging: bool = typer.Option(False, "--disable-logging", help="禁用所有配置文件中的日志记录"),
    # 控制
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
):
    """生成Special拓扑（6x6 DM示例）。"""

    # 延迟导入以避免 cli <-> cli_special 的循环依赖
    from .cli import (
        console,
        display_topology_info,
        display_system_requirements,
        confirm_generation,
        _run_with_progress,
        validate_as_number,  # 保持与主命令一致的验证
    )

    # 额外验证（与主 CLI 一致）
    validate_as_number(bgp_as)

    # 构造 Special 配置
    base_special = create_dm6_6_sample()
    special_config = SpecialTopologyConfig(
        source_node=base_special.source_node,
        dest_node=base_special.dest_node,
        gateway_nodes=base_special.gateway_nodes,
        internal_bridge_edges=base_special.internal_bridge_edges,
        torus_bridge_edges=base_special.torus_bridge_edges,
        base_topology=base_topology,
        include_base_connections=include_base,
    )

    # 组装完整 TopologyConfig
    try:
        config = TopologyConfig(
            size=6,
            topology_type=TopologyType.SPECIAL,
            multi_area=False,
            ospf_config=(
                OSPFConfig(
                    hello_interval=hello_interval,
                    dead_interval=dead_interval,
                    spf_delay=spf_delay,
                    lsa_min_arrival=lsa_min_arrival,
                    maximum_paths=maximum_paths,
                )
                if enable_ospf6
                else None
            ),
            isis_config=(
                ISISConfig(
                    net_address="49.0001.0000.0000.0001.00",
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
                )
                if enable_isis
                else None
            ),
            bgp_config=BGPConfig(as_number=bgp_as) if enable_bgp else None,
            bfd_config=BFDConfig(enabled=enable_bfd),
            daemons_off=daemons_off,
            bgpd_off=bgpd_off,
            ospf6d_off=ospf6d_off,
            isisd_off=isisd_off,
            bfdd_off=bfdd_off,
            dummy_gen_protocols=set(sum([s.lower().split(',') for s in dummy_gen], [])),
            disable_logging=disable_logging,
            special_config=special_config,
        )
    except Exception as e:
        console.print(f"[red]配置验证失败: {e}[/red]")
        raise typer.Exit(1)

    # 展示基础信息
    display_topology_info(config)

    # 展示 Special 细节
    table = Table(title="Special拓扑详情")
    table.add_column("属性", style="cyan")
    table.add_column("值", style="green")
    base_topology_display = base_topology.upper() if isinstance(base_topology, str) else base_topology.value.upper()
    table.add_row("基础拓扑", base_topology_display)
    table.add_row("包含基础连接", "是" if include_base else "否")
    table.add_row("源节点", str(special_config.source_node))
    table.add_row("目标节点", str(special_config.dest_node))
    table.add_row("网关节点数", str(len(special_config.gateway_nodes)))
    table.add_row("内部桥接边数", str(len(special_config.internal_bridge_edges)))
    table.add_row("Torus桥接边数", str(len(special_config.torus_bridge_edges)))
    console.print(table)

    # 系统需求与确认
    requirements = SystemRequirements.calculate_for_topology(config)
    display_system_requirements(requirements)
    if not yes and not confirm_generation(config):
        console.print("[yellow]已取消[/yellow]")
        raise typer.Exit()

    # 生成
    _run_with_progress("生成Special拓扑...", config)

