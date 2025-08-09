#!/usr/bin/env python3
"""
函数式版本的Torus拓扑批量命令执行脚本
在所有节点上执行指定命令

特性:
- 函数式编程风格
- 类型安全的配置管理
- 改进的错误处理和结果报告
- 更好的并发处理
- 进程管理功能
- 可组合的操作流水线

使用方法:
    python3 execute_on_torus_functional.py clab-ospfv3-torus9x9 9 "ping -c 3 google.com"
    python3 execute_on_torus_functional.py clab-ospfv3-torus5x5 5 "iperf3 -s" --detach
    python3 execute_on_torus_functional.py clab-ospfv3-torus9x9 9 --kill-process "iperf3" --signal INT
"""

import time
from dataclasses import dataclass
from enum import Enum

from typing import List, Optional, Tuple, Iterator

import anyio
from anyio import create_task_group

# 依赖：使用 Typer/Rich（已在 pyproject.toml 中由 uv 管理）
import typer
from rich.table import Table
from rich.console import Console
# 复用工具（支持脚本直接运行与包运行）
try:
    from experiment_utils.utils import (
        Result,
        ExecutionConfig,
        log_info,
        log_error,
        log_success,
        log_warning,
        ProgressReporter,
        run_shell_with_retry,
        generate_container_names,
    )
except ModuleNotFoundError:
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
    from experiment_utils.utils import (
        Result,
        ExecutionConfig,
        log_info,
        log_error,
        log_success,
        log_warning,
        ProgressReporter,
        run_shell_with_retry,
        generate_container_names,
    )


console = Console()

# ============================================================================
# 内置轻量工具：Result、配置对象、日志与进度（单文件自包含）
# ============================================================================

@dataclass(frozen=True)
class NetworkConfig:
    prefix: str
    size: int
    topology_type: str = "torus"

# ============================================================================
# 核心数据类型
# ============================================================================

class ExecutionMode(Enum):
    """执行模式"""
    FOREGROUND = "foreground"
    DETACH = "detach"
    KILL_PROCESS = "kill_process"

class Signal(Enum):
    """信号类型"""
    TERM = "TERM"
    INT = "INT"
    KILL = "KILL"
    HUP = "HUP"
    USR1 = "USR1"
    USR2 = "USR2"

@dataclass(frozen=True)
class ExecutionTask:
    """执行任务"""
    container_name: str
    command: str
    mode: ExecutionMode
    signal: Optional[Signal] = None
    process_pattern: Optional[str] = None
    runtime: str = "docker"  # 容器运行时: docker 或 podman

@dataclass(frozen=True)
class ExecutionResult:
    """执行结果"""
    container_name: str
    success: bool
    output: str = ""
    error: Optional[str] = None
    duration: float = 0.0
    pids_affected: List[str] = None

    def __post_init__(self):
        if self.pids_affected is None:
            object.__setattr__(self, 'pids_affected', [])

@dataclass(frozen=True)
class ProcessInfo:
    """进程信息"""
    pid: str
    command: str
    container_name: str

# ============================================================================
# 纯函数 - 任务生成逻辑
# ============================================================================




def create_execution_task(
    container_name: str,
    command: str,
    mode: ExecutionMode,
    signal: Optional[Signal] = None,
    process_pattern: Optional[str] = None,
    runtime: str = "docker"
) -> ExecutionTask:
    """创建执行任务"""
    return ExecutionTask(
        container_name=container_name,
        command=command,
        mode=mode,
        signal=signal,
        process_pattern=process_pattern,
        runtime=runtime
    )

def create_command_execution_tasks(
    container_names: List[str],
    command: str,
    detach: bool = False,
    runtime: str = "docker"
) -> List[ExecutionTask]:
    """创建命令执行任务列表"""
    mode = ExecutionMode.DETACH if detach else ExecutionMode.FOREGROUND
    return [
        create_execution_task(name, command, mode, runtime=runtime)
        for name in container_names
    ]

def create_process_kill_tasks(
    container_names: List[str],
    process_pattern: str,
    signal: Signal = Signal.TERM,
    runtime: str = "docker"
) -> List[ExecutionTask]:
    """创建进程终止任务列表"""
    return [
        create_execution_task(
            name, "", ExecutionMode.KILL_PROCESS, signal, process_pattern, runtime
        )
        for name in container_names
    ]

