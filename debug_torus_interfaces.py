#!/usr/bin/env python3
"""
调试 Torus 拓扑接口分配问题
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from topo_gen.core.types import TopologyType, Coordinate, NodeType
from topo_gen.core.models import TopologyConfig, NetworkConfig, OSPFConfig, RouterInfo
from topo_gen.links import generate_all_links, generate_interface_mappings


def debug_torus_interfaces():
    """调试 Torus 拓扑接口分配"""
    print("=== 调试 Torus 拓扑接口分配 ===")
    
    config = TopologyConfig(
        size=6,
        topology_type=TopologyType.TORUS,
        network_config=NetworkConfig(),
        ospf_config=OSPFConfig()
    )
    
    # 生成链路
    links = generate_all_links(config)
    print(f"生成了 {len(links)} 条链路")
    
    # 创建路由器信息
    routers = []
    for row in range(config.size):
        for col in range(config.size):
            coord = Coordinate(row, col)
            router_name = f"router_{row:02d}_{col:02d}"
            
            router = RouterInfo(
                name=router_name,
                coordinate=coord,
                node_type=NodeType.INTERNAL,
                router_id=f"10.{row}.{col}.1",
                loopback_ipv6=f"2001:db8::{row:02x}{col:02x}:1"
            )
            routers.append(router)
    
    # 生成接口映射
    interface_mappings = generate_interface_mappings(config, routers)
    
    # 检查角落节点和边界节点的接口
    test_nodes = [
        (0, 0, "左上角"),
        (0, 5, "右上角"), 
        (5, 0, "左下角"),
        (5, 5, "右下角"),
        (0, 3, "上边中间"),
        (3, 0, "左边中间"),
        (3, 3, "中心节点")
    ]
    
    print("\n检查关键节点的接口分配:")
    for row, col, desc in test_nodes:
        router_name = f"router_{row:02d}_{col:02d}"
        interfaces = interface_mappings.get(router_name, {})
        
        print(f"\n{desc} - {router_name}:")
        print(f"  接口数量: {len(interfaces)}")
        for intf, addr in interfaces.items():
            print(f"  {intf}: {addr}")
        
        if len(interfaces) != 4:
            print(f"  ❌ 错误: 应该有 4 个接口，实际有 {len(interfaces)} 个")
        else:
            print(f"  ✅ 正确: 有 4 个接口")
    
    # 检查 router_00_00 的具体连接和方向计算
    print(f"\n详细检查 router_00_00 的连接:")
    from topo_gen.links import calculate_direction

    router_00_00_coord = Coordinate(0, 0)
    router_00_00_links = []
    for link in links:
        if "router_00_00" in [link.router1_name, link.router2_name]:
            router_00_00_links.append(link)

    print(f"router_00_00 参与的链路数: {len(router_00_00_links)}")
    for link in router_00_00_links:
        if link.router1_name == "router_00_00":
            peer = link.router2_name
            local_addr = link.router1_addr
            # 提取对端坐标
            peer_parts = peer.split('_')
            peer_coord = Coordinate(int(peer_parts[1]), int(peer_parts[2]))
        else:
            peer = link.router1_name
            local_addr = link.router2_addr
            # 提取对端坐标
            peer_parts = peer.split('_')
            peer_coord = Coordinate(int(peer_parts[1]), int(peer_parts[2]))

        # 计算方向
        direction = calculate_direction(router_00_00_coord, peer_coord, config.size)
        print(f"  连接到 {peer} ({peer_coord}): {local_addr}")
        print(f"    计算方向: {direction}")

        # 检查坐标差
        row_diff = peer_coord.row - router_00_00_coord.row
        col_diff = peer_coord.col - router_00_00_coord.col
        print(f"    坐标差: row_diff={row_diff}, col_diff={col_diff}")


def main():
    """主函数"""
    print("开始调试 Torus 拓扑接口分配问题...\n")
    debug_torus_interfaces()


if __name__ == "__main__":
    main()
