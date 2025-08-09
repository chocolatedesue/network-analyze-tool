"""
现代化配置生成器
使用函数式编程和类型安全的配置生成
"""

from __future__ import annotations

from typing import Dict, List, Optional, Callable, Any, Protocol, Set
from functools import partial
from dataclasses import dataclass
from pathlib import Path
import ipaddress

from ..core.types import (
    Coordinate, Direction, NodeType, RouterName, InterfaceName,
    IPv6Address, ASNumber, RouterID, ConfigBuilder, ConfigPipeline, TopologyType
)
from ..core.models import (
    TopologyConfig, RouterInfo, OSPFConfig, BGPConfig, BFDConfig
)
from ..utils.functional import pipe, compose, memoize


def get_topology_type_str(topology_type) -> str:
    """获取拓扑类型字符串"""
    if hasattr(topology_type, 'value'):
        return topology_type.value
    return str(topology_type)

# 配置生成协议
class ConfigGenerator(Protocol):
    """配置生成器协议"""
    
    def generate(self, router_info: RouterInfo, config: TopologyConfig) -> str:
        """生成配置"""
        ...

# 基础配置构建器
@dataclass(frozen=True)
class ConfigSection:
    """配置段"""
    name: str
    content: List[str]
    
    def render(self) -> str:
        """渲染配置段"""
        if not self.content:
            return ""
        
        lines = [f"# {self.name}", "!"] + self.content + ["!"]
        return "\n".join(lines)

class ConfigBuilder:
    """配置构建器"""
    
    def __init__(self):
        self.sections: List[ConfigSection] = []
    
    def add_section(self, name: str, content: List[str]) -> ConfigBuilder:
        """添加配置段"""
        self.sections.append(ConfigSection(name, content))
        return self
    
    def add_header(self, router_name: str, description: str) -> ConfigBuilder:
        """添加配置头部"""
        header_content = [
            f"! {description} for {router_name}",
            "!",
            "frr version 7.5.1_git",
            "frr defaults traditional",
            "!",
            f"hostname {router_name}",
        ]
        return self.add_section("Header", header_content)
    
    def add_footer(self) -> ConfigBuilder:
        """添加配置尾部"""
        footer_content = ["line vty", "!"]
        return self.add_section("Footer", footer_content)
    
    def build(self) -> str:
        """构建最终配置"""
        return "\n".join(section.render() for section in self.sections)

# 简化的配置生成器函数
def create_header_section(router_name: str, description: str) -> ConfigSection:
    """创建头部配置段"""
    content = [
        f"! {description} for {router_name}",
        "!",
        "frr version 7.5.1_git",
        "frr defaults traditional",
        "!",
        f"hostname {router_name}",
    ]
    return ConfigSection("Header", content)

def create_interface_section(interface_name: str, ipv6_addr: IPv6Address) -> ConfigSection:
    """创建接口配置段"""
    # 转换为字符串并检查是否包含前缀
    addr_str = str(ipv6_addr)
    addr_with_prefix = addr_str if '/' in addr_str else f"{addr_str}/127"
    content = [
        f"interface {interface_name}",
        # f" description \"Point-to-point link interface\"",
        f" ipv6 address {addr_with_prefix}",
        # f" no shutdown",
    ]
    return ConfigSection(f"Interface {interface_name}", content)

def create_loopback_section(ipv6_addr: IPv6Address) -> ConfigSection:
    """创建Loopback接口配置段"""
    # 转换为字符串并确保loopback地址包含/128前缀
    addr_str = str(ipv6_addr)
    addr_with_prefix = addr_str if '/128' in addr_str else f"{addr_str}/128"
    content = [
        "interface lo",
        # f" description \"Loopback interface for router ID\"",
        f" ipv6 address {addr_with_prefix}",
    ]
    return ConfigSection("Loopback Interface", content)

def create_ospf_section(
    router_info: RouterInfo,
    ospf_config: OSPFConfig,
    interfaces: Dict[str, str],
    topology_config: Optional[TopologyConfig] = None
) -> ConfigSection:
    """创建OSPF配置段 - 先接口配置，后router定义"""
    from ..core.types import ensure_ipv6_prefix, get_direction_for_interface
    from ..core.types import Direction as Dir

    content = []

    # 在Special模式下，对于gateway节点，需要排除用于eBGP的接口
    excluded_interfaces = set()
    if (topology_config and
        topology_config.topology_type == TopologyType.SPECIAL and
        topology_config.bgp_config is not None and
        router_info.node_type == NodeType.GATEWAY):
        excluded_interfaces = _get_ebgp_interfaces(router_info, topology_config)

    # 1. 先配置所有接口（按接口名排序确保一致性）
    for interface_name in sorted(interfaces.keys()):
        # 在Special模式下，跳过用于eBGP的接口
        if interface_name in excluded_interfaces:
            continue

        # 基本OSPF6接口设置
        content.extend([
            f"interface {interface_name}",
            f" ipv6 ospf6 area {router_info.area_id}",
            f" ipv6 ospf6 hello-interval {ospf_config.hello_interval}",
            f" ipv6 ospf6 dead-interval {ospf_config.dead_interval}",
            f" ipv6 ospf6 retransmit-interval {ospf_config.retransmit_interval}",
        ])

        # 根据接口方向设置开销：横向(eth3/eth4)=40，纵向(eth1/eth2)=20
        direction = get_direction_for_interface(interface_name)
        if direction in (Dir.EAST, Dir.WEST):
            content.append(" ipv6 ospf6 cost 40")
        elif direction in (Dir.NORTH, Dir.SOUTH):
            content.append(" ipv6 ospf6 cost 20")
        elif ospf_config.cost:
            # 回退到全局cost（如果提供）
            content.append(f" ipv6 ospf6 cost {ospf_config.cost}")

        # 可选优先级
        if ospf_config.priority is not None:
            content.append(f" ipv6 ospf6 priority {ospf_config.priority}")

        # 点到点网络与前缀通告设置
        content.extend([
            " ipv6 ospf6 p2p-p2mp connected-prefixes exclude",
            " ipv6 ospf6 network point-to-point",
        ])

    # 2. Loopback接口配置
    content.extend([
        "interface lo",
        f" ipv6 ospf6 area {router_info.area_id}",
    ])

    # 3. 最后配置router ospf6（在接口配置之后）
    content.extend([
        "router ospf6",
        f" ospf6 router-id {router_info.router_id}",
        # f" area {router_info.area_id}",
        f" timers throttle spf {ospf_config.spf_delay} {ospf_config.spf_delay * 2} {ospf_config.spf_delay * 50}",
        " timers lsa min-arrival 0",
        " maximum-paths 1",
    ])

    return ConfigSection("OSPF6 Configuration", content)

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

def create_bgp_section(
    router_info: RouterInfo,
    bgp_config: BGPConfig,
    all_routers: List[RouterInfo],
    topology_config: TopologyConfig
) -> ConfigSection:
    """创建BGP配置段"""
    if not router_info.as_number:
        return ConfigSection("BGP Configuration", [])
    
    content = [
        f"router bgp {router_info.as_number}",
        f" bgp router-id {router_info.router_id}",
        " bgp log-neighbor-changes",
        " bgp bestpath as-path multipath-relax",
        " no bgp default ipv4-unicast",
    ]
    
    # 添加邻居配置
    if get_topology_type_str(topology_config.topology_type) == "special":
        # Special拓扑的BGP配置逻辑（包含完整的address-family配置）
        content.extend(_create_special_bgp_neighbors(router_info, all_routers, topology_config))
    else:
        # Grid/Torus拓扑的BGP配置逻辑
        content.extend(_create_regular_bgp_neighbors(router_info, all_routers))

        # IPv6地址族配置
        from ..core.types import extract_ipv6_address, ensure_ipv6_prefix
        loopback_with_prefix = ensure_ipv6_prefix(str(router_info.loopback_ipv6), 128)
        address_family_config = [
            " address-family ipv6 unicast",
            f"  network {loopback_with_prefix}",
        ]

        # 只有在OSPF6启用时才重分发OSPF6路由
        if topology_config.ospf_config is not None:
            address_family_config.append("  redistribute ospf6")

        address_family_config.append("  redistribute connected")
        content.extend(address_family_config)

        # 激活邻居
        for router in all_routers:
            if router.coordinate != router_info.coordinate and router.as_number == router_info.as_number:
                neighbor_ipv6 = extract_ipv6_address(str(router.loopback_ipv6))
                content.append(f"  neighbor {neighbor_ipv6} activate")

        content.extend([
            " exit-address-family",
        ])
    
    return ConfigSection("BGP Configuration", content)

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

    # 调试信息
    if router_info.coordinate.row == 0 and router_info.coordinate.col == 1:
        print(f"DEBUG: router_00_01 iBGP neighbors: {len(ibgp_neighbors)}")
        print(f"DEBUG: all_routers count: {len(all_routers)}")
        for r in all_routers[:3]:
            print(f"  Router {r.coordinate}: AS={r.as_number}, type={r.node_type}")

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

def create_bfd_section(bfd_config: BFDConfig) -> ConfigSection:
    """创建BFD配置段"""
    if not bfd_config.enabled:
        return ConfigSection("BFD Configuration", [])
    
    content = [
        f"bfd",
        f" profile {bfd_config.profile_name}",
        f"  detect-multiplier {bfd_config.detect_multiplier}",
        f"  receive-interval {bfd_config.receive_interval}",
        f"  transmit-interval {bfd_config.transmit_interval}",
        f"  echo-mode",
        f" exit",
    ]
    
    return ConfigSection("BFD Configuration", content)

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

        # 调试信息
        if router_info.coordinate.row == 0 and router_info.coordinate.col == 0:
            print(f"DEBUG: config.enable_bgp={config.enable_bgp}, is_gateway={is_gateway}, topo_type={topo_type}")
            print(f"DEBUG: enable_bgp={enable_bgp}")
            print(f"DEBUG: config.ospf_config is not None={config.ospf_config is not None}")
            print(f"DEBUG: enable_ospf6={config.ospf_config is not None}")

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

        content = [
            "zebra=yes",
            f"bgpd={'yes' if enable_bgp else 'no'}",
            "ospfd=no",
            f"ospf6d={'yes' if enable_ospf6 else 'no'}",
            "ripd=no",
            "ripngd=no",
            "isisd=no",
            "pimd=no",
            "ldpd=no",
            "nhrpd=no",
            "eigrpd=no",
            "babeld=no",
            "sharpd=no",
            "pbrd=no",
            f"bfdd={'yes' if enable_bfd else 'no'}",
            "fabricd=no",
            "vrrpd=no",
            "mgmtd=no",
            "staticd=no",
        ]
        
        return "\n".join(content) + "\n"

