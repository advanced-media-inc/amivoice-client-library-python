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
