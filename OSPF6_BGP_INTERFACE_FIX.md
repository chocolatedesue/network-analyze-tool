# Special模式下BGP Gateway节点OSPF6配置修复

## 问题描述

在Special模式下，对于激活了BGP的gateway节点，OSPF6配置不应该包括用于eBGP的eth接口。这些接口专门用于跨域BGP连接，不应该参与OSPF6路由。

## 解决方案

### 修改的文件

- `topo_gen/generators/config.py`

### 主要修改

1. **修改`create_ospf_section`函数**：
   - 添加了`topology_config`参数
   - 在Special模式下，对于gateway节点，排除用于eBGP的接口

2. **新增`_get_ebgp_interfaces`函数**：
   - 识别Special拓扑中用于eBGP的接口
   - 包括内部桥接连接和Torus桥接连接的接口

3. **更新OSPF6配置生成器**：
   - 传递topology_config参数给create_ospf_section函数

### 代码逻辑

```python
# 在Special模式下，对于gateway节点，需要排除用于eBGP的接口
excluded_interfaces = set()
if (topology_config and 
    topology_config.topology_type == TopologyType.SPECIAL and
    topology_config.bgp_config is not None and
    router_info.node_type == NodeType.GATEWAY):
    excluded_interfaces = _get_ebgp_interfaces(router_info, topology_config)

# 添加接口配置时跳过eBGP接口
for interface_name in interfaces.keys():
    if interface_name in excluded_interfaces:
        continue
    # ... 添加OSPF6接口配置
```

### eBGP接口识别逻辑

`_get_ebgp_interfaces`函数通过以下方式识别eBGP接口：

1. **内部桥接连接**：检查`special_config.internal_bridge_edges`
2. **Torus桥接连接**：检查`special_config.torus_bridge_edges`
3. **方向计算**：使用`calculate_direction`函数确定接口方向
4. **接口映射**：使用`INTERFACE_MAPPING`将方向映射到接口名称

## 测试验证

### 测试场景

1. **Gateway节点测试**：
   - 节点类型：NodeType.GATEWAY
   - 拓扑类型：TopologyType.SPECIAL
   - BGP配置：已启用
   - 预期结果：eBGP接口从OSPF6配置中排除

2. **非Gateway节点测试**：
   - 节点类型：NodeType.INTERNAL
   - 预期结果：所有接口包含在OSPF6配置中

### 实际验证结果

#### Gateway节点 (0,1) 配置

**BGP配置** (`bgpd.conf`)：
```
neighbor eth1 interface remote-as external
```

**OSPF6配置** (`ospf6d.conf`)：
```
interface eth2
    ipv6 ospf6 area 0.0.0.0
interface eth3
    ipv6 ospf6 area 0.0.0.0
interface eth4
    ipv6 ospf6 area 0.0.0.0
# 注意：eth1接口被正确排除
```

#### 非Gateway节点 (2,2) 配置

**BGP配置** (`bgpd.conf`)：
```
# 没有eBGP邻居配置
```

**OSPF6配置** (`ospf6d.conf`)：
```
interface eth1
    ipv6 ospf6 area 0.0.0.0
interface eth3
    ipv6 ospf6 area 0.0.0.0
# 所有接口都包含在OSPF6配置中
```

## 影响范围

### 受影响的配置

- **Special拓扑**：✅ 修复生效
- **Grid拓扑**：✅ 无影响
- **Torus拓扑**：✅ 无影响

### 受影响的节点类型

- **Gateway节点**：✅ eBGP接口从OSPF6配置中排除
- **Internal节点**：✅ 无影响
- **Source/Dest节点**：✅ 无影响

## 总结

这个修复确保了在Special模式下：

1. **BGP Gateway节点**的eBGP接口不会参与OSPF6路由
2. **路由隔离**：跨域BGP连接与域内OSPF6路由正确分离
3. **配置一致性**：BGP和OSPF6配置不会产生冲突
4. **向后兼容**：不影响其他拓扑类型和节点类型

修复后的配置更符合实际网络部署场景，其中BGP用于域间路由，OSPF6用于域内路由。