class ZebraConfigGenerator:
    """Zebra配置生成器 - 按建议文档优化配置顺序"""

    @staticmethod
    def generate(router_info: RouterInfo, config: TopologyConfig) -> str:
        """生成zebra配置 - 先基础网络、后路由协议的顺序"""
        builder = ConfigBuilder()

        # 添加头部
        builder.add_header(router_info.name, "Zebra configuration")

        # 1. 基础网络配置 - IP转发（在接口配置后启用）
        builder.add_section("Forwarding", [
            "ip forwarding",
            "ipv6 forwarding",
        ])

        # 2. 基础网络配置 - Loopback接口（最重要的基础设施）
        loopback_section = create_loopback_section(router_info.loopback_ipv6)
        builder.sections.append(loopback_section)

        # 3. 基础网络配置 - 物理接口（按接口名排序确保一致性）
        for interface_name in sorted(router_info.interfaces.keys()):
            ipv6_addr = router_info.interfaces[interface_name]
            interface_section = create_interface_section(interface_name, ipv6_addr)
            builder.sections.append(interface_section)

        # 4. 日志配置（在基础网络配置后）
        if not config.disable_logging:
            builder.add_section("Logging", [
                "log file /var/log/frr/zebra.log debugging",
                "log commands",
            ])

        # 添加尾部
        builder.add_footer()

        return builder.build()

class OSPF6ConfigGenerator:
    """OSPF6配置生成器"""

    @staticmethod
    def generate(router_info: RouterInfo, config: TopologyConfig) -> str:
        """生成ospf6d配置"""
        # 如果OSPF6被禁用，返回空配置
        if not config.ospf_config:
            return ""

        builder = ConfigBuilder()

        # 添加头部
        builder.add_header(router_info.name, "OSPF6 configuration")

        # 添加日志配置
        if not config.disable_logging:
            builder.add_section("Logging", [
                "log file /var/log/frr/ospf6d.log debugging",
                "log commands",
            ])

        # 添加调试配置
        if not config.disable_logging:
            builder.add_section("Debug", [
                "debug ospf6 neighbor state",
                # "debug ospf6 spf process",
                # "debug ospf6 route table",
                # "debug ospf6 lsa unknown",
            ])

        # 添加OSPF配置
        ospf_section = create_ospf_section(router_info, config.ospf_config, router_info.interfaces, config)
        builder.sections.append(ospf_section)

        # 添加尾部
        builder.add_footer()

        return builder.build()

class BGPConfigGenerator:
    """BGP配置生成器"""

    @staticmethod
    def generate(router_info: RouterInfo, config: TopologyConfig, all_routers: List[RouterInfo] = None) -> str:
        """生成bgpd配置"""
        if not config.enable_bgp or not config.bgp_config:
            return ""

        builder = ConfigBuilder()

        # 添加头部
        builder.add_header(router_info.name, "BGP configuration")

        # 添加日志配置
        if not config.disable_logging:
            builder.add_section("Logging", [
                "log file /var/log/frr/bgpd.log debugging",
                "log commands",
            ])

        # 获取所有Gateway路由器（如果没有提供all_routers，则只包含当前路由器）
        gateway_routers = []
        if all_routers:
            gateway_routers = [r for r in all_routers if r.node_type == NodeType.GATEWAY]

        # 添加BGP配置
        bgp_section = create_bgp_section(router_info, config.bgp_config, gateway_routers, config)
        builder.sections.append(bgp_section)

        # 添加尾部
        builder.add_footer()

        return builder.build()

class BFDConfigGenerator:
    """BFD配置生成器"""

    @staticmethod
    def generate(router_info: RouterInfo, config: TopologyConfig) -> str:
        """生成bfdd配置"""
        if not config.enable_bfd:
            return ""

        builder = ConfigBuilder()

        # 添加头部
        builder.add_header(router_info.name, "BFD configuration")

        # 添加日志配置
        if not config.disable_logging:
            builder.add_section("Logging", [
                "log file /var/log/frr/bfdd.log debugging",
                "log commands",
            ])

        # 添加BFD配置
        bfd_section = create_bfd_section(config.bfd_config)
        builder.sections.append(bfd_section)

        # 添加尾部
        builder.add_footer()

        return builder.build()

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
