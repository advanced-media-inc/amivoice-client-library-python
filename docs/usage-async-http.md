# 非同期 HTTP 音声認識（v2）ガイド

長時間の音声ファイルやバッチ処理には、非同期 HTTP 音声認識 API（v2）を利用します。
本ライブラリでは、`AmiVoiceAsyncClient` クラスを用いて非同期ジョブを登録・取得・待機します。

なお、クラス名に「Async」を含みますが、Python の `async` / `await` 構文を使用するライブラリではありません。通常の同期（ブロッキング）メソッドを提供します。`await` は使用できません。

- インストール、認証、共通の `RecognitionSettings`、ユーザー辞書管理: [共通利用ガイド](./usage.md)
- 短時間の録音済みファイルの一括認識: [同期 HTTP 音声認識ガイド](./usage-sync-http.md)
- リアルタイム・ストリーミング認識: [WebSocket ストリーミング認識ガイド](./usage-websocket.md)

## 基本的な流れ

非同期 HTTP 認識は、ジョブの登録（`submit()`）、状態取得（`get_job()`）、完了待機（`wait()`）の 3 つの操作で利用します。

```python
from amivoice import AmiVoiceAsyncClient, Engine, RecognitionSettings

client = AmiVoiceAsyncClient(settings=RecognitionSettings(grammar_file_names=Engine.A_GENERAL))

# 音声のアップロードと受付応答を待つ。認識完了までは待たない。
submission = client.submit("audio.wav")
print(f"受付ジョブID: {submission.session_id}")

# 完了までブロックして待機
snapshot = client.wait(submission.session_id)
print(f"状態: {snapshot.status}")
if snapshot.recognition is not None:
    print(f"認識テキスト: {snapshot.recognition.text}")
```

## ジョブ ID からの再開

ジョブ ID（`submission.session_id`）をデータベースやファイルへ保存しておけば、プロセスの再起動後や別のクライアントインスタンスからでも状態の取得や待機を再開できます。
取得や待機だけを行う場合、クライアントのコンストラクタで `grammar_file_names` の指定は不要です。

```python
from amivoice import AmiVoiceAsyncClient

client = AmiVoiceAsyncClient()

# 保存済みのジョブIDから状態と結果を取得
snapshot = client.get_job("job1")

# 保存済みのジョブIDの完了を待機
completed_snapshot = client.wait("job1")
```

## 入力音声の仕様と一時ファイル退避

`submit()` には、ファイルパス（文字列）、`pathlib.Path`、`bytes`、バイナリファイルオブジェクト（ストリーム）を渡せます。

音声データの上限は 2,147,483,647 バイト（約 2 GiB）です。ファイルは分割して読み込みます。
長さを事前に判定できないストリームは、一時ファイルへ退避してから送信します。
一時ファイル用に音声サイズ分のディスク容量が必要です。

利用者が渡したストリームは現在位置から読み、ライブラリでは閉じません。
呼び出し元で寿命を管理してください。
内部で開いたファイルと一時ファイルは、送信終了時や例外発生時に閉じて回収します。

### 送信音声の照合

`submit()` は実際に送信した音声チャンクから MD5 チェックサムを計算し、`AsyncJobSubmission` の `audio_size` と `audio_md5` にローカル情報として保持します。
サーバーから返った受付応答本文（`data` や `raw`）には追加しません。
なお、ここでの MD5 は転送確認を目的とした値であり、暗号学的な真正性を保証するものではありません。

ジョブ状態を取得した後は、`job.matches_audio(snapshot)` でサーバー側の観測値と照合できます。
このメソッドは同一のジョブ ID に対してのみ呼び出し可能で、異なるジョブ ID を渡すと `ConfigurationError` を送出します。
大文字と小文字を区別せずに比較し、サイズと MD5 の両方を比較できて一致した場合は `True` を返します。
いずれか一方で比較可能な不一致を確認した場合は `False` を返します。

ジョブが `queued` などでサーバー側のメタデータが未到着の場合や、カスタムの transport が音声を最後まで読み切らなかったために MD5 が `None` の場合など、情報が不足しているときは `None` を返します。
不一致を検出した場合でも、ライブラリ側でジョブの自動再登録やキャンセルは行いません。
`False` の場合は、元の音声とサーバー応答を確認して原因を調査してください。

