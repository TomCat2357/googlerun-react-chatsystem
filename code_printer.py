import os
import argparse
import fnmatch

def should_omit(path, omit_patterns):
    """
    path: 対象のファイルまたはディレクトリのパス
    omit_patterns: gitignore風のパターンのリスト。例: ['*.py', 'folder/']
    
    Returns True if the path should be omitted.
    """
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

def print_code(target_path, exts=None, exact_names=None, base_dir=None, recursive=False, omit=None):
    # Gitignoreルールに則った排除チェック
    if omit and should_omit(target_path, omit):
        return

    if base_dir is None:
        base_dir = os.path.dirname(target_path) if os.path.isfile(target_path) else target_path

    if os.path.isfile(target_path):
        file_name = os.path.basename(target_path)
        _, file_ext = os.path.splitext(target_path)
        
        # ファイル名と拡張子のフィルタチェック
        if exts or exact_names:
            # 拡張子がある場合のチェック
            if file_ext and exts and file_ext.lower() in exts:
                pass  # 拡張子一致
            # 拡張子がない、または完全一致のファイル名をチェック
            elif exact_names and file_name in exact_names:
                pass  # ファイル名完全一致
            else:
                return  # どのフィルタにも一致しない場合はスキップ
                
        # 基準ディレクトリからの相対パスを表示
        rel_path = os.path.relpath(target_path, base_dir)
        print()
        print(f"### {rel_path} ###")
        print()
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            content = "[テキストとして読み込めないファイル]"
        except Exception as e:
            content = f"[読み込みエラー: {e}]"
        print(content)
        print()  # ファイル間の区切り用の空行
        print(f"### End of file: {rel_path} ###")
        print()  # ファイル間の区切り用の空行
        
    elif os.path.isdir(target_path):
        if recursive:
            # 再帰的に全てのサブディレクトリを探索
            for entry in sorted(os.listdir(target_path)):
                entry_path = os.path.join(target_path, entry)
                print_code(entry_path, exts, exact_names, base_dir, recursive, omit)
        else:
            # 直下のファイルのみ処理（サブディレクトリは探索しない）
            for entry in sorted(os.listdir(target_path)):
                entry_path = os.path.join(target_path, entry)
                if os.path.isfile(entry_path):
                    print_code(entry_path, exts, exact_names, base_dir, recursive, omit)
    else:
        print(f"エラー: '{target_path}' はファイルでもディレクトリでもありません。")

def main():
    parser = argparse.ArgumentParser(
        description="指定パスがファイルならそのファイル、ディレクトリなら（オプションにより）再帰的または直下のファイルを出力します。"
    )
    parser.add_argument("path", nargs='+', help="対象となるファイルまたはフォルダのパス")
    parser.add_argument(
        "-e",
        "--ext",
        nargs="*",
        default=None,
        help="対象とするファイルの拡張子（例: .py .txt）。指定がある場合はその拡張子のファイルのみ出力します。"
    )
    parser.add_argument(
        "-n",
        "--name",
        nargs="*",
        default=None,
        help="対象とするファイル名（完全一致）。拡張子のないファイル（例: Dockerfile Makefile）を指定する場合に便利です。"
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="このオプションを指定すると、ディレクトリ内を再帰的に探索します（デフォルトは直下のみ）。"
    )
    parser.add_argument(
        "-o",
        "--omit",
        nargs="*",
        default=None,
        help="排除するファイル名やフォルダ名のリスト。gitignore風のパターン（例: *.py, folder/）で指定します。"
    )
    args = parser.parse_args()

    # 拡張子フィルタ（小文字に統一）
    exts = [ext.lower() for ext in args.ext] if args.ext else None
    
    # 完全一致ファイル名リスト
    exact_names = args.name if args.name else None

    # フィルタが何も指定されていない場合は全ファイル対象
    if not exts and not exact_names:
        print("情報: フィルタが指定されていないため、全てのファイルを出力します。")

    for target_path in args.path:
        target = os.path.abspath(target_path)

        if not os.path.exists(target):
            print(f"エラー: 指定されたパス '{target}' は存在しません。")
            continue

        # 複数のパスが指定された場合、カレントディレクトリをbase_dirとする
        base_dir = os.getcwd()
        print_code(target, exts, exact_names, base_dir, recursive=args.recursive, omit=args.omit)

if __name__ == "__main__":
    main()