# 自定义配置文件样例梳理

## 地面网络配置样例

### 完整配置样例
```yaml
templates:
  frr:
    image: library/frrouting/frr:v8.4.0
    start_commands:
    - chown -R frr:frr /var/log/frr
    - /usr/lib/frr/frrinit.sh start
    stop_commands:
    - /usr/lib/frr/frrinit.sh stop
    volumes:
    - frr_conf:/etc/frr

nodes:
  node1:
    default_status: UP
    node_type: host
    alias: my_node_1
    extra_args:
      x: [-171, 948]
      y: [-82, 498]
    template: frr
    vNICs:
      eth0:
        ip: [10.0.0.2/8, fd00::2/8]
        mac: 36:50:fc:3c:e9:bc

  node2:
    default_status: UP
    node_type: router
    alias: node2
    extra_args:
      x: [31, 948]
      y: [-98, 498]
    template: frr
    physical: true
    vNICs:
      eth0:
        physical_nic_name: XGE1/0/6
        ip: [10.0.0.3/8, fd00::3/8]
        mac: 36:50:fc:7b:11:a3

  node3:
    default_status: UP
    node_type: monitor
    alias: node3
    extra_args:
      x: [-60, 948]
      y: [47, 498]
    template: frr
    vNICs:
      eth0:
        ip: [10.0.0.4/8, fd00::4/8]
        mac: 36:50:fc:9a:e0:8e

logical_links:
  veth_pairs:
  - [node2:eth0, node3:eth0]
  - [node1:eth0, node3:eth0]
```

### 节点配置字段
- `node_type`: host/router/as/monitor/null
- `image`: 镜像地址
- `start_commands/stop_commands`: 启动/停止命令数组
- `volumes`: 挂载卷
- `resources`: 资源配置
- `default_status`: UP/DOWN
- `vNICs`: 网络接口配置
- `alias`: 别名
- `extra_args`: 额外参数（坐标等）
- `physical`: 是否物理节点

### 网络接口配置
```yaml
vNICs:
  eth0:
    ip: [10.0.0.2/8, fd00::2/8]  # IPv4/IPv6地址
    mac: 36:50:fc:3c:e9:bc
    physical_nic_name: XGE1/0/6  # 物理节点专用
```

### 链路配置
```yaml
links:
  veth_pairs:
  - [node2:eth0, node3:eth0]  # 点对点链路

bridges:
  bridge1:
    name: my_bridge
    veths: [node0:eth0, node1:eth0, node2:eth0]  # 桥接模式

logical_links:
  veth_pairs:
  - [node2:eth0, node3:eth0]  # 可达性
```

### 模板配置
```yaml
templates:
  frr:
    image: library/frrouting/frr:v8.4.0
    start_commands:
    - chown -R frr:frr /var/log/frr
    - /usr/lib/frr/frrinit.sh start
    stop_commands:
    - /usr/lib/frr/frrinit.sh stop
    volumes:
    - frr_conf:/etc/frr
    default_status: DOWN
```

## 卫星网络配置样例

### 完整配置样例
```yaml
templates:
  sat_tmpl:
    node_type: sat
    image: ponedo/frr-ubuntu20:tiny
    start_commands:
    - chown -R frr:frr /var/log/frr
    - /usr/lib/frr/frrinit.sh start
    stop_commands:
    - /usr/lib/frr/frrinit.sh stop
    volumes:
    - frr_conf:/etc/frr
    - frr_log:/var/log/frr
    fixed_vNICs:
      eth0: {}
      eth1: {}
      eth2: {}
      eth3: {}
      eth4: {}
      eth5: {}
    resources:
      cpu_score: 1691
      memory: 4GB

  gs_tmpl:
    node_type: gs
    image: ponedo/frr-ubuntu20:tiny
    start_commands:
    - chown -R frr:frr /var/log/frr
    - /usr/lib/frr/frrinit.sh start
    stop_commands:
    - /usr/lib/frr/frrinit.sh stop
    volumes:
    - frr_conf:/etc/frr
    - frr_log:/var/log/frr

# 固定节点（卫星）
fixed_nodes:
  Sat0:
    sat_id: 0
    template: sat_tmpl
  Sat1:
    sat_id: 1
    template: sat_tmpl
  Sat2:
    sat_id: 2
    node_type: sat
    physical: true
    fixed_vNICs:
      eth0: {physical_nic_name: XGE1/0/5}
      eth1: {physical_nic_name: XGE1/0/6}
      eth2: {physical_nic_name: XGE1/0/7}
      eth3: {physical_nic_name: XGE1/0/8}
      eth4: {physical_nic_name: XGE1/0/9}
      eth5: {physical_nic_name: XGE1/0/10}
    vNICs:
      eth6: {physical_nic_name: XGE1/0/11}

  gs_0:
    template: gs_tmpl
    gs_id: 0
    fixed_vNICs:
      eth0: {}

# 用户自定义节点
nodes:
  Sat2_host:
    physical: true
    node_type: host
    vNICs:
      eth0: {physical_nic_name: XGE1/0/12}

# 链路配置
links:
  engines: [walker_delta]
  veth_pairs:
  - [Sat2:eth6, Sat2_host:eth0]
  - [Sat3:eth2, Sat3_host:eth0]
```

### 卫星网络特有字段
- `sat_id`: 卫星ID
- `gs_id`: 地面站ID
- `end_user_id`: 终端用户ID
- `fixed_vNICs`: 必须存在的网口
- `engines`: 轨道构型（如walker_delta）

## 配置验证规则
1. `fixed_nodes` 和 `nodes` 中的节点必须在ZIP包中有对应文件夹
2. 物理节点必须配置 `physical_nic_name`
3. 虚拟节点必须设置 `image`
4. 链路两端网口必须正确配置MAC地址（点对点模式）

## 使用说明
1. 下载默认配置文件
2. 编辑 `config.yaml`
3. 压缩为ZIP包
4. 上传到平台
5. 应用配置</content>
<parameter name="filePath">/home/ccds/work/network-analyze-tool/online-service/docs/config-examples.md
