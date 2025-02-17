import os
import sys
import argparse

def print_code(target_path, exts=None, base_dir=None, recursive=False):
    """
    target_path: 処理対象のファイルまたはディレクトリのパス
    exts: 対象とする拡張子のリスト（例: ['.py', '.txt']）。Noneの場合は全ファイル対象。
    base_dir: ヘッダーで表示する相対パスの基準となるディレクトリ。
              指定がない場合は、最初に渡された target_path がファイルならそのディレクトリ、
              ディレクトリならそのディレクトリ自身が基準になります。
    recursive: Trueの場合、再帰的にサブディレクトリも探索します。
    """
    if base_dir is None:
        base_dir = os.path.dirname(target_path) if os.path.isfile(target_path) else target_path

    if os.path.isfile(target_path):
        # 拡張子フィルタのチェック（指定がある場合）
        if exts:
            _, file_ext = os.path.splitext(target_path)
            if file_ext.lower() not in exts:
                # ルートで指定されたファイルの場合はメッセージを出して終了
                #print(f"指定されたファイルの拡張子 '{file_ext}' はフィルタ対象外です。")
                return
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
        print(f"### End of file: {rel_path} ###") # 区切り線を追加
        print()  # ファイル間の区切り用の空行
        
    elif os.path.isdir(target_path):
        if recursive:
            # 再帰的に全てのサブディレクトリを探索
            for entry in sorted(os.listdir(target_path)):
                entry_path = os.path.join(target_path, entry)
                print_code(entry_path, exts, base_dir, recursive)
        else:
            # 直下のファイルのみ処理（サブディレクトリは探索しない）
            for entry in sorted(os.listdir(target_path)):
                entry_path = os.path.join(target_path, entry)
                if os.path.isfile(entry_path):
                    print_code(entry_path, exts, base_dir, recursive)
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
        "-r",
        "--recursive",
        action="store_true",
        help="このオプションを指定すると、ディレクトリ内を再帰的に探索します（デフォルトは直下のみ）。"
    )
    args = parser.parse_args()

    # 拡張子フィルタ（小文字に統一）
    exts = [ext.lower() for ext in args.ext] if args.ext else None

    for target_path in args.path:
        target = os.path.abspath(target_path)

        if not os.path.exists(target):
            print(f"エラー: 指定されたパス '{target}' は存在しません。")
            continue

        # 複数のパスが指定された場合、最初のパスのディレクトリをbase_dirとする
        base_dir = os.path.dirname(os.path.abspath(args.path[0])) if os.path.isfile(os.path.abspath(args.path[0])) else os.path.abspath(args.path[0])
        print_code(target, exts, base_dir, recursive=args.recursive)

if __name__ == "__main__":
    main()
