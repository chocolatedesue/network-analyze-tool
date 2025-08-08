"""
链路生成和地址分配模块
实现与 old_topo_gen 一致的链路生成和接口地址映射功能
"""

from __future__ import annotations

from typing import Dict, List, Tuple, Set
import ipaddress
from dataclasses import dataclass

from .core.types import (
    Coordinate, Direction, RouterName, InterfaceName, IPv6Address,
    INTERFACE_MAPPING, REVERSE_DIRECTION
)
from .core.models import TopologyConfig, RouterInfo, TopologyType


@dataclass
class LinkAddress:
    """链路地址信息"""
    network: str
    router1_addr: str  # 带前缀的地址
    router2_addr: str  # 带前缀的地址
    router1_name: str
    router2_name: str


def generate_link_ipv6(size: int, coord1: Coordinate, coord2: Coordinate) -> LinkAddress:
    """生成链路IPv6地址对 - 使用/127网络，避免网络地址"""
    # 确保节点顺序一致性
    node1_id = coord1.row * size + coord1.col
    node2_id = coord2.row * size + coord2.col

    if node1_id > node2_id:
        coord1, coord2 = coord2, coord1
        node1_id, node2_id = node2_id, node1_id

    # 计算链路ID（使用更简单的方法，避免过大的数值）
    # 使用 Cantor pairing function 的简化版本来生成唯一的链路 ID
    if node1_id < node2_id:
        link_id = (node1_id + node2_id) * (node1_id + node2_id + 1) // 2 + node2_id
    else:
        link_id = (node1_id + node2_id) * (node1_id + node2_id + 1) // 2 + node1_id

    # 使用2001:db8:2000::/48作为链路地址空间
    base_network = ipaddress.IPv6Network("2001:db8:2000::/48")

    # 每个链路使用/126子网，这样有4个地址可选，我们选择::1和::2
    subnet_bits = 126 - 48  # 78位用于子网编号
    subnet_id = link_id % (2 ** subnet_bits)

    # 将 subnet_id 分解为多个段，避免单个段超过 4 位十六进制
    segment1 = (subnet_id >> 16) & 0xFFFF  # 高16位
    segment2 = subnet_id & 0xFFFF          # 低16位

    # 构建IPv6地址，确保每个段都不超过4位十六进制
    if segment1 > 0:
        # 如果有高位段，使用两段格式
        ipv6_suffix = f"{segment1:x}:{segment2:04x}"
    else:
        # 如果没有高位段，使用单段格式
        ipv6_suffix = f"{segment2:04x}"

    # 生成/126子网用于地址选择
    link_network_126 = ipaddress.IPv6Network(f"2001:db8:2000:{ipv6_suffix}::/126")

    # 对于/126网络，我们有4个地址：::0, ::1, ::2, ::3
    # 选择::1和::2，避免::0（网络地址）和::3（看起来像广播地址）
    network_addr = link_network_126.network_address

    # 两个路由器都得到非零结尾的地址
    addr1 = str(network_addr + 1)  # router1 得到::1
    addr2 = str(network_addr + 2)  # router2 得到::2

    # 但是接口配置仍然使用/127前缀（点对点链路的标准做法）
    link_network = ipaddress.IPv6Network(f"2001:db8:2000:{ipv6_suffix}::/127")

    router1_name = f"router_{coord1.row:02d}_{coord1.col:02d}"
    router2_name = f"router_{coord2.row:02d}_{coord2.col:02d}"

    return LinkAddress(
        network=str(link_network),
        router1_addr=f"{addr1}/127",  # 使用/127前缀
        router2_addr=f"{addr2}/127",  # 使用/127前缀
        router1_name=router1_name,
        router2_name=router2_name
    )


def get_neighbors_func(topology_type: TopologyType, size: int, special_config=None):
    """获取邻居函数"""
    if topology_type == TopologyType.GRID:
        return lambda coord: get_grid_neighbors(coord, size)
    elif topology_type == TopologyType.TORUS:
        return lambda coord: get_torus_neighbors(coord, size)
    elif topology_type == TopologyType.SPECIAL and special_config:
        return lambda coord: get_special_neighbors(coord, size, special_config)
    else:
        return lambda coord: get_grid_neighbors(coord, size)


