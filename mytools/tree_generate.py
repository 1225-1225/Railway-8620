import os

# ==================== 在这里设置你要扫描的文件夹路径 ====================
folder_path = "C:\PCL2\.minecraft\\versions\\1.20.1-Forge_47.4.21\mods"  # 请修改为实际路径
# ====================================================================

# 树状图绘制字符
CONNECTOR_LAST = "└── "
CONNECTOR_MID  = "├── "
INDENT_LAST    = "    "
INDENT_MID     = "│   "

def generate_tree(root_path, prefix="", depth=None, current_depth=0, output_lines=None):
    """递归生成目录树，结果存入 output_lines 列表"""
    if output_lines is None:
        output_lines = []

    if depth is not None and current_depth > depth:
        return output_lines

    try:
        entries = list(os.scandir(root_path))
    except PermissionError:
        output_lines.append(f"{prefix}[权限不足，无法读取]")
        return output_lines
    except OSError as e:
        output_lines.append(f"{prefix}[错误: {e}]")
        return output_lines

    # 排序：目录在前，文件在后，各自按名称排序
    def sort_key(entry):
        is_dir = entry.is_dir(follow_symlinks=True)
        return (not is_dir, entry.name.lower())

    entries.sort(key=sort_key)

    for idx, entry in enumerate(entries):
        is_last = (idx == len(entries) - 1)
        connector = CONNECTOR_LAST if is_last else CONNECTOR_MID
        line = prefix + connector + entry.name

        # 处理符号链接（不进入，防止循环）
        if entry.is_symlink():
            try:
                target = os.readlink(entry.path)
                line += f" -> {target} (symlink)"
            except OSError:
                line += " (broken symlink)"
            output_lines.append(line)
            continue

        if entry.is_dir():
            line += "/"
            output_lines.append(line)
            extension = INDENT_LAST if is_last else INDENT_MID
            generate_tree(entry.path, prefix + extension, depth, current_depth + 1, output_lines)
        else:
            output_lines.append(line)

    return output_lines

# 主程序
if __name__ == "__main__":
    # 转换为绝对路径，便于显示
    abs_path = os.path.abspath(folder_path)

    if not os.path.exists(abs_path):
        print(f"错误：路径 '{abs_path}' 不存在")
    elif not os.path.isdir(abs_path):
        print(f"错误：'{abs_path}' 不是一个文件夹")
    else:
        lines = [abs_path + "/"]
        generate_tree(abs_path, output_lines=lines)
        print("\n".join(lines))