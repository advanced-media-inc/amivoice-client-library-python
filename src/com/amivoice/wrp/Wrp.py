import sys
import threading
import time
from contextlib import suppress
from urllib.parse import quote


def q(s: str) -> str:
    """文字列を UTF-8 で URL エンコードする

    Args:
        s: エンコード対象の文字列

    Returns:
        URL エンコードされた文字列
    """
    return quote(s, "UTF-8")


class Wrp:
    """WebSocket 音声認識サーバと通信するためのクライアントクラス"""

    VERSION = f"Wrp/1.0.06 Python/{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]} ({sys.platform})"

    @staticmethod
    def getVersion() -> str:
        """アプリケーションのバージョン文字列を返す

        Returns:
            バージョン文字列
        """
        return Wrp.VERSION

    @staticmethod
    def construct(implementation: int = 0) -> "Wrp":
        """Wrp 実装インスタンスを生成するファクトリメソッド

        Args:
            implementation: 実装タイプ0 はデフォルト実装（現在は 1）

        Returns:
            Wrp インスタンス

        Raises:
            ValueError: 未知の実装タイプが指定された場合
        """
        if implementation == 0:
            implementation = 1  # default implementation
        if implementation == 1:
            from .Wrp_ import Wrp_  # noqa: PLC0415 遅延インポート必須なため

            return Wrp_()
        else:
            raise ValueError("Unknown implementation: " + str(implementation))

    def __init__(self) -> None:
        """インスタンスを初期化する"""
        self.condition_ = threading.Condition()
        self.listener_ = None
        self.serverURL_ = None
        self.proxyServerName_ = None
        self.connectTimeout_ = 0
        self.receiveTimeout_ = 0
        self.grammarFileNames_ = None
        self.completeTimeout_: str | None = None
        self.wildcardModelPenalty_: str | None = None
        self.mode_ = None
        self.profileId_ = None
        self.profileWords_ = None
        self.segmenterType_ = None
        self.segmenterProperties_ = None
        self.keepFillerToken_ = None
        self.resultUpdatedInterval_ = None
        self.maxDecodingTime_ = None
        self.maxResponseTime_ = None
        self.maxDecodingRate_ = None
        self.targetResponseTime_ = None
        self.targetDecodingRate_ = None
        self.noInputTimeout_ = None
        self.recognitionTimeout_ = None
        self.confidenceLevel_: str | None = None
        self.extension_ = None
        self.authorization_ = None
        self.codec_ = None
        self.resultType_ = None
        self.state_ = -1
        self.lastMessage_ = ""
        self.waitingResults_ = 0

    def setListener(self, listener: object) -> None:
        """イベントリスナを設定する

        Args:
            listener: 設定するリスナオブジェクトNone の場合はリスナを解除する
        """
        self.listener_ = listener

    def setServerURL(self, serverURL: str) -> None:
        """接続先の WebSocket 音声認識サーバ URL を設定する

        http:// または https:// の URL は自動的に非TLS / TLS の WebSocket URL に変換される

        Args:
            serverURL: サーバの URL 文字列
        """
        self.serverURL_ = serverURL
        if self.serverURL_ is not None:
            if self.serverURL_.startswith("http://"):
                self.serverURL_ = (
                    "ws://" + self.serverURL_[7:]  # nosemgrep
                )
            elif self.serverURL_.startswith("https://"):
                self.serverURL_ = "wss://" + self.serverURL_[8:]

    def setProxyServerName(self, proxyServerName: str | None) -> None:
        """プロキシサーバ名を設定する

        Args:
            proxyServerName: プロキシサーバのホスト名（ポート含む）None の場合はプロキシを使用しない
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

    def setNoInputTimeout(self, noInputTimeout: str | None) -> None:
        """発話検出タイムアウトを設定する

        Args:
            noInputTimeout: 発話検出タイムアウトの文字列（ミリ秒）
        """
        self.noInputTimeout_ = noInputTimeout

    def setRecognitionTimeout(self, recognitionTimeout: str | None) -> None:
        """認識処理タイムアウトを設定する

        Args:
            recognitionTimeout: 認識処理タイムアウトの文字列（ミリ秒）
        """
        self.recognitionTimeout_ = recognitionTimeout

    def setConfidenceLevel(self, confidenceLevel: str | None) -> None:
        """信頼度しきい値を設定する

        Args:
            confidenceLevel: 信頼度しきい値の文字列
        """
        self.confidenceLevel_ = confidenceLevel

    def setExtension(self, extension: str | None) -> None:
        """使用量集計タグを設定する

        Args:
            extension: 使用量集計タグの文字列
        """
        self.extension_ = extension

    def setAuthorization(self, authorization: str | None) -> None:
        """認証情報を設定する

        Args:
            authorization: 認証情報の文字列
        """
        self.authorization_ = authorization

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

    def setServiceAuthorization(self, serviceAuthorization: str | None) -> None:
        """サービス認証キーを設定する

        authorization として設定するエイリアスメソッド

        Args:
            serviceAuthorization: サービス認証キーの文字列
        """
        if serviceAuthorization is not None:
            self.authorization_ = serviceAuthorization

    def setVoiceDetection(self, voiceDetection: str | None) -> None:
        """発話区間検出パラメータを設定する

        segmenterType および segmenterProperties に変換して設定する

        Args:
            voiceDetection: 発話区間検出パラメータの文字列
        """
        if voiceDetection is not None:
            self.segmenterType_ = "G4"
            self.segmenterProperties_ = voiceDetection
            if len(voiceDetection) > 3 and voiceDetection[0] == "G" and voiceDetection[2] == " ":
                self.segmenterType_ = voiceDetection[:2]
                self.segmenterProperties_ = voiceDetection[3:]

    def connect(self) -> bool:
        """WebSocket 音声認識サーバに接続する

        Returns:
            接続に成功した場合は True、失敗した場合は False
        """
        if self.isConnected_():
            self.lastMessage_ = "WARNING: already connected to WebSocket server"
            if self.listener_ is not None:
                self.listener_.TRACE(self.lastMessage_)
            return False
        if self.serverURL_ is None:
            self.lastMessage_ = "ERROR: can't connect to WebSocket server (Missing server URL)"
            if self.listener_ is not None:
                self.listener_.TRACE(self.lastMessage_)
            return False
        try:
            self.state_ = 0
            self.waitingResults_ = 0
            self.connect_(
                self.serverURL_,
                self.proxyServerName_,
                self.connectTimeout_,
                self.receiveTimeout_,
            )
        except Exception as e:
            self.lastMessage_ = "ERROR: can't connect to WebSocket server (" + str(e) + "): " + self.serverURL_
            if self.listener_ is not None:
                self.listener_.TRACE(self.lastMessage_)
            self.state_ = -1
            self.disconnect_()
            return False
        self.lastMessage_ = "INFO: connected to WebSocket server: " + self.serverURL_
        if self.listener_ is not None:
            self.listener_.TRACE(self.lastMessage_)
        return True

    def connect_(self, serverURL: str, proxyServerName: str | None, connectTimeout: int, receiveTimeout: int) -> None:
        """接続処理の実装サブクラスでオーバーライドする

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
        """WebSocket 音声認識サーバから切断する

        Returns:
            切断に成功した場合は True、失敗した場合は False
        """
        if not self.isConnected_():
            self.lastMessage_ = "WARNING: already disconnected from WebSocket server"
            if self.listener_ is not None:
                self.listener_.TRACE(self.lastMessage_)
            return False
        self.state_ = -1
        self.disconnect_()
        self.lastMessage_ = "INFO: disconnected from WebSocket server"
        if self.listener_ is not None:
            self.listener_.TRACE(self.lastMessage_)
        return True

    def disconnect_(self) -> None:
        """切断処理の実装サブクラスでオーバーライドする

        Raises:
            NotImplementedError: サブクラスで実装されていない場合
        """
        raise NotImplementedError()

    def isConnected(self) -> bool:
        """WebSocket 音声認識サーバに接続中かどうかを返す

        Returns:
            接続中の場合は True、未接続の場合は False
        """
        return self.isConnected_()

    def isConnected_(self) -> bool:
        """接続状態確認の実装サブクラスでオーバーライドする

        Returns:
            接続中の場合は True、未接続の場合は False

        Raises:
            NotImplementedError: サブクラスで実装されていない場合
        """
        raise NotImplementedError()

    def feedDataResume(self) -> bool:  # noqa: PLR0912,PLR0915
        """WebSocket 音声認識サーバへの音声データ送信を開始する

        Returns:
            開始に成功した場合は True、失敗した場合は False
        """
        with self.condition_:
            if not self.isConnected_():
                self.lastMessage_ = "WARNING: already disconnected from WebSocket server"
                if self.listener_ is not None:
                    self.listener_.TRACE(self.lastMessage_)
                return False
            if self.state_ != 0:
                self.lastMessage_ = "WARNING: already started feeding data to WebSocket server"
                if self.listener_ is not None:
                    self.listener_.TRACE(self.lastMessage_)
                return False
            command = ""
            command += "s "
            if self.codec_ is not None and len(self.codec_) > 0:
                command += self.codec_
            else:
                command += "16K"
            if self.grammarFileNames_ is not None and len(self.grammarFileNames_) > 0:
                command += " "
                command += self.grammarFileNames_
                if self.grammarFileNames_.find("\001") != -1 and not self.grammarFileNames_.endswith("\001"):
                    command += "\001"
            else:
                command += " \001"
            if self.completeTimeout_ is not None:
                command += " completeTimeout="
                if self.completeTimeout_.find(" ") != -1:
                    command += '"'
                    command += self.completeTimeout_
                    command += '"'
                else:
                    command += self.completeTimeout_
            if self.wildcardModelPenalty_ is not None:
                command += " wildcardModelPenalty="
                if self.wildcardModelPenalty_.find(" ") != -1:
                    command += '"'
                    command += self.wildcardModelPenalty_
                    command += '"'
                else:
                    command += self.wildcardModelPenalty_
            if self.mode_ is not None:
                command += " mode="
                if self.mode_.find(" ") != -1:
                    command += '"'
                    command += self.mode_
                    command += '"'
                else:
                    command += self.mode_
            if self.profileId_ is not None:
                command += " profileId="
                if self.profileId_.find(" ") != -1:
                    command += '"'
                    command += self.profileId_
                    command += '"'
                else:
                    command += self.profileId_
            if self.profileWords_ is not None:
                command += " profileWords="
                if self.profileWords_.find(" ") != -1 or self.profileWords_.find('"') != -1:
                    command += '"'
                    command += self.profileWords_.replace('"', '""')
                    command += '"'
                else:
                    command += self.profileWords_
            if self.segmenterType_ is not None:
                command += " segmenterType="
                if self.segmenterType_.find(" ") != -1:
                    command += '"'
                    command += self.segmenterType_
                    command += '"'
                else:
                    command += self.segmenterType_
            if self.segmenterProperties_ is not None:
                command += " segmenterProperties="
                if self.segmenterProperties_.find(" ") != -1 or self.segmenterProperties_.find('"') != -1:
                    command += '"'
                    command += self.segmenterProperties_.replace('"', '""')
                    command += '"'
                else:
                    command += self.segmenterProperties_
            if self.keepFillerToken_ is not None:
                command += " keepFillerToken="
                if self.keepFillerToken_.find(" ") != -1:
                    command += '"'
                    command += self.keepFillerToken_
                    command += '"'
                else:
                    command += self.keepFillerToken_
            if self.resultUpdatedInterval_ is not None:
                command += " resultUpdatedInterval="
                if self.resultUpdatedInterval_.find(" ") != -1:
                    command += '"'
                    command += self.resultUpdatedInterval_
                    command += '"'
                else:
                    command += self.resultUpdatedInterval_
            if self.maxDecodingTime_ is not None:
                command += " maxDecodingTime="
                if self.maxDecodingTime_.find(" ") != -1:
                    command += '"'
                    command += self.maxDecodingTime_
                    command += '"'
                else:
                    command += self.maxDecodingTime_
            if self.maxResponseTime_ is not None:
                command += " maxResponseTime="
                if self.maxResponseTime_.find(" ") != -1:
                    command += '"'
                    command += self.maxResponseTime_
                    command += '"'
                else:
                    command += self.maxResponseTime_
            if self.maxDecodingRate_ is not None:
                command += " maxDecodingRate="
                if self.maxDecodingRate_.find(" ") != -1:
                    command += '"'
                    command += self.maxDecodingRate_
                    command += '"'
                else:
                    command += self.maxDecodingRate_
            if self.targetResponseTime_ is not None:
                command += " targetResponseTime="
                if self.targetResponseTime_.find(" ") != -1:
                    command += '"'
                    command += self.targetResponseTime_
                    command += '"'
                else:
                    command += self.targetResponseTime_
            if self.targetDecodingRate_ is not None:
                command += " targetDecodingRate="
                if self.targetDecodingRate_.find(" ") != -1:
                    command += '"'
                    command += self.targetDecodingRate_
                    command += '"'
                else:
                    command += self.targetDecodingRate_
            if self.noInputTimeout_ is not None:
                command += " noInputTimeout="
                if self.noInputTimeout_.find(" ") != -1:
                    command += '"'
                    command += self.noInputTimeout_
                    command += '"'
                else:
                    command += self.noInputTimeout_
            if self.recognitionTimeout_ is not None:
                command += " recognitionTimeout="
                if self.recognitionTimeout_.find(" ") != -1:
                    command += '"'
                    command += self.recognitionTimeout_
                    command += '"'
                else:
                    command += self.recognitionTimeout_
            if self.confidenceLevel_ is not None:
                command += " confidenceLevel="
                if self.confidenceLevel_.find(" ") != -1:
                    command += '"'
                    command += self.confidenceLevel_
                    command += '"'
                else:
                    command += self.confidenceLevel_
            if self.extension_ is not None:
                command += " extension="
                if self.extension_.find(" ") != -1 or self.extension_.find('"') != -1:
                    command += '"'
                    command += self.extension_.replace('"', '""')
                    command += '"'
                else:
                    command += self.extension_
            if self.authorization_ is not None:
                command += " authorization="
                if self.authorization_.find(" ") != -1:
                    command += '"'
                    command += self.authorization_
                    command += '"'
                else:
                    command += self.authorization_
            if self.resultType_ is not None:
                command += " resultType="
                if self.resultType_.find(" ") != -1:
                    command += '"'
                    command += self.resultType_
                    command += '"'
                else:
                    command += self.resultType_
            try:
                self.state_ = 1
                data = command.encode("UTF-8")
                self.sendRequest_(data, 0, len(data), 0)
                while self.state_ == 1:
                    self.condition_.wait()
                if self.state_ != 2:
                    return False
            except InterruptedError:
                self.lastMessage_ = "WARNING: interrupted to start feeding data to WebSocket server"
                if self.listener_ is not None:
                    self.listener_.TRACE(self.lastMessage_)
                return False
            except OSError as e:
                self.lastMessage_ = "ERROR: can't start feeding data to WebSocket server (" + str(e) + ")"
                if self.listener_ is not None:
                    self.listener_.TRACE(self.lastMessage_)
                return False
            return True

    def feedData(self, data: bytes, dataOffset: int, dataBytes: int) -> bool:
        """WebSocket 音声認識サーバへ音声データを送信する

        Args:
            data: 送信する音声データのバイト列
            dataOffset: data 内の開始オフセット
            dataBytes: 送信するバイト数

        Returns:
            送信に成功した場合は True、失敗した場合は False
        """
        with self.condition_:
            if not self.isConnected_():
                self.lastMessage_ = "WARNING: already disconnected from WebSocket server"
                if self.listener_ is not None:
                    self.listener_.TRACE(self.lastMessage_)
                return False
            if self.state_ not in {2, 3}:
                self.lastMessage_ = "WARNING: already stopped feeding data to WebSocket server"
                if self.listener_ is not None:
                    self.listener_.TRACE(self.lastMessage_)
                return False
            try:
                self.state_ = 3
                self.sendRequest_(data, dataOffset, dataBytes, 0x70)  # 'p'
            except OSError as e:
                self.lastMessage_ = "ERROR: can't feed data to WebSocket server (" + str(e) + ")"
                if self.listener_ is not None:
                    self.listener_.TRACE(self.lastMessage_)
                return False
            return True

    def feedDataPause(self) -> bool:
        """WebSocket 音声認識サーバへの音声データ送信を完了する

        Returns:
            完了に成功した場合は True、失敗した場合は False
        """
        with self.condition_:
            if not self.isConnected_():
                self.lastMessage_ = "WARNING: already disconnected from WebSocket server"
                if self.listener_ is not None:
                    self.listener_.TRACE(self.lastMessage_)
                return False
            if self.state_ not in {2, 3}:
                self.lastMessage_ = "WARNING: already stopped feeding data to WebSocket server"
                if self.listener_ is not None:
                    self.listener_.TRACE(self.lastMessage_)
                return False
            try:
                self.state_ = 4
                data = b"e"
                self.sendRequest_(data, 0, len(data), 0)
                while self.state_ == 4:
                    self.condition_.wait()
                if self.state_ != 0:
                    return False
            except InterruptedError:
                self.lastMessage_ = "WARNING: interrupted to stop feeding data to WebSocket server"
                if self.listener_ is not None:
                    self.listener_.TRACE(self.lastMessage_)
                return False
            except OSError as e:
                self.lastMessage_ = "ERROR: can't stop feeding data to WebSocket server (" + str(e) + ")"
                if self.listener_ is not None:
                    self.listener_.TRACE(self.lastMessage_)
                return False
            return True

    def getLastMessage(self) -> str:
        """最後に発生したメッセージを返す

        Returns:
            最後に発生したメッセージの文字列
        """
        return self.lastMessage_

    def getWaitingResults(self) -> int:
        """認識結果情報待機数を返す

        Returns:
            現在待機中の認識結果数
        """
        return self.waitingResults_

    def sleep(self, timeout: float) -> None:
        """指定した時間（ミリ秒）だけスリープする

        Args:
            timeout: スリープ時間（ミリ秒）
        """
        with suppress(Exception):
            time.sleep(timeout / 1000.0)

    def sendRequest_(self, data: bytes, dataOffset: int, dataBytes: int, command: int) -> None:
        """WebSocket フレームを送信する実装サブクラスでオーバーライドする

        Args:
            data: 送信するデータのバイト列
            dataOffset: data 内の開始オフセット
            dataBytes: 送信するバイト数
            command: WebSocket コマンドバイト

        Raises:
            NotImplementedError: サブクラスで実装されていない場合
        """
        raise NotImplementedError()

    def onOpen_(self) -> None:
        """接続が確立したときに呼び出される内部イベントハンドラ"""

    def onClose_(self) -> None:
        """セッションが山了したときに呼び出される内部イベントハンドラ"""
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
            self.lastMessage_ = "ERROR: caught exception (" + str(cause) + ")"
            if self.listener_ is not None:
                self.listener_.TRACE(self.lastMessage_)
            self.state_ = 5
            self.condition_.notify_all()

    def onMessage_(self, message: str) -> None:  # noqa: PLR0912,PLR0915
        """サーバからメッセージを受信したときに呼び出される内部イベントハンドラ

        コマンドバイトに応じて適切なリスナメソッドを呼び出す

        Args:
            message: 受信したメッセージの文字列
        """
        if len(message) == 0:
            return
        command = message[0]
        if command == "s":
            if len(message) > 1:
                with self.condition_:
                    self.lastMessage_ = "ERROR: can't start feeding data to WebSocket server (" + message[2:] + ")"
                    if self.listener_ is not None:
                        self.listener_.TRACE(self.lastMessage_)
                    self.state_ = 5
                    self.condition_.notify_all()
            else:
                with self.condition_:
                    self.lastMessage_ = "INFO: started feeding data to WebSocket server"
                    if self.listener_ is not None:
                        self.listener_.TRACE(self.lastMessage_)
                    self.state_ = 2
                    self.condition_.notify_all()
        elif command == "p":
            if len(message) > 1:
                with self.condition_:
                    self.lastMessage_ = "ERROR: can't feed data to WebSocket server (" + message[2:] + ")"
                    if self.listener_ is not None:
                        self.listener_.TRACE(self.lastMessage_)
                    self.state_ = 5
                    self.condition_.notify_all()
            else:
                pass
        elif command == "e":
            if len(message) > 1:
                with self.condition_:
                    self.lastMessage_ = "ERROR: can't stop feeding data to WebSocket server (" + message[2:] + ")"
                    if self.listener_ is not None:
                        self.listener_.TRACE(self.lastMessage_)
                    self.state_ = 5
                    self.condition_.notify_all()
            else:
                with self.condition_:
                    self.lastMessage_ = "INFO: stopped feeding data to WebSocket server"
                    if self.listener_ is not None:
                        self.listener_.TRACE(self.lastMessage_)
                    self.state_ = 0
                    self.condition_.notify_all()
        elif command == "S":
            self.waitingResults_ += 1
            if self.listener_ is not None:
                self.listener_.utteranceStarted(int(message[2:]))
        elif command == "E":
            if self.listener_ is not None:
                self.listener_.utteranceEnded(int(message[2:]))
        elif command == "C":
            if self.listener_ is not None:
                self.listener_.resultCreated()
        elif command == "U":
            if self.listener_ is not None:
                self.listener_.resultUpdated(message[2:])
        elif command == "A":
            if self.listener_ is not None:
                self.listener_.resultFinalized(message[2:])
            self.waitingResults_ -= 1
        elif command == "R":
            if self.listener_ is not None:
                self.listener_.resultFinalized("\001\001\001\001\001" + message[2:])
            self.waitingResults_ -= 1
        elif (command in {"Q", "G"}) and self.listener_ is not None:
            self.listener_.eventNotified(command, message[2:])
