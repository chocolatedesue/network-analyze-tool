#!/usr/bin/env python3
"""
OSPFv3 拓扑生成器 - 函数式编程版本
使用现代Python函数式编程范式重构的OSPFv3网络拓扑生成器

特性:
- 不可变数据结构 (Pydantic models)
- 纯函数设计
- 函数组合和管道操作 (toolz)
- 错误处理 (returns)
- 类型安全 (typing)
- 现代CLI (typer)
- 并行处理优化
"""

from __future__ import annotations
from typing import Optional
import sys

import typer
from rich.console import Console
from rich.prompt import Confirm
from rich.panel import Panel
from returns.result import Success, Failure

from ospfv3_models import TopologyConfig, TopologyType, OSPFConfig, BGPConfig, SpecialTopologyConfig
from ospfv3_generator import generate_topology


app = typer.Typer(
    name="ospfv3-generator",
    help="OSPFv3 网络拓扑生成器 (函数式编程版本)",
    add_completion=False,
    rich_markup_mode="rich"
)
console = Console()


def validate_size(size: int) -> int:
    """验证网格大小"""
    if size <= 0:
        raise typer.BadParameter("网格大小必须大于 0")
    
    total_nodes = size * size
    if total_nodes > 4000:
        max_size = int((4000) ** 0.5)
        raise typer.BadParameter(
            f"节点数 ({total_nodes}) 超过 4000 的限制。"
            f"建议最大支持 {max_size}x{max_size} = {max_size**2} 节点"
        )
    
    return size





def validate_area_size(area_size: Optional[int], size: int) -> Optional[int]:
    """验证区域大小"""
    if area_size is not None and area_size > size:
        raise typer.BadParameter(f"区域大小 ({area_size}) 不能大于网格大小 ({size})")
    return area_size


