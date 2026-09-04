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
