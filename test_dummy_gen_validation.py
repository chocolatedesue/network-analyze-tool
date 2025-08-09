#!/usr/bin/env python3
"""
测试 dummy-gen 参数验证功能
"""

import sys
from pathlib import Path
import pytest
from pydantic import ValidationError

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from topo_gen.core.models import TopologyConfig
from topo_gen.core.types import TopologyType


def test_valid_dummy_gen_protocols():
    """测试有效的 dummy-gen 协议"""
    # 测试单个协议
    config = TopologyConfig(
        size=4,
        topology_type=TopologyType.GRID,
        dummy_gen_protocols={"ospf6d"}
    )
    assert config.dummy_gen_protocols == {"ospf6d"}
    
    # 测试多个协议
    config = TopologyConfig(
        size=4,
        topology_type=TopologyType.GRID,
        dummy_gen_protocols={"ospf6d", "bgpd", "bfdd"}
    )
    assert config.dummy_gen_protocols == {"ospf6d", "bgpd", "bfdd"}
    
    # 测试空集合
    config = TopologyConfig(
        size=4,
        topology_type=TopologyType.GRID,
        dummy_gen_protocols=set()
    )
    assert config.dummy_gen_protocols == set()


def test_invalid_dummy_gen_protocols():
    """测试无效的 dummy-gen 协议"""
    # 测试单个无效协议
    with pytest.raises(ValidationError) as exc_info:
        TopologyConfig(
            size=4,
            topology_type=TopologyType.GRID,
            dummy_gen_protocols={"invalid_protocol"}
        )
    
    error_msg = str(exc_info.value)
    assert "无效的协议名称: invalid_protocol" in error_msg
    assert "支持的协议: bfdd, bgpd, ospf6d" in error_msg
    
    # 测试多个无效协议
    with pytest.raises(ValidationError) as exc_info:
        TopologyConfig(
            size=4,
            topology_type=TopologyType.GRID,
            dummy_gen_protocols={"invalid1", "invalid2"}
        )
    
    error_msg = str(exc_info.value)
    assert "无效的协议名称: invalid1, invalid2" in error_msg
    
    # 测试混合有效和无效协议
    with pytest.raises(ValidationError) as exc_info:
        TopologyConfig(
            size=4,
            topology_type=TopologyType.GRID,
            dummy_gen_protocols={"ospf6d", "invalid_protocol", "bgpd"}
        )
    
    error_msg = str(exc_info.value)
    assert "无效的协议名称: invalid_protocol" in error_msg


def test_case_sensitivity():
    """测试大小写敏感性"""
    # 验证只接受小写
    with pytest.raises(ValidationError):
        TopologyConfig(
            size=4,
            topology_type=TopologyType.GRID,
            dummy_gen_protocols={"OSPF6D"}  # 大写应该失败
        )
    
    with pytest.raises(ValidationError):
        TopologyConfig(
            size=4,
            topology_type=TopologyType.GRID,
            dummy_gen_protocols={"BgPd"}  # 混合大小写应该失败
        )


if __name__ == "__main__":
    test_valid_dummy_gen_protocols()
    test_invalid_dummy_gen_protocols()
    test_case_sensitivity()
    print("✅ 所有 dummy-gen 验证测试通过！")
