"""
现代化类型定义模块
使用 Pydantic v2 提供类型安全、验证和序列化功能
"""

from __future__ import annotations

from typing import Dict, List, Optional, Union, Protocol, runtime_checkable, Any, Annotated
from enum import Enum
from pathlib import Path
import ipaddress
from pydantic import BaseModel, Field, ConfigDict, field_validator, computed_field
from pydantic.types import PositiveInt

# 基础 Pydantic 配置
class BaseTypeModel(BaseModel):
    """基础类型模型配置"""
    model_config = ConfigDict(
        frozen=True,  # 不可变
        extra='forbid',  # 禁止额外字段
        validate_assignment=True,  # 赋值时验证
        use_enum_values=True,  # 使用枚举值
        str_strip_whitespace=True,  # 去除空白字符
        arbitrary_types_allowed=True,  # 允许任意类型
    )

# 基础类型定义 - 使用 Pydantic 约束类型
RouterName = Annotated[str, Field(min_length=1, max_length=64, pattern=r'^[a-zA-Z0-9_-]+$')]
InterfaceName = Annotated[str, Field(min_length=1, max_length=32, pattern=r'^[a-zA-Z0-9_-]+$')]
IPv6Address = Annotated[str, Field(description="IPv6地址")]
IPv6Network = Annotated[str, Field(description="IPv6网络")]
ASNumber = Annotated[int, Field(ge=1, le=4294967295, description="BGP AS号")]
RouterID = Annotated[str, Field(pattern=r'^\d+\.\d+\.\d+\.\d+$', description="路由器ID")]
AreaID = Annotated[str, Field(pattern=r'^\d+\.\d+\.\d+\.\d+$', description="OSPF区域ID")]

# 向量类型 - 用于方向向量，允许负值
class Vector(BaseTypeModel):
    """不可变向量类型，用于方向向量，允许负值"""
    row: Annotated[int, Field(ge=-99, le=99, description="行向量分量")]
    col: Annotated[int, Field(ge=-99, le=99, description="列向量分量")]

    def __new__(cls, *args, **kwargs):
        """重写 __new__ 方法以支持位置参数"""
        # 处理位置参数
        if len(args) == 2 and not kwargs:
            # 位置参数调用: Vector(1, 2)
            kwargs = {'row': args[0], 'col': args[1]}
            args = ()
        elif len(args) == 1 and not kwargs:
            # 单个参数，可能是元组或列表
            arg = args[0]
            if isinstance(arg, (tuple, list)) and len(arg) == 2:
                kwargs = {'row': arg[0], 'col': arg[1]}
                args = ()
            else:
                raise TypeError(f"Cannot create Vector from single argument: {arg}")
        elif len(args) > 2:
            raise TypeError(f"Vector() takes at most 2 positional arguments but {len(args)} were given")

        # 创建实例
        instance = super().__new__(cls)
        return instance

    def __init__(self, *args, **kwargs):
        """初始化方法"""
        # 处理位置参数
        if len(args) == 2 and not kwargs:
            # 位置参数调用: Vector(1, 2)
            super().__init__(row=args[0], col=args[1])
        elif len(args) == 1 and not kwargs:
            # 单个参数，可能是元组或列表
            arg = args[0]
            if isinstance(arg, (tuple, list)) and len(arg) == 2:
                super().__init__(row=arg[0], col=arg[1])
            else:
                raise TypeError(f"Cannot create Vector from single argument: {arg}")
        elif len(args) == 0:
            # 关键字参数调用: Vector(row=1, col=2)
            super().__init__(**kwargs)
        else:
            raise TypeError(f"Invalid arguments for Vector: args={args}, kwargs={kwargs}")

    def __str__(self) -> str:
        return f"({self.row},{self.col})"

    def __hash__(self) -> int:
        return hash((self.row, self.col))

