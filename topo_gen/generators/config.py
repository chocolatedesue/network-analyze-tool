"""
现代化配置生成器
"""

from __future__ import annotations

from typing import Dict, List, Optional, Protocol, Set

from ..core.types import (
    Coordinate, Direction, NodeType, RouterName, InterfaceName,
    IPv6Address, ASNumber, RouterID, ConfigPipeline, TopologyType,
    get_direction_for_interface,
)
from ..core.models import (
    TopologyConfig, RouterInfo, OSPFConfig, BGPConfig, BFDConfig
)
from .renderer import render_template

from ..utils.topo import get_topology_type_str

# 配置生成协议
class ConfigGenerator(Protocol):
    """配置生成器协议"""
    
    def generate(self, router_info: RouterInfo, config: TopologyConfig) -> str:
        """生成配置"""
        ...

def _build_ospf_context(router_info: RouterInfo, config: TopologyConfig) -> Dict[str, object]:
    """构建 OSPF 模板上下文。"""
    assert config.ospf_config is not None
    ospf_config = config.ospf_config

    excluded_interfaces: Set[str] = set()
    if (
        config.topology_type == TopologyType.SPECIAL
        and config.bgp_config is not None
        and router_info.node_type == NodeType.GATEWAY
    ):
        excluded_interfaces = _get_ebgp_interfaces(router_info, config)

    interfaces_ctx: List[Dict[str, object]] = []
    for interface_name in sorted(router_info.interfaces.keys()):
        if interface_name in excluded_interfaces:
            continue
        direction = get_direction_for_interface(interface_name)
        cost: Optional[int] = None
        if direction in (Direction.EAST, Direction.WEST):
            cost = 40
        elif direction in (Direction.NORTH, Direction.SOUTH):
            cost = 20
        elif ospf_config.cost:
            cost = ospf_config.cost
        interfaces_ctx.append(
            {
                "name": interface_name,
                "area_id": router_info.area_id,
                "hello_interval": ospf_config.hello_interval,
                "dead_interval": ospf_config.dead_interval,
                "retransmit_interval": ospf_config.retransmit_interval,
                "transmit_delay": ospf_config.transmit_delay,
                "priority": ospf_config.priority,
                "cost": cost,
            }
        )

    return {
        "router_name": router_info.name,
        "disable_logging": config.disable_logging,
        "interfaces": interfaces_ctx,
        "loopback_area_id": router_info.area_id,
        "router": {
            "router_id": router_info.router_id,
            "spf_delay": ospf_config.spf_delay,
            "lsa_min_arrival": ospf_config.lsa_min_arrival,
            "maximum_paths": ospf_config.maximum_paths,
        },
    }

def _get_ebgp_interfaces(router_info: RouterInfo, topology_config: TopologyConfig) -> Set[str]:
    """获取用于eBGP的接口列表（Special拓扑中的跨域连接接口）"""
    from ..core.types import INTERFACE_MAPPING
    from ..links import calculate_direction

    ebgp_interfaces = set()

    if not topology_config.special_config:
        return ebgp_interfaces

    # 内部桥接连接（在ContainerLab中创建的物理连接）
    for edge in topology_config.special_config.internal_bridge_edges:
        if edge[0] == router_info.coordinate:
            other_coord = edge[1]
            direction = calculate_direction(router_info.coordinate, other_coord)
            if direction:
                interface = INTERFACE_MAPPING[direction]
                ebgp_interfaces.add(interface)
        elif edge[1] == router_info.coordinate:
            other_coord = edge[0]
            direction = calculate_direction(router_info.coordinate, other_coord)
            if direction:
                interface = INTERFACE_MAPPING[direction]
                ebgp_interfaces.add(interface)

    # Torus桥接连接（为gateway节点提供额外接口用于BGP）
    for edge in topology_config.special_config.torus_bridge_edges:
        if edge[0] == router_info.coordinate:
            other_coord = edge[1]
            direction = calculate_direction(router_info.coordinate, other_coord)
            if direction:
                interface = INTERFACE_MAPPING[direction]
                ebgp_interfaces.add(interface)
        elif edge[1] == router_info.coordinate:
            other_coord = edge[0]
            direction = calculate_direction(router_info.coordinate, other_coord)
            if direction:
                interface = INTERFACE_MAPPING[direction]
                ebgp_interfaces.add(interface)

    return ebgp_interfaces

