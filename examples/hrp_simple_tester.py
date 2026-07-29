import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

# <!-- バイトコードキャッシュファイルの作成を抑制するために...
sys.dont_write_bytecode = True
# -->
from com.amivoice.hrp.Hrp import Hrp  # noqa: E402
from com.amivoice.hrp.HrpListener import HrpListener  # noqa: E402


class HrpSimpleTester(HrpListener):
    """HTTP 音声認識サーバへの音声データ送信と認識結果受信を行う簡易テスタークラス"""

    @staticmethod
    def main(args: "Sequence[str]") -> None:
        """HTTP 音声認識サーバに接続し、音声データを送信して認識結果を出力するメイン処理

        Args:
            args: コマンドライン引数
                [0] serverURL: HTTP 音声認識サーバの URL
                [1] audioFileName: 音声データファイルのパス
                [2] codec: 音声コーデック
                [3] grammarFileNames: グラマーファイル名
                [4] authorization: API 認証情報
        """
        if len(args) < 4:
            print("Usage: python HrpSimpleTester.py <url> <audioFileName> <codec> <grammarFileNames> [<authorization>]")
            return

        serverURL = args[0]
        audioFileName = args[1]
        codec = args[2]
        grammarFileNames = args[3]
        authorization = args[4] if len(args) > 4 else None

        # HTTP 音声認識サーバイベントリスナの作成
        listener = HrpSimpleTester()

        # HTTP 音声認識サーバの初期化
        hrp = Hrp.construct()
        hrp.setListener(listener)
        hrp.setServerURL(serverURL)
        hrp.setCodec(codec)
        hrp.setGrammarFileNames(grammarFileNames)
        hrp.setAuthorization(authorization)

        # HTTP 音声認識サーバへの接続
        if not hrp.connect():
            print(hrp.getLastMessage())
            print(f"HTTP 音声認識サーバ {serverURL} への接続に失敗しました。")
            return

        try:
            # HTTP 音声認識サーバへの音声データの送信の開始
            if not hrp.feedDataResume():
                print(hrp.getLastMessage())
                print("HTTP 音声認識サーバへの音声データの送信の開始に失敗しました。")
                return

            try:
                with Path(audioFileName).open("rb") as audioStream:
                    # 音声データファイルからの音声データの読み込み
                    audioData = audioStream.read(4096)
                    while len(audioData) > 0:
                        # 微小時間のスリープ
                        hrp.sleep(1)

                        # HTTP 音声認識サーバへの音声データの送信
                        if not hrp.feedData(audioData, 0, len(audioData)):
                            print(hrp.getLastMessage())
                            print("HTTP 音声認識サーバへの音声データの送信に失敗しました。")
                            break

                        # 音声データファイルからの音声データの読み込み
                        audioData = audioStream.read(4096)
            except OSError:
                print(f"音声データファイル {audioFileName} の読み込みに失敗しました。")

            # HTTP 音声認識サーバへの音声データの送信の完了
            if not hrp.feedDataPause():
                print(hrp.getLastMessage())
                print("HTTP 音声認識サーバへの音声データの送信の完了に失敗しました。")
                return
        finally:
            # HTTP 音声認識サーバからの切断
            hrp.disconnect()

    def __init__(self) -> None:
        """インスタンスを初期化する"""

    def resultCreated(self, sessionId: str) -> None:
        """音声認識セッションが作成されたときに呼び出されるコールバック

        Args:
            sessionId: 作成されたセッションの ID
        """
        # print("C %s" % sessionId)

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


HrpSimpleTester.main(sys.argv[1:])