# 坐标类型 - 使用 Pydantic 模型，支持位置参数
class Coordinate(BaseTypeModel):
    """不可变坐标类型，带验证，支持位置参数和关键字参数"""
    row: Annotated[int, Field(ge=0, le=99, description="行坐标")]
    col: Annotated[int, Field(ge=0, le=99, description="列坐标")]

    def __new__(cls, *args, **kwargs):
        """重写 __new__ 方法以支持位置参数"""
        # 处理位置参数
        if len(args) == 2 and not kwargs:
            # 位置参数调用: Coordinate(1, 2)
            kwargs = {'row': args[0], 'col': args[1]}
            args = ()
        elif len(args) == 1 and not kwargs:
            # 单个参数，可能是元组或列表
            arg = args[0]
            if isinstance(arg, (tuple, list)) and len(arg) == 2:
                kwargs = {'row': arg[0], 'col': arg[1]}
                args = ()
            else:
                raise TypeError(f"Cannot create Coordinate from single argument: {arg}")
        elif len(args) > 2:
            raise TypeError(f"Coordinate() takes at most 2 positional arguments but {len(args)} were given")

        # 创建实例
        instance = super().__new__(cls)
        return instance

    def __init__(self, *args, **kwargs):
        """初始化方法"""
        # 处理位置参数
        if len(args) == 2 and not kwargs:
            # 位置参数调用: Coordinate(1, 2)
            super().__init__(row=args[0], col=args[1])
        elif len(args) == 1 and not kwargs:
            # 单个参数，可能是元组或列表
            arg = args[0]
            if isinstance(arg, (tuple, list)) and len(arg) == 2:
                super().__init__(row=arg[0], col=arg[1])
            else:
                raise TypeError(f"Cannot create Coordinate from single argument: {arg}")
        elif len(args) == 0:
            # 关键字参数调用: Coordinate(row=1, col=2)
            super().__init__(**kwargs)
        else:
            raise TypeError(f"Invalid arguments for Coordinate: args={args}, kwargs={kwargs}")

    def __str__(self) -> str:
        return f"({self.row},{self.col})"

    def __hash__(self) -> int:
        return hash((self.row, self.col))

    def __add__(self, other: Union['Coordinate', 'Vector']) -> 'Coordinate':
        """支持与坐标或向量相加

        注意：这个方法可能产生无效坐标（负值），调用者需要处理边界检查
        """
        new_row = self.row + other.row
        new_col = self.col + other.col

        # 如果结果坐标无效，抛出异常而不是创建无效对象
        if new_row < 0 or new_col < 0:
            raise ValueError(f"坐标加法结果无效: ({self.row},{self.col}) + ({other.row},{other.col}) = ({new_row},{new_col})")

        return Coordinate(new_row, new_col)

    def __sub__(self, other: 'Coordinate') -> 'Coordinate':
        return Coordinate(self.row - other.row, self.col - other.col)

    @computed_field
    @property
    def manhattan_distance_from_origin(self) -> int:
        """计算到原点的曼哈顿距离"""
        return abs(self.row) + abs(self.col)

    def manhattan_distance_to(self, other: 'Coordinate') -> int:
        """计算到另一个坐标的曼哈顿距离"""
        return abs(self.row - other.row) + abs(self.col - other.col)

    def is_adjacent_to(self, other: 'Coordinate') -> bool:
        """检查是否与另一个坐标相邻"""
        return self.manhattan_distance_to(other) == 1

    @classmethod
    def from_tuple(cls, coord_tuple: tuple[int, int]) -> 'Coordinate':
        """从元组创建坐标"""
        return cls(coord_tuple[0], coord_tuple[1])

    @classmethod
    def from_dict(cls, coord_dict: dict) -> 'Coordinate':
        """从字典创建坐标"""
        return cls(row=coord_dict['row'], col=coord_dict['col'])

# 方向枚举 - 增强功能
class Direction(str, Enum):
    """方向枚举，支持字符串序列化"""
    NORTH = "north"
    SOUTH = "south"
    WEST = "west"
    EAST = "east"

    @property
    def opposite(self) -> 'Direction':
        """获取相反方向"""
        opposites = {
            Direction.NORTH: Direction.SOUTH,
            Direction.SOUTH: Direction.NORTH,
            Direction.WEST: Direction.EAST,
            Direction.EAST: Direction.WEST,
        }
        return opposites[self]

    @property
    def vector(self) -> Vector:
        """获取方向向量"""
        vectors = {
            Direction.NORTH: Vector(row=-1, col=0),
            Direction.SOUTH: Vector(row=1, col=0),
            Direction.WEST: Vector(row=0, col=-1),
            Direction.EAST: Vector(row=0, col=1),
        }
        return vectors[self]

    @property
    def angle_degrees(self) -> int:
        """获取方向角度（度）"""
        angles = {
            Direction.NORTH: 0,
            Direction.EAST: 90,
            Direction.SOUTH: 180,
            Direction.WEST: 270,
        }
        return angles[self]

    def rotate_clockwise(self) -> 'Direction':
        """顺时针旋转90度"""
        rotations = {
            Direction.NORTH: Direction.EAST,
            Direction.EAST: Direction.SOUTH,
            Direction.SOUTH: Direction.WEST,
            Direction.WEST: Direction.NORTH,
        }
        return rotations[self]

    def rotate_counterclockwise(self) -> 'Direction':
        """逆时针旋转90度"""
        rotations = {
            Direction.NORTH: Direction.WEST,
            Direction.WEST: Direction.SOUTH,
            Direction.SOUTH: Direction.EAST,
            Direction.EAST: Direction.NORTH,
        }
        return rotations[self]

