"""AmiVoice 高レベル Python クライアントのパブリックエクスポート。"""

from importlib.metadata import PackageNotFoundError, version

from ._billing import build_billing_extension
from ._segmenter import SegmenterProperties
from ._stream import StreamConnectionManager, StreamSession
from .api_key import ApiKeyIssuanceClient
from .client import AmiVoiceClient, transcribe
from .constants import Codec, Engine
from .dictionary import ProfileWord, UserDictionaryClient, build_profile_words
from .exceptions import (
    AmiVoiceError,
    ApiKeyIssuanceApiError,
    AuthenticationError,
    ConfigurationError,
    ConnectionFailedError,
    DictionaryApiError,
    RecognitionError,
)
from .grammar import build_grammar_file_names, encode_grammar
from .models import NotificationEvent, RecognitionResult, StreamEvent, StreamEventType, Token, UtteranceEvent, UtteranceResult

try:
    __version__ = version("amivoice-api-client")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "AmiVoiceClient",
    "AmiVoiceError",
    "ApiKeyIssuanceApiError",
    "ApiKeyIssuanceClient",
    "AuthenticationError",
    "Codec",
    "ConfigurationError",
    "ConnectionFailedError",
    "DictionaryApiError",
    "Engine",
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
    "build_profile_words",
    "encode_grammar",
    "transcribe",
]
