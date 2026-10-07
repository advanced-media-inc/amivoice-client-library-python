# amivoice-client-library-python

AmiVoice API を利用して音声認識アプリケーションを開発するための Python クライアントライブラリと、そのサンプルプログラムを提供しています。
本ライブラリは MIT License で提供します。

## パッケージ構成

```text
src/
└── amivoice/
    ├── __init__.py           # 公開API
    ├── client.py             # 同期HTTP・WebSocket音声認識
    ├── _*.py                 # 標準ライブラリによるHTTP・WebSocket通信と設定の処理
    ├── constants.py          # 接続エンジンと音声フォーマット
    ├── models.py             # 認識結果とイベント
    ├── dictionary.py         # ユーザー辞書の管理
    ├── api_key.py            # APIキーの発行
    ├── sentiment_analysis.py # 感情パラメータの定義取得
    ├── grammar.py            # ルールグラマの指定
    └── exceptions.py         # 公開例外
```

## クイックスタート

Python 3.11 以降に対応しています。アプリケーションから利用する場合は、配布パッケージをインストールします。

```bash
pip install amivoice-api-client
```

API キーを環境変数`AMIVOICE_API_KEY`に設定してから実行してください。
クライアントは環境変数からキーを読み取るため、ソースコードや実行時の引数にキーを書く必要はありません。

```python
from amivoice import AmiVoiceClient, Engine

client = AmiVoiceClient(grammar_file_names=Engine.A_GENERAL)
result = client.transcribe("audio.wav")
print(result.text)
```

`grammar_file_names`は HTTP と WebSocket の両方で必須です。HTTP ではヘッダ付き音声であれば`codec`を省略できます。
WebSocket では`codec`も必ず指定してください。

詳細な利用方法は[利用方法](https://github.com/advanced-media-inc/amivoice-client-library-python/blob/main/docs/usage.md)を参照してください。

## 公式仕様

最新の公式仕様は[AmiVoice API マニュアル](https://docs.amivoice.com/amivoice-api/manual/getting-started)をご確認ください。
