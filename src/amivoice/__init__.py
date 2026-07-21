"""AmiVoice 高レベル Python クライアントのパブリックエクスポート。"""

from importlib.metadata import PackageNotFoundError, version

from ._stream import StreamConnectionManager, StreamSession
from .client import AmiVoiceClient, transcribe
from .exceptions import (
    AmiVoiceError,
    AuthenticationError,
    ConfigurationError,
    ConnectionFailedError,
    RecognitionError,
)
from .models import NotificationEvent, RecognitionResult, StreamEvent, StreamEventType, UtteranceEvent

try:
    __version__ = version("amivoice-client-library-python")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "AmiVoiceClient",
    "AmiVoiceError",
    "AuthenticationError",
    "ConfigurationError",
    "ConnectionFailedError",
    "NotificationEvent",
    "RecognitionError",
    "RecognitionResult",
    "StreamConnectionManager",
    "StreamEvent",
    "StreamEventType",
    "StreamSession",
    "UtteranceEvent",
    "transcribe",
]
