"""認識と補助APIで共通に使うHTTP User-Agent"""

import sys
from functools import cache
from importlib.metadata import PackageNotFoundError, version


@cache
def build_client_user_agent() -> str:
    """配布バージョンとPythonのメジャー・マイナーを含む識別子をキャッシュする

    Returns:
        str: HTTPヘッダ用のライブラリ識別子、メタデータ未取得時のバージョンは0.0.0
    """
    try:
        package_version = version("amivoice-api-client")
    except PackageNotFoundError:
        package_version = "0.0.0"
    return f"amivoice-api-client/{package_version} Python/{sys.version_info.major}.{sys.version_info.minor}"
