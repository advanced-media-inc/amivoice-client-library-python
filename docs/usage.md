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

## HTTP音声認識

```python
from amivoice import AmiVoiceClient

client = AmiVoiceClient(
    grammar_file_names="-a-general",
    codec="16K",
)
result = client.transcribe("audio.wav")
print(result.text)
```

`transcribe()`には、ファイルパス、`pathlib.Path`、`bytes`、バイナリファイルオブジェクトを渡せます。

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
from amivoice import AmiVoiceClient, ProfileWord

client = AmiVoiceClient(
    grammar_file_names="-a-general",
    profile_words=(
        ProfileWord(written="AmiVoice", spoken="あみぼいす", classname="固有名詞"),
        ProfileWord(written="WWW", spoken="とりぷるだぶる"),
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

AmiVoice API Private の「音声入力_ルール」エンジンを使う場合は、`build_grammar_file_names()`で接続エンジン名とグラマ指定を組み立てます。この機能は通常の AmiVoice API 環境では利用できません。

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

`billing_key`は内部で`extension`の専用 JSON 形式に変換されます。既存の`extension`と同時には指定できません。低レベル API に直接渡す場合は、`build_billing_extension()`を使用できます。

```python
from amivoice import build_billing_extension
from com.amivoice.hrp.Hrp import Hrp

hrp = Hrp.construct()
hrp.setExtension(build_billing_extension("user01"))
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

登録した単語を音声認識で利用する場合は、登録時と同じ接続エンジン名を指定し、`profile_id` の先頭に `:` を付けます。

```python
from amivoice import AmiVoiceClient

recognition_client = AmiVoiceClient(
    grammar_file_names="-a-general",
    codec="16K",
    profile_id=":user01",
)
result = recognition_client.transcribe("audio.wav")
```

## WebSocketストリーミング認識

```python
from amivoice import AmiVoiceClient

client = AmiVoiceClient(grammar_file_names="-a-general", codec="16K")

with client.stream() as session:
    session.write(audio_chunk)
    for event in session.poll():
        print(event.text)
    session.end()
```

## 低レベルAPI

既存の低レベル API を利用する場合は、次の import パスを使用できます。

```python
from com.amivoice.hrp.Hrp import Hrp
from com.amivoice.wrp.Wrp import Wrp
```

高レベル API の利用を優先し、プロトコルを直接制御する必要がある場合に低レベル API を使用してください。

## サンプル

低レベル API を使用したサンプルプログラムは`examples/`にあります。

サンプルの実行には、AmiVoice API キーと音声ファイルが必要です。API キーは環境変数に設定し、各サンプルの引数として渡します。

```bash
export AMIVOICE_API_KEY="your-api-key"

# HTTP・簡易版
uv run examples/hrp_simple_tester.py \
  https://acp-api.amivoice.com/v1/recognize \
  audio/test.wav 16K -a-general "$AMIVOICE_API_KEY"

# WebSocket・簡易版
uv run examples/wrp_simple_tester.py \
  wss://acp-api.amivoice.com/v1/ \
  audio/test.wav 16K -a-general "$AMIVOICE_API_KEY"

# HTTP・詳細版
uv run examples/hrp_tester.py \
  g=-a-general c=16K ou="$AMIVOICE_API_KEY" \
  https://acp-api.amivoice.com/v1/recognize audio/test.wav

# WebSocket・詳細版
uv run examples/wrp_tester.py \
  g=-a-general c=16K ou="$AMIVOICE_API_KEY" \
  wss://acp-api.amivoice.com/v1/ audio/test.wav
```
