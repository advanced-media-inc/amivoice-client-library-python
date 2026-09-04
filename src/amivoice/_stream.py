"""ストリーミング音声認識セッションの管理クラス群。"""

import queue
from collections.abc import Callable, Iterator

from com.amivoice.wrp.Wrp import Wrp as _Wrp
from com.amivoice.wrp.WrpListener import WrpListener

from ._billing import resolve_billing_extension
from ._params import RecognitionParams
from ._transport import WrpTransport, bool_string
from .exceptions import ConnectionFailedError, RecognitionError
from .models import NotificationEvent, RecognitionResult, StreamEvent, UtteranceEvent, parse_result

_SENTINEL = object()  # poll() ループ終端マーカー


class _WrpListenerAdapter(WrpListener):
    """WRP ライブラリのコールバックを ``StreamSession`` のイベントキューへ変換するアダプター。

    コールバックのメソッド名は override 元の ``WrpListener``（上流ライブラリ）に合わせる。
    引数名は snake_case にするが、上流はキャメルケースの引数を位置引数で渡すため、
    引数名不一致による ``reportIncompatibleMethodOverride`` を抑制する。
    """

    def __init__(self, session: "StreamSession") -> None:
        super().__init__()
        self._session = session

    def utteranceStarted(self, start_time: int) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        self._session._on_utterance_started(UtteranceEvent("started", start_time))

    def utteranceEnded(self, end_time: int) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        self._session._on_utterance_ended(UtteranceEvent("ended", end_time))

    def resultUpdated(self, result: str) -> None:
        self._session._on_result_updated(result)

    def resultFinalized(self, result: str) -> None:
        self._session._on_result_finalized(result)

    def eventNotified(self, event_id: str, event_message: str) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        self._session._on_event_notified(NotificationEvent(event_id, event_message))