# ============================================================================
# 命令执行函数
# ============================================================================

def build_container_command(task: ExecutionTask) -> str:
    """构建容器命令 - 纯函数"""
    if task.runtime not in ("docker", "podman"):
        raise ValueError(f"不支持的容器运行时: {task.runtime}. 支持的运行时: docker, podman")

    if task.mode == ExecutionMode.DETACH:
        return f"{task.runtime} exec -d {task.container_name} {task.command}"
    else:
        return f"{task.runtime} exec {task.container_name} {task.command}"

# 保持向后兼容性的别名
def build_docker_command(task: ExecutionTask) -> str:
    """构建Docker命令 - 向后兼容性别名"""
    return build_container_command(task)

def create_execution_result(
    container_name: str,
    success: bool,
    duration: float,
    output: str = "",
    error: Optional[str] = None,
    pids_affected: Optional[List[str]] = None
) -> ExecutionResult:
    """创建执行结果 - 纯函数"""
    return ExecutionResult(
        container_name=container_name,
        success=success,
        output=output,
        error=error,
        duration=duration,
        pids_affected=pids_affected or []
    )

def handle_subprocess_error(e: Exception, container_name: str, duration: float) -> ExecutionResult:
    """处理子进程错误 - 纯函数"""
    import subprocess

    if isinstance(e, subprocess.CalledProcessError):
        error_msg = e.stderr.strip() if e.stderr else str(e)
        return create_execution_result(container_name, False, duration, error=f"命令失败: {error_msg}")
    elif isinstance(e, subprocess.TimeoutExpired):
        return create_execution_result(container_name, False, duration, error="命令超时")
    else:
        return create_execution_result(container_name, False, duration, error=f"未知错误: {str(e)}")

async def execute_docker_command(cmd: str, container_name: str, timeout: int = 60) -> ExecutionResult:
    """异步执行Docker命令 - 函数式错误处理"""
    start_time = time.time()

    try:
        # 用 anyio 运行子进程，兼容复杂命令用 shell
        rc, out, err = await run_shell_with_retry(cmd, timeout)
        duration = time.time() - start_time
        if rc == 0:
            return create_execution_result(container_name, True, duration, output=out)
        else:
            return create_execution_result(
                container_name, False, duration,
                error=(f"命令失败: {err}" if err else f"返回码: {rc}")
            )

    except TimeoutError:
        duration = time.time() - start_time
        return create_execution_result(container_name, False, duration, error="命令超时")
    except Exception as e:
        duration = time.time() - start_time
        return create_execution_result(container_name, False, duration, error=f"未知错误: {str(e)}")

async def execute_command_task(task: ExecutionTask) -> ExecutionResult:
    """异步执行命令任务 - 简化版"""
    if task.mode == ExecutionMode.KILL_PROCESS:
        return await execute_kill_process_task(task)

    cmd = build_container_command(task)
    return await execute_docker_command(cmd, task.container_name)

async def find_process_pids(container_name: str, pattern: str, runtime: str = "docker") -> Result[List[str], str]:
    """异步查找进程PID - 纯函数式处理"""
    try:
        pgrep_cmd = f"{runtime} exec {container_name} pgrep -f '{pattern}'"

        rc, out, _ = await run_shell_with_retry(pgrep_cmd, 30)
        if rc != 0 or not out:
            return Result.ok([])
        pids = [pid.strip() for pid in out.split('\n') if pid.strip()]
        return Result.ok(pids)

    except TimeoutError:
        return Result.error("查找进程超时")
    except Exception as e:
        return Result.error(f"查找进程失败: {str(e)}")

async def kill_processes_by_pids(container_name: str, pids: List[str], signal: Signal, runtime: str = "docker") -> Result[str, str]:
    """异步根据PID终止进程 - 纯函数式处理"""
    if not pids:
        return Result.ok("没有进程需要终止")

    try:
        pids_str = ' '.join(pids)
        signal_name = signal.value
        kill_cmd = f"{runtime} exec {container_name} kill -{signal_name} {pids_str}"

        rc, _, err = await run_shell_with_retry(kill_cmd, 30)
        if rc == 0:
            return Result.ok(f"成功终止 {len(pids)} 个进程")
        else:
            return Result.error(f"终止进程失败: {err if err else f'返回码: {rc}'}")
    except Exception as e:
        return Result.error(f"终止进程失败: {str(e)}")

