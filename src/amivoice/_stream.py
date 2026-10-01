"""WRP 確認応答とイベントキューを直接管理するストリーミング認識"""

import queue
import threading
from collections.abc import Iterator
from contextlib import suppress

from ._params import RecognitionParams
from ._recognition_protocol import build_wrp_start_command, parse_wrp_message
from ._websocket_transport import WebSocketTransport
from .exceptions import RecognitionError
from .models import RecognitionResult, StreamEvent

_SENTINEL = object()


class StreamSession:
    """アクティブな WebSocket 音声認識セッション

    ``client.stream()`` のコンテキストマネージャから取得する
    音声は ``write()`` で送信し、``end()`` で残りの確定結果を待つ
    ``events()`` はブロッキング、``poll()`` はノンブロッキングでイベントを返す
    """

    def __init__(self, wrp: WebSocketTransport, *, finalize_timeout_ms: int = 60_000) -> None:
        """接続済み WebSocket とイベントキューを初期化する

        Args:
            wrp (WebSocketTransport): 接続済みの通信境界
            finalize_timeout_ms (int): 開始確認と認識終了の既定待機時間（ミリ秒）
        """
        self._wrp = wrp
        self._finalize_timeout_ms = finalize_timeout_ms
        self._event_queue: queue.SimpleQueue[object] = queue.SimpleQueue()
        self._finalized_results: list[RecognitionResult] = []
        self._condition = threading.Condition()
        self._write_lock = threading.Lock()
        self._started = False
        self._ended = False
        self._end_acknowledged = False
        self._waiting_results = 0
        self._error: RecognitionError | None = None
        self._events_closed = False
        self._closing = False
        self._receiver: threading.Thread | None = None

    def _start_recognition(self, command: str) -> None:
        self._receiver = threading.Thread(target=self._receive_events, name="amivoice-stream-receiver", daemon=True)
        self._receiver.start()
        try:
            self._wrp.send_text(command)
            with self._condition:
                ready = self._condition.wait_for(
                    lambda: self._started or self._error is not None, timeout=self._finalize_timeout_ms / 1000
                )
                self._raise_receiver_error()
                if not ready:
                    raise RecognitionError("Timed out waiting for stream start acknowledgement")
        except RecognitionError as exc:
            self._fail_recognition(exc)
            raise

    def _raise_receiver_error(self) -> None:
        if self._error is not None:
            raise self._error

    def _receive_events(self) -> None:
        try:
            while True:
                message = self._wrp.receive_message()
                if isinstance(message, bytes):
                    message = message.decode("UTF-8")
                parsed = parse_wrp_message(message)
                with self._condition:
                    if self._closing:
                        return
                    if parsed.command == "s":
                        self._started = True
                    elif parsed.command == "e":
                        self._end_acknowledged = True
                    elif parsed.command == "S":
                        self._waiting_results += 1
                    elif parsed.command in {"A", "R"}:
                        self._waiting_results = max(0, self._waiting_results - 1)
                    if parsed.event is not None:
                        if parsed.event.result is not None:
                            self._finalized_results.append(parsed.event.result)
                        self._event_queue.put(parsed.event)
                    self._condition.notify_all()
                    if self._end_acknowledged and self._waiting_results == 0:
                        self._finish_events()
                        return
        except (RecognitionError, UnicodeError) as exc:
            if not self._closing:
                error = exc if isinstance(exc, RecognitionError) else RecognitionError("Invalid WRP response encoding")
                self._fail_recognition(error)

    def _finish_events(self) -> None:
        if not self._events_closed:
            self._events_closed = True
            self._event_queue.put(_SENTINEL)

    def _fail_recognition(self, error: RecognitionError) -> None:
        with self._condition:
            if self._error is None and not self._events_closed:
                self._error = error
                self._event_queue.put(error)
                self._finish_events()
            self._condition.notify_all()

    def write(self, chunk: bytes) -> None:
        """音声チャンクを送信する

        Args:
            chunk (bytes): 送信する音声バイト列

        Raises:
            RecognitionError: 終了後の送信、通信失敗、受信側のエラー
        """
        with self._write_lock:
            self._raise_receiver_error()
            if self._ended or self._closing:
                raise RecognitionError("Cannot write to an ended session")
            try:
                self._wrp.send_binary(b"p" + chunk)
            except RecognitionError as exc:
                self._fail_recognition(exc)
                raise

    def poll(self) -> Iterator[StreamEvent]:
        """その時点でキューに溜まっているイベントを返す

        Yields:
            StreamEvent: 公開認識イベント

        Raises:
            RecognitionError: キュー内の受信エラー
        """
        while True:
            try:
                item = self._event_queue.get_nowait()
            except queue.Empty:
                if self._events_closed:
                    self._raise_receiver_error()
                return
            if item is _SENTINEL:
                return
            if isinstance(item, RecognitionError):
                raise item
            if isinstance(item, StreamEvent):
                yield item

    def events(self, *, timeout: float | None = None) -> Iterator[StreamEvent]:
        """次のイベントを待ち、終了または受信エラーまで逐次返す

        Args:
            timeout (float | None): 次のイベントを待つ秒数、None は無制限

        Yields:
            StreamEvent: 公開認識イベント

        Raises:
            RecognitionError: イベント待機タイムアウトまたは受信失敗
        """
        while True:
            if self._events_closed and self._event_queue.empty():
                self._raise_receiver_error()
                return
            try:
                item = self._event_queue.get(timeout=timeout)
            except queue.Empty as exc:
                raise RecognitionError("Timed out waiting for stream event") from exc
            if item is _SENTINEL:
                return
            if isinstance(item, RecognitionError):
                raise item
            if isinstance(item, StreamEvent):
                yield item

    def end(self, *, timeout: float | None = None) -> None:
        """送信終了の確認応答とすべての残りの認識結果を一つの期限で待つ

        Args:
            timeout (float | None): 最大待機秒数、None は既定値

        Raises:
            RecognitionError: 確認応答、認識結果のタイムアウトまたは受信失敗
        """
        with self._write_lock:
            self._raise_receiver_error()
            if self._ended:
                return
            self._ended = True
            try:
                self._wrp.send_text("e")
            except RecognitionError as exc:
                self._fail_recognition(exc)
                raise
        wait_seconds = self._finalize_timeout_ms / 1000 if timeout is None else timeout
        with self._condition:
            ready = self._condition.wait_for(
                lambda: (self._end_acknowledged and self._waiting_results == 0) or self._error is not None, timeout=wait_seconds
            )
            self._raise_receiver_error()
            if not ready:
                error = RecognitionError("Timed out waiting for remaining recognition results or end acknowledgement")
                self._fail_recognition(error)
                raise error

    def results(self) -> list[RecognitionResult]:
        """確定済み認識結果を受信順のコピーとして返す

        Returns:
            list[RecognitionResult]: 確定済み結果
        """
        with self._condition:
            return list(self._finalized_results)

    def _close_recognition(self) -> None:
        with self._condition:
            self._closing = True
            self._ended = True
            self._finish_events()
            self._condition.notify_all()
        try:
            self._wrp.close()
        finally:
            if self._receiver is not None:
                self._receiver.join(timeout=2)


