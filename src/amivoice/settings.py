"""公開設定とクライアント既定値を継承するsentinel"""

from enum import Enum
from typing import Final


class UseClientDefault(Enum):
    """クライアントに設定した値を継承する指定"""

    USE_CLIENT_DEFAULT = "USE_CLIENT_DEFAULT"

    def __repr__(self) -> str:
        """短い公開名を返す

        Returns:
            str: 公開定数の名前
        """
        return "USE_CLIENT_DEFAULT"


USE_CLIENT_DEFAULT: Final = UseClientDefault.USE_CLIENT_DEFAULT
