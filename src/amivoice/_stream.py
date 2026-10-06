"""s/p/e応答を受信し、終了応答まで認識結果を保つセッション管理"""

import math
import queue
import threading
from collections.abc import Iterator
from contextlib import suppress

from ._params import RecognitionParams
from ._request_parameters import build_start_command
from ._websocket_connection import WebSocketConnection, WebSocketTransport
from .exceptions import AmiVoiceError, AuthenticationError, ConfigurationError, RecognitionError
from .models import NotificationEvent, RecognitionResult, StreamEvent, UtteranceEvent, parse_result

_SENTINEL = object()


class StreamSession:
    """1つの認識セッション、イベント消費者は1つのスレッドで管理する"""

    def __init__(self, transport: WebSocketTransport, *, api_key: str, timeout: float = 60.0) -> None:
        """接続済みの通信処理を保持する

        Args:
            transport (WebSocketTransport): 接続済みのWebSocket
            api_key (str): 例外メッセージから除外する認証情報
            timeout (float): 開始と終了の最大待機秒数
        """
        self._transport = transport
        self._api_key = api_key
        self._timeout = timeout
        self._queue: queue.SimpleQueue[object] = queue.SimpleQueue()
        self._results: list[RecognitionResult] = []
        self._started = threading.Event()
        self._finished = threading.Event()
        self._ended = False
        self._error: AmiVoiceError | None = None
        self._thread: threading.Thread | None = None
        self._end_lock = threading.Lock()

    def start(self, command: str) -> None:
        """受信処理を開始し、sの成功応答を待つ

        Args:
            command (str): 認識開始コマンド

        Raises:
            AmiVoiceError: 開始要求や待機に失敗した場合
        """
        self._thread = threading.Thread(target=self._receive_events, name="amivoice-recognition", daemon=True)
        self._thread.start()
        try:
            self._transport.send_text(command)
            if not self._started.wait(self._timeout):
                raise RecognitionError("Timed out waiting for recognition start response")
            self._raise_error()
        except Exception:
            self.close()
            raise

    def _raise_error(self) -> None:
        if self._error is not None:
            raise self._error

    def _finish(self, error: AmiVoiceError | None = None) -> None:
        if self._finished.is_set():
            return
        self._error = error
        self._queue.put(_SENTINEL)
        self._finished.set()
        self._started.set()

    def _receive_events(self) -> None:
        try:
            while not self._finished.is_set():
                packet = self._transport.receive_text()
                if packet is None:
                    raise RecognitionError("WebSocket closed before recognition end response")
                self._handle_packet(packet)
        except Exception as exc:
            if not self._finished.is_set():
                if isinstance(exc, AmiVoiceError):
                    error = type(exc)(str(exc).replace(self._api_key, "[redacted]"))
                else:
                    error = RecognitionError("WebSocket recognition event processing failed")
                self._finish(error)

    def _handle_packet(self, packet: str) -> None:
        if not packet or (len(packet) > 1 and packet[1] != " "):
            raise RecognitionError("WebSocket recognition packet format is invalid")
        kind, payload = packet[0], packet[2:]
        if kind in ("s", "p", "e"):
            self._handle_response(kind, payload)
            return
        if not self._started.is_set():
            raise RecognitionError("WebSocket recognition event arrived before start response")
        if kind in ("A", "R"):
            result = parse_result(payload, raise_on_error=False)
            if any(not isinstance(result.data.get(key), str) for key in ("code", "message", "text")):
                raise RecognitionError("WebSocket final result is missing code, message or text")
            self._results.append(result)
            self._queue.put(StreamEvent("final", text=result.text, result=result))
        elif kind == "U":
            result = parse_result(payload, raise_on_error=False)
            self._queue.put(StreamEvent("partial", text=result.text))
        elif kind in ("S", "E"):
            timestamp = int(payload)
            if timestamp < 0:
                raise RecognitionError("WebSocket utterance time must not be negative")
            event_type = "started" if kind == "S" else "ended"
            public_type = "utterance_started" if kind == "S" else "utterance_ended"
            self._queue.put(StreamEvent(public_type, utterance=UtteranceEvent(event_type, timestamp)))
        elif kind == "C":
            if payload:
                raise RecognitionError("WebSocket recognition start event must not have a payload")
            self._queue.put(StreamEvent("notification", notification=NotificationEvent("C", "")))
        elif kind != "G":
            raise RecognitionError("Unsupported WebSocket recognition event")

    def _handle_response(self, kind: str, payload: str) -> None:
        if payload:
            message = f"{kind} {payload}".replace(self._api_key, "[redacted]")
            if "service authorization" in payload and kind == "s":
                raise AuthenticationError(message)
            raise RecognitionError(message)
        if kind == "s":
            if self._started.is_set():
                raise RecognitionError("Duplicate WebSocket start response")
            self._started.set()
        elif kind == "e":
            if not self._ended:
                raise RecognitionError("Unexpected WebSocket end response")
            self._finish()
        # 概要例にはp成功応答も登場するため受け取っても待機・状態変更しない

    def write(self, chunk: bytes) -> None:
        """認識開始後だけ音声を送信する

        Args:
            chunk (bytes): 音声の一部

        Raises:
            RecognitionError: 終了後や非接続時の送信
        """
        self._raise_error()
        if self._ended or self._finished.is_set() or not self._started.is_set():
            raise RecognitionError("Cannot write to an ended or inactive session")
        if not isinstance(chunk, bytes):
            raise ConfigurationError("Stream audio must be bytes")
        self._transport.send_audio(chunk)

    def poll(self) -> Iterator[StreamEvent]:
        """到着済みイベントを返し、通信エラーも伝える

        Yields:
            StreamEvent: 到着した順のイベント
        """
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                self._raise_error()
                return
            if item is _SENTINEL:
                self._raise_error()
                return
            if isinstance(item, StreamEvent):
                yield item

    def events(self, *, timeout: float | None = None) -> Iterator[StreamEvent]:
        """イベントを待機し、終了応答又は通信エラーで終える

        Args:
            timeout (float | None): 次のイベントを待つ最大秒数

        Yields:
            StreamEvent: 到着した順のイベント

        Raises:
            RecognitionError: 待機がタイムアウトした場合
        """
        while True:
            if self._finished.is_set() and self._queue.empty():
                self._raise_error()
                return
            try:
                item = self._queue.get(timeout=timeout)
            except queue.Empty:
                raise RecognitionError("Timed out waiting for stream event") from None
            if item is _SENTINEL:
                self._raise_error()
                return
            if isinstance(item, StreamEvent):
                yield item

    def end(self, *, timeout: float | None = None) -> None:
        """eの応答まで途中結果と確定結果を受信する

        Args:
            timeout (float | None): 終了応答を待つ最大秒数、省略時は既定値

        Raises:
            RecognitionError: 終了失敗又は待機タイムアウト
        """
        wait = self._timeout if timeout is None else timeout
        if isinstance(wait, bool) or not isinstance(wait, (int, float)) or not math.isfinite(wait) or wait < 0:
            raise ConfigurationError("Stream end timeout must be a finite non-negative number")
        with self._end_lock:
            self._raise_error()
            if self._finished.is_set():
                return
            if not self._ended:
                self._ended = True
                self._transport.send_text("e")
        if not self._finished.wait(wait):
            self._finish(RecognitionError("Timed out waiting for recognition end response"))
            self.close()
        self._raise_error()

    def results(self) -> list[RecognitionResult]:
        """確定済みの結果を到着順で返す

        Returns:
            list[RecognitionResult]: 結果一覧のコピー
        """
        return list(self._results)

    def close(self) -> None:
        """切断して受信スレッドを終了する"""
        if not self._finished.is_set():
            self._finish(RecognitionError("Recognition session was closed before end response"))
        self._transport.close()
        if self._thread is not None and threading.current_thread() is not self._thread:
            self._thread.join(timeout=2)