def _connect_websocket_transport(api_url: str, params: RecognitionParams) -> WebSocketTransport:
    """接続設定だけを汎用 WebSocket 層へ渡し接続する

    Args:
        api_url (str): ws / wss エンドポイント
        params (RecognitionParams): 解決済み認識設定

    Returns:
        WebSocketTransport: 接続済みトランスポート
    """
    transport = WebSocketTransport()
    transport.connect(
        api_url,
        connect_timeout_ms=params.connect_timeout,
        receive_timeout_ms=params.receive_timeout,
        proxy_server_name=params.proxy_server_name,
    )
    return transport


class StreamConnectionManager:
    """``client.stream()`` が返す接続コンテキストマネージャ

    ``__enter__`` で開始確認まで待ち、``__exit__`` で受信スレッドと接続を閉じる
    ``enter = __enter__`` の手動接続 API も提供する
    """

    def __init__(
        self, *, api_key: str, api_url: str, params: RecognitionParams, wrp_transport: WebSocketTransport | None = None
    ) -> None:
        """認識設定と任意のテスト用接続を保持する

        Args:
            api_key (str): 認証キー
            api_url (str): WebSocket URL
            params (RecognitionParams): 解決済みの設定
            wrp_transport (WebSocketTransport | None): 接続済みテストトランスポート
        """
        self._api_key = api_key
        self._api_url = api_url
        self._params = params
        self._wrp_transport = wrp_transport
        self._session: StreamSession | None = None

    def __enter__(self) -> StreamSession:
        """WebSocket 接続を開き、認識開始が確認されたセッションを返す

        Returns:
            StreamSession: 認識開始済みセッション
        """
        if self._session is not None:
            raise RecognitionError("Stream manager is already entered")
        transport = (
            self._wrp_transport if self._wrp_transport is not None else _connect_websocket_transport(self._api_url, self._params)
        )
        session = StreamSession(
            transport, finalize_timeout_ms=self._params.receive_timeout if self._params.receive_timeout > 0 else 60_000
        )
        self._session = session
        try:
            session._start_recognition(build_wrp_start_command(self._params, self._api_key))
        except BaseException:
            self._session = None
            session._close_recognition()
            raise
        return session

    enter = __enter__

    def __exit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: object | None) -> None:
        """受信待機を解除し接続とスレッドを閉じる

        Args:
            exc_type (type[BaseException] | None): コンテキスト内の例外型
            exc_val (BaseException | None): コンテキスト内の例外
            exc_tb (object | None): トレースバック
        """
        session, self._session = self._session, None
        if session is not None:
            with suppress(Exception):
                session._close_recognition()

    def __del__(self) -> None:
        """GC 時にもベストエフォートで切断する"""
        if getattr(self, "_session", None) is not None:
            self.__exit__(None, None, None)
