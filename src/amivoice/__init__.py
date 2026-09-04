"""AmiVoice 高レベル Python クライアントのパブリックエクスポート。"""

from importlib.metadata import PackageNotFoundError, version

from ._billing import build_billing_extension
from ._segmenter import SegmenterProperties
from ._stream import StreamConnectionManager, StreamSession
from .client import AmiVoiceClient, transcribe
from .dictionary import ProfileWord, UserDictionaryClient
from .exceptions import (
    AmiVoiceError,
    AuthenticationError,
    ConfigurationError,
    ConnectionFailedError,
    DictionaryApiError,
    RecognitionError,
)
from .grammar import RULE_GRAMMAR_ENGINE, build_grammar_file_names, encode_grammar
from .models import NotificationEvent, RecognitionResult, StreamEvent, StreamEventType, Token, UtteranceEvent, UtteranceResult

try:
    __version__ = version("amivoice-api-client")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "RULE_GRAMMAR_ENGINE",
    "AmiVoiceClient",
    "AmiVoiceError",
    "AuthenticationError",
    "ConfigurationError",
    "ConnectionFailedError",
    "DictionaryApiError",
    "NotificationEvent",
    "ProfileWord",
    "RecognitionError",
    "RecognitionResult",
    "SegmenterProperties",
    "StreamConnectionManager",
    "StreamEvent",
    "StreamEventType",
    "StreamSession",
    "Token",
    "UserDictionaryClient",
    "UtteranceEvent",
    "UtteranceResult",
    "build_billing_extension",
    "build_grammar_file_names",
    "encode_grammar",
    "transcribe",
]
