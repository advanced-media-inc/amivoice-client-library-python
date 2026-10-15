# AmiVoice Python クライアントで HTTP・WebSocket 認識を利用する

## インストール

Python 3.11 以降に対応しています。
以下のコマンドでクライアントライブラリをインストールします。

```bash
pip install amivoice-api-client
```

## 認証

API キーを参照する場合、環境変数`AMIVOICE_API_KEY`の利用を推奨します。
以下の値を自分のキーに置き換えて、実行する環境へ設定してください。

```bash
export AMIVOICE_API_KEY="your-api-key"
```

各`amivoice`クライアントは、`api_key`を省略すると環境変数からキーを読み取ります。
アプリケーション側で安全に管理したキーをコンストラクタへ渡すこともできますが、ソースコード、コマンドラインの引数、URL などにはキーを書かないでください。

### APIキーの発行

`ApiKeyIssuanceClient`を使うと、有効期限や接続元 IP アドレスの制限を付けた API キーを発行できます。
API キーの発行権限が付いた API キーを Bearer 認証で使用します。発行用のキーはサーバー側で管理してください。

発行専用の環境変数`AMIVOICE_ISSUER_API_KEY`に、発行権限が付いた API キーを設定します。`ApiKeyIssuanceClient`では、`AMIVOICE_API_KEY`は発行用として使用しません。

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

`expires_in`にはミリ秒の整数、`2h`などの API 形式の文字列、`timedelta`を指定できます。省略時の有効期限はサーバー側の既定値で、公式仕様では 30 秒です。整数と`timedelta`は 1 ミリ秒以上を指定してください。1 ミリ秒未満の`timedelta`の端数は切り捨てます。

`allowed_ip_addresses`には IPv4 アドレスまたは IPv4 CIDR の一覧を指定します。各要素は文字列、`ipaddress.IPv4Address`、`ipaddress.IPv4Network`を使用できます。IPv6 アドレスや空の一覧を指定すると`ConfigurationError`を送出します。接続元 IP アドレスを制限しない場合は、この引数を省略してください。

## HTTP音声認識

`grammar_file_names`には接続エンジン名を指定します。
コンストラクタで共通の設定を保持し、`transcribe()`の呼び出し時に上書きできます。

```python
from amivoice import AmiVoiceClient, Codec, Engine

client = AmiVoiceClient(
    grammar_file_names=Engine.A_GENERAL,
    codec=Codec.HEADER_16K,
)
result = client.transcribe("audio.wav")
print(result.text)
```

`transcribe()`にはファイルパス、`pathlib.Path`、`bytes`、バイナリファイルオブジェクトを渡せます。入力音声は 16,777,215 バイト以下である必要があります。

モジュールレベルの`transcribe()`でも同期 HTTP で認識できます。

```python
from amivoice import Engine, transcribe

result = transcribe("audio.wav", grammar_file_names=Engine.A_GENERAL)
print(result.text)
```

### 音声フォーマットと接続エンジン

`Codec`は音声フォーマット名の定数です。`Codec.HEADER_16K`は文字列`"16K"`と同じ値で、`Codec("lsb16k")`のように大文字小文字を区別せずに解決できます。文字列の有効性を判定するときは`Codec(value)`を呼び、`ValueError`を捕捉してください。`"lsb16k" in Codec`の結果は Python のバージョンによって異なります。

音声ファイルのヘッダにフォーマット情報がある場合、HTTP 認識では`codec`を省略できます。ヘッダ付き音声で明示する場合は、8kHz または 11.025kHz なら`Codec.HEADER_8K`、16kHz 以上なら`Codec.HEADER_16K`を使用します。

