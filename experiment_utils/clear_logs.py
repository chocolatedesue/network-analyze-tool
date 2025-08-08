#!/usr/bin/env python3
"""
递归清空指定目录下所有 .log 文件和 route.json 文件内容的脚本
使用函数式编程风格，提高代码可读性和可维护性
"""

import os
import sys
import argparse
from pathlib import Path
from typing import List, Tuple, Iterator, NamedTuple
from functools import partial
from itertools import chain


class FileResult(NamedTuple):
    """文件处理结果"""
    file_path: Path
    success: bool
    error_message: str = ""


class ProcessingStats(NamedTuple):
    """处理统计信息"""
    success_count: int
    failed_count: int
    failed_files: List[str]


def find_target_files(directory: Path) -> Iterator[Path]:
    """
    查找目标文件（.log 和 route.json）

    Args:
        directory: 目录路径

    Yields:
        Path: 目标文件路径
    """
    log_files = directory.rglob("*.log")
    route_files = directory.rglob("route.json")
    return chain(log_files, route_files)


def clear_file_content(file_path: Path) -> FileResult:
    """
    清空单个文件内容

    Args:
        file_path: 文件路径

    Returns:
        FileResult: 处理结果
    """
    try:
        with open(file_path, 'w') as f:
            f.truncate(0)
        return FileResult(file_path, True)
    except PermissionError:
        return FileResult(file_path, False, "权限不足")
    except Exception as e:
        return FileResult(file_path, False, str(e))


def process_files(files: Iterator[Path], base_path: Path) -> ProcessingStats:
    """
    处理文件列表

    Args:
        files: 文件路径迭代器
        base_path: 基础路径（用于显示相对路径）

    Returns:
        ProcessingStats: 处理统计信息
    """
    results = map(clear_file_content, files)

    success_count = 0
    failed_count = 0
    failed_files = []

    for result in results:
        relative_path = result.file_path.relative_to(base_path)

        if result.success:
            print(f"✓ 已清空: {relative_path}")
            success_count += 1
        else:
            error_msg = f"{result.error_message}: {relative_path}"
            print(f"✗ {error_msg}")
            failed_files.append(error_msg)
            failed_count += 1

    return ProcessingStats(success_count, failed_count, failed_files)


def validate_directory(directory: str) -> Path:
    """
    验证目录是否存在且有效

    Args:
        directory: 目录路径字符串

    Returns:
        Path: 验证后的目录路径对象

    Raises:
        SystemExit: 目录不存在或无效时退出程序
    """
    directory_path = Path(directory)

    if not directory_path.exists():
        print(f"错误: 目录 '{directory}' 不存在")
        sys.exit(1)

    if not directory_path.is_dir():
        print(f"错误: '{directory}' 不是一个目录")
        sys.exit(1)

    return directory_path


def group_files_by_type(files: List[Path]) -> Tuple[List[Path], List[Path]]:
    """
    按文件类型分组

    Args:
        files: 文件路径列表

    Returns:
        Tuple[List[Path], List[Path]]: (log文件列表, route.json文件列表)
    """
    log_files = [f for f in files if f.suffix == '.log']
    route_files = [f for f in files if f.name == 'route.json']
    return log_files, route_files


def display_file_preview(log_files: List[Path], route_files: List[Path], base_path: Path) -> None:
    """
    显示将要处理的文件预览

    Args:
        log_files: log文件列表
        route_files: route.json文件列表
        base_path: 基础路径
    """
    print(f"\n找到 {len(log_files)} 个 .log 文件:")
    for log_file in log_files:
        print(f"  - {log_file.relative_to(base_path)}")

    print(f"\n找到 {len(route_files)} 个 route.json 文件:")
    for route_file in route_files:
        print(f"  - {route_file.relative_to(base_path)}")


def confirm_operation(total_files: int, skip_confirm: bool) -> bool:
    """
    确认操作

    Args:
        total_files: 总文件数
        skip_confirm: 是否跳过确认

    Returns:
        bool: 是否继续操作
    """
    if skip_confirm:
        return True

    print(f"\n警告: 这将清空上述 {total_files} 个文件的内容!")
    confirm = input("确定要继续吗? (y/N): ").strip().lower()
    return confirm in ['y', 'yes']


def clear_log_files(directory: str) -> ProcessingStats:
    """
    主要的文件清空逻辑

    Args:
        directory: 目录路径

    Returns:
        ProcessingStats: 处理统计信息
    """
    directory_path = validate_directory(directory)
    print(f"开始处理目录: {directory_path.absolute()}")

    target_files = find_target_files(directory_path)
    return process_files(target_files, directory_path)


def create_argument_parser() -> argparse.ArgumentParser:
    """
    创建命令行参数解析器

    Returns:
        argparse.ArgumentParser: 配置好的参数解析器
    """
    parser = argparse.ArgumentParser(
        description="递归清空指定目录下所有 .log 文件和 route.json 文件的内容",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python clear_logs.py /path/to/directory
  python clear_logs.py ./test_logs
  python clear_logs.py .
        """
    )

    parser.add_argument(
        'directory',
        help='要处理的目录路径'
    )

    parser.add_argument(
        '-y', '--yes',
        action='store_true',
        help='跳过确认提示，直接执行'
    )

    return parser


def display_results(stats: ProcessingStats) -> None:
    """
    显示处理结果

    Args:
        stats: 处理统计信息
    """
    print(f"\n操作完成!")
    print(f"成功清空: {stats.success_count} 个文件")

    if stats.failed_count > 0:
        print(f"失败: {stats.failed_count} 个文件")
        print("\n失败详情:")
        for failed_file in stats.failed_files:
            print(f"  - {failed_file}")

    print(f"总计处理: {stats.success_count + stats.failed_count} 个文件")


def main() -> None:
    """主函数"""
    parser = create_argument_parser()
    args = parser.parse_args()

    # 验证并获取目录路径
    directory_path = validate_directory(args.directory)
    print(f"目标目录: {directory_path.resolve()}")

    # 查找目标文件
    all_files = list(find_target_files(directory_path))

    if not all_files:
        print("未找到任何 .log 文件或 route.json 文件")
        return

    # 按类型分组并显示预览
    log_files, route_files = group_files_by_type(all_files)
    display_file_preview(log_files, route_files, directory_path)

    # 确认操作
    if not confirm_operation(len(all_files), args.yes):
        print("操作已取消")
        return

    # 执行清空操作
    print("\n开始清空文件...")
    stats = clear_log_files(args.directory)

    # 显示结果
    display_results(stats)


if __name__ == "__main__":
    main()
