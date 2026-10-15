# amivoice-client-library-python

AmiVoice API を利用して音声認識アプリケーションを開発するための Python クライアントライブラリと、そのサンプルプログラムを提供しています。
本ライブラリは MIT License で提供します。

## パッケージ構成

```text
src/
└── amivoice/
    ├── __init__.py           # 公開API
    ├── client.py             # 同期HTTP・WebSocket音声認識
    ├── async_client.py       # 非同期HTTP音声認識（同期メソッド提供）
    ├── _*.py                 # 標準ライブラリによるHTTP・WebSocket通信と設定の処理
    ├── constants.py          # 接続エンジンと音声フォーマット
    ├── models.py             # 認識結果とイベント
    ├── async_models.py       # 非同期HTTPジョブと認識結果モデル
    ├── dictionary.py         # ユーザー辞書の管理
    ├── api_key.py            # APIキーの発行
    ├── sentiment_analysis.py # 感情パラメータの定義取得
    ├── grammar.py            # ルールグラマの指定
    ├── settings.py           # クライアント既定値の継承指定
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

長時間の音声やバッチ処理には、非同期 HTTP 音声認識 API（v2）を利用できる`AmiVoiceAsyncClient`も用意されています。
Python の`async`/`await`構文ではなく通常の同期（ブロッキング）メソッドを提供し、ジョブの登録（`submit`）、状態取得（`get_job`）、完了待機（`wait`）を行えます。

詳細な利用方法は[利用方法](https://github.com/advanced-media-inc/amivoice-client-library-python/blob/main/docs/usage.md)を参照してください。

## クライアント既定値の継承（USE_CLIENT_DEFAULT）

クライアントの認識メソッド（`transcribe()`、`stream()`、`submit()`など）では、個別引数を省略するか`USE_CLIENT_DEFAULT`（型は`UseClientDefault`）を指定すると、コンストラクタで保持した設定を継承します。
任意設定を解除して送信しない場合は`None`を渡し、`False`や`0`は解除ではなく明示的な指定値として扱われます。
なお、コンストラクタの URL 引数（`http_api_url`、`ws_api_url`）は既存どおり`None`を拒否し、`USE_CLIENT_DEFAULT`で既定 URL を選択します。

ラッパー関数などで引数をそのまま転送する場合も、未指定の既定値に`USE_CLIENT_DEFAULT`を使用します。

```python
from amivoice import USE_CLIENT_DEFAULT, AmiVoiceClient, Engine, RecognitionResult, UseClientDefault


def recognize_speech(
    audio: bytes,
    *,
    client: AmiVoiceClient,
    confidence_level: float | None | UseClientDefault = USE_CLIENT_DEFAULT,
) -> RecognitionResult:
    return client.transcribe(audio, confidence_level=confidence_level)


client = AmiVoiceClient(grammar_file_names=Engine.A_GENERAL, confidence_level=0.2)
result = recognize_speech(b"RIFF...", client=client)
```

## 公式仕様

最新の公式仕様は以下のマニュアルをご確認ください。

- [AmiVoice API マニュアル（概要・同期HTTP・WebSocket）](https://docs.amivoice.com/amivoice-api/manual/getting-started)
- [非同期HTTP音声認識API（非同期HTTPインタフェース）](https://docs.amivoice.com/amivoice-api/manual/async-http-interface)