def get_grid_neighbors(coord: Coordinate, size: int) -> Dict[Direction, Coordinate]:
    """获取Grid拓扑的邻居"""
    neighbors = {}
    row, col = coord.row, coord.col
    
    if row > 0:
        neighbors[Direction.NORTH] = Coordinate(row - 1, col)
    if row < size - 1:
        neighbors[Direction.SOUTH] = Coordinate(row + 1, col)
    if col > 0:
        neighbors[Direction.WEST] = Coordinate(row, col - 1)
    if col < size - 1:
        neighbors[Direction.EAST] = Coordinate(row, col + 1)
    
    return neighbors


def get_torus_neighbors(coord: Coordinate, size: int) -> Dict[Direction, Coordinate]:
    """获取Torus拓扑的邻居"""
    row, col = coord.row, coord.col
    return {
        Direction.NORTH: Coordinate((row - 1 + size) % size, col),
        Direction.SOUTH: Coordinate((row + 1) % size, col),
        Direction.WEST: Coordinate(row, (col - 1 + size) % size),
        Direction.EAST: Coordinate(row, (col + 1) % size)
    }


def get_special_neighbors(coord: Coordinate, size: int, special_config) -> Dict[Direction, Coordinate]:
    """获取特殊拓扑的邻居"""
    from .topology.special import get_filtered_grid_neighbors

    neighbors = {}

    # 1. 首先获取基础拓扑的邻居（过滤跨区域连接）
    if special_config.include_base_connections:
        if special_config.base_topology == TopologyType.TORUS:
            neighbors = get_torus_neighbors(coord, size)
        else:  # GRID - 使用过滤后的邻居
            neighbors = get_filtered_grid_neighbors(coord, size)

    # 2. 添加特殊连接
    # 内部桥接连接
    for edge in special_config.internal_bridge_edges:
        if edge[0] == coord:
            # 找一个可用的方向
            for direction in Direction:
                if direction not in neighbors:
                    neighbors[direction] = edge[1]
                    break
        elif edge[1] == coord:
            # 找一个可用的方向
            for direction in Direction:
                if direction not in neighbors:
                    neighbors[direction] = edge[0]
                    break

    # Torus桥接连接（为gateway节点提供额外接口）
    for edge in special_config.torus_bridge_edges:
        if edge[0] == coord:
            # 找一个可用的方向
            for direction in Direction:
                if direction not in neighbors:
                    neighbors[direction] = edge[1]
                    break
        elif edge[1] == coord:
            # 找一个可用的方向
            for direction in Direction:
                if direction not in neighbors:
                    neighbors[direction] = edge[0]
                    break

    return neighbors


def generate_all_links(config: TopologyConfig) -> List[LinkAddress]:
    """生成所有链路信息"""
    processed_pairs = set()
    links = []

    # 处理字符串和枚举值的比较
    is_special = (config.topology_type == TopologyType.SPECIAL or
                  str(config.topology_type).lower() == 'special')

    if is_special and config.special_config:
        # 对于特殊拓扑，需要区分哪些连接在ContainerLab中创建

        # 1. 生成基础拓扑连接（如果启用）- 使用过滤后的邻居
        if config.special_config.include_base_connections:
            from .topology.special import get_filtered_grid_neighbors

            for row in range(config.size):
                for col in range(config.size):
                    coord = Coordinate(row, col)

                    # Special 拓扑始终使用过滤后的 grid 邻居作为基础
                    # torus 连接通过 torus_bridge_edges 单独添加
                    neighbors = get_filtered_grid_neighbors(coord, config.size)

                    for neighbor_coord in neighbors.values():
                        pair = tuple(sorted([
                            (coord.row, coord.col),
                            (neighbor_coord.row, neighbor_coord.col)
                        ]))

                        if pair not in processed_pairs:
                            processed_pairs.add(pair)
                            link = generate_link_ipv6(config.size, coord, neighbor_coord)
                            links.append(link)

        # 2. 添加内部桥接连接（在ContainerLab中创建）
        for edge in config.special_config.internal_bridge_edges:
            pair = tuple(sorted([
                (edge[0].row, edge[0].col),
                (edge[1].row, edge[1].col)
            ]))

            if pair not in processed_pairs:
                processed_pairs.add(pair)
                link = generate_link_ipv6(config.size, edge[0], edge[1])
                links.append(link)

        # 3. 添加torus桥接连接（为gateway节点提供额外接口用于BGP）
        for edge in config.special_config.torus_bridge_edges:
            pair = tuple(sorted([
                (edge[0].row, edge[0].col),
                (edge[1].row, edge[1].col)
            ]))

            if pair not in processed_pairs:
                processed_pairs.add(pair)
                link = generate_link_ipv6(config.size, edge[0], edge[1])
                links.append(link)

    else:
        # 标准拓扑处理
        for row in range(config.size):
            for col in range(config.size):
                coord = Coordinate(row, col)

                # 直接调用相应的邻居函数，避免 lambda 闭包问题
                is_torus = (config.topology_type == TopologyType.TORUS or
                           str(config.topology_type).lower() == 'torus')

                if is_torus:
                    neighbors = get_torus_neighbors(coord, config.size)
                else:  # GRID
                    neighbors = get_grid_neighbors(coord, config.size)

                for neighbor_coord in neighbors.values():
                    pair = tuple(sorted([
                        (coord.row, coord.col),
                        (neighbor_coord.row, neighbor_coord.col)
                    ]))

                    if pair not in processed_pairs:
                        processed_pairs.add(pair)
                        link = generate_link_ipv6(config.size, coord, neighbor_coord)
                        links.append(link)

    return links


def generate_interface_mappings(
    config: TopologyConfig,
    routers: List[RouterInfo]
) -> Dict[str, Dict[str, str]]:
    """生成所有路由器的接口地址映射"""
    links = generate_all_links(config)
    neighbors_func = get_neighbors_func(config.topology_type, config.size, config.special_config)

    # 初始化接口映射
    interface_mappings = {router.name: {} for router in routers}

    # 为每个链路分配接口
    for link in links:
        # 找到两个路由器的坐标
        router1_coord = None
        router2_coord = None

        for router in routers:
            if router.name == link.router1_name:
                router1_coord = router.coordinate
            elif router.name == link.router2_name:
                router2_coord = router.coordinate

        if router1_coord is None or router2_coord is None:
            continue

        # 计算方向
        direction1 = calculate_direction(router1_coord, router2_coord, config.size)
        if direction1 is None:
            # 对于特殊连接，使用可用的接口
            direction1 = find_available_direction(router1_coord, neighbors_func)

        direction2 = REVERSE_DIRECTION[direction1]

        # 分配接口
        intf1 = INTERFACE_MAPPING[direction1]
        intf2 = INTERFACE_MAPPING[direction2]

        interface_mappings[link.router1_name][intf1] = link.router1_addr
        interface_mappings[link.router2_name][intf2] = link.router2_addr

    # 对于Special拓扑，还需要为Torus桥接连接生成接口地址（仅用于路由配置）
    if (get_topology_type_str(config.topology_type) == "special" and
        config.special_config and
        config.special_config.torus_bridge_edges):

        for edge in config.special_config.torus_bridge_edges:
            coord1, coord2 = edge

            # 找到对应的路由器
            router1_name = f"router_{coord1.row:02d}_{coord1.col:02d}"
            router2_name = f"router_{coord2.row:02d}_{coord2.col:02d}"

            # 检查这些路由器是否在当前路由器列表中
            if router1_name in interface_mappings and router2_name in interface_mappings:
                # 生成链路地址
                link = generate_link_ipv6(config.size, coord1, coord2)

                # 计算方向
                direction1 = calculate_direction(coord1, coord2, config.size)
                if direction1 is None:
                    # 对于Torus桥接，可能需要特殊处理方向
                    direction1 = find_available_direction_for_torus_bridge(coord1, interface_mappings[router1_name])

                direction2 = REVERSE_DIRECTION[direction1]

                # 分配接口（如果接口还没有被使用）
                intf1 = INTERFACE_MAPPING[direction1]
                intf2 = INTERFACE_MAPPING[direction2]

                if intf1 not in interface_mappings[router1_name]:
                    interface_mappings[router1_name][intf1] = link.router1_addr
                if intf2 not in interface_mappings[router2_name]:
                    interface_mappings[router2_name][intf2] = link.router2_addr

    return interface_mappings


def find_available_direction_for_torus_bridge(coord: Coordinate, existing_interfaces: Dict[str, str]) -> Direction:
    """为Torus桥接连接找到可用的方向"""
    # 按优先级顺序尝试方向
    for direction in [Direction.NORTH, Direction.SOUTH, Direction.WEST, Direction.EAST]:
        interface = INTERFACE_MAPPING[direction]
        if interface not in existing_interfaces:
            return direction
    # 如果所有方向都被占用，返回北方向（这种情况不应该发生）
    return Direction.NORTH


