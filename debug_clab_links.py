#!/usr/bin/env python3
"""
调试 ContainerLab 链路生成问题
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from topo_gen.core.types import TopologyType, Coordinate, Direction, INTERFACE_MAPPING
from topo_gen.core.models import TopologyConfig, OSPFConfig, BFDConfig
from topo_gen.links import convert_links_to_clab_format
from topo_gen.engine import TopologyEngine

def debug_clab_links():
    """调试 ContainerLab 链路生成"""
    print("=== 调试 ContainerLab 链路生成 ===")
    
    # 创建10x10 Torus配置
    config = TopologyConfig(
        size=10,
        topology_type=TopologyType.TORUS,
        multi_area=False,
        ospf_config=OSPFConfig(),
        bfd_config=BFDConfig(enabled=False)
    )
    
    # 生成路由器信息
    generator = TopologyEngine()
    routers = generator._generate_routers(config)
    
    print(f"生成了 {len(routers)} 个路由器")
    
    # 生成 ContainerLab 链路
    clab_links = convert_links_to_clab_format(config, routers)
    
    print(f"生成了 {len(clab_links)} 个 ContainerLab 链路")
    
    # 检查接口使用情况
    interface_usage = {}  # {router_name: {interface: count}}
    
    for router1, intf1, router2, intf2 in clab_links:
        # 统计 router1 的接口使用
        if router1 not in interface_usage:
            interface_usage[router1] = {}
        if intf1 not in interface_usage[router1]:
            interface_usage[router1][intf1] = 0
        interface_usage[router1][intf1] += 1
        
        # 统计 router2 的接口使用
        if router2 not in interface_usage:
            interface_usage[router2] = {}
        if intf2 not in interface_usage[router2]:
            interface_usage[router2][intf2] = 0
        interface_usage[router2][intf2] += 1
    
    # 查找重复使用的接口
    print(f"\n=== 检查 ContainerLab 接口重复 ===")
    duplicates_found = False
    duplicate_details = []
    
    for router_name, interfaces in interface_usage.items():
        for intf, count in interfaces.items():
            if count > 1:
                print(f"❌ {router_name}:{intf} 被使用了 {count} 次")
                duplicates_found = True
                duplicate_details.append((router_name, intf, count))
    
    if not duplicates_found:
        print("✅ 没有发现接口重复使用")
    else:
        # 显示重复接口的详细信息
        print(f"\n=== 重复接口详细信息 ===")
        for router_name, intf, count in duplicate_details:
            print(f"\n{router_name}:{intf} 的所有使用:")
            for i, (r1, i1, r2, i2) in enumerate(clab_links):
                if (r1 == router_name and i1 == intf) or (r2 == router_name and i2 == intf):
                    print(f"  {i+1}. {r1}:{i1} <-> {r2}:{i2}")
    
    # 检查特定路由器的链路
    test_router = "router_08_09"
    print(f"\n=== {test_router} 的所有链路 ===")
    router_links = []
    
    for r1, i1, r2, i2 in clab_links:
        if r1 == test_router or r2 == test_router:
            router_links.append((r1, i1, r2, i2))
    
    print(f"{test_router} 参与了 {len(router_links)} 个链路:")
    for r1, i1, r2, i2 in router_links:
        if r1 == test_router:
            print(f"  {r1}:{i1} -> {r2}:{i2}")
        else:
            print(f"  {r2}:{i2} -> {r1}:{i1}")
    
    # 统计该路由器的接口使用
    router_interfaces = {}
    for r1, i1, r2, i2 in router_links:
        if r1 == test_router:
            if i1 not in router_interfaces:
                router_interfaces[i1] = 0
            router_interfaces[i1] += 1
        if r2 == test_router:
            if i2 not in router_interfaces:
                router_interfaces[i2] = 0
            router_interfaces[i2] += 1
    
    print(f"\n{test_router} 的接口使用统计:")
    for intf, count in router_interfaces.items():
        status = "❌ 重复" if count > 1 else "✅ 正常"
        print(f"  {intf}: {count} 次 {status}")

def debug_small_torus_clab():
    """调试小规模 Torus 的 ContainerLab 链路"""
    print(f"\n=== 调试 3x3 Torus ContainerLab 链路 ===")
    
    config = TopologyConfig(
        size=3,
        topology_type=TopologyType.TORUS,
        multi_area=False,
        ospf_config=OSPFConfig(),
        bfd_config=BFDConfig(enabled=False)
    )
    
    # 生成路由器信息
    generator = TopologyEngine()
    routers = generator._generate_routers(config)
    
    # 生成 ContainerLab 链路
    clab_links = convert_links_to_clab_format(config, routers)
    
    print(f"3x3 Torus ContainerLab 链路数: {len(clab_links)}")
    print("所有链路:")
    for i, (r1, i1, r2, i2) in enumerate(clab_links, 1):
        print(f"  {i:2d}. {r1}:{i1} <-> {r2}:{i2}")

if __name__ == "__main__":
    debug_clab_links()
    debug_small_torus_clab()
