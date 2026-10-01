# AmiVoice Python クライアントで HTTP・WebSocket 認識を利用する

## インストール

```bash
uv sync
```

アプリケーションから配布パッケージを利用する場合は、次のコマンドを実行します。

```bash
pip install amivoice-api-client
```

## 認証

API キーは環境変数で指定できます。

```bash
export AMIVOICE_API_KEY="your-api-key"
```

または、`AmiVoiceClient`のコンストラクタへ渡します。

```python
from amivoice import AmiVoiceClient

client = AmiVoiceClient(api_key="your-api-key")
```

### APIキーの発行

`ApiKeyIssuanceClient`を使うと、有効期限や接続元 IP アドレス制限を付けた API キーを発行できます。API キー発行機能付きの API キーを Bearer 認証で使用します。発行用の API キーはサーバー側で管理してください。

```python
from datetime import timedelta

from amivoice import ApiKeyIssuanceClient

api_key_issuance_client = ApiKeyIssuanceClient(api_key="api-key-with-issuance-permission")
issued_api_key = api_key_issuance_client.issue(
    expires_in=timedelta(hours=2),
    allowed_ip_addresses=("203.0.113.0/24",),
)
```

API キーをコンストラクタへ渡さない場合は、`AMIVOICE_ISSUER_API_KEY`の環境変数を使用します。音声認識用の`AMIVOICE_API_KEY`は使用しません。`expires_in`にはミリ秒の整数、`2h`などの API 形式の文字列、`timedelta`を指定できます。省略時の有効期限は 30 秒です。整数と`timedelta`は 1 ミリ秒以上を指定してください。1 ミリ秒未満の`timedelta`の端数は切り捨てます。
`allowed_ip_addresses`には、IPv4 アドレスまたは IPv4 CIDR を文字列、`ipaddress.IPv4Address`、`ipaddress.IPv4Network`で指定します。IPv6 アドレスや空の一覧を指定すると`ConfigurationError`が送出されます。接続元 IP アドレスを制限しない場合は`allowed_ip_addresses`を省略してください。

## HTTP音声認識

```python
from amivoice import AmiVoiceClient, Codec, Engine

client = AmiVoiceClient(
    grammar_file_names=Engine.A_GENERAL,
    codec=Codec.HEADER_16K,
)
result = client.transcribe("audio.wav")
print(result.text)
```

