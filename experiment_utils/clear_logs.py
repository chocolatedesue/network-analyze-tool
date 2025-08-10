#!/usr/bin/env python3
"""
递归清空指定目录下所有 .log 文件、route.json 文件和 .pcap 文件内容的脚本
支持同步和异步两种模式，异步模式可显著提高大量文件的处理速度
"""

import os
import sys
import argparse
from pathlib import Path
from typing import List, Tuple
import asyncio

# 简化的日志函数
def log_info(msg: str):
    print(f"ℹ️  {msg}")

def log_success(msg: str):
    print(f"✅ {msg}")

def log_warning(msg: str):
    print(f"⚠️  {msg}")

def log_error(msg: str):
    print(f"❌ {msg}")


def find_target_files(directory: Path) -> List[Path]:
    """查找目标文件（.log、route.json 和 .pcap）"""
    files = []
    
    # 查找 .log 文件
    files.extend(directory.rglob("*.log"))
    
    # 查找 route.json 文件
    files.extend(directory.rglob("route.json"))
    
    # 查找 .pcap 文件
    files.extend(directory.rglob("*.pcap"))
    
    return files


def clear_file_sync(file_path: Path) -> Tuple[bool, str]:
    """同步清空单个文件"""
    try:
        with open(file_path, 'w') as f:
            f.truncate(0)
        return True, ""
    except PermissionError:
        return False, "权限不足"
    except Exception as e:
        return False, str(e)


async def clear_file_async(file_path: Path) -> Tuple[bool, str]:
    """异步清空单个文件"""
    try:
        # 使用异步文件操作
        async with asyncio.to_thread(open, file_path, 'w') as f:
            await asyncio.to_thread(f.truncate, 0)
        return True, ""
    except PermissionError:
        return False, "权限不足"
    except Exception as e:
        return False, str(e)


def process_files_sync(files: List[Path], base_path: Path) -> Tuple[int, int, List[str]]:
    """同步处理文件列表"""
    success_count = 0
    failed_count = 0
    failed_files = []

    for file_path in files:
        relative_path = file_path.relative_to(base_path)
        success, error_msg = clear_file_sync(file_path)
        
        if success:
            log_success(f"已清空: {relative_path}")
            success_count += 1
        else:
            error_desc = f"{error_msg}: {relative_path}"
            log_error(f"失败: {error_desc}")
            failed_files.append(error_desc)
            failed_count += 1

    return success_count, failed_count, failed_files


async def process_files_async(files: List[Path], base_path: Path, max_workers: int = 10) -> Tuple[int, int, List[str]]:
    """异步并发处理文件列表"""
    semaphore = asyncio.Semaphore(max_workers)
    
    async def worker(file_path: Path) -> Tuple[Path, bool, str]:
        """工作协程"""
        async with semaphore:
            success, error_msg = await clear_file_async(file_path)
            return file_path, success, error_msg
    
    # 创建所有任务并并发执行
    tasks = [worker(file_path) for file_path in files]
    results = await asyncio.gather(*tasks)
    
    # 统计结果
    success_count = 0
    failed_count = 0
    failed_files = []

    for file_path, success, error_msg in results:
        relative_path = file_path.relative_to(base_path)
        
        if success:
            log_success(f"已清空: {relative_path}")
            success_count += 1
        else:
            error_desc = f"{error_msg}: {relative_path}"
            log_error(f"失败: {error_desc}")
            failed_files.append(error_desc)
            failed_count += 1

    return success_count, failed_count, failed_files


def validate_directory(directory: str) -> Path:
    """验证目录是否存在且有效"""
    directory_path = Path(directory)

    if not directory_path.exists():
        log_error(f"目录 '{directory}' 不存在")
        sys.exit(1)

    if not directory_path.is_dir():
        log_error(f"'{directory}' 不是一个目录")
        sys.exit(1)

    return directory_path


def group_files_by_type(files: List[Path]) -> Tuple[List[Path], List[Path], List[Path]]:
    """按文件类型分组"""
    log_files = [f for f in files if f.suffix == '.log']
    route_files = [f for f in files if f.name == 'route.json']
    pcap_files = [f for f in files if f.suffix == '.pcap']
    return log_files, route_files, pcap_files


def display_file_preview(log_files: List[Path], route_files: List[Path], pcap_files: List[Path], base_path: Path) -> None:
    """显示将要处理的文件预览"""
    log_info(f"找到 {len(log_files)} 个 .log 文件:")
    for log_file in log_files[:5]:  # 只显示前5个
        print(f"  - {log_file.relative_to(base_path)}")
    if len(log_files) > 5:
        print(f"  ... 还有 {len(log_files) - 5} 个")

    log_info(f"找到 {len(route_files)} 个 route.json 文件:")
    for route_file in route_files[:5]:
        print(f"  - {route_file.relative_to(base_path)}")
    if len(route_files) > 5:
        print(f"  ... 还有 {len(route_files) - 5} 个")

    log_info(f"找到 {len(pcap_files)} 个 .pcap 文件:")
    for pcap_file in pcap_files[:5]:
        print(f"  - {pcap_file.relative_to(base_path)}")
    if len(pcap_files) > 5:
        print(f"  ... 还有 {len(pcap_files) - 5} 个")