class StreamSession:
    """アクティブな WebSocket ストリーミング認識セッション。

    ``StreamConnectionManager.__enter__`` が返す。直接インスタンス化しないこと。

    イベント消費には 2 通りの方法がある:

    - :meth:`events` — ブロッキングで逐次消費する（推奨）。``end()`` の終端まで待機する。
    - :meth:`poll` — ノンブロッキング。その時点で溜まっているイベントのみ返す。

    Example::

        with client.stream(
            grammar_file_names="-a-general",
            codec="16K",
        ) as session:
            session.write(
                audio_bytes
            )
            session.end()
            for event in session.events():
                if event.is_final:
                    print(
                        event.result.data[
                            "text"
                        ]
                    )
                elif (
                    event.type
                    == "partial"
                ):
                    print(
                        "...",
                        event.text,
                    )
    """

    def __init__(self, wrp: WrpTransport, *, finalize_timeout_ms: int = 60_000) -> None:
        """内部使用専用。``wrp`` はすでに connect 済みの WRP トランスポートオブジェクト。

        Args:
            wrp: connect 済みの WRP トランスポート。
            finalize_timeout_ms: ``end()`` が残りの認識結果を待機する既定タイムアウト（ミリ秒）。
        """
        self._wrp = wrp
        self._finalize_timeout_ms = finalize_timeout_ms
        self._event_queue: queue.SimpleQueue[object] = queue.SimpleQueue()
        self._finalized_results: list[RecognitionResult] = []
        self._ended = False
        self._adapter = _WrpListenerAdapter(self)
        self._wrp.setListener(self._adapter)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def write(self, chunk: bytes) -> None:
        """音声チャンクを送信する。

        Args:
            chunk: 送信する PCM 音声バイト列。

        Raises:
            RecognitionError: 送信に失敗した場合。
        """
        if self._ended:
            raise RecognitionError("Cannot write to an ended session")
        if not self._wrp.feedData(chunk, 0, len(chunk)):
            raise RecognitionError(self._wrp.getLastMessage())

    def poll(self) -> Iterator[StreamEvent]:
        """キューに溜まったイベントをすべて yield する（ノンブロッキング）。

        呼び出した時点でキューに溜まっているイベントのみを返し、キューが空になると即座に
        終了する。まだ結果が届いていない場合は何も返さないため、ポーリングループでは
        別途 sleep 等で待機する必要がある。逐次消費してブロックしたい場合は
        :meth:`events` を使用する。

        ``end()`` 呼び出し後に呼ぶと、残っているイベントをすべて返した後で終了する。

        Yields:
            ``StreamEvent`` オブジェクト。
        """
        while True:
            try:
                item = self._event_queue.get_nowait()
            except queue.Empty:
                break
            if item is _SENTINEL:
                break
            if isinstance(item, StreamEvent):
                yield item

    def events(self, *, timeout: float | None = None) -> Iterator[StreamEvent]:
        """イベントをブロッキングで逐次 yield する。

        次のイベントが届くまで待機し、``end()`` が投入する終端マーカーに到達すると
        イテレーションを終了する。音声送信と別スレッドで消費するか、送信完了後に
        ``end()`` を呼んでから消費する。

        Args:
            timeout: 次のイベントを待機する最大秒数。``None`` は無制限。指定した時間内に
                イベントが届かなかった場合は ``RecognitionError`` を送出する。

        Yields:
            ``StreamEvent`` オブジェクト。

        Raises:
            RecognitionError: ``timeout`` 秒以内にイベントが届かなかった場合。
        """
        while True:
            try:
                item = self._event_queue.get(timeout=timeout)
            except queue.Empty as exc:
                raise RecognitionError("Timed out waiting for stream event") from exc
            if item is _SENTINEL:
                return
            if isinstance(item, StreamEvent):
                yield item

    def end(self, *, timeout: float | None = None) -> None:
        """音声送信終了を宣言し、残りの認識結果を待機する。

        ``feedDataPause`` を発行し、WRP の待機結果がゼロになるまでポーリングする。
        呼び出し後は ``write()`` できない。

        Args:
            timeout: 残りの認識結果を待機する最大秒数。``None`` の場合はコンストラクタ時の
                既定タイムアウト（``finalize_timeout_ms``）を使用する。

        Raises:
            RecognitionError: 終了処理中にエラーが発生した場合、または待機がタイムアウトした場合。
        """
        if self._ended:
            return
        self._ended = True

        if not self._wrp.feedDataPause():
            raise RecognitionError(self._wrp.getLastMessage())

        # 残り待機結果がゼロになるまでポーリング
        poll_interval_ms = 100
        max_wait_ms = self._finalize_timeout_ms if timeout is None else int(timeout * 1000)
        waited_ms = 0
        while self._wrp.getWaitingResults() > 0:
            if waited_ms >= max_wait_ms:
                raise RecognitionError("Timed out waiting for remaining recognition results")
            self._wrp.sleep(poll_interval_ms)
            waited_ms += poll_interval_ms

        # poll() / events() ループ終端マーカーをキューに投入
        self._event_queue.put(_SENTINEL)

    def results(self) -> list[RecognitionResult]:
        """``end()`` 後の確定済み認識結果一覧を返す。

        Returns:
            確定済み ``RecognitionResult`` のリスト（順序保証）。
        """
        return list(self._finalized_results)

    # ------------------------------------------------------------------
    # Internal callbacks (called by _WrpListenerAdapter)
    # ------------------------------------------------------------------

    def _on_result_updated(self, text: str) -> None:
        self._event_queue.put(StreamEvent(type="partial", text=text))

    def _on_result_finalized(self, raw: str) -> None:
        result = parse_result(raw, raise_on_error=False)
        self._finalized_results.append(result)
        text = str(result.data.get("text", ""))
        self._event_queue.put(StreamEvent(type="final", text=text, result=result))

    def _on_utterance_started(self, event: UtteranceEvent) -> None:
        self._event_queue.put(StreamEvent(type="utterance_started", utterance=event))

    def _on_utterance_ended(self, event: UtteranceEvent) -> None:
        self._event_queue.put(StreamEvent(type="utterance_ended", utterance=event))

    def _on_event_notified(self, event: NotificationEvent) -> None:
        self._event_queue.put(StreamEvent(type="notification", notification=event))


