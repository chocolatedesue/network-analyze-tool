"""
experiment_utils 通用可复用工具
- Result 泛型结果类型
- ExecutionConfig 执行配置
- 简单彩色日志函数（基于 Rich）
- Rich 进度条封装 ProgressReporter
- 容器命名与生成辅助
- anyio 子进程执行帮助 run_shell
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Optional, TypeVar, Tuple, Iterator, List

import anyio
from anyio import fail_after
import subprocess
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

console = Console()

T = TypeVar("T")
E = TypeVar("E")


class Result(Generic[T, E]):
    __slots__ = ("_ok", "_value", "_error")

    def __init__(self, ok: bool, value: Optional[T] = None, error: Optional[E] = None):
        self._ok = ok
        self._value = value
        self._error = error

    @staticmethod
    def ok(value: T) -> "Result[T, E]":
        return Result(True, value=value)

    @staticmethod
    def error(error: E) -> "Result[T, E]":
        return Result(False, error=error)

    def is_ok(self) -> bool:
        return self._ok

    def is_error(self) -> bool:
        return not self._ok

    def unwrap(self) -> T:
        if not self._ok:
            raise RuntimeError(f"Tried to unwrap error result: {self._error}")
        return self._value  # type: ignore

    def unwrap_error(self) -> E:
        if self._ok:
            raise RuntimeError("Tried to unwrap_error on ok result")
        return self._error  # type: ignore

    # 兼容函数式用法
    def map(self, func):
        if self.is_error():
            return self
        try:
            return Result.ok(func(self._value))
        except Exception as e:
            return Result.error(str(e))  # type: ignore

    def and_then(self, func):
        if self.is_error():
            return self
        try:
            return func(self._value)
        except Exception as e:
            return Result.error(str(e))  # type: ignore


@dataclass(frozen=True)
class ExecutionConfig:
    max_workers: int = 4
    timeout: int = 30
    verbose: bool = False
    runtime: str = "docker"  # 容器运行时: docker 或 podman


# 简单彩色日志

def log_info(msg: str):
    console.print(f"[cyan]{msg}[/cyan]")


def log_success(msg: str):
    console.print(f"[green]{msg}[/green]")


def log_warning(msg: str):
    console.print(f"[yellow]{msg}[/yellow]")


def log_error(msg: str):
    console.print(f"[red]{msg}[/red]")


# 进度条封装（Rich 可选）
class ProgressReporter:
    def __init__(self):
        self.progress: Optional[Progress] = None
        self.use_rich = True

    def __enter__(self):
        try:
            self.progress = Progress(
                SpinnerColumn(),
                TextColumn("{task.description}"),
                BarColumn(),
                TextColumn("{task.percentage:>3.0f}%"),
                TimeElapsedColumn(),
                transient=True,
                console=console,
            )
            self.progress.start()
        except Exception:
            self.use_rich = False
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.progress:
            self.progress.stop()

    def create_task(self, description: str, total: int):
        if self.progress:
            return self.progress.add_task(description, total=total)
        return 0

    def update_task(self, task_id: int, advance: int = 1):
        if self.progress:
            self.progress.update(task_id, advance=advance)

# 带重试的 shell 执行
class TransientShellError(Exception):
    pass

@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.3, max=3.0),
    retry=retry_if_exception_type(TransientShellError),
)
async def run_shell_with_retry(cmd: str, timeout: int) -> Tuple[int, str, str]:
    """运行 shell 命令，短暂性错误自动重试。
    重试策略：3 次指数退避，仅在返回码非 0 且 stderr 存在时重试。
    """
    rc, out, err = await run_shell(cmd, timeout)
    # 将“明显的短暂性失败”视为可重试（可按需要扩展匹配条件）
    if rc != 0 and err:
        raise TransientShellError(err)
    return rc, out, err


# 容器命名与生成辅助

def create_container_name(prefix: str, row: int, col: int) -> str:
    return f"{prefix}-router_{row:02d}_{col:02d}"


def generate_container_names(prefix: str, size: int) -> Iterator[str]:
    for row in range(size):
        for col in range(size):
            yield create_container_name(prefix, row, col)


# 容器运行时命令构建

def build_container_exec_command(
    container_name: str,
    command: str,
    runtime: str = "docker",
    detach: bool = False
) -> str:
    """构建容器执行命令

    Args:
        container_name: 容器名称
        command: 要执行的命令
        runtime: 容器运行时 (docker 或 podman)
        detach: 是否后台执行

    Returns:
        完整的容器执行命令字符串

    Raises:
        ValueError: 当运行时不支持时
    """
    if runtime not in ("docker", "podman"):
        raise ValueError(f"不支持的容器运行时: {runtime}. 支持的运行时: docker, podman")

    detach_flag = "-d " if detach else ""
    return f"{runtime} exec {detach_flag}{container_name} {command}"


def validate_runtime(runtime: str) -> bool:
    """验证容器运行时是否支持

    Args:
        runtime: 容器运行时名称

    Returns:
        True 如果支持，False 如果不支持
    """
    return runtime in ("docker", "podman")


# anyio 子进程执行帮助
async def run_shell(cmd: str, timeout: int) -> Tuple[int, str, str]:
    """运行 shell 命令，返回 (returncode, stdout_text, stderr_text)
    超时将抛出 TimeoutError
    """
    with fail_after(timeout):
        result = await anyio.run_process(
            ["sh", "-c", cmd],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    rc = result.returncode
    out = (result.stdout or b"").decode("utf-8", errors="replace").strip()
    err = (result.stderr or b"").decode("utf-8", errors="replace").strip()
    return rc, out, err


# 延迟配置相关工具

@dataclass
class DelayConfig:
    """延迟配置数据类"""
    prefix: str
    size: int
    vertical_delay: int = 10
    horizontal_delay: int = 20
    runtime: Optional[str] = None
    
    def __post_init__(self):
        if self.size <= 0:
            raise ValueError("网格大小必须 > 0")
        if self.runtime and not validate_runtime(self.runtime):
            raise ValueError(f"不支持的容器运行时: {self.runtime}")


def build_containerlab_command(base_cmd: str, runtime: Optional[str] = None) -> str:
    """构建 containerlab 命令，按需注入 --runtime 以兼容 podman/docker。

    规则: 当 runtime 提供时，将其紧随 `containerlab` 之后插入。
    """
    if not runtime:
        return base_cmd
    parts = base_cmd.split(' ', 1)
    if len(parts) == 2 and parts[0] == 'containerlab':
        return f"containerlab --runtime {runtime} {parts[1]}"
    return f"{base_cmd} --runtime {runtime}"


def generate_delay_commands(delay_config: DelayConfig) -> List[str]:
    """生成所有延迟配置命令"""
    commands: List[str] = []
    
    # 遍历所有节点
    for row in range(delay_config.size):
        for col in range(delay_config.size):
            node_name = create_container_name(delay_config.prefix, row, col)
            
            # 竖直接口 - eth1 (north), eth2 (south)
            for eth in ['eth1', 'eth2']:
                base_cmd = f"containerlab tools netem set -n {node_name} -i {eth} --delay {delay_config.vertical_delay}ms"
                cmd = build_containerlab_command(base_cmd, delay_config.runtime)
                commands.append(cmd)
            
            # 水平接口 - eth3 (west), eth4 (east)  
            for eth in ['eth3', 'eth4']:
                base_cmd = f"containerlab tools netem set -n {node_name} -i {eth} --delay {delay_config.horizontal_delay}ms"
                cmd = build_containerlab_command(base_cmd, delay_config.runtime)
                commands.append(cmd)
    
    return commands


async def execute_delay_command(cmd: str, config: ExecutionConfig) -> Result[str, str]:
    """执行延迟配置命令，带重试机制"""
    try:
        rc, out, err = await run_shell_with_retry(cmd, config.timeout)
        if rc == 0:
            return Result.ok(out)
        else:
            return Result.error(f"命令执行失败 (rc={rc}): {err}")
    except Exception as e:
        return Result.error(f"执行异常: {str(e)}")


async def execute_commands_with_progress(
    commands: List[str], 
    exec_config: ExecutionConfig
) -> List[Result[str, str]]:
    """并发执行命令，带进度显示"""
    results: List[Result[str, str]] = [Result.error("未执行")] * len(commands)
    semaphore = anyio.Semaphore(exec_config.max_workers)

    async def worker(idx: int, cmd: str, reporter: ProgressReporter, task_id: int) -> None:
        """工作协程"""
        async with semaphore:
            if exec_config.verbose:
                log_info(f"执行: {cmd}")
            
            result = await execute_delay_command(cmd, exec_config)
            results[idx] = result
            
            if not result.is_ok():
                log_warning(f"命令失败: {cmd[:60]}...")
            
            reporter.update_task(task_id, 1)

    with ProgressReporter() as reporter:
        task_id = reporter.create_task("配置网络延迟", len(commands))
        
        async with anyio.create_task_group() as tg:
            for i, cmd in enumerate(commands):
                tg.start_soon(worker, i, cmd, reporter, task_id)

    return results


async def set_torus_delays_async(
    delay_config: DelayConfig,
    exec_config: ExecutionConfig,
    execute: bool = False
) -> Result[List[str], str]:
    """
    异步设置 Torus 拓扑延迟
    
    Args:
        delay_config: 延迟配置
        exec_config: 执行配置
        execute: 是否实际执行命令
        
    Returns:
        Result[命令列表, 错误信息]
    """
    try:
        commands = generate_delay_commands(delay_config)
        
        log_info(f"=== 生成 {delay_config.size}x{delay_config.size} 延迟配置 ===")
        log_info(f"竖直环: {delay_config.vertical_delay}ms网卡延迟 -> {delay_config.vertical_delay*2}ms链路延迟 (eth1/eth2)")
        log_info(f"水平环: {delay_config.horizontal_delay}ms网卡延迟 -> {delay_config.horizontal_delay*2}ms链路延迟 (eth3/eth4)")
        if delay_config.runtime:
            log_info(f"容器运行时: {delay_config.runtime}")
        log_info(f"总计 {len(commands)} 条命令")
        
        if not execute:
            log_warning("预览模式 - 不执行命令")
            for cmd in commands[:5]:  # 显示前5个作为示例
                print(f"  {cmd}")
            if len(commands) > 5:
                print(f"  ... 还有 {len(commands) - 5} 个命令")
            log_warning("使用 --execute 参数来实际执行命令")
            return Result.ok(commands)
        
        log_info(f"使用 {exec_config.max_workers} 个并发任务执行命令...")
        results = await execute_commands_with_progress(commands, exec_config)
        
        # 统计结果
        success_count = sum(1 for result in results if result.is_ok())
        failed_count = len(results) - success_count
        
        if failed_count == 0:
            log_success(f"全部成功! {success_count}/{len(commands)} 命令执行完成")
        else:
            log_warning(f"部分成功: {success_count}/{len(commands)} 成功, {failed_count} 失败")
            
            # 显示失败的命令（最多5个）
            failed_commands = [
                cmd for result, cmd in zip(results, commands) 
                if result.is_error()
            ]
            for i, cmd in enumerate(failed_commands[:5]):
                log_error(f"失败 {i+1}: {cmd}")
            
            if len(failed_commands) > 5:
                log_error(f"... 还有 {len(failed_commands) - 5} 个失败命令")
        
        return Result.ok(commands)
        
    except Exception as e:
        error_msg = f"配置延迟时发生错误: {str(e)}"
        log_error(error_msg)
        return Result.error(error_msg)