async def execute_kill_process_task(task: ExecutionTask) -> ExecutionResult:
    """异步执行进程终止任务 - 函数式组合"""
    start_time = time.time()

    # 异步函数式管道：查找PID -> 终止进程 -> 创建结果
    pids_result = await find_process_pids(task.container_name, task.process_pattern, task.runtime)

    if pids_result.is_error():
        duration = time.time() - start_time
        return create_execution_result(
            task.container_name, False, duration,
            error=pids_result._error
        )

    pids = pids_result.unwrap()
    kill_result = await kill_processes_by_pids(task.container_name, pids, task.signal or Signal.TERM, task.runtime)

    duration = time.time() - start_time

    if kill_result.is_ok():
        message = kill_result.unwrap()
        return create_execution_result(
            task.container_name, True, duration,
            output=message, pids_affected=pids
        )
    else:
        return create_execution_result(
            task.container_name, False, duration,
            error=kill_result._error
        )

async def execute_tasks_batch(
    tasks: List[ExecutionTask],
    exec_config: ExecutionConfig
) -> List[Result[ExecutionResult, str]]:
    """异步批量执行任务"""
    semaphore = anyio.Semaphore(exec_config.max_workers)

    async def execute_with_semaphore(task: ExecutionTask) -> Result[ExecutionResult, str]:
        async with semaphore:
            try:
                result = await execute_command_task(task)
                return Result.ok(result)
            except Exception as e:
                return Result.error(str(e))

    results: List[Result[ExecutionResult, str]] = []
    with ProgressReporter() as progress:
        if progress.use_rich:
            task_id = progress.create_task("执行任务", len(tasks))
            async with create_task_group() as tg:
                for task in tasks:
                    async def runner(t: ExecutionTask):
                        res = await execute_with_semaphore(t)
                        results.append(res)
                        progress.update_task(task_id, 1)
                    tg.start_soon(runner, task)
        else:
            # 无进度条时直接顺序执行（也可换成并发，如有需要）
            for t in tasks:
                results.append(await execute_with_semaphore(t))
    return results

# ============================================================================
# 显示和报告函数
# ============================================================================

def print_configuration_summary(
    network_config: NetworkConfig,
    command: str,
    mode: ExecutionMode,
    total_tasks: int,
    process_pattern: Optional[str] = None,
    signal: Optional[Signal] = None
):
    """打印配置摘要"""
    if console:
        table = Table(title=f"{network_config.size}x{network_config.size} Torus 批量执行配置")
        table.add_column("配置项", style="cyan")
        table.add_column("值", style="green")

        table.add_row("容器前缀", network_config.prefix)
        table.add_row("网格大小", f"{network_config.size}x{network_config.size}")
        table.add_row("总任务数", str(total_tasks))
        table.add_row("执行模式", mode.value)

        if mode == ExecutionMode.KILL_PROCESS:
            table.add_row("进程模式", process_pattern or "")
            table.add_row("信号", signal.value if signal else "TERM")
        else:
            table.add_row("命令", command)

        console.print(table)
    else:
        log_info(f"=== 在 {network_config.size}x{network_config.size} Torus 拓扑上执行任务 ===")
        if mode == ExecutionMode.KILL_PROCESS:
            log_info(f"进程模式: {process_pattern}")
            log_info(f"信号: {signal.value if signal else 'TERM'}")
        else:
            log_info(f"命令: {command}")
        log_info(f"执行模式: {mode.value}")
        log_info(f"总计 {total_tasks} 个任务")

def print_tasks_preview(tasks: List[ExecutionTask], max_display: int = 5):
    """打印任务预览"""
    log_info("任务预览:")
    for task in tasks[:max_display]:
        if task.mode == ExecutionMode.KILL_PROCESS:
            log_info(f"  在 {task.container_name} 中终止匹配 '{task.process_pattern}' 的进程")
        else:
            log_info(f"  在 {task.container_name} 中执行: {task.command}")

    if len(tasks) > max_display:
        log_info(f"  ... 还有 {len(tasks) - max_display} 个任务")

def categorize_results(results: List[Result[ExecutionResult, str]]) -> Tuple[List[ExecutionResult], List[ExecutionResult]]:
    """分类结果 - 纯函数"""
    def extract_result(result: Result[ExecutionResult, str]) -> ExecutionResult:
        if result.is_ok():
            return result.unwrap()
        else:
            return ExecutionResult("unknown", False, error=result._error)

    extracted = [extract_result(r) for r in results]
    successful = [r for r in extracted if r.success]
    failed = [r for r in extracted if not r.success]

    return successful, failed

def print_failure_summary(failed_results: List[ExecutionResult], max_display: int = 5):
    """打印失败摘要 - 副作用隔离"""
    if not failed_results:
        return

    log_warning(f"失败的任务 ({len(failed_results)} 个):")
    for result in failed_results[:max_display]:
        log_error(f"  - {result.container_name}: {result.error}")

    if len(failed_results) > max_display:
        log_warning(f"  ... 还有 {len(failed_results) - max_display} 个失败")

def print_performance_stats(successful_results: List[ExecutionResult]):
    """打印性能统计 - 副作用隔离"""
    if not successful_results:
        return

    durations = [r.duration for r in successful_results]
    avg_time = sum(durations) / len(durations)
    log_info(f"平均执行时间: {avg_time:.2f}秒")

    # 进程终止统计
    total_pids = sum(len(r.pids_affected or []) for r in successful_results)
    if total_pids > 0:
        log_info(f"总计终止进程数: {total_pids}")

def print_execution_results(results: List[Result[ExecutionResult, str]]):
    """打印执行结果 - 函数式组合"""
    successful_results, failed_results = categorize_results(results)

    # 总体统计
    log_success(f"完成: {len(successful_results)}/{len(results)} 成功")

    # 详细信息
    print_failure_summary(failed_results)
    print_performance_stats(successful_results)

# ============================================================================
# 函数式辅助函数
# ============================================================================

def determine_execution_mode(process_pattern: Optional[str], detach: bool) -> ExecutionMode:
    """确定执行模式 - 纯函数"""
    if process_pattern:
        return ExecutionMode.KILL_PROCESS
    elif detach:
        return ExecutionMode.DETACH
    else:
        return ExecutionMode.FOREGROUND

def create_tasks_pipeline(
    network_config: NetworkConfig,
    command: str,
    detach: bool,
    process_pattern: Optional[str],
    signal: Signal,
    runtime: str = "docker"
) -> List[ExecutionTask]:
    """创建任务管道 - 函数式组合"""
    container_names = list(generate_container_names(network_config.prefix, network_config.size))
    mode = determine_execution_mode(process_pattern, detach)

    if mode == ExecutionMode.KILL_PROCESS:
        return create_process_kill_tasks(container_names, process_pattern, signal, runtime)
    else:
        return create_command_execution_tasks(container_names, command, detach, runtime)

def extract_execution_results(results: List[Result[ExecutionResult, str]]) -> List[ExecutionResult]:
    """提取执行结果 - 函数式映射"""
    def safe_extract(result: Result[ExecutionResult, str]) -> ExecutionResult:
        return (result.unwrap() if result.is_ok()
                else ExecutionResult("unknown", False, error=result._error))

    return [safe_extract(r) for r in results]

def handle_preview_mode(tasks: List[ExecutionTask]) -> Result[List[ExecutionResult], str]:
    """处理预览模式 - 副作用隔离"""
    print_tasks_preview(tasks)
    log_info("使用 --execute 参数来实际执行任务")
    return Result.ok([])

async def execute_tasks_pipeline(
    tasks: List[ExecutionTask],
    exec_config: ExecutionConfig
) -> Result[List[ExecutionResult], str]:
    """异步执行任务管道 - 函数式错误处理"""
    try:
        log_info(f"开始执行 {len(tasks)} 个任务...")

        results = await execute_tasks_batch(tasks, exec_config)
        print_execution_results(results)

        exec_results = extract_execution_results(results)
        return Result.ok(exec_results)

    except Exception as e:
        return Result.error(f"执行任务失败: {str(e)}")

