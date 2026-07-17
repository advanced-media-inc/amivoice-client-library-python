import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

# <!-- バイトコードキャッシュファイルの作成を抑制するために...
sys.dont_write_bytecode = True
# -->
import com.amivoice.wrp.Wrp  # noqa: E402
import com.amivoice.wrp.WrpListener  # noqa: E402


class WrpSimpleTester(com.amivoice.wrp.WrpListener):
    """WebSocket 音声認識サーバへの音声データ送信と認識結果受信を行う簡易テスタークラス"""

    @staticmethod
    def main(args: "Sequence[str]") -> None:
        """WebSocket 音声認識サーバに接続し、音声データを送信して認識結果を出力するメイン処理

        Args:
            args: コマンドライン引数
                [0] serverURL: WebSocket 音声認識サーバの URL
                [1] audioFileName: 音声データファイルのパス
                [2] codec: 音声コーデック
                [3] grammarFileNames: グラマーファイル名
                [4] authorization: API 認証情報
        """
        if len(args) < 4:
            print("Usage: python WrpSimpleTester.py <url> <audioFileName> <codec> <grammarFileNames> [<authorization>]")
            return

        serverURL = args[0]
        audioFileName = args[1]
        codec = args[2]
        grammarFileNames = args[3]
        authorization = args[4] if len(args) > 4 else None

        # WebSocket 音声認識サーバイベントリスナの作成
        listener = WrpSimpleTester()

        # WebSocket 音声認識サーバの初期化
        wrp = com.amivoice.wrp.Wrp.construct()
        wrp.setListener(listener)
        wrp.setServerURL(serverURL)
        wrp.setCodec(codec)
        wrp.setGrammarFileNames(grammarFileNames)
        wrp.setAuthorization(authorization)

        # WebSocket 音声認識サーバへの接続
        if not wrp.connect():
            print(wrp.getLastMessage())
            print(f"WebSocket 音声認識サーバ {serverURL} への接続に失敗しました。")
            return

        try:
            # WebSocket 音声認識サーバへの音声データの送信の開始
            if not wrp.feedDataResume():
                print(wrp.getLastMessage())
                print("WebSocket 音声認識サーバへの音声データの送信の開始に失敗しました。")
                return

            try:
                with Path(audioFileName).open("rb") as audioStream:
                    # 音声データファイルからの音声データの読み込み
                    audioData = audioStream.read(4096)
                    while len(audioData) > 0:
                        # 微小時間のスリープ
                        wrp.sleep(1)

                        # 認識結果情報待機数が 1 以下になるまでスリープ
                        maxSleepTime = 50000
                        while wrp.getWaitingResults() > 1 and maxSleepTime > 0:
                            wrp.sleep(100)
                            maxSleepTime -= 100

                        # WebSocket 音声認識サーバへの音声データの送信
                        if not wrp.feedData(audioData, 0, len(audioData)):
                            print(wrp.getLastMessage())
                            print("WebSocket 音声認識サーバへの音声データの送信に失敗しました。")
                            break

                        # 音声データファイルからの音声データの読み込み
                        audioData = audioStream.read(4096)
            except OSError:
                print(f"音声データファイル {audioFileName} の読み込みに失敗しました。")

            # WebSocket 音声認識サーバへの音声データの送信の完了
            if not wrp.feedDataPause():
                print(wrp.getLastMessage())
                print("WebSocket 音声認識サーバへの音声データの送信の完了に失敗しました。")
                return
        finally:
            # WebSocket 音声認識サーバからの切断
            wrp.disconnect()

    def __init__(self) -> None:
        """インスタンスを初期化する"""

    def utteranceStarted(self, startTime: int) -> None:
        """発話が開始されたときに呼び出されるコールバック

        Args:
            startTime: 発話の開始時刻（ミリ秒）
        """
        # print("S %d" % startTime)

    def utteranceEnded(self, endTime: int) -> None:
        """発話が終了したときに呼び出されるコールバック

        Args:
            endTime: 発話の終了時刻（ミリ秒）
        """
        # print("E %d" % endTime)

    def resultCreated(self) -> None:
        """音声認識セッションが作成されたときに呼び出されるコールバック"""
        # print("C")

    def resultUpdated(self, result: str) -> None:
        """音声認識結果が更新されたときに呼び出されるコールバック

        Args:
            result: 更新された認識結果の文字列
        """
        # print("U %s" % result)

    def resultFinalized(self, result: str) -> None:
        """音声認識結果が確定したときに呼び出されるコールバック

        Args:
            result: 確定した認識結果の文字列（JSON 形式）
        """
        # print("F %s" % result)
        print(result)
        text = self.text_(result)
        if text is not None:
            print(f" -> {text}")

    def eventNotified(self, eventId: str, eventMessage: str) -> None:
        """イベントが通知されたときに呼び出されるコールバック

        Args:
            eventId: イベントの ID
            eventMessage: イベントメッセージ
        """
        # print(eventId + " " + eventMessage)

    def TRACE(self, message: str) -> None:
        """デバッグ用のトレースメッセージを処理するコールバック

        Args:
            message: トレースメッセージ
        """

    def text_(self, result: str) -> str | None:
        """認識結果 JSON 文字列からテキストを抽出する

        Args:
            result: 認識結果の JSON 形式文字列

        Returns:
            テキストが含まれる場合はそのテキスト文字列
        """
        if result.find(',"text":"') == -1:
            return None
        return json.loads(result)["text"]


WrpSimpleTester.main(sys.argv[1:])