# 拓扑类型
class TopologyType(str, Enum):
    """拓扑类型枚举"""
    GRID = "grid"
    TORUS = "torus"
    SPECIAL = "special"

    @property
    def description(self) -> str:
        """获取拓扑类型描述"""
        descriptions = {
            TopologyType.GRID: "网格拓扑 - 二维网格结构",
            TopologyType.TORUS: "环形拓扑 - 环绕连接的网格",
            TopologyType.SPECIAL: "特殊拓扑 - 自定义连接模式",
        }
        return descriptions[self]

    @property
    def max_neighbors(self) -> int:
        """获取最大邻居数"""
        max_neighbors = {
            TopologyType.GRID: 4,  # 最多4个邻居（内部节点）
            TopologyType.TORUS: 4,  # 所有节点都有4个邻居
            TopologyType.SPECIAL: 8,  # 特殊拓扑可能有更多连接
        }
        return max_neighbors[self]

# 节点类型
class NodeType(str, Enum):
    """节点类型枚举"""
    CORNER = "corner"
    EDGE = "edge"
    INTERNAL = "internal"
    GATEWAY = "gateway"
    SOURCE = "source"
    DESTINATION = "destination"

    @property
    def description(self) -> str:
        """获取节点类型描述"""
        descriptions = {
            NodeType.CORNER: "角点节点 - 位于网格角落",
            NodeType.EDGE: "边缘节点 - 位于网格边缘",
            NodeType.INTERNAL: "内部节点 - 位于网格内部",
            NodeType.GATEWAY: "网关节点 - 特殊拓扑中的网关",
            NodeType.SOURCE: "源节点 - 特殊拓扑中的源",
            NodeType.DESTINATION: "目标节点 - 特殊拓扑中的目标",
        }
        return descriptions[self]

    @property
    def is_special(self) -> bool:
        """是否为特殊节点类型"""
        return self in {NodeType.GATEWAY, NodeType.SOURCE, NodeType.DESTINATION}

# 协议类型
class ProtocolType(str, Enum):
    """协议类型枚举"""
    OSPFV3 = "ospfv3"
    BGP = "bgp"
    BFD = "bfd"
    STATIC = "static"

    @property
    def description(self) -> str:
        """获取协议描述"""
        descriptions = {
            ProtocolType.OSPFV3: "OSPFv3 - IPv6开放最短路径优先协议",
            ProtocolType.BGP: "BGP - 边界网关协议",
            ProtocolType.BFD: "BFD - 双向转发检测",
            ProtocolType.STATIC: "静态路由",
        }
        return descriptions[self]

    @property
    def default_port(self) -> Optional[int]:
        """获取协议默认端口"""
        ports = {
            ProtocolType.OSPFV3: None,  # OSPF使用IP协议89
            ProtocolType.BGP: 179,
            ProtocolType.BFD: 3784,
            ProtocolType.STATIC: None,
        }
        return ports[self]

# 邻居映射类型 - 使用 Pydantic 模型
class NeighborMap(BaseTypeModel):
    """邻居映射模型"""
    neighbors: Dict[Direction, Any] = Field(default_factory=dict, description="方向到坐标的映射")

    def __getitem__(self, direction: Direction):
        return self.neighbors[direction]

    def __setitem__(self, direction: Direction, coordinate) -> None:
        # 由于模型是frozen的，这里会抛出异常，这是期望的行为
        raise TypeError("NeighborMap is immutable")

    def __contains__(self, direction: Direction) -> bool:
        return direction in self.neighbors

    def __iter__(self):
        return iter(self.neighbors)

    def __len__(self) -> int:
        return len(self.neighbors)

    def items(self):
        return self.neighbors.items()

    def values(self):
        return self.neighbors.values()

    def keys(self):
        return self.neighbors.keys()

    def get(self, direction: Direction, default=None):
        return self.neighbors.get(direction, default)

    @classmethod
    def from_dict(cls, neighbors: Dict[Direction, Any]) -> 'NeighborMap':
        """从字典创建邻居映射"""
        return cls(neighbors=neighbors)

# 接口映射类型
InterfaceMap = Dict[InterfaceName, IPv6Address]
RouterInterfaces = Dict[RouterName, InterfaceMap]