def _build_bgp_context(router_info: RouterInfo, config: TopologyConfig, all_routers: Optional[List[RouterInfo]]) -> Dict[str, object]:
    """构建 BGP 模板上下文。"""
    if not router_info.as_number:
        return {
            "router_name": router_info.name,
            "disable_logging": config.disable_logging,
            "as_number": None,
            "router_id": router_info.router_id,
            "ebgp_interfaces": [],
            "ibgp_peers": [],
            "address_family": None,
        }

    ebgp_ifaces: List[str] = []
    if get_topology_type_str(config.topology_type) == "special":
        ebgp_ifaces = sorted(_get_ebgp_interfaces(router_info, config))

    ibgp_peers: List[str] = []
    if all_routers:
        from ..core.types import extract_ipv6_address
        for r in all_routers:
            is_router_gateway = (
                r.node_type == NodeType.GATEWAY
                or str(r.node_type) == "gateway"
                or (hasattr(r.node_type, "value") and r.node_type.value == "gateway")
            )
            if r.coordinate != router_info.coordinate and r.as_number == router_info.as_number and is_router_gateway:
                ibgp_peers.append(extract_ipv6_address(str(r.loopback_ipv6)))

    from ..core.types import ensure_ipv6_prefix
    loopback_with_prefix = ensure_ipv6_prefix(str(router_info.loopback_ipv6), 128)
    address_family = {
        "network": loopback_with_prefix,
        "redistribute_ospf6": config.ospf_config is not None,
        "redistribute_connected": True,
        "activate_ebgp_interfaces": ebgp_ifaces,
        "activate_ibgp_peers": ibgp_peers,
    }

    return {
        "router_name": router_info.name,
        "disable_logging": config.disable_logging,
        "as_number": router_info.as_number,
        "router_id": router_info.router_id,
        "ebgp_interfaces": ebgp_ifaces,
        "ibgp_peers": ibgp_peers,
        "address_family": address_family,
    }

