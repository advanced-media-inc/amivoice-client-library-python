import base64
import socket
import ssl
import threading
from contextlib import suppress
from urllib.parse import quote

from .Hrp import Hrp


def bq(s: str) -> bytes:
    """文字列を UTF-8 で URL エンコードし、バイト列を返す

    Args:
        s: エンコード対象の文字列

    Returns:
        URL エンコードされたバイト列
    """
    return quote(s, "UTF-8").encode()


class Hrp_(Hrp):
    """HTTP 音声認識サーバとの実際の通信を担当する Hrp の実装クラス"""

    _serverCertificateVerification = True

    @staticmethod
    def _basic(userName: str, password: str) -> bytes:
        """Basic 認証用の Base64 エンコード文字列を生成する

        Args:
            userName: ユーザー名
            password: パスワード

        Returns:
            Base64 エンコードされた認証情報のバイト列
        """
        return base64.b64encode((userName + ":" + password).encode())

    def __init__(self) -> None:
        """インスタンスを初期化する"""
        super().__init__()
        self.host_ = None
        self.resource_ = None
        self.proxyUserName_ = None
        self.proxyPassword_ = None
        self.socket_ = None
        self.requestBodyChunked_ = None
        self.requestBodyParted_ = None
        self.requestBodyPartedOffset_ = 0
        self.inData_ = bytearray()
        self.inDataBytes_ = 0
        self.inDataBytes__ = 0
        self.inDataEncoding__ = None
        self.result__ = None
        self.thread_ = None

    def connect_(self, serverURL: str, proxyServerName: str | None, connectTimeout: int, receiveTimeout: int) -> None:  # noqa: PLR0912,PLR0915
        """HTTP/HTTPS サーバへの接続を確立する

        Args:
            serverURL: 接続先のサーバ URL
            proxyServerName: プロキシサーバ名（ポートや認証情報含む）。None の場合はプロキシを使用しない
            connectTimeout: 接続タイムアウト（ミリ秒）
            receiveTimeout: 受信タイムアウト（ミリ秒）

        Raises:
            ValueError: URL またはポートで解析エラーが発生した場合
            OSError: 接続またはハンドシェイクに失敗した場合
        """
        colonDoubleSlashIndex = serverURL.find("://")
        if colonDoubleSlashIndex == -1:
            raise ValueError("Invalid server URL")
        scheme = serverURL[:colonDoubleSlashIndex]
        if scheme not in {"http", "https"}:
            raise ValueError("Invalid scheme: " + scheme)
        slashIndex = serverURL.find("/", colonDoubleSlashIndex + 3)
        if slashIndex != -1:
            hostName = serverURL[colonDoubleSlashIndex + 3 : slashIndex]
            self.resource_ = serverURL[slashIndex:]
        else:
            hostName = serverURL[colonDoubleSlashIndex + 3 :]
            self.resource_ = "/"
        colonIndex = hostName.find(":", hostName.find("]") + 1)
        if colonIndex != -1:
            try:
                port = int(hostName[colonIndex + 1 :])
            except ValueError:
                raise ValueError("Invalid port: " + hostName[colonIndex + 1 :]) from None
            hostName = hostName[:colonIndex]
        elif scheme == "https":
            port = 443
        else:
            port = 80
        if port == 80:
            self.host_ = hostName
        else:
            self.host_ = hostName + ":" + str(port)
        proxyHostName = None
        proxyPort = 0
        self.proxyUserName_ = None
        self.proxyPassword_ = None
        if proxyServerName is not None:
            proxyHostName = proxyServerName
            atIndex = proxyHostName.rfind("@")
            if atIndex != -1:
                colonIndex = proxyHostName.find(":")
                if colonIndex != -1 and colonIndex < atIndex:
                    self.proxyUserName_ = proxyHostName[:colonIndex]
                    self.proxyPassword_ = proxyHostName[colonIndex + 1 : atIndex]
                    proxyHostName = proxyHostName[atIndex + 1 :]
            colonIndex = proxyHostName.find(":", proxyHostName.find("]") + 1)
            if colonIndex != -1:
                try:
                    proxyPort = int(proxyHostName[colonIndex + 1 :])
                except ValueError:
                    raise ValueError("Invalid port: " + proxyHostName[colonIndex + 1 :]) from None
                proxyHostName = proxyHostName[:colonIndex]
            else:
                proxyPort = 80
        if proxyServerName is not None:
            if connectTimeout > 0:
                self.socket_ = socket.create_connection((proxyHostName, proxyPort), connectTimeout / 1000.0)
            else:
                self.socket_ = socket.create_connection((proxyHostName, proxyPort))
        elif connectTimeout > 0:
            self.socket_ = socket.create_connection((hostName, port), connectTimeout / 1000.0)
        else:
            self.socket_ = socket.create_connection((hostName, port))
        if receiveTimeout > 0:
            self.socket_.settimeout(receiveTimeout / 1000.0)
        else:
            self.socket_.settimeout(None)
        if proxyServerName is not None:
            if scheme == "https":
                proxyRequestHeader = bytearray()
                proxyRequestHeader.extend(b"CONNECT ")
                proxyRequestHeader.extend(hostName.encode())
                proxyRequestHeader.extend(b":")
                proxyRequestHeader.extend(str(port).encode())
                proxyRequestHeader.extend(b" HTTP/1.1\r\n")
                proxyRequestHeader.extend(b"Host: ")
                proxyRequestHeader.extend(self.host_.encode())
                proxyRequestHeader.extend(b"\r\n")
                proxyRequestHeader.extend(b"User-Agent: ")
                proxyRequestHeader.extend(Hrp.getVersion().encode())
                proxyRequestHeader.extend(b"\r\n")
                if self.proxyUserName_ is not None and self.proxyPassword_ is not None:
                    proxyRequestHeader.extend(b"Proxy-Authorization: Basic ")
                    proxyRequestHeader.extend(Hrp_._basic(self.proxyUserName_, self.proxyPassword_))
                    proxyRequestHeader.extend(b"\r\n")
                    self.proxyUserName_ = None
                    self.proxyPassword_ = None
                proxyRequestHeader.extend(b"\r\n")
                self.socket_.send(proxyRequestHeader)
                proxyResponseHeader = bytearray()
                CRLFCRLF = 0
                c = self.socket_.recv(1)
                while c:
                    proxyResponseHeader.extend(c)
                    CRLFCRLF &= 0x00FFFFFF
                    CRLFCRLF <<= 8
                    CRLFCRLF |= ord(c)
                    if CRLFCRLF == 0x0D0A0D0A:
                        break
                    c = self.socket_.recv(1)
                if (
                    proxyResponseHeader[8] != 0x20  # ' '
                    or proxyResponseHeader[9] != 0x32  # '2'
                    or proxyResponseHeader[10] != 0x30  # '0'
                    or proxyResponseHeader[11] != 0x30  # '0'
                    or proxyResponseHeader[12] != 0x20
                ):  # ' '
                    raise OSError("Invalid response code: " + proxyResponseHeader[9:12].decode())
            else:
                self.resource_ = serverURL
        if scheme == "https":
            try:
                context = ssl.create_default_context()
                if not Hrp_._serverCertificateVerification:
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                self.socket_ = context.wrap_socket(self.socket_, server_hostname=hostName)
            except Exception:
                self.socket_.close()
                self.socket_ = None
                raise
        self.thread_ = threading.Thread(target=self.run)
        self.thread_.start()

    def disconnect_(self) -> None:
        """接続を切断する"""
        if self.socket_ is not None:
            try:
                self.socket_.shutdown(socket.SHUT_RDWR)
                self.socket_.close()
            except OSError:
                pass
        if self.thread_ is not None:
            with suppress(Exception):
                self.thread_.join()
            self.thread_ = None
        self.socket_ = None

    def isConnected_(self) -> bool:
        """接続が確立しているかどうかを返す

        Returns:
            接続が確立している場合は True、それ以外は False
        """
        return self.socket_ is not None

    def sendRequestHeader_(  # noqa: PLR0912,PLR0913,PLR0915
        self,
        domainId: str,
        codec: str | None,
        resultType: str | None,
        resultEncoding: str | None,
        serviceAuthorization: str | None,
        voiceDetection: str | None,
        acceptTopic: str | None,
        contentType: str | None,
        accept: str | None,
        requestType: str,
        dataBytes: int,
    ) -> None:
        """HTTP リクエストヘッダを構築して送信する

        Args:
            domainId: ドメイン ID 文字列
            codec: 音声コーデック文字列
            resultType: 認識結果タイプ文字列
            resultEncoding: 認識結果の文字エンコーディング文字列
            serviceAuthorization: サービス認証キー文字列
            voiceDetection: 発話区間検出パラメータ文字列
            acceptTopic: Accept-Topic ヘッダ文字列
            contentType: Content-Type ヘッダ文字列
            accept: Accept ヘッダ文字列
            requestType: リクエストタイプ文字列
            dataBytes: 音声データのバイト数
        """
        self.requestBodyChunked_ = None
        self.requestBodyParted_ = None
        self.requestBodyPartedOffset_ = 0
        self.inDataBytes_ = 0
        self.inDataBytes__ = 0
        self.inDataEncoding__ = None
        self.result__ = ""
        requestHeader = bytearray()
        requestHeader.extend(b"POST ")
        requestHeader.extend(self.resource_.encode())
        if requestType[0] != "m":
            delimiter = 0x3F if self.resource_.find("?") == -1 else 0x26  # '?' '&'
            if domainId is not None and len(domainId) > 0:
                requestHeader.append(delimiter)
                delimiter = 0x26  # '&'
                requestHeader.extend(b"d=")
                requestHeader.extend(bq(domainId))
            if codec is not None and len(codec) > 0:
                requestHeader.append(delimiter)
                delimiter = 0x26  # '&'
                requestHeader.extend(b"c=")
                requestHeader.extend(bq(codec))
            if resultType is not None and len(resultType) > 0:
                requestHeader.append(delimiter)
                delimiter = 0x26  # '&'
                requestHeader.extend(b"r=")
                requestHeader.extend(bq(resultType))
            if resultEncoding is not None and len(resultEncoding) > 0:
                requestHeader.append(delimiter)
                delimiter = 0x26  # '&'
                requestHeader.extend(b"e=")
                requestHeader.extend(bq(resultEncoding))
            if serviceAuthorization is not None and len(serviceAuthorization) > 0:
                requestHeader.append(delimiter)
                delimiter = 0x26  # '&'
                requestHeader.extend(b"u=")
                requestHeader.extend(bq(serviceAuthorization))
            if voiceDetection is not None:
                requestHeader.append(delimiter)
                delimiter = 0x26  # '&'
                requestHeader.extend(b"v=")
                requestHeader.extend(bq(voiceDetection))
        else:
            requestBody = bytearray()
            if domainId is not None and len(domainId) > 0:
                requestBody.extend(b'\r\n--1234567890ABCDEFGHIJ\r\nContent-Disposition: form-data; name="d"\r\n\r\n')
                requestBody.extend(domainId.encode("UTF-8"))
            if codec is not None and len(codec) > 0:
                requestBody.extend(b'\r\n--1234567890ABCDEFGHIJ\r\nContent-Disposition: form-data; name="c"\r\n\r\n')
                requestBody.extend(codec.encode("UTF-8"))
            if resultType is not None and len(resultType) > 0:
                requestBody.extend(b'\r\n--1234567890ABCDEFGHIJ\r\nContent-Disposition: form-data; name="r"\r\n\r\n')
                requestBody.extend(resultType.encode("UTF-8"))
            if resultEncoding is not None and len(resultEncoding) > 0:
                requestBody.extend(b'\r\n--1234567890ABCDEFGHIJ\r\nContent-Disposition: form-data; name="e"\r\n\r\n')
                requestBody.extend(resultEncoding.encode("UTF-8"))
            if serviceAuthorization is not None and len(serviceAuthorization) > 0:
                requestBody.extend(b'\r\n--1234567890ABCDEFGHIJ\r\nContent-Disposition: form-data; name="u"\r\n\r\n')
                requestBody.extend(serviceAuthorization.encode("UTF-8"))
            if voiceDetection is not None:
                requestBody.extend(b'\r\n--1234567890ABCDEFGHIJ\r\nContent-Disposition: form-data; name="v"\r\n\r\n')
                requestBody.extend(voiceDetection.encode("UTF-8"))
            requestBody.extend(b'\r\n--1234567890ABCDEFGHIJ\r\nContent-Disposition: form-data; name="a"\r\n\r\n')
            requestBody.extend(b"\r\n--1234567890ABCDEFGHIJ--\r\n")
            self.requestBodyParted_ = requestBody  # [70+n+][70+n+][70+n+][70+n+][70+n+][70+n+]70+28 bytes
        requestHeader.extend(b" HTTP/1.1\r\n")
        requestHeader.extend(b"Host: ")
        requestHeader.extend(self.host_.encode())
        requestHeader.extend(b"\r\n")
        requestHeader.extend(b"User-Agent: ")
        requestHeader.extend(Hrp.getVersion().encode())
        requestHeader.extend(b"\r\n")
        if self.proxyUserName_ is not None and self.proxyPassword_ is not None:
            requestHeader.extend(b"Proxy-Authorization: Basic ")
            requestHeader.extend(Hrp_._basic(self.proxyUserName_, self.proxyPassword_))
            requestHeader.extend(b"\r\n")
        if requestType[1] != "c":
            requestHeader.extend(b"Content-Length: ")
            if self.requestBodyParted_ is None:
                requestHeader.extend(str(dataBytes).encode())
            else:
                requestHeader.extend(str(dataBytes + len(self.requestBodyParted_)).encode())
            requestHeader.extend(b"\r\n")
        else:
            self.requestBodyChunked_ = b"0\r\n\r\n"
            requestHeader.extend(b"Transfer-Encoding: chunked\r\n")
        if self.requestBodyParted_ is None:
            if acceptTopic is not None and len(acceptTopic) > 0:
                requestHeader.extend(b"Accept-Topic: ")
                requestHeader.extend(acceptTopic.encode())
                requestHeader.extend(b"\r\n")
            if contentType is not None and len(contentType) > 0:
                requestHeader.extend(b"Content-Type: ")
                requestHeader.extend(contentType.encode())
                requestHeader.extend(b"\r\n")
            if accept is not None and len(accept) > 0:
                requestHeader.extend(b"Accept: ")
                requestHeader.extend(accept.encode())
                requestHeader.extend(b"\r\n")
        else:
            requestHeader.extend(b"Content-Type: multipart/form-data; boundary=1234567890ABCDEFGHIJ\r\n")
        requestHeader.extend(b"\r\n")
        self.socket_.send(requestHeader)

    def sendRequestBody_(self, data: bytes | None, dataOffset: int, dataBytes: int) -> None:
        """HTTP リクエストボディ（音声データ）を送信する

        Args:
            data: 送信する音声データのバイト列。None の場合は終端データを送信する
            dataOffset: data 内の開始オフセット
            dataBytes: 送信するバイト数
        """
        if data is not None and dataBytes > 0:
            if self.requestBodyParted_ is not None and self.requestBodyPartedOffset_ == 0:
                self.requestBodyPartedOffset_ = len(self.requestBodyParted_) - 28
                if self.requestBodyChunked_ is not None:
                    self.socket_.send(format(self.requestBodyPartedOffset_, "x").encode())
                    self.socket_.send(self.requestBodyChunked_[1:3])
                self.socket_.send(self.requestBodyParted_[: self.requestBodyPartedOffset_])
                if self.requestBodyChunked_ is not None:
                    self.socket_.send(self.requestBodyChunked_[3:5])
            if self.requestBodyChunked_ is not None:
                self.socket_.send(format(dataBytes, "x").encode())
                self.socket_.send(self.requestBodyChunked_[1:3])
            self.socket_.send(data[dataOffset : dataOffset + dataBytes])
            if self.requestBodyChunked_ is not None:
                self.socket_.send(self.requestBodyChunked_[3:5])
        elif self.requestBodyParted_ is not None:
            if self.requestBodyChunked_ is not None:
                self.socket_.send(
                    format(
                        len(self.requestBodyParted_) - self.requestBodyPartedOffset_,
                        "x",
                    ).encode()
                )
                self.socket_.send(self.requestBodyChunked_[1:3])
            self.socket_.send(self.requestBodyParted_[self.requestBodyPartedOffset_ :])
            if self.requestBodyChunked_ is not None:
                self.socket_.send(self.requestBodyChunked_[3:5])
                self.socket_.send(self.requestBodyChunked_)
        elif self.requestBodyChunked_ is not None:
            self.socket_.send(self.requestBodyChunked_)

    def run(self) -> None:
        """スレッド内でサーバからのレスポンスを受信し続けるメインループ"""
        try:
            while True:
                sessionId = self.receiveResponseHeader_()
                super().onOpen_(sessionId)
                if self.inDataBytes__ > 0:
                    self.receiveResponseBody_()
                    crlfIndex = self.result__.find("\r\n")
                    while crlfIndex != -1:
                        result = self.result__[:crlfIndex]
                        super().onMessage_(result)
                        self.result__ = self.result__[crlfIndex + 2 :]
                        crlfIndex = self.result__.find("\r\n")
                else:
                    while self.receiveChunkedResponseBody_():
                        crlfIndex = self.result__.find("\r\n")
                        while crlfIndex != -1:
                            result = self.result__[:crlfIndex]
                            super().onMessage_(result)
                            self.result__ = self.result__[crlfIndex + 2 :]
                            crlfIndex = self.result__.find("\r\n")
                super().onClose_()
        except OSError as e:
            super().onError_(e)

    def receiveResponseHeader_(self) -> str:
        """HTTP レスポンスヘッダを受信しセッション ID を返す

        Returns:
            レスポンスヘッダから取得したセッション ID

        Raises:
            OSError: レスポンスコードが不正またはストリームが予期せず終了した場合
        """
        responseHeaderBytes = self.read_CRLFCRLF_()
        if responseHeaderBytes == -1:
            raise OSError("Unexpected end of stream")
        responseHeader = self.inData_[:responseHeaderBytes]
        if (
            responseHeader[8] != 0x20  # ' '
            or responseHeader[9] != 0x32  # '2'
            or responseHeader[10] != 0x30  # '0'
            or responseHeader[11] != 0x30  # '0'
            or responseHeader[12] != 0x20
        ):  # ' '
            raise OSError("Invalid response code: " + responseHeader[9:12].decode())
        index1 = responseHeader.find(b"\r\nX-Session-ID: ")
        if index1 == -1:
            raise OSError("Missing session id")
        index1 += 16
        index2 = responseHeader.find(b"\r\n", index1)
        if index2 == -1:
            raise OSError("Missing session id")
        sessionId = responseHeader[index1:index2].decode()
        self.inDataEncoding__ = "UTF-8"
        index1 = responseHeader.find(b"\r\nContent-Type: ")
        if index1 != -1:
            index1 += 16
            index2 = responseHeader.find(b"\r\n", index1)
            if index2 != -1:
                index3 = responseHeader.find(b"; charset=", index1)
                if index3 != -1 and index3 < index2:
                    index3 += 10
                    self.inDataEncoding__ = responseHeader[index3:index2].decode().upper()
                    if self.inDataEncoding__ == "SHIFT_JIS":
                        self.inDataEncoding__ = "MS932"
        index1 = responseHeader.find(b"\r\nContent-Length: ")
        if index1 != -1:
            index1 += 18
            index2 = responseHeader.find(b"\r\n", index1)
            if index2 != -1:
                try:
                    self.inDataBytes__ = int(responseHeader[index1:index2].decode())
                except ValueError:
                    raise OSError("Invalid content length: " + responseHeader[index1:index2].decode()) from None
        self.shift_(responseHeaderBytes)
        return sessionId

    def receiveResponseBody_(self) -> None:
        """非チャンクの HTTP レスポンスボディを受信する

        Raises:
            OSError: ストリームが予期せず終了した場合
        """
        if not self.read_(self.inDataBytes__):
            raise OSError("Unexpected end of stream")
        self.result_(self.inDataBytes__)
        self.shift_(self.inDataBytes__)

    def receiveChunkedResponseBody_(self) -> bool:
        """HTTP レスポンスボディを 1 チャンク受信する

        Returns:
            続きのチャンクがある場合は True、最後のチャンク（サイズ 0）の場合は False

        Raises:
            OSError: ストリームが予期せず終了した場合
        """
        chunkedResponseHeaderBytes = self.read_CRLF_()
        if chunkedResponseHeaderBytes == -1:
            raise OSError("Unexpected end of stream")
        self.inDataBytes__ = 0
        for i in range(chunkedResponseHeaderBytes):
            c = self.inData_[i]
            if c >= 0x30 and c <= 0x39:  # '0' '9'
                self.inDataBytes__ <<= 4
                self.inDataBytes__ += c - 0x30  # '0'
            elif c >= 0x41 and c <= 0x46:  # 'A' 'F'
                self.inDataBytes__ <<= 4
                self.inDataBytes__ += c - 0x41 + 10  # 'A'
            elif c >= 0x61 and c <= 0x66:  # 'a' 'f'
                self.inDataBytes__ <<= 4
                self.inDataBytes__ += c - 0x61 + 10  # 'a'
            else:
                break
        self.shift_(chunkedResponseHeaderBytes)
        if self.inDataBytes__ == 0:
            if not self.read_(2):
                raise OSError("Unexpected end of stream")
            self.shift_(2)
            return False
        if not self.read_(self.inDataBytes__ + 2):
            raise OSError("Unexpected end of stream")
        self.result_(self.inDataBytes__)
        self.shift_(self.inDataBytes__ + 2)
        return True

    def read_CRLFCRLF_(self) -> int:
        """受信バッファから CRLFCRLF を探し、その位置までのバイト数を返す

        Returns:
            CRLFCRLF の後のバイト位置。ストリームが終了した場合は -1
        """
        inDataBytes = self.inData_.find(b"\r\n\r\n")
        while inDataBytes == -1:
            inData = self.socket_.recv(4096)
            if not inData:
                return -1
            self.inData_ += inData
            self.inDataBytes_ += len(inData)
            inDataBytes = self.inData_.find(b"\r\n\r\n")
        return inDataBytes + 4

    def read_CRLF_(self) -> int:
        """受信バッファから CRLF を探し、その位置までのバイト数を返す

        Returns:
            CRLF の後のバイト位置。ストリームが終了した場合は -1
        """
        inDataBytes = self.inData_.find(b"\r\n")
        while inDataBytes == -1:
            inData = self.socket_.recv(4096)
            if not inData:
                return -1
            self.inData_ += inData
            self.inDataBytes_ += len(inData)
            inDataBytes = self.inData_.find(b"\r\n")
        return inDataBytes + 2

    def read_(self, inDataBytes: int) -> bool:
        """指定バイト数のデータがバッファに満たされるまで読み込む

        Args:
            inDataBytes: 必要なバイト数

        Returns:
            必要バイト数を読み込めた場合は True、ストリーム終了で読み込めなかった場合は False
        """
        while self.inDataBytes_ < inDataBytes:
            inData = self.socket_.recv(inDataBytes - self.inDataBytes_)
            if not inData:
                return False
            self.inData_ += inData
            self.inDataBytes_ += len(inData)
        return True

    def result_(self, inDataBytes: int) -> None:
        """受信バッファの先頭から指定バイト数をデコードして結果文字列に追加する

        Args:
            inDataBytes: デコードするバイト数
        """
        try:
            result = self.inData_[:inDataBytes].decode(self.inDataEncoding__)
        except (LookupError, UnicodeDecodeError):
            result = self.inData_[:inDataBytes].decode()
        self.result__ += result

    def shift_(self, inDataBytes: int) -> None:
        """受信バッファの先頭から指定バイト数を移動する

        Args:
            inDataBytes: 移動するバイト数
        """
        self.inDataBytes_ -= inDataBytes
        self.inData_[:inDataBytes] = []
