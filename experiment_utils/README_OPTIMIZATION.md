# Simple Delay 脚本优化总结

## 优化特性

### 1. 使用 utils.py 的可复用工具
- **Result 类型**: 提供类型安全的结果处理，替代元组返回值
- **ExecutionConfig**: 统一的执行配置管理
- **ProgressReporter**: 改进的进度条显示，使用 Rich 库
- **日志函数**: 彩色日志输出 (log_info, log_success, log_warning, log_error)

### 2. 改进的错误处理和重试机制
- **run_shell_with_retry**: 带重试的命令执行，使用指数退避策略
- **TransientShellError**: 区分短暂性错误，仅重试可恢复的失败
- **类型安全**: DelayConfig 数据类验证输入参数

### 3. 优化的并发处理
- **异步架构**: 完全基于 anyio 的异步操作
- **信号量控制**: 限制并发度，避免资源过载
- **任务组管理**: 使用 anyio.create_task_group() 确保所有任务完成

### 4. 模块化设计
- **DelayConfig**: 延迟配置数据类
- **函数分离**: 命令生成、执行、进度管理分离
- **可复用工具**: 延迟配置工具移至 utils.py，可供其他脚本使用

## 主要改进对比

### 原版本
```python
# 简单的元组返回
def execute_command(cmd: str) -> Tuple[bool, Optional[str]]:
    try:
        subprocess.run(cmd, shell=True, check=True, capture_output=True)
        return True, None
    except subprocess.CalledProcessError:
        return False, f"命令失败: {cmd}"

# 手动进度条管理
if HAS_RICH and not verbose:
    with Progress(...) as progress_ctx:
        # 复杂的进度条逻辑
```

### 优化版本
```python
# 类型安全的 Result 类型
async def execute_delay_command(cmd: str, config: ExecutionConfig) -> Result[str, str]:
    try:
        rc, out, err = await run_shell_with_retry(cmd, config.timeout)
        if rc == 0:
            return Result.ok(out)
        else:
            return Result.error(f"命令执行失败 (rc={rc}): {err}")

# 简化的进度条管理
with ProgressReporter() as reporter:
    task_id = reporter.create_task("配置网络延迟", len(commands))
    # 自动处理进度更新
```

## 使用示例

### 基本使用
```bash
# 预览模式 (不执行命令)
uv run python experiment_utils/simple_delay.py clab-torus5x5 5

# 实际执行
uv run python experiment_utils/simple_delay.py clab-torus5x5 5 --execute

# 自定义延迟值
uv run python experiment_utils/simple_delay.py clab-torus5x5 5 \
    --vertical 15 --horizontal 25 --execute

# 使用 Podman 运行时
uv run python experiment_utils/simple_delay.py clab-torus5x5 5 \
    --runtime podman --execute

# 调整并发度和超时
uv run python experiment_utils/simple_delay.py clab-torus5x5 5 \
    --workers 8 --timeout 60 --verbose --execute
```

### 在其他脚本中使用工具函数
```python
from experiment_utils.utils import (
    DelayConfig, 
    ExecutionConfig, 
    set_torus_delays_async
)

# 创建配置
delay_config = DelayConfig(
    prefix="my-torus",
    size=3,
    vertical_delay=5,
    horizontal_delay=10,
    runtime="docker"
)

exec_config = ExecutionConfig(
    max_workers=6,
    timeout=45,
    verbose=True
)

# 异步执行
result = await set_torus_delays_async(delay_config, exec_config, execute=True)
if result.is_ok():
    print("配置成功!")
else:
    print(f"配置失败: {result.unwrap_error()}")
```

## 性能改进

1. **并发执行**: 并行处理多个命令，显著提高执行速度
2. **重试机制**: 自动重试短暂性失败，提高成功率
3. **进度显示**: 实时进度反馈，改善用户体验
4. **资源控制**: 信号量限制并发度，避免系统过载

## 错误处理改进

1. **详细错误信息**: 提供具体的失败原因和返回码
2. **分类错误处理**: 区分用户错误、系统错误和网络错误
3. **优雅降级**: 部分失败时继续执行，最后统一报告
4. **类型安全**: 编译时捕获类型错误