def _create_special_bgp_neighbors(
    router_info: RouterInfo,
    all_routers: List[RouterInfo],
    topology_config: TopologyConfig
) -> List[str]:
    """创建Special拓扑的BGP邻居配置"""
    from ..core.types import INTERFACE_MAPPING, Direction, extract_ipv6_address, ensure_ipv6_prefix
    from ..links import calculate_direction

    neighbors = []

    # 1. 计算eBGP接口（跨域连接）
    ebgp_interfaces = []

    if topology_config.special_config:
        # 内部桥接连接（在ContainerLab中创建的物理连接）
        for edge in topology_config.special_config.internal_bridge_edges:
            if edge[0] == router_info.coordinate:
                other_coord = edge[1]
                direction = calculate_direction(router_info.coordinate, other_coord)
                if direction:
                    interface = INTERFACE_MAPPING[direction]
                    ebgp_interfaces.append(interface)
            elif edge[1] == router_info.coordinate:
                other_coord = edge[0]
                direction = calculate_direction(router_info.coordinate, other_coord)
                if direction:
                    interface = INTERFACE_MAPPING[direction]
                    ebgp_interfaces.append(interface)

        # Torus桥接连接（为gateway节点提供额外接口用于BGP）
        for edge in topology_config.special_config.torus_bridge_edges:
            if edge[0] == router_info.coordinate:
                other_coord = edge[1]
                direction = calculate_direction(router_info.coordinate, other_coord)
                if direction:
                    interface = INTERFACE_MAPPING[direction]
                    ebgp_interfaces.append(interface)
            elif edge[1] == router_info.coordinate:
                other_coord = edge[0]
                direction = calculate_direction(router_info.coordinate, other_coord)
                if direction:
                    interface = INTERFACE_MAPPING[direction]
                    ebgp_interfaces.append(interface)

    # 去重并排序
    ebgp_interfaces = sorted(set(ebgp_interfaces))

    # 2. 添加eBGP接口邻居配置
    for interface in ebgp_interfaces:
        neighbors.append(f" neighbor {interface} interface remote-as external")

    # 3. 添加iBGP邻居（同AS内的其他Gateway路由器）
    ibgp_neighbors = []
    for router in all_routers:
        # 处理节点类型比较（支持枚举和字符串）
        is_router_gateway = (
            router.node_type == NodeType.GATEWAY or
            str(router.node_type) == "gateway" or
            (hasattr(router.node_type, 'value') and router.node_type.value == "gateway")
        )

        if (router.coordinate != router_info.coordinate and
            router.as_number == router_info.as_number and
            is_router_gateway):
            # 提取纯IPv6地址（去掉前缀）
            neighbor_ipv6 = extract_ipv6_address(str(router.loopback_ipv6))
            neighbors.extend([
                f" neighbor {neighbor_ipv6} remote-as {router.as_number}",
                f" neighbor {neighbor_ipv6} update-source lo",
                f" neighbor {neighbor_ipv6} next-hop-self",
            ])
            ibgp_neighbors.append(router)

    neighbors.append("!")

    # 4. 添加IPv6地址族配置
    loopback_with_prefix = ensure_ipv6_prefix(str(router_info.loopback_ipv6), 128)
    neighbors.extend([
        " address-family ipv6 unicast",
        f"  network {loopback_with_prefix}",
    ])

    # 激活eBGP接口邻居
    for interface in ebgp_interfaces:
        neighbors.append(f"  neighbor {interface} activate")

    # 激活iBGP邻居
    for router in all_routers:
        if (router.coordinate != router_info.coordinate and
            router.as_number == router_info.as_number and
            router.node_type == NodeType.GATEWAY):
            neighbor_ipv6 = extract_ipv6_address(str(router.loopback_ipv6))
            neighbors.append(f"  neighbor {neighbor_ipv6} activate")

    # 只有在OSPF6启用时才重分发OSPF6路由
    redistribute_config = []
    if topology_config.ospf_config is not None:
        redistribute_config.append("  redistribute ospf6")
    redistribute_config.extend([
        "  redistribute connected",
        " exit-address-family"
    ])
    neighbors.extend(redistribute_config)

    return neighbors

def _create_regular_bgp_neighbors(
    router_info: RouterInfo,
    all_routers: List[RouterInfo]
) -> List[str]:
    """创建Grid/Torus拓扑的BGP邻居配置"""
    from ..core.types import extract_ipv6_address

    neighbors = []

    # 所有其他路由器都是iBGP邻居
    for router in all_routers:
        if router.coordinate != router_info.coordinate:
            # 提取纯IPv6地址（去掉前缀）
            neighbor_ipv6 = extract_ipv6_address(str(router.loopback_ipv6))
            neighbors.extend([
                f" neighbor {neighbor_ipv6} remote-as {router_info.as_number}",
                f" neighbor {neighbor_ipv6} update-source lo",
                f" neighbor {neighbor_ipv6} next-hop-self",
            ])

    return neighbors

# 旧的 BFD 行级构造函数已不再需要

# 具体的配置生成器实现
class DaemonsConfigGenerator:
    """Daemons配置生成器"""
    
    @staticmethod
    def generate(router_info: RouterInfo, config: TopologyConfig) -> str:
        """生成daemons配置"""
        # 判断是否启用BGP
        topo_type = get_topology_type_str(config.topology_type)

        # 处理节点类型比较（支持枚举和字符串）
        is_gateway = (
            router_info.node_type == NodeType.GATEWAY or
            str(router_info.node_type) == "gateway" or
            (hasattr(router_info.node_type, 'value') and router_info.node_type.value == "gateway")
        )

        enable_bgp = config.enable_bgp and (
            is_gateway or
            topo_type in ["grid", "torus"]
        )

        # 判断是否启用BFD和OSPF6
        enable_bfd = config.enable_bfd
        enable_ospf6 = config.ospf_config is not None

        # 当 daemons_off=True 时，仅在 daemons 文件中关闭相应守护进程，但仍允许生成对应配置文件
        if getattr(config, 'daemons_off', False):
            enable_bgp = False
            enable_ospf6 = False
            enable_bfd = False
        # 细粒度关闭：仅关闭某一类守护进程
        if getattr(config, 'bgpd_off', False):
            enable_bgp = False
        if getattr(config, 'ospf6d_off', False):
            enable_ospf6 = False
        if getattr(config, 'bfdd_off', False):
            enable_bfd = False

        return render_template(
            "daemons.j2",
            {
                "enable_bgp": enable_bgp,
                "enable_bfd": enable_bfd,
                "enable_ospf6": enable_ospf6,
            },
        ) + "\n"

