Title: 大规模网络仿真平台 - SERNES

URL Source: https://sernes.cn/docs/api_doc

Markdown Content:
API文档
-----

API
---

该部分主要是用于自定义用户需求开放的api接口。

### 1 网络配置

`/api/network/`

#### 1.1 网络配置创建

> POST `/api/network/create/`

**功能**：包含网络、星座、信关站、终端等，仅保存到数据库。

**参数**：

*   顶级参数（body -- json）

| 参数名 | 类型 | 是否必需 | 描述 |
| --- | --- | --- | --- |
| network_name | String | 是 | 网络名称 |
| network_description | String | 否 | 网络描述 |
| constellation | Object | 是 | 星座配置对象 |
| gs_set | Array | 是 | 地面站配置数组 |

*   constellation 星座参数

| 参数名 | 类型 | 是否必需 | 描述 |
| --- | --- | --- | --- |
| name | String | 是 | 星座名称 |
| type | String | 否 | 星座类型，为 "walker_delta" |
| orbit_altitude | Number | 是 | 轨道高度（公里） |
| orbit_inclination | Number | 是 | 轨道倾角（度） |
| orbit_num | Number | 是 | 轨道平面数量 |
| sat_num_per_orbit | Number | 是 | 每个轨道的卫星数量 |
| phase_shift | Number | 是 | 相位偏移 |
| sat_isl_link_num | Number | 否 | 卫星间链路数量，固定为 4 |
| sat_gsl_link_num | Number | 否 | 卫星地面链路数量 |
| sat_access_link_num | Number | 否 | 卫星接入链路数量 |

*   gs_set 信关站参数

| 参数名 | 类型 | 是否必需 | 描述 |
| --- | --- | --- | --- |
| name | String | 是 | 地面站名称 |
| latitude | Number | 是 | 地面站纬度（度） |
| longitude | Number | 是 | 地面站经度（度） |
| elevation | Number | 是 | 地面站海拔高度（米） |
| gs_antenna_num | Number | 否 | 地面站天线数量 |
| gs_antenna_angle | Number | 否 | 地面站天线角度（度）范围为[0,90] |

**返回值**

*   成功响应 - 200

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 操作状态，值为"success" |
| network_id | Number | 新创建网络的唯一标识符，用于后续网络监控 |

*   错误响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 操作状态，值为"error" |
| msg | String | 错误信息，描述错误原因 |

示例：

