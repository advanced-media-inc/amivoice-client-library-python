# AmiVoice Python クライアント利用ガイド

## 方式の選び方とガイド一覧

用途に応じて 3 つの音声認識インタフェースを選択できます。このページでは共通の設定と周辺機能を説明し、各方式の手順は専用ガイドで説明します。

| 方式 | ガイド | 主な用途 | クライアント・関数 |
| --- | --- | --- | --- |
| 同期 HTTP | [同期 HTTP 音声認識ガイド](./usage-sync-http.md) | 16 MB 以下の録音済み音声を簡単に音声認識したい場合 | `AmiVoiceClient.transcribe()`、`transcribe()` |
| 非同期 HTTP（v2） | [非同期 HTTP 音声認識（v2）ガイド](./usage-async-http.md) | 大きい録音済み音声や認識精度を上げたい場合 | `AmiVoiceAsyncClient` |
| WebSocket | [WebSocket ストリーミング認識ガイド](./usage-websocket.md) | リアルタイム性が求められる場合 | `AmiVoiceClient.stream()` |

## インストール

Python 3.11 以降に対応しています。
以下のコマンドでクライアントライブラリをインストールします。

```bash
pip install amivoice-api-client
```

## 認証

API キーを参照する場合、環境変数 `AMIVOICE_API_KEY` の利用を推奨します。
以下の値を自分のキーに置き換えて、実行する環境へ設定してください。

```bash
export AMIVOICE_API_KEY="your-api-key"
```

各 `amivoice` クライアントは、`api_key` を省略すると環境変数からキーを読み取ります。
アプリケーション側で安全に管理したキーをコンストラクタへ渡すこともできますが、ソースコード、コマンドラインの引数、URL などにはキーを書かないでください。

### API キーの発行

`ApiKeyIssuanceClient` を使うと、有効期限や接続元 IP アドレスの制限を付けた API キーを発行できます。
API キーの発行権限が付いた API キーを Bearer 認証で使用します。発行用のキーはサーバー側で管理してください。

発行専用の環境変数 `AMIVOICE_ISSUER_API_KEY` に、発行権限が付いた API キーを設定します。`ApiKeyIssuanceClient` では、`AMIVOICE_API_KEY` は発行用として使用しません。

```bash
export AMIVOICE_ISSUER_API_KEY="api-key-with-issuance-permission"
```

```python
from datetime import timedelta

from amivoice import ApiKeyIssuanceClient

api_key_issuance_client = ApiKeyIssuanceClient()
issued_api_key = api_key_issuance_client.issue(
    expires_in=timedelta(hours=2),
    allowed_ip_addresses=("203.0.113.0/24",),
)
# 発行したキーは必要な利用先へ安全に渡し、画面やログへ出力しない
```

`expires_in` にはミリ秒の整数、`2h` などの API 形式の文字列、`timedelta` を指定できます。省略時の有効期限はサーバー側の既定値で、公式仕様では 30 秒です。整数と `timedelta` は 1 ミリ秒以上を指定してください。1 ミリ秒未満の `timedelta` の端数は切り捨てます。

`allowed_ip_addresses` には IPv4 アドレスまたは IPv4 CIDR の一覧を指定します。各要素は文字列、`ipaddress.IPv4Address`、`ipaddress.IPv4Network` を使用できます。IPv6 アドレスや空の一覧を指定すると `ConfigurationError` を送出します。接続元 IP アドレスを制限しない場合は、この引数を省略してください。

## 共通の認識設定

認識設定は `RecognitionSettings` にまとめ、`AmiVoiceClient`、`AmiVoiceAsyncClient` のコンストラクタと、`transcribe()`、`stream()`、`submit()` の `settings` へ渡します。モジュールレベルの `transcribe()` も同じ形式です。旧 API の個別の認識引数は削除されています。
プロキシ、通信タイムアウト、接続 URL、`raise_on_error`、`wait()` の待機制御は、引き続き独立した引数です。
任意の認識パラメータを指定しない場合、ライブラリはサーバーの既定値を補って送信しません。公式に記載された既定値も、予告なく変更される場合があります。

### 個別引数からの移行

以前は `AmiVoiceClient(grammar_file_names=Engine.A_GENERAL, confidence_level=0.2)` のように指定していました。現在は、同じ設定を次のようにまとめます。呼び出し時の上書きも `settings` へ移してください。

