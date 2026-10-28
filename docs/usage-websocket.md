# WebSocket ストリーミング認識ガイド

このガイドでは、`AmiVoiceClient.stream()` を使った WebSocket ストリーミング認識について説明します。

- インストール、認証、共通の `RecognitionSettings`、ユーザー辞書管理: [共通利用ガイド](./usage.md)
- 短時間の録音済みファイルの一括認識: [同期 HTTP 音声認識ガイド](./usage-sync-http.md)
- 長時間音声やバッチ処理: [非同期 HTTP 音声認識（v2）ガイド](./usage-async-http.md)

## 基本的な使い方

`stream()` では `grammar_file_names` と `codec` の両方が必須です。音声フォーマットや接続エンジンの定数は[音声フォーマットと接続エンジン](./usage.md#音声フォーマットと接続エンジン)を参照してください。`with` で接続を管理し、例外が起きた場合もソケットと受信処理を終了させます。

以下はヘッダ付きの音声ファイルを開き、4096 バイトずつ送信する例です。送信中と送信終了後のイベントを、同じ処理で読み取ります。

```python
from amivoice import AmiVoiceClient, Codec, Engine, RecognitionSettings, StreamEvent


def show_event(event: StreamEvent) -> None:
    if event.is_final and event.result is not None:
        if event.result.is_error:
            print("区間の認識失敗:", event.result.data["code"])
        else:
            print("確定:", event.result.text)
    elif event.is_partial:
        print("途中:", event.text)
    elif event.utterance is not None:
        print(event.type, event.utterance.time)
    elif event.notification is not None:
        print("通知:", event.notification.event_id)


client = AmiVoiceClient(
    settings=RecognitionSettings(
        grammar_file_names=Engine.A_GENERAL,
        codec=Codec.HEADER_16K,
    ),
)
with open("audio.wav", "rb") as audio, client.stream() as session:
    for chunk in iter(lambda: audio.read(4096), b""):
        session.write(chunk)
        for event in session.poll():
            show_event(event)

    session.end(timeout=60.0)
    for event in session.poll():
        show_event(event)
    results = session.results()

# results は集計だけに使い、表示済みのイベントを再表示しない
print("成功区間数:", sum(not result.is_error for result in results))
print("失敗区間数:", sum(result.is_error for result in results))
```

`session.end()` は終了コマンドを送るだけでなく、サーバーの `e` 応答まで待ちます。その間も途中結果と確定結果を受信します。最後の結果を取りこぼさないように、`end()` の後で `poll()` または `results()` を読んでください。

`poll()` は到着済みのイベントを返し、まだ到着していないイベントは待ちません。イベントは読み取り時にキューから取り出されます。単一の消費者で読み取り、複数のスレッドや `events()` から同時に消費しないでください。上の例では送信中の `poll()` と終了後の `poll()` を同じスレッドで使い、各イベントを一度だけ表示します。

`results()` は確定結果の一覧のコピーを返します。イベントを消費せず、`poll()` で表示した確定結果も含みます。結果の表示を `poll()` で行う場合は、`results()` から同じ結果を重ねて表示しないようにしてください。

## 区間ごとの結果と通知

確定結果の `A` イベントは、`type="final"` の `StreamEvent` になります。公式サンプルと状態遷移表にある `R` も、互換対応として同じ形式で処理します。`event.result` には[同期 HTTP と同じ `RecognitionResult`](./usage-sync-http.md#型付き認識結果)が入ります。

確定した各区間の `event.result.is_error` または `session.results()` の各結果を調べてください。先行区間が `code="o"` で拒否されても、後続区間の認識に成功する場合があります。セッション全体の成否は全区間を確認して判断し、先行区間の拒否だけで後続区間の受信を打ち切らないでください。通信障害や開始・終了コマンドへのエラー応答は例外として通知します。

`U` は `partial`、`S` と `E` は `utterance_started` と `utterance_ended` に対応します。発話境界の `utterance.time` はミリ秒です。`C` は認識処理の開始を表す `notification` で、`notification.event_id` は `"C"` です。

## 話者ダイアライゼーションの設定

WebSocket の話者ダイアライゼーションの設定方法は同期 HTTP と同じです。`SegmenterProperties` の `speaker_diarization`、`diarizer_alpha`、`diarizer_transition_bias` を使用します。設定手順とコード例は[同期 HTTP の話者ダイアライゼーションの設定](./usage-sync-http.md#話者ダイアライゼーションの設定)を参照してください。

WebSocket の `stream()` では `codec` の指定が必須です。確定結果の `event.result` または `session.results()` の各区間から、単語ごとの `token.label` を参照できます。`RecognitionSettings` の `speaker_diarization`、`diarization_min_speaker`、`diarization_max_speaker` は非同期 HTTP（v2）専用であり、WebSocket では使用できません。

## WebSocket 専用の設定と非対応設定

`result_updated_interval` と `no_input_timeout` は WebSocket 専用の設定です。共通のコンストラクタの `settings` に指定しても、HTTP の `transcribe()` ではサーバーへ送信しません。

- `result_updated_interval`: 途中結果の発行間隔（ミリ秒。`0` は途中結果を発行しない）
- `no_input_timeout`: 発話開始までのタイムアウト（ミリ秒。`0` は無効）

一方、`selected_channel` と `audio_filter_properties` は HTTP 用の設定で、WebSocket では利用できません（WebSocket では 1 チャネル目だけが認識対象になります）。これらをクライアントの `settings` に保持したまま `stream()` を呼ぶと、`ConfigurationError` を送出します。WebSocket の呼び出しでは、`settings=RecognitionSettings(selected_channel=None)` などでチャネル設定を解除してください。設定の継承と解除の詳細は[クライアント設定の継承と解除（USE_CLIENT_DEFAULT）](./usage.md#クライアント設定の継承と解除use_client_default)を参照してください。

ログ保存なしの設定（`logging_opt_out`）や WebSocket URL 末尾の `/` の注意点は、[ログ保存なしの認識](./usage.md#ログ保存なしの認識)を参照してください。

## 待機上限と終了タイムアウト

接続・受信タイムアウトや `recognition_timeout` の基本仕様は、[タイムアウトと単位](./usage.md#タイムアウトと単位)を参照してください。

| 設定 | 単位 | 用途 |
| --- | --- | --- |
| `connect_timeout` | ミリ秒 | 接続待機。`0` は無制限 |
| `receive_timeout` | ミリ秒 | 受信待機。ソケットの待機では `0` は無制限 |
| `recognition_timeout` | ミリ秒 | サーバー側の認識完了までの時間（最初の発話区間の先頭検出時点から計測）。`0` は無効 |
| `session.end(timeout=...)` | 秒 | WebSocket の終了応答を待つ時間 |

WebSocket の開始・終了応答には、クライアント側の待機上限があります。通常は `receive_timeout` を秒へ換算した値を使用します。`receive_timeout=0` でも、この待機上限はクライアントの既定値である 60 秒です。サーバー側の既定値ではありません。終了時だけ上限を変える場合は、`session.end(timeout=...)` を秒単位で指定します。

## 使用例 CLI

環境変数 `AMIVOICE_API_KEY` を設定したうえで、リポジトリのルートから実行します。共通のオプション一覧は[共通の CLI オプション](./usage.md#共通の-cli-オプション)を参照してください。

```bash
# WebSocket・簡易版
uv run examples/wrp_simple_tester.py audio/test.wav --codec 16K

# WebSocket・詳細版では送信単位と途中イベントの表示を指定できる
uv run examples/wrp_tester.py audio/test.wav audio/test2.wav \
  --engine=-a-general --codec 16K --chunk-size 4096 --show-events
```

WebSocket の簡易版（`examples/wrp_simple_tester.py`）と詳細版（`examples/wrp_tester.py`）には `--chunk-size` があり、送信するバイト数を正の整数で指定します。既定値は `4096` です。
詳細版は複数の音声ファイルを位置引数で受け付け、共通の詳細オプションに加えて `--result-updated-interval`、`--no-input-timeout` をミリ秒で指定できます。`--show-events` は途中結果と発話境界も表示するオプションです。

`--url` を明示して `--logging-opt-out` を使う場合は、末尾の `/` を含む `/v1/nolog/` のパスが必要です。指定した URL を自動でログ保存なしのパスへ変更しません。

```bash
uv run examples/wrp_tester.py audio/test.wav --codec 16K \
  --logging-opt-out --url wss://acp-api.amivoice.com/v1/nolog/
```

`--help` は API キーなしで実行でき、通信もしません。

```bash
uv run examples/wrp_tester.py --help
```

終了コードは成功が `0`、認識・通信・ファイル読み込みなどの失敗が `1` です。
引数の構文や型が不正な場合は、`argparse` が `2` で終了します。
数値の範囲や URL とログ保存設定の組み合わせなど、クライアントが検出する設定エラーは `1` です。
