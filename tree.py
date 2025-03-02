import os
import sys
import argparse
import fnmatch

def should_omit(path, omit_patterns):
    """
    path: 対象のファイルまたはディレクトリのパス
    omit_patterns: gitignore風のパターンのリスト。例: ['*.py', 'folder/']
    
    Returns True if the path should be omitted.
    """
    if not omit_patterns:
        return False
        
    base_name = os.path.basename(path)
    for pattern in omit_patterns:
        # パターンが末尾に '/' を含む場合、ディレクトリ専用のルールとみなす
        if pattern.endswith('/'):
            if os.path.isdir(path) and fnmatch.fnmatch(base_name, pattern.rstrip('/')):
                return True
        else:
            if fnmatch.fnmatch(base_name, pattern):
                return True
    return False

def parse_args():
    parser = argparse.ArgumentParser(
        description="指定ディレクトリ以下の対象拡張子のファイル一覧をツリー状に出力します"
    )
    # 探索対象のディレクトリ（位置引数）
    parser.add_argument(
        "path", 
        nargs='+',
        help="探索対象のディレクトリ"
    )
    # 対象拡張子（オプション）
    parser.add_argument(
        "-e", "--ext",
        nargs="*",
        default=None,
        help="対象ファイルの拡張子（例: .py, .js）。指定がある場合はその拡張子のファイルのみ対象とします。"
    )
    # 対象ファイル名（完全一致）
    parser.add_argument(
        "-n", "--name",
        nargs="*", 
        default=None,
        help="対象とするファイル名（完全一致）。拡張子のないファイル（例: Dockerfile Makefile）を指定する場合に便利です。"
    )
    # 除外対象（オプション）
    parser.add_argument(
        "-o", "--omit",
        nargs="*",
        default=None,
        help="探索から除外するディレクトリまたはファイル名のリスト。gitignore風のパターン（例: *.py, folder/）で指定します。"
    )
    # 再帰探索オプション（オプション）
    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        help="このオプションを指定すると、ディレクトリ内を再帰的に探索します（指定がない場合は直下のみ）。"
    )
    
    args = parser.parse_args()
    
    # 拡張子フィルタ（小文字に統一）
    exts = [ext.lower() for ext in args.ext] if args.ext else None
    
    # 完全一致ファイル名リスト
    exact_names = args.name if args.name else None
    
    # フィルタが何も指定されていない場合は全ファイル対象
    if not exts and not exact_names:
        print("情報: フィルタが指定されていないため、全てのファイルを出力します。")
        
    return args.path, exts, exact_names, args.omit, args.recursive

def file_matches_filters(entry_name, exts, exact_names):
    """
    ファイル名がフィルタ条件（拡張子または完全一致名）に一致するかチェック
    """
    if not exts and not exact_names:
        return True  # フィルタ指定なしの場合は全ファイル対象
        
    # ファイル名完全一致チェック
    if exact_names and entry_name in exact_names:
        return True
        
    # 拡張子チェック
    if exts:
        for ext in exts:
            if entry_name.lower().endswith(ext):
                return True
                
    return False

def has_matching_file(directory, exts, exact_names, omit):
    """
    ディレクトリ内に条件に一致するファイルが存在するかチェック（再帰的）
    """
    if should_omit(directory, omit):
        return False
        
    try:
        with os.scandir(directory) as it:
            for entry in it:
                full_path = os.path.join(directory, entry.name)
                
                if should_omit(full_path, omit):
                    continue
                    
                if entry.is_file():
                    if file_matches_filters(entry.name, exts, exact_names):
                        return True
                elif entry.is_dir():
                    if has_matching_file(full_path, exts, exact_names, omit):
                        return True
    except PermissionError:
        return False
        
    return False

def print_tree(root, exts, exact_names, omit, prefix="", recursive=False):
    """
    ディレクトリ構造をツリー状に出力
    """
    try:
        entries = sorted(os.listdir(root))
    except PermissionError:
        print(f"{prefix}[アクセス権限エラー: {root}]")
        return

    matching_entries = []
    for entry in entries:
        full_path = os.path.join(root, entry)
        
        if should_omit(full_path, omit):
            continue
            
        if os.path.isdir(full_path):
            # ディレクトリの場合、再帰的にチェック
            if recursive and has_matching_file(full_path, exts, exact_names, omit):
                matching_entries.append(entry)
        elif os.path.isfile(full_path):
            # ファイルの場合、フィルタ条件に一致するかチェック
            if file_matches_filters(entry, exts, exact_names):
                matching_entries.append(entry)

    for i, entry in enumerate(matching_entries):
        full_path = os.path.join(root, entry)
        connector = "└── " if i == len(matching_entries) - 1 else "├── "
        print(prefix + connector + entry)
        
        if os.path.isdir(full_path) and recursive:
            new_prefix = prefix + ("    " if i == len(matching_entries) - 1 else "│   ")
            print_tree(full_path, exts, exact_names, omit, new_prefix, recursive)

if __name__ == '__main__':
    paths, exts, exact_names, omit, recursive = parse_args()

    for project_dir in paths:
        if not os.path.exists(project_dir):
            print(f"エラー: 指定されたパス '{project_dir}' は存在しません。")
            continue
            
        project_dir = os.path.abspath(project_dir)
        print(project_dir)
        print_tree(project_dir, exts, exact_names, omit, prefix="", recursive=recursive)
        
        # 複数のパスが指定された場合は、区切り線を入れる
        if len(paths) > 1 and project_dir != paths[-1]:
            print("\n" + "-" * 40 + "\n")