# 同期 HTTP 音声認識ガイド

このガイドでは、`AmiVoiceClient.transcribe()` とモジュールレベルの `transcribe()` を使った同期 HTTP 音声認識について説明します。

- インストール、認証、共通の `RecognitionSettings`、ユーザー辞書管理: [共通利用ガイド](./usage.md)
- 長時間音声やバッチ処理: [非同期 HTTP 音声認識（v2）ガイド](./usage-async-http.md)
- リアルタイム・ストリーミング認識: [WebSocket ストリーミング認識ガイド](./usage-websocket.md)

## 基本的な使い方

`RecognitionSettings.grammar_file_names` には接続エンジン名を指定します。音声フォーマットや接続エンジンの定数は[音声フォーマットと接続エンジン](./usage.md#音声フォーマットと接続エンジン)を参照してください。
共通の認識設定はコンストラクタの `settings` へ渡し、`transcribe()` の `settings` で呼び出しごとに上書きできます。継承と解除のルールは[クライアント設定の継承と解除（USE_CLIENT_DEFAULT）](./usage.md#クライアント設定の継承と解除use_client_default)を参照してください。

```python
from amivoice import AmiVoiceClient, Codec, Engine, RecognitionSettings

client = AmiVoiceClient(
    settings=RecognitionSettings(
        grammar_file_names=Engine.A_GENERAL,
        codec=Codec.HEADER_16K,
    ),
)
result = client.transcribe("audio.wav")
print(result.text)
```

`transcribe()` にはファイルパス、`pathlib.Path`、`bytes`、バイナリファイルオブジェクトを渡せます。入力音声は 16,777,215 バイト以下である必要があります。

モジュールレベルの `transcribe()` でも同期 HTTP で認識できます。

```python
from amivoice import Engine, RecognitionSettings, transcribe

result = transcribe("audio.wav", settings=RecognitionSettings(grammar_file_names=Engine.A_GENERAL))
print(result.text)
```

## 認識の成功と失敗

HTTP ステータスが 200 でも、認識に成功したとは限りません。ライブラリは本文の `code` と `message` で成否を判定します。成功結果は両方が空文字列で、`text` が空ではありません。`code` または `message` が空でなければ、`RecognitionResult.is_error` は `True` になります。信頼度による拒否を示す `code="o"` も音声認識は行っていません。

`transcribe()` は既定の `raise_on_error=True` で、認識失敗時に `RecognitionError` を送出します。失敗した結果をアプリケーションで調べる場合は、`raise_on_error=False` を指定します。

```python
from amivoice import AmiVoiceClient, Engine, RecognitionSettings

client = AmiVoiceClient(settings=RecognitionSettings(grammar_file_names=Engine.A_GENERAL))
result = client.transcribe("audio.wav", raise_on_error=False)
if result.is_error:
    print("認識失敗:", result.data["code"])
else:
    print(result.text)
```

`raise_on_error=False` は、通信障害や不正なレスポンスまで成功結果に変える設定ではありません。通信に失敗した場合は `ConnectionFailedError`、結果の形式が不正な場合などは `RecognitionError` を送出します。

## 型付き認識結果

`RecognitionResult.results` から発話区間と単語を参照できます。信頼度、時刻、話者ラベル、言語ラベルも型付きで取得できます。

```python
from amivoice import AmiVoiceClient, Engine, RecognitionSettings

client = AmiVoiceClient(settings=RecognitionSettings(grammar_file_names=Engine.A_GENERAL))
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

`spoken`、`confidence`、`starttime`、`endtime`、`label`、`language` など、エンジンや設定によって省略されるフィールドは `None` になります。`raw` には受信した JSON 文字列、`data` にはその辞書、`text` には認識テキストが入ります。`is_error`、`session_id` も公開フィールドです。

## 話者ダイアライゼーションの設定

同期 HTTP の話者ダイアライゼーションは、`SegmenterProperties` の `speaker_diarization`、`diarizer_alpha`、`diarizer_transition_bias` で設定します。発話検出や言語識別とあわせて指定できます。単語ごとの話者ラベルは、認識結果の `token.label` から参照できます。

```python
from amivoice import AmiVoiceClient, Engine, RecognitionSettings, SegmenterProperties

client = AmiVoiceClient(
    settings=RecognitionSettings(
        grammar_file_names=Engine.A_GENERAL,
        segmenter=SegmenterProperties(
            speaker_diarization=True,
            diarizer_alpha="1e-20",
            languages=("ja", "en"),
        ),
    ),
)
result = client.transcribe("audio.wav")
print(result.text)
```

`diarizer_alpha` と `diarizer_transition_bias` は、`speaker_diarization=True` のときのみ指定できます。型付きの `segmenter` と設定文字列の `segmenter_properties` は同時に指定できません。発話検出と言語識別の共通仕様は[セグメンター設定](./usage.md#セグメンター設定)を参照してください。

なお、`RecognitionSettings` の `speaker_diarization`、`diarization_min_speaker`、`diarization_max_speaker` は非同期 HTTP（v2）専用の設定です。同期 HTTP でこれらを指定すると `ConfigurationError` を送出します。非同期 HTTP の仕様は[非同期 HTTP の話者ダイアライゼーションの設定](./usage-async-http.md#話者ダイアライゼーションの設定)を参照してください。

## マルチチャネル音声のチャネル選択

複数チャネルの音声を同期 HTTP で認識する場合は、`selected_channel` で認識対象を指定できます。チャネル番号は `0` から始まり、単一チャネルは整数で指定します。複数チャネルの混合平均は `(0, N)` のタプルで指定し、`N` は正の整数に限ります。

`(0, 1)` はチャネル 0 と 1 を混合する指定です。`(1, 2)` のように先頭が 0 以外の範囲や、`(0, 0)` のように開始と終了が同じ範囲は `ConfigurationError` になります。チャネル 0 だけを認識する場合は `selected_channel=0` を使用してください。

```python
from amivoice import AmiVoiceClient, Engine, RecognitionSettings

client = AmiVoiceClient(
    settings=RecognitionSettings(grammar_file_names=Engine.A_GENERAL, selected_channel=(0, 1)),
)
result = client.transcribe("stereo.wav")
print(result.text)
```

複数チャネルに対応するのは、Wave、Ogg、FLAC などヘッダに音声フォーマットが含まれる音声です。`codec="LSB16K"` などを指定して送るヘッダなし PCM は 1 チャネルだけに対応します。別のチャネルの選択や複数チャネルの混合はできません。詳しくは[音声フォーマットのチャネルの説明](https://docs.amivoice.com/amivoice-api/manual/audio-format#channels)を参照してください。

API の設定文字列を直接指定する場合は `audio_filter_properties` を使用します。対応する形式は `selectedChannel=0` などの単一チャネル、または `selectedChannel=0-N` の範囲です。`selected_channel` と同時には指定できません。WebSocket では 1 チャネル目だけが認識対象になります。

`selected_channel` と `audio_filter_properties` は HTTP 用の設定で、WebSocket では利用できません。これらをクライアントの `settings` に保持したまま `stream()` を呼ぶと、`ConfigurationError` を送出します。WebSocket の呼び出しでは、`settings=RecognitionSettings(selected_channel=None)` などでチャネル設定を解除してください。
一方、WebSocket 専用の `result_updated_interval` と `no_input_timeout` は、共通のコンストラクタの `settings` に指定しても、HTTP の `transcribe()` ではサーバーへ送信しません。

ログ保存なしの設定（`logging_opt_out`）やタイムアウトの単位は、[ログ保存なしの認識](./usage.md#ログ保存なしの認識)と[タイムアウトと単位](./usage.md#タイムアウトと単位)を参照してください。

## 使用例 CLI

環境変数 `AMIVOICE_API_KEY` を設定したうえで、リポジトリのルートから実行します。共通のオプション一覧は[共通の CLI オプション](./usage.md#共通の-cli-オプション)を参照してください。

```bash
# HTTP・簡易版
uv run examples/hrp_simple_tester.py audio/test.wav

# HTTP・詳細版では複数ファイルを指定できる
uv run examples/hrp_tester.py audio/test.wav audio/test2.wav \
  --engine=-a-general --codec 16K --selected-channel 0
```

HTTP の詳細版（`examples/hrp_tester.py`）では複数の音声ファイルを位置引数で受け付け、共通の詳細オプションに加えて `--selected-channel` を指定できます。CLI では単一チャネルを整数で指定します。複数チャネルを混合するタプルは、Python API から指定してください。

`--url` を明示して `--logging-opt-out` を使う場合は、`/v1/nolog/recognize` のパスが必要です。指定した URL を自動でログ保存なしのパスへ変更しません。

```bash
uv run examples/hrp_tester.py audio/test.wav \
  --logging-opt-out --url https://acp-api.amivoice.com/v1/nolog/recognize
```

`--help` は API キーなしで実行でき、通信もしません。

```bash
uv run examples/hrp_tester.py --help
```

終了コードは成功が `0`、認識・通信・ファイル読み込みなどの失敗が `1` です。
引数の構文や型が不正な場合は、`argparse` が `2` で終了します。
数値の範囲や URL とログ保存設定の組み合わせなど、クライアントが検出する設定エラーは `1` です。