def get_topology_type_str(topology_type) -> str:
    """获取拓扑类型字符串"""
    if hasattr(topology_type, 'value'):
        return topology_type.value
    return str(topology_type)





def find_available_direction(coord: Coordinate, neighbors_func) -> Direction:
    """找到可用的方向"""
    neighbors = neighbors_func(coord)
    for direction in Direction:
        if direction not in neighbors:
            return direction
    return Direction.NORTH  # 默认返回北方向


def convert_links_to_clab_format(
    config: TopologyConfig,
    routers: List[RouterInfo]
) -> List[Tuple[str, str, str, str]]:
    """将链路信息转换为ContainerLab格式"""
    links = generate_all_links(config)
    clab_links = []

    # 生成正确的接口映射
    interface_mappings = generate_interface_mappings(config, routers)

    # 为每个链路生成ContainerLab格式
    for link in links:
        # 从接口映射中找到对应的接口
        router1_interfaces = interface_mappings.get(link.router1_name, {})
        router2_interfaces = interface_mappings.get(link.router2_name, {})

        # 找到使用了这个链路地址的接口
        intf1 = None
        intf2 = None

        for interface, addr in router1_interfaces.items():
            if addr == link.router1_addr:
                intf1 = interface
                break

        for interface, addr in router2_interfaces.items():
            if addr == link.router2_addr:
                intf2 = interface
                break

        if intf1 and intf2:
            clab_links.append((link.router1_name, intf1, link.router2_name, intf2))

    return clab_links


def generate_loopback_ipv6(area_id: int, coord: Coordinate) -> str:
    """生成IPv6环回地址"""
    row, col = coord.row, coord.col
    # 使用灵活的十六进制格式，避免超过4位的限制
    area_hex = f"{area_id:x}" if area_id <= 0xFFFF else f"{area_id >> 16:x}:{area_id & 0xFFFF:04x}"
    row_hex = f"{row:x}" if row <= 0xFFFF else f"{row >> 16:x}:{row & 0xFFFF:04x}"
    col_hex = f"{col:x}" if col <= 0xFFFF else f"{col >> 16:x}:{col & 0xFFFF:04x}"

    address = f"2001:db8:1000:{area_hex}:{row_hex}:{col_hex}::1"
    return address  # 不包含前缀，因为RouterInfo.loopback_ipv6字段期望纯地址


def calculate_direction(from_coord: Coordinate, to_coord: Coordinate, size: int = 6) -> Optional[Direction]:
    """计算从一个坐标到另一个坐标的方向"""
    row_diff = to_coord.row - from_coord.row
    col_diff = to_coord.col - from_coord.col

    # 标准相邻方向
    if row_diff == -1 and col_diff == 0:
        return Direction.NORTH
    elif row_diff == 1 and col_diff == 0:
        return Direction.SOUTH
    elif row_diff == 0 and col_diff == -1:
        return Direction.WEST
    elif row_diff == 0 and col_diff == 1:
        return Direction.EAST

    # Torus环绕连接（动态处理任意大小网格）
    wrap_distance = size - 1

    # 北-南环绕：选择更短的路径
    if row_diff == wrap_distance and col_diff == 0:  # (0,x) -> (size-1,x) - 向北环绕更短
        return Direction.NORTH
    elif row_diff == -wrap_distance and col_diff == 0:  # (size-1,x) -> (0,x) - 向南环绕更短
        return Direction.SOUTH

    # 东-西环绕：选择更短的路径
    if row_diff == 0 and col_diff == wrap_distance:  # (x,0) -> (x,size-1) - 向西环绕更短
        return Direction.WEST
    elif row_diff == 0 and col_diff == -wrap_distance:  # (x,size-1) -> (x,0) - 向东环绕更短
        return Direction.EAST

    # 对角连接（Torus桥接或特殊连接）
    if abs(row_diff) > 1 or abs(col_diff) > 1:
        # 选择一个合适的方向，优先选择行差较大的方向
        if abs(row_diff) >= abs(col_diff):
            return Direction.NORTH if row_diff < 0 else Direction.SOUTH
        else:
            return Direction.WEST if col_diff < 0 else Direction.EAST

    return None
