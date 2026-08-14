# amivoice-client-library-python

AmiVoice API を利用して音声認識アプリケーションを開発するための Python クライアントライブラリと、そのサンプルプログラムを提供しています。
本ライブラリは MIT License で提供します。

## パッケージ構成

```text
src/
├── amivoice/            # 高レベルAPI
└── com/amivoice/
    ├── hrp/             # HTTP音声認識API（HRP）
    └── wrp/             # WebSocket音声認識API（WRP）
```

高レベル API は次のように利用できます。

```python
from amivoice import AmiVoiceClient

client = AmiVoiceClient(
    api_key="your-api-key",
    grammar_file_names="-a-general",
    codec="16K",
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
