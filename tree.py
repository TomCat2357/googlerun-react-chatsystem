import os
import sys
import argparse

def parse_args():
    parser = argparse.ArgumentParser(
        description="指定ディレクトリ以下の対象拡張子のファイル一覧をツリー状に出力します"
    )
    # 探索対象のディレクトリ（位置引数）
    parser.add_argument(
        "path",
        nargs=1,
        help="探索対象のディレクトリ"
    )
    # 対象拡張子（オプション）
    parser.add_argument(
        "-e", "--ext",
        nargs="*",
        default=None,
        help="対象ファイルの拡張子（例: .py, .js）。指定がある場合はその拡張子のファイルのみ対象とします。"
    )
    # 除外対象（オプション）
    parser.add_argument(
        "-o", "--omit",
        nargs="*",
        default=None,
        help="探索から除外するディレクトリまたはファイル名のリスト（例: *.py, folder/）"
    )
    # 再帰探索オプション（オプション）
    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        help="このオプションを指定すると、ディレクトリ内を再帰的に探索します（指定がない場合は直下のみ）。"
    )
    args = parser.parse_args()
    project_dir = args.path[0]
    # 拡張子指定がない場合は全てのファイルを対象とする
    exts = args.ext if args.ext is not None else []
    # 除外パターンから末尾の '/' を除去しておく
    omit = [pattern.rstrip('/') for pattern in (args.omit if args.omit is not None else [])]
    return project_dir, exts, omit, args.recursive

def has_matching_file(directory, exts, omit, match_all=False):
    if os.path.basename(directory) in omit:
        return False
    try:
        with os.scandir(directory) as it:
            for entry in it:
                full_path = os.path.join(directory, entry.name)
                if os.path.basename(entry.name) in omit:
                    continue
                if entry.is_file():
                    if match_all:
                        return True
                    for ext in exts:
                        if entry.name.endswith(ext):
                            return True
                elif entry.is_dir():
                    if has_matching_file(full_path, exts, omit, match_all):
                        return True
    except PermissionError:
        return False
    return False

def print_tree(root, exts, omit, prefix="", match_all=False, recursive=False):
    try:
        entries = sorted(os.listdir(root))
    except PermissionError:
        return

    matching_entries = []
    for entry in entries:
        full_path = os.path.join(root, entry)
        if os.path.basename(entry) in omit:
            continue
        if os.path.isdir(full_path):
            if has_matching_file(full_path, exts, omit, match_all):
                matching_entries.append(entry)
        elif os.path.isfile(full_path):
            if match_all or any(entry.endswith(ext) for ext in exts):
                matching_entries.append(entry)

    for i, entry in enumerate(matching_entries):
        full_path = os.path.join(root, entry)
        connector = "└── " if i == len(matching_entries) - 1 else "├── "
        print(prefix + connector + entry)
        if os.path.isdir(full_path) and recursive:
            new_prefix = prefix + ("    " if i == len(matching_entries) - 1 else "│   ")
            print_tree(full_path, exts, omit, new_prefix, match_all, recursive)

if __name__ == '__main__':
    project_dir, target_exts, omit, recursive = parse_args()

    # 拡張子に'.'が含まれている場合、または指定がない場合は全ファイル対象とする
    match_all = (target_exts and '.' in target_exts) or (not target_exts)
    if match_all:
        target_exts = []

    print(project_dir)
    print_tree(project_dir, target_exts, omit, prefix="", match_all=match_all, recursive=recursive)