# ============================================================================
# 主要业务逻辑 - 简化版
# ============================================================================

async def execute_on_torus_functional(
    network_config: NetworkConfig,
    exec_config: ExecutionConfig,
    command: str = "",
    detach: bool = False,
    process_pattern: Optional[str] = None,
    signal: Signal = Signal.TERM,
    execute: bool = False,
    show_preview: bool = True
) -> Result[List[ExecutionResult], str]:
    """简化的异步函数式Torus批量执行

    使用函数式编程原则：
    - 纯函数组合
    - 管道式数据流
    - 副作用隔离
    - 单一职责
    - 异步IO操作
    """

    # 函数式管道：创建任务 -> 显示配置 -> 处理模式
    tasks = create_tasks_pipeline(network_config, command, detach, process_pattern, signal, exec_config.runtime)
    mode = determine_execution_mode(process_pattern, detach)

    # 显示配置摘要 - 副作用隔离
    print_configuration_summary(network_config, command, mode, len(tasks), process_pattern, signal)

    # 条件分支处理 - 函数式风格
    if show_preview and not execute:
        return handle_preview_mode(tasks)

    if not execute:
        return Result.ok([])

    return await execute_tasks_pipeline(tasks, exec_config)

# ============================================================================
# CLI接口
# ============================================================================

def create_typer_app():
    """创建Typer应用"""
    app = typer.Typer(
        name="execute_on_torus_functional",
        help="函数式版本的Torus拓扑批量命令执行脚本",
        epilog="在所有节点上执行指定命令或管理进程"
    )

    @app.command()
    def main(
        prefix: str = typer.Argument(..., help="容器名前缀 (如: clab-ospfv3-torus9x9)"),
        size: int = typer.Argument(..., help="网格大小"),
        command: str = typer.Argument("", help="要执行的命令"),
        execute: bool = typer.Option(False, "--execute", help="执行命令"),
        detach: bool = typer.Option(False, "--detach", help="后台执行命令"),
        kill_process: Optional[str] = typer.Option(None, "--kill-process", help="终止匹配的进程"),
        signal: str = typer.Option("TERM", "--signal", help="发送的信号 (TERM, INT, KILL等)"),
        workers: int = typer.Option(4, "--workers", help="并发工作线程数"),
        timeout: int = typer.Option(30, "--timeout", help="命令超时时间(秒)"),
        runtime: str = typer.Option("docker", "--runtime", help="容器运行时 (docker/podman)"),
        verbose: bool = typer.Option(False, "--verbose", help="显示详细信息")
    ):
        """在Torus拓扑上批量执行命令或管理进程"""
        try:
            # 验证参数
            if not kill_process and not command:
                log_error("必须提供命令或使用 --kill-process 选项")
                raise typer.Exit(1)

            if kill_process and command:
                log_error("不能同时使用命令和 --kill-process 选项")
                raise typer.Exit(1)

            # 验证信号
            try:
                signal_enum = Signal(signal.upper())
            except ValueError:
                log_error(f"无效的信号: {signal}. 可用信号: {', '.join([s.value for s in Signal])}")
                raise typer.Exit(1)

            # 验证容器运行时
            if runtime not in ("docker", "podman"):
                log_error(f"无效的容器运行时: {runtime}. 支持的运行时: docker, podman")
                raise typer.Exit(1)

            # 创建配置对象
            network_config = NetworkConfig(prefix=prefix, size=size, topology_type="torus")
            exec_config = ExecutionConfig(max_workers=workers, timeout=timeout, verbose=verbose, runtime=runtime)

            # 执行主要逻辑 - 异步调用（anyio）
            result = anyio.run(execute_on_torus_functional,
                network_config,
                exec_config,
                command,
                detach,
                kill_process,
                signal_enum,
                execute,
                not execute,
            )

            if result.is_error():
                log_error(result._error)
                raise typer.Exit(1)

            log_success("批量执行完成")

        except Exception as e:
            log_error(f"未知错误: {str(e)}")
            raise typer.Exit(1)

    return app



def main():
    """主入口函数 - 使用Typer"""
    app = create_typer_app()
    app()

if __name__ == "__main__":
    main()
