"""http.client に HTTP / チャンク転送を任せる HRP 認識クライアント"""

import http.client
from dataclasses import replace

from ._http_connection import create_http_connection
from ._params import RecognitionParams
from ._recognition_protocol import build_hrp_request
from .exceptions import AuthenticationError, ConnectionFailedError, RecognitionError
from .models import RecognitionResult, parse_result


class HttpRecognitionTransport:
    """呼び出しごとに独立した HTTP 接続で認識する（共有ソケットを持たない）"""

    def transcribe(
        self, api_url: str, api_key: str, params: RecognitionParams, audio: bytes, *, raise_on_error: bool = True
    ) -> RecognitionResult:
        """音声を送信し、最後の確定認識結果を返す

        Args:
            api_url (str): HRP エンドポイント
            api_key (str): 認証キー
            params (RecognitionParams): 解決済みの認識設定
            audio (bytes): 送信する音声
            raise_on_error (bool): サービスのエラー結果を例外にするか

        Returns:
            RecognitionResult: session ID を含む最後の確定結果

        Raises:
            ConnectionFailedError: 接続失敗
            AuthenticationError: HTTP 401 / 403
            RecognitionError: 送受信または応答解析の失敗
        """
        request = build_hrp_request(params, api_key, audio)
        connection, target = create_http_connection(
            api_url, connect_timeout_ms=params.connect_timeout, proxy_server_name=params.proxy_server_name
        )
        try:
            try:
                connection.connect()
            except (OSError, http.client.HTTPException) as exc:
                raise ConnectionFailedError("HRP connection failed") from exc
            if connection.sock is not None:
                connection.sock.settimeout(params.receive_timeout / 1000 if params.receive_timeout > 0 else None)
            try:
                # iterable を渡すことでチャンク転送のエンコードは標準ライブラリが担当する
                chunks = (request.body[offset : offset + 4096] for offset in range(0, len(request.body), 4096))
                connection.request("POST", target, body=chunks, headers=request.headers, encode_chunked=True)
                response = connection.getresponse()
                if response.status in {401, 403}:
                    raise AuthenticationError(f"HRP authentication failed: HTTP {response.status}")
                if response.status != 200:
                    raise RecognitionError(f"HRP request failed: HTTP {response.status}")
                encoding = response.headers.get_content_charset() or "UTF-8"
                raw = response.read().decode(encoding)
                session_id = response.getheader("X-Session-ID")
            except (OSError, http.client.HTTPException, UnicodeError, LookupError) as exc:
                raise RecognitionError("HRP response failed") from exc
            finalized = [line for line in raw.split("\r\n") if line and not line.endswith(("...", '..."}'))]
            if not finalized:
                raise RecognitionError("No recognition result was finalized")
            result = parse_result(finalized[-1], raise_on_error=False)
            result = replace(result, session_id=session_id)
            if result.is_error and raise_on_error:
                raise RecognitionError(str(result.data.get("message") or result.data.get("code") or result.data), result=result)
            return result
        finally:
            connection.close()
