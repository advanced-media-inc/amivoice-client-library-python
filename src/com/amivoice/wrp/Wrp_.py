import base64
import random
import socket
import ssl
import threading
from contextlib import suppress
from typing import ClassVar

from .Wrp import Wrp


class Wrp_(Wrp):
    """WebSocket 音声認識サーバとの実際の通信を担当する Wrp の実装クラス"""

    _serverCertificateVerification = True

    _base64Table: ClassVar[tuple[int, ...]] = (
        0x41,
        0x42,
        0x43,
        0x44,
        0x45,
        0x46,
        0x47,
        0x48,  # 'A' 'B' 'C' 'D' 'E' 'F' 'G' 'H'
        0x49,
        0x4A,
        0x4B,
        0x4C,
        0x4D,
        0x4E,
        0x4F,
        0x50,  # 'I' 'J' 'K' 'L' 'M' 'N' 'O' 'P'
        0x51,
        0x52,
        0x53,
        0x54,
        0x55,
        0x56,
        0x57,
        0x58,  # 'Q' 'R' 'S' 'T' 'U' 'V' 'W' 'X'
        0x59,
        0x5A,
        0x61,
        0x62,
        0x63,
        0x64,
        0x65,
        0x66,  # 'Y' 'Z' 'a' 'b' 'c' 'd' 'e' 'f'
        0x67,
        0x68,
        0x69,
        0x6A,
        0x6B,
        0x6C,
        0x6D,
        0x6E,  # 'g' 'h' 'i' 'j' 'k' 'l' 'm' 'n'
        0x6F,
        0x70,
        0x71,
        0x72,
        0x73,
        0x74,
        0x75,
        0x76,  # 'o' 'p' 'q' 'r' 's' 't' 'u' 'v'
        0x77,
        0x78,
        0x79,
        0x7A,
        0x30,
        0x31,
        0x32,
        0x33,  # 'w' 'x' 'y' 'z' '0' '1' '2' '3'
        0x34,
        0x35,
        0x36,
        0x37,
        0x38,
        0x39,
        0x2B,
        0x2F,  # '4' '5' '6' '7' '8' '9' '+' '/'
    )

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
        self.socket_ = None
        self.outData_ = bytearray(10 + 1 + 4096)
        self.inData_ = bytearray()
        self.inDataBytes_ = 0
        self.result__ = None
        self.thread_ = None

    def connect_(self, serverURL: str, proxyServerName: str | None, connectTimeout: int, receiveTimeout: int) -> None:  # noqa: PLR0912,PLR0915
        """WebSocket サーバへの接続とハンドシェイクを実行する

        Args:
            serverURL: 接続先の WebSocket サーバ URL
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
        if scheme not in {"ws", "wss"}:
            raise ValueError("Invalid scheme: " + scheme)
        slashIndex = serverURL.find("/", colonDoubleSlashIndex + 3)
        if slashIndex != -1:
            hostName = serverURL[colonDoubleSlashIndex + 3 : slashIndex]
            resource = serverURL[slashIndex:]
        else:
            hostName = serverURL[colonDoubleSlashIndex + 3 :]
            resource = "/"
        colonIndex = hostName.find(":", hostName.find("]") + 1)
        if colonIndex != -1:
            try:
                port = int(hostName[colonIndex + 1 :])
            except ValueError:
                raise ValueError("Invalid port: " + hostName[colonIndex + 1 :]) from None
            hostName = hostName[:colonIndex]
        elif scheme == "wss":
            port = 443
        else:
            port = 80
        if port == 80:
            host = hostName
        else:
            host = hostName + ":" + str(port)
        proxyHostName = None
        proxyPort = 0
        proxyUserName = None
        proxyPassword = None
        if proxyServerName is not None:
            proxyHostName = proxyServerName
            atIndex = proxyHostName.rfind("@")
            if atIndex != -1:
                colonIndex = proxyHostName.find(":")
                if colonIndex != -1 and colonIndex < atIndex:
                    proxyUserName = proxyHostName[:colonIndex]
                    proxyPassword = proxyHostName[colonIndex + 1 : atIndex]
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
            if scheme in {"ws", "wss"}:
                proxyRequestHeader = bytearray()
                proxyRequestHeader.extend(b"CONNECT ")
                proxyRequestHeader.extend(hostName.encode())
                proxyRequestHeader.extend(b":")
                proxyRequestHeader.extend(str(port).encode())
                proxyRequestHeader.extend(b" HTTP/1.1\r\n")
                proxyRequestHeader.extend(b"Host: ")
                proxyRequestHeader.extend(host.encode())
                proxyRequestHeader.extend(b"\r\n")
                proxyRequestHeader.extend(b"User-Agent: ")
                proxyRequestHeader.extend(Wrp.getVersion().encode())
                proxyRequestHeader.extend(b"\r\n")
                if proxyUserName is not None and proxyPassword is not None:
                    proxyRequestHeader.extend(b"Proxy-Authorization: Basic ")
                    proxyRequestHeader.extend(Wrp_._basic(proxyUserName, proxyPassword))
                    proxyRequestHeader.extend(b"\r\n")
                    proxyUserName = None
                    proxyPassword = None
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
                resource = serverURL
        if scheme == "wss":
            try:
                context = ssl.create_default_context()
                if not Wrp_._serverCertificateVerification:
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                self.socket_ = context.wrap_socket(self.socket_, server_hostname=hostName)
            except Exception:
                self.socket_.close()
                self.socket_ = None
                raise
        self.inDataBytes_ = 0
        self.result__ = None
        # -----------------------------------------------------------
        # GET <resource> HTTP/1.1
        # Host: <hostName>:<port>
        # Upgrade: websocket
        # Connection: upgrade
        # Sec-WebSocket-Key: ...
        #
        # -----------------------------------------------------------
        requestHeader = bytearray()
        requestHeader.extend(b"GET ")
        requestHeader.extend(resource.encode())
        requestHeader.extend(b" HTTP/1.1\r\n")
        requestHeader.extend(b"Host: ")
        requestHeader.extend(host.encode())
        requestHeader.extend(b"\r\n")
        requestHeader.extend(b"User-Agent: ")
        requestHeader.extend(Wrp.getVersion().encode())
        requestHeader.extend(b"\r\n")
        requestHeader.extend(b"Upgrade: websocket\r\n")
        requestHeader.extend(b"Connection: upgrade\r\n")
        requestHeader.extend(b"Sec-WebSocket-Key: ")
        for _i in range(0, 20, 4):
            twentyFourBits = random.randint(0, 0xFFFFFFFF) & 0x3F3F3F3F
            requestHeader.append(Wrp_._base64Table[(twentyFourBits >> 24) & 0x3F])
            requestHeader.append(Wrp_._base64Table[(twentyFourBits >> 16) & 0x3F])
            requestHeader.append(Wrp_._base64Table[(twentyFourBits >> 8) & 0x3F])
            requestHeader.append(Wrp_._base64Table[(twentyFourBits) & 0x3F])
        eightBits = random.randint(0, 0xFFFFFFFF) & 0x3F300000
        requestHeader.append(Wrp_._base64Table[(eightBits >> 24) & 0x3F])
        requestHeader.append(Wrp_._base64Table[(eightBits >> 16) & 0x3F])
        requestHeader.extend(b"==\r\n")
        requestHeader.extend(b"\r\n")
        self.socket_.send(requestHeader)
        # -----------------------------------------------------------
        # HTTP/1.1 101 Switching Protocols
        # Upgrade: websocket
        # Connection: upgrade
        # Sec-WebSocket-Accept: ...
        #
        # -----------------------------------------------------------
        responseHeaderBytes = self.read_CRLFCRLF_()
        if responseHeaderBytes == -1:
            raise OSError("Unexpected end of stream")
        responseHeader = self.inData_[:responseHeaderBytes]
        if (
            responseHeader[8] != 0x20  # ' '
            or responseHeader[9] != 0x31  # '1'
            or responseHeader[10] != 0x30  # '0'
            or responseHeader[11] != 0x31  # '1'
            or responseHeader[12] != 0x20
        ):  # ' '
            raise OSError("Handshake error (invalid response code: " + responseHeader[9:12].decode() + ")")
        self.shift_(responseHeaderBytes)
        self.thread_ = threading.Thread(target=self.run)
        self.thread_.start()

    def disconnect_(self) -> None:
        """接続を閉じる"""
        if self.socket_ is not None:
            try:
                self.outData_[0] = 0x88
                self.outData_[1] = 0x00
                self.socket_.send(self.outData_[:2])
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
        """接続中かどうかを返す

        Returns:
            接続中の場合は True、それ以外は False
        """
        return self.socket_ is not None

    def sendRequest_(self, data: bytes, dataOffset: int, dataBytes: int, command: int) -> None:
        """WebSocket フレーム標準に従ったデータフレームを送信する

        Args:
            data: 送信するデータのバイト列
            dataOffset: data 内の開始オフセット
            dataBytes: 送信するバイト数
            command: アプリケーション層のコマンドバイト（0 の場合はテキストフレーム）
        """
        # 0                   1                   2                   3
        # 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
        # +-+-+-+-+-------+-+-------------+-------------------------------+
        # |F|R|R|R| opcode|M| Payload len |    Extended payload length    |
        # |I|S|S|S|  (4)  |A|     (7)     |             (16/64)           |
        # |N|V|V|V|       |S|             |   (if payload len==126/127)   |
        # | |1|2|3|       |K|             |                               |
        # +-+-+-+-+-------+-+-------------+ - - - - - - - - - - - - - - - +
        # |     Extended payload length continued, if payload len == 127  |
        # + - - - - - - - - - - - - - - - +-------------------------------+
        # |                               |Masking-key, if MASK set to 1  |
        # +-------------------------------+-------------------------------+
        # | Masking-key (continued)       |          Payload Data         |
        # +-------------------------------- - - - - - - - - - - - - - - - +
        # :                     Payload Data continued ...                :
        # + - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - +
        # |                     Payload Data continued ...                |
        # +---------------------------------------------------------------+
        realDataBytes = (0 if command == 0 else 1) + dataBytes
        if len(self.outData_) < 10 + realDataBytes:
            self.outData_ = bytearray(10 + realDataBytes)
        outDataBytes = 0
        self.outData_[outDataBytes] = 0x80 | (0x01 if command == 0 else 0x02)
        outDataBytes += 1
        if realDataBytes < 126:
            self.outData_[outDataBytes] = realDataBytes
            outDataBytes += 1
        elif realDataBytes < 65536:
            self.outData_[outDataBytes] = 126
            outDataBytes += 1
            self.outData_[outDataBytes] = (realDataBytes >> 8) & 0xFF
            outDataBytes += 1
            self.outData_[outDataBytes] = (realDataBytes) & 0xFF
            outDataBytes += 1
        else:
            self.outData_[outDataBytes] = 127
            outDataBytes += 1
            self.outData_[outDataBytes] = 0
            outDataBytes += 1
            self.outData_[outDataBytes] = 0
            outDataBytes += 1
            self.outData_[outDataBytes] = 0
            outDataBytes += 1
            self.outData_[outDataBytes] = 0
            outDataBytes += 1
            self.outData_[outDataBytes] = (realDataBytes >> 24) & 0xFF
            outDataBytes += 1
            self.outData_[outDataBytes] = (realDataBytes >> 16) & 0xFF
            outDataBytes += 1
            self.outData_[outDataBytes] = (realDataBytes >> 8) & 0xFF
            outDataBytes += 1
            self.outData_[outDataBytes] = (realDataBytes) & 0xFF
            outDataBytes += 1
        if command == 0:
            pass
        else:
            self.outData_[outDataBytes] = command
            outDataBytes += 1
        self.outData_[outDataBytes : outDataBytes + dataBytes] = data[dataOffset : dataOffset + dataBytes]
        outDataBytes += dataBytes
        self.socket_.send(self.outData_[:outDataBytes])

    def run(self) -> None:
        """スレッド内でサーバからのレスポンスを受信し続けるメインループ"""
        try:
            super().onOpen_()
            while self.receiveResponse_():
                super().onMessage_(self.result__)
            super().onClose_()
        except OSError as e:
            super().onError_(e)

    def receiveResponse_(self) -> bool:
        """WebSocket フレームを 1 つ受信する

        Returns:
            フレームを正常受信した場合は True、接続が閉じた場合は False

        Raises:
            OSError: ストリームが予期せず終了した場合またはデータが不正な場合
        """
        # 0                   1                   2                   3
        # 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
        # +-+-+-+-+-------+-+-------------+-------------------------------+
        # |F|R|R|R| opcode|M| Payload len |    Extended payload length    |
        # |I|S|S|S|  (4)  |A|     (7)     |             (16/64)           |
        # |N|V|V|V|       |S|             |   (if payload len==126/127)   |
        # | |1|2|3|       |K|             |                               |
        # +-+-+-+-+-------+-+-------------+ - - - - - - - - - - - - - - - +
        # |     Extended payload length continued, if payload len == 127  |
        # + - - - - - - - - - - - - - - - +-------------------------------+
        # |                               |Masking-key, if MASK set to 1  |
        # +-------------------------------+-------------------------------+
        # | Masking-key (continued)       |          Payload Data         |
        # +-------------------------------- - - - - - - - - - - - - - - - +
        # :                     Payload Data continued ...                :
        # + - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - +
        # |                     Payload Data continued ...                |
        # +---------------------------------------------------------------+
        if not self.read_(2):
            if self.inDataBytes_ == 0:
                return False
            raise OSError("Unexpected end of stream")
        inDataType = self.inData_[0] & 0x0F
        inDataBytes = self.inData_[1] & 0x7F
        self.shift_(2)
        if inDataBytes == 126:
            if not self.read_(2):
                raise OSError("Unexpected end of stream")
            inDataBytes = ((self.inData_[0] & 0xFF) << 8) | (self.inData_[1] & 0xFF)
            self.shift_(2)
        elif inDataBytes == 127:
            if not self.read_(8):
                raise OSError("Unexpected end of stream")
            if (
                self.inData_[0] != 0
                or self.inData_[1] != 0
                or self.inData_[2] != 0
                or self.inData_[3] != 0
                or (self.inData_[4] & 0x80) != 0
            ):
                raise OSError("Invalid payload length: " + str(inDataBytes))
            inDataBytes = (
                ((self.inData_[4] & 0xFF) << 24)
                | ((self.inData_[5] & 0xFF) << 16)
                | ((self.inData_[6] & 0xFF) << 8)
                | (self.inData_[7] & 0xFF)
            )
            self.shift_(8)
        if inDataBytes < 0:
            raise OSError("Invalid payload length: " + str(inDataBytes))
        if not self.read_(inDataBytes):
            raise OSError("Unexpected end of stream")
        if inDataType == 1:
            self.result_(inDataBytes)
        elif inDataType == 10:
            self.result_(0)  # set inDataBytes to 0 so that the data is not treated as a recognition result...
        else:
            raise OSError("Detected invalid frame data (data type " + inDataType + ")")
        self.shift_(inDataBytes)
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
        """受信バッファの先頭から指定バイト数をデコードして結果文字列に設定する

        Args:
            inDataBytes: デコードするバイト数
        """
        if inDataBytes > 0 and self.inData_[inDataBytes - 1] == 0x0A:  # '\n'
            inDataBytes -= 1
            if inDataBytes > 0 and self.inData_[inDataBytes - 1] == 0x0D:  # '\r'
                inDataBytes -= 1
        try:
            result = self.inData_[:inDataBytes].decode("UTF-8")
        except UnicodeDecodeError:
            result = self.inData_[:inDataBytes].decode()
        self.result__ = result

    def shift_(self, inDataBytes: int) -> None:
        """受信バッファの先頭から指定バイト数を移動する

        Args:
            inDataBytes: 移動するバイト数
        """
        self.inDataBytes_ -= inDataBytes
        self.inData_[:inDataBytes] = []
