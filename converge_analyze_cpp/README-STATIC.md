# 静态编译版本 - Alpine Linux x64 支持

本文档说明如何构建和使用静态编译版本的网络收敛分析工具，特别适用于Alpine Linux x64系统。

## 🎯 特性

- ✅ **完全静态链接** - 无需任何动态库依赖
- ✅ **Alpine Linux 优化** - 专为Alpine Linux x64设计
- ✅ **单文件部署** - 只需一个可执行文件
- ✅ **跨发行版兼容** - 可在不同Linux发行版间移植
- ✅ **信号处理修复** - 正确处理Ctrl+C退出
- ✅ **QDisc事件监听** - 真正解析netlink消息

## 🚀 快速开始

### 1. 静态编译

```bash
# 在开发机器上编译
cd converge_analyze_cpp
./build-static.sh

# 或者指定libc类型
./build-static.sh musl    # 推荐用于Alpine
./build-static.sh glibc   # 用于其他发行版
```

### 2. 部署到Alpine Linux

```bash
# 复制静态编译的可执行文件到Alpine系统
scp build-static/ConvergenceAnalyzer user@alpine-host:/usr/local/bin/

# 在Alpine系统上运行
./ConvergenceAnalyzer --threshold 3000 --router-name alpine-router
```

## 📋 构建要求

### 开发机器 (编译环境)

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install cmake build-essential libc6-dev uuid-dev pkg-config
```

**Alpine Linux:**
```bash
apk add cmake build-base musl-dev util-linux-dev linux-headers pkgconfig
```

**CentOS/RHEL:**
```bash
sudo yum install cmake gcc-c++ glibc-static libuuid-devel pkgconfig
```

### 目标机器 (运行环境)

**无需任何依赖** - 静态编译的可执行文件可以直接运行！

## 🔧 构建选项

### 基本构建
```bash
./build-static.sh          # 默认musl静态编译
./build-static.sh musl     # 明确指定musl
./build-static.sh glibc    # 使用glibc静态编译
./build-static.sh clean    # 清理构建文件
```

### 高级构建
```bash
# 使用特定编译器
CC=gcc CXX=g++ ./build-static.sh

# 查看帮助
./build-static.sh help
```

## 📊 验证静态链接

```bash
# 检查文件类型
file build-static/ConvergenceAnalyzer
# 输出: ELF 64-bit LSB executable, x86-64, version 1 (GNU/Linux), statically linked

# 检查动态库依赖
ldd build-static/ConvergenceAnalyzer
# 输出: not a dynamic executable

# 检查文件大小
ls -lh build-static/ConvergenceAnalyzer
# 约2.8MB
```

## 🐛 问题修复

### 1. 信号处理问题
- ✅ **已修复**: 程序现在能正确响应Ctrl+C信号并优雅退出
- ✅ **改进**: 使用非阻塞socket避免recv()调用阻塞
- ✅ **优化**: 信号处理器立即停止监控器

### 2. QDisc事件监听问题  
- ✅ **已修复**: 真正解析netlink消息而不是返回假数据
- ✅ **改进**: 正确解析TC消息中的netem信息
- ✅ **优化**: 支持完整的QDisc属性解析

## 🎮 使用示例

### 基本监控
```bash
# 启动监控
./ConvergenceAnalyzer --threshold 3000 --router-name alpine-test

# 在另一个终端触发netem事件
sudo tc qdisc add dev eth0 root netem delay 10ms

# 使用Ctrl+C停止监控
```

### 高级配置
```bash
# 自定义日志路径和阈值
./ConvergenceAnalyzer \
  --threshold 5000 \
  --router-name production-spine1 \
  --log-path /tmp/convergence.json
```

## 📁 文件结构

```
converge_analyze_cpp/
├── build-static.sh          # 静态编译脚本
├── build.sh                 # 常规编译脚本  
├── CMakeLists.txt           # CMake配置
├── build-static/            # 静态编译输出目录
│   └── ConvergenceAnalyzer  # 静态链接的可执行文件
├── main.cpp                 # 主程序
├── convergence_monitor.*    # 监控器实现
├── netlink_monitor.*        # Netlink监听器
└── logger.*                 # 日志记录器
```

## 🔍 技术细节

### 静态链接配置
- 使用 `-static` 编译标志
- 强制使用静态库 `.a` 文件
- 禁用共享库构建
- 静态链接 libgcc 和 libstdc++

### 兼容性
- **目标架构**: x86_64
- **最低内核**: Linux 3.2.0+
- **Alpine版本**: 3.10+
- **glibc版本**: 2.17+ (如果使用glibc构建)

### 性能特性
- 多线程netlink事件处理
- 原子操作和无锁数据结构
- 非阻塞socket I/O
- 高效的内存管理

## 🚨 注意事项

1. **NSS警告**: 静态链接可能在某些系统上产生NSS相关警告，这是正常的
2. **文件大小**: 静态链接会增加文件大小（约2.8MB）
3. **权限要求**: 监听netlink事件需要适当的权限
4. **内存使用**: 静态链接可能略微增加内存使用

## 📞 支持

如果遇到问题：
1. 检查构建日志中的错误信息
2. 确认目标系统架构为x86_64
3. 验证内核版本支持netlink
4. 检查运行权限

## 🎉 成功标志

当看到以下输出时，说明静态编译成功：
```
[SUCCESS] 确认: 可执行文件已完全静态链接
[SUCCESS] 可执行文件测试通过
[SUCCESS] 静态编译的可执行文件: build-static/ConvergenceAnalyzer
[INFO] 此文件可以在Alpine Linux x64系统上运行
```
