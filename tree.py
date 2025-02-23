import os
import sys
import argparse

try:
    import pathspec
except ImportError:
    pathspec = None

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
        help="対象ファイルの拡張子（例: .py, .js など）。'.'を指定すると全てのファイルを対象とします。",
        nargs='+'
    )
    # 除外ディレクトリ・ファイル（オプション、短縮形 -e, --exclude で指定可能）
    parser.add_argument(
        "-o", "--omit", 
        help="探索から除外するディレクトリまたはファイル名のリスト", 
        nargs='+', 
        default=[]
    )
    # .gitignore を利用した除外ルール（オプション、短縮形 -i, --ignore で指定可能）
    parser.add_argument(
        "-i", "--ignore", 
        help=".gitignore ファイルのパス。指定された場合、そのルールで除外します。",
        default=None
    )
    args = parser.parse_args()
    return args.project_dir, args.exts, args.omit, args.ignore

def load_ignore_spec(ignore_file):
    if not pathspec:
        print("pathspecライブラリがインストールされていません。'.gitignore'による除外は無視されます。", file=sys.stderr)
        return None
    try:
        with open(ignore_file, 'r', encoding='utf-8') as f:
            lines = [line.rstrip() for line in f if line.strip() and not line.lstrip().startswith('#')]
        return pathspec.PathSpec.from_lines('gitwildmatch', lines)
    except Exception as e:
        print(f".gitignoreファイルの読み込みに失敗しました: {e}", file=sys.stderr)
        return None

def is_ignored(path, ignore_spec, base_dir):
    if ignore_spec is None:
        return False
    try:
        rel_path = os.path.relpath(path, base_dir)
    except ValueError:
        # base_dir と path の関係でエラーが出た場合は無視しない
        return False
    # Windows環境などで区切り文字を統一
    rel_path = rel_path.replace(os.sep, '/')
    return ignore_spec.match_file(rel_path)

def has_matching_file(directory, exts, exclude_list, ignore_spec, base_dir, match_all=False):
    # 除外対象のディレクトリならスキップ
    if os.path.basename(directory) in exclude_list:
        return False
    if is_ignored(directory, ignore_spec, base_dir):
        return False
    try:
        with os.scandir(directory) as it:
            for entry in it:
                full_path = os.path.join(directory, entry.name)
                if is_ignored(full_path, ignore_spec, base_dir):
                    continue
                if entry.is_file():
                    if os.path.basename(entry.name) in exclude_list:
                        continue
                    if match_all:
                        return True
                    for ext in exts:
                        if entry.name.endswith(ext):
                            return True
                elif entry.is_dir():
                    if os.path.basename(entry.name) in exclude_list:
                        continue
                    if has_matching_file(full_path, exts, exclude_list, ignore_spec, base_dir, match_all):
                        return True
    except PermissionError:
        return False
    return False

def print_tree(root, exts, exclude_list, ignore_spec, base_dir, prefix="", match_all=False):
    if is_ignored(root, ignore_spec, base_dir):
        return
    try:
        entries = sorted(os.listdir(root))
    except PermissionError:
        return

    matching_entries = []
    for entry in entries:
        full_path = os.path.join(root, entry)
        if os.path.basename(entry) in exclude_list:
            continue
        if is_ignored(full_path, ignore_spec, base_dir):
            continue
        if os.path.isdir(full_path):
            if has_matching_file(full_path, exts, exclude_list, ignore_spec, base_dir, match_all):
                matching_entries.append(entry)
        elif os.path.isfile(full_path):
            if os.path.basename(entry) in exclude_list:
                continue
            if match_all or any(entry.endswith(ext) for ext in exts):
                matching_entries.append(entry)

    for i, entry in enumerate(matching_entries):
        full_path = os.path.join(root, entry)
        connector = "└── " if i == len(matching_entries) - 1 else "├── "
        print(prefix + connector + entry)
        if os.path.isdir(full_path):
            new_prefix = prefix + ("    " if i == len(matching_entries) - 1 else "│   ")
            print_tree(full_path, exts, exclude_list, ignore_spec, base_dir, new_prefix, match_all)

if __name__ == '__main__':
    project_dir, target_exts, exclude_list, ignore_file = parse_args()
    
    # '.' が指定されている場合、全てのファイルを対象とする
    match_all = '.' in target_exts
    if match_all:
        # 他の拡張子指定は無視
        target_exts = []
    
    # .gitignore の読み込み
    ignore_spec = None
    if ignore_file is not None:
        ignore_spec = load_ignore_spec(ignore_file)
    
    # ルートディレクトリ名を表示
    print(project_dir)
    print_tree(project_dir, target_exts, exclude_list, ignore_spec, project_dir, prefix="", match_all=match_all)