ヘッダなし PCM では、エンディアンとサンプリングレートに合った`Codec.LSB16K`や`Codec.MSB16K`などを指定してください。詳しくは[公式の音声フォーマット](https://docs.amivoice.com/amivoice-api/manual/audio-format)を参照してください。

`Engine`は接続エンジン名の定数です。定数名は公式の接続エンジン名から先頭の`-`を除き、`-`を`_`に置き換えて大文字にしたものです。例えば`-a2-ja-general`は`Engine.A2_JA_GENERAL`に対応します。

会話用の汎用エンジンは`Engine.A_GENERAL`、音声入力用は`Engine.A_GENERAL_INPUT`を指定します。AmiVoice API Private のルールエンジンは`Engine.A_RULE_INPUT_PRIVATE`を使用します。グラマファイルを使うルールグラマは、この Private エンジン専用です。

利用するエンジンと使用できる音声の組み合わせは[公式のエンジン一覧](https://docs.amivoice.com/amivoice-api/manual/engines#list)で確認してください。

### 認識の成功と失敗

HTTP ステータスが 200 でも、認識に成功したとは限りません。ライブラリは本文の`code`と`message`で成否を判定します。成功結果は両方が空文字列で、`text`が空ではありません。`code`または`message`が空でなければ、`RecognitionResult.is_error`は`True`になります。信頼度による拒否を示す`code="o"`も音声認識は行っていません。

`transcribe()`は既定の`raise_on_error=True`で、認識失敗時に`RecognitionError`を送出します。失敗した結果をアプリケーションで調べる場合は、`raise_on_error=False`を指定します。

```python
from amivoice import AmiVoiceClient, Engine

client = AmiVoiceClient(grammar_file_names=Engine.A_GENERAL)
result = client.transcribe("audio.wav", raise_on_error=False)
if result.is_error:
    print("認識失敗:", result.data["code"])
else:
    print(result.text)
```

`raise_on_error=False`は、通信障害や不正なレスポンスまで成功結果に変える設定ではありません。通信に失敗した場合は`ConnectionFailedError`、結果の形式が不正な場合などは`RecognitionError`を送出します。

### 型付き認識結果

`RecognitionResult.results`から発話区間と単語を参照できます。信頼度、時刻、話者ラベル、言語ラベルも型付きで取得できます。

```python
from amivoice import AmiVoiceClient, Engine

client = AmiVoiceClient(grammar_file_names=Engine.A_GENERAL)
result = client.transcribe("audio.wav")

print(result.utterance_id)
for utterance in result.results:
    print(utterance.text, utterance.starttime, utterance.endtime)
    for token in utterance.tokens:
        print(
            token.written,
            token.spoken,
            token.confidence,
            token.label,
            token.language,
        )
```

`spoken`、`confidence`、`starttime`、`endtime`、`label`、`language`など、エンジンや設定によって省略されるフィールドは`None`になります。`raw`には受信した JSON 文字列、`data`にはその辞書、`text`には認識テキストが入ります。`is_error`、`session_id`も公開フィールドです。

## WebSocketストリーミング認識

`stream()`では`grammar_file_names`と`codec`の両方が必須です。`with`で接続を管理し、例外が起きた場合もソケットと受信処理を終了させます。

以下はヘッダ付きの音声ファイルを開き、4096 バイトずつ送信する例です。送信中と送信終了後のイベントを、同じ処理で読み取ります。

```python
from amivoice import AmiVoiceClient, Codec, Engine, StreamEvent


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
    grammar_file_names=Engine.A_GENERAL,
    codec=Codec.HEADER_16K,
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

`session.end()`は終了コマンドを送るだけでなく、サーバーの`e`応答まで待ちます。その間も途中結果と確定結果を受信します。最後の結果を取りこぼさないように、`end()`の後で`poll()`または`results()`を読んでください。

`poll()`は到着済みのイベントを返し、まだ到着していないイベントは待ちません。イベントは読み取り時にキューから取り出されます。単一の消費者で読み取り、複数のスレッドや`events()`から同時に消費しないでください。上の例では送信中の`poll()`と終了後の`poll()`を同じスレッドで使い、各イベントを一度だけ表示します。

`results()`は確定結果の一覧のコピーを返します。イベントを消費せず、`poll()`で表示した確定結果も含みます。結果の表示を`poll()`で行う場合は、`results()`から同じ結果を重ねて表示しないようにしてください。

### 区間ごとの結果と通知

確定結果の`A`イベントは、`type="final"`の`StreamEvent`になります。公式サンプルと状態遷移表にある`R`も、互換対応として同じ形式で処理します。

確定した各区間の`event.result.is_error`または`session.results()`の各結果を調べてください。先行区間が`code="o"`で拒否されても、後続区間の認識に成功する場合があります。セッション全体の成否は全区間を確認して判断し、先行区間の拒否だけで後続区間の受信を打ち切らないでください。通信障害や開始・終了コマンドへのエラー応答は例外として通知します。

`U`は`partial`、`S`と`E`は`utterance_started`と`utterance_ended`に対応します。発話境界の`utterance.time`はミリ秒です。`C`は認識処理の開始を表す`notification`で、`notification.event_id`は`"C"`です。

## 共通の認識設定

コンストラクタで指定した値は、各認識呼び出しの設定として引き継がれます。対応する引数を`transcribe()`や`stream()`に指定すると、その呼び出しだけ上書きします。任意の認識パラメータを指定しない場合、ライブラリはサーバーの既定値を勝手に補って送信しません。公式に記載された既定値も、予告なく変更される場合があります。

### クライアント設定の継承と解除（USE_CLIENT_DEFAULT）

`transcribe()`や`stream()`などの呼び出しメソッドでは、各引数を省略するか公開 sentinel の`USE_CLIENT_DEFAULT`（型は`UseClientDefault`）を指定すると、クライアントに保持された設定を継承します。
任意の認識設定を解除して送信しない場合は`None`を指定します。`False`や`0`は解除ではなく、明示的な指定値として扱われます。
一方、コンストラクタの URL 引数（`http_api_url`、`ws_api_url`）は既存どおり`None`を拒否し、`USE_CLIENT_DEFAULT`で既定 URL を選択します。

ラッパー関数などで引数をそのまま転送する場合も、未指定を表す引数に`USE_CLIENT_DEFAULT`を指定します。

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

### ログ保存なしの認識

サーバー側に音声を保存しない設定で認識する場合は、`logging_opt_out=True`を指定します。同期 HTTP と WebSocket の既定 URL が、それぞれログ保存なしの URL に切り替わります。`transcribe()`や`stream()`の呼び出し時にも指定できます。

```python
from amivoice import AmiVoiceClient, Engine

client = AmiVoiceClient(
    grammar_file_names=Engine.A_GENERAL,
    logging_opt_out=True,
)
result = client.transcribe("audio.wav")
print(result.text)
```

`http_api_url`、`ws_api_url`、呼び出し時の`api_url`で URL を指定した場合、その URL は書き換えません。`logging_opt_out=True`のときは、明示した URL のパスが下表と一致するかを検証します。一致しない場合は通信前に`ConfigurationError`を送出します。既定と同じ URL を明示した場合も、この検証の対象です。

| インタフェース | ログ保存なしのパス | 例 |
| --- | --- | --- |
| 同期 HTTP | `/v1/nolog/recognize` | `https://acp-api.amivoice.com/v1/nolog/recognize` |
| WebSocket | `/v1/nolog/` | `wss://acp-api.amivoice.com/v1/nolog/` |

WebSocket の URL は末尾の`/`まで必要です。`wss://acp-api.amivoice.com/v1/nolog`のように末尾の`/`がない場合、AmiVoice API ではログ保存ありになります。詳しくは[公式のログ保存の説明](https://docs.amivoice.com/amivoice-api/manual/log-retention)を参照してください。

AWS PrivateLink で接続する場合は、ホスト名を`acp-api-private.amivoice.com`へ変えた URL を指定します。以下のクライアントは WebSocket でも利用できます。`stream()`の呼び出し時には、音声のフォーマットと合う`codec`を指定してください。

```python
from amivoice import AmiVoiceClient, Engine

client = AmiVoiceClient(
    grammar_file_names=Engine.A_GENERAL,
    logging_opt_out=True,
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
| `connect_timeout` | ミリ秒 | 接続待機。`0`は無制限 |
| `receive_timeout` | ミリ秒 | 受信待機。ソケットの待機では`0`は無制限 |
| `recognition_timeout` | ミリ秒 | サーバー側の認識完了までの時間。`0`は無効 |
| `session.end(timeout=...)` | 秒 | WebSocket の終了応答を待つ時間 |

WebSocket の開始・終了応答には、クライアント側の待機上限があります。通常は`receive_timeout`を秒へ換算した値を使用します。`receive_timeout=0`でも、この待機上限はクライアントの既定値である 60 秒です。サーバー側の既定値ではありません。終了時だけ上限を変える場合は、`session.end(timeout=...)`を指定します。

`recognition_timeout`は音声の再生時間ではなく、認識処理にかかる時間を対象とします。同期 HTTP ではサーバーが音声の受信を開始した時点、WebSocket では最初の発話区間の先頭を検出した時点から計測します。

### インタフェース専用の設定

`selected_channel`と`audio_filter_properties`は同期 HTTP 専用です。これらをコンストラクタに設定したクライアントで`stream()`を呼ぶと、設定を無視せず`ConfigurationError`を送出します。WebSocket では音声フィルタを指定しないクライアントを使用してください。

`result_updated_interval`と`no_input_timeout`は WebSocket 専用です。共通のコンストラクタに指定しても、HTTP の`transcribe()`ではサーバーへ送信しません。

`result_updated_interval`は途中結果を発行する間隔で、単位はミリ秒です。`0`を指定すると途中結果を発行しません。`no_input_timeout`は発話開始までのタイムアウトをミリ秒で指定し、`0`で無効になります。

### マルチチャネル音声のチャネル選択

複数チャネルの音声を同期 HTTP で認識する場合は、`selected_channel`で認識対象を指定できます。チャネル番号は`0`から始まり、単一チャネルは整数で指定します。複数チャネルの混合平均は`(0, N)`のタプルで指定し、`N`は正の整数に限ります。

`(0, 1)`はチャネル 0 と 1 を混合する指定です。`(1, 2)`のように先頭が 0 以外の範囲や、`(0, 0)`のように開始と終了が同じ範囲は`ConfigurationError`になります。チャネル 0 だけを認識する場合は`selected_channel=0`を使用してください。

```python
from amivoice import AmiVoiceClient, Engine

client = AmiVoiceClient(
    grammar_file_names=Engine.A_GENERAL,
    selected_channel=(0, 1),
)
result = client.transcribe("stereo.wav")
print(result.text)
```

複数チャネルに対応するのは、Wave、Ogg、FLAC などヘッダに音声フォーマットが含まれる音声です。`codec="LSB16K"`などを指定して送るヘッダなし PCM は 1 チャネルだけに対応します。別のチャネルの選択や複数チャネルの混合はできません。詳しくは[音声フォーマットのチャネルの説明](https://docs.amivoice.com/amivoice-api/manual/audio-format#channels)を参照してください。

API の設定文字列を直接指定する場合は`audio_filter_properties`を使用します。対応する形式は`selectedChannel=0`などの単一チャネル、または`selectedChannel=0-N`の範囲です。`selected_channel`と同時には指定できません。WebSocket では 1 チャネル目だけが認識対象になります。

### セッション単語登録

認識セッションだけで有効にする単語は、`ProfileWord`のシーケンスで指定できます。ハイブリッドエンジンでは`spoken`を必須とし、クラスを指定する場合は`classname`を追加します。End to End エンジンでは`alternative_written`と`biasing`を使用します。公式の送信形式に沿った設定文字列も指定できます。

```python
from amivoice import AmiVoiceClient, Engine, ProfileWord

client = AmiVoiceClient(
    grammar_file_names=Engine.A_GENERAL,
    profile_words=(
        ProfileWord("AmiVoice", "あみぼいす", "固有名詞"),
        ProfileWord("WWW", "とりぷるだぶる"),
    ),
)
result = client.transcribe("audio.wav")
print(result.text)
```

セッション単語の各値には半角スペースや`|`を含めないでください。表記の`written`には半角コロン`:`も使えません。これらの文字を含む`ProfileWord`を生成したり送信形式へ変換したりすると、`ConfigurationError`を送出します。複数の単語はライブラリが`|`で連結し、API の送信形式へ変換します。

`profile_id`と`profile_words`を同時に指定すると、`profile_words`が優先されます。プロファイルに登録済みの単語はそのセッションで有効になりません。

### セグメンター設定

発話検出、話者ダイアライゼーション、言語識別は`SegmenterProperties`で指定できます。同期 HTTP と WebSocket の両方で利用できます。

```python
from amivoice import AmiVoiceClient, Engine, SegmenterProperties

client = AmiVoiceClient(
    grammar_file_names=Engine.A_GENERAL,
    segmenter=SegmenterProperties(
        speaker_diarization=True,
        diarizer_alpha="1e-20",
        languages=("ja", "en"),
    ),
)
result = client.transcribe("audio.wav")
print(result.text)
```

型付きの`segmenter`と設定文字列の`segmenter_properties`は同時に指定できません。`languages`には`ja`、`en`、`zh`、`ko`、`th`を指定できます。言語識別の結果と音声認識の結果の言語が異なる場合もあるため、両方を確認してください。

### 信頼度しきい値とフィラー

発話区間の認識結果を信頼度で拒否する場合は、`confidence_level`を指定します。同期 HTTP と WebSocket の両方で利用でき、範囲は`0.0`以上`1.0`以下です。

```python
from amivoice import AmiVoiceClient, Engine

client = AmiVoiceClient(
    grammar_file_names=Engine.A_GENERAL,
    confidence_level=0.3,
)
result = client.transcribe("audio.wav", raise_on_error=False)
if result.is_error:
    print("認識失敗:", result.data["code"])
else:
    print(result.text)
```

指定した値未満の区間はサーバー側で拒否されます。拒否を表す`code="o"`は成功ではなく、`is_error=True`になります。`1.0`では多くの結果が拒否されるため、値は用途に合わせて設定してください。

`confidence_level`を指定しない場合はサーバーへ送信しません。公式仕様の既定値は`0.1`ですが、固定された値としてライブラリから送信することはありません。

フィラーを残す場合は`keep_filler_token=True`、削除する場合は`False`を指定します。End to End エンジンはこの設定に対応せず、値を明示すると`ConfigurationError`を送出します。End to End エンジンでは`False`も指定せず、省略してください。

### 処理時間とレスポンスの制御

処理時間の制御は、認識処理を途中で打ち切ったり、処理速度と認識率を調整したりする上級者向けの設定です。値を小さくしすぎると、認識結果が途中で終了する場合があります。コンストラクタ、`transcribe()`、`stream()`、モジュールレベルの`transcribe()`で指定できます。

| 設定 | 単位 | 用途 |
| --- | --- | --- |
| `max_decoding_time` | ミリ秒 | 認識処理時間の上限 |
| `max_response_time` | ミリ秒 | 音声時間に加える処理時間の上限。リアルタイム録音時のみ有効 |
| `target_response_time` | ミリ秒 | 暫定結果の目標応答時間。リアルタイム録音時のみ有効 |
| `max_decoding_rate` | 音声時間に対する倍率 | 認識処理時間の上限。録音済みのバッチ音声のみ有効 |
| `target_decoding_rate` | 音声時間に対する倍率 | 暫定結果の目標倍率。録音済みのバッチ音声のみ有効 |

例えば、リアルタイム録音を送る WebSocket のクライアントでは、`max_response_time=5_000`と`target_response_time=1_000`を指定できます。これらは録音済みファイルを送信するバッチ認識では無効です。

バッチ音声の HTTP 認識では、処理時間を音声時間に対する倍率で制御できます。

```python
from amivoice import AmiVoiceClient, Engine

client = AmiVoiceClient(
    grammar_file_names=Engine.A_GENERAL,
    max_decoding_time=30_000,
    max_decoding_rate=2.0,
    target_decoding_rate=1.5,
)
result = client.transcribe("audio.wav")
print(result.text)
```

時間系の`0`は無効、レート系の負値も無効を表します。公式仕様の既定値は時間系が`0`、レート系が`-1`です。未指定の値は送信せず、サーバーの既定値に委ねます。

### ルールグラマ

AmiVoice API Private の「音声入力_ルール」エンジンを使う場合は、`build_grammar_file_names()`で接続エンジン名とグラマ指定を組み立てます。グラマファイルを使えるのは`Engine.A_RULE_INPUT_PRIVATE`だけで、ヘルパーも既定でこのエンジンを使います。この機能は通常の AmiVoice API 環境では利用できません。

グラマ本文を直接指定するときは、`encode_grammar()`で GZIP 圧縮と Base64 エンコードを行います。URL とエンコード済み本文は混在できます。ヘルパーは URL エンコードを追加せず、送信時のエンコードはライブラリが処理します。

```python
from pathlib import Path

from amivoice import AmiVoiceClient, build_grammar_file_names, encode_grammar

grammar_file_names = build_grammar_file_names(
    encode_grammar(Path("Number.gram").read_text(encoding="utf-8")),
    "https://example.com/grammars/Burger.gram",
    fallback=True,
)
client = AmiVoiceClient(
    grammar_file_names=grammar_file_names,
    complete_timeout=5_000,
    wildcard_model_penalty=4.0,
)
result = client.transcribe("audio.wav")
print(result.text)
```

通常のグラマ指定は`|`で連結します。前のグラマで認識に失敗したときだけ次を試す場合は、`fallback=True`で`||`を使用します。

`complete_timeout`は確定待ちタイムアウトをミリ秒で指定します。`wildcard_model_penalty`は`<GARBAGE>`の認識されやすさを調整し、目安は`2.0`から`6.0`です。目安の範囲外も指定できますが、負値は指定できません。両引数とも`-a-rule-input-private`専用で、ほかのエンジンに指定すると`ConfigurationError`を送出します。

Private 環境の既定値は異なる場合があります。JSGF や SRGS の文法はライブラリで検証しません。[公式のルールグラマ](https://docs.amivoice.com/amivoice-api/manual/rule-grammar)と[グラマファイルの指定方法](https://docs.amivoice.com/amivoice-api/manual/set-grammar-file)を確認してください。誤ったグラマはサーバー側でエラーになります。

### 使用量集計タグ

使用量をユーザーやアプリケーション単位で集計する場合は、`billing_key`を指定します。同期 HTTP と WebSocket の両方で利用できます。

```python
from amivoice import AmiVoiceClient, Engine

client = AmiVoiceClient(
    grammar_file_names=Engine.A_GENERAL,
    billing_key="user01",
)
result = client.transcribe("audio.wav")
print(result.text)
```

`billing_key`は内部で`extension`用の JSON 形式に変換します。`extension`と同時には指定できません。`extension`を自分で組み立てる場合は、公開ヘルパー`build_billing_extension()`も利用できます。使用量は AmiVoice Cloud Platform のマイページにある発話量 CSV で確認してください。

## ユーザー辞書管理

`UserDictionaryClient`で、プロファイルの単語を登録・取得・削除できます。API キーは環境変数`AMIVOICE_API_KEY`から読み取ります。

> [!NOTE]
> AmiVoice API のユーザー辞書登録は、指定した単語一覧による全件置換のみです。単語単位の追加・削除 API はありません。既存の単語を残して追加・変更する場合は、残す単語を含む一覧を登録してください。

`register_words()`は置換後の一覧を登録します。`clear_words()`は空の一覧を登録して全件を削除します。

以下の例は`user01`の内容を置き換え、最後に全件を削除します。既存のプロファイルを使う場合は、事前に内容をバックアップしてください。

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

`list_profiles(engine, sampling_rate=...)`はプロファイル名、`list_classnames(engine, sampling_rate=...)`は利用できるクラス名を、文字列のタプルで返します。

ハイブリッドエンジンでは 8k 用と 16k 用のプロファイルが分かれます。音声に合わせて`sampling_rate="8k"`または`"16k"`を指定すると、API のクエリ`adf=8k`または`adf=16k`に変換します。省略時はサーバーの既定値に委ね、公式仕様では 16k 用が対象です。

### End to Endエンジンの単語強調

End to End エンジンでは`alternative_written`と`biasing`を指定します。`biasing`は`0.0`以上`1.0`以下です。数値のほか、`"0.5"`などの小数表記の文字列も使用できます。`"1e-5"`などの指数表記の文字列は指定できません。ハイブリッド用の`spoken`や`classname`と、End to End 用のフィールドは混在させないでください。

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

辞書 API の`engine`には、公式の音声認識エンジン一覧にある接続エンジン名を指定します。旧例の`-a-e2e`ではなく、上の例は`Engine.A2_JA_GENERAL`を使用します。辞書 API 専用の別名として`-a-e2e`を使う根拠はありません。End to End エンジンでは 8k と 16k を同じエンジンとして扱うため、`sampling_rate`の指定は不要です。

### 登録した辞書の参照

ユーザー辞書はアプリケーションのデータベースなどで全件を保持し、バックアップしてください。API のプロファイルをマスターデータにせず、アプリケーションで管理する一覧から更新する方法が推奨されています。

音声認識で参照する場合は、登録時と同じ接続エンジンを使い、`profile_id`の先頭に`:`を付けます。辞書 API の登録・取得・削除には`:`を付けない ID を渡してください。

```python
from amivoice import AmiVoiceClient, Engine

recognition_client = AmiVoiceClient(
    grammar_file_names=Engine.A_GENERAL,
    profile_id=":user01",
)
result = recognition_client.transcribe("audio.wav")
print(result.text)
```

`:`付きの ID は参照だけを行います。`:`を付けないと、セッション終了時にプロファイルを上書きする場合があります。ライブラリは値を書き換えず、`UserWarning`を出します。詳しくは[公式のプロファイルの利用方法](https://docs.amivoice.com/amivoice-api/manual/user-dictionary-use-profile)を参照してください。

## 感情パラメータの定義取得

`SentimentAnalysisClient().list_parameters(language="ja")`で、感情パラメータの名前、表示名、最小値、最大値を取得できます。対応する表示言語は`ja`のみです。API キーは環境変数`AMIVOICE_API_KEY`から読み取ります。

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
非同期 HTTP クライアント（`AmiVoiceAsyncClient`）では、話者ダイアライゼーションと感情分析の設定はまだ提供していません。
同期 HTTP・WebSocket の話者ダイアライゼーションは、前述のセグメンター設定で利用できます。

## 非同期HTTP音声認識（v2）

長時間の音声ファイルやバッチ処理には、非同期 HTTP 音声認識 API（v2）を利用します。
本ライブラリでは、`AmiVoiceAsyncClient`クラスを用いて非同期ジョブを登録・取得・待機します。

なお、クラス名に「Async」を含みますが、Python の`async`/`await`構文を使用するライブラリではありません。通常の同期（ブロッキング）メソッドを提供します。`await`は使用できません。

### 基本的な流れ

非同期 HTTP 認識は、ジョブの登録（`submit()`）、状態取得（`get_job()`）、完了待機（`wait()`）の 3 つの操作で利用します。

```python
from amivoice import AmiVoiceAsyncClient, Engine

client = AmiVoiceAsyncClient(grammar_file_names=Engine.A_GENERAL)

# 音声のアップロードと受付応答を待つ。認識完了までは待たない。
submission = client.submit("audio.wav")
print(f"受付ジョブID: {submission.session_id}")

# 完了までブロックして待機
snapshot = client.wait(submission.session_id)
print(f"状態: {snapshot.status}")
if snapshot.recognition is not None:
    print(f"認識テキスト: {snapshot.recognition.text}")
```

### ジョブIDからの再開

ジョブ ID（`submission.session_id`）をデータベースやファイルへ保存しておけば、プロセスの再起動後や別のクライアントインスタンスからでも状態の取得や待機を再開できます。
取得や待機だけを行う場合、クライアントのコンストラクタで`grammar_file_names`の指定は不要です。

```python
from amivoice import AmiVoiceAsyncClient

client = AmiVoiceAsyncClient()

# 保存済みのジョブIDから状態と結果を取得
snapshot = client.get_job("job1")

# 保存済みのジョブIDの完了を待機
completed_snapshot = client.wait("job1")
```

### 入力音声の仕様と一時ファイル退避

`submit()`には、ファイルパス（文字列）、`pathlib.Path`、`bytes`、バイナリファイルオブジェクト（ストリーム）を渡せます。

音声データの上限は 2,147,483,647 バイト（約 2 GiB）です。ファイルは分割して読み込みます。
長さを事前に判定できないストリームは、一時ファイルへ退避してから送信します。
一時ファイル用に音声サイズ分のディスク容量が必要です。

利用者が渡したストリームは現在位置から読み、ライブラリでは閉じません。
呼び出し元で寿命を管理してください。
内部で開いたファイルと一時ファイルは、送信終了時や例外発生時に閉じて回収します。

#### 送信音声の照合

`submit()`は実際に送信した音声チャンクから MD5 チェックサムを計算し、`AsyncJobSubmission`の`audio_size`と`audio_md5`にローカル情報として保持します。
サーバーから返った受付応答本文（`data`や`raw`）には追加しません。
なお、ここでの MD5 は転送確認を目的とした値であり、暗号学的な真正性を保証するものではありません。

ジョブ状態を取得した後は、`job.matches_audio(snapshot)`でサーバー側の観測値と照合できます。
このメソッドは同一のジョブ ID に対してのみ呼び出し可能で、異なるジョブ ID を渡すと`ConfigurationError`を送出します。
大文字と小文字を区別せずに比較し、サイズと MD5 の両方を比較できて一致した場合は`True`を返します。
いずれか一方で比較可能な不一致を確認した場合は`False`を返します。

ジョブが`queued`などでサーバー側のメタデータが未到着の場合や、カスタムの transport が音声を最後まで読み切らなかったために MD5 が`None`の場合など、情報が不足しているときは`None`を返します。
不一致を検出した場合でも、ライブラリ側でジョブの自動再登録やキャンセルは行いません。
`False`の場合は、元の音声とサーバー応答を確認して原因を調査してください。

```python
from amivoice import AmiVoiceAsyncClient, Engine

client = AmiVoiceAsyncClient(grammar_file_names=Engine.A_GENERAL)
job = client.submit("audio.wav")
snapshot = client.get_job(job.session_id)
matched = job.matches_audio(snapshot)

if matched is False:
    print("送信音声の不一致を検出しました。")
```

### 共通設定の継承と解除

コンストラクタの認識設定は`submit()`に引き継がれ、呼び出し単位で上書きできます。
プロキシ、通信タイムアウト、接続先は`get_job()`と`wait()`でも継承・上書きできます。
各引数は省略するか`USE_CLIENT_DEFAULT`を渡すとクライアントの設定を継承し、任意の認識設定やプロキシは`None`を渡すと解除できます。
`False`や`0`は解除ではなく明示的な指定値として扱われます。
通信タイムアウトは非負整数が必要で、`None`による解除には対応しません。
接続先 URL は既存どおり`None`を拒否し、`USE_CLIENT_DEFAULT`で既定 URL を選択します。

```python
from amivoice import AmiVoiceAsyncClient, Engine

client = AmiVoiceAsyncClient(
    grammar_file_names=Engine.A_GENERAL,
    profile_id=":user01",
)

# この呼び出しだけプロファイル辞書を使用しない
job = client.submit("audio.wav", profile_id=None)
```

### ログ保存なしの設定（logging_opt_out）

非同期 HTTP 音声認識 API（v2）におけるログ保存なしの設定は、同期 HTTP や WebSocket と異なり、接続先 URL のパスを変更する方式ではありません。
`d`パラメータの`loggingOptOut`へ、`True`または`False`を送信します。

| 設定 | 動作 |
| --- | --- |
| `logging_opt_out=True` | 音声ログを保存しない |
| `logging_opt_out=False` | 音声ログを保存する |
| 省略または`None` | 値を送信せず、サーバーの既定値（ログ保存あり）に従う |

ライブラリ内部では、非同期 HTTP のエンドポイントとして常に`/v2/recognitions`を使用します。

### ジョブの状態と結果の構造

非同期ジョブの状態を表す`AsyncJobSnapshot.status`には、既知の 5 状態があります。処理待ちは`queued`、処理開始は`started`、処理中は`processing`、処理完了は`completed`、ジョブ失敗は`error`です。終端状態に達したかを表す`is_terminal`は、`completed`または`error`のときのみ`True`を返します。これらに加えて、空白や制御文字を含まない非空のラベルであれば、将来追加される未知の状態も文字列として保持します。未知の状態が返ってきた場合、`is_terminal`は`False`になり、`recognition`は`None`のまま扱われます。このとき`wait()`による待機は継続しますが、設定した`timeout`は有効です。応答に含まれる未定義の追加フィールドは、`snapshot.data`や`snapshot.raw`から参照できます。

ジョブ完了後の認識自体の成否を含む全体の成否は、`snapshot.is_error`で判定できます。将来の応答変更などで空の結果が返った場合も、型が正しい空の`text`や空配列を含む正常な完了結果であれば`AsyncRecognitionResult`として返されます。この場合、認識処理のエラー有無は`code`や`message`に基づく`is_error`で判定し、認識本文が空である点は利用側で確認します。また、失敗を示す`code`や`message`が存在する場合は、`segments`や`results`といった詳細配列が省かれていても認識失敗として扱われます。

なお、ライブラリはあらゆる未知の形式を無条件に許容するわけではありません。ジョブ ID の不一致や、`completed`時に必須となる`text`、`code`、`message`の欠落・型不正は`AsyncHttpApiError`になります。配列ではない詳細フィールド、平坦形式と入れ子形式が混在する曖昧なエンベロープ、空文字や制御文字を含む不正な`status`も同じ例外を送出します。

認識結果と生データの参照構造は以下の表のとおりです。

| フィールド | 内容 |
| --- | --- |
| `snapshot.recognition` | 完了時の`AsyncRecognitionResult`、処理中やジョブ失敗では`None` |
| `snapshot.recognition.results` | `tuple[UtteranceResult, ...]`、通常形式では区間内の結果を順番に並べる |
| `snapshot.recognition.segments` | `tuple[RecognitionResult, ...]`、区間ごとの詳細結果 |
| `snapshot.recognition.raw` / `data` | 認識結果部分の正規化した JSON 文字列と辞書 |
| `snapshot.raw` / `data` | 状態取得 API 全体の元の応答文字列と辞書 |

`compatible_with_sync=True`では、`results`にサーバーの集約結果を保持します。
この形式で区間詳細が返らない場合、`segments`は空のタプルです。
`snapshot.raw`と`data`には機密情報が含まれ得るため、無条件にログへ出力しないでください。

### 待機制御（wait）とエラーハンドリング

`wait()`メソッドは、ジョブが終端状態になるまでポーリングを行いながら呼び出し元をブロックします。

```python
from amivoice import AmiVoiceAsyncClient, AsyncJobError, AsyncJobTimeoutError

client = AmiVoiceAsyncClient()

try:
    snapshot = client.wait("job1", poll_interval=10.0, timeout=300.0)
except AsyncJobTimeoutError as error:
    # 待機がタイムアウトした場合（サーバー側のジョブはキャンセルされない）
    print(f"待機がタイムアウトしました。ジョブID: {error.session_id}")
    # 同じIDを使って後から再開可能
except AsyncJobError as error:
    # ジョブまたは認識処理が失敗した場合（raise_on_error=Trueの既定動作）
    print(f"ジョブが失敗しました: {error.message}")
    # error.snapshotで状態を調査できる。詳細本文を無条件にログへ出さない。
```

`poll_interval`は正の有限数で、単位は秒です。既定値は 10 秒です。
`timeout`も正の有限数で秒単位ですが、`None`を指定すると無制限になります。
`0`、負値、`bool`、無限大、`NaN`などの不正値は`ConfigurationError`になります。

待機上限を超えると`AsyncJobTimeoutError`を送出します。サーバーのジョブはキャンセルしません。
例外の`session_id`と、最後の状態を保持する`snapshot`から取得を再開できます。
まだ状態を取得できていない場合、`snapshot`は`None`です。

既定の transport は、待機期限にソケット通信を中断します。
ただし、DNS 名前解決、OS の接続処理、独自 transport など、ソケット中断で止められない処理には待機上限を保証できません。
`connect_timeout`と`receive_timeout`はミリ秒単位で、`0`は無制限です。

ジョブや認識の失敗は、既定の`raise_on_error=True`で`AsyncJobError`になります。
`False`では、失敗した終端状態をスナップショットとして返します。
通信失敗の`ConnectionFailedError`、HTTP エラーや不正応答の`AsyncHttpApiError`は、この設定にかかわらず送出します。

#### 原因コードと再試行の目安

ジョブ失敗や認識失敗の調査では、`snapshot.error_code`および`AsyncJobError.error_code`で単一の原因コードを参照できます。また、`snapshot.is_retryable`および`AsyncJobError.is_retryable`で再試行を検討する目安を取得できます。`AsyncJobError`のプロパティは、内部の`snapshot`へ処理を委譲します。

ジョブ失敗（`status="error"`）では、サーバーが返した`error_message`から`amineth_code`を抽出します。`error_code="o"`（認識拒否・信頼度拒否など）のときは、`is_retryable`は`False`を返します。その他の 1 文字コードのときは、`is_retryable`は`True`を返します。これは[公式ドキュメント](https://docs.amivoice.com/amivoice-api/manual/async-http-interface)のエラー状態に案内されている「しばらく待ってからの再登録を検討する目安」であり、成功の保証やライブラリによる自動再送ではありません。原因コードが含まれない場合、複数のコードが含まれる場合、1 文字以外のコードなど原因が曖昧な場合は、`error_code`と`is_retryable`はともに`None`を返します。未知の原因に対して再試行可否を断定しません。

ジョブが処理中（`status`が`queued`、`started`、`processing`のいずれか）のときは終端に達していないため、`error_code`と`is_retryable`は常に`None`を返します。

完了後の認識失敗（`status="completed"`かつ`is_error=True`）では、認識結果の`code`が 1 文字の場合に`error_code`として取得できます。信頼度拒否を示す`code="o"`のときは、`is_retryable`は`False`を返します。それ以外の認識失敗コードでは、`is_retryable`は`None`を返します。公式ドキュメントにおけるジョブ`error`状態の再試行案内を、完了後の音声認識エラー全般へ拡張しないためです。

### 通信と運用の注意点

POST の通信が途切れた場合、音声が受理されたか判別できません。
重複ジョブや二重請求を避けるため、登録（POST）の自動再送は行いません。
単発の`get_job()`でも再試行は行いません。

一方で、`wait()`による完了待機中の一時的な GET 失敗に限っては、設定に従って自動で再試行します。
再試行の対象は`ConnectionFailedError`と HTTP 429、500、502、503、504 のみです。
HTTP 200 の不正応答や HTTP 401、404 など、その他の失敗は再試行せずに例外を送出します。
既定では`max_retries=3`で連続失敗時に最大 3 回の追加 GET を行い、`0`を指定すると再試行を無効化できます。
待機時間は`retry_backoff=1.0`（秒）から試行ごとに倍増し、最大 30 秒で頭打ちになります。
状態を取得できた場合、連続失敗の回数はリセットされます。
再試行のバックオフ待機も全体の`timeout`に含まれ、待機上限に達したときは直近に取得できた最後の`snapshot`を保持して`AsyncJobTimeoutError`を送出します。
なお、この再試行は待機中の状態確認（GET）だけを対象としており、ジョブ自体を再登録するものではありません。
`content_id`はデータを紐付ける文字列であり、同じ値の再使用によって重複登録を防ぐことはできません。

結果は処理終了後 7 日間保存されます。存在しない ID や期限切れの結果は HTTP 404 になります。
ただし、別ユーザーのジョブにアクセスした場合などにも 404 が返るため、期限切れとは断定しません。
HTTP エラーや不正応答、受付拒否が起きた場合は`AsyncHttpApiError`を送出します。例外の`status_code`、`body`、`raw_body`に加え、JSON オブジェクトの応答であれば`data`（辞書または`None`）、サーバーが返したエラー情報は`code`と`api_message`（文字列または`None`）から取得できます。ライブラリ側で本文を解析するため、利用側での独自の JSON 再解析は不要です。`message`や`str(error)`は機密情報を含まない安全な一般説明を返します。生レスポンスである`body`や`raw_body`、`data`には機密情報が含まれ得るため、無条件にログへ出力しないでください。
また、認証エラー時は公開例外`AsyncHttpAuthenticationError`を送出します。この例外は`AsyncHttpApiError`と`AuthenticationError`の両方を継承しており、HTTP 401 応答だけでなく、受付時（HTTP 200）の`code="-"`でも発生します。そのため、既存の`AuthenticationError`ハンドラと非同期固有の`AsyncHttpApiError`ハンドラのどちらでも捕捉できます。

このクライアントでは、話者ダイアライゼーションと感情分析の設定はまだ提供していません。
`SegmenterProperties`の話者設定は、明示的な`False`も含めて非同期 HTTP では拒否します。
発話検出と言語識別は利用できます。
同期 HTTP 用のルール設定、WebSocket 用の途中結果間隔と発話開始待ち設定も対応していません。

## 使用例CLI

`examples/`の各プログラムは、現在の公開 API を使用します。認証は環境変数`AMIVOICE_API_KEY`から読み取るため、キーを引数へ渡しません。リポジトリのルートから実行してください。

```bash
# HTTP・簡易版
uv run examples/hrp_simple_tester.py audio/test.wav

# WebSocket・簡易版
uv run examples/wrp_simple_tester.py audio/test.wav --codec 16K

# HTTP・詳細版では複数ファイルを指定できる
uv run examples/hrp_tester.py audio/test.wav audio/test2.wav \
  --engine=-a-general --codec 16K --selected-channel 0

# WebSocket・詳細版では送信単位と途中イベントの表示を指定できる
uv run examples/wrp_tester.py audio/test.wav audio/test2.wav \
  --engine=-a-general --codec 16K --chunk-size 4096 --show-events

# 非同期HTTP・ジョブの登録（アップロードと受付後にジョブIDを表示）
uv run examples/async_http_tester.py submit audio/test.wav --engine=-a-general

# 非同期HTTP・状態と認識結果の取得
uv run examples/async_http_tester.py status <session_id>

# 非同期HTTP・ジョブ完了の待機
uv run examples/async_http_tester.py wait <session_id> --poll-interval 10.0 --timeout 300.0
```

`--engine`の値は先頭が`-`のため、`--engine=-a-general`のように`=`で指定する方法を推奨します。
既定のエンジンは`-a-general`です。同期 HTTP・WebSocket CLI の音声フォーマットの既定値は`16K`です。
非同期 HTTP CLI の`--codec`は省略でき、ヘッダなし音声では明示してください。

非同期 HTTP CLI（`examples/async_http_tester.py`）では、共通引数（`--url`、`--proxy-server-name`、`--connect-timeout`、`--receive-timeout`）をサブコマンド（`submit`、`status`、`wait`）の前に指定します。

```bash
uv run examples/async_http_tester.py --connect-timeout 10000 --receive-timeout 30000 submit audio/test.wav
```

### CLIのオプション

簡易版と詳細版は、次の共通オプションを使用できます。

| オプション | 内容 |
| --- | --- |
| `--engine=...` | 接続エンジン名 |
| `--codec` | 公式の音声フォーマット名 |
| `--url` | 接続先 URL の上書き |
| `--logging-opt-out` | ログ保存なしのエンドポイントを使用 |
| `--connect-timeout` | 接続のタイムアウト。ミリ秒、CLI の既定値は`10000` |
| `--receive-timeout` | 受信のタイムアウト。ミリ秒、CLI の既定値は`30000` |

詳細版は複数の音声ファイルを位置引数で受け付け、次の設定を追加できます。

| オプション | 内容 |
| --- | --- |
| `--profile-id` | 辞書の参照。例は`:user01` |
| `--profile-words` | セッション単語の設定文字列 |
| `--segmenter-properties` | 発話検出、話者ダイアライゼーション、言語識別の設定文字列 |
| `--confidence-level` | 信頼度しきい値 |
| `--keep-filler-token` / `--no-keep-filler-token` | フィラーの保持・削除。省略時は値を送信しない |
| `--billing-key` | 使用量集計タグ |
| `--recognition-timeout` | 認識完了までのタイムアウト。ミリ秒 |
| `--max-decoding-time` | 認識処理時間の上限。ミリ秒 |
| `--max-response-time` | 音声時間に加える処理時間の上限。ミリ秒 |
| `--max-decoding-rate` | 音声時間に対する処理時間の上限倍率 |
| `--target-response-time` | 暫定結果の目標応答時間。ミリ秒 |
| `--target-decoding-rate` | 暫定結果の目標倍率 |

HTTP の詳細版だけで使える設定は`--selected-channel`です。CLI では単一チャネルを整数で指定します。複数チャネルを混合するタプルは、Python API から指定してください。

WebSocket の詳細版は`--result-updated-interval`、`--no-input-timeout`をミリ秒で指定できます。`--show-events`は途中結果と発話境界も表示するオプションです。WebSocket の簡易版と詳細版には`--chunk-size`があり、送信するバイト数を正の整数で指定します。既定値は`4096`です。

`--url`を明示して`--logging-opt-out`を使う場合は、HTTP なら`/v1/nolog/recognize`、WebSocket なら`/v1/nolog/`のパスが必要です。指定した URL を自動でログ保存なしのパスへ変更しません。

```bash
uv run examples/hrp_tester.py audio/test.wav \
  --logging-opt-out --url https://acp-api.amivoice.com/v1/nolog/recognize

uv run examples/wrp_tester.py audio/test.wav --codec 16K \
  --logging-opt-out --url wss://acp-api.amivoice.com/v1/nolog/
```

`--help`は API キーなしで実行でき、通信もしません。

```bash
uv run examples/hrp_tester.py --help
uv run examples/wrp_tester.py --help
uv run examples/async_http_tester.py --help
uv run examples/async_http_tester.py submit --help
uv run examples/async_http_tester.py status --help
uv run examples/async_http_tester.py wait --help
```

同期 HTTP と WebSocket の終了コードは成功が`0`、認識・通信・ファイル読み込みなどの失敗が`1`です。
引数の構文や型が不正な場合は、`argparse`が`2`で終了します。
数値の範囲や URL とログ保存設定の組み合わせなど、クライアントが検出する設定エラーは`1`です。

非同期 HTTP CLI の終了コードは以下のとおりです。

| 終了コード | 内容 |
| --- | --- |
| `0` | 操作成功。`status`では処理中の状態を取得した場合も成功 |
| `1` | 認識・通信・ジョブ・設定・ファイルなどのエラー |
| `2` | argparse が検出した引数構文・型のエラー |
| `3` | `wait()`の待機タイムアウト。サーバーのジョブは継続し、同じ ID で再開できる |
