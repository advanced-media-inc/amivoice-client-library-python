---
applyTo: "**.py"
---

<!-- Pythonコードについてのカスタムインストラクション -->

### Pythonのバージョン

Python のバージョンは 3.11+とし、引数、返り値には型ヒントを積極的に使用すること。

関数には Google Style の Docstring を記載すること。

### 注意事項

- `sys.path.append`などで遅延インポートが必要な場合を除き、特別な理由がなければ必ず import 文はファイルの先頭で行うこと。特に関数内で import することは禁止する。
- `boto3`モジュールを使用するプロジェクトの場合、セッションの宣言は各ファイル内で行い、クラス化しないこと。別ファイルから共通のセッションを呼び出すことは禁止する。

### リンター・フォーマッター

Python プログラムのリンター及びフォーマッターには Ruff を使用する。
Python プログラムに変更を加えた際には以下のコマンドでコードを整形すること。

```sh
uv run ruff check --fix --config <pyproject.tomlのパス>
uv run ruff format <変更したファイルパス> --config <pyproject.tomlのパス>
```

これで直らないエラーがある場合は、手動で修正すること。
エラーがなくなるまで、これを繰り返すこと。

### ロギング

ログを出力する際には `loguru` モジュールを使用する。
debug / info / warning / error / critical の各レベルを適切に使い分けること。
また、AWS 上で動作するプログラムでは `logger.exception` を禁止する。
