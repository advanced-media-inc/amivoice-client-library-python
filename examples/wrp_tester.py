import json
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

# <!-- バイトコードキャッシュファイルの作成を抑制するために...
sys.dont_write_bytecode = True
# -->
from com.amivoice.wrp.Wrp import Wrp  # noqa: E402
from com.amivoice.wrp.WrpListener import WrpListener  # noqa: E402


class WrpTester(WrpListener):
    """WebSocket 音声認識サーバへの音声データ送信と認識結果受信を行うテスタークラス"""

    @staticmethod
    def main(args: "Sequence[str]") -> None:  # noqa: PLR0912,PLR0915
        """WebSocket 音声認識サーバに接続し、音声データを送信して認識結果を出力するメイン処理

        Args:
            args: コマンドライン引数のシーケンス。各引数はパラメータ（例: g=<grammarFileNames>）
                またはオプション（例: -v）の形式で指定する
        """
        # WebSocket 音声認識サーバ URL
        serverURL = None
        # プロキシサーバ名
        proxyServerName = None
        # 音声データファイル名
        audioFileNames = []
        # グラマファイル名
        grammarFileNames = None
        # プロファイル ID
        profileId = None
        # プロファイル登録単語
        profileWords = None
        # セグメンタプロパティ
        segmenterProperties = None
        # フィラー単語を保持するかどうか
        keepFillerToken = None
        # 認識中イベント発行間隔
        resultUpdatedInterval = None
        # 最大認識処理時間
        maxDecodingTime = None
        # 最大応答時間
        maxResponseTime = None
        # 最大認識処理割合
        maxDecodingRate = None
        # 目標応答時間
        targetResponseTime = None
        # 目標認識処理割合
        targetDecodingRate = None
        # 発話検出タイムアウト
        noInputTimeout = None
        # 認識処理タイムアウト
        recognitionTimeout = None
        # 使用量集計タグ
        extension = None
        # サービス認証キー文字列
        authorization = None
        # 音声データ形式
        codec = None
        # 認識結果タイプ
        resultType = None
        # サービス認証キー文字列
        serviceAuthorization = None
        # 発話区間検出パラメータ文字列
        voiceDetection = None
        # 接続タイムアウト
        connectTimeout = 5000
        # 受信タイムアウト
        receiveTimeout = 0
        # 処理ループ (1～)
        loop = 1
        # スリープ時間
        sleepTime = -2
        # 詳細出力
        verbose = False
        # 実装タイプ
        implementation = 0

        # 引数のチェック
        for arg in args:
            if arg.startswith("g="):
                grammarFileNames = arg[2:]
            elif arg.startswith("i="):
                profileId = arg[2:]
            elif arg.startswith("w="):
                profileWords = arg[2:]
            elif arg.startswith("op="):
                segmenterProperties = arg[3:]
            elif arg.startswith("of="):
                keepFillerToken = arg[3:]
            elif arg.startswith("oi="):
                resultUpdatedInterval = arg[3:]
            elif arg.startswith("omdt="):
                maxDecodingTime = arg[5:]
            elif arg.startswith("omrt="):
                maxResponseTime = arg[5:]
            elif arg.startswith("omdr="):
                maxDecodingRate = arg[5:]
            elif arg.startswith("otrt="):
                targetResponseTime = arg[5:]
            elif arg.startswith("otdr="):
                targetDecodingRate = arg[5:]
            elif arg.startswith("on="):
                noInputTimeout = arg[3:]
            elif arg.startswith("oo="):
                recognitionTimeout = arg[3:]
            elif arg.startswith("oe="):
                extension = arg[3:]
            elif arg.startswith("ou="):
                authorization = arg[3:]
            elif arg.startswith("c="):
                codec = arg[2:]
            elif arg.startswith("r="):
                resultType = arg[2:]
            elif arg.startswith("u="):
                serviceAuthorization = arg[2:]
            elif arg.startswith("v="):
                voiceDetection = arg[2:]
            elif arg.startswith("-x"):
                proxyServerName = arg[2:]
            elif arg.startswith("-c"):
                connectTimeout = int(arg[2:])
            elif arg.startswith("-r"):
                receiveTimeout = int(arg[2:])
            elif arg.startswith("-l"):
                loop = int(arg[2:])
            elif arg.startswith("-e"):
                if len(arg) > 2:
                    sleepTime = int(arg[2:])
                else:
                    sleepTime = -1
            elif arg.startswith("-v"):
                verbose = True
            elif arg.startswith("-1"):
                implementation = 1
            elif arg.startswith("-2"):
                implementation = 2
            elif arg.startswith("-3"):
                implementation = 3
            elif serverURL is None:
                serverURL = arg
            else:
                audioFileNames.append(arg)
            if verbose:
                print(f"DEBUG: {arg}")
        if len(audioFileNames) == 0:
            print("Usage: python WrpTester.py [<parameters/options>]")
            print("                            <url>")
            print("                             <audioFileName>...")
            print("Parameters:")
            print("  g=<grammarFileNames>")
            print("  i=<profileId>")
            print("  w=<profileWords>")
            print("  op=<segmenterProperties>")
            print("  of=<keepFillerToken>")
            print("  oi=<resultUpdatedInterval>")
            print("  omdt=<maxDecodingTime>")
            print("  omrt=<maxResponseTime>")
            print("  omdr=<maxDecodingRate>")
            print("  otrt=<targetResponseTime>")
            print("  otdr=<targetDecodingRate>")
            print("  on=<noInputTimeout>")
            print("  oo=<recognitionTimeout>")
            print("  oe=<extension>")
            print("  ou=<authorization>")
            print("  c=<codec>")
            print("  r=<resultType>")
            print("  u=<serviceAuthorization>")
            print("  v=<voiceDetection>")
            print("Options:")
            print("  -x<proxyServerName>         (default: -x)")
            print("  -c<connectionTimeout>       (default: -c5000)")
            print("  -r<receiveTimeout>          (default: -r0)")
            print("  -l<loop>                    (default: -l1)")
            print("  -e                          realtime simulation (default: -)")
            print("  -v                          verbose output (default: -)")
            return

        # 開始時間の取得
        startTime = time.time()

        # スリープ時間の計算
        if sleepTime == -1:
            if codec is not None:
                if codec.upper() == "22K" or codec.upper() == "MSB22K" or codec.upper() == "LSB22K":
                    sleepTime = 4096 * 1000 / 2 / 22050
                elif codec.upper() == "16K" or codec.upper() == "MSB16K" or codec.upper() == "LSB16K":
                    sleepTime = 4096 * 1000 / 2 / 16000
                elif codec.upper() == "11K" or codec.upper() == "MSB11K" or codec.upper() == "LSB11K":
                    sleepTime = 4096 * 1000 / 2 / 11025
                elif codec.upper() == "8K" or codec.upper() == "MSB8K" or codec.upper() == "LSB8K":
                    sleepTime = 4096 * 1000 / 2 / 8000
                elif codec.upper() == "MULAW" or codec.upper() == "ALAW":
                    sleepTime = 4096 * 1000 / 1 / 8000
                else:
                    sleepTime = 4096 * 1000 / 2 / 16000  # 16K が指定されたものとして計算...
            else:
                sleepTime = 4096 * 1000 / 2 / 16000  # 16K が指定されたものとして計算...

        # WebSocket 音声認識サーバイベントリスナの作成
        listener = WrpTester(verbose)

        # WebSocket 音声認識サーバの初期化
        wrp = Wrp.construct(implementation)
        wrp.setListener(listener)
        wrp.setServerURL(serverURL)
        wrp.setProxyServerName(proxyServerName)
        wrp.setConnectTimeout(connectTimeout)
        wrp.setReceiveTimeout(receiveTimeout)
        wrp.setGrammarFileNames(grammarFileNames)
        wrp.setProfileId(profileId)
        wrp.setProfileWords(profileWords)
        wrp.setSegmenterProperties(segmenterProperties)
        wrp.setKeepFillerToken(keepFillerToken)
        wrp.setResultUpdatedInterval(resultUpdatedInterval)
        wrp.setMaxDecodingTime(maxDecodingTime)
        wrp.setMaxResponseTime(maxResponseTime)
        wrp.setMaxDecodingRate(maxDecodingRate)
        wrp.setTargetResponseTime(targetResponseTime)
        wrp.setTargetDecodingRate(targetDecodingRate)
        wrp.setNoInputTimeout(noInputTimeout)
        wrp.setRecognitionTimeout(recognitionTimeout)
        wrp.setExtension(extension)
        wrp.setAuthorization(authorization)
        wrp.setCodec(codec)
        wrp.setResultType(resultType)
        wrp.setServiceAuthorization(serviceAuthorization)
        wrp.setVoiceDetection(voiceDetection)

        # WebSocket 音声認識サーバへの接続
        if not wrp.connect():
            if not verbose:
                print(wrp.getLastMessage())
            print(f"WebSocket 音声認識サーバ {serverURL} への接続に失敗しました。")
            return

        try:
            # <!--
            if verbose:
                print("")
                print("======================= " + Wrp.getVersion())
            # -->
            for i in range(loop):
                for audioFileName in audioFileNames:
                    # <!--
                    if verbose:
                        print("")
                        if loop > 1:
                            print(f"----------------------- [{i + 1}] {audioFileName}")
                        else:
                            print(f"----------------------- {audioFileName}")
                        print("")
                    # -->

                    # WebSocket 音声認識サーバへの音声データの送信の開始
                    if not wrp.feedDataResume():
                        if not verbose:
                            print(wrp.getLastMessage())
                        print("WebSocket 音声認識サーバへの音声データの送信の開始に失敗しました。")
                        break

                    try:
                        with Path(audioFileName).open("rb") as audioStream:
                            # 音声データファイルからの音声データの読み込み
                            audioData = audioStream.read(4096)
                            while len(audioData) > 0:
                                # スリープ時間が計算されているかどうかのチェック
                                if sleepTime >= 0:
                                    # スリープ時間が計算されている場合...
                                    # 微小時間のスリープ
                                    wrp.sleep(sleepTime)
                                else:
                                    # スリープ時間が計算されていない場合...
                                    # 微小時間のスリープ
                                    wrp.sleep(1)

                                    # 認識結果情報待機数が 1 以下になるまでスリープ
                                    maxSleepTime = 50000
                                    while wrp.getWaitingResults() > 1 and maxSleepTime > 0:
                                        wrp.sleep(100)
                                        maxSleepTime -= 100

                                # WebSocket 音声認識サーバへの音声データの送信
                                if not wrp.feedData(audioData, 0, len(audioData)):
                                    if not verbose:
                                        print(wrp.getLastMessage())
                                    print("WebSocket 音声認識サーバへの音声データの送信に失敗しました。")
                                    break

                                # 音声データファイルからの音声データの読み込み
                                audioData = audioStream.read(4096)
                    except OSError:
                        print(f"音声データファイル {audioFileName} の読み込みに失敗しました。")

                    # WebSocket 音声認識サーバへの音声データの送信の完了
                    if not wrp.feedDataPause():
                        if not verbose:
                            print(wrp.getLastMessage())
                        print("WebSocket 音声認識サーバへの音声データの送信の完了に失敗しました。")
                        break
            # <!--
            if verbose:
                print("")
                print("=======================")
                print("")
            # -->
        finally:
            # WebSocket 音声認識サーバからの切断
            wrp.disconnect()

        # 終了時間の取得
        endTime = time.time()

        # 経過時間の表示
        print(f"INFO: elapsed time: {(endTime - startTime) * 1000.0:.3f} [msec.]")

    def __init__(self, verbose: bool) -> None:
        """インスタンスを初期化する

        Args:
            verbose: 詳細出力を有効にするかどうか。True の場合、デバッグ情報を出力する
        """
        self.verbose_ = verbose

    def utteranceStarted(self, startTime: int) -> None:
        """発話が開始されたときに呼び出されるコールバック

        Args:
            startTime: 発話の開始時刻（ミリ秒）
        """
        print(f"S {startTime}")

    def utteranceEnded(self, endTime: int) -> None:
        """発話が終了したときに呼び出されるコールバック

        Args:
            endTime: 発話の終了時刻（ミリ秒）
        """
        print(f"E {endTime}")

    def resultCreated(self) -> None:
        """音声認識セッションが作成されたときに呼び出されるコールバック"""
        print("C")

    def resultUpdated(self, result: str) -> None:
        """音声認識結果が更新されたときに呼び出されるコールバック

        Args:
            result: 更新された認識結果の文字列
        """
        print(f"U {result}")
        text = self.text_(result)
        if text is not None:
            print(f"   -> {text}")

    def resultFinalized(self, result: str) -> None:
        """音声認識結果が確定したときに呼び出されるコールバック

        Args:
            result: 確定した認識結果の文字列（JSON 形式）
        """
        print(f"F {result}")
        text = self.text_(result)
        if text is not None:
            print(f"   -> {text}")

    def eventNotified(self, eventId: str, eventMessage: str) -> None:
        """イベントが通知されたときに呼び出されるコールバック

        Args:
            eventId: イベントの ID
            eventMessage: イベントメッセージ
        """
        print(eventId + " " + eventMessage)

    def TRACE(self, message: str) -> None:
        """デバッグ用のトレースメッセージを処理するコールバック

        Args:
            message: トレースメッセージ
        """
        if self.verbose_:
            print(message)

    def text_(self, result: str) -> str | None:
        """認識結果 JSON 文字列からテキストを抽出する

        Args:
            result: 認識結果の JSON 形式文字列

        Returns:
            テキストが含まれる場合はそのテキスト文字列。含まれない場合は None
        """
        if result.find(',"text":"') == -1:
            return None
        return json.loads(result)["text"]


WrpTester.main(sys.argv[1:])