@app.command("grid")
def generate_grid(
    size: int = typer.Argument(..., help="方形网格的边长 (生成 size x size 的拓扑)", callback=validate_size),
    multi_area: bool = typer.Option(False, "--multi-area", help="启用多区域模式"),
    area_size: Optional[int] = typer.Option(None, "--area-size", help="区域大小 (仅在多区域模式下有效，默认为10)"),
    enable_bfd: bool = typer.Option(False, "--enable-bfd", help="启用BFD (Bidirectional Forwarding Detection) 支持"),
    enable_bgp: bool = typer.Option(False, "--enable-bgp", help="启用BGP支持"),
    bgp_as: int = typer.Option(65000, "--bgp-as", help="BGP AS号"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认，直接生成"),
    hello_interval: int = typer.Option(2, "--hello-interval", help="OSPF Hello间隔 (秒)"),
    dead_interval: int = typer.Option(10, "--dead-interval", help="OSPF Dead间隔 (秒)"),
    spf_delay: int = typer.Option(20, "--spf-delay", help="SPF延迟 (毫秒)"),
    north_south_priority: Optional[int] = typer.Option(None, "--north-south-priority", help="纵向接口 (eth1/eth2) OSPF6 优先级"),
    east_west_priority: Optional[int] = typer.Option(None, "--east-west-priority", help="横向接口 (eth3/eth4) OSPF6 优先级"),
) -> None:
    """
    生成OSPFv3 Grid拓扑配置

    Grid拓扑特点:
    - 边缘节点不环绕连接
    - 角落节点: 2个邻居
    - 边缘节点: 3个邻居
    - 内部节点: 4个邻居
    - 更符合实际网络部署场景

    使用示例:
    \b
    # 生成3x3基础Grid拓扑
    python generate_ospfv3_functional.py grid 3 --yes

    # 生成5x5多区域Grid拓扑，启用BFD
    python generate_ospfv3_functional.py grid 5 --multi-area --enable-bfd --yes

    # 自定义OSPF参数的Grid拓扑
    python generate_ospfv3_functional.py grid 4 --hello-interval 1 --dead-interval 5 --spf-delay 10 --yes

    # 设置接口优先级的Grid拓扑
    python generate_ospfv3_functional.py grid 3 --north-south-priority 100 --east-west-priority 50 --yes
    """
    area_size = validate_area_size(area_size, size)

    config = TopologyConfig(
        size=size,
        topology_type=TopologyType.GRID,
        multi_area=multi_area,
        area_size=area_size,
        enable_bfd=enable_bfd
    )

    # 添加BGP配置
    if enable_bgp:
        from ospfv3_models import BGPConfig
        config.bgp_config = BGPConfig(as_number=bgp_as)
    
    ospf_config = OSPFConfig(
        hello_interval=hello_interval,
        dead_interval=dead_interval,
        spf_delay=spf_delay,
        north_south_priority=north_south_priority,
        east_west_priority=east_west_priority
    )
    
    # 添加OSPF配置到拓扑配置
    config.ospf_config = ospf_config
    
    _generate_with_confirmation(config, yes)


@app.command("torus")
def generate_torus(
    size: int = typer.Argument(..., help="方形网格的边长 (生成 size x size 的拓扑)", callback=validate_size),
    multi_area: bool = typer.Option(False, "--multi-area", help="启用多区域模式"),
    area_size: Optional[int] = typer.Option(None, "--area-size", help="区域大小 (仅在多区域模式下有效，默认为10)"),
    enable_bfd: bool = typer.Option(False, "--enable-bfd", help="启用BFD (Bidirectional Forwarding Detection) 支持"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认，直接生成"),
    hello_interval: int = typer.Option(1, "--hello-interval", help="OSPF Hello间隔 (秒)"),
    dead_interval: int = typer.Option(10, "--dead-interval", help="OSPF Dead间隔 (秒)"),
    spf_delay: int = typer.Option(20, "--spf-delay", help="SPF延迟 (毫秒)"),
    north_south_priority: Optional[int] = typer.Option(None, "--north-south-priority", help="纵向接口 (eth1/eth2) OSPF6 优先级"),
    east_west_priority: Optional[int] = typer.Option(None, "--east-west-priority", help="横向接口 (eth3/eth4) OSPF6 优先级"),
) -> None:
    """
    生成OSPFv3 Torus拓扑配置

    Torus拓扑特点:
    - 边缘节点环绕连接
    - 所有节点都有4个邻居
    - 更高的连接密度和路径冗余
    - 适合研究网络收敛性能

    使用示例:
    \b
    # 生成3x3基础Torus拓扑
    python generate_ospfv3_functional.py torus 3 --yes

    # 生成4x4多区域Torus拓扑，启用BFD
    python generate_ospfv3_functional.py torus 4 --multi-area --enable-bfd --yes

    # 快速收敛的Torus拓扑（更短的Hello间隔）
    python generate_ospfv3_functional.py torus 3 --hello-interval 1 --dead-interval 3 --yes

    # 大规模Torus拓扑（适合性能测试）
    python generate_ospfv3_functional.py torus 10 --spf-delay 50 --yes
    """
    area_size = validate_area_size(area_size, size)
    
    config = TopologyConfig(
        size=size,
        topology_type=TopologyType.TORUS,
        multi_area=multi_area,
        area_size=area_size,
        enable_bfd=enable_bfd
    )
    
    ospf_config = OSPFConfig(
        hello_interval=hello_interval,
        dead_interval=dead_interval,
        spf_delay=spf_delay,
        north_south_priority=north_south_priority,
        east_west_priority=east_west_priority
    )
    
    # 添加OSPF配置到拓扑配置
    config.ospf_config = ospf_config
    
    _generate_with_confirmation(config, yes)


@app.command("special")
def generate_special(
    size: int = typer.Argument(6, help="网格大小 (默认6x6，用于dm6_6_sample)"),
    enable_bfd: bool = typer.Option(False, "--enable-bfd", help="启用BFD (Bidirectional Forwarding Detection) 支持"),
    enable_bgp: bool = typer.Option(True, "--enable-bgp", help="为gateway节点启用BGP"),
    base_topology: str = typer.Option("grid", "--base-topology", help="基础拓扑类型 (grid/torus)"),
    include_base: bool = typer.Option(True, "--include-base/--no-include-base", help="是否包含基础拓扑连接"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认，直接生成"),
    hello_interval: int = typer.Option(2, "--hello-interval", help="OSPF Hello间隔 (秒)"),
    dead_interval: int = typer.Option(10, "--dead-interval", help="OSPF Dead间隔 (秒)"),
    spf_delay: int = typer.Option(20, "--spf-delay", help="SPF延迟 (毫秒)"),
    bgp_as: int = typer.Option(65000, "--bgp-as", help="BGP AS号"),
) -> None:
    """
    生成特殊拓扑配置 (基于dm6_6_sample)

    特殊拓扑特点:
    - 基于6x6网格的域分割示例
    - 包含源节点 (1,4) 和目标节点 (4,1)
    - 16个Gateway节点支持BGP
    - 4条内部桥接连接 + 4条Torus桥接连接（仅路由配置）
    - 只生成有连接的18个节点
    - ContainerLab中只包含内部桥接连接

    使用示例:
    \b
    # 生成基础特殊拓扑（Grid基础+特殊连接+BGP）
    python generate_ospfv3_functional.py special --yes

    # 生成Torus基础的特殊拓扑
    python generate_ospfv3_functional.py special --base-topology torus --yes

    # 只生成特殊连接，不包含基础拓扑
    python generate_ospfv3_functional.py special --no-include-base --yes

    # 生成特殊拓扑，启用BFD，自定义BGP AS号
    python generate_ospfv3_functional.py special --enable-bfd --bgp-as 65001 --yes

    # 生成特殊拓扑，禁用BGP
    python generate_ospfv3_functional.py special --no-enable-bgp --yes

    # 生成特殊拓扑，自定义OSPF参数
    python generate_ospfv3_functional.py special --hello-interval 1 --dead-interval 5 --spf-delay 10 --yes
    """
    if size != 6:
        console.print("[yellow]⚠️  特殊拓扑当前只支持6x6网格[/yellow]")
        size = 6

    # 解析基础拓扑类型
    base_topo = TopologyType.TORUS if base_topology.lower() == "torus" else TopologyType.GRID

    # 创建特殊拓扑配置
    special_config = SpecialTopologyConfig.create_dm6_6_sample()
    special_config.base_topology = base_topo
    special_config.include_base_connections = include_base

    config = TopologyConfig(
        size=size,
        topology_type=TopologyType.SPECIAL,
        multi_area=False,
        enable_bfd=enable_bfd,
        special_config=special_config
    )

    ospf_config = OSPFConfig(
        hello_interval=hello_interval,
        dead_interval=dead_interval,
        spf_delay=spf_delay
    )

    bgp_config = BGPConfig(
        as_number=bgp_as,
        enable_ipv6=True,
        redistribute_ospf6=True,
        redistribute_connected=True
    ) if enable_bgp else None

    # 添加配置到拓扑配置
    config.ospf_config = ospf_config
    config.bgp_config = bgp_config

    _generate_with_confirmation(config, yes)


def _generate_with_confirmation(config: TopologyConfig, skip_confirmation: bool) -> None:
    """生成拓扑配置，可选择跳过确认"""
    # 显示配置信息
    _display_config_info(config)
    
    # 用户确认
    if not skip_confirmation:
        if config.total_routers > 100:
            console.print("\n[yellow]⚠️  即将生成大规模网络，这可能需要较多系统资源[/yellow]")
        
        if not Confirm.ask(f"\n确认生成 {config.size}x{config.size} OSPFv3 {config.topology_type.value.title()} 拓扑?"):
            console.print("[red]已取消[/red]")
            raise typer.Exit(0)
    
    # 执行生成
    result = generate_topology(config)
    
    if isinstance(result, Success):
        generation_result = result.unwrap()
        console.print(f"\n[green]✅ 生成完成！耗时: {generation_result.elapsed_time:.2f}秒[/green]")
        console.print(f"[blue]📁 配置位置: {generation_result.target_dir}/[/blue]")
    else:
        error_msg = result.failure()
        console.print(f"\n[red]❌ 生成失败: {error_msg}[/red]")
        raise typer.Exit(1)


def _display_config_info(config: TopologyConfig) -> None:
    """显示配置信息"""
    info_lines = [
        f"[bold]规模:[/bold] {config.size}x{config.size}",
        f"[bold]节点数:[/bold] {config.total_routers}",
        f"[bold]连接数:[/bold] {config.total_links}",
        f"[bold]协议:[/bold] OSPFv3",
        f"[bold]拓扑:[/bold] {config.topology_type.value.title()}",
        f"[bold]BFD支持:[/bold] {'启用' if config.enable_bfd else '禁用'}",
        f"[bold]区域模式:[/bold] {'多区域' if config.multi_area else '单区域'}",
    ]

    if config.multi_area:
        info_lines.append(f"[bold]区域大小:[/bold] {config.effective_area_size}x{config.effective_area_size}")

    if config.topology_type == TopologyType.SPECIAL:
        info_lines.extend([
            f"[bold]BGP支持:[/bold] {'启用' if config.bgp_config else '禁用'}",
            f"[bold]特殊节点:[/bold] 源节点、目标节点、Gateway节点"
        ])
        if config.special_config:
            base_topo_name = config.special_config.base_topology.value.title()
            info_lines.extend([
                f"[bold]基础拓扑:[/bold] {base_topo_name}",
                f"[bold]包含基础连接:[/bold] {'是' if config.special_config.include_base_connections else '否'}",
                f"[bold]Gateway节点数:[/bold] {len(config.special_config.gateway_nodes)}",
                f"[bold]内部桥接:[/bold] {len(config.special_config.internal_bridge_edges)}条",
                f"[bold]Torus桥接:[/bold] {len(config.special_config.torus_bridge_edges)}条(仅路由配置)"
            ])

    panel = Panel(
        "\n".join(info_lines),
        title=f"OSPFv3 {config.topology_type.value.title()} 拓扑配置",
        border_style="blue"
    )

    console.print(panel)


@app.command("version")
def show_version() -> None:
    """显示版本信息"""
    version_info = """
[bold blue]OSPFv3 拓扑生成器 - 函数式编程版本[/bold blue]
版本: 2.0.0
作者: Augment Agent
日期: 2025-08-06

[bold green]特性:[/bold green]
• 不可变数据结构 (Pydantic models)
• 纯函数设计
• 函数组合和管道操作 (toolz)
• 错误处理 (returns)
• 类型安全 (typing)
• 现代CLI (typer)
• 并行处理优化
    """
    console.print(Panel(version_info, border_style="green"))


def main() -> None:
    """主入口函数"""
    try:
        app()
    except KeyboardInterrupt:
        console.print("\n[yellow]操作被用户中断[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[red]未预期的错误: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
