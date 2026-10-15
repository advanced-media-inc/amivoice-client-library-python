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
    ├── settings.py           # 認識設定とクライアント既定値の継承指定
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
from amivoice import AmiVoiceClient, Engine, RecognitionSettings

client = AmiVoiceClient(settings=RecognitionSettings(grammar_file_names=Engine.A_GENERAL))
result = client.transcribe("audio.wav")
print(result.text)
```

認識設定は`RecognitionSettings`にまとめて`settings`へ渡します。旧 API の個別の認識引数は使用できません。
`RecognitionSettings.grammar_file_names`は HTTP と WebSocket の両方で必須です。HTTP ではヘッダ付き音声であれば`codec`を省略できます。
WebSocket では`codec`も必ず指定してください。

長時間の音声やバッチ処理には、非同期 HTTP 音声認識 API（v2）を利用できる`AmiVoiceAsyncClient`も用意されています。
Python の`async`/`await`構文ではなく通常の同期（ブロッキング）メソッドを提供し、ジョブの登録（`submit`）、状態取得（`get_job`）、完了待機（`wait`）を行えます。

詳細な利用方法は以下のガイドを参照してください。

- [共通利用ガイド（インストール・認証・共通設定・辞書管理）](https://github.com/advanced-media-inc/amivoice-client-library-python/blob/main/docs/usage.md)
- [同期 HTTP 音声認識ガイド](./docs/usage-sync-http.md)
- [非同期 HTTP 音声認識（v2）ガイド](./docs/usage-async-http.md)
- [WebSocket ストリーミング認識ガイド](./docs/usage-websocket.md)

## クライアント既定値の継承（USE_CLIENT_DEFAULT）

コンストラクタの`settings=None`は空の認識設定を表します。
認識メソッド（`transcribe()`、`stream()`、`submit()`）では、`settings`を省略するか`USE_CLIENT_DEFAULT`（型は`UseClientDefault`）を指定すると、クライアントの設定を継承します。空の`RecognitionSettings()`もすべての項目を継承します。
呼び出し時の`settings=None`は全認識設定を解除します。接続エンジンも解除されるため、そのまま送信すると必須設定の不足で`ConfigurationError`になります。

`RecognitionSettings`の各項目は、省略または`USE_CLIENT_DEFAULT`で継承し、`None`で解除します。`False`や`0`は解除ではなく明示値です。
プロキシ、通信タイムアウト、接続 URL、`raise_on_error`、完了待機の引数は、引き続き独立した引数です。
同期クライアントのコンストラクタでは、URL 引数に`USE_CLIENT_DEFAULT`を指定すると既定 URL を選択します。
非同期クライアントのコンストラクタの`api_url`は URL 文字列のみを受け付けます。
呼び出し時の`api_url=USE_CLIENT_DEFAULT`は、カスタム URL も含めてクライアントの接続先を継承し、既定 URL へリセットしません。URL に`None`は指定できません。

ラッパー関数などで引数をそのまま転送する場合も、未指定の既定値に`USE_CLIENT_DEFAULT`を使用します。

```python
from amivoice import (
    USE_CLIENT_DEFAULT,
    AmiVoiceClient,
    Engine,
    RecognitionResult,
    RecognitionSettings,
    UseClientDefault,
)


def recognize_speech(
    audio: bytes,
    *,
    client: AmiVoiceClient,
    confidence_level: float | None | UseClientDefault = USE_CLIENT_DEFAULT,
) -> RecognitionResult:
    return client.transcribe(audio, settings=RecognitionSettings(confidence_level=confidence_level))


client = AmiVoiceClient(
    settings=RecognitionSettings(grammar_file_names=Engine.A_GENERAL, confidence_level=0.2)
)
result = recognize_speech(b"RIFF...", client=client)
```

## 公式仕様

最新の公式仕様は以下のマニュアルをご確認ください。

- [AmiVoice API マニュアル（概要・同期HTTP・WebSocket）](https://docs.amivoice.com/amivoice-api/manual/getting-started)
- [非同期HTTP音声認識API（非同期HTTPインタフェース）](https://docs.amivoice.com/amivoice-api/manual/async-http-interface)
