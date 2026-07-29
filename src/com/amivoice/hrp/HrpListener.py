class HrpListener:
    """HTTP 音声認識サーバのイベントリスナ基底クラス"""

    def resultCreated(self, sessionId: str) -> None:
        """音声認識セッションが作成されたときに呼び出されるコールバック

        Args:
            sessionId: 作成されたセッションの ID
        """

    def resultUpdated(self, result: str) -> None:
        """音声認識結果が更新されたときに呼び出されるコールバック

        Args:
            result: 更新された認識結果の文字列
        """

    def resultFinalized(self, result: str) -> None:
        """音声認識結果が確定したときに呼び出されるコールバック

        Args:
            result: 確定した認識結果の文字列
        """

    def TRACE(self, message: str) -> None:
        """デバッグ用のトレースメッセージを受け取るコールバック

        Args:
            message: トレースメッセージ
        """