# 链路类型 - 使用 Pydantic 模型，支持位置参数
class Link(BaseTypeModel):
    """网络链路模型，带验证，支持位置参数和关键字参数"""
    router1: Coordinate = Field(description="第一个路由器坐标")
    router2: Coordinate = Field(description="第二个路由器坐标")
    direction1: Direction = Field(description="第一个路由器的方向")
    direction2: Direction = Field(description="第二个路由器的方向")
    network: IPv6Network = Field(description="链路网络地址")

    def __init__(self, *args, **kwargs):
        """支持位置参数和关键字参数的构造函数

        支持的调用方式：
        - Link(router1, router2, direction1, direction2, network)  # 位置参数
        - Link(router1=router1, router2=router2, ...)  # 关键字参数
        """
        if len(args) == 5 and not kwargs:
            # 位置参数调用: Link(router1, router2, direction1, direction2, network)
            super().__init__(
                router1=args[0],
                router2=args[1],
                direction1=args[2],
                direction2=args[3],
                network=args[4]
            )
        elif len(args) == 0:
            # 关键字参数调用: Link(router1=router1, router2=router2, ...)
            super().__init__(**kwargs)
        else:
            raise TypeError(f"Link() takes 0 or 5 positional arguments but {len(args)} were given")

    @field_validator('direction2')
    @classmethod
    def validate_direction_consistency(cls, v: Direction, info) -> Direction:
        """验证方向一致性"""
        if 'direction1' in info.data:
            direction1 = info.data['direction1']
            if direction1.opposite != v:
                raise ValueError(f"方向不一致: {direction1} vs {v}")
        return v

    @field_validator('router2')
    @classmethod
    def validate_routers_different(cls, v: Coordinate, info) -> Coordinate:
        """验证路由器不同"""
        if 'router1' in info.data and info.data['router1'] == v:
            raise ValueError("链路的两个路由器不能相同")
        return v

    @computed_field
    @property
    def link_id(self) -> str:
        """链路唯一标识"""
        coords = sorted([self.router1, self.router2], key=lambda c: (c.row, c.col))
        return f"{coords[0]}_{coords[1]}"

    @computed_field
    @property
    def is_horizontal(self) -> bool:
        """是否为水平链路"""
        return self.router1.row == self.router2.row

    @computed_field
    @property
    def is_vertical(self) -> bool:
        """是否为垂直链路"""
        return self.router1.col == self.router2.col

    def get_other_router(self, router: Coordinate) -> Coordinate:
        """获取链路另一端的路由器"""
        if router == self.router1:
            return self.router2
        elif router == self.router2:
            return self.router1
        else:
            raise ValueError(f"路由器 {router} 不在此链路上")

    def get_direction_for_router(self, router: Coordinate) -> Direction:
        """获取指定路由器在此链路上的方向"""
        if router == self.router1:
            return self.direction1
        elif router == self.router2:
            return self.direction2
        else:
            raise ValueError(f"路由器 {router} 不在此链路上")

# 配置字典类型 - 使用简单的字典类型注解
OSPFConfigDict = Dict[str, Union[int, str]]
BGPConfigDict = Dict[str, Union[int, str, List[str]]]

# 协议接口
@runtime_checkable
class TopologyProtocol(Protocol):
    """拓扑生成协议"""
    
    def get_neighbors(self, coord: Coordinate, size: int) -> NeighborMap:
        """获取邻居节点"""
        ...
    
    def get_node_type(self, coord: Coordinate, size: int) -> NodeType:
        """获取节点类型"""
        ...
    
    def calculate_total_links(self, size: int) -> int:
        """计算总链路数"""
        ...

@runtime_checkable
class ConfigGeneratorProtocol(Protocol):
    """配置生成器协议"""
    
    def generate_config(self, router_name: RouterName, **kwargs: Any) -> str:
        """生成配置"""
        ...

# 结果类型 - 使用 Pydantic 模型，支持位置参数
class Success(BaseTypeModel):
    """成功结果模型，支持位置参数和关键字参数"""
    value: Any = Field(description="成功返回的值")
    message: Optional[str] = Field(default=None, description="成功消息")

    def __init__(self, *args, **kwargs):
        """支持位置参数和关键字参数的构造函数

        支持的调用方式：
        - Success(value)  # 位置参数
        - Success(value, message)  # 位置参数
        - Success(value=value, message=message)  # 关键字参数
        """
        if len(args) == 1 and not kwargs:
            # 位置参数调用: Success(value)
            super().__init__(value=args[0])
        elif len(args) == 2 and not kwargs:
            # 位置参数调用: Success(value, message)
            super().__init__(value=args[0], message=args[1])
        elif len(args) == 0:
            # 关键字参数调用: Success(value=value, message=message)
            super().__init__(**kwargs)
        else:
            raise TypeError(f"Invalid arguments for Success: args={args}, kwargs={kwargs}")

    @computed_field
    @property
    def is_success(self) -> bool:
        return True

