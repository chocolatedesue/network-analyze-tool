#!/usr/bin/env python3
"""
按批次在匹配 prefix 的容器上执行相同命令，直到全部容器执行过一次。
- 默认运行时：docker（可切换 podman）
- 每批按百分比选择（默认 20%），批次间隔（默认 10s）
- 支持并发、detach、dry-run
- 容器集合解析：优先从 prefix 末尾解析 WxH（如 *-grid5x5/*-torus9x9）；也可显式传 --size 或 --dims

用法示例：
  uv run experiment_utils/execute_in_batches.py clab-ospfv3-torus5x5 "echo hello" --percent 25 --interval 10
  uv run experiment_utils/execute_in_batches.py clab-ospfv3-grid5x5 "sleep 600" --percent 10 --interval 5 --runtime podman --detach
"""
from __future__ import annotations

import math
import re
import shlex
import random
from dataclasses import dataclass
from typing import List, Optional, Tuple

import anyio
import typer

try:
    from experiment_utils.utils import (
        log_info,
        log_warning,
        log_error,
        log_success,
        ProgressReporter,
        Result,
        run_shell_with_retry,
    )
except ModuleNotFoundError:
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
    from experiment_utils.utils import (
        log_info,
        log_warning,
        log_error,
        log_success,
        ProgressReporter,
        Result,
        run_shell_with_retry,
    )

app = typer.Typer(name="execute_in_batches", help="按批次在容器上执行命令")


@dataclass(frozen=True)
class Dimensions:
    width: int
    height: int


def parse_dims_from_prefix(prefix: str) -> Optional[Dimensions]:
    m = re.search(r"(\d+)x(\d+)$", prefix)
    if not m:
        return None
    return Dimensions(int(m.group(1)), int(m.group(2)))


def build_container_names(prefix: str, dims: Dimensions) -> List[str]:
    names: List[str] = []
    for x in range(dims.width):
        for y in range(dims.height):
            names.append(f"{prefix}-router_{x:02d}_{y:02d}")
    return names


async def list_containers_by_runtime(prefix: str, runtime: str) -> List[str]:
    pattern = rf"^{re.escape(prefix)}-router_[0-9]{{2}}_[0-9]{{2}}$"
    fmt = "{{.Names}}"
    base_cmd = f"{shlex.quote(runtime)} ps --format {shlex.quote(fmt)}"
    rc, out, err = await run_shell_with_retry(base_cmd, 20)
    if rc != 0:
        log_warning(f"无法列出容器: {err}")
        return []
    candidates = [line.strip() for line in out.splitlines() if line.strip()]
    return [c for c in candidates if re.match(pattern, c)]


async def resolve_target_containers(prefix: str, runtime: str, dims: Optional[Dimensions]) -> Result[List[str], str]:
    if dims:
        return Result.ok(build_container_names(prefix, dims))
    parsed = parse_dims_from_prefix(prefix)
    if parsed:
        return Result.ok(build_container_names(prefix, parsed))
    # fallback list from runtime
    names = await list_containers_by_runtime(prefix, runtime)
    if not names:
        return Result.error(f"未能解析容器集合，prefix: {prefix}")
    return Result.ok(names)


def ceil_div(a: int, b: int) -> int:
    return (a + b - 1) // b


async def exec_in_container(runtime: str, name: str, cmd: str, detach: bool) -> Result[None, str]:
    exec_flag = "-d " if detach else ""
    quoted_cmd = shlex.quote(cmd)
    shell_cmd = f"{runtime} exec {exec_flag}{shlex.quote(name)} sh -lc {quoted_cmd}"
    rc, _out, err = await run_shell_with_retry(shell_cmd, 120)
    if rc == 0:
        return Result.ok(None)
    return Result.error(err or f"exec failed rc={rc}")


