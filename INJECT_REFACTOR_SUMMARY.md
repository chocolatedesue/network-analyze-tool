# 网络故障注入工具重构总结

## 重构目标

基于用户要求，对 `experiment_utils/inject.py` 进行重构，目标是：
- 从拓展性可读性优化
- 用 anyio 优化
- 保持交互方式不变
- 去掉复杂依赖和状态

## 重构前的问题

1. **复杂依赖**: 依赖不存在的 `functional_utils` 模块
2. **同步阻塞**: 使用 `ThreadPoolExecutor` 和 `time.sleep()`
3. **状态管理复杂**: 多层嵌套的状态传递
4. **代码冗余**: 存在未使用的 argparse 接口

## 重构后的改进

### 1. 使用 anyio 统一异步处理

**之前**:
```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def execute_commands_batch(commands, exec_config):
    with ThreadPoolExecutor(max_workers=exec_config.max_workers) as executor:
        futures = [executor.submit(execute_injection_command, cmd) for cmd in commands]
        # ...
```

**现在**:
```python
import anyio

async def execute_commands_batch(commands, exec_config):
    semaphore = anyio.Semaphore(exec_config.max_workers)
    async with anyio.create_task_group() as tg:
        # 异步并发执行
```

### 2. 简化依赖结构

**移除的依赖**:
- `functional_utils` (不存在的模块)
- `concurrent.futures`
- `asyncio` (未使用)
- 复杂的 `argparse` 接口

**保留的核心依赖**:
- `anyio` - 统一异步框架
- `typer` - CLI 框架
- `rich` - 终端输出美化

### 3. 去除复杂状态管理

**之前**:
```python
# 复杂的函数式管道和状态传递
return (setup_topology_and_links(prefix, injection_config)
        .map(lambda data: handle_topology_setup(*data, prefix, injection_config))
        .and_then(lambda context: handle_execution_mode(context, execute, show_preview, exec_config)))
```

**现在**:
```python
# 简化的异步流程
setup_result = setup_topology_and_links(prefix, injection_config)
if setup_result.is_error():
    return setup_result

context = handle_topology_setup(*setup_result.unwrap(), prefix, injection_config)
return await handle_execution_mode(context, execute, show_preview, exec_config)
```

### 4. 内置工具类型

**之前**: 依赖外部 `functional_utils.Result`
**现在**: 内置简化的 `Result` 类型

```python
@dataclass(frozen=True)
class Result:
    """简化的 Result 类型，用于错误处理"""
    _value: Optional[any] = None
    _error: Optional[str] = None
    
    @classmethod
    def ok(cls, value):
        return cls(_value=value)
    
    @classmethod
    def error(cls, error: str):
        return cls(_error=error)
```

### 5. 改进的异步命令执行

**之前**: 同步 subprocess 调用
**现在**: anyio 异步进程执行

```python
async def execute_injection_command(command: InjectionCommand, timeout: int = 30):
    cmd_list = ["sh", "-c", command.command]
    
    with anyio.move_on_after(timeout):
        result = await anyio.run_process(
            cmd_list,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
```

## 性能改进

1. **并发性能**: 使用 anyio 的异步并发，比线程池更高效
2. **资源使用**: 异步 I/O 减少线程开销
3. **响应性**: 非阻塞等待，更好的用户体验

## 兼容性保证

✅ **CLI 接口完全兼容**:
```bash
# 所有原有命令都能正常工作
uv run experiment_utils/inject.py clab-ospfv3-torus5x5 --max-executions 3 -t netem
uv run experiment_utils/inject.py clab-ospfv3-grid5x5 --failure-ratio 0.2 -t link
uv run experiment_utils/inject.py clab-ospfv3-torus5x5 --specific-link 0,0-0,1 --execute
```

✅ **功能完全保持**:
- 拓扑解析 (grid/torus)
- 故障注入类型 (link/netem)
- 预览模式
- 批量执行
- 进度显示

## 代码质量改进

1. **可读性**: 去除复杂的函数式管道，逻辑更清晰
2. **可维护性**: 减少依赖，内聚性更强
3. **可扩展性**: anyio 提供更好的异步扩展能力
4. **类型安全**: 保持完整的类型注解

## 测试验证

创建了 `test_inject_refactor.py` 验证:
- ✅ 基本功能 (拓扑解析、链路生成)
- ✅ 异步命令执行
- ✅ 预览模式
- ✅ CLI 接口兼容性

## 使用建议

1. **开发环境**: 使用 `uv run` 执行脚本
2. **生产环境**: anyio 提供更好的性能和稳定性
3. **扩展开发**: 基于 anyio 的异步架构更容易扩展新功能

## 总结

这次重构成功实现了所有目标：
- ✅ 提升了可扩展性和可读性
- ✅ 使用 anyio 优化了异步处理
- ✅ 完全保持了交互方式不变
- ✅ 去除了复杂依赖和状态管理

重构后的代码更加现代化、高效且易于维护，为后续功能扩展奠定了良好基础。