class Failure(BaseTypeModel):
    """失败结果模型，支持位置参数和关键字参数"""
    error: str = Field(description="错误信息")
    error_code: Optional[str] = Field(default=None, description="错误代码")
    details: Optional[Dict[str, Any]] = Field(default=None, description="错误详情")

    def __init__(self, *args, **kwargs):
        """支持位置参数和关键字参数的构造函数

        支持的调用方式：
        - Failure(error)  # 位置参数
        - Failure(error, error_code)  # 位置参数
        - Failure(error, error_code, details)  # 位置参数
        - Failure(error=error, error_code=error_code)  # 关键字参数
        """
        if len(args) == 1 and not kwargs:
            # 位置参数调用: Failure(error)
            super().__init__(error=args[0])
        elif len(args) == 2 and not kwargs:
            # 位置参数调用: Failure(error, error_code)
            super().__init__(error=args[0], error_code=args[1])
        elif len(args) == 3 and not kwargs:
            # 位置参数调用: Failure(error, error_code, details)
            super().__init__(error=args[0], error_code=args[1], details=args[2])
        elif len(args) == 0:
            # 关键字参数调用: Failure(error=error, error_code=error_code)
            super().__init__(**kwargs)
        else:
            raise TypeError(f"Invalid arguments for Failure: args={args}, kwargs={kwargs}")

    @computed_field
    @property
    def is_success(self) -> bool:
        return False

    @classmethod
    def from_exception(cls, exc: Exception, error_code: Optional[str] = None) -> 'Failure':
        """从异常创建失败结果"""
        return cls(
            error=str(exc),
            error_code=error_code or exc.__class__.__name__,
            details={"exception_type": exc.__class__.__name__}
        )

Result = Union[Success, Failure]

# 验证结果类型 - 使用 Pydantic 模型，支持位置参数
class ValidationResult(BaseTypeModel):
    """验证结果模型，支持位置参数和关键字参数"""
    valid: bool = Field(description="是否验证通过")
    errors: List[str] = Field(default_factory=list, description="错误列表")
    warnings: List[str] = Field(default_factory=list, description="警告列表")

    def __init__(self, *args, **kwargs):
        """支持位置参数和关键字参数的构造函数

        支持的调用方式：
        - ValidationResult(valid)  # 位置参数
        - ValidationResult(valid, errors)  # 位置参数
        - ValidationResult(valid, errors, warnings)  # 位置参数
        - ValidationResult(valid=valid, errors=errors)  # 关键字参数
        """
        if len(args) == 1 and not kwargs:
            # 位置参数调用: ValidationResult(valid)
            super().__init__(valid=args[0])
        elif len(args) == 2 and not kwargs:
            # 位置参数调用: ValidationResult(valid, errors)
            super().__init__(valid=args[0], errors=args[1])
        elif len(args) == 3 and not kwargs:
            # 位置参数调用: ValidationResult(valid, errors, warnings)
            super().__init__(valid=args[0], errors=args[1], warnings=args[2])
        elif len(args) == 0:
            # 关键字参数调用: ValidationResult(valid=valid, errors=errors)
            super().__init__(**kwargs)
        else:
            raise TypeError(f"Invalid arguments for ValidationResult: args={args}, kwargs={kwargs}")

    @computed_field
    @property
    def has_errors(self) -> bool:
        """是否有错误"""
        return len(self.errors) > 0

    @computed_field
    @property
    def has_warnings(self) -> bool:
        """是否有警告"""
        return len(self.warnings) > 0

    @computed_field
    @property
    def error_count(self) -> int:
        """错误数量"""
        return len(self.errors)

    @computed_field
    @property
    def warning_count(self) -> int:
        """警告数量"""
        return len(self.warnings)

    def add_error(self, error: str) -> None:
        """添加错误（注意：由于frozen=True，这会失败）"""
        raise TypeError("ValidationResult is immutable. Create a new instance instead.")

    def add_warning(self, warning: str) -> None:
        """添加警告（注意：由于frozen=True，这会失败）"""
        raise TypeError("ValidationResult is immutable. Create a new instance instead.")

    @classmethod
    def create_valid(cls, warnings: Optional[List[str]] = None) -> 'ValidationResult':
        """创建有效的验证结果"""
        return cls(valid=True, warnings=warnings or [])

    @classmethod
    def create_invalid(cls, errors: List[str], warnings: Optional[List[str]] = None) -> 'ValidationResult':
        """创建无效的验证结果"""
        return cls(valid=False, errors=errors, warnings=warnings or [])