```python
from amivoice import AmiVoiceClient, Engine, RecognitionSettings

client = AmiVoiceClient(
    settings=RecognitionSettings(grammar_file_names=Engine.A_GENERAL, confidence_level=0.2),
    connect_timeout=10_000,
)
result = client.transcribe(
    "audio.wav",
    settings=RecognitionSettings(confidence_level=0.3),
    raise_on_error=False,
)
```

### 設定項目一覧

以下は `RecognitionSettings` の全項目です。各項目の既定値は `USE_CLIENT_DEFAULT` です。インタフェースによる制限は、後述の各設定の説明と各方式のガイドを確認してください。

| 項目 | 内容 |
| --- | --- |
| `grammar_file_names` | 接続エンジン名 |
| `codec` | 音声フォーマット |
| `profile_id` | ユーザー辞書の参照名 |
| `profile_words` | セッション単語。設定文字列または `ProfileWord` の一覧 |
| `segmenter` | 型付きの `SegmenterProperties` |
| `segmenter_properties` | セグメンターの設定文字列 |
| `selected_channel` | 認識対象チャネル。整数または混合範囲のタプル |
| `audio_filter_properties` | 同期 HTTP のチャネル設定文字列 |
| `confidence_level` | 信頼度しきい値 |
| `keep_filler_token` | フィラーを残すか |
| `result_updated_interval` | WebSocket の途中結果間隔。ミリ秒 |
| `extension` | 使用量集計などの JSON 設定文字列 |
| `billing_key` | 使用量集計タグ |
| `recognition_timeout` | 認識完了のタイムアウト。ミリ秒 |
| `complete_timeout` | ルール認識の確定待ち時間。ミリ秒 |
| `wildcard_model_penalty` | ルール認識のワイルドカードペナルティ |
| `max_decoding_time` | 認識処理時間の上限。ミリ秒 |
| `max_response_time` | 最大応答時間。ミリ秒 |
| `max_decoding_rate` | 認識処理時間の上限倍率 |
| `target_response_time` | 目標応答時間。ミリ秒 |
| `target_decoding_rate` | 認識処理時間の目標倍率 |
| `no_input_timeout` | WebSocket の発話開始待ち時間。ミリ秒 |
| `logging_opt_out` | 音声ログを保存しないか |
| `content_id` | 非同期 HTTP のユーザー定義 ID。冪等性キーではない |
| `compatible_with_sync` | 非同期 HTTP（v2）で同期 HTTP インタフェース互換の認識結果形式を返させる設定 |
| `speaker_diarization` | 非同期 HTTP の話者ダイアライゼーション有効化 |
| `diarization_min_speaker` | 非同期 HTTP の最小話者数。`1` 以上 `20` 以下の整数 |
| `diarization_max_speaker` | 非同期 HTTP の最大話者数。`1` 以上 `20` 以下の整数 |

`RecognitionSettings` は `frozen=True`、`kw_only=True` のデータクラスです。生成時はキーワード引数を使い、生成後に項目を変更できません。
`profile_words` へ渡した単語一覧は、生成時にタプルへコピーします。元のリストを変更しても設定には反映されません。
値や設定の組み合わせ、インタフェースごとの対応可否は、クライアントの初期化時と呼び出し時に検証します。設定オブジェクトを生成しただけでは、すべての値の検証は行いません。

### クライアント設定の継承と解除（USE_CLIENT_DEFAULT）

コンストラクタ（`AmiVoiceClient`、`AmiVoiceAsyncClient`）では、`settings` を省略するか `None` を指定すると、空の認識設定になります。
モジュール関数 `transcribe()` の `settings` は `RecognitionSettings` 型の必須キーワード引数です。省略すると `TypeError` になり、`None` や `USE_CLIENT_DEFAULT` などの `RecognitionSettings` 以外の値を指定すると、クライアント生成や通信の前に `ConfigurationError` を送出します。空の `RecognitionSettings()` は型として受け付けますが、必須の `grammar_file_names` が不足するため `ConfigurationError` になります。
クライアントインスタンスの呼び出しメソッド（`client.transcribe()`、`client.stream()`、`client.submit()`）の `settings` は、次のように扱います。

| 指定 | 動作 |
| --- | --- |
| 省略または `USE_CLIENT_DEFAULT` | クライアントの認識設定を継承 |
| 空の `RecognitionSettings()` | すべての項目を継承 |
| 項目を指定した `RecognitionSettings(...)` | 指定した項目だけ上書き |
| `None` | 指定不可（通信前に `ConfigurationError` を送出） |

