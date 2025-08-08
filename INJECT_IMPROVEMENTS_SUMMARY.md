# 网络故障注入工具改进总结

## 改进内容

基于用户反馈，对 `experiment_utils/inject.py` 进行了两个重要改进：

### 1. 🔍 **添加示例命令展示**

#### 配置阶段示例命令
在注入执行前显示一条将要执行的示例命令，让用户清楚了解即将执行的操作。

**改进前**:
```
ℹ 故障注入类型: netem
ℹ 总链路数: 26
ℹ 故障链路数: 1 (3.8%)
ℹ 执行周期: 3
```

**改进后**:
```
ℹ 故障注入类型: netem
ℹ 总链路数: 26
ℹ 故障链路数: 1 (3.8%)
ℹ 执行周期: 3
ℹ 示例命令 (将要执行的命令类型):
  容器: clab-ospfv3-torus3x3-router_00_00
  接口: eth4
  命令: containerlab tools netem set -n clab-ospfv3-torus3x3-router_00_00 -i eth4 --loss 100 --delay 40ms
ℹ   (每个链路将在两个方向执行类似命令)
```

#### 每个周期的示例命令
在每个注入周期开始时显示具体的示例命令，包括故障注入和故障恢复阶段。

**新增功能**:
```
📋 第 1 周期示例命令:
  容器: clab-ospfv3-torus3x3-router_00_00
  接口: eth4
  操作: 故障注入
  命令: containerlab tools netem set -n clab-ospfv3-torus3x3-router_00_00 -i eth4 --loss 100 --delay 40ms

[执行故障注入...]
[等待间隔时间...]

📋 第 1 周期示例命令:
  容器: clab-ospfv3-torus3x3-router_00_00
  接口: eth4
  操作: 故障恢复
  命令: containerlab tools netem set -n clab-ospfv3-torus3x3-router_00_00 -i eth4 --loss 0 --delay 40ms
```

### 2. 🚨 **改进错误处理和提醒**

当执行错误时，提供标红提醒并立即退出，避免继续执行可能有问题的操作。

**错误检测和显示**:
```
✗ 故障注入失败 (2/2 个命令失败)
  ✗ container-name:eth4 - 执行错误: Command returned non-zero exit status 1.
  ✗ container-name:eth3 - 执行错误: Command returned non-zero exit status 1.

💥 第 1 个周期执行失败，停止执行
错误详情: 故障注入失败 (2/2 个命令失败)
```

### 3. 🎯 **修复指定单点故障的一致性问题**

修复了当指定单点故障且 `--max-executions > 1` 时，第二个周期及后续周期不使用相同链路的问题。

**问题**: 
- 指定 `--specific-link 0,0-0,1 --max-executions 3`
- 第一个周期使用 (0,0)-(0,1)
- 第二、三个周期可能使用随机选择的其他链路

**修复**:
```python
def generate_cycle_links():
    """生成每个周期的故障链路"""
    yield initial_failed_links
    for _ in range(1, injection_config.max_executions):
        # 如果指定了单点故障或者设置了一致性周期，则使用相同的链路
        if injection_config.specific_link or injection_config.consistent_cycles:
            yield initial_failed_links
        else:
            yield select_failed_links(all_links, injection_config.failure_ratio)
```

## 技术实现细节

### 示例命令展示

1. **配置阶段示例**: `show_example_command()`
   - 取第一个故障链路作为示例
   - 生成对应的注入命令
   - 以友好的格式显示容器、接口和命令

2. **周期阶段示例**: `show_cycle_example_command()`
   - 在每个注入周期开始时显示故障注入命令
   - 在每个注入周期中间显示故障恢复命令
   - 清楚标识周期号和操作类型

3. **集成到配置摘要**: 修改 `print_injection_summary()` 函数
   - 添加 `topology` 和 `prefix` 参数
   - 在配置信息后自动显示示例命令

4. **集成到执行周期**: 修改 `execute_injection_cycle()` 函数
   - 在故障注入前显示示例命令
   - 在故障恢复前显示示例命令

### 错误处理改进

1. **命令级别错误检测**:
   - 在 `execute_injection_cycle()` 中检查每个命令的执行结果
   - 统计失败的命令数量和详情

2. **周期级别错误处理**:
   - 在 `execute_cycles_functional()` 中检测周期失败
   - 立即停止执行并返回错误结果

3. **用户友好的错误显示**:
   - 使用红色标记错误信息
   - 显示失败命令的容器和接口信息
   - 限制错误详情显示数量（最多3个）

### 单点故障一致性修复

1. **逻辑改进**: 在链路生成逻辑中添加 `specific_link` 检查
2. **行为统一**: 指定单点故障时自动启用一致性模式
3. **向后兼容**: 保持 `--consistent-cycles` 参数的原有功能

## 使用示例

### 查看示例命令
```bash
# 预览模式会显示示例命令
uv run experiment_utils/inject.py clab-ospfv3-torus3x3 --failure-ratio 0.1
```

### 指定单点故障多周期
```bash
# 现在所有周期都会使用相同的指定链路
uv run experiment_utils/inject.py clab-ospfv3-torus3x3 \
  --specific-link 0,0-0,1 \
  --max-executions 3 \
  --execute
```

### 错误处理验证
```bash
# 如果容器不存在，会立即显示错误并退出
uv run experiment_utils/inject.py nonexistent-prefix \
  --execute
```

## 测试验证

通过以下测试验证了改进功能：

1. ✅ **配置阶段示例命令**: 确认在预览模式下正确显示示例命令
2. ✅ **周期阶段示例命令**: 验证每个周期都显示故障注入和恢复命令
3. ✅ **不同注入类型**: 确认 NETEM 和 LINK 类型都正确显示
4. ✅ **错误检测**: 验证命令失败时的错误检测和显示
5. ✅ **单点故障一致性**: 确认多个周期使用相同的指定链路
6. ✅ **向后兼容性**: 确认原有功能不受影响

## 总结

这些改进显著提升了工具的用户体验：

- **🔍 透明性**: 用户可以清楚看到将要执行的命令类型
- **📋 实时性**: 每个周期都显示具体的执行命令，便于跟踪和调试
- **🚨 安全性**: 错误时立即停止，避免继续执行有问题的操作
- **🎯 一致性**: 指定单点故障时行为更加可预测
- **💡 友好性**: 更好的错误提示和状态显示

所有改进都保持了向后兼容性，现有的使用方式和参数都继续有效。