# 配置构建器类型 - 使用 Pydantic 模型
class ConfigBuilder(BaseTypeModel):
    """配置构建器模型"""
    name: str = Field(description="构建器名称")
    description: Optional[str] = Field(default=None, description="构建器描述")
    priority: int = Field(default=0, description="执行优先级")
    enabled: bool = Field(default=True, description="是否启用")

    @computed_field
    @property
    def identifier(self) -> str:
        """构建器标识符"""
        return f"{self.name}_{self.priority}"

ConfigPipeline = List[ConfigBuilder]

# 文件操作类型 - 使用 Pydantic 约束类型
FileContent = Annotated[str, Field(description="文件内容")]
FilePath = Annotated[Path, Field(description="文件路径")]

# 网络配置类型 - 使用 Pydantic 模型
class NetworkConfigDict(BaseTypeModel):
    """网络配置字典模型"""
    ipv6_prefix: IPv6Network = Field(description="IPv6前缀")
    subnet_mask: Annotated[int, Field(ge=64, le=128)] = Field(default=127, description="子网掩码长度")
    mtu: Annotated[int, Field(ge=1280, le=9000)] = Field(default=1500, description="最大传输单元")

    @field_validator('ipv6_prefix')
    @classmethod
    def validate_ipv6_prefix(cls, v: str) -> str:
        """验证IPv6前缀"""
        try:
            ipaddress.IPv6Network(v)
            return v
        except ValueError as e:
            raise ValueError(f"无效的IPv6前缀: {v}") from e

# IPv6 地址处理工具类 - 使用 Pydantic 模型
class IPv6AddressHelper(BaseTypeModel):
    """IPv6地址处理助手类"""
    address: str = Field(description="IPv6地址")
    prefix_length: Optional[int] = Field(default=None, ge=0, le=128, description="前缀长度")

    @field_validator('address')
    @classmethod
    def validate_ipv6_address(cls, v: str) -> str:
        """验证IPv6地址格式"""
        # 提取地址部分（去除前缀）
        addr_part = v.split('/')[0] if '/' in v else v
        try:
            ipaddress.IPv6Address(addr_part)
            return v
        except ValueError as e:
            raise ValueError(f"无效的IPv6地址: {v}") from e

    @computed_field
    @property
    def pure_address(self) -> str:
        """纯IPv6地址（不含前缀）"""
        return self.address.split('/')[0] if '/' in self.address else self.address

    @computed_field
    @property
    def with_prefix(self) -> str:
        """带前缀的IPv6地址"""
        if '/' in self.address:
            return self.address
        prefix = self.prefix_length or 128
        return f"{self.address}/{prefix}"

    @computed_field
    @property
    def network(self) -> str:
        """IPv6网络地址"""
        try:
            if '/' in self.address:
                return str(ipaddress.IPv6Network(self.address, strict=False))
            else:
                prefix = self.prefix_length or 128
                return str(ipaddress.IPv6Network(f"{self.address}/{prefix}", strict=False))
        except ValueError:
            return self.with_prefix

    @computed_field
    @property
    def is_link_local(self) -> bool:
        """是否为链路本地地址"""
        addr = ipaddress.IPv6Address(self.pure_address)
        return addr.is_link_local

    @computed_field
    @property
    def is_global(self) -> bool:
        """是否为全局地址"""
        addr = ipaddress.IPv6Address(self.pure_address)
        return addr.is_global

    @computed_field
    @property
    def is_loopback(self) -> bool:
        """是否为回环地址"""
        addr = ipaddress.IPv6Address(self.pure_address)
        return addr.is_loopback

    @classmethod
    def from_string(cls, ipv6_str: str, default_prefix: int = 128) -> 'IPv6AddressHelper':
        """从字符串创建IPv6地址助手"""
        if '/' in ipv6_str:
            addr, prefix = ipv6_str.split('/')
            return cls(address=addr, prefix_length=int(prefix))
        else:
            return cls(address=ipv6_str, prefix_length=default_prefix)

    def to_network(self) -> 'IPv6NetworkHelper':
        """转换为网络地址助手"""
        return IPv6NetworkHelper(network=self.with_prefix)

