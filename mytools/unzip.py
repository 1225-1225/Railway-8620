#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
批量解压脚本
功能：解压指定文件夹内的所有压缩包到各自独立的文件夹中
支持格式：.zip, .rar, .7z, .tar, .tar.gz, .tgz, .tar.bz2, .tar.xz
"""

import os
import sys
import zipfile
import tarfile
import subprocess
from pathlib import Path
import shutil

# ==================== 配置区域 ====================
# 在这里设置您的路径，修改后直接运行脚本即可

# 源文件夹路径（包含压缩包的文件夹）
# 如果留空或设为 None，则使用脚本所在目录
SOURCE_DIR = r"E:\Download\fromIDM\maps"

# 输出文件夹路径（解压目标文件夹）
# 如果留空或设为 None，则在源文件夹下创建 'extracted' 子目录
OUTPUT_DIR = r"E:\Download\fromIDM\unzipmaps"

# 是否覆盖已存在的文件夹（True=覆盖，False=跳过）
OVERWRITE = False

# 支持的压缩包扩展名
SUPPORTED_EXTENSIONS = [
    '.zip',
    '.rar',
    '.7z',
    '.tar',
    '.tar.gz', '.tgz',
    '.tar.bz2', '.tbz2',
    '.tar.xz', '.txz',
    '.gz', '.bz2', '.xz'
]

# 压缩类型映射
ARCHIVE_TYPES = {
    '.zip': 'zip',
    '.rar': 'rar',
    '.7z': '7z',
    '.tar': 'tar',
    '.tar.gz': 'tar', '.tgz': 'tar',
    '.tar.bz2': 'tar', '.tbz2': 'tar',
    '.tar.xz': 'tar', '.txz': 'tar',
    '.gz': 'gzip',
    '.bz2': 'bzip2',
    '.xz': 'xz'
}


class BatchExtractor:
    def __init__(self, source_dir=None, output_dir=None, overwrite=False):
        """
        初始化批量解压器

        Args:
            source_dir: 源文件夹路径（包含压缩包）
            output_dir: 输出文件夹路径（解压目标）
            overwrite: 是否覆盖已存在的文件夹
        """
        self.source_dir = Path(source_dir) if source_dir else Path.cwd()
        self.output_dir = Path(output_dir) if output_dir else self.source_dir / 'extracted'
        self.overwrite = overwrite
        self.extracted_count = 0
        self.failed_count = 0
        self.skipped_count = 0
        self.results = []

    def find_archives(self):
        """
        查找源文件夹中的所有压缩包

        Returns:
            list: 压缩包文件路径列表
        """
        archives = []
        for file_path in self.source_dir.iterdir():
            if file_path.is_file():
                file_ext = file_path.suffix.lower()
                file_name = file_path.name.lower()

                # 检查文件扩展名是否在支持列表中
                is_supported = (
                    file_ext in SUPPORTED_EXTENSIONS or
                    any(file_name.endswith(ext) for ext in SUPPORTED_EXTENSIONS)
                )

                if is_supported:
                    archives.append(file_path)
        return sorted(archives)

    def detect_archive_type(self, file_path):
        """
        检测压缩包类型

        Args:
            file_path: 压缩包文件路径

        Returns:
            str: 压缩类型（'zip', 'rar', '7z', 'tar', 'gzip', 'bzip2', 'xz'）
        """
        file_name = file_path.name.lower()

        # 检查复合扩展名（如 .tar.gz）
        for ext in ['.tar.gz', '.tgz', '.tar.bz2', '.tbz2', '.tar.xz', '.txz']:
            if file_name.endswith(ext):
                return ARCHIVE_TYPES[ext]

        # 检查单一扩展名
        suffix = file_path.suffix.lower()
        return ARCHIVE_TYPES.get(suffix, 'unknown')

    def get_extract_folder_name(self, archive_path):
        """
        获取解压目标文件夹名称

        Args:
            archive_path: 压缩包文件路径

        Returns:
            Path: 目标文件夹路径
        """
        # 去除压缩包扩展名
        archive_name = archive_path.name

        # 处理复合扩展名
        for ext in ['.tar.gz', '.tgz', '.tar.bz2', '.tbz2', '.tar.xz', '.txz']:
            if archive_name.lower().endswith(ext):
                archive_name = archive_name[:-len(ext)]
                break
        else:
            # 处理单一扩展名
            archive_name = os.path.splitext(archive_name)[0]

        return self.output_dir / archive_name

    def extract_zip(self, archive_path, extract_to):
        """解压 ZIP 文件"""
        try:
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                zip_ref.extractall(extract_to)
            return True, None
        except Exception as e:
            return False, str(e)

    def extract_tar(self, archive_path, extract_to):
        """解压 TAR 文件"""
        try:
            with tarfile.open(archive_path, 'r:*') as tar_ref:
                tar_ref.extractall(extract_to)
            return True, None
        except Exception as e:
            return False, str(e)

    def extract_rar(self, archive_path, extract_to):
        """解压 RAR 文件（需要 unrar 或 7z）"""
        # 优先使用 7z
        if self._check_command_available('7z'):
            return self._extract_with_7z(archive_path, extract_to)
        # 降级使用 unrar
        elif self._check_command_available('unrar'):
            return self._extract_with_unrar(archive_path, extract_to)
        else:
            return False, "需要安装 7z 或 unrar 命令行工具"

    def extract_7z(self, archive_path, extract_to):
        """解压 7Z 文件（需要 7z）"""
        if self._check_command_available('7z'):
            return self._extract_with_7z(archive_path, extract_to)
        else:
            return False, "需要安装 7z 命令行工具"

    def extract_gzip(self, archive_path, extract_to):
        """解压 GZIP 文件"""
        try:
            import gzip
            output_file = extract_to / archive_path.stem
            with gzip.open(archive_path, 'rb') as gz_file:
                with open(output_file, 'wb') as out_file:
                    shutil.copyfileobj(gz_file, out_file)
            return True, None
        except Exception as e:
            return False, str(e)

    def extract_bzip2(self, archive_path, extract_to):
        """解压 BZIP2 文件"""
        try:
            import bz2
            output_file = extract_to / archive_path.stem
            with bz2.open(archive_path, 'rb') as bz2_file:
                with open(output_file, 'wb') as out_file:
                    shutil.copyfileobj(bz2_file, out_file)
            return True, None
        except Exception as e:
            return False, str(e)

    def extract_xz(self, archive_path, extract_to):
        """解压 XZ 文件（需要 xz 命令）"""
        if self._check_command_available('xz'):
            return self._extract_with_xz(archive_path, extract_to)
        else:
            return False, "需要安装 xz 命令行工具"

    def _check_command_available(self, command):
        """检查命令是否可用"""
        try:
            subprocess.run([command, '--help'],
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE,
                         timeout=2)
            return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _extract_with_7z(self, archive_path, extract_to):
        """使用 7z 命令解压"""
        try:
            subprocess.run([
                '7z', 'x', str(archive_path),
                f'-o{extract_to}',
                '-y'  # 自动确认
            ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return True, None
        except subprocess.CalledProcessError as e:
            return False, f"7z 解压失败: {str(e)}"

    def _extract_with_unrar(self, archive_path, extract_to):
        """使用 unrar 命令解压"""
        try:
            subprocess.run([
                'unrar', 'x', str(archive_path),
                str(extract_to) + os.sep,
                '-y'  # 自动确认
            ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return True, None
        except subprocess.CalledProcessError as e:
            return False, f"unrar 解压失败: {str(e)}"

    def _extract_with_xz(self, archive_path, extract_to):
        """使用 xz 命令解压"""
        try:
            output_file = extract_to / archive_path.stem
            subprocess.run([
                'xz', '-d', '-k',  # 解压并保留原文件
                '-c', str(archive_path)
            ], check=True, stdout=open(output_file, 'wb'), stderr=subprocess.PIPE)
            return True, None
        except subprocess.CalledProcessError as e:
            return False, f"xz 解压失败: {str(e)}"

    def extract_archive(self, archive_path):
        """
        解压单个压缩包

        Args:
            archive_path: 压缩包文件路径

        Returns:
            tuple: (是否成功, 错误信息)
        """
        archive_type = self.detect_archive_type(archive_path)
        extract_to = self.get_extract_folder_name(archive_path)

        # 检查目标文件夹是否存在
        if extract_to.exists():
            if not self.overwrite:
                print(f"  ⏭️  跳过（文件夹已存在）: {extract_to.name}")
                self.skipped_count += 1
                return (False, "文件夹已存在")
            else:
                print(f"  🗑️  删除已存在的文件夹: {extract_to.name}")
                shutil.rmtree(extract_to)

        # 创建目标文件夹
        extract_to.mkdir(parents=True, exist_ok=True)

        print(f"  📦 解压中: {archive_path.name} -> {extract_to.name}")
        print(f"     类型: {archive_type}")

        # 根据类型调用相应的解压方法
        extract_methods = {
            'zip': self.extract_zip,
            'tar': self.extract_tar,
            'rar': self.extract_rar,
            '7z': self.extract_7z,
            'gzip': self.extract_gzip,
            'bzip2': self.extract_bzip2,
            'xz': self.extract_xz
        }

        extract_func = extract_methods.get(archive_type)
        if not extract_func:
            return (False, f"不支持的压缩类型: {archive_type}")

        success, error = extract_func(archive_path, extract_to)

        if success:
            print(f"  ✅ 解压成功: {extract_to.name}")
            self.extracted_count += 1
            self.results.append({
                'archive': archive_path.name,
                'folder': extract_to.name,
                'status': 'success',
                'error': None
            })
        else:
            print(f"  ❌ 解压失败: {archive_path.name}")
            print(f"     错误: {error}")
            self.failed_count += 1
            self.results.append({
                'archive': archive_path.name,
                'folder': extract_to.name,
                'status': 'failed',
                'error': error
            })

        return (success, error)

    def extract_all(self):
        """解压所有找到的压缩包"""
        print("=" * 60)
        print("批量解压工具")
        print("=" * 60)
        print(f"源目录: {self.source_dir}")
        print(f"输出目录: {self.output_dir}")
        print(f"覆盖模式: {'是' if self.overwrite else '否'}")
        print("=" * 60)

        # 查找压缩包
        archives = self.find_archives()

        if not archives:
            print("❌ 未找到任何压缩包")
            return

        print(f"📋 找到 {len(archives)} 个压缩包:")
        for idx, archive in enumerate(archives, 1):
            print(f"   {idx}. {archive.name} ({self.detect_archive_type(archive)})")

        print("\n" + "=" * 60)
        print("开始解压...")
        print("=" * 60 + "\n")

        # 逐个解压
        for idx, archive in enumerate(archives, 1):
            print(f"[{idx}/{len(archives)}] 处理: {archive.name}")
            self.extract_archive(archive)
            print()

        # 输出统计信息
        print("=" * 60)
        print("解压完成！")
        print("=" * 60)
        print(f"✅ 成功: {self.extracted_count}")
        print(f"❌ 失败: {self.failed_count}")
        print(f"⏭️  跳过: {self.skipped_count}")
        print(f"📊 总计: {len(archives)}")
        print(f"📁 输出目录: {self.output_dir}")
        print("=" * 60)

        # 如果有失败的，显示详细信息
        if self.failed_count > 0:
            print("\n❌ 失败详情:")
            for result in self.results:
                if result['status'] == 'failed':
                    print(f"  - {result['archive']}: {result['error']}")

        return self.extracted_count > 0


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(
        description='批量解压脚本 - 解压文件夹内的所有压缩包到各自独立的文件夹',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用说明:
  1. 直接运行: 使用脚本顶部配置区域的变量设置
     python batch_extract.py

  2. 命令行参数: 优先级高于配置区域变量
     python batch_extract.py -s /path/to/archives -o /path/to/output --overwrite

  3. 混合使用: 部分使用配置变量，部分使用命令行参数
     python batch_extract.py -s /path/to/archives  # 仅指定源目录，输出目录使用配置变量

配置优先级: 命令行参数 > 配置区域变量 > 默认值

支持格式:
  ZIP, RAR, 7Z, TAR, TAR.GZ, TAR.BZ2, TAR.XZ, GZIP, BZIP2, XZ
        """
    )

    parser.add_argument(
        '-s', '--source',
        type=str,
        default=None,
        help='源文件夹路径（包含压缩包的文件夹），如不指定则使用配置区域的 SOURCE_DIR'
    )

    parser.add_argument(
        '-o', '--output',
        type=str,
        default=None,
        help='输出文件夹路径（解压目标文件夹），如不指定则使用配置区域的 OUTPUT_DIR'
    )

    parser.add_argument(
        '--overwrite',
        action='store_true',
        help='覆盖已存在的文件夹，如不指定则使用配置区域的 OVERWRITE'
    )

    args = parser.parse_args()

    # 创建解压器实例，优先使用命令行参数，否则使用配置变量
    extractor = BatchExtractor(
        source_dir=args.source if args.source else (SOURCE_DIR if SOURCE_DIR else None),
        output_dir=args.output if args.output else (OUTPUT_DIR if OUTPUT_DIR else None),
        overwrite=args.overwrite if args.overwrite else OVERWRITE
    )

    # 执行解压
    extractor.extract_all()


if __name__ == "__main__":
    main()