class ZebraConfigGenerator:
    """Zebra配置生成器 - 按建议文档优化配置顺序"""

    @staticmethod
    def generate(router_info: RouterInfo, config: TopologyConfig) -> str:
        """生成zebra配置 - 先基础网络、后路由协议的顺序"""
        # 处理地址前缀
        loopback = str(router_info.loopback_ipv6)
        if "/128" not in loopback:
            loopback = f"{loopback}/128"

        iface_list = []
        for interface_name in sorted(router_info.interfaces.keys()):
            addr_str = str(router_info.interfaces[interface_name])
            addr_with_prefix = addr_str if "/" in addr_str else f"{addr_str}/127"
            iface_list.append({"name": interface_name, "addr": addr_with_prefix})

        return render_template(
            "zebra.conf.j2",
            {
                "router_name": router_info.name,
                "loopback_ipv6": loopback,
                "interfaces": iface_list,
                "disable_logging": config.disable_logging,
            },
        )

class OSPF6ConfigGenerator:
    """OSPF6配置生成器"""

    @staticmethod
    def generate(router_info: RouterInfo, config: TopologyConfig) -> str:
        """生成ospf6d配置"""
        # 如果OSPF6被禁用，返回空配置
        if not config.ospf_config:
            return ""

        ctx = _build_ospf_context(router_info, config)
        return render_template("ospf6d.conf.j2", ctx)

class BGPConfigGenerator:
    """BGP配置生成器"""

    @staticmethod
    def generate(router_info: RouterInfo, config: TopologyConfig, all_routers: List[RouterInfo] = None) -> str:
        """生成bgpd配置"""
        if not config.enable_bgp or not config.bgp_config:
            return ""

        ctx = _build_bgp_context(router_info, config, all_routers)
        return render_template("bgpd.conf.j2", ctx)

class BFDConfigGenerator:
    """BFD配置生成器"""

    @staticmethod
    def generate(router_info: RouterInfo, config: TopologyConfig) -> str:
        """生成bfdd配置"""
        if not config.enable_bfd:
            return ""

        return render_template(
            "bfdd.conf.j2",
            {
                "router_name": router_info.name,
                "bfd": config.bfd_config,
                "disable_logging": config.disable_logging,
            },
        )

# 配置生成器工厂
class ConfigGeneratorFactory:
    """配置生成器工厂"""
    
    _generators: Dict[str, type] = {
        "daemons": DaemonsConfigGenerator,
        "zebra.conf": ZebraConfigGenerator,
        "ospf6d.conf": OSPF6ConfigGenerator,
        "bgpd.conf": BGPConfigGenerator,
        "bfdd.conf": BFDConfigGenerator,
    }
    
    @classmethod
    def register(cls, config_type: str, generator_class: type):
        """注册配置生成器"""
        cls._generators[config_type] = generator_class
    
    @classmethod
    def create(cls, config_type: str) -> ConfigGenerator:
        """创建配置生成器"""
        if config_type not in cls._generators:
            raise ValueError(f"未知的配置类型: {config_type}")
        
        generator_class = cls._generators[config_type]
        return generator_class()
    
    @classmethod
    def get_all_types(cls) -> List[str]:
        """获取所有支持的配置类型"""
        return list(cls._generators.keys())

# 配置生成管道
def create_config_pipeline(config_types: List[str]) -> ConfigPipeline:
    """创建配置生成管道"""
    generators = [ConfigGeneratorFactory.create(config_type) for config_type in config_types]
    
    def pipeline(router_info: RouterInfo, config: TopologyConfig) -> Dict[str, str]:
        """执行配置生成管道"""
        results = {}
        for config_type, generator in zip(config_types, generators):
            results[config_type] = generator.generate(router_info, config)
        return results
    
    return pipeline
