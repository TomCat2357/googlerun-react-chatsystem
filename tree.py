import os
import sys
import argparse

def parse_args():
    parser = argparse.ArgumentParser(
        description="指定ディレクトリ以下の対象拡張子のファイル一覧をツリー状に出力します"
    )
    # 対象ディレクトリ（必須）
    parser.add_argument(
        "project_dir", 
        help="探索対象のディレクトリ"
    )
    # 対象拡張子（必須、複数指定可能）
    parser.add_argument(
        "exts", 
        help="対象ファイルの拡張子（例: .py, .js など）", 
        nargs='+'
    )
    # 除外ディレクトリ（オプション、短縮形 -e, --exclude で指定可能）
    parser.add_argument(
        "-e", "--exclude", 
        help="探索から除外するディレクトリのリスト", 
        nargs='+', 
        default=[]
    )
    args = parser.parse_args()
    return args.project_dir, args.exts, args.exclude

def has_matching_file(directory, exts, exclude_dirs):
    # 除外対象のディレクトリならスキップ
    if os.path.basename(directory) in exclude_dirs:
        return False
    try:
        with os.scandir(directory) as it:
            for entry in it:
                if entry.is_file():
                    for ext in exts:
                        if entry.name.endswith(ext):
                            return True
                elif entry.is_dir():
                    # 除外対象ディレクトリは探索しない
                    if os.path.basename(entry.path) in exclude_dirs:
                        continue
                    if has_matching_file(entry.path, exts, exclude_dirs):
                        return True
    except PermissionError:
        return False
    return False

def print_tree(root, exts, exclude_dirs, prefix=""):
    try:
        entries = sorted(os.listdir(root))
    except PermissionError:
        return

    matching_entries = []
    for entry in entries:
        full_path = os.path.join(root, entry)
        # ディレクトリの場合は内部に対象ファイルがあるかチェック
        if os.path.isdir(full_path):
            if entry in exclude_dirs:
                continue
            if has_matching_file(full_path, exts, exclude_dirs):
                matching_entries.append(entry)
        # ファイルの場合は拡張子でチェック
        elif os.path.isfile(full_path):
            for ext in exts:
                if entry.endswith(ext):
                    matching_entries.append(entry)
                    break

    for i, entry in enumerate(matching_entries):
        full_path = os.path.join(root, entry)
        connector = "└── " if i == len(matching_entries) - 1 else "├── "
        print(prefix + connector + entry)
        if os.path.isdir(full_path):
            new_prefix = prefix + ("    " if i == len(matching_entries) - 1 else "│   ")
            print_tree(full_path, exts, exclude_dirs, new_prefix)

if __name__ == '__main__':
    project_dir, target_exts, exclude_dirs = parse_args()
    
    # ルートディレクトリ名を表示
    print(project_dir)
    print_tree(project_dir, target_exts, exclude_dirs)
