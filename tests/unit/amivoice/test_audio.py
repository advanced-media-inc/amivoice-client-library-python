# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

"""_audio モジュールのユニットテスト。"""

import io
from pathlib import Path

import pytest

from amivoice._audio import resolve_audio


def test_resolve_audio_bytes_input_valid_return_bytes() -> None:
    """Bytes を渡すとそのまま返すことを確認する。"""
    # Given: bytes 型の音声データ
    audio = b"raw-audio"

    # When: resolve_audio を呼び出す
    result = resolve_audio(audio)

    # Then: 入力と同一の bytes が返る
    assert result == b"raw-audio"


def test_resolve_audio_binary_io_input_valid_return_bytes() -> None:
    """BinaryIO を渡すと内容が読み出されることを確認する。"""
    # Given: BytesIO に格納された音声データ
    audio = io.BytesIO(b"stream-data")

    # When: resolve_audio を呼び出す
    result = resolve_audio(audio)

    # Then: ストリームの内容が返る
    assert result == b"stream-data"


def test_resolve_audio_string_path_input_valid_return_bytes(tmp_path: Path) -> None:
    """文字列パスを渡すとファイル内容が読み出されることを確認する。"""
    # Given: 一時ファイルと文字列パス
    audio_file = tmp_path / "test.raw"
    audio_file.write_bytes(b"file-data")

    # When: resolve_audio を文字列パスで呼び出す
    result = resolve_audio(str(audio_file))

    # Then: ファイル内容が返る
    assert result == b"file-data"


def test_resolve_audio_path_object_input_valid_return_bytes(tmp_path: Path) -> None:
    """Path オブジェクトを渡すとファイル内容が読み出されることを確認する。"""
    # Given: 一時ファイルと Path オブジェクト
    audio_file = tmp_path / "test.raw"
    audio_file.write_bytes(b"path-data")

    # When: resolve_audio を Path オブジェクトで呼び出す
    result = resolve_audio(audio_file)

    # Then: ファイル内容が返る
    assert result == b"path-data"


def test_resolve_audio_unsupported_type_invalid_raise_TypeError() -> None:
    """サポート外の型を渡すと TypeError が送出されることを確認する。"""
    # Given: サポートされていない整数型の音声ソース
    audio = 12345

    # When / Then: resolve_audio を呼び出すと TypeError が送出される
    with pytest.raises(TypeError, match="Unsupported audio source type"):
        resolve_audio(audio)