インスタンスメソッドの呼び出し時に `settings=None` は指定できず、呼び出し直後に通信せず `ConfigurationError` を送出します。クライアントの設定を引き継がずに別の設定で認識したい場合は、新しいクライアントを作成するか、`RecognitionSettings(...)` で必要な項目を明示して上書きしてください。
`RecognitionSettings` の各項目では、省略または公開 sentinel の `USE_CLIENT_DEFAULT`（型は `UseClientDefault`）が継承、`None` が解除です。`False` や `0` は明示値として扱います。
同期 HTTP・WebSocket の `logging_opt_out` は真偽値が必要で、項目単位の `None` による解除はできません。ログ保存なしを無効にする場合は `False` を指定してください。非同期 HTTP での扱いは[非同期 HTTP のログ保存なしの設定](./usage-async-http.md#ログ保存なしの設定logging_opt_out)を参照してください。

次の組み合わせは、片方だけを上書きすると、クライアントに保持されたもう片方の形式を解除します。`None` による片方の解除でも同じ動作です。

- `segmenter` と `segmenter_properties`
- `selected_channel` と `audio_filter_properties`
- `billing_key` と `extension`

同期クライアントのコンストラクタの URL 引数（`http_api_url`、`ws_api_url`）は、`USE_CLIENT_DEFAULT` で既定 URL を選択します。
呼び出し時の `api_url` は、省略または `USE_CLIENT_DEFAULT` でクライアントの接続先を継承します。カスタム URL も継承し、既定 URL へリセットする指定ではありません。URL に `None` は指定できません。非同期クライアントの URL 指定は[非同期 HTTP の共通設定の継承と解除](./usage-async-http.md#共通設定の継承と解除)を参照してください。

ラッパー関数などで引数をそのまま転送する場合も、未指定を表す引数に `USE_CLIENT_DEFAULT` を指定します。

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

### 音声フォーマットと接続エンジン

`Codec` は音声フォーマット名の定数です。`Codec.HEADER_16K` は文字列 `"16K"` と同じ値で、`Codec("lsb16k")` のように大文字小文字を区別せずに解決できます。文字列の有効性を判定するときは `Codec(value)` を呼び、`ValueError` を捕捉してください。`"lsb16k" in Codec` の結果は Python のバージョンによって異なります。

音声ファイルのヘッダにフォーマット情報がある場合、HTTP 認識では `codec` を省略できます。ヘッダ付き音声で明示する場合は、8kHz または 11.025kHz なら `Codec.HEADER_8K`、16kHz 以上なら `Codec.HEADER_16K` を使用します。WebSocket の `stream()` では `codec` が必須です。

ヘッダなし PCM では、エンディアンとサンプリングレートに合った `Codec.LSB16K` や `Codec.MSB16K` などを指定してください。詳しくは[公式の音声フォーマット](https://docs.amivoice.com/amivoice-api/manual/audio-format)を参照してください。

`Engine` は接続エンジン名の定数です。定数名は公式の接続エンジン名から先頭の `-` を除き、`-` を `_` に置き換えて大文字にしたものです。例えば `-a2-ja-general` は `Engine.A2_JA_GENERAL` に対応します。

会話用の汎用エンジンは `Engine.A_GENERAL`、音声入力用は `Engine.A_GENERAL_INPUT` を指定します。AmiVoice API Private のルールエンジンは `Engine.A_RULE_INPUT_PRIVATE` を使用します。グラマファイルを使うルールグラマは、この Private エンジン専用です。

利用するエンジンと使用できる音声の組み合わせは[公式のエンジン一覧](https://docs.amivoice.com/amivoice-api/manual/engines#list)で確認してください。

### ログ保存なしの認識

サーバー側に音声を保存しない設定で認識する場合は、`RecognitionSettings(logging_opt_out=True)` を指定します。同期 HTTP と WebSocket の既定 URL が、それぞれログ保存なしの URL に切り替わります。`transcribe()` や `stream()` の `settings` でも指定できます。非同期 HTTP（v2）では URL のパスではなくリクエストパラメータで制御するため、[非同期 HTTP のログ保存なしの設定](./usage-async-http.md#ログ保存なしの設定logging_opt_out)を参照してください。

```python
from amivoice import AmiVoiceClient, Engine, RecognitionSettings

client = AmiVoiceClient(
    settings=RecognitionSettings(grammar_file_names=Engine.A_GENERAL, logging_opt_out=True),
)
result = client.transcribe("audio.wav")
print(result.text)
```

`http_api_url`、`ws_api_url`、呼び出し時の `api_url` で URL を指定した場合、その URL は書き換えません。`logging_opt_out=True` のときは、明示した URL のパスが下表と一致するかを検証します。一致しない場合は通信前に `ConfigurationError` を送出します。既定と同じ URL を明示した場合も、この検証の対象です。

| インタフェース | ログ保存なしのパス | 例 |
| --- | --- | --- |
| 同期 HTTP | `/v1/nolog/recognize` | `https://acp-api.amivoice.com/v1/nolog/recognize` |
| WebSocket | `/v1/nolog/` | `wss://acp-api.amivoice.com/v1/nolog/` |

WebSocket の URL は末尾の `/` まで必要です。`wss://acp-api.amivoice.com/v1/nolog` のように末尾の `/` がない場合、AmiVoice API ではログ保存ありになります。詳しくは[公式のログ保存の説明](https://docs.amivoice.com/amivoice-api/manual/log-retention)を参照してください。

AWS PrivateLink で接続する場合は、ホスト名を `acp-api-private.amivoice.com` へ変えた URL を指定します。以下のクライアントは WebSocket でも利用できます。`stream()` の呼び出し時には、音声のフォーマットと合う `codec` を指定してください。

```python
from amivoice import AmiVoiceClient, Engine, RecognitionSettings

client = AmiVoiceClient(
    settings=RecognitionSettings(grammar_file_names=Engine.A_GENERAL, logging_opt_out=True),
    http_api_url="https://acp-api-private.amivoice.com/v1/nolog/recognize",
    ws_api_url="wss://acp-api-private.amivoice.com/v1/nolog/",
)
result = client.transcribe("audio.wav")
print(result.text)
```

### タイムアウトと単位

認識のタイムアウトと、クライアントの通信待機時間は別の設定です。

| 設定 | 単位 | 用途 |
| --- | --- | --- |
| `connect_timeout` | ミリ秒 | 接続待機。`0` は無制限 |
| `receive_timeout` | ミリ秒 | 受信待機。ソケットの待機では `0` は無制限 |
| `recognition_timeout` | ミリ秒 | サーバー側の認識完了までの時間。`0` は無効 |

`recognition_timeout` は音声の再生時間ではなく、認識処理にかかる時間を対象とします。同期 HTTP ではサーバーが音声の受信を開始した時点、WebSocket では最初の発話区間の先頭を検出した時点から計測します。

WebSocket の開始・終了応答の待機上限と `session.end(timeout=...)` は、[WebSocket の待機上限と終了タイムアウト](./usage-websocket.md#待機上限と終了タイムアウト)を参照してください。非同期 HTTP の `wait(poll_interval=..., timeout=...)` は、[非同期 HTTP の待機制御とエラーハンドリング](./usage-async-http.md#待機制御waitとエラーハンドリング)を参照してください。

### インタフェース専用の設定

インタフェースごとに利用できる専用設定が異なります。

- HTTP 専用（`selected_channel`、`audio_filter_properties`）: [マルチチャネル音声のチャネル選択](./usage-sync-http.md#マルチチャネル音声のチャネル選択)および[WebSocket の専用設定と非対応設定](./usage-websocket.md#websocket-専用の設定と非対応設定)を参照してください。
- WebSocket 専用（`result_updated_interval`、`no_input_timeout`）: [WebSocket の専用設定と非対応設定](./usage-websocket.md#websocket-専用の設定と非対応設定)を参照してください。
- 非同期 HTTP 専用（`content_id`、`compatible_with_sync`）と非対応項目: [非同期 HTTP 音声認識（v2）ガイド](./usage-async-http.md)を参照してください。

### セッション単語登録

認識セッションだけで有効にする単語は、`ProfileWord` のシーケンスで指定できます。ハイブリッドエンジンでは `spoken` を必須とし、クラスを指定する場合は `classname` を追加します。End to End エンジンでは `alternative_written` と `biasing` を使用します。公式の送信形式に沿った設定文字列も指定できます。

```python
from amivoice import AmiVoiceClient, Engine, ProfileWord, RecognitionSettings

client = AmiVoiceClient(
    settings=RecognitionSettings(
        grammar_file_names=Engine.A_GENERAL,
        profile_words=(
            ProfileWord("AmiVoice", "あみぼいす", "固有名詞"),
            ProfileWord("WWW", "とりぷるだぶる"),
        ),
    ),
)
result = client.transcribe("audio.wav")
print(result.text)
```

セッション単語の各値には半角スペースや `|` を含めないでください。表記の `written` には半角コロン `:` も使えません。これらの文字を含む `ProfileWord` を生成したり送信形式へ変換したりすると、`ConfigurationError` を送出します。複数の単語はライブラリが `|` で連結し、API の送信形式へ変換します。

`profile_id` と `profile_words` を同時に指定すると、`profile_words` が優先されます。プロファイルに登録済みの単語はそのセッションで有効になりません。

### セグメンター設定

発話検出と言語識別は `SegmenterProperties` で指定できます。同期 HTTP、WebSocket、非同期 HTTP（v2）のすべてで利用できます。

```python
from amivoice import AmiVoiceClient, Engine, RecognitionSettings, SegmenterProperties

client = AmiVoiceClient(
    settings=RecognitionSettings(
        grammar_file_names=Engine.A_GENERAL,
        segmenter=SegmenterProperties(
            languages=("ja", "en"),
        ),
    ),
)
result = client.transcribe("audio.wav")
print(result.text)
```

型付きの `segmenter` と設定文字列の `segmenter_properties` は同時に指定できません。`languages` には `ja`、`en`、`zh`、`ko`、`th` を指定できます。言語識別の結果と音声認識の結果の言語が異なる場合もあるため、両方を確認してください。

話者ダイアライゼーションの設定方法はインタフェースによって異なります。各方式の専用ガイドを参照してください。

- 同期 HTTP: [同期 HTTP の話者ダイアライゼーションの設定](./usage-sync-http.md#話者ダイアライゼーションの設定)
- WebSocket: [WebSocket の話者ダイアライゼーションの設定](./usage-websocket.md#話者ダイアライゼーションの設定)
- 非同期 HTTP（v2）: [非同期 HTTP の話者ダイアライゼーションの設定](./usage-async-http.md#話者ダイアライゼーションの設定)

### 信頼度しきい値とフィラー

発話区間の認識結果を信頼度で拒否する場合は、`confidence_level` を指定します。同期 HTTP、WebSocket、非同期 HTTP で利用でき、範囲は `0.0` 以上 `1.0` 以下です。

```python
from amivoice import AmiVoiceClient, Engine, RecognitionSettings

client = AmiVoiceClient(
    settings=RecognitionSettings(grammar_file_names=Engine.A_GENERAL, confidence_level=0.3),
)
result = client.transcribe("audio.wav", raise_on_error=False)
if result.is_error:
    print("認識失敗:", result.data["code"])
else:
    print(result.text)
```

指定した値未満の区間はサーバー側で拒否されます。拒否を表す `code="o"` は成功ではなく、`is_error=True` になります。`1.0` では多くの結果が拒否されるため、値は用途に合わせて設定してください。

`confidence_level` を指定しない場合はサーバーへ送信しません。公式仕様の既定値は `0.1` ですが、固定された値としてライブラリから送信することはありません。

フィラーを残す場合は `keep_filler_token=True`、削除する場合は `False` を指定します。End to End エンジンはこの設定に対応せず、値を明示すると `ConfigurationError` を送出します。End to End エンジンでは `False` も指定せず、省略してください。

### 処理時間とレスポンスの制御

処理時間の制御は、認識処理を途中で打ち切ったり、処理速度と認識率を調整したりする上級者向けの設定です。値を小さくしすぎると、認識結果が途中で終了する場合があります。コンストラクタ、`transcribe()`、`stream()`、`submit()`、モジュールレベルの `transcribe()` の `settings` で指定できます。

| 設定 | 単位 | 用途 |
| --- | --- | --- |
| `max_decoding_time` | ミリ秒 | 認識処理時間の上限 |
| `max_response_time` | ミリ秒 | 音声時間に加える処理時間の上限。リアルタイム録音時のみ有効 |
| `target_response_time` | ミリ秒 | 暫定結果の目標応答時間。リアルタイム録音時のみ有効 |
| `max_decoding_rate` | 音声時間に対する倍率 | 認識処理時間の上限。録音済みのバッチ音声のみ有効 |
| `target_decoding_rate` | 音声時間に対する倍率 | 暫定結果の目標倍率。録音済みのバッチ音声のみ有効 |

例えば、リアルタイム録音を送る WebSocket のクライアントでは、`max_response_time=5_000` と `target_response_time=1_000` を指定できます。これらは録音済みファイルを送信するバッチ認識では無効です。

バッチ音声の HTTP 認識では、処理時間を音声時間に対する倍率で制御できます。

```python
from amivoice import AmiVoiceClient, Engine, RecognitionSettings

client = AmiVoiceClient(
    settings=RecognitionSettings(
        grammar_file_names=Engine.A_GENERAL,
        max_decoding_time=30_000,
        max_decoding_rate=2.0,
        target_decoding_rate=1.5,
    ),
)
result = client.transcribe("audio.wav")
print(result.text)
```

時間系の `0` は無効、レート系の負値も無効を表します。公式仕様の既定値は時間系が `0`、レート系が `-1` です。未指定の値は送信せず、サーバーの既定値に委ねます。

### ルールグラマ

AmiVoice API Private の「音声入力_ルール」エンジンを使う場合は、`build_grammar_file_names()` で接続エンジン名とグラマ指定を組み立てます。グラマファイルを使えるのは `Engine.A_RULE_INPUT_PRIVATE` だけで、ヘルパーも既定でこのエンジンを使います。この機能は通常の AmiVoice API 環境では利用できません。

グラマ本文を直接指定するときは、`encode_grammar()` で GZIP 圧縮と Base64 エンコードを行います。URL とエンコード済み本文は混在できます。ヘルパーは URL エンコードを追加せず、送信時のエンコードはライブラリが処理します。

```python
from pathlib import Path

from amivoice import AmiVoiceClient, RecognitionSettings, build_grammar_file_names, encode_grammar

grammar_file_names = build_grammar_file_names(
    encode_grammar(Path("Number.gram").read_text(encoding="utf-8")),
    "https://example.com/grammars/Burger.gram",
    fallback=True,
)
client = AmiVoiceClient(
    settings=RecognitionSettings(
        grammar_file_names=grammar_file_names,
        complete_timeout=5_000,
        wildcard_model_penalty=4.0,
    ),
)
result = client.transcribe("audio.wav")
print(result.text)
```

通常のグラマ指定は `|` で連結します。前のグラマで認識に失敗したときだけ次を試す場合は、`fallback=True` で `||` を使用します。

`complete_timeout` は確定待ちタイムアウトをミリ秒で指定します。`wildcard_model_penalty` は `<GARBAGE>` の認識されやすさを調整し、目安は `2.0` から `6.0` です。目安の範囲外も指定できますが、負値は指定できません。両引数とも `-a-rule-input-private` 専用で、ほかのエンジンに指定すると `ConfigurationError` を送出します。また、非同期 HTTP（v2）ではこれらのルール設定に対応していません。

Private 環境の既定値は異なる場合があります。JSGF や SRGS の文法はライブラリで検証しません。[公式のルールグラマ](https://docs.amivoice.com/amivoice-api/manual/rule-grammar)と[グラマファイルの指定方法](https://docs.amivoice.com/amivoice-api/manual/set-grammar-file)を確認してください。誤ったグラマはサーバー側でエラーになります。

### 使用量集計タグ

使用量をユーザーやアプリケーション単位で集計する場合は、`billing_key` を指定します。同期 HTTP、WebSocket、非同期 HTTP で利用できます。

```python
from amivoice import AmiVoiceClient, Engine, RecognitionSettings

client = AmiVoiceClient(
    settings=RecognitionSettings(grammar_file_names=Engine.A_GENERAL, billing_key="user01"),
)
result = client.transcribe("audio.wav")
print(result.text)
```

`billing_key` は内部で `extension` 用の JSON 形式に変換します。`extension` と同時には指定できません。`extension` を自分で組み立てる場合は、公開ヘルパー `build_billing_extension()` も利用できます。使用量は AmiVoice Cloud Platform のマイページにある発話量 CSV で確認してください。

## ユーザー辞書管理

`UserDictionaryClient` で、プロファイルの単語を登録・取得・削除できます。API キーは環境変数 `AMIVOICE_API_KEY` から読み取ります。

> [!NOTE]
> AmiVoice API のユーザー辞書登録は、指定した単語一覧による全件置換のみです。単語単位の追加・削除 API はありません。既存の単語を残して追加・変更する場合は、残す単語を含む一覧を登録してください。

`register_words()` は置換後の一覧を登録します。`clear_words()` は空の一覧を登録して全件を削除します。

以下の例は `user01` の内容を置き換え、最後に全件を削除します。既存のプロファイルを使う場合は、事前に内容をバックアップしてください。

```python
from amivoice import Engine, ProfileWord, UserDictionaryClient

user_dictionary = UserDictionaryClient()
user_dictionary.register_words(
    Engine.A_GENERAL,
    "user01",
    (
        ProfileWord(written="AmiVoice", spoken="あみぼいす", classname="固有名詞"),
        ProfileWord(written="WWW", spoken="とりぷるだぶる"),
    ),
    sampling_rate="16k",
)

words = user_dictionary.get_words(Engine.A_GENERAL, "user01", sampling_rate="16k")
for word in words:
    print(word.written, word.spoken, word.classname)

profiles = user_dictionary.list_profiles(Engine.A_GENERAL, sampling_rate="16k")
classnames = user_dictionary.list_classnames(Engine.A_GENERAL, sampling_rate="16k")
print("プロファイル:", profiles)
print("クラス名:", classnames)

# user01 の単語を全件削除する
user_dictionary.clear_words(Engine.A_GENERAL, "user01", sampling_rate="16k")
```

`list_profiles(engine, sampling_rate=...)` はプロファイル名、`list_classnames(engine, sampling_rate=...)` は利用できるクラス名を、文字列のタプルで返します。

ハイブリッドエンジンでは 8k 用と 16k 用のプロファイルが分かれます。音声に合わせて `sampling_rate="8k"` または `"16k"` を指定すると、API のクエリ `adf=8k` または `adf=16k` に変換します。省略時はサーバーの既定値に委ね、公式仕様では 16k 用が対象です。

### End to End エンジンの単語強調

End to End エンジンでは `alternative_written` と `biasing` を指定します。`biasing` は `0.0` 以上 `1.0` 以下です。数値のほか、`"0.5"` などの小数表記の文字列も使用できます。`"1e-5"` などの指数表記の文字列は指定できません。ハイブリッド用の `spoken` や `classname` と、End to End 用のフィールドは混在させないでください。

```python
from amivoice import Engine, ProfileWord, UserDictionaryClient

user_dictionary = UserDictionaryClient()
user_dictionary.register_words(
    Engine.A2_JA_GENERAL,
    "user01",
    (
        ProfileWord(
            written="AmiVoice",
            alternative_written="あみぼいす",
            biasing=0.75,
        ),
    ),
)
```

辞書 API の `engine` には、公式の音声認識エンジン一覧にある接続エンジン名を指定します。旧例の `-a-e2e` ではなく、上の例は `Engine.A2_JA_GENERAL` を使用します。辞書 API 専用の別名として `-a-e2e` を使う根拠はありません。End to End エンジンでは 8k と 16k を同じエンジンとして扱うため、`sampling_rate` の指定は不要です。

### 登録した辞書の参照

ユーザー辞書はアプリケーションのデータベースなどで全件を保持し、バックアップしてください。API のプロファイルをマスターデータにせず、アプリケーションで管理する一覧から更新する方法が推奨されています。

音声認識で参照する場合は、登録時と同じ接続エンジンを使い、`profile_id` の先頭に `:` を付けます。辞書 API の登録・取得・削除には `:` を付けない ID を渡してください。

```python
from amivoice import AmiVoiceClient, Engine, RecognitionSettings

recognition_client = AmiVoiceClient(
    settings=RecognitionSettings(grammar_file_names=Engine.A_GENERAL, profile_id=":user01"),
)
result = recognition_client.transcribe("audio.wav")
print(result.text)
```

`:` 付きの ID は参照だけを行います。`:` を付けないと、セッション終了時にプロファイルを上書きする場合があります。ライブラリは値を書き換えず、`UserWarning` を出します。詳しくは[公式のプロファイルの利用方法](https://docs.amivoice.com/amivoice-api/manual/user-dictionary-use-profile)を参照してください。

## 感情パラメータの定義取得

`SentimentAnalysisClient().list_parameters(language="ja")` で、感情パラメータの名前、表示名、最小値、最大値を取得できます。対応する表示言語は `ja` のみです。API キーは環境変数 `AMIVOICE_API_KEY` から読み取ります。

```python
from amivoice import SentimentAnalysisClient

parameters = SentimentAnalysisClient().list_parameters(language="ja")
for parameter in parameters:
    print(
        parameter.name,
        parameter.display_name,
        parameter.minimum,
        parameter.maximum,
    )
```

この API は定義の取得専用で、音声の感情を分析したり、音声認識ジョブを作成したりするものではありません。
非同期 HTTP クライアント（`AmiVoiceAsyncClient`）では、感情分析のジョブ設定はまだ提供していません。
話者ダイアライゼーションは方式によって指定方法が異なります。同期 HTTP・WebSocket では[同期 HTTP の話者ダイアライゼーションの設定](./usage-sync-http.md#話者ダイアライゼーションの設定)および[WebSocket の話者ダイアライゼーションの設定](./usage-websocket.md#話者ダイアライゼーションの設定)を参照してください。非同期 HTTP では `RecognitionSettings(speaker_diarization=True, ...)` で指定します。詳細は[非同期 HTTP の話者ダイアライゼーションの設定](./usage-async-http.md#話者ダイアライゼーションの設定)を参照してください。

## 使用例 CLI の共通仕様

`examples/` の各プログラムは、現在の公開 API を使用します。認証は環境変数 `AMIVOICE_API_KEY` から読み取るため、キーを引数へ渡しません。リポジトリのルートから実行してください。

各方式の実行例、専用オプション、終了コードは、それぞれのガイドを参照してください。

- [同期 HTTP の使用例 CLI](./usage-sync-http.md#使用例-cli)
- [非同期 HTTP の使用例 CLI](./usage-async-http.md#使用例-cli)
- [WebSocket の使用例 CLI](./usage-websocket.md#使用例-cli)

`--engine` の値は先頭が `-` のため、`--engine=-a-general` のように `=` で指定する方法を推奨します。
既定のエンジンは `-a-general` です。同期 HTTP・WebSocket CLI の音声フォーマットの既定値は `16K` です。
非同期 HTTP CLI の `--codec` は省略でき、ヘッダなし音声では明示してください。
`--help` は API キーなしで実行でき、通信もしません。

### 共通の CLI オプション

同期 HTTP・WebSocket の簡易版と詳細版は、次の共通オプションを使用できます。
非同期 HTTP CLI でも同名の接続・認識オプションを利用できます。配置位置やサブコマンドの詳細は[非同期 HTTP の使用例 CLI](./usage-async-http.md#使用例-cli)を参照してください。

| オプション | 内容 |
| --- | --- |
| `--engine=...` | 接続エンジン名 |
| `--codec` | 公式の音声フォーマット名 |
| `--url` | 接続先 URL の上書き |
| `--logging-opt-out` | ログ保存なしの設定を使用 |
| `--connect-timeout` | 接続のタイムアウト。ミリ秒、CLI の既定値は `10000` |
| `--receive-timeout` | 受信のタイムアウト。ミリ秒、CLI の既定値は `30000` |

同期 HTTP・WebSocket の詳細版（`hrp_tester.py`、`wrp_tester.py`）と非同期 HTTP の `submit` サブコマンドでは、次の認識オプションを指定できます。

| オプション | 内容 |
| --- | --- |
| `--profile-id` | 辞書の参照。例は `:user01` |
| `--profile-words` | セッション単語の設定文字列 |
| `--segmenter-properties` | 発話検出、話者ダイアライゼーション（同期 HTTP・WebSocket のみ）、言語識別の設定文字列 |
| `--confidence-level` | 信頼度しきい値 |
| `--keep-filler-token` / `--no-keep-filler-token` | フィラーの保持・削除。省略時は値を送信しない |
| `--billing-key` | 使用量集計タグ |
| `--recognition-timeout` | 認識完了までのタイムアウト。ミリ秒 |
| `--max-decoding-time` | 認識処理時間の上限。ミリ秒 |
| `--max-response-time` | 音声時間に加える処理時間の上限。ミリ秒 |
| `--max-decoding-rate` | 音声時間に対する処理時間の上限倍率 |
| `--target-response-time` | 暫定結果の目標応答時間。ミリ秒 |
| `--target-decoding-rate` | 暫定結果の目標倍率 |
