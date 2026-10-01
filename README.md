# amivoice-client-library-python

AmiVoice API を利用して音声認識アプリケーションを開発するための Python クライアントライブラリと、そのサンプルプログラムを提供しています。
本ライブラリは MIT License で提供します。

## パッケージ構成

```text
src/
└── amivoice/
    ├── client.py                 # 公開 AmiVoiceClient と transcribe
    ├── models.py                 # 認識結果とストリームイベントのモデル
    ├── _recognition_protocol.py  # HTTP リクエスト生成・WebSocket コマンド生成・イベント変換
    ├── _http_connection.py       # 標準ライブラリによる HTTP/TLS/プロキシ接続
    ├── _http_recognition.py      # HTTP 音声認識（HRP）の送受信
    ├── _websocket_transport.py   # 標準 socket による RFC 6455 WebSocket 通信
    ├── _stream.py                # WebSocket ストリーミング認識セッション管理
    └── ...                       # 音声検証・辞書・グラマ・設定等の内部モジュール
```

本ライブラリは外部ランタイム依存を持たず、Python 標準ライブラリのみで動作します。旧パッケージ構成に含まれていた `com.amivoice` は廃止されました。

高レベル API は次のように利用できます。

```python
from amivoice import AmiVoiceClient, Codec, Engine

client = AmiVoiceClient(
    api_key="your-api-key",
    grammar_file_names=Engine.A_GENERAL,
    codec=Codec.HEADER_16K,
)
result = client.transcribe("audio.wav")
print(result.text)
```

詳細な利用方法は [利用方法](https://github.com/advanced-media-inc/amivoice-client-library-python/blob/main/docs/usage.md) を参照してください。

## 開発

```bash
uv sync
uv run pytest tests/unit
uv run ruff check .
uv run ruff format --check .
```

API キーなどの認証情報は、ソースコードへ直接記述せず環境変数などから渡してください。