`Codec`は音声フォーマット名の定数です。`Codec.HEADER_16K`は`"16K"`と同じ値として扱われ、`Codec("lsb16k")`のように大文字小文字を区別せずに解決できます。文字列が有効な音声フォーマット名かを判定するときは、`"lsb16k" in Codec`ではなく`Codec(value)`を呼び、`ValueError`を捕捉してください。`in`演算子の結果は Python のバージョンによって異なります。音声ファイルのヘッダにフォーマット情報がある場合は、HTTP 音声認識では`codec`の指定を省略できます。ヘッダ付き音声で明示的に指定する場合は、8kHz または 11.025kHz なら`Codec.HEADER_8K`、16kHz 以上なら`Codec.HEADER_16K`を使用してください。ヘッダなし PCM では`Codec.LSB16K`や`Codec.MSB16K`など、エンディアンとサンプリングレートに合った定数を指定します。ヘッダなし音声に`Codec.HEADER_8K`や`Codec.HEADER_16K`を指定すると、ヘッダの読み込みに失敗して`LSB16K`として扱われます。詳細は[AmiVoice APIの音声フォーマット](https://docs.amivoice.com/amivoice-api/manual/audio-format)を参照してください。

`Engine`は接続エンジン名の定数です。定数名は、公式ドキュメントの接続エンジン名から先頭の`-`を除き、`-`を`_`に置き換えて大文字にしたものです（例：`-a2-ja-general`は`Engine.A2_JA_GENERAL`）。会話用の汎用エンジンは`Engine.A_GENERAL`、音声入力用は`Engine.A_GENERAL_INPUT`、AmiVoice API Private のルールエンジンは`Engine.A_RULE_INPUT_PRIVATE`で指定できます。グラマファイルを使うルールグラマは`Engine.A_RULE_INPUT_PRIVATE`専用で、ほかのエンジンとは組み合わせられません（[ルールグラマ](https://docs.amivoice.com/amivoice-api/manual/rule-grammar)）。

エンジンごとに対応するサンプリングレートとインタフェースが異なるため、`Engine`と`Codec`を組み合わせるときは[AmiVoice APIの音声認識エンジン一覧](https://docs.amivoice.com/amivoice-api/manual/engines#list)を確認してください。特に次の制約があります。

- すべてのエンジンは 16kHz に対応するが、8kHz または 11.025kHz に対応するのは一部のエンジンだけである。例えば、`Engine.A_GENERAL`は 8kHz と 16kHz に対応し、`Engine.A_MEDICAL`と`Engine.A_RULE_INPUT_PRIVATE`は 16kHz に対応する。
- `Engine.A_NAME_INPUT_PRIVATE`、`Engine.A_ADDRESS_INPUT_PRIVATE`、`Engine.A_RULE_INPUT_PRIVATE`は AmiVoice API Private 向けのエンジンで、非同期 HTTP インタフェースでは利用できない。

`Engine`と`Codec`のすべての組み合わせが有効とは限らないため、利用するインタフェース、エンジン、音声のサンプリングレートの対応を公式一覧で確認してください。

`transcribe()`には、ファイルパス、`pathlib.Path`、`bytes`、バイナリファイルオブジェクトを渡せます。

### ログ保存なしの認識

ログを保存せずに認識する場合は、`logging_opt_out=True`を指定します。同期 HTTP と WebSocket の既定エンドポイントが、それぞれログ保存なしのエンドポイントへ切り替わります。

```python
from amivoice import AmiVoiceClient

client = AmiVoiceClient(logging_opt_out=True)
result = client.transcribe("audio.wav")

with client.stream() as session:
    session.write(audio_chunk)
    session.end()
```

`transcribe()`や`stream()`の呼び出し時にも`logging_opt_out`を指定できます。

`http_api_url`、`ws_api_url`、`api_url`で URL を明示した場合、その URL は`logging_opt_out`で書き換えられません。`logging_opt_out`が有効なときに明示した URL のパスがログ保存なしのエンドポイントと一致しない場合は、リクエストを送信する前に`ConfigurationError`を送出します。既定と同じ URL を明示した場合も同じです。

| インタフェース | ログ保存なしのパス | 例 |
| --- | --- | --- |
| 同期 HTTP | `/v1/nolog/recognize` | `https://acp-api.amivoice.com/v1/nolog/recognize` |
| WebSocket | `/v1/nolog/` | `wss://acp-api.amivoice.com/v1/nolog/` |

WebSocket の URL は末尾の`/`まで必要です。`wss://acp-api.amivoice.com/v1/nolog`のように`/`がない URL は、AmiVoice API ではログ保存ありになります。詳しくは[ログ保存](https://docs.amivoice.com/amivoice-api/manual/log-retention)を参照してください。

AWS PrivateLink で接続する場合は、ホスト名だけを`acp-api-private.amivoice.com`へ変えた URL を指定します。

```python
client = AmiVoiceClient(
    logging_opt_out=True,
    http_api_url="https://acp-api-private.amivoice.com/v1/nolog/recognize",
    ws_api_url="wss://acp-api-private.amivoice.com/v1/nolog/",
)
```

### マルチチャネル音声のチャネル選択

複数チャネルの音声を同期 HTTP で認識する場合は、`selected_channel`で認識対象を指定できます。単一チャネルは整数、複数チャネルの混合平均は`(開始チャネル, 終了チャネル)`のタプルで指定します。チャネル番号は`0`から始まります。`(0, 0)`のように開始と終了が同じタプルは`ConfigurationError`になります。単一チャネルは整数で指定してください。

```python
from amivoice import AmiVoiceClient

client = AmiVoiceClient(selected_channel=(0, 1))
result = client.transcribe("stereo.wav")
```

複数チャネルに対応するのは、Wave、Ogg、FLAC などファイルのヘッダに音声フォーマットが含まれる「ヘッダあり」の音声だけです。`codec="LSB16K"`のように音声フォーマットを指定して送る「ヘッダなし」の PCM データは 1 チャネルにしか対応しないため、`selected_channel`で別のチャネルを選んだり、複数チャネルを混合したりできません。詳細は公式マニュアルの[音声フォーマット](https://docs.amivoice.com/amivoice-api/manual/audio-format#channels)を参照してください。

API の`audioFilterProperties`を直接指定する場合は、`audio_filter_properties`を使用します。`selected_channel`と同時には指定できません。チャネル選択は同期 HTTP の`transcribe()`専用で、WebSocket の`stream()`では利用できません。コンストラクタで`selected_channel`または`audio_filter_properties`を指定したクライアントで`stream()`を呼び出すと、設定を無視せずに`ConfigurationError`を送出します。WebSocket で認識する場合は、音声フィルタを指定しないクライアントを使用してください。WebSocket では 1 チャネル目だけが認識対象になります。

### 型付き認識結果

`RecognitionResult.results`から発話区間、単語、信頼度、時刻、話者ラベル、言語ラベルを型付きで参照できます。

```python
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

`spoken`、`confidence`、`starttime`、`endtime`、`label`、`language`など、エンジンや設定により省略されるフィールドは`None`になります。`RecognitionResult.raw`、`data`、`text`、`is_error`、`session_id`も引き続き利用できます。

### セッション単語登録

認識セッションだけで有効にする単語は、`ProfileWord`のシーケンスで指定できます。ハイブリッドエンジンでは`spoken`を必須とし、クラスを指定する場合は`classname`を追加します。End to End エンジンでは`alternative_written`と`biasing`を指定します。従来どおり、ワイヤー形式の文字列も指定できます。

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
```

`ProfileWord`の値には空白や`|`を含めないでください。表記（`written`）には半角コロン（`:`）も使えません。これらの文字を含む`ProfileWord`を生成または変換すると、`ConfigurationError`が送出されます。複数の単語は、ライブラリが`|`で連結して API 送信用の形式へ変換します。

### セグメンター設定

発話検出、話者ダイアライゼーション、言語識別は`SegmenterProperties`で指定できます。次の設定は同期 HTTP と WebSocket で利用できます。

```python
from amivoice import AmiVoiceClient, SegmenterProperties

client = AmiVoiceClient(
    segmenter=SegmenterProperties(
        speaker_diarization=True,
        diarizer_alpha="1e-20",
        languages=("ja", "en"),
    ),
)
result = client.transcribe("audio.wav")
```

`segmenter`と既存の`segmenter_properties`は同時に指定できません。`languages`には`ja`、`en`、`zh`、`ko`、`th`を指定できます。言語識別結果と音声認識結果の言語を比較してください。`useLid`を利用する場合は、両者の言語が異なるケースもあります。

### 信頼度しきい値

発話区間の認識結果を信頼度しきい値でリジェクトする場合は、`confidence_level`を指定します。同期 HTTP と WebSocket の両方で利用でき、指定可能な範囲は`0.0`以上`1.0`以下です。

```python
from amivoice import AmiVoiceClient

client = AmiVoiceClient(confidence_level=0.3)
result = client.transcribe("audio.wav")
```

指定した値未満の発話区間はサーバー側でリジェクトされます。リジェクトされた結果はレスポンスコードが`o`となり、認識結果として成功扱いですが、`text`が空になることがあります。`1.0`を指定すると、ほとんどの認識結果がリジェクトされるため、値は用途に合わせて設定してください。

`confidence_level`を指定しない場合はパラメータを送信せず、サーバー側のデフォルト値に委ねます。公式仕様上のデフォルト値は`0.1`ですが、予告なく変更される可能性があります。

### 処理時間とレスポンスの制御

処理時間制御パラメータは、認識処理を途中で打ち切ったり、処理速度と認識率を調整したりする上級者向けの設定です。値を小さくしすぎると、認識結果が途中で終了する場合があります。コンストラクタ、`transcribe()`、`stream()`、モジュールレベルの`transcribe()`で指定できます。

リアルタイム録音の WebSocket 認識では、次のように指定します。

```python
from amivoice import AmiVoiceClient

client = AmiVoiceClient(
    max_decoding_time=30_000,
    max_response_time=5_000,
    target_response_time=1_000,
)

with client.stream() as session:
    session.write(audio_chunk)
    session.end()
```

バッチ音声の HTTP 認識では、処理時間を音声時間に対する倍率で制御できます。

```python
client = AmiVoiceClient(
    max_decoding_time=30_000,
    max_decoding_rate=2.0,
    target_decoding_rate=1.5,
)
result = client.transcribe("audio.wav")
```

`max_decoding_time`は認識処理時間の上限をミリ秒で指定します。`max_response_time`は音声時間に加える処理時間の上限をミリ秒で指定し、`target_response_time`は暫定結果の目標応答時間をミリ秒で指定します。後者 2 つはリアルタイム録音時のみ有効です。

`max_decoding_rate`は音声時間に対する認識処理時間の上限倍率を指定し、`target_decoding_rate`は暫定結果の目標倍率を指定します。これらはバッチ音声のみ有効です。時間系の`0`は無効を表し、レート系の負値も無効指定として利用できます。公式仕様のデフォルト値は、時間系が`0`、レート系が`-1`です。未指定の場合はパラメータを送信せず、サーバー側のデフォルト値に委ねます。

### ルールグラマ

AmiVoice API Private の「音声入力_ルール」エンジン（`Engine.A_RULE_INPUT_PRIVATE`）を使う場合は、`build_grammar_file_names()`で接続エンジン名とグラマ指定を組み立てます。グラマファイルを使えるのはこのエンジンだけで、`build_grammar_file_names()`も既定でこのエンジンを使います。この機能は通常の AmiVoice API 環境では利用できません。

グラマ本文を直接指定するときは、`encode_grammar()`で GZIP 圧縮と Base64 エンコードを行います。URL とエンコード済み本文は混在でき、ヘルパーは URL エンコードを追加しません。

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
```

通常のグラマ指定では`|`で連結します。前のグラマで認識に失敗した場合は、次のグラマへフォールバックするため`||`で連結します。`complete_timeout`は確定待ちタイムアウトをミリ秒で指定します。`wildcard_model_penalty`は`<GARBAGE>`の認識されやすさを調整し、目安は`2.0`から`6.0`です。Private 環境のデフォルト値は異なることがあります。目安の範囲外も指定できます。ただし、負値は指定できません。

「音声入力_ルール」エンジンは非同期 HTTP では利用できません。JSGF や SRGS の文法検証は行わないため、グラマのフォーマットと書き方は[グラマファイルの公式ドキュメント](https://docs.amivoice.com/amivoice-api/manual/grammar-file)を確認してください。誤ったグラマを指定した場合はサーバー側でエラーになります。

### 使用量集計タグ

使用量をユーザーやアプリケーション単位で集計する場合は、`billing_key`を指定します。同期 HTTP と WebSocket の両方で利用できます。

```python
from amivoice import AmiVoiceClient

client = AmiVoiceClient(billing_key="user01")
result = client.transcribe("audio.wav")

with client.stream() as session:
    session.write(audio_chunk)
    session.end()
```

`billing_key`は内部で`extension`の専用 JSON 形式に変換されます。既存の`extension`と同時には指定できません。公開 API の`extension`パラメータへ直接渡す JSON 文字列を生成する場合は、`build_billing_extension()`を使用します（`billing_key`と同時に指定しないでください）。

```python
from amivoice import AmiVoiceClient, build_billing_extension

client = AmiVoiceClient(
    extension=build_billing_extension("user01"),
)
result = client.transcribe("audio.wav")
```

使用量の確認は、AmiVoice Cloud Platform のマイページにある発話量 CSV を利用してください。

## ユーザー辞書管理

ユーザー辞書登録 API を利用すると、プロファイルへ単語を登録・取得・削除できます。API キーは環境変数 `AMIVOICE_API_KEY` から解決されますが、`UserDictionaryClient` のコンストラクタへ渡すこともできます。

```python
from amivoice import ProfileWord, UserDictionaryClient

# 登録は単語の追加ではなく、指定した一覧による全件置換
user_dictionary = UserDictionaryClient()
user_dictionary.register_words(
    "-a-general",
    "user01",
    (
        ProfileWord(written="AmiVoice", spoken="あみぼいす", classname="固有名詞"),
        ProfileWord(written="WWW", spoken="とりぷるだぶる"),
    ),
    sampling_rate="16k",
)

words = user_dictionary.get_words("-a-general", "user01", sampling_rate="16k")
for word in words:
    print(word.written, word.spoken, word.classname)

# 空の一覧を登録するとプロファイルの単語を全件削除
user_dictionary.clear_words("-a-general", "user01", sampling_rate="16k")

# ハイブリッドエンジンで利用できるクラス名を取得
classnames = user_dictionary.list_classnames("-a-general")
```

End to End エンジンの単語強調では、`alternative_written` と `biasing` を指定します。`biasing` は `0.0` 以上 `1.0` 以下です。数値のほか、`"0.5"` のような小数表記の文字列も指定できます。`"1e-5"` のような指数表記の文字列は指定できません。

```python
user_dictionary.register_words(
    "-a-e2e",
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

ハイブリッドエンジンでは 8k 用と 16k 用のプロファイルが分かれるため、音声のサンプリングレートに合わせて `sampling_rate="8k"` または `sampling_rate="16k"` を指定します。省略時は 16k 用のプロファイルが対象です。登録時は既存の単語を保持したい場合も、保持する単語を含む全件を渡してください。

ユーザー辞書はアプリケーションのデータベースなどで保持し、バックアップしてください。プロファイルをマスターデータにせず、API のプロファイルを更新する前にアプリケーションで全件を管理することが推奨されています。

登録した単語を音声認識で利用する場合は、登録時と同じ接続エンジン名を指定し、`profile_id` の先頭に `:` を付けます。`:` 付きのプロファイル ID は、プロファイルを参照だけする指定です。`:` を付けないと、セッション終了時にプロファイルを上書きする場合があります（[プロファイルの利用](https://docs.amivoice.com/amivoice-api/manual/user-dictionary-use-profile)）。ライブラリは値を書き換えず、先頭に `:` がない場合は `UserWarning` を出します。

```python
from amivoice import AmiVoiceClient, Codec, Engine

recognition_client = AmiVoiceClient(
    grammar_file_names=Engine.A_GENERAL,
    codec=Codec.HEADER_16K,
    profile_id=":user01",
)
result = recognition_client.transcribe("audio.wav")
```

## WebSocketストリーミング認識

```python
from amivoice import AmiVoiceClient, Codec, Engine

client = AmiVoiceClient(grammar_file_names=Engine.A_GENERAL, codec=Codec.HEADER_16K)

with client.stream() as session:
    session.write(audio_chunk)
    for event in session.poll():
        print(event.text)
    session.end()
    for event in session.events():
        print(event.text)
```

音声チャンクの送信には `write()` を使い、キューへ届いたイベントの随時取得には `poll()` を使用します。音声の送信を終えたら `end()` を呼び出します。`end()` は終了の確認応答と残りの確定認識結果を待ち受けます。呼び出し後もキューに残る確定イベントなどは、`session.events()` で終了まで順次取り出せます。

サーバーから届くイベントは `session.poll()` や `session.events()` から受信順に取得できます。サーバーが発話区間を検出して音声認識処理を始めると、`type="recognition_started"` のイベントが届きます。このイベントは検出した区間の認識処理開始を表すもので、セッション自体の開始確認（`s`）や発話区間の開始（`S`）とは異なります。追加の時刻情報は持たず、`text` は空、`result`、`utterance`、`notification` は `None` です。発話終了イベントの前に届く場合もあれば後に届く場合もありますが、クライアントの終了待機などの状態制御には影響しません。

```python
for event in session.poll():
    if event.type == "recognition_started":
        print("認識処理を開始しました")
    elif event.is_final:
        print(f"確定結果: {event.text}")
```

### タイムアウト

接続と受信のタイムアウトはミリ秒単位で指定し、ライブラリの既定値はいずれも 0（無制限）です。一方で、`examples` 配下の詳細 CLI スクリプトでは接続タイムアウトの初期値に 5,000 ミリ秒を採用しています。

ストリーミング認識では、`receive_timeout` に 0 より大きい値を指定すると、セッション開始確認や終了確認の待ち時間にもその値が適用されます。`receive_timeout` が 0 の場合でも、セッション開始確認および `end()` の待機時間には既定値として 60 秒が適用されます。

終了処理を明示的に制御する場合は、`end(timeout=...)` に秒単位で上限を指定します。指定した制限時間内に、終了確認と未受信の確定認識結果の双方が揃うまで待機します。

### 例外処理

音声認識の処理中に問題が発生した場合、ライブラリは状況に応じた例外を送出します。

認証に失敗した場合は `AuthenticationError` が送出されます。HTTP 401 や 403 の応答、および WebSocket ハンドシェイク時の 401 や 403 応答がこれに該当します。

接続先に到達できない場合やハンドシェイクが成立しない場合は `ConnectionFailedError` が送出されます。

通信切断やサーバーからの異常応答などの受信エラーは、ストリーミング認識セッションの `write()`、`end()`、`events()`、`poll()` の各呼び出しに `RecognitionError` として伝播します。

## 低レベルAPIの廃止について

旧バージョンで提供されていた `com.amivoice` パッケージ（`Hrp`、`Wrp` など）および低レベル API は廃止されました。すべての音声認識処理には `AmiVoiceClient`、`transcribe()`、`stream()` などの公開 API を使用してください。

## サンプル

公開 API を使用したサンプルプログラムを `examples/` に用意しています。

サンプルの実行には AmiVoice API キーと音声ファイルが必要です。API キーを CLI 引数へ直接渡す方法は推奨されません。環境変数 `AMIVOICE_API_KEY` を設定して実行してください。

```bash
export AMIVOICE_API_KEY="your-api-key"

# HTTP・簡易版（URL 音声ファイル コーデック 接続エンジン名 [APIキー]）
# APIキー引数を省略すると環境変数 AMIVOICE_API_KEY を使用します
uv run examples/hrp_simple_tester.py \
  https://acp-api.amivoice.com/v1/recognize \
  audio/test.wav 16K -a-general

# WebSocket・簡易版（URL 音声ファイル コーデック 接続エンジン名 [APIキー]）
uv run examples/wrp_simple_tester.py \
  wss://acp-api.amivoice.com/v1/ \
  audio/test.wav 16K -a-general

# HTTP・詳細版（URL 音声ファイル一覧 オプション）
uv run examples/hrp_tester.py \
  https://acp-api.amivoice.com/v1/recognize \
  audio/test.wav \
  --grammar-file-names=-a-general \
  --codec 16K

# WebSocket・詳細版（URL 音声ファイル一覧 オプション）
uv run examples/wrp_tester.py \
  wss://acp-api.amivoice.com/v1/ \
  audio/test.wav \
  --grammar-file-names=-a-general \
  --codec 16K
```

利用可能なすべてのコマンドラインオプションや引数の詳細は、各スクリプトに `--help` を指定して確認してください。

```bash
uv run examples/hrp_tester.py --help
uv run examples/wrp_tester.py --help
```
