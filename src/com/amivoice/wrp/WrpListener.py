class WrpListener:
    """WebSocket 音声認識サーバのイベントリスナ基底クラス"""

    def utteranceStarted(self, startTime: int) -> None:
        """発話が開始されたときに呼び出されるコールバック

        Args:
            startTime: 発話の開始時刻（ミリ秒）
        """

    def utteranceEnded(self, endTime: int) -> None:
        """発話が終了したときに呼び出されるコールバック

        Args:
            endTime: 発話の終了時刻（ミリ秒）
        """

    def resultCreated(self) -> None:
        """音声認識セッションが作成されたときに呼び出されるコールバック"""

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

    def eventNotified(self, eventId: str, eventMessage: str) -> None:
        """イベントが通知されたときに呼び出されるコールバック

        Args:
            eventId: イベントの ID
            eventMessage: イベントメッセージ
        """

    def TRACE(self, message: str) -> None:
        """デバッグ用のトレースメッセージを受け取るコールバック

        Args:
            message: トレースメッセージ
        """
