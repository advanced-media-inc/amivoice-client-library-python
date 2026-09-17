import importlib
import sys
import threading
import time
from contextlib import suppress
from urllib.parse import quote

from .HrpListener import HrpListener


def q(s: str) -> str:
    """文字列を UTF-8 で URL エンコードする

    Args:
        s: エンコード対象の文字列

    Returns:
        URL エンコードされた文字列
    """
    return quote(s, encoding="UTF-8")


class Hrp:
    """HTTP 音声認識サーバと通信するためのクライアントクラス"""

    VERSION: str = f"Hrp/1.0.06 Python/{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]} ({sys.platform})"

    @staticmethod
    def getVersion() -> str:
        """アプリケーションのバージョン文字列を返す

        Returns:
            バージョン文字列
        """
        return Hrp.VERSION

    @staticmethod
    def construct(implementation: int = 0) -> "Hrp":
        """Hrp 実装インスタンスを生成するファクトリメソッド

        Args:
            implementation: 実装タイプ。0 はデフォルト実装（現在は 1）

        Returns:
            Hrp インスタンス

        Raises:
            ValueError: 未知の実装タイプが指定された場合
        """
        if implementation == 0:
            implementation = 1  # default implementation
        if implementation == 1:
            module = importlib.import_module(".Hrp_", __package__)
            return module.Hrp_()
        else:
            raise ValueError(f"Unknown implementation: {implementation}")

    def __init__(self) -> None:
        """インスタンスを初期化する"""
        self.condition_: threading.Condition = threading.Condition()
        self.listener_: HrpListener | None = None
        self.serverURL_: str | None = None
        self.proxyServerName_: str | None = None
        self.connectTimeout_: int = 0
        self.receiveTimeout_: int = 0
        self.grammarFileNames_: str | None = None
        self.completeTimeout_: str | None = None
        self.wildcardModelPenalty_: str | None = None
        self.mode_: str | None = None
        self.profileId_: str | None = None
        self.profileWords_: str | None = None
        self.segmenterType_: str | None = None
        self.segmenterProperties_: str | None = None
        self.audioFilterProperties_: str | None = None
        self.keepFillerToken_: str | None = None
        self.resultUpdatedInterval_: str | None = None
        self.maxDecodingTime_: str | None = None
        self.maxResponseTime_: str | None = None
        self.maxDecodingRate_: str | None = None
        self.targetResponseTime_: str | None = None
        self.targetDecodingRate_: str | None = None
        self.recognitionTimeout_: str | None = None
        self.extension_: str | None = None
        self.authorization_: str | None = None
        self.domainId_: str | None = None
        self.confidenceLevel_: str | None = None
        self.codec_: str | None = None
        self.resultType_: str | None = None
        self.resultEncoding_: str | None = None
        self.serviceAuthorization_: str | None = None
        self.voiceDetection_: str | None = None
        self.acceptTopic_: str | None = None
        self.contentType_: str | None = None
        self.accept_: str | None = None
        self.state_: int = -1
        self.lastMessage_: str = ""

    def setListener(self, listener: HrpListener | None) -> None:
        """イベントリスナを設定する

        Args:
            listener: 設定するリスナオブジェクト。None の場合はリスナを解除する
        """
        self.listener_ = listener

    def setServerURL(self, serverURL: str | None) -> None:
        """接続先の HTTP 音声認識サーバ URL を設定する

        Args:
            serverURL: サーバの URL 文字列
        """
        self.serverURL_ = serverURL

    def setProxyServerName(self, proxyServerName: str | None) -> None:
        """プロキシサーバ名を設定する

        Args:
            proxyServerName: プロキシサーバのホスト名（ポート含む）。None の場合はプロキシを使用しない
        """
        self.proxyServerName_ = proxyServerName

    def setConnectTimeout(self, connectTimeout: int) -> None:
        """接続タイムアウトを設定する

        Args:
            connectTimeout: 接続タイムアウト（ミリ秒）
        """
        self.connectTimeout_ = connectTimeout

    def setReceiveTimeout(self, receiveTimeout: int) -> None:
        """受信タイムアウトを設定する

        Args:
            receiveTimeout: 受信タイムアウト（ミリ秒）
        """
        self.receiveTimeout_ = receiveTimeout

    def setGrammarFileNames(self, grammarFileNames: str | None) -> None:
        """グラマファイル名を設定する

        Args:
            grammarFileNames: グラマファイル名の文字列
        """
        self.grammarFileNames_ = grammarFileNames

    def setCompleteTimeout(self, completeTimeout: str | None) -> None:
        """ルールグラマの確定待ちタイムアウトを設定する

        Args:
            completeTimeout: 確定待ちタイムアウト（ミリ秒）の文字列
        """
        self.completeTimeout_ = completeTimeout

    def setWildcardModelPenalty(self, wildcardModelPenalty: str | None) -> None:
        """ルールグラマのワイルドカードモデルペナルティを設定する

        Args:
            wildcardModelPenalty: ワイルドカードモデルペナルティの文字列
        """
        self.wildcardModelPenalty_ = wildcardModelPenalty

    def setMode(self, mode: str | None) -> None:
        """認識モードを設定する

        Args:
            mode: 認識モードの文字列
        """
        self.mode_ = mode

    def setProfileId(self, profileId: str | None) -> None:
        """プロファイル ID を設定する

        Args:
            profileId: プロファイル ID の文字列
        """
        self.profileId_ = profileId

    def setProfileWords(self, profileWords: str | None) -> None:
        """プロファイル登録単語を設定する

        Args:
            profileWords: 登録単語の文字列
        """
        self.profileWords_ = profileWords

    def setSegmenterType(self, segmenterType: str | None) -> None:
        """セグメンタタイプを設定する

        Args:
            segmenterType: セグメンタタイプの文字列
        """
        self.segmenterType_ = segmenterType

    def setSegmenterProperties(self, segmenterProperties: str | None) -> None:
        """セグメンタプロパティを設定する

        Args:
            segmenterProperties: セグメンタプロパティの文字列
        """
        self.segmenterProperties_ = segmenterProperties

    def setAudioFilterProperties(self, audioFilterProperties: str | None) -> None:
        """音声フィルタプロパティを設定する

        Args:
            audioFilterProperties: 音声フィルタプロパティの文字列
        """
        self.audioFilterProperties_ = audioFilterProperties

    def setKeepFillerToken(self, keepFillerToken: str | None) -> None:
        """フィラー単語を保持するかどうかを設定する

        Args:
            keepFillerToken: フィラー単語保持フラグの文字列（"true"/"false"）
        """
        self.keepFillerToken_ = keepFillerToken

    def setResultUpdatedInterval(self, resultUpdatedInterval: str | None) -> None:
        """認識中イベント発行間隔を設定する

        Args:
            resultUpdatedInterval: イベント発行間隔の文字列（ミリ秒）
        """
        self.resultUpdatedInterval_ = resultUpdatedInterval

    def setMaxDecodingTime(self, maxDecodingTime: str | None) -> None:
        """最大認識処理時間を設定する

        Args:
            maxDecodingTime: 最大認識処理時間の文字列（ミリ秒）
        """
        self.maxDecodingTime_ = maxDecodingTime

    def setMaxResponseTime(self, maxResponseTime: str | None) -> None:
        """最大応答時間を設定する

        Args:
            maxResponseTime: 最大応答時間の文字列（ミリ秒）
        """
        self.maxResponseTime_ = maxResponseTime

    def setMaxDecodingRate(self, maxDecodingRate: str | None) -> None:
        """最大認識処理割合を設定する

        Args:
            maxDecodingRate: 最大認識処理割合の文字列
        """
        self.maxDecodingRate_ = maxDecodingRate

    def setTargetResponseTime(self, targetResponseTime: str | None) -> None:
        """目標応答時間を設定する

        Args:
            targetResponseTime: 目標応答時間の文字列（ミリ秒）
        """
        self.targetResponseTime_ = targetResponseTime

    def setTargetDecodingRate(self, targetDecodingRate: str | None) -> None:
        """目標認識処理割合を設定する

        Args:
            targetDecodingRate: 目標認識処理割合の文字列
        """
        self.targetDecodingRate_ = targetDecodingRate

    def setRecognitionTimeout(self, recognitionTimeout: str | None) -> None:
        """認識処理タイムアウトを設定する

        Args:
            recognitionTimeout: 認識処理タイムアウトの文字列（ミリ秒）
        """
        self.recognitionTimeout_ = recognitionTimeout

    def setExtension(self, extension: str | None) -> None:
        """拡張情報を設定する

        Args:
            extension: 拡張情報の文字列
        """
        self.extension_ = extension

    def setAuthorization(self, authorization: str | None) -> None:
        """認証情報を設定する

        Args:
            authorization: 認証情報の文字列
        """
        self.authorization_ = authorization

    def setDomainId(self, domainId: str | None) -> None:
        """ドメイン ID を設定する

        Args:
            domainId: ドメイン ID の文字列
        """
        self.domainId_ = domainId

    def setConfidenceLevel(self, confidenceLevel: str | None) -> None:
        """信頼度しきい値を設定する

        Args:
            confidenceLevel: 信頼度しきい値の文字列
        """
        self.confidenceLevel_ = confidenceLevel

    def setCodec(self, codec: str | None) -> None:
        """音声コーデックを設定する

        Args:
            codec: 音声コーデックの文字列
        """
        self.codec_ = codec

    def setResultType(self, resultType: str | None) -> None:
        """認識結果タイプを設定する

        Args:
            resultType: 認識結果タイプの文字列
        """
        self.resultType_ = resultType

    def setResultEncoding(self, resultEncoding: str | None) -> None:
        """認識結果の文字エンコーディングを設定する

        Args:
            resultEncoding: 文字エンコーディングの文字列
        """
        self.resultEncoding_ = resultEncoding

    def setServiceAuthorization(self, serviceAuthorization: str | None) -> None:
        """サービス認証キーを設定する

        Args:
            serviceAuthorization: サービス認証キーの文字列
        """
        self.serviceAuthorization_ = serviceAuthorization

    def setVoiceDetection(self, voiceDetection: str | None) -> None:
        """発話区間検出パラメータを設定する

        Args:
            voiceDetection: 発話区間検出パラメータの文字列
        """
        self.voiceDetection_ = voiceDetection

    def setAcceptTopic(self, acceptTopic: str | None) -> None:
        """HTTP リクエストの Accept-Topic ヘッダを設定する

        Args:
            acceptTopic: Accept-Topic ヘッダの文字列
        """
        self.acceptTopic_ = acceptTopic

    def setContentType(self, contentType: str | None) -> None:
        """HTTP リクエストの Content-Type ヘッダを設定する

        Args:
            contentType: Content-Type ヘッダの文字列
        """
        self.contentType_ = contentType

    def setAccept(self, accept: str | None) -> None:
        """HTTP リクエストの Accept ヘッダを設定する

        Args:
            accept: Accept ヘッダの文字列
        """
        self.accept_ = accept

    def connect(self) -> bool:
        """HTTP 音声認識サーバに接続する

        Returns:
            接続に成功した場合は True、失敗した場合は False
        """
        listener = self.listener_
        if self.isConnected_():
            self.lastMessage_ = "WARNING: already connected to HTTP server"
            if listener is not None:
                listener.TRACE(self.lastMessage_)
            return False
        server_url = self.serverURL_
        if server_url is None:
            self.lastMessage_ = "ERROR: can't connect to HTTP server (Missing server URL)"
            if listener is not None:
                listener.TRACE(self.lastMessage_)
            return False
        try:
            self.state_ = 0
            self.connect_(
                server_url,
                self.proxyServerName_,
                self.connectTimeout_,
                self.receiveTimeout_,
            )
        except Exception as e:
            self.lastMessage_ = f"ERROR: can't connect to HTTP server ({e}): {server_url}"
            if listener is not None:
                listener.TRACE(self.lastMessage_)
            self.state_ = -1
            self.disconnect_()
            return False
        self.lastMessage_ = f"INFO: connected to HTTP server: {server_url}"
        if listener is not None:
            listener.TRACE(self.lastMessage_)
        return True

    def connect_(self, serverURL: str, proxyServerName: str | None, connectTimeout: int, receiveTimeout: int) -> None:
        """接続処理の実装。サブクラスでオーバーライドする

        Args:
            serverURL: サーバ URL
            proxyServerName: プロキシサーバ名
            connectTimeout: 接続タイムアウト（ミリ秒）
            receiveTimeout: 受信タイムアウト（ミリ秒）

        Raises:
            NotImplementedError: サブクラスで実装されていない場合
        """
        raise NotImplementedError()

    def disconnect(self) -> bool:
        """HTTP 音声認識サーバから切断する

        Returns:
            切断に成功した場合は True、失敗した場合は False
        """
        listener = self.listener_
        if not self.isConnected_():
            self.lastMessage_ = "WARNING: already disconnected from HTTP server"
            if listener is not None:
                listener.TRACE(self.lastMessage_)
            return False
        self.state_ = -1
        self.disconnect_()
        self.lastMessage_ = "INFO: disconnected from HTTP server"
        if listener is not None:
            listener.TRACE(self.lastMessage_)
        return True

    def disconnect_(self) -> None:
        """切断処理の実装。サブクラスでオーバーライドする

        Raises:
            NotImplementedError: サブクラスで実装されていない場合
        """
        raise NotImplementedError()

    def isConnected(self) -> bool:
        """HTTP 音声認識サーバに接続中かどうかを返す

        Returns:
            接続中の場合は True、未接続の場合は False
        """
        return self.isConnected_()

    def isConnected_(self) -> bool:
        """接続状態確認の実装。サブクラスでオーバーライドする

        Returns:
            接続中の場合は True、未接続の場合は False

        Raises:
            NotImplementedError: サブクラスで実装されていない場合
        """
        raise NotImplementedError()

    # type="s"  dataBytes>0 - Single part & no chunked encoding
    # type="sc" dataBytes=0 - Single part & chunked encoding
    # type="m"  dataBytes>0 - Multi parts & no chunked encoding
    # type="mc" dataBytes=0 - Multi parts & chunked encoding
    def feedDataResume(self, type: str | None = "mc", dataBytes: int = 0) -> bool:  # noqa: PLR0912, PLR0915
        """HTTP 音声認識サーバへの音声データ送信を開始する

        Args:
            type: リクエストタイプ。"s" はシングルパート＆非チャンク、"sc" はシングルパート＆チャンク、
                "m" はマルチパート＆非チャンク、"mc" はマルチパート＆チャンク
            dataBytes: 音声データの合計バイト数。チャンクドエンコーディングの場合は 0 を指定する

        Returns:
            開始に成功した場合は True、失敗した場合は False
        """
        feed_type = "mc" if type is None else type
        listener = self.listener_
        if dataBytes > 0:
            if feed_type.find("m") == -1:
                if feed_type.find("c") == -1:
                    feed_type = "s "
                else:
                    feed_type = "sc"
            elif feed_type.find("c") == -1:
                feed_type = "m "
            else:
                feed_type = "mc"
        elif feed_type.find("m") == -1:
            feed_type = "sc"
        else:
            feed_type = "mc"
        with self.condition_:
            if not self.isConnected_():
                self.lastMessage_ = "WARNING: already disconnected from HTTP server"
                if listener is not None:
                    listener.TRACE(self.lastMessage_)
                return False
            if self.state_ != 0:
                self.lastMessage_ = "WARNING: already started feeding data to HTTP server"
                if listener is not None:
                    listener.TRACE(self.lastMessage_)
                return False
            domainId = ""
            if self.domainId_ is not None:
                domainId += self.domainId_
                if self.confidenceLevel_ is not None:
                    if len(domainId) > 0:
                        domainId += " "
                    domainId += "confidenceLevel="
                    with suppress(Exception):
                        domainId += q(self.confidenceLevel_)
            else:
                if self.grammarFileNames_ is not None:
                    domainId += "grammarFileNames="
                    with suppress(Exception):
                        domainId += q(self.grammarFileNames_)
                if self.completeTimeout_ is not None:
                    if len(domainId) > 0:
                        domainId += " "
                    domainId += "completeTimeout="
                    with suppress(Exception):
                        domainId += q(self.completeTimeout_)
                if self.wildcardModelPenalty_ is not None:
                    if len(domainId) > 0:
                        domainId += " "
                    domainId += "wildcardModelPenalty="
                    with suppress(Exception):
                        domainId += q(self.wildcardModelPenalty_)
                if self.mode_ is not None:
                    if len(domainId) > 0:
                        domainId += " "
                    domainId += "mode="
                    with suppress(Exception):
                        domainId += q(self.mode_)
                if self.profileId_ is not None:
                    if len(domainId) > 0:
                        domainId += " "
                    domainId += "profileId="
                    with suppress(Exception):
                        domainId += q(self.profileId_)
                if self.profileWords_ is not None:
                    if len(domainId) > 0:
                        domainId += " "
                    domainId += "profileWords="
                    with suppress(Exception):
                        domainId += q(self.profileWords_)
                if self.segmenterType_ is not None:
                    if len(domainId) > 0:
                        domainId += " "
                    domainId += "segmenterType="
                    with suppress(Exception):
                        domainId += q(self.segmenterType_)
                if self.segmenterProperties_ is not None:
                    if len(domainId) > 0:
                        domainId += " "
                    domainId += "segmenterProperties="
                    with suppress(Exception):
                        domainId += q(self.segmenterProperties_)
                if self.audioFilterProperties_ is not None:
                    if len(domainId) > 0:
                        domainId += " "
                    domainId += "audioFilterProperties="
                    with suppress(Exception):
                        domainId += q(self.audioFilterProperties_)
                if self.keepFillerToken_ is not None:
                    if len(domainId) > 0:
                        domainId += " "
                    domainId += "keepFillerToken="
                    with suppress(Exception):
                        domainId += q(self.keepFillerToken_)
                if self.resultUpdatedInterval_ is not None:
                    if len(domainId) > 0:
                        domainId += " "
                    domainId += "resultUpdatedInterval="
                    with suppress(Exception):
                        domainId += q(self.resultUpdatedInterval_)
                if self.maxDecodingTime_ is not None:
                    if len(domainId) > 0:
                        domainId += " "
                    domainId += "maxDecodingTime="
                    with suppress(Exception):
                        domainId += q(self.maxDecodingTime_)
                if self.maxResponseTime_ is not None:
                    if len(domainId) > 0:
                        domainId += " "
                    domainId += "maxResponseTime="
                    with suppress(Exception):
                        domainId += q(self.maxResponseTime_)
                if self.maxDecodingRate_ is not None:
                    if len(domainId) > 0:
                        domainId += " "
                    domainId += "maxDecodingRate="
                    with suppress(Exception):
                        domainId += q(self.maxDecodingRate_)
                if self.targetResponseTime_ is not None:
                    if len(domainId) > 0:
                        domainId += " "
                    domainId += "targetResponseTime="
                    with suppress(Exception):
                        domainId += q(self.targetResponseTime_)
                if self.targetDecodingRate_ is not None:
                    if len(domainId) > 0:
                        domainId += " "
                    domainId += "targetDecodingRate="
                    with suppress(Exception):
                        domainId += q(self.targetDecodingRate_)
                if self.recognitionTimeout_ is not None:
                    if len(domainId) > 0:
                        domainId += " "
                    domainId += "recognitionTimeout="
                    with suppress(Exception):
                        domainId += q(self.recognitionTimeout_)
                if self.confidenceLevel_ is not None:
                    if len(domainId) > 0:
                        domainId += " "
                    domainId += "confidenceLevel="
                    with suppress(Exception):
                        domainId += q(self.confidenceLevel_)
                if self.extension_ is not None:
                    if len(domainId) > 0:
                        domainId += " "
                    domainId += "extension="
                    with suppress(Exception):
                        domainId += q(self.extension_)
                if self.authorization_ is not None:
                    if len(domainId) > 0:
                        domainId += " "
                    domainId += "authorization="
                    with suppress(Exception):
                        domainId += q(self.authorization_)
            try:
                self.state_ = 1
                self.sendRequestHeader_(
                    domainId,
                    self.codec_,
                    self.resultType_,
                    self.resultEncoding_,
                    self.serviceAuthorization_,
                    self.voiceDetection_,
                    self.acceptTopic_,
                    self.contentType_,
                    self.accept_,
                    feed_type,
                    dataBytes,
                )
                self.state_ = 2
                self.lastMessage_ = "INFO: started feeding data to HTTP server"
                if listener is not None:
                    listener.TRACE(self.lastMessage_)
            except OSError as e:
                self.lastMessage_ = f"ERROR: can't start feeding data to HTTP server ({e})"
                if listener is not None:
                    listener.TRACE(self.lastMessage_)
                return False
            return True

    def feedData(self, data: bytes, dataOffset: int, dataBytes: int) -> bool:
        """HTTP 音声認識サーバへ音声データを送信する

        Args:
            data: 送信する音声データのバイト列
            dataOffset: data 内の開始オフセット
            dataBytes: 送信するバイト数

        Returns:
            送信に成功した場合は True、失敗した場合は False
        """
        listener = self.listener_
        with self.condition_:
            if not self.isConnected_():
                self.lastMessage_ = "WARNING: already disconnected from HTTP server"
                if listener is not None:
                    listener.TRACE(self.lastMessage_)
                return False
            if self.state_ not in {2, 3}:
                self.lastMessage_ = "WARNING: already stopped feeding data to HTTP server"
                if listener is not None:
                    listener.TRACE(self.lastMessage_)
                return False
            try:
                self.state_ = 3
                self.sendRequestBody_(data, dataOffset, dataBytes)
            except OSError as e:
                self.lastMessage_ = f"ERROR: can't feed data to HTTP server ({e})"
                if listener is not None:
                    listener.TRACE(self.lastMessage_)
                return False
            return True

    def feedDataPause(self) -> bool:
        """HTTP 音声認識サーバへの音声データ送信を完了する

        Returns:
            完了に成功した場合は True、失敗した場合は False
        """
        listener = self.listener_
        with self.condition_:
            if not self.isConnected_():
                self.lastMessage_ = "WARNING: already disconnected from HTTP server"
                if listener is not None:
                    listener.TRACE(self.lastMessage_)
                return False
            if self.state_ not in {2, 3}:
                self.lastMessage_ = "WARNING: already stopped feeding data to HTTP server"
                if listener is not None:
                    listener.TRACE(self.lastMessage_)
                return False
            try:
                self.state_ = 4
                self.sendRequestBody_(None, 0, 0)
                while self.state_ == 4:
                    self.condition_.wait()
                if self.state_ == 5:
                    self.lastMessage_ = "ERROR: can't stop feeding data to HTTP server"
                    if listener is not None:
                        listener.TRACE(self.lastMessage_)
                    return False
                self.lastMessage_ = "INFO: stopped feeding data to HTTP server"
                if listener is not None:
                    listener.TRACE(self.lastMessage_)
            except InterruptedError:
                self.lastMessage_ = "WARNING: interrupted to stop feeding data to HTTP server"
                if listener is not None:
                    listener.TRACE(self.lastMessage_)
                return False
            except OSError as e:
                self.lastMessage_ = f"ERROR: can't stop feeding data to HTTP server ({e})"
                if listener is not None:
                    listener.TRACE(self.lastMessage_)
                return False
            return True

    def getLastMessage(self) -> str:
        """最後に発生したメッセージを返す

        Returns:
            最後に発生したメッセージの文字列
        """
        return self.lastMessage_

    def sleep(self, timeout: float) -> None:
        """指定した時間（ミリ秒）だけスリープする

        Args:
            timeout: スリープ時間（ミリ秒）
        """
        with suppress(Exception):
            time.sleep(timeout / 1000.0)

    def sendRequestHeader_(  # noqa: PLR0913
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
        """HTTP リクエストヘッダを送信する実装。サブクラスでオーバーライドする

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

        Raises:
            NotImplementedError: サブクラスで実装されていない場合
        """
        raise NotImplementedError()

    def sendRequestBody_(self, data: bytes | None, dataOffset: int, dataBytes: int) -> None:
        """HTTP リクエストボディを送信する実装。サブクラスでオーバーライドする

        Args:
            data: 送信するデータのバイト列。None の場合は終端データを送信する
            dataOffset: data 内の開始オフセット
            dataBytes: 送信するバイト数

        Raises:
            NotImplementedError: サブクラスで実装されていない場合
        """
        raise NotImplementedError()

    def onOpen_(self, sessionId: str) -> None:
        """接続後にセッションが開始されたときに呼び出される内部イベントハンドラ

        Args:
            sessionId: 開始されたセッションの ID
        """
        if self.listener_ is not None:
            self.listener_.resultCreated(sessionId)

    def onClose_(self) -> None:
        """セッションが終了したときに呼び出される内部イベントハンドラ"""
        with self.condition_:
            self.state_ = 0
            self.condition_.notify_all()

    def onError_(self, cause: Exception) -> None:
        """エラー発生時に呼び出される内部イベントハンドラ

        Args:
            cause: 発生した例外
        """
        with self.condition_:
            if self.state_ in (-1, 0, 5):
                return
            self.lastMessage_ = f"ERROR: caught exception ({cause})"
            if self.listener_ is not None:
                self.listener_.TRACE(self.lastMessage_)
            self.state_ = 5
            self.condition_.notify_all()

    def onMessage_(self, resultData: str) -> None:
        """サーバからメッセージを受信したときに呼び出される内部イベントハンドラ

        Args:
            resultData: 受信した認識結果データの文字列
        """
        if self.listener_ is not None:  # {
            if resultData.endswith(("...", '..."}')):
                self.listener_.resultUpdated(resultData)
            else:
                self.listener_.resultFinalized(resultData)
