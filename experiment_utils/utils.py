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