def confirm_operation(total_files: int, skip_confirm: bool) -> bool:
    """确认操作"""
    if skip_confirm:
        return True

    log_warning(f"这将清空 {total_files} 个文件的内容!")
    confirm = input("确定要继续吗? (y/N): ").strip().lower()
    return confirm in ['y', 'yes']


def clear_files_sync(directory: str) -> Tuple[int, int, List[str]]:
    """同步清空文件"""
    directory_path = validate_directory(directory)
    log_info(f"开始处理目录: {directory_path.absolute()}")

    target_files = find_target_files(directory_path)
    return process_files_sync(target_files, directory_path)


async def clear_files_async(directory: str, max_workers: int = 10) -> Tuple[int, int, List[str]]:
    """异步清空文件"""
    directory_path = validate_directory(directory)
    log_info(f"开始异步处理目录: {directory_path.absolute()}")

    target_files = find_target_files(directory_path)
    return await process_files_async(target_files, directory_path, max_workers)


def create_argument_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description="递归清空指定目录下所有 .log 文件、route.json 文件和 .pcap 文件的内容",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python clear_logs.py /path/to/directory
  python clear_logs.py ./test_logs --async-mode --workers 20
  python clear_logs.py . -y --async-mode
        """
    )

    parser.add_argument('directory', help='要处理的目录路径')
    parser.add_argument('-y', '--yes', action='store_true', help='跳过确认提示，直接执行')
    parser.add_argument('--async-mode', action='store_true', help='使用异步模式加速处理')
    parser.add_argument('--workers', type=int, default=10, help='异步模式下的最大并发数 (默认: 10)')

    return parser


def display_results(success_count: int, failed_count: int, failed_files: List[str]) -> None:
    """显示处理结果"""
    total_count = success_count + failed_count
    
    log_success(f"操作完成!")
    log_info(f"成功清空: {success_count} 个文件")

    if failed_count > 0:
        log_warning(f"失败: {failed_count} 个文件")
        log_error("失败详情:")
        for failed_file in failed_files[:10]:  # 只显示前10个失败的文件
            print(f"  - {failed_file}")
        if len(failed_files) > 10:
            print(f"  ... 还有 {len(failed_files) - 10} 个失败文件")

    log_info(f"总计处理: {total_count} 个文件")


async def main_async(args) -> None:
    """异步主函数"""
    directory_path = validate_directory(args.directory)
    log_info(f"目标目录: {directory_path.resolve()}")

    # 查找目标文件
    all_files = find_target_files(directory_path)
    if not all_files:
        log_warning("未找到任何 .log 文件、route.json 文件或 .pcap 文件")
        return

    # 按类型分组并显示预览
    log_files, route_files, pcap_files = group_files_by_type(all_files)
    display_file_preview(log_files, route_files, pcap_files, directory_path)

    # 确认操作
    total_files = len(all_files)
    if not confirm_operation(total_files, args.yes):
        log_info("操作已取消")
        return

    # 执行清空操作
    log_info(f"开始异步清空文件 (并发数: {args.workers})...")
    success_count, failed_count, failed_files = await clear_files_async(args.directory, args.workers)

    # 显示结果
    display_results(success_count, failed_count, failed_files)


def main() -> None:
    """主函数"""
    parser = create_argument_parser()
    args = parser.parse_args()

    # 如果启用异步模式
    if getattr(args, 'async_mode', False):
        asyncio.run(main_async(args))
        return

    # 同步模式（默认）
    directory_path = validate_directory(args.directory)
    log_info(f"目标目录: {directory_path.resolve()}")

    # 查找目标文件
    all_files = find_target_files(directory_path)
    if not all_files:
        log_warning("未找到任何 .log 文件、route.json 文件或 .pcap 文件")
        return

    # 按类型分组并显示预览
    log_files, route_files, pcap_files = group_files_by_type(all_files)
    display_file_preview(log_files, route_files, pcap_files, directory_path)

    # 确认操作
    if not confirm_operation(len(all_files), args.yes):
        log_info("操作已取消")
        return

    # 执行清空操作
    log_info("开始清空文件...")
    success_count, failed_count, failed_files = clear_files_sync(args.directory)

    # 显示结果
    display_results(success_count, failed_count, failed_files)


if __name__ == "__main__":
    main()