```python
from amivoice import AmiVoiceAsyncClient, Engine, RecognitionSettings

client = AmiVoiceAsyncClient(settings=RecognitionSettings(grammar_file_names=Engine.A_GENERAL))
job = client.submit("audio.wav")
snapshot = client.get_job(job.session_id)
matched = job.matches_audio(snapshot)

if matched is False:
    print("送信音声の不一致を検出しました。")
```

## 共通設定の継承と解除

コンストラクタの `settings` は `submit()` に引き継がれ、呼び出し単位で上書きできます。
`settings` と各項目の継承・解除は、[共通の認識設定](./usage.md#クライアント設定の継承と解除use_client_default)と同じです。
プロキシ、通信タイムアウト、接続先は独立した引数で、`get_job()` と `wait()` でも継承・上書きできます。
プロキシは省略または `USE_CLIENT_DEFAULT` で継承し、`None` で解除します。
通信タイムアウトは非負整数が必要で、`None` による解除には対応しません。`0` は明示値です。

非同期クライアントのコンストラクタの `api_url` は、URL 文字列のみを受け付けます。省略時の URL は `https://acp-api-async.amivoice.com/v2/recognitions` です。コンストラクタに `USE_CLIENT_DEFAULT` や `None` は渡せません。
`submit()`、`get_job()`、`wait()` では、`api_url` を省略するか `USE_CLIENT_DEFAULT` を渡すと、カスタム URL も含めてクライアントの接続先を継承します。既定 URL へリセットする指定ではありません。呼び出し時も URL に `None` は指定できません。

```python
from amivoice import AmiVoiceAsyncClient, Engine, RecognitionSettings

client = AmiVoiceAsyncClient(
    settings=RecognitionSettings(grammar_file_names=Engine.A_GENERAL, profile_id=":user01"),
)

# この呼び出しだけプロファイル辞書を使用しない。接続エンジンは継承する。
job = client.submit("audio.wav", settings=RecognitionSettings(profile_id=None))
```

## ログ保存なしの設定（logging_opt_out）

非同期 HTTP 音声認識 API（v2）におけるログ保存なしの設定は、同期 HTTP や WebSocket と異なり、接続先 URL のパスを変更する方式ではありません。
`RecognitionSettings.logging_opt_out` の値を `d` パラメータの `loggingOptOut` へ送信します。`True` と `False` の両方を指定できます。

| 設定 | 動作 |
| --- | --- |
| `logging_opt_out=True` | 音声ログを保存しない |
| `logging_opt_out=False` | 音声ログを保存する |
| `None` | 値を解除して送信せず、サーバーの既定値（ログ保存あり）に従う |
| 省略または `USE_CLIENT_DEFAULT` | クライアントの値を継承。継承する値もなければ送信しない |

ライブラリ内部では、非同期 HTTP のエンドポイントとして常に `/v2/recognitions` を使用します。

## 話者ダイアライゼーションの設定

非同期 HTTP 音声認識（v2）の話者ダイアライゼーションは、`RecognitionSettings` の 3 項目で設定します。
サーバーへはマルチパートフィールド `d` 内のパラメータとして送信します。仕様の詳細は公式マニュアルの[話者ダイアライゼーション](https://docs.amivoice.com/amivoice-api/manual/speaker-diarization)、[リクエストパラメータ一覧](https://docs.amivoice.com/amivoice-api/manual/request-parameters)、[非同期 HTTP 音声認識インターフェース](https://docs.amivoice.com/amivoice-api/manual/async-http-interface)、[認識結果フォーマット](https://docs.amivoice.com/amivoice-api/manual/result-format)を参照してください。

| 項目 | 型 | 既定値 | `d` パラメータ | 内容 |
| --- | --- | --- | --- | --- |
| `speaker_diarization` | `bool \| None \| UseClientDefault` | `USE_CLIENT_DEFAULT` | `speakerDiarization` | 話者ダイアライゼーションの有効化。`True` は `"True"`、`False` は `"False"`（先頭大文字）を送信。省略時のサーバー既定値は `False` |
| `diarization_min_speaker` | `int \| None \| UseClientDefault` | `USE_CLIENT_DEFAULT` | `diarizationMinSpeaker` | 最小話者数。`1` 以上 `20` 以下の整数。省略時のサーバー既定値は `1` |
| `diarization_max_speaker` | `int \| None \| UseClientDefault` | `USE_CLIENT_DEFAULT` | `diarizationMaxSpeaker` | 最大話者数。`1` 以上 `20` 以下の整数。省略時のサーバー既定値は `10` |

`diarization_min_speaker` と `diarization_max_speaker` には `1` から `20` までの整数を、`diarization_min_speaker <= diarization_max_speaker` となるように指定します。話者数が分かっている場合は、最小話者数と最大話者数を同じ値にします。片方だけを指定した場合、未指定側はサーバーの既定値（最小 `1`、最大 `10`）が使われます。例えば `diarization_min_speaker=15` のみを指定すると、サーバー既定の最大値 `10` を超えるため受付に失敗する場合があります。
`bool`、`float`、`str` や範囲外（`1`〜`20` 以外）の値を指定すると、通信前に `ConfigurationError` を送出します。また、`speaker_diarization=True` で最小・最大話者数の両方を指定した際に大小関係が逆転している場合も `ConfigurationError` になります。話者ダイアライゼーションが無効でも、逆転した人数設定が残っていると、受付時に `AsyncHttpApiError` を送出することがあります。

これら 3 項目は非同期 HTTP（`AmiVoiceAsyncClient`）専用です。同期 HTTP（`AmiVoiceClient.transcribe()`）や WebSocket（`AmiVoiceClient.stream()`）、`AmiVoiceClient` のコンストラクタでは、明示的な `False` を含めて `ConfigurationError` で拒否します。`None` と `USE_CLIENT_DEFAULT` は許容します。同期 HTTP や WebSocket で話者ダイアライゼーションを利用する場合は、`segmenter=SegmenterProperties(speaker_diarization=True)` を使用してください。

非同期 HTTP では `SegmenterProperties` の話者設定である`speaker_diarization`、`diarizer_alpha`、`diarizer_transition_bias`は別方式のため使用できず、指定すると `ConfigurationError` になります。
`SegmenterProperties` の発話区間検出（VAD）と言語識別（LID）は非同期 HTTP でも利用できます。

### 基本的な実行とラベル参照

単一話者のサンプル音声 `audio.wav` に合わせて、`speaker_diarization=True`、`diarization_min_speaker=1`、`diarization_max_speaker=1` を指定し、完了後に単語ごとの話者ラベルを参照する例です。

```python
from amivoice import AmiVoiceAsyncClient, Engine, RecognitionSettings

client = AmiVoiceAsyncClient(
    settings=RecognitionSettings(
        grammar_file_names=Engine.A_GENERAL,
        speaker_diarization=True,
        diarization_min_speaker=1,
        diarization_max_speaker=1,
    ),
)

submission = client.submit("audio.wav")
snapshot = client.wait(submission.session_id)

if snapshot.recognition is not None:
    for utterance in snapshot.recognition.results:
        for token in utterance.tokens:
            # label はすべての単語に付くとは限らないため None を区別する
            # 公式のラベル文字列は小文字の "speaker0" などであり、リクエスト内でのみ有効（個人名には変換しない）
            speaker = token.label if token.label is not None else "ラベルなし"
            # starttime / endtime も任意フィールド（単位はミリ秒）のため None を区別する
            if token.starttime is not None and token.endtime is not None:
                timing = f"{token.starttime}ms - {token.endtime}ms"
            else:
                timing = "時刻なし"
            print(f"[{speaker}] {token.written} ({timing})")
```

認識結果の各単語（`utterance.tokens` の各 `Token`）から、`token.label`、`token.written`、`token.starttime`、`token.endtime` を参照できます。

`token.label` には `"speaker0"`、`"speaker1"` などの文字列、または `None` が入ります。実 API で全単語にラベルが付く保証はなく、未付与の単語は `None` のまま保持します。`speaker0`、`speaker1`、`speaker3` のように欠番になる場合もあります。
ラベルは 1 リクエスト内でのみ有効です。複数リクエスト間で同じ話者に同じラベルが付く保証はなく、個人を特定するものでもありません。
`token.starttime` と `token.endtime` はミリ秒単位の任意フィールドで、存在しない場合は `None` です。
ライブラリはサーバーが返した話者ラベルをそのまま保持します。話者ごとの発話結合や集約は行いません。

### 呼び出し単位での上書き・無効化・解除と警告

各項目は `USE_CLIENT_DEFAULT` でクライアント既定値を継承し、明示値で上書き、`None` でクライアント既定値を解除します。`speaker_diarization=False` または `None` を指定すると、どちらも話者ダイアライゼーション機能を使用しません。

`diarization_min_speaker` や `diarization_max_speaker` だけを指定しても、`speaker_diarization` は自動で `True` になりません。
また、`speaker_diarization=False` または `None` で機能を無効化しても、指定または継承された人数設定は送信されます。最小話者数が最大話者数を超えるなど、不正な設定が残っていると受付時に拒否されます。
話者ダイアライゼーションが無効な状態で最小・最大話者数の設定が残っている場合、`submit()` 実行時に標準の `logging`（`logging.WARNING`）で警告を 1 回出力します。警告が出てもリクエストの送信自体は止まりません。機能を無効化する際に人数設定の送信と警告も止めたい場合は、`diarization_min_speaker=None` と `diarization_max_speaker=None` を指定して解除するか、新しいクライアントを作成してください。なお、ライブラリは `logging.basicConfig()` などの全体設定を変更しません。

以下のコードは、呼び出し単位で設定を上書き・無効化・解除する例です。

```python
from amivoice import AmiVoiceAsyncClient, Engine, RecognitionSettings

client = AmiVoiceAsyncClient(
    settings=RecognitionSettings(
        grammar_file_names=Engine.A_GENERAL,
        speaker_diarization=True,
        diarization_min_speaker=2,
        diarization_max_speaker=6,
    ),
)

# 1. この呼び出しだけ話者数の範囲を 3〜4 人に上書きする（speaker_diarization=True は継承）
job_override = client.submit(
    "audio.wav",
    settings=RecognitionSettings(
        diarization_min_speaker=3,
        diarization_max_speaker=4,
    ),
)

# 2. この呼び出しだけ話者ダイアライゼーション機能のみを無効化する
# クライアント既定の人数設定（2〜6）は引き継がれて送信されるため、警告（logging.WARNING）が出る
job_disable = client.submit(
    "audio.wav",
    settings=RecognitionSettings(
        speaker_diarization=False,
    ),
)

# 3. 話者ダイアライゼーション機能と人数設定の両方を None で解除する（人数は送信されず警告も出ない）
job_clear = client.submit(
    "audio.wav",
    settings=RecognitionSettings(
        speaker_diarization=None,
        diarization_min_speaker=None,
        diarization_max_speaker=None,
    ),
)
```

### 音声・運用上の制約と精度特性

認識可能な話者数は最大 20 人です。話者ダイアライゼーション有効時は、1 リクエストあたり最大 3 時間までの音声が対象となり、通常より処理時間が増加します。

ライブラリ側では送信前の音声長の解析や 3 時間超の音声の自動分割をせず、サーバー側の判定に委ねます。受付時（POST）に拒否された場合は `AsyncHttpApiError` を送出します。受付後のジョブ失敗や認識失敗では、`get_job()` はエラースナップショットを返します。`wait()` は `raise_on_error=True`（既定）で `AsyncJobError`、`False` でエラースナップショットを返します。待機が `AsyncJobTimeoutError` となった場合も、同じジョブ ID で後から `get_job()` や `wait()` を再開できます。

ノイズ、エコー、同時発話が含まれる音声では、複数の話者が単一のラベルになる場合があります。ノイズやエコー、同時発話を避けて録音し、`diarization_min_speaker` と `diarization_max_speaker` で話者数の範囲を指定すると推定精度を改善できる可能性があります。ただし、本ライブラリは推定精度を保証しません。

## ジョブの状態と結果の構造

非同期ジョブの状態を表す `AsyncJobSnapshot.status` には、既知の 5 状態があります。処理待ちは `queued`、処理開始は `started`、処理中は `processing`、処理完了は `completed`、ジョブ失敗は `error` です。終端状態に達したかを表す `is_terminal` は、`completed` または `error` のときのみ `True` を返します。

ジョブ完了後の認識自体の成否を含む全体の成否は、`snapshot.is_error` で判定できます。将来の応答変更などで空の結果が返った場合も、型が正しい空の `text` や空配列を含む正常な完了結果であれば `AsyncRecognitionResult` として返されます。この場合、認識処理のエラー有無は `code` や `message` に基づく `is_error` で判定し、認識本文が空である点は利用側で確認します。また、失敗を示す `code` や `message` が存在する場合は、`segments` や `results` といった詳細配列が省かれていても認識失敗として扱われます。

なお、ライブラリはあらゆる未知の形式を無条件に許容するわけではありません。ジョブ ID の不一致や、`completed` 時に必須となる `text`、`code`、`message` の欠落・型不正は `AsyncHttpApiError` になります。配列ではない詳細フィールド、平坦形式と入れ子形式が混在する曖昧なエンベロープ、空文字や制御文字を含む不正な `status` も同じ例外を送出します。

認識結果と生データの参照構造は以下の表のとおりです。

| フィールド | 内容 |
| --- | --- |
| `snapshot.recognition` | 完了時の `AsyncRecognitionResult`、処理中やジョブ失敗では `None` |
| `snapshot.recognition.results` | `tuple[UtteranceResult, ...]`、通常形式では区間内の結果を順番に並べる |
| `snapshot.recognition.segments` | `tuple[RecognitionResult, ...]`、区間ごとの詳細結果 |
| `snapshot.recognition.raw` / `data` | 認識結果部分の正規化した JSON 文字列と辞書 |
| `snapshot.raw` / `data` | 状態取得 API 全体の元の応答文字列と辞書 |

`compatible_with_sync=True` では、`results` にサーバーの集約結果を保持します。
この形式で区間詳細が返らない場合、`segments` は空のタプルです。
`snapshot.raw` と `data` には機密情報が含まれ得るため、無条件にログへ出力しないでください。

## 待機制御（wait）とエラーハンドリング

`wait()` メソッドは、ジョブが終端状態になるまでポーリングを行いながら呼び出し元をブロックします。

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

`poll_interval` は正の有限数（秒）で、最大 3600 秒（1 時間）、既定値は 10 秒です。
`timeout` は正の有限数（秒）で最大 604800 秒（7 日）、`None`（既定値）を指定すると無制限になります。
上限ちょうどの値は指定できます。上限超過や `0`、負値、`bool`、無限大、`NaN` などの不正な値は、通信や待機を始める前に `ConfigurationError` を送出します。

待機期限に達し、取得済みの応答から終端状態を確認できなかった場合は、`AsyncJobTimeoutError` を送出します。サーバーのジョブはキャンセルしません。
例外の `session_id` と、最後の状態を保持する `snapshot` から取得を再開できます。
まだ状態を取得できていない場合、`snapshot` は `None` です。

既定の transport は、通信中に待機期限へ達するとソケット通信を中断します。
ただし、DNS 名前解決、OS の接続処理、独自 transport など、ソケット中断で止められない処理には待機上限を保証できません。
`connect_timeout` と `receive_timeout` はミリ秒単位で、`0` は無制限です。

一方で、本文を最後まで読み切った応答は、受信完了や解析の時点で待機期限に達していても破棄せずに検証・解析します。
取得した応答が終端状態であればタイムアウトより優先し、正常完了は `snapshot` を返し、ジョブまたは認識の失敗は `raise_on_error` の設定に従います。
非終端状態であり、かつ待機期限に達している場合は、その最新 `snapshot` を保持して `AsyncJobTimeoutError` を送出します。
通信途中の失敗や受信中断で応答を取得できず、待機期限に達した場合は、それまでに取得できた最後の `snapshot`（未取得なら `None`）でタイムアウトします。
なお、待機期限の経過後に新しい GET を開始したり、待機期限自体を延長したりすることはありません。

ジョブや認識の失敗は、既定の `raise_on_error=True` で `AsyncJobError` になります。
`False` では、失敗した終端状態をスナップショットとして返します。
通信失敗の `ConnectionFailedError`、HTTP エラーや不正応答の `AsyncHttpApiError` は、この設定にかかわらず送出します。

### 原因コードと再試行の目安

ジョブ失敗や認識失敗の調査では、`snapshot.error_code` および `AsyncJobError.error_code` で単一の原因コードを参照できます。また、`snapshot.is_retryable` および `AsyncJobError.is_retryable` で再試行を検討する目安を取得できます。`AsyncJobError` のプロパティは、内部の `snapshot` へ処理を委譲します。

ジョブ失敗（`status="error"`）では、サーバーが返した `error_message` から `amineth_code` を抽出します。`error_code="o"`（認識拒否・信頼度拒否など）のときは、`is_retryable` は `False` を返します。その他の 1 文字コードのときは、`is_retryable` は `True` を返します。これは[公式ドキュメント](https://docs.amivoice.com/amivoice-api/manual/async-http-interface)のエラー状態に案内されている「しばらく待ってからの再登録を検討する目安」であり、成功の保証やライブラリによる自動再送ではありません。原因コードが含まれない場合、複数のコードが含まれる場合、1 文字以外のコードなど原因が曖昧な場合は、`error_code` と `is_retryable` はともに `None` を返します。未知の原因に対して再試行可否を断定しません。

ジョブが処理中（`status` が `queued`、`started`、`processing` のいずれか）のときは終端に達していないため、`error_code` と `is_retryable` は常に `None` を返します。

完了後の認識失敗（`status="completed"` かつ `is_error=True`）では、認識結果の `code` が 1 文字の場合に `error_code` として取得できます。信頼度拒否を示す `code="o"` のときは、`is_retryable` は `False` を返します。それ以外の認識失敗コードでは、`is_retryable` は `None` を返します。公式ドキュメントにおけるジョブ `error` 状態の再試行案内を、完了後の音声認識エラー全般へ拡張しないためです。

## 通信と運用の注意点

POST の通信が途切れた場合、音声が受理されたか判別できません。
重複ジョブや二重請求を避けるため、登録（POST）の自動再送は行いません。
単発の `get_job()` でも再試行は行いません。

一方で、`wait()` による完了待機中の一時的な GET 失敗に限っては、設定に従って自動で再試行します。
再試行の対象は `ConnectionFailedError` と HTTP 429、500、502、503、504 のみです。
HTTP 200 の不正応答や HTTP 401、404 など、その他の失敗は再試行せずに例外を送出します。
既定では `max_retries=3` で連続失敗時に最大 3 回の追加 GET を行い、`0` を指定すると再試行を無効化できます。
待機時間は `retry_backoff=1.0`（秒）から試行ごとに倍増し、最大 30 秒で頭打ちになります。
状態を取得できた場合、連続失敗の回数はリセットされます。
再試行のバックオフ待機も全体の `timeout` に含まれ、待機上限に達したときは直近に取得できた最後の `snapshot` を保持して `AsyncJobTimeoutError` を送出します。
なお、この再試行は待機中の状態確認（GET）だけを対象としており、ジョブ自体を再登録するものではありません。
`content_id` はデータを紐付ける文字列であり、同じ値の再使用によって重複登録を防ぐことはできません。

結果は処理終了後 7 日間保存されます。存在しない ID や期限切れの結果は HTTP 404 になります。
ただし、別ユーザーのジョブにアクセスした場合などにも 404 が返るため、期限切れとは断定しません。
HTTP エラーや不正応答、受付拒否が起きた場合は `AsyncHttpApiError` を送出します。例外の `status_code`、`body`、`raw_body` に加え、JSON オブジェクトの応答であれば `data`（辞書または `None`）、サーバーが返したエラー情報は `code` と `api_message`（文字列または `None`）から取得できます。ライブラリ側で本文を解析するため、利用側での独自の JSON 再解析は不要です。`message` や `str(error)` は機密情報を含まない安全な一般説明を返します。生レスポンスである `body` や `raw_body`、`data` には機密情報が含まれ得るため、無条件にログへ出力しないでください。
また、認証エラー時は公開例外 `AsyncHttpAuthenticationError` を送出します。この例外は `AsyncHttpApiError` と `AuthenticationError` の両方を継承しており、HTTP 401 応答だけでなく、受付時（HTTP 200）の `code="-"` でも発生します。そのため、既存の `AuthenticationError` ハンドラと非同期固有の `AsyncHttpApiError` ハンドラのどちらでも捕捉できます。

このクライアントでは、感情分析の設定はまだ提供していません。
非同期 HTTP の話者ダイアライゼーションは `RecognitionSettings` の `speaker_diarization`、`diarization_min_speaker`、`diarization_max_speaker` で指定します。`SegmenterProperties` の話者設定は同期 HTTP・WebSocket 専用の別方式であり、明示的な `False` も含めて非同期 HTTP では拒否します。
`SegmenterProperties` の発話検出と言語識別は利用できます。
同期 HTTP 用のルール設定、WebSocket 用の途中結果間隔と発話開始待ち設定も対応していません。

## 使用例 CLI

環境変数 `AMIVOICE_API_KEY` を設定したうえで、リポジトリのルートから実行します。共通のオプション一覧は[共通の CLI オプション](./usage.md#共通の-cli-オプション)を参照してください。

```bash
# 非同期HTTP・ジョブの登録（アップロードと受付後にジョブIDを表示）
uv run examples/async_http_tester.py submit audio/test.wav --engine=-a-general

# 非同期HTTP・状態と認識結果の取得
uv run examples/async_http_tester.py status <session_id>

# 非同期HTTP・ジョブ完了の待機
uv run examples/async_http_tester.py wait <session_id> --poll-interval 10.0 --timeout 300.0
```

非同期 HTTP CLI（`examples/async_http_tester.py`）では、共通引数（`--url`、`--proxy-server-name`、`--connect-timeout`、`--receive-timeout`）をサブコマンド（`submit`、`status`、`wait`）の前に指定します。
`submit` サブコマンドでは、[共通の認識オプション](./usage.md#共通の-cli-オプション)を指定できます。加えて `--selected-channel`、`--content-id`、`--compatible-with-sync` / `--no-compatible-with-sync`、`--logging-opt-out` / `--no-logging-opt-out` も指定可能です。話者ダイアライゼーション用には `--speaker-diarization` / `--no-speaker-diarization`（`BooleanOptionalAction`、省略時は `None`）を指定できます。話者数の範囲には `--diarization-min-speaker` と `--diarization-max-speaker`（ともに整数、省略時は `None`）を指定します。`--codec` は省略でき、ヘッダなし音声では明示してください。
`status` と `wait` の標準出力形式と終了コードは変わらず、CLI 独自の話者別の集約表示は行いません。単語ごとの話者ラベル（`token.label`）を参照する場合は、[話者ダイアライゼーションの設定](#話者ダイアライゼーションの設定)の Python コード例を参照してください。

```bash
uv run examples/async_http_tester.py --connect-timeout 10000 --receive-timeout 30000 submit audio/test.wav
```

`--help` は API キーなしで実行でき、通信もしません。

```bash
uv run examples/async_http_tester.py --help
uv run examples/async_http_tester.py submit --help
uv run examples/async_http_tester.py status --help
uv run examples/async_http_tester.py wait --help
```

非同期 HTTP CLI の終了コードは以下のとおりです。

| 終了コード | 内容 |
| --- | --- |
| `0` | 操作成功。`status` では処理中の状態を取得した場合も成功 |
| `1` | 認識・通信・ジョブ・設定・ファイルなどのエラー |
| `2` | argparse が検出した引数構文・型のエラー |
| `3` | `wait()` の待機タイムアウト。サーバーのジョブは継続し、同じ ID で再開できる |