async def run_batches(
    names: List[str],
    runtime: str,
    cmd: str,
    percent: int,
    interval: int,
    parallel: int,
    detach: bool,
    dry_run: bool,
    shuffle: bool,
) -> Result[None, str]:
    """Run command in batches across containers.

    - Stable batching: keep deterministic order unless shuffle=True
    - Backpressure with semaphore controls concurrency
    - Logs concise per batch; errors summarized inline per container
    """
    total = len(names)
    if shuffle:
        random.Random(0).shuffle(names)  # deterministic shuffle for reproducibility
    batch_size = max(1, (total * percent + 99) // 100)

    index = 0
    batch_no = 1

    while index < total:
        end = min(index + batch_size, total)
        batch = names[index:end]
        preview = ", ".join(batch[:min(3, len(batch))]) + (" ..." if len(batch) > 3 else "")
        log_info(
            f"[Batch {batch_no}] {index+1}..{end}/{total} size={len(batch)} interval={interval}s | {preview}"
        )

        if dry_run:
            example = batch[0] if batch else ""
            log_info(f"  would exec on {example}: {cmd}")
        else:
            results: List[Tuple[str, Result[None, str]]] = []
            semaphore = anyio.Semaphore(max(1, parallel))
            async with anyio.create_task_group() as tg:
                async def worker(container_name: str):
                    async with semaphore:
                        res = await exec_in_container(runtime, container_name, cmd, detach)
                        results.append((container_name, res))
                for n in batch:
                    tg.start_soon(worker, n)

            # 检查结果，在非detach模式下遇到错误立即退出
            failures = 0
            for container_name, res in results:
                if res.is_error():
                    failures += 1
                    log_error(f"容器 {container_name} 执行失败: {res._error}")
                    if not detach:
                        return Result.error(f"容器 {container_name} 执行失败，非detach模式下退出: {res._error}")

            log_info(f"[Batch {batch_no}] executed={len(batch)} failures={failures}")

        index = end
        batch_no += 1
        if index < total:
            await anyio.sleep(interval)

    return Result.ok(None)


@app.command()
def main(
    prefix: str = typer.Argument(..., help="容器名前缀 (如: clab-ospfv3-torus5x5)"),
    command: str = typer.Argument(..., help="要在容器里执行的命令"),
    percent: int = typer.Option(20, "--percent", "-p", min=1, max=100, help="每批百分比"),
    interval: int = typer.Option(10, "--interval", "-i", min=0, help="批次间隔(秒)"),
    runtime: str = typer.Option("docker", "--runtime", "-r", help="容器运行时 (docker/podman)"),
    parallel: int = typer.Option(1, "--parallel", help="批内并发数，默认 1 顺序执行"),
    detach: bool = typer.Option(False, "--detach", "-d", help="在容器内后台执行"),
    dry_run: bool = typer.Option(False, "--dry-run", help="仅打印不执行"),
    size: Optional[int] = typer.Option(None, "--size", help="方阵尺寸 N (N x N)"),
    dims: Optional[str] = typer.Option(None, "--dims", help="矩阵尺寸 WxH，如 5x5"),
    shuffle: bool = typer.Option(False, "--shuffle", help="是否对容器顺序随机化 (可复现)"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过执行前确认"),
):
    try:
        dim_obj: Optional[Dimensions] = None
        if dims:
            m = re.match(r"^(\d+)x(\d+)$", dims)
            if not m:
                log_error("--dims 需为 WxH 格式，例如 5x5")
                raise typer.Exit(1)
            dim_obj = Dimensions(int(m.group(1)), int(m.group(2)))
        elif size is not None:
            dim_obj = Dimensions(size, size)

        # 解析容器集合
        names_res = anyio.run(resolve_target_containers, prefix, runtime, dim_obj)
        if names_res.is_error():
            log_error(names_res._error)
            raise typer.Exit(1)
        names = names_res.unwrap()
        if not names:
            log_error("未找到任何容器")
            raise typer.Exit(1)

        log_info(f"解析到 {len(names)} 个容器；runtime={runtime}; percent={percent}%; interval={interval}s; parallel={parallel}; detach={detach}; shuffle={shuffle}")
        log_info(f"示例容器: {', '.join(names[:min(5, len(names))])}{' ...' if len(names) > 5 else ''}")

        # 执行前确认
        if not dry_run:
            example = names[0]
            log_info(f"命令预览: 将在 {len(names)} 个容器上执行: {command}")
            log_info(f"示例容器: {example} （runtime={runtime}, detach={detach}）")
            if not yes:
                if not typer.confirm("确认上述命令是否正确并继续执行？", default=False):
                    log_warning("已取消执行")
                    raise typer.Exit(0)

        # 执行批次
        res = anyio.run(
            run_batches,
            names,
            runtime,
            command,
            percent,
            interval,
            parallel,
            detach,
            dry_run,
            shuffle,
        )
        if res.is_error():
            log_error(res._error)
            raise typer.Exit(1)

        log_success("全部容器已完成该命令的执行")
    except KeyboardInterrupt:
        log_warning("用户中断")
        raise typer.Exit(130)
    except Exception as e:
        log_error(f"未知错误: {e}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()