class IPv6NetworkHelper(BaseTypeModel):
    """IPv6网络地址处理助手类"""
    network: str = Field(description="IPv6网络地址")

    @field_validator('network')
    @classmethod
    def validate_ipv6_network(cls, v: str) -> str:
        """验证IPv6网络地址格式"""
        try:
            ipaddress.IPv6Network(v)
            return v
        except ValueError as e:
            raise ValueError(f"无效的IPv6网络地址: {v}") from e

    @computed_field
    @property
    def network_address(self) -> str:
        """网络地址"""
        return str(ipaddress.IPv6Network(self.network).network_address)

    @computed_field
    @property
    def broadcast_address(self) -> str:
        """广播地址"""
        return str(ipaddress.IPv6Network(self.network).broadcast_address)

    @computed_field
    @property
    def prefix_length(self) -> int:
        """前缀长度"""
        return ipaddress.IPv6Network(self.network).prefixlen

    @computed_field
    @property
    def num_addresses(self) -> int:
        """地址数量"""
        return ipaddress.IPv6Network(self.network).num_addresses

    def get_host_address(self, host_num: int) -> IPv6AddressHelper:
        """获取指定主机号的地址"""
        network = ipaddress.IPv6Network(self.network)
        hosts = list(network.hosts())
        if 0 <= host_num < len(hosts):
            return IPv6AddressHelper.from_string(str(hosts[host_num]), self.prefix_length)
        else:
            raise ValueError(f"主机号 {host_num} 超出范围 [0, {len(hosts)-1}]")

    def contains(self, address: str) -> bool:
        """检查是否包含指定地址"""
        try:
            addr = ipaddress.IPv6Address(address.split('/')[0])
            return addr in ipaddress.IPv6Network(self.network)
        except ValueError:
            return False

# 便利函数
def extract_ipv6_address(ipv6_with_prefix: str) -> str:
    """从带前缀的IPv6地址中提取纯地址部分"""
    return IPv6AddressHelper.from_string(ipv6_with_prefix).pure_address

def ensure_ipv6_prefix(ipv6_address: str, prefix_length: int = 128) -> str:
    """确保IPv6地址包含前缀"""
    return IPv6AddressHelper.from_string(ipv6_address, prefix_length).with_prefix

# 接口映射配置 - 使用 Pydantic 模型
class InterfaceMapping(BaseTypeModel):
    """接口映射配置模型"""
    direction_to_interface: Dict[Direction, str] = Field(
        default_factory=lambda: {
            Direction.NORTH: "eth1",
            Direction.SOUTH: "eth2",
            Direction.WEST: "eth3",
            Direction.EAST: "eth4"
        },
        description="方向到接口名称的映射"
    )

    def get_interface(self, direction: Direction) -> str:
        """获取方向对应的接口名称"""
        return self.direction_to_interface[direction]

    def get_direction(self, interface: str) -> Optional[Direction]:
        """获取接口对应的方向"""
        for direction, intf in self.direction_to_interface.items():
            if intf == interface:
                return direction
        return None

    @computed_field
    @property
    def interface_to_direction(self) -> Dict[str, Direction]:
        """接口名称到方向的反向映射"""
        return {intf: direction for direction, intf in self.direction_to_interface.items()}

class DirectionMapping(BaseTypeModel):
    """方向映射配置模型"""
    reverse_mapping: Dict[Direction, Direction] = Field(
        default_factory=lambda: {
            Direction.NORTH: Direction.SOUTH,
            Direction.SOUTH: Direction.NORTH,
            Direction.WEST: Direction.EAST,
            Direction.EAST: Direction.WEST
        },
        description="方向反向映射"
    )

    def get_reverse(self, direction: Direction) -> Direction:
        """获取相反方向"""
        return self.reverse_mapping[direction]

    def get_clockwise(self, direction: Direction) -> Direction:
        """获取顺时针方向"""
        return direction.rotate_clockwise()

    def get_counterclockwise(self, direction: Direction) -> Direction:
        """获取逆时针方向"""
        return direction.rotate_counterclockwise()

# 全局实例（保持向后兼容）
_default_interface_mapping = InterfaceMapping()
_default_direction_mapping = DirectionMapping()

INTERFACE_MAPPING = _default_interface_mapping.direction_to_interface
REVERSE_DIRECTION = _default_direction_mapping.reverse_mapping

# 新的类型安全访问方式
def get_interface_for_direction(direction: Direction) -> str:
    """获取方向对应的接口名称（类型安全）"""
    return _default_interface_mapping.get_interface(direction)

def get_direction_for_interface(interface: str) -> Optional[Direction]:
    """获取接口对应的方向（类型安全）"""
    return _default_interface_mapping.get_direction(interface)