def _build_wrp_transport(api_key: str, api_url: str, params: RecognitionParams) -> WrpTransport:
    """WRP トランスポートオブジェクトを生成して接続する。"""
    wrp: WrpTransport = _Wrp.construct()

    wrp.setServerURL(api_url)
    wrp.setAuthorization(api_key)

    keep_filler = None if params.keep_filler_token is None else bool_string(params.keep_filler_token)
    interval = None if params.result_updated_interval is None else str(params.result_updated_interval)
    recognition_timeout = None if params.recognition_timeout is None else str(params.recognition_timeout)
    complete_timeout = None if params.complete_timeout is None else str(params.complete_timeout)
    wildcard_model_penalty = None if params.wildcard_model_penalty is None else repr(params.wildcard_model_penalty)
    max_decoding_time = None if params.max_decoding_time is None else str(params.max_decoding_time)
    max_response_time = None if params.max_response_time is None else str(params.max_response_time)
    max_decoding_rate = None if params.max_decoding_rate is None else repr(params.max_decoding_rate)
    target_response_time = None if params.target_response_time is None else str(params.target_response_time)
    target_decoding_rate = None if params.target_decoding_rate is None else repr(params.target_decoding_rate)
    confidence_level = None if params.confidence_level is None else repr(params.confidence_level)
    extension = resolve_billing_extension(params.extension, params.billing_key)
    no_input_timeout = None if params.no_input_timeout is None else str(params.no_input_timeout)
    optional_setters: tuple[tuple[Callable[[str | None], None], str | None], ...] = (
        (wrp.setGrammarFileNames, params.grammar_file_names),
        (wrp.setCompleteTimeout, complete_timeout),
        (wrp.setWildcardModelPenalty, wildcard_model_penalty),
        (wrp.setCodec, params.codec),
        (wrp.setResultType, params.result_type),
        (wrp.setProxyServerName, params.proxy_server_name),
        (wrp.setVoiceDetection, params.voice_detection),
        (wrp.setMode, params.mode),
        (wrp.setProfileId, params.profile_id),
        (wrp.setProfileWords, params.profile_words),
        (wrp.setSegmenterType, params.segmenter_type),
        (wrp.setSegmenterProperties, params.segmenter_properties),
        (wrp.setExtension, extension),
        (wrp.setKeepFillerToken, keep_filler),
        (wrp.setResultUpdatedInterval, interval),
        (wrp.setRecognitionTimeout, recognition_timeout),
        (wrp.setMaxDecodingTime, max_decoding_time),
        (wrp.setMaxResponseTime, max_response_time),
        (wrp.setMaxDecodingRate, max_decoding_rate),
        (wrp.setTargetResponseTime, target_response_time),
        (wrp.setTargetDecodingRate, target_decoding_rate),
        (wrp.setConfidenceLevel, confidence_level),
        (wrp.setNoInputTimeout, no_input_timeout),
    )
    for setter, value in optional_setters:
        if value is not None:
            setter(value)

    if params.connect_timeout > 0:
        wrp.setConnectTimeout(params.connect_timeout)
    if params.receive_timeout > 0:
        wrp.setReceiveTimeout(params.receive_timeout)

    if not wrp.connect():
        raise ConnectionFailedError(wrp.getLastMessage())

    return wrp


class StreamConnectionManager:
    """``client.stream()`` が返すコンテキストマネージャ。

    ``__enter__`` で WebSocket 接続を確立し ``StreamSession`` を返す。
    ``__exit__`` で切断する。

    openai-python の ``RealtimeConnectionManager`` と同様に
    ``enter = __enter__`` escape hatch を提供する。

    Example::

        manager = client.stream(
            grammar_file_names="-a-general",
            codec="16K",
        )
        # コンテキストマネージャ経由（推奨）
        with (
            manager as session
        ):
            session.write(
                data
            )
            session.end()

        # escape hatch（非同期フレームワーク等での手動管理）
        session = (
            manager.enter()
        )
        try:
            session.write(
                data
            )
            session.end()
        finally:
            manager.__exit__(
                None,
                None,
                None,
            )
    """

    def __init__(
        self,
        *,
        api_key: str,
        api_url: str,
        params: RecognitionParams,
        wrp_transport: WrpTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._api_url = api_url
        self._params = params
        self._wrp_transport = wrp_transport  # テスト注入用

        self._wrp: WrpTransport | None = None
        self._session: StreamSession | None = None

    def __enter__(self) -> StreamSession:
        """WebSocket 接続を確立し ``StreamSession`` を返す。"""
        if self._wrp_transport is not None:
            wrp = self._wrp_transport
        else:
            wrp = _build_wrp_transport(self._api_key, self._api_url, self._params)

        # feedDataResume() 内で発生する通知を取りこぼさないよう、
        # 先に StreamSession 側でリスナーを設定してから開始する
        # end() の待機タイムアウトは receive_timeout（0 は無制限だが実務上の上限として 60 秒）に合わせる
        finalize_timeout_ms = self._params.receive_timeout if self._params.receive_timeout > 0 else 60_000
        self._wrp = wrp
        self._session = StreamSession(wrp, finalize_timeout_ms=finalize_timeout_ms)

        if not wrp.feedDataResume():
            self._session = None
            self._wrp = None
            wrp.disconnect()
            raise RecognitionError(wrp.getLastMessage())

        return self._session

    # escape hatch — openai-python 互換パターン
    enter = __enter__

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        """WebSocket 接続を切断する。"""
        if self._wrp is not None:
            try:
                self._wrp.disconnect()
            except Exception:
                pass
            finally:
                self._wrp = None
                self._session = None

    def __del__(self) -> None:
        """GC 時のフェールセーフ切断。"""
        if self._wrp is not None:
            try:
                self._wrp.disconnect()
            except Exception:
                pass
            finally:
                self._wrp = None