\`\`\`
{
  "network_name": "my_network",
  "network_description": "",
  "constellation": {
    "name": "my_constellation",
    "type": "walker_delta", //default walker_delta
    "orbit_altitude": 550,
    "orbit_inclination": 53,
    "orbit_num": 60,
    "sat_num_per_orbit": 60,
    "phase_shift": 1,
    "sat_isl_link_num": 4, //default 4
    "sat_gsl_link_num": 1, //default 1
    "sat_access_link_num": 1 //default 1
  },
  "gs_set": [
    {
      "name": "GS0",
      "latitude": 25.1,
      "longitude": 123.1,
      "elevation": 121.1,
      "gs_antenna_num": 1, //default 1
      "gs_antenna_angle": 1 //default 1
    },
    {
      "name": "GS1",
      "latitude": 24.1,
      "longitude": 125.1,
      "elevation": 126.1,
      "gs_antenna_num": 1, //default 1
      "gs_antenna_angle": 1 //default 1
    }
  ]
}
\`\`\`

返回值

*   成功响应 - 200

\`\`\`
{
  "status": "success",
  "network_id": 111, // 返回网络ID，用于网络准备阶段监控
}
\`\`\`

*   失败响应 - 400/500

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

#### 1.2 配置文件上传

> POST `/api/network/<network-id>/file/upload`

**功能**：判断上传内容合法性，包括文件格式和文件结构的验证。

**参数**：

url 中的 `<network-id>` 为整数类型。

POST参数为 `form-data` ，格式要求：

| key | value |
| --- | --- |
| file | Content-Type: application/zip |

**返回值参数**

*   成功响应 - 200

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 操作状态，值为 "success" |
| path | String | 上传文件在共享盘中的绝对路径 |

*   错误响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 操作状态，值为"error" |
| msg | String | 错误信息，描述错误原因 |

示例

返回值

*   成功响应 - 200

\`\`\`
{
  "status": "success",
  "path": "/mnt/share/xxxx.zip"
}
\`\`\` 
*   错误响应 - 400/500

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\` 

#### 1.3 网络列表

> GET `/api/network/list`

**功能**：数据库中信息分页。

**参数**：

分页参数 (Parameter)

| 参数名 | 类型 | 是否必需 | 默认值 | 描述 |
| --- | --- | --- | --- | --- |
| page | Integer | 否 | 1 | 当前页码 |
| pageSize | Integer | 否 | 10 | 每页显示记录数 |

筛选参数 (Parameter)

| 参数名 | 类型 | 是否必需 | 描述 | 匹配方式 |
| --- | --- | --- | --- | --- |
| id | Number | 否 | 网络ID | 模糊匹配 |
| name | String | 否 | 网络名称 | 模糊匹配 |
| status | Number | 否 | 网络状态 | 精确匹配 |
| startDate | String | 否 | 开始日期 | 大于等于 |
| endDate | String | 否 | 结束日期 | 小于等于 |

排序参数 (Parameter)

| 参数名 | 类型 | 是否必需 | 可选值 | 描述 |
| --- | --- | --- | --- | --- |
| sortBy | String | 否 | - | 排序字段名 |
| sortOrder | String | 否 | asc/desc | 排序方式，asc-升序，desc-降序 |

**返回值**：

*   成功响应 - 200

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "success" |
| total | Number | 总记录数 |
| pages | Number | 总页数 |
| page | Number | 当前页码 |
| pageSize | Number | 每页记录数 |
| data | Array | 数据记录数组 |

data 数组元素参数

| 参数名 | 类型 | 描述 | 可选值 |
| --- | --- | --- | --- |
| network_id | Number | 网络ID | - |
| network_name | String | 网络名称 | - |
| network_status | Number | 网络状态 | 0: 暂存、1: 运行中 |
| network_type | Number | 网络类型 | 0: 卫星、1: BGP |
| create_time | String | 创建时间 | 格式：YYYY-mm-dd HH:mm:ss |

*   错误响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息描述 |

**示例**：

\`\`\`
GET /api/network/list?page=1&pageSize=10&name=test&status=1&sortBy=create_time&sortOrder=desc
\`\`\`

*   成功响应 - 200

\`\`\`
{
  "status": "success",
  "total": 100,
  "pages": 10,
  "page": 1,
  "pageSize": 10,
  "data": [
    {
      "network_id": 111,
      "network_name": "my_network",
      "network_status": 1,
      "network_type": 1,
      "create_time": "2024-03-24 15:10:00"
    }
  ]
}
\`\`\`

*   失败响应 - 400/500

\`\`\`
{
  "status": "error",
  "msg": "参数错误"
}
\`\`\`

#### 1.4 网络配置运行

> GET `/api/network/<network-id>/run/`

**功能**：在平台中运行一个网络。调用前做状态检查，是否可以调用。

**参数**：

url 中 `<network-id>`

**返回值**：

*   成功响应 - 200

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "success" |

*   失败响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
GET /api/network/60/run/
\`\`\`

返回值

*   成功响应

\`\`\`
{
  "status": "success"
}
\`\`\`

*   失败响应

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

#### 1.5 网络配置销毁

> GET `/api/network/<network-id>/destroy/`

**功能**：销毁一个运行中的网络。调用前做检查，当前网络ID是否匹配（防止异常调用导致系统出错）。

**参数**：

url 中 `<network-id>`

**返回值**：

*   成功响应 - 200

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "success" |

*   失败响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
GET /api/network/60/destroy/
\`\`\`

返回值

*   成功响应

\`\`\`
{
  "status": "success"
}
\`\`\`

*   失败响应

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

#### 1.6 网络重置

> GET `/api/network/<network-id>/reset/`

**功能**：对当前运行网络中的所有节点，停止容器进程，并重置该节点的所有IP地址及路由信息。

**参数**：

url 中 `<network-id>`

**返回值**：

*   成功响应 - 200

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "success" |

*   失败响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
GET /api/network/60/reset/
\`\`\`

返回值

*   成功响应

\`\`\`
{
  "status": "success"
}
\`\`\`

*   失败响应

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

#### 1.7 网络生命周期监控

> WebSocket `/ws/network/<network-id>/status/`

**功能**：对当前运行网络中的所有节点，停止容器进程，并重置该节点的所有IP地址及路由信息。

**参数**：

url 中 `<network-id>` ， 发送消息，以订阅对应通道

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| message | String | 固定值，"create" 或 "destroy" |

**返回值**：

网络运行、销毁、重置时需要显示进度条，需要用到 image_preparing（容器准备中）,topo_creating（网络拓扑建立中）, nf_loading（网络功能加载中）,nf_starting（网络功能启动中）, nf_unloading（网络功能拆卸中）, topo_destroying（网络拓扑销毁中）四个状态。

一个网络的生命周期包括如下状态： image_preparing, created, configured, topo_creating, nf_loading, nf_starting. running, nf_unloading, topo_destroying。

补充说明

*   卫星网络场景生命周期监控

    *   启动：topo_creating，nf_loading
    *   销毁：nf_unloading，topo_destroying

*   BGP网络场景生命周期监控

    *   启动：topo_creating，nf_loading，nf_starting
    *   销毁：nf_unloading，topo_destroying

*   成功响应

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| type | String | "update" |
| data | Object | 信息 |

data 参数

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | "topo_creating"等固定值 |
| progress | Number | 0.1 |
| estimated_time | Number | 10 |

*   失败响应

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| type | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
WebSocket /ws/network/60/status/
\`\`\`

发送

\`\`\`
{"message": "create"}
{"message": "destroy"}
\`\`\`

返回值

*   成功响应

\`\`\`
{
  "type": "update",
  "data": {
    "status": "topo_creating", //网络拓扑创建中
    "progress": 0.1, //完成进度，10%
    "estimated_time": 10 // 预估时间，分钟（全局预估时间，不是阶段预估时间）
  }
}
\`\`\`

*   失败响应

\`\`\`
{
  "type": "error",
  "msg": "Error message here..."
}
\`\`\`

#### 1.8 网络配置详情

> GET `/api/network/<network-id>/info/`

**功能**：返回一个网络的详细信息。

**参数**：

url 中 `<network-id>`

**返回值**：

*   成功响应 - 200

通用参数（两种类型共有）

| 参数名 | 类型 | 描述 | 可选值 |
| --- | --- | --- | --- |
| status | String | 响应状态 | "success" |
| network_id | Number | 网络ID | - |
| network_name | String | 网络名称 | - |
| network_description | String | 网络描述 | - |
| network_status | Number | 网络状态 | 0: 暂存、1: 运行中 |
| network_type | Number | 网络类型 | 0: 卫星、1: BGP |
| create_time | String | 创建时间 | 格式：YYYY-mm-dd HH:mm:ss |

**卫星网络特有参数** (network_type = 0)

*   constellation 对象参数

| 参数名 | 类型 | 描述 | 默认值 |
| --- | --- | --- | --- |
| name | String | 星座名称 | - |
| type | String | 星座类型 | "walker_delta" |
| orbit_altitude | Number | 轨道高度（公里） | - |
| orbit_inclination | Number | 轨道倾角（度） | - |
| orbit_num | Number | 轨道平面数量 | - |
| sat_num_per_orbit | Number | 每个轨道的卫星数量 | - |
| phase_shift | Number | 相位偏移 | - |
| sat_isl_link_num | Number | 卫星间链路数量 | 4 |
| sat_gsl_link_num | Number | 卫星地面链路数量 | 1 |
| sat_access_link_num | Number | 卫星接入链路数量 | 1 |

*   gs_set 数组元素参数

| 参数名 | 类型 | 描述 | 默认值 |
| --- | --- | --- | --- |
| gs_id | Number | 地面站ID | - |
| node_id | Number | 节点ID | -1 |
| name | String | 地面站名称 | - |
| latitude | Number | 纬度（度） | - |
| longitude | Number | 经度（度） | - |
| elevation | Number | 海拔高度（米） | - |
| gs_antenna_num | Number | 地面站天线数量 | 1 |
| gs_antenna_angle | Number | 地面站天线角度（度） | 1 |

*   user_terminals 数组元素参数

| 参数名 | 类型 | 描述 | 默认值 |
| --- | --- | --- | --- |
| end_user_id | Number | 终端用户ID | -1 |
| node_id | Number | 节点ID | -1 |
| name | String | 终端名称 | - |
| latitude | Number | 纬度（度） | - |
| longitude | Number | 经度（度） | - |
| elevation | Number | 海拔高度（米） | - |

*   失败响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
GET /api/network/60/reset/
\`\`\`

返回值

*   成功响应

**卫星网络** (network_type = 0)

\`\`\`
{
  "status": "success",
  "network_id": 111,
  "network_name": "my_network",
  "network_description": "",
  "network_status": 0, // 0-暂存/1-运行中
  "network_type": 0, // 0-卫星 1-BGP
  "create_time": "2024:03:24 15:10:00", // 创建时间  YYYY-mm-dd HH:mm:ss
  "constellation": {
    "name": "my_constellation",
    "type": "walker_delta", //default walker_delta
    "orbit_altitude": 550,
    "orbit_inclination": 53,
    "orbit_num": 60,
    "sat_num_per_orbit": 60, 
    "phase_shift": 1,
    "sat_isl_link_num": 4, //default 4
    "sat_gsl_link_num": 1, //default 1
    "sat_access_link_num": 1, //default 1
  },
  "gs_set": [
    {
      "gs_id": 0,
      "node_id": -1,
      "name": "GS0",
      "latitude": 25.1,
      "longitude": 123.1,
      "elevation": 121.1,
      "gs_antenna_num": 1, //default 1
      "gs_antenna_angle": 1, //default 1
    },
    {
      "gs_id": 1,
      "node_id": -1,
      "name": "GS1",
      "latitude": 24.1,
      "longitude": 125.1,
      "elevation": 126.1,
      "gs_antenna_num": 1, //default 1
      "gs_antenna_angle": 1, //default 1
    },
  ],
  "user_terminals": [
    {
      "end_user_id": -1,
      "node_id": -1,
      "name": "alice",
      "latitude": 25.1,
      "longitude": 123.1,
      "elevation": 121.1,
    },
    {
      "end_user_id": -1,
      "node_id": -1,
      "name": "bob",
      "latitude": 35.1,
      "longitude": 143.1,
      "elevation": 125.1,
    }
  ]
}
\`\`\`

**BGP网络** (network_type = 1)

\`\`\`
{
  "status": "success",
  "network_id": 111,
  "network_name": "my_network",
  "network_description": "",
  "network_status": 0, // 0-暂存/1-运行中
  "network_type": 1, // 0-卫星 1-BGP
  "create_time": "2024:03:24 15:10:00", // 创建时间  YYYY-mm-dd HH:mm:ss
}
\`\`\`

*   失败响应

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

#### 1.9 网络配置删除

> GET `/api/network/<network-id>/remove/`

**功能**：删除一个网络。调用前做检查，不可以删除正在运行的网络。

**参数**：

url 中 `<network-id>`

**返回值**：

*   成功响应 - 200

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "success" |

*   失败响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
GET /api/network/60/remove/
\`\`\`

返回值

*   成功响应

\`\`\`
{
  "status": "success"
}
\`\`\`

*   失败响应

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

#### 1.10 配置文件删除

> GET `/api/network/<int:network-id>/file/delete`

**功能**：判断上传内容合法性，包括文件格式正确和文件结构符合标准。

**参数**：

url 中 `<network-id>`

**返回值**：

*   成功响应 - 200

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "success" |

*   失败响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
GET /api/network/60/file/delete
\`\`\`

返回值

*   成功响应

\`\`\`
{
  "status": "success"
}
\`\`\`

*   失败响应

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

#### 1.11 默认配置文件下载

> GET `/api/network/<int:network-id>/file/default/download`

**功能**：下载一个网络的默认文件。

**参数**：

url 中 `<network-id>`

**返回值**：

*   成功响应 - 200

`application/zip`

*   失败响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
GET /api/network/60/file/default/download
\`\`\`

返回值

*   成功响应

一个zip压缩包下载

*   失败响应

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

#### 1.12 容器镜像准备

> GET `/api/network/<int:network-id>/image/prepare`

**功能**：准备某个网络所需的所有容器镜像（准备工作包括：拉取镜像、提取文件系统）。

**参数**：

url 中 `<network-id>`

**返回值**：

*   成功响应 - 200

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "success" |

*   失败响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
GET /api/network/60/image/prepare
\`\`\`

返回值

*   成功响应

zip文件下载

*   失败响应

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

#### 1.13 强制清除网络

> GET `/api/network/force_clean/`

**功能**：强制清理运行中的网络。

**参数**：

无

**返回值**：

*   成功响应 - 200

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "success" |

*   失败响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
GET /api/network/force_clean/
\`\`\`

返回值

*   成功响应

\`\`\`
{
  "status": "success"
}
\`\`\`

*   失败响应

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

#### 1.14 当前配置文件下载

> GET `/api/network/<int:network-id>/file/current/download`

**功能**：下载一个网络的默认文件。

**参数**：

url 中 `<network-id>`

**返回值**：

*   成功响应 - 200

`application/zip`

*   失败响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
GET /api/network/60/file/current/download
\`\`\`

返回值

*   成功响应

一个zip压缩包下载

*   失败响应

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

### 2 集群管理

`/api/cluster`

#### 2.1 集群健康状态监控

> GET `/api/cluster/health`

**功能**：获取集群健康状态。

**参数**：

无

**返回值**：

*   成功响应 - 200

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "success" |
| expected_nodes | Number | 节点数量 |
| online_nodes | Number | 在线节点数量 |

*   失败响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
GET /api/cluster/health
\`\`\`

返回值

*   成功响应

\`\`\`
{
  "status": "success",
  "expected_nodes": 8,
  "online_nodes": 8
}
\`\`\`

*   失败响应

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

### 3 节点管理

`/api/vnode`

#### 3.1 虚拟节点列表

> GET `/api/vnode/list`

**功能**：获取节点列表信息。

**参数**：

控制参数 (Parameter)

| 参数名 | 类型 | 是否必需 | 默认值 | 描述 |
| --- | --- | --- | --- | --- |
| lite | Integer | 否 | 10 | 是否返回精简版数据：0: 完整版；1: 精简版 注：精简版不支持分页/筛选/排序功能 |

分页参数 (Parameter) - 仅**完整版**支持

| 参数名 | 类型 | 是否必需 | 默认值 | 描述 |
| --- | --- | --- | --- | --- |
| page | Integer | 否 | 1 | 当前页码 |
| pageSize | Integer | 否 | 10 | 每页显示记录数 |

筛选参数 (Parameter) - 仅**完整版**支持

| 参数名 | 类型 | 是否必需 | 描述 | 匹配方式 |
| --- | --- | --- | --- | --- |
| node_id | Number | 否 | 虚拟节点ID | 模糊匹配 |
| node_name | String | 否 | 虚拟节点名称 | 模糊匹配 |
| status | Number | 否 | 容器状态 | 精确匹配 |
| type | String | 否 | 节点类型 | 模糊匹配 |

排序参数 (Parameter) - 仅**完整版**支持

| 参数名 | 类型 | 是否必需 | 可选值 | 描述 |
| --- | --- | --- | --- | --- |
| sortBy | String | 否 | - | 排序字段名 |
| sortOrder | String | 否 | asc/desc | 排序方式，asc-升序，desc-降序 |

**返回值**：

*   成功响应 - 200 - **完整版**

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "success" |
| total | Number | 总记录数 |
| pages | Number | 总页数 |
| page | Number | 当前页码 |
| pageSize | Number | 每页记录数 |
| data | Array | 虚拟节点数据数组 |

data 数组元素 - **完整版**

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| node_id | Number | 节点ID |
| node_name | String | 节点名称 |
| alias | String | 节点别名（仅在BGP场景存在） |
| current_status | Number | 当前状态 |
| image | String | 容器镜像 |
| node_type | String | 节点类型 |
| physical | Boolean | 是否物理节点 |

*   成功响应 - 200 - **精简版**

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "success" |
| data | Array | 虚拟节点数据数组 |

data 数组元素 - **精简版**

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| node_id | Number | 节点ID |
| node_name | String | 节点名称 |
| alias | String | 节点别名（仅在BGP场景存在） |
| physical | Boolean | 是否物理节点 |

*   错误响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息描述 |

**示例**：

*   完整版请求

\`\`\`
GET /api/vnode/list?page=1&pageSize=10&node_name=test&status=1&sortBy=node_id&sortOrder=desc
\`\`\`

*   精简版请求

\`\`\`
GET /api/vnode/list?lite=1
\`\`\`

返回值：

*   完整版响应

\`\`\`
{
    "status": "success",
    "total": 4,
    "pages": 1,
    "page": 1,
    "pageSize": 10,
    "data": [
        {
            "node_id": 1,
            "node_name": "node0",
            "alias": "AS1",
            "current_status": 1,
            "image": "ponedo/frr-ubuntu20:tiny",
            "node_type": "test",
            "physical": true
        }
    ]
}
\`\`\`

*   精简版响应

\`\`\`
{
    "status": "success",
    "data": [
        {
            "node_id": 0,
            "node_name": "Sat0",
            "alias": "AS1"
        },
        {
            "node_id": 1,
            "node_name": "Sat1",
            "physical": true
        }
    ]
}
\`\`\`

*   失败响应

\`\`\`
{
    "status": "error",
    "msg": "参数错误"
}
\`\`\`

#### 3.2 虚拟节点修改

> GET `/api/vnode/<node-id>/update`

**功能**：启动或者停止一个虚拟节点。

**参数**： (Parameter)

| 参数名 | 类型 | 是否必需 | 描述 |
| --- | --- | --- | --- |
| action | String | 是 | 控制节点状态，固定值"up" 或 "down" |

url 中 `<node-id>`

**返回值**：

*   成功响应 - 200

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "success" |

*   失败响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
GET /api/vnode/30/update?action=down
\`\`\`

返回值

*   成功响应 - 200

\`\`\`
{
  "status": "success"
}
\`\`\`

*   失败响应 - 2400/500

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

#### 3.3 虚拟节点批量修改

> POST `/api/vnode/update/batch/`

**功能**：多节点批量修改状态。

**参数**：

POST参数为 （body -- json） ，格式要求：

| 参数名 | 类型 | 是否必需 | 描述 |
| --- | --- | --- | --- |
| action | String | 是 | 控制节点列表状态，固定值"up" 或 "down" |
| node_ids | Array | 是 | 节点id列表 |

**返回值**

*   成功响应 - 200

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 操作状态，值为 "success" |
| node_ids | String | 控制节点列表状态，固定值"up" 或 "down" |
| action | Array | 节点id列表 |

*   错误响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 操作状态，值为"error" |
| msg | String | 错误信息，描述错误原因 |

**示例**：

\`\`\`
{
    "action": "up",
    "node_ids": [1, 2, 3]
}
\`\`\`

返回值

*   成功响应 - 200

\`\`\`
{
  "status": "success",
  "action": "up",
  "node_ids": [1, 2, 3]
}
\`\`\`

*   错误响应 - 400/500

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

#### 3.4 事件列表获取

> GET `/api/vnode/action/list/`

**功能**：节点事件列表获取。

**参数**：

筛选参数 (Parameter)

| 参数名 | 类型 | 是否必需 | 描述 |
| --- | --- | --- | --- |
| type | Number | 否 | 0-可编辑模板 1-直接执行，默认两种都能查 |

**返回值**：

*   成功响应 - 200

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "success" |
| action_list | Array | 事件列表 |

action_list 数组元素

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| action_id | Number | 事件id |
| action_name | String | 事件名称 |
| type | Number | 事件类型 |

*   失败响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
GET /api/vnode/action/list?type=0
\`\`\`

返回值

*   成功响应

\`\`\`
{
  "status": "success",
  "action_list": [
      {"action_id": 1, "action_name": "操作名称", "type": 0},
      {"action_id": 12, "action_name": "操作名称", "type": 0},
  ]
}
\`\`\`

*   失败响应

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

#### 3.5 事件详情获取

> GET `/api/vnode/action/<action-id>/info`

**功能**：获取某一个操作的代码模板。

**参数**：

url 中 `<action-id>`

**返回值**：

*   成功响应 - 200

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "success" |
| action_id | Number | 事件id |
| action_name | String | 事件名称 |
| shell | String | 终端 |
| type | Number | 0-可编辑模板 1-直接执行 |
| echo | Number | echo表示需要返回该命令的输出结果 |
| cmd_list | Array | 命令列表 |

cmd_list 数组元素

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| cmd | String | 命令内容 |

*   失败响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
GET /api/vnode/action/12/info
\`\`\`

返回值

*   成功响应

\`\`\`
{
    "status": "success",
    "action_id": 12, 
    "action_name": "操作名称",
    "shell": "/bin/bash",
    "type": 1, // 0-可编辑模板 1-直接执行
    "echo": 1, // echo表示需要返回该命令的输出结果
    "cmd_list": [
        {"cmd": "config terminal"},
        {"cmd": "router bgp <input:as_number>"},
        {"cmd": "network <input:cidr_ip>"},  
    ]
}
\`\`\`

*   失败响应

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

#### 3.6 虚拟节点终端

> GET `/api/vnode/<node-id>/terminal/`

**功能**：获取节点终端的 websocket 地址。

**参数**：

url 中 `<node-id>`

控制参数 (Parameter)

| 参数名 | 类型 | 是否必需 | 默认值 | 描述 |
| --- | --- | --- | --- | --- |
| cmd | String | 否 | bash | str执行的终端路径，注意url符号转化，例如/ -> %2F 如：bash、vtysh、sh、/bin/bash等 |

**返回值**：

*   成功响应 - 200

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "success" |
| terminal_url | String | web terminal的websocket连接，可执行命令 |

*   失败响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
GET /api/vnode/<node-id>/terminal/?cmd=%2Fusr%2Fbin%2Fbash
\`\`\`

返回值

*   成功响应

\`\`\`
{
   "status": "success",
   "terminal_url": "ws://172.10.80.158:8080/api/virtnet/ws/terminal/?network_id=1&node_id=1&cmd=%2Fusr%2Fbin%2Fbash"
}
\`\`\`

*   失败响应

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

#### 3.7 删除事件模板

> GET `/api/vnode/action/<action_id>/delete`

**功能**：删除指定的事件模板。

**参数**：

url 中 `<action_id>`

**返回值**：

*   成功响应 - 200

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "success" |

*   失败响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
GET /api/vnode/action/12/delete
\`\`\`

返回值

*   成功响应

\`\`\`
{
  "status": "success"
}
\`\`\`

*   失败响应

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

#### 3.8 节点执行事件

> WebSocket `/ws/vnode/<node-id>/exec/`

**功能**：在前台执行一个事件，可以拿到实时返回值。

**参数**：

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| cmd_list | Array | 命令列表 |

**返回值**：

*   成功响应

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| type | String | 命令执行状态 |
| data | Array | 返回值字符串列表 |

*   失败响应

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
WebSocket /ws/vnode/<node-id>/exec/
\`\`\`

发送

\`\`\`
{
  "cmd_list": [
    "config terminal",
    "router bgp <input:as_number>",
    "network <input:cidr_ip>"
  ]
}
\`\`\`

返回值

*   成功响应

\`\`\`
{
  "type": "update",
  "data": [
    "1234567890",
    "1234567890",
    "1234567890",
  ]
}
\`\`\`

*   失败响应

\`\`\`
{
  "type": "error",
  "msg": "Error message here..."
}
\`\`\`

### 4 链路管理

`/api/vlink`

#### 4.1 链路修改

> POST `/api/vlink/<link_id>/update/`

**功能**：修改一条链路的信息。

**参数**：

POST参数为 （body -- json） ，格式要求：

| 参数名 | 类型 | 是否必需 | 描述 |
| --- | --- | --- | --- |
| op | String | 是 | 固定值 "up"、"down"、"traffic_control" |
| args | Object | 否 | 需要调节的参数，该字段当op为"traffic_control"时携带。 |

args 参数

| 参数名 | 类型 | 是否必需 | 默认值 | 描述 |
| --- | --- | --- | --- | --- |
| bw | Number | 否 | -1 | 正整数，如果设置-1，卫星场景下表示由物理引擎接管 |
| delay | Number | 否 | -1 | 非负整数，如果设置-1，卫星场景下表示由物理引擎接管 |
| loss | Number | 否 | -1 | 0-1范围，如果设置-1，卫星场景下表示由物理引擎接管 |

**返回值**：

*   成功响应 - 200

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "success" |
| link_id | String | 链路id |
| op | String | 固定值 "up"、"down"、"traffic_control" |

*   失败响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
POST /api/vlink/12-15-30-5/update/
\`\`\`

参数

\`\`\`
{
  "op": "up",
}
\`\`\`

返回值

*   成功响应 - 200

\`\`\`
{
  "status": "success",
   "link_id":"12-15-30-5",
   "op": "up"
}
\`\`\`

*   失败响应 - 400/500

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

参数

\`\`\`
{
  "op": "traffic_control",
  "args": {
    "bw": 1000, //带宽1000Mbps
    "delay": -1, //系统自由管理
    "loss": 0.3, //丢包率30%
  }
}
\`\`\`

返回值

*   成功响应 - 200

\`\`\`
{
  "status": "success",
   "link_id":"12-15-30-5",
   "op": "traffic_control"
}
\`\`\`

*   失败响应 - 400/500

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

#### 4.2 链路批量修改

> POST `/api/vlink/update/batch/`

**功能**：多链路批量修改状态。

**参数**：

POST参数为 （body -- json） ，格式要求：

| 参数名 | 类型 | 是否必需 | 描述 |
| --- | --- | --- | --- |
| op | String | 是 | 固定值 "up"、"down"、"traffic_control" |
| link_ids | Array | 是 | 需要修改的链路的id数组 |
| args | Object | 否 | 需要调节的参数，该字段当op为"traffic_control"时携带。 |

**返回值**

*   成功响应 - 200

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 操作状态，值为 "success" |
| link_ids | Array | 链路的id数组 |
| op | String | 操作 |

*   错误响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 操作状态，值为"error" |
| msg | String | 错误信息，描述错误原因 |

**示例**：

\`\`\`
POST /api/vlink/update/batch/
\`\`\`

参数

\`\`\`
{
    "op":"down",
    "link_ids":["4-25-5-30","3-20-26-159"]
}
\`\`\`

返回值

*   成功响应 - 200

\`\`\`
{
  "status": "success",
  "action": "down",
  "link_ids":["4-25-5-30","3-20-26-159"]
}
\`\`\`

*   错误响应 - 400/500

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

参数

\`\`\`
{
    "op":"traffic_control",
    "link_ids":["4-25-5-30","3-20-26-159"],
    "args": {
        "bw": 1000, //带宽1000Mbps
        "delay": -1, //系统自由管理
        "loss": 0.3, //丢包率30%
    }
}
\`\`\`

返回值

*   成功响应 - 200

\`\`\`
{
  "status": "success",
  "action": "traffic_control",
  "link_ids":["4-25-5-30","3-20-26-159"]
}
\`\`\`

*   错误响应 - 400/500

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

### 5 卫星可视化平台

`/api/satvis/`

#### 5.1 获取信关站信息

> GET `api/satvis/ground_station/info`

**功能**：获取信关站信息。

**参数**：

无

**返回值**：

*   成功响应 - 200

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "success" |
| gs_list | Array | 信关站信息列表 |

gs_list 元素

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| gs_id | Number | 信关站id |
| node_id | Number | 虚拟节点id |
| name | String | 信关站名称 |
| latitude | Number | 纬度 |
| longitude | Number | 经度 |
| elevation | Number | 海拔高度 |
| gs_antenna_num | Number | 天线数量 |
| gs_antenna_angle | Number | 天线角度 |
| status | String | 状态 "UP"或者"DOWN" |
| physical | Boolean | 是否为实物节点 |

*   失败响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
GET /api/satvis/ground_station/info
\`\`\`

返回值

*   成功响应

\`\`\`
{
    "status": "success",
    "gs_list":[
        {
            "gs_id": 0,
            "node_id": 100, //虚拟节点id
            "name": "GS0",
            "latitude": 25.1,
            "longitude": 123.1,
            "elevation": 121.1,
            "gs_antenna_num": 1,
            "gs_antenna_angle": 1,
            "status": "UP",
            "physical": true
        },
        {
            "gs_id": 1,
            "node_id": 101, //虚拟节点id
            "name": "GS1",
            "latitude": 24.1,
            "longitude": 125.1,
            "elevation": 126.1,
            "gs_antenna_num": 1,
            "gs_antenna_angle": 1,
            "status": "DOWN",
            "physical": false
        },
    ]
}
\`\`\`

*   失败响应

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

#### 5.2 获取动态场景列表

> GET `/api/satvis/scenario/list`

**功能**：获取动态场景列表。

**参数**：

无

**返回值**：

*   成功响应 - 200

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "success" |
| scenario_list | Array | 动态场景列表 |

scenario_list 元素

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| scenario_id | Number | 动态场景id |
| scenario_status | Number | 0：未计算，不可选 1：已经计算，可选选 2：运行中 200：计算失败，可选 |
| scenario_name | String | 动态场景名称 |

*   失败响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
GET /api/satvis/scenario/list
\`\`\`

返回值

*   成功响应

\`\`\`
{
    "status": "success",
    "scenario_list":[
        {
            "scenario_id": 1,
            "scenario_name":"2024年冬至",
            "scenario_status": 1 // 已经计算，可选
        },
        {
            "scenario_id": 2,
            "scenario_name":"2024年冬至",
            "scenario_status": 2 // 运行中
        }
    ]
}
\`\`\`

*   失败响应

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

#### 5.3 新建动态场景

> POST `/api/satvis/scenario/create`

**功能**：获取动态场景列表。

**参数**：

POST参数为 （body -- json） ，格式要求：

| 参数名 | 类型 | 是否必需 | 限制 | 描述 |
| --- | --- | --- | --- | --- |
| scenario_name | String | 是 | 无 | 动态场景名称 |
| start_time | String | 是 | 遵循 `ISO 8601` 标准，或常用时间格式 | 场景起始时间 |
| duration | Number | 是 | 持续时间必须为正整数，持续时间存在一个最大值，由管理员设置。 | 场景持续时间 |
| granularity | Number | 是 | 物理引擎模型粒度应在大于等于 1。 | 物理引擎模型粒度（秒） |
| position_update_interval | Number | 是 | 卫星位置前端渲染更新时间粒度应在 5 到 20 秒之间，卫星位置前端渲染更新时间粒度应为物理引擎模型粒度的倍数。 | 卫星位置前端渲染更新时间粒度（单位为秒，必须被granularity整除，默认与granularity一致） |
| event_update_interval | Number | 是 | 链路状态与属性更新时间粒度应在 5 到 20 秒之间，卫星位置前端渲染更新时间粒度应为物理引擎模型粒度的倍数。 | 链路状态与属性更新时间粒度 |
| sun_outage_critical_angle | Number | 是 | 日凌判定链路太阳光夹角应在 0 到 90 度之间。 | 日凌判定链路太阳光夹角 |
| laser_outage_rate | Number | 是 | 异轨星间链路异常发生概率应在 [0, 1] | 异轨星间链路异常发生概率 |
| gsl_plan_method | String | 是 | 默认为min_distance | 星地链路切换策略 |

**返回值**：

*   成功响应 - 200

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "success" |
| scenario_id | Number | 动态场景id |

*   失败响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
GET /api/satvis/scenario/create
\`\`\`

参数

\`\`\`
{
  "scenario_name": "test", //场景名称
  "start_time": "2024-06-22T00:00:00+08:00", //场景起始时间
  "duration": 60, //场景持续时间
  "granularity": 1, //物理引擎模型粒度（秒）
  "position_update_interval": 10, //卫星位置前端渲染更新时间粒度（单位为秒，必须被granularity整除，默认与granularity一致）
  "event_update_interval": 10, //链路状态与属性更新时间粒度（单位为秒，必须被granularity整除，默认为大于10s的最小值）
  "sun_outage_critical_angle": 5, //日凌判定链路太阳光夹角（单位为度，default 5）
  "laser_outage_rate": 0.1, //异轨星间链路异常发生概率（default 0.1）
  "gsl_plan_method": "min_distance", //星地链路切换策略（预置选项包括min_distance；可选customized，此时用户需要上传星地切换策略至共享盘；默认min_distance）
}
\`\`\`

返回值

*   成功响应

\`\`\`
{
    "status": "success",
    "scenario_id": 1,
}
\`\`\`

*   失败响应

\`\`\`
{
    "status": "error",
    "msg": "错误信息"
}
\`\`\`

#### 5.4 获取单动态场景详情

> GET `/api/satvis/scenario/<scenario_id>/info`

**功能**：获取单动态场景详情。

**参数**：

url 中 `<scenario_id>`

**返回值**：

*   成功响应 - 200

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "success". |
| network_id | Number | 网路id |
| scenario_id | Number | 动态场景id |
| scenario_name | String | 动态场景名称 |
| start_time | String | 动态场景起始时间 |
| duration | Number | 场景持续时间 |
| granularity | Number | 物理引擎模型粒度（秒） |
| position_update_interval | Number | 星位置前端渲染更新时间粒度 |
| event_update_interval | Number | 链路状态与属性更新时间粒度，单位为秒 |
| sun_outage_critical_angle | Number | 日凌判定链路太阳光夹角，单位为度 |
| laser_outage_rate | Number | 异轨星间链路异常发生概率 |
| gsl_plan_method | String | 星地链路切换策略 |
| created_time | String | 创建时间 |
| scenario_status | Number | 场景状态，0-计算中、1-就绪、2-运行中、200-计算失败 |

*   失败响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
GET /api/satvis/scenario/2/info
\`\`\`

返回值

*   成功响应

\`\`\`
{
  "status": "success",
  "network_id": 0,
  "scenario_id": 2,
  "scenario_name": "test", //场景名称
  "start_time": "2024-06-22T00:00:00+08:00", //场景起始时间
  "duration": 60, //场景持续时间
  "granularity": 1, //物理引擎模型粒度（秒）
  "position_update_interval": 10, //卫星位置前端渲染更新时间粒度（单位为秒，必须被granularity整除，默认与granularity一致）
  "event_update_interval": 10, //链路状态与属性更新时间粒度（单位为秒，必须被granularity整除，默认为大于10s的最小值）
  "sun_outage_critical_angle": 5, //日凌判定链路太阳光夹角（单位为度，default 5）
  "laser_outage_rate": 0.1, //异轨星间链路异常发生概率（default 0.1）
  "gsl_plan_method": "min_distance", //星地链路切换策略（预置选项包括min_distance；可选customized，此时用户需要上传星地切换策略至共享盘；默认min_distance）
  "created_time": "2024-06-21T16:00:00+0000", //default 1
  "scenario_status": 0, // 0-计算中 1-就绪 2-运行中 200-计算失败
}
\`\`\`

*   失败响应

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

#### 5.5 删除动态场景

> GET `/api/satvis/scenario/<scenario_id>/delete`

**功能**：删除动态场景。

**参数**：

url 中 `<scenario_id>`

**返回值**：

*   成功响应 - 200

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "success" |

*   失败响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
GET /api/satvis/scenario/2/delete
\`\`\`

返回值

*   成功响应

\`\`\`
{
  "status": "success"
}
\`\`\`

*   失败响应

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

#### 5.6 动态场景播放

> GET `/api/satvis/scenario/<scenario_id>/play`

**功能**：仿真动态场景播放操作。

**参数**：

url 中 `<scenario_id>`

**返回值**：

*   成功响应 - 200

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "success" |

*   失败响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
GET /api/satvis/scenario/2/play
\`\`\`

返回值

*   成功响应

\`\`\`
{
  "status": "success"
}
\`\`\`

*   失败响应

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

#### 5.7 获取系统当前仿真状态

> GET `/api/satvis/scenario/status`

**功能**：获取系统当前仿真状态。

**参数**：

无

**返回值**：

*   成功响应 - 200

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "success" |
| emulation_status | Number | 0-无仿真任务 1-正在仿真 |
| network_id | Number | 当前网络id |
| scenario_id | Number | 当前场景id |

*   失败响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
GET /api/satvis/scenario/status
\`\`\`

返回值

*   成功响应

\`\`\`
{
    "status": "success",
    "emulation_status": 1, // 0-无仿真任务 1-正在仿真
    "network_id": 1, //当前网络id
    "scenario_id": 1 //当前场景id
}
\`\`\`

*   失败响应

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

#### 5.8 获取卫星轨迹信息

> GET `/api/satvis/<scenario_id>/sat_trajectory`

**功能**：获取卫星轨迹信息。

**参数**：

url 中 `<scenario_id>`

**返回值**：

*   成功响应 - 200

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "success" |
| startTime | String | 全部时间-开始时间，时间格式为 ISO8601 |
| endTime | String | 全部时间-结束时间，时间格式为 ISO8601 |
| starNetData | Array | 卫星信息数组 |

starNetData 元素

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| sat_id | Number | 卫星id |
| node_id | Number | 节点id |
| status | String | 状态，"UP" 或者 "DOWN" |
| physical | Boolean | 是否为实物节点 |
| host | Array | 表示该卫星上存在的载荷节点 |
| description | String | 描述 |
| epochTime | String | 卫星轨迹-开始时间 |
| pathData | Array | 路径数组 |

host 元素

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| node_id | Number | 节点id |
| node_name | String | 节点名称 |

pathData 元素

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| time | String | 当前时间 |
| timeInterval | Number | 当前时间距离开始时间秒数 |
| lat | Number | 纬度 |
| lon | Number | 经度 |
| height | Number | 高度 |

*   失败响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
GET /api/satvis/2/sat_trajectory
\`\`\`

返回值

*   成功响应

\`\`\`
{
  "status": "success",
  "startTime":"2024:03:24T15:10:00Z", //全部时间-开始时间   时间格式为 ISO8601 
  "endTime":"2024:03:24T15:10:00Z", //全部时间-结束时间
  "starNetData": [
    {
      "sat_id": 0,  //星星id
      "node_id": 0, //虚拟节点id
      "status": "DOWN", //状态
      "physical": true,
      "host": [
          {"node_id":100,"node_name":"Sat100_host"}
      ], //host，星载
      "description": "Sat0", //星星描述
      "epochTime":"2024:03:24T15:10:00Z", //星星轨迹-开始时间
      "pathData": [
        {
            "time": "2024:03:24T15:10:00Z", //当前时间
            "timeInterval":0,  //当前时间距离开始时间秒数
            "lat": 30, //纬度
            "lon": 175, //经度
            "height": 15200 //高度
        },
        {
            "time": "2024:03:24T15:10:03Z",
            "timeInterval":300,
            "lat": 30,
            "lon": 175,
            "height": 15200
        }
      ]
    },
    {
      "sat_id": 1,  //星星id
      "node_id": 1, //虚拟节点id
      "status": "UP", //状态
      "physical": false,
      "host": [], //host，星载
      "description": "Sat1", //星星描述
      "epochTime":"2024:03:24T15:10:00Z",
      "pathData":[
        {
          "time": "2024:03:24T15:10:00Z",
          "timeInterval":0,
          "lat": 30,
          "lon": 175,
          "height": 15200
        }
      ]
    }
  ]
}
\`\`\`

*   失败响应

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

#### 5.9 获取链路预计算信息

> GET `/api/satvis/<scenario_id>/init_edge_list`

**功能**：获取链路预计算信息。

**参数**：

url 中 `<scenario_id>`

**返回值**：

*   成功响应 - 200

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "success" |
| current_seconds | Number | 当前播放进度(秒)，相对于start_time的差值 |
| links | Array | 链路数组 |

links 元素

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| link_id | Number | 链路id |
| source_node_id | Number | 源节点id |
| target_node_id | Number | 目前节点id |
| linkType | String | 节点类型，intra-orbit 或空 |
| linkStatus | Array | 表示当前的节点状态，可能同时处于多种状态。渲染时，按照linkStatus列表中的第一个状态渲染该链路的颜色。 "Normal" 或者其他异常状态，包括： "User-outage"：用户手动控制该链路关闭 "Sun-outage"：日凌导致该链路关闭 当链路为"Normal" 表示该链路正常，不存在任何异常，只要存在任何一种异常则链路关闭。 |

*   失败响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
GET /api/satvis/2/init_edge_list
\`\`\`

返回值

*   成功响应

\`\`\`
{
  "status": "success",
  "current_seconds": 12, // 当前播放进度(秒)，相对于start_time的差值
  "links": [
    {
      "link_id": "0-1-1-4", //虚拟链路id
      "source_node_id": 0, //开始节点id
      "target_node_id": 1, //结束节点id
      "linkType": "intra-orbit",
      "linkStatus": ["Normal"]
    },
    {
      "link_id": "1-7-11-46", //虚拟链路id
      "source_node_id": 1,
      "target_node_id": 11,
      "linkType": "inter-orbit",
      "linkStatus": ["Sun-outage"]
    },
    {
      "link_id": "1-7-12-51", //虚拟链路id
      "source_node_id": 1,
      "target_node_id": 12,
      "linkType": "inter-orbit",
      "linkStatus": ["User-outage", "Sun-outage"] //链路状态，可能同时处于多种状态。渲染时，按照linkStatus列表中的第一个状态渲染该链路的颜色。
    },
    {
      "link_id": "1-10-101-1123", //虚拟链路id
      "source_node_id": 101,
      "target_node_id": 1,
      "linkType": "",
      "linkStatus": ["Normal"]
    },
    {
      "link_id": "16-111-104-1126", //虚拟链路id
      "source_node_id": 104,
      "target_node_id": 16,
      "linkType": "",
      "linkStatus": ["Normal"]
    }
  ]
}
\`\`\`

*   失败响应

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

#### 5.10 获取链路实时网络属性

> WebSocket `/ws/satvis/<scenario-id>/link_attributes/<link-id>`

**功能**：每隔一段时间（event_update_interval秒）推送一条链路的实时时延、带宽、丢包率等信息。

**参数**：

url 中 `<scenario-id>` 和 `<link-id>`

发送任意消息。

**返回值**：

*   成功响应

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| current_seconds | Number | 当前播放进度(秒)，相对于start_time的差值 |
| source_node_id | Number | 源节点id |
| target_node_id | Number | 目前节点id |
| source_node_name | String | 源节点名称 |
| target_node_name | String | 目的节点名称 |
| online | Boolean | 当前此链路是否在线（没有被用户手动置为Outage），若是则为true，否则为false |
| bandwidth | Number | 带宽信息 |
| loss | Number | 丢包率，[0,1] |
| delay | Number | 时延 |

*   失败响应

返回服务器错误信息。

**示例**：

\`\`\`
WebSocket /ws/satvis/2/link_attributes/12-45-1-3
\`\`\`

发送

\`\`\`
"SERNES"
\`\`\`

返回值

*   成功响应

\`\`\`
{
  "current_seconds": 12, // 当前播放进度(秒)，相对于start_time的差值
  "source_node_id": 122,
  "target_node_id": 123,
  "source_node_name": "Sat122",
  "target_node_name": "Sat123",
  "online": true, // 当前此链路是否在线（没有被用户手动置为Outage），若是则为true，否则为false
  "bandwidth": 1000,
  "loss": 0.01,
  "delay": 5000,
}
\`\`\`

#### 5.11 动态场景播放停止

> GET `/api/satvis/<scenario_id>/terminate`

**功能**：仿真动态场景播放停止操作。

**参数**：

url 中 `<scenario_id>`

**返回值**：

*   成功响应 - 200

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "success" |

*   失败响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
GET /api/satvis/scenario/2/terminate
\`\`\`

返回值

*   成功响应

\`\`\`
{
  "status": "success"
}
\`\`\`

*   失败响应

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

#### 5.12 网络实时状态推送

> WebSocket `/ws/satvis/vnode/status/`

**功能**：在网络中节点发生变化时推送增量变化，当用户手动控制该节点启动或者停止时会推送内容。

**参数**：

发送任意值

**返回值**：

*   成功响应

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| type | String | 节点类型状态，固定为 "node-update"， |
| data | Array | 数据列表 |

data 元素

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| node_id | Number | 节点id |
| node_type | String | 节点类型，为 "sat"、"gs" 和 "end_user" |
| event | String | "UP" 或者 "DOWN" |

*   失败响应

返回服务器错误信息。

**示例**：

\`\`\`
WebSocket /ws/satvis/2/link_attributes/12-45-1-3
\`\`\`

发送

\`\`\`
"SERNES"
\`\`\`

返回值

*   成功响应

\`\`\`
{
  "current_seconds": 12, // 当前播放进度(秒)，相对于start_time的差值
  "source_node_id": 122,
  "target_node_id": 123,
  "source_node_name": "Sat122",
  "target_node_name": "Sat123",
  "online": true, // 当前此链路是否在线（没有被用户手动置为Outage），若是则为true，否则为false
  "bandwidth": 1000,
  "loss": 0.01,
  "delay": 5000,
}
\`\`\`

### 6 BGP可视化平台

`/api/bgpvis/`

#### 6.1 获取网络拓扑

> GET `/api/bgpvis/topology`

**功能**：返回当前时刻运行的网络的状态。

**参数**：

无

**返回值**：

*   成功响应 - 200

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "success" |
| network_id | Number | 正在运行的网络id |
| nodes | Array | 节点信息列表 |
| links | Array | 链路信息列表 |

nodes 元素

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| id | Number | 节点id |
| name | String | 节点名称 |
| type | String | 节点类型，为"host"、"router"、"as"、"monitor" |
| alias | String | 节点别称 |
| status | String | 节点状态，"UP" 或者 "DOWN" |
| physical | Boolean | 是否为实物节点 |
| x | Array | 第一个参数为节点在画布中的x位置，中心点是(0, 0)，第二个参数为分辨率width |
| y | Array | 第一个参数为节点在画布中的y位置，中心点是(0, 0)，第二个参数为分辨率height |

*   失败响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
GET /api/bgpvis/topology
\`\`\`

返回值

*   成功响应

\`\`\`
{
    "status": "success",
    "network_id": 0,
    "nodes": [
        {
            "id": 1,
            "name": "AS1",
            "type": "router",
            "alias": "AS1",
            "status": "DOWN",
            "physical": true,
            "x": [
                -591.8478005191374,
                1602
            ],
            "y": [
                31.618981283416005,
                782
            ]
        }
    ],
    "links": [
        {
            "id": "1",
            "source_id": 2,
            "target_id": 3,
            "status": "UP"
        }
    ]
}
\`\`\`

*   失败响应

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

#### 6.2 保存拓扑布局

> POST `/api/bgpvis/topology/save`

**功能**：将当前布局保存到 yaml 中。

**参数**：

POST参数为 （body -- json） ，格式要求：

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| 多个节点的名称 | Object | 包含每一个节点的xy信息 |

节点 Object 结构

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| x | Array | 第一个参数为节点在画布中的x位置，中心点是(0, 0)，第二个参数为分辨率width |
| y | Array | 第一个参数为节点在画布中的y位置，中心点是(0, 0)，第二个参数为分辨率height |

**返回值**：

*   成功响应 - 200

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "success" |

*   失败响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
POST /api/bgpvis/topology/save
\`\`\`

参数

\`\`\`
{
    "node0" : {
        "x": [
            -163.21903797733037,
            1602
        ],
        "y": [
            -215.65374598931172,
            782
        ]
    },
    "node1": {
        "x": [
            -591.8478005191374,
            1602
        ],
        "y": [
            31.618981283416005,
            782
        ]
    }
}
\`\`\`

返回值

*   成功响应 - 200

\`\`\`
{
  "status": "success",
}
\`\`\`

*   失败响应 - 400/500

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

#### 6.3 网络实时状态推送

> WebSocket `/ws/bgpvis/status/`

**功能**：在网络发生变化时推送增量变化。

**参数**：

无

**返回值**：

*   成功响应

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| type | String | 节点类型状态，固定为 "node-update" 或者 "link-update" |
| data | Array | 数据列表 |

data 元素

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| node_id | Number | 节点id，如果是 "link-update" 则不返回该字段 |
| link_id | String | 链路id，如果是 "node-update" 则不返回该字段 |
| event | String | "UP" 或者 "DOWN" |

*   失败响应

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
WebSocket /ws/bgpvis/status/
\`\`\`

返回值

*   成功响应

\`\`\`
{
  "type": "link-update",
  "data": [
      {
        "link_id": "link0",
        "event": "UP" // UP DOWN
      },
      {
        "link_id": "link1",
        "event": "DOWN" // UP DOWN
      }
  ]
}

{
  "type": "node-update",
  "data": [
      {
        "node_id": 132,
        "event": "UP" // UP DOWN
      },
      {
        "node_id": 135,
        "event": "DOWN" // UP DOWN
      }
  ]
}
\`\`\`

*   失败响应

\`\`\`
{
  "type": "error",
  "msg": "Error message here..."
}
\`\`\`

#### 6.4 链路实时属性推送

> WebSocket `/ws/bgpvis/link_attributes/<link-id>`

**功能**：链路状态实时推送。

**参数**：

发送任意值

**返回值**：

*   成功响应

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| type | String | 响应状态，固定值，"success" |
| source_node_id | Number | 源节点id |
| target_node_id | Number | 目前节点id |
| source_node_name | String | 源节点名称 |
| target_node_name | String | 目的节点名称 |
| online | Boolean | 当前此链路是否在线，没有被用户手动置为DOWN，若是则为true，否则为false |
| bandwidth | Number | 带宽信息 |
| loss | Number | 丢包率，[0,1] |
| delay | Number | 时延 |

*   失败响应

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
WebSocket /ws/bgpvis/link_attributes/Node122-Node123-12-84
\`\`\`

发送

\`\`\`
"SERNES"
\`\`\`

返回值

*   成功响应

\`\`\`
{
  "type": "success",
  "source_node_id": 122,
  "target_node_id": 123,
  "source_node_name": "Node122",
  "target_node_name": "Node123",
  "online": true,
  "bandwidth": 1000,
  "loss": 0.01,
  "delay": 5000,
}
\`\`\`

*   失败响应

\`\`\`
{
  "type": "error",
  "msg": "Error message here..."
}
\`\`\`

### 7 平台工具接口

`/api/tools/`

#### 7.1 工具状态

> GET `/api/tools/status`

**功能**：对正在运行的网络，查看其各个工具是否正在运行。

**参数**：

无

**返回值**：

*   成功响应 - 200

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "success" |
| pcap_status | Number | 抓包工具状态 0-未运行 1-正在运行 |

*   失败响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
GET /api/tools/status
\`\`\`

返回值

*   成功响应

\`\`\`
{
    "status": "success",
    "pcap_status": 1 //抓包工具状态 0-未运行 1-正在运行
}
\`\`\`

*   失败响应

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

#### 7.2 日志下载

> POST `/api/tools/log/download`

**功能**：从正在运行的网络中挑选数个节点，下载其中的日志信息。

**参数**：

POST参数为 （body -- json） ，格式要求：

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| nodes | Array | 节点id的一个列表 |
| volumes | String | 必须是用户在yaml中配置过的volume |

**返回值**：

*   成功响应 - 200

`application/zip`

*   失败响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
POST /api/tools/log/download
\`\`\`

参数

\`\`\`
{
    "nodes": [12, 23, 56, 76], // NodeID
    "volumes": "/var/log" //必须是用户在yaml中配置过的volume
}
\`\`\`

返回值

*   成功响应 - 200

一个zip文件下载

*   失败响应 - 400/500

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

#### 7.3 开始抓包

> POST `/api/tools/pcap/start`

**功能**：开始抓取当前运行网络中的部分节点数据包。

**参数**：

POST参数为 （body -- json） ，格式要求：

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| nodes | Array | 节点id的一个列表 |

**返回值**：

*   成功响应 - 200

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "success" |

*   失败响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
POST /api/tools/pcap/start
\`\`\`

参数

\`\`\`
{
    "nodes": [12, 23, 56, 76], // NodeID
}
\`\`\`

返回值

*   成功响应 - 200

\`\`\`
{
    "status": "success",
}
\`\`\`

*   失败响应 - 400/500

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

#### 7.4 停止抓包

> GET `/api/tools/pcap/stop`

**功能**：停止抓取当前运行网络中的部分节点数据包。

**参数**：

无

**返回值**：

*   成功响应 - 200

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "success" |

*   失败响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
GET /api/tools/pcap/stop
\`\`\`

返回值

*   成功响应 - 200

\`\`\`
{
    "status": "success",
}
\`\`\`

*   失败响应 - 400/500

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

#### 7.5 包文件列表

> GET `/api/tools/pcap/<network-id>/list`

**功能**：列出在某个网络中已经抓取的数据包文件。

**参数**：

url 中 `<network-id>`

**返回值**：

*   成功响应 - 200

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "success" |
| data | Array | 一个包含数据包文件名的列表 |

*   失败响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
GET /api/tools/pcap/12/list
\`\`\`

返回值

*   成功响应 - 200

\`\`\`
{
  "status": "success",
  "data": [
       "20240705_175143.pcap",
       "20240705_175146.pcap"
  ]
}
\`\`\`

*   失败响应 - 400/500

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

#### 7.6 下载抓包文件

> GET `/api/tools/pcap/download`

**功能**：下载一个数据包文件。

**参数**：

参数 (Parameter) ：

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| network_id | Number | 网络id |
| file_name | String | 需要下载的数据包文件名 |

**返回值**：

*   成功响应 - 200

`application/zip`

*   失败响应 - 400/500

| 参数名 | 类型 | 描述 |
| --- | --- | --- |
| status | String | 响应状态，固定值 "error" |
| msg | String | 错误信息 |

**示例**：

\`\`\`
GET /api/tools/pcap/download?network_id=12&file_name=20240705_175146.pcap
\`\`\`

参数

\`\`\`
{
    "nodes": [12, 23, 56, 76], // NodeID
    "volumes": "/var/log" //必须是用户在yaml中配置过的volume
}
\`\`\`

返回值

*   成功响应 - 200

一个zip文件下载

*   失败响应 - 400/500

\`\`\`
{
  "status": "error",
  "msg": "错误信息"
}
\`\`\`