def get_reverse_direction(direction: Direction) -> Direction:
    """获取相反方向（类型安全）"""
    return _default_direction_mapping.get_reverse(direction)

# 链路地址模型 - 增强版
class LinkAddress(BaseTypeModel):
    """链路地址模型"""
    network: IPv6Network = Field(description="链路网络地址")
    router1_addr: IPv6Address = Field(description="路由器1的IPv6地址")
    router2_addr: IPv6Address = Field(description="路由器2的IPv6地址")
    router1_name: RouterName = Field(description="路由器1名称")
    router2_name: RouterName = Field(description="路由器2名称")

    @field_validator('router1_addr', 'router2_addr')
    @classmethod
    def validate_addresses_in_network(cls, v: str, info) -> str:
        """验证地址是否在网络范围内"""
        if 'network' in info.data:
            network = info.data['network']
            helper = IPv6NetworkHelper(network=network)
            addr = v.split('/')[0]  # 去除前缀
            if not helper.contains(addr):
                raise ValueError(f"地址 {v} 不在网络 {network} 范围内")
        return v

    @field_validator('router2_addr')
    @classmethod
    def validate_addresses_different(cls, v: str, info) -> str:
        """验证两个地址不同"""
        if 'router1_addr' in info.data:
            addr1 = info.data['router1_addr'].split('/')[0]
            addr2 = v.split('/')[0]
            if addr1 == addr2:
                raise ValueError("链路两端的地址不能相同")
        return v

    @computed_field
    @property
    def link_id(self) -> str:
        """链路标识符"""
        names = sorted([self.router1_name, self.router2_name])
        return f"{names[0]}_{names[1]}"

    @computed_field
    @property
    def router1_helper(self) -> IPv6AddressHelper:
        """路由器1地址助手"""
        return IPv6AddressHelper.from_string(self.router1_addr)

    @computed_field
    @property
    def router2_helper(self) -> IPv6AddressHelper:
        """路由器2地址助手"""
        return IPv6AddressHelper.from_string(self.router2_addr)

    @computed_field
    @property
    def network_helper(self) -> IPv6NetworkHelper:
        """网络地址助手"""
        return IPv6NetworkHelper(network=self.network)

    def get_peer_address(self, router_name: str) -> str:
        """获取对端路由器地址"""
        if router_name == self.router1_name:
            return self.router2_addr
        elif router_name == self.router2_name:
            return self.router1_addr
        else:
            raise ValueError(f"路由器 {router_name} 不在此链路上")

    def get_peer_name(self, router_name: str) -> str:
        """获取对端路由器名称"""
        if router_name == self.router1_name:
            return self.router2_name
        elif router_name == self.router2_name:
            return self.router1_name
        else:
            raise ValueError(f"路由器 {router_name} 不在此链路上")

# 拓扑统计信息模型
class TopologyStats(BaseTypeModel):
    """拓扑统计信息模型"""
    total_routers: PositiveInt = Field(description="总路由器数")
    total_links: int = Field(ge=0, description="总链路数")
    topology_type: TopologyType = Field(description="拓扑类型")
    size: PositiveInt = Field(description="网格大小")

    # 节点类型统计
    corner_nodes: int = Field(default=0, ge=0, description="角点节点数")
    edge_nodes: int = Field(default=0, ge=0, description="边缘节点数")
    internal_nodes: int = Field(default=0, ge=0, description="内部节点数")
    special_nodes: int = Field(default=0, ge=0, description="特殊节点数")

    @computed_field
    @property
    def density(self) -> float:
        """拓扑密度（实际链路数/最大可能链路数）"""
        max_links = self.total_routers * (self.total_routers - 1) // 2
        return self.total_links / max_links if max_links > 0 else 0.0

    @computed_field
    @property
    def average_degree(self) -> float:
        """平均度数"""
        return (2 * self.total_links) / self.total_routers if self.total_routers > 0 else 0.0

    @computed_field
    @property
    def node_type_distribution(self) -> Dict[str, int]:
        """节点类型分布"""
        return {
            "corner": self.corner_nodes,
            "edge": self.edge_nodes,
            "internal": self.internal_nodes,
            "special": self.special_nodes
        }

    @field_validator('total_links')
    @classmethod
    def validate_links_count(cls, v: int, info) -> int:
        """验证链路数合理性"""
        if 'total_routers' in info.data:
            max_links = info.data['total_routers'] * (info.data['total_routers'] - 1) // 2
            if v > max_links:
                raise ValueError(f"链路数 {v} 超过最大可能值 {max_links}")
        return v
