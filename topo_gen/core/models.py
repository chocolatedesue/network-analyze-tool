"""
现代化数据模型
使用 Pydantic v2 和最新特性
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Any, ClassVar
from pydantic import BaseModel, Field, ConfigDict, computed_field, field_validator, model_validator
from pydantic.networks import IPv6Address, IPv6Network
from enum import Enum
import ipaddress

from .types import (
    Coordinate, Direction, TopologyType, NodeType, ProtocolType,
    RouterName, InterfaceName, ASNumber, RouterID, NeighborMap, AreaID,
    IPv6AddressHelper, IPv6NetworkHelper, LinkAddress, TopologyStats,
    ValidationResult, Success, Failure
)
from pathlib import Path

class BaseConfig(BaseModel):
    """基础配置类"""
    model_config = ConfigDict(
        frozen=True,  # 不可变
        extra='forbid',  # 禁止额外字段
        validate_assignment=True,  # 赋值时验证
        use_enum_values=True,  # 使用枚举值
        str_strip_whitespace=True,  # 去除空白字符
    )

class NetworkConfig(BaseConfig):
    """网络配置"""
    ipv6_prefix: str = Field(default="2001:db8:1000::", description="IPv6前缀")
    loopback_prefix: str = Field(default="2001:db8:1000::", description="Loopback前缀")
    link_prefix: str = Field(default="2001:db8:2000::", description="链路前缀")
    subnet_mask: int = Field(default=127, ge=64, le=128, description="子网掩码长度")
    
    @field_validator('ipv6_prefix', 'loopback_prefix', 'link_prefix')
    @classmethod
    def validate_ipv6_prefix(cls, v: str) -> str:
        """验证IPv6前缀格式"""
        try:
            ipaddress.IPv6Network(f"{v}/64")
            return v
        except ValueError as e:
            raise ValueError(f"无效的IPv6前缀: {v}") from e

class OSPFConfig(BaseConfig):
    """OSPF配置 - 增强版"""
    hello_interval: int = Field(default=2, ge=1, le=65535, description="Hello间隔(秒)")
    dead_interval: int = Field(default=10, ge=1, le=65535, description="Dead间隔(秒)")
    spf_delay: int = Field(default=50, ge=1, le=65535, description="SPF延迟(毫秒)")
    area_id: AreaID = Field(default="0.0.0.0", description="区域ID")
    cost: Optional[int] = Field(default=None, ge=1, le=65535, description="接口开销")
    priority: Optional[int] = Field(default=None, ge=0, le=255, description="路由器优先级")

    # 新增字段
    retransmit_interval: int = Field(default=5, ge=1, le=3600, description="重传间隔(秒)")
    transmit_delay: int = Field(default=1, ge=1, le=3600, description="传输延迟(秒)")
    authentication_type: Optional[str] = Field(default=None, description="认证类型")
    lsa_min_arrival: int = Field(default=1000, ge=10, le=60000, description="LSA最小到达间隔(毫秒)")
    maximum_paths: int = Field(default=64, ge=1, le=128, description="ECMP最大路径数")

    @field_validator('dead_interval')
    @classmethod
    def validate_dead_interval(cls, v: int, info) -> int:
        """验证Dead间隔必须大于Hello间隔"""
        if 'hello_interval' in info.data and v <= info.data['hello_interval']:
            raise ValueError("Dead间隔必须大于Hello间隔")
        return v

    @computed_field
    @property
    def is_backbone_area(self) -> bool:
        """是否为骨干区域"""
        return self.area_id == "0.0.0.0"

    @computed_field
    @property
    def dead_to_hello_ratio(self) -> float:
        """Dead间隔与Hello间隔的比值"""
        return self.dead_interval / self.hello_interval

class BGPConfig(BaseConfig):
    """BGP配置 - 增强版"""
    as_number: ASNumber = Field(description="AS号")
    router_id: Optional[RouterID] = Field(default=None, description="路由器ID")
    enable_ipv6: bool = Field(default=True, description="启用IPv6")
    confederation_id: Optional[ASNumber] = Field(default=None, description="联邦ID")

    # 新增字段
    local_preference: int = Field(default=100, ge=0, le=4294967295, description="本地优先级")
    med: Optional[int] = Field(default=None, ge=0, le=4294967295, description="多出口判别器")
    hold_time: int = Field(default=180, ge=3, le=65535, description="保持时间(秒)")
    keepalive_time: int = Field(default=60, ge=1, le=21845, description="保活时间(秒)")
    connect_retry_time: int = Field(default=120, ge=1, le=65535, description="连接重试时间(秒)")

    @field_validator('as_number')
    @classmethod
    def validate_as_number(cls, v: int) -> int:
        """验证AS号范围"""
        if not (1 <= v <= 4294967295):  # 32位AS号范围
            raise ValueError(f"AS号必须在1-4294967295范围内: {v}")
        return v

    @field_validator('keepalive_time')
    @classmethod
    def validate_keepalive_time(cls, v: int, info) -> int:
        """验证保活时间必须小于保持时间的1/3"""
        if 'hold_time' in info.data and v >= info.data['hold_time'] / 3:
            raise ValueError("保活时间必须小于保持时间的1/3")
        return v

    @computed_field
    @property
    def is_private_as(self) -> bool:
        """是否为私有AS号"""
        return (64512 <= self.as_number <= 65534) or (4200000000 <= self.as_number <= 4294967294)

    @computed_field
    @property
    def as_type(self) -> str:
        """AS类型"""
        if self.is_private_as:
            return "private"
        elif 1 <= self.as_number <= 64511:
            return "public_16bit"
        else:
            return "public_32bit"

class BFDConfig(BaseConfig):
    """BFD配置 - 增强版"""
    enabled: bool = Field(default=False, description="是否启用BFD")
    detect_multiplier: int = Field(default=3, ge=1, le=255, description="检测倍数")
    receive_interval: int = Field(default=300, ge=10, le=60000, description="接收间隔(毫秒)")
    transmit_interval: int = Field(default=300, ge=10, le=60000, description="发送间隔(毫秒)")
    profile_name: str = Field(default="default", description="配置文件名")

    # 新增字段
    echo_mode: bool = Field(default=False, description="是否启用回显模式")
    echo_interval: int = Field(default=50, ge=10, le=60000, description="回显间隔(毫秒)")
    passive_mode: bool = Field(default=False, description="是否为被动模式")
    minimum_ttl: int = Field(default=1, ge=1, le=255, description="最小TTL值")

    @computed_field
    @property
    def detection_time_ms(self) -> int:
        """检测时间(毫秒)"""
        return self.receive_interval * self.detect_multiplier

    @computed_field
    @property
    def detection_time_seconds(self) -> float:
        """检测时间(秒)"""
        return self.detection_time_ms / 1000.0

    @field_validator('echo_interval')
    @classmethod
    def validate_echo_interval(cls, v: int, info) -> int:
        """验证回显间隔"""
        if 'receive_interval' in info.data and v > info.data['receive_interval']:
            raise ValueError("回显间隔不应大于接收间隔")
        return v

class RouterInfo(BaseConfig):
    """路由器信息 - 增强版"""
    name: RouterName = Field(description="路由器名称")
    coordinate: Coordinate = Field(description="坐标位置")
    node_type: NodeType = Field(description="节点类型")
    router_id: RouterID = Field(description="路由器ID")
    loopback_ipv6: IPv6Address = Field(description="Loopback IPv6地址")
    interfaces: Dict[InterfaceName, IPv6Address] = Field(default_factory=dict, description="接口地址映射")
    neighbors: Dict[Direction, Coordinate] = Field(default_factory=dict, description="邻居映射")
    area_id: AreaID = Field(default="0.0.0.0", description="OSPF区域ID")
    as_number: Optional[ASNumber] = Field(default=None, description="BGP AS号")

    # 新增字段
    management_ip: Optional[IPv6Address] = Field(default=None, description="管理IP地址")
    description: Optional[str] = Field(default=None, max_length=255, description="路由器描述")
    vendor: Optional[str] = Field(default="generic", description="设备厂商")
    model: Optional[str] = Field(default="router", description="设备型号")

    @computed_field
    @property
    def neighbor_count(self) -> int:
        """邻居数量"""
        return len(self.neighbors)

    @computed_field
    @property
    def interface_count(self) -> int:
        """接口数量"""
        return len(self.interfaces)

    @computed_field
    @property
    def neighbor_map(self) -> NeighborMap:
        """获取邻居映射对象"""
        return NeighborMap.from_dict(self.neighbors)

    @computed_field
    @property
    def loopback_helper(self) -> IPv6AddressHelper:
        """Loopback地址助手"""
        return IPv6AddressHelper.from_string(self.loopback_ipv6)

    @computed_field
    @property
    def is_border_router(self) -> bool:
        """是否为边界路由器"""
        return self.node_type in {NodeType.CORNER, NodeType.EDGE, NodeType.GATEWAY}

    @computed_field
    @property
    def is_special_node(self) -> bool:
        """是否为特殊节点"""
        return self.node_type.is_special

    def get_interface_for_direction(self, direction: Direction) -> Optional[str]:
        """获取指定方向的接口地址"""
        from .types import get_interface_for_direction
        interface_name = get_interface_for_direction(direction)
        return self.interfaces.get(interface_name)

    def has_neighbor_in_direction(self, direction: Direction) -> bool:
        """检查指定方向是否有邻居"""
        return direction in self.neighbors

    def get_neighbor_coordinate(self, direction: Direction) -> Optional[Coordinate]:
        """获取指定方向的邻居坐标"""
        return self.neighbors.get(direction)

class LinkInfo(BaseConfig):
    """链路信息 - 增强版"""
    router1_name: RouterName = Field(description="路由器1名称")
    router2_name: RouterName = Field(description="路由器2名称")
    router1_coord: Coordinate = Field(description="路由器1坐标")
    router2_coord: Coordinate = Field(description="路由器2坐标")
    router1_interface: InterfaceName = Field(description="路由器1接口")
    router2_interface: InterfaceName = Field(description="路由器2接口")
    router1_ipv6: IPv6Address = Field(description="路由器1 IPv6地址")
    router2_ipv6: IPv6Address = Field(description="路由器2 IPv6地址")
    network: IPv6Network = Field(description="网络地址")

    # 新增字段
    bandwidth: Optional[int] = Field(default=None, ge=1, description="带宽(Mbps)")
    delay: Optional[int] = Field(default=None, ge=0, description="延迟(微秒)")
    cost: Optional[int] = Field(default=None, ge=1, le=65535, description="链路开销")
    description: Optional[str] = Field(default=None, max_length=255, description="链路描述")

    @computed_field
    @property
    def link_id(self) -> str:
        """链路唯一标识"""
        coords = sorted([self.router1_coord, self.router2_coord], key=lambda c: (c.row, c.col))
        return f"{coords[0]}_{coords[1]}"

    @computed_field
    @property
    def link_address(self) -> LinkAddress:
        """获取链路地址对象"""
        return LinkAddress(
            network=self.network,
            router1_addr=self.router1_ipv6,
            router2_addr=self.router2_ipv6,
            router1_name=self.router1_name,
            router2_name=self.router2_name
        )

    @computed_field
    @property
    def is_horizontal(self) -> bool:
        """是否为水平链路"""
        return self.router1_coord.row == self.router2_coord.row

    @computed_field
    @property
    def is_vertical(self) -> bool:
        """是否为垂直链路"""
        return self.router1_coord.col == self.router2_coord.col

    @computed_field
    @property
    def manhattan_distance(self) -> int:
        """曼哈顿距离"""
        return self.router1_coord.manhattan_distance_to(self.router2_coord)

    @computed_field
    @property
    def is_adjacent(self) -> bool:
        """是否为相邻链路"""
        return self.manhattan_distance == 1

    def get_peer_info(self, router_name: str) -> tuple[str, str, Coordinate]:
        """获取对端路由器信息"""
        if router_name == self.router1_name:
            return self.router2_name, self.router2_ipv6, self.router2_coord
        elif router_name == self.router2_name:
            return self.router1_name, self.router1_ipv6, self.router1_coord
        else:
            raise ValueError(f"路由器 {router_name} 不在此链路上")

class SpecialTopologyConfig(BaseConfig):
    """特殊拓扑配置"""
    source_node: Coordinate = Field(description="源节点坐标")
    dest_node: Coordinate = Field(description="目标节点坐标")
    gateway_nodes: Set[Coordinate] = Field(description="网关节点集合")
    internal_bridge_edges: List[tuple[Coordinate, Coordinate]] = Field(description="内部桥接边")
    torus_bridge_edges: List[tuple[Coordinate, Coordinate]] = Field(description="Torus桥接边")
    base_topology: TopologyType = Field(description="基础拓扑类型")
    include_base_connections: bool = Field(default=True, description="是否包含基础连接")
    
    @classmethod
    def create_dm6_6_sample(
        cls,
        base_topology: TopologyType = TopologyType.TORUS,
        include_base_connections: bool = True
    ) -> SpecialTopologyConfig:
        """创建6x6示例配置"""
        return cls(
            source_node=Coordinate(1, 4),
            dest_node=Coordinate(4, 1),
            gateway_nodes={
                Coordinate(0, 1), Coordinate(0, 4), Coordinate(1, 0), Coordinate(1, 2),
                Coordinate(1, 3), Coordinate(1, 5), Coordinate(2, 1), Coordinate(2, 4),
                Coordinate(3, 1), Coordinate(3, 4), Coordinate(4, 0), Coordinate(4, 2),
                Coordinate(4, 3), Coordinate(4, 5), Coordinate(5, 1), Coordinate(5, 4)
            },
            internal_bridge_edges=[
                (Coordinate(1, 2), Coordinate(1, 3)),
                (Coordinate(4, 2), Coordinate(4, 3)),
                (Coordinate(2, 1), Coordinate(3, 1)),
                (Coordinate(2, 4), Coordinate(3, 4)),
            ],
            torus_bridge_edges=[
                (Coordinate(0, 1), Coordinate(5, 1)),
                (Coordinate(0, 4), Coordinate(5, 4)),
                (Coordinate(1, 0), Coordinate(1, 5)),
                (Coordinate(4, 0), Coordinate(4, 5)),
            ],
            base_topology=base_topology,
            include_base_connections=include_base_connections
        )

class TopologyConfig(BaseConfig):
    """拓扑配置"""
    size: int = Field(ge=2, le=100, description="网格大小")
    topology_type: TopologyType = Field(description="拓扑类型")
    multi_area: bool = Field(default=False, description="是否多区域")
    area_size: Optional[int] = Field(default=None, ge=2, description="区域大小")

    # 协议配置
    network_config: NetworkConfig = Field(default_factory=NetworkConfig, description="网络配置")
    ospf_config: Optional[OSPFConfig] = Field(default_factory=OSPFConfig, description="OSPF配置")
    bgp_config: Optional[BGPConfig] = Field(default=None, description="BGP配置")
    bfd_config: BFDConfig = Field(default_factory=BFDConfig, description="BFD配置")

    # 守护进程控制
    daemons_off: bool = Field(default=False, description="仅关闭守护进程但仍生成对应配置文件")
    bgpd_off: bool = Field(default=False, description="仅关闭 BGP 守护进程")
    ospf6d_off: bool = Field(default=False, description="仅关闭 OSPF6 守护进程")
    bfdd_off: bool = Field(default=False, description="仅关闭 BFD 守护进程")

    # Dummy 生成控制（将真实配置保存为 -bak.conf，并生成空配置作为主文件）
    dummy_gen_protocols: Set[str] = Field(default_factory=set, description="需要生成空配置的协议集合，支持: ospf6d/bgpd/bfdd")

    # 日志控制
    disable_logging: bool = Field(default=False, description="禁用所有配置文件中的日志记录")

    @field_validator('dummy_gen_protocols')
    @classmethod
    def validate_dummy_gen_protocols(cls, v: Set[str]) -> Set[str]:
        """验证 dummy 生成协议名称"""
        valid_protocols = {"ospf6d", "bgpd", "bfdd"}
        if v:
            invalid_protocols = v - valid_protocols
            if invalid_protocols:
                raise ValueError(f"无效的协议名称: {', '.join(sorted(invalid_protocols))}。支持的协议: {', '.join(sorted(valid_protocols))}")
        return v

    # 输出目录（可选），若未设置则使用默认命名规则
    output_dir: Optional[Path] = Field(default=None, description="自定义输出目录")

    # 特殊拓扑配置
    special_config: Optional[SpecialTopologyConfig] = Field(default=None, description="特殊拓扑配置")

    @field_validator('area_size')
    @classmethod
    def validate_area_size(cls, v: Optional[int], info) -> Optional[int]:
        """验证区域大小"""
        if v is not None and 'size' in info.data and v > info.data['size']:
            raise ValueError("区域大小不能大于网格大小")
        return v
    
    @model_validator(mode='after')
    def validate_special_config(self) -> TopologyConfig:
        """验证特殊拓扑配置"""
        if self.topology_type == TopologyType.SPECIAL and self.special_config is None:
            raise ValueError("特殊拓扑必须提供special_config")
        return self
    
    @computed_field
    @property
    def total_routers(self) -> int:
        """总路由器数量"""
        return self.size * self.size
    
    @computed_field
    @property
    def total_links(self) -> int:
        """总链路数量"""
        if self.topology_type == TopologyType.TORUS:
            return self.size * self.size * 2
        elif self.topology_type == TopologyType.GRID:
            return 2 * self.size * (self.size - 1)
        elif self.topology_type == TopologyType.SPECIAL and self.special_config:
            base_links = 0
            if self.special_config.include_base_connections:
                if self.special_config.base_topology == TopologyType.TORUS:
                    base_links = self.size * self.size * 2
                else:
                    base_links = 2 * self.size * (self.size - 1)
            return base_links + len(self.special_config.internal_bridge_edges) + len(self.special_config.torus_bridge_edges)
        return 0

    @computed_field
    @property
    def topology_stats(self) -> TopologyStats:
        """获取拓扑统计信息"""
        # 计算节点类型分布
        corner_nodes = 0
        edge_nodes = 0
        internal_nodes = 0
        special_nodes = 0

        if self.topology_type == TopologyType.GRID:
            corner_nodes = 4
            edge_nodes = 4 * (self.size - 2) if self.size > 2 else 0
            internal_nodes = max(0, (self.size - 2) ** 2)
        elif self.topology_type == TopologyType.TORUS:
            internal_nodes = self.size * self.size
        elif self.topology_type == TopologyType.SPECIAL and self.special_config:
            special_nodes = len(self.special_config.gateway_nodes) + 2  # +2 for source and dest
            internal_nodes = self.total_routers - special_nodes

        return TopologyStats(
            total_routers=self.total_routers,
            total_links=self.total_links,
            topology_type=self.topology_type,
            size=self.size,
            corner_nodes=corner_nodes,
            edge_nodes=edge_nodes,
            internal_nodes=internal_nodes,
            special_nodes=special_nodes
        )
    
    @computed_field
    @property
    def enable_bfd(self) -> bool:
        """是否启用BFD"""
        return self.bfd_config.enabled
    
    @computed_field
    @property
    def enable_bgp(self) -> bool:
        """是否启用BGP"""
        return self.bgp_config is not None

class SystemRequirements(BaseConfig):
    """系统需求"""
    min_memory_gb: float = Field(description="最小内存需求(GB)")
    recommended_memory_gb: float = Field(description="推荐内存需求(GB)")
    max_workers_config: int = Field(default=6, ge=1, le=32, description="配置生成最大工作线程")
    max_workers_filesystem: int = Field(default=4, ge=1, le=16, description="文件系统最大工作线程")
    
    @classmethod
    def calculate_for_topology(cls, config: TopologyConfig) -> SystemRequirements:
        """根据拓扑配置计算系统需求"""
        base_memory = config.total_routers * 0.045  # 每个路由器45MB
        if config.enable_bgp:
            base_memory *= 1.5  # BGP增加50%内存需求
        if config.enable_bfd:
            base_memory *= 1.2  # BFD增加20%内存需求
            
        return cls(
            min_memory_gb=base_memory,
            recommended_memory_gb=base_memory * 1.5,
            max_workers_config=min(6, max(1, config.total_routers // 50)),
            max_workers_filesystem=min(4, max(1, config.total_routers // 100))
        )

class GenerationResult(BaseConfig):
    """生成结果，支持位置参数和关键字参数"""
    success: bool = Field(description="是否成功")
    message: str = Field(description="结果消息")
    output_dir: Optional[Path] = Field(default=None, description="输出目录")
    error_details: Optional[str] = Field(default=None, description="错误详情")
    stats: Optional[Dict[str, Any]] = Field(default=None, description="生成统计信息")
    errors: Optional[List[str]] = Field(default=None, description="错误列表")

    def __init__(self, *args, **kwargs):
        """支持位置参数和关键字参数的构造函数

        支持的调用方式：
        - GenerationResult(success, message)  # 位置参数
        - GenerationResult(success, message, output_dir)  # 位置参数
        - GenerationResult(success=success, message=message)  # 关键字参数
        """
        if len(args) == 2 and not kwargs:
            # 位置参数调用: GenerationResult(success, message)
            super().__init__(success=args[0], message=args[1])
        elif len(args) == 3 and not kwargs:
            # 位置参数调用: GenerationResult(success, message, output_dir)
            super().__init__(success=args[0], message=args[1], output_dir=args[2])
        elif len(args) == 0:
            # 关键字参数调用: GenerationResult(success=success, message=message)
            super().__init__(**kwargs)
        else:
            raise TypeError(f"Invalid arguments for GenerationResult: args={args}, kwargs={kwargs}")