class StreamConnectionManager:
    """withで接続を確立し、例外時も確実に切断する"""

    def __init__(
        self, *, api_key: str, api_url: str, params: RecognitionParams, wrp_transport: WebSocketTransport | None = None
    ) -> None:
        """接続設定を保持し、通信はenter時まで行わない

        Args:
            api_key (str): 認証情報
            api_url (str): WebSocket接続先
            params (RecognitionParams): 認識設定
            wrp_transport (WebSocketTransport | None): テスト用通信処理
        """
        self._api_key = api_key
        self._api_url = api_url
        self._params = params
        self._transport = wrp_transport
        self._session: StreamSession | None = None

    def __enter__(self) -> StreamSession:
        """接続とs応答の確認を行う

        Returns:
            StreamSession: 認識開始が成功したセッション
        """
        if self._session is not None:
            raise ConfigurationError("Stream manager is already entered")
        command = build_start_command(self._params)
        transport = self._transport if self._transport is not None else WebSocketConnection()
        wait = self._params.receive_timeout / 1000 or 60.0  # クライアント側の開始・終了待機上限
        session = StreamSession(transport, api_key=self._api_key, timeout=wait)
        try:
            transport.connect(self._api_url, self._api_key, self._params)
            session.start(command)
        except Exception:
            transport.close()
            raise
        self._session = session
        return session

    enter = __enter__

    def __exit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: object | None) -> None:
        """正常終了時はe応答を待ち、例外時は直ちに切断する

        Args:
            exc_type (type[BaseException] | None): 例外型
            exc_val (BaseException | None): 例外
            exc_tb (object | None): トレースバック
        """
        session, self._session = self._session, None
        if session is not None:
            try:
                if exc_type is None:
                    session.end()
            finally:
                session.close()

    def __del__(self) -> None:
        """未終了セッションのソケットを回収する"""
        with suppress(Exception):
            if self._session is not None:
                self._session.close()
