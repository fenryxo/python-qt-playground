from __future__ import annotations
import struct
from abc import ABC, abstractmethod
from collections import OrderedDict
from enum import unique, IntEnum
from typing import Union, List, Dict, Tuple, cast, TypeVar, Generic

from ipc.types import Fd, Bytes, IPCError
from ipc.convert import int32_to_bytes, int64_to_bytes, int_from_bytes, float_to_bytes, float_from_bytes

NativeType = Union[
    None, bool, int, float, str, bytes, bytearray, memoryview, Fd,
    Dict['NativeType', 'NativeType'], List['NativeType'], Tuple['NativeType', ...]]

T = TypeVar('T')


@unique
class Markers(IntEnum):
    """Markers of data types and data structures in encoded message."""
    FALSE = 0
    TRUE = 1
    NONE = 2
    INT64 = 3
    DOUBLE = 4
    STRING = 5
    BYTES = 6
    ARRAY_START = 7
    ARRAY_END = 8
    DICT_START = 9
    DICT_END = 10
    FD = 11


class CodecError(IPCError):
    """An error occurring during encoding/decoding."""


class EncoderError(CodecError):
    """An error occurring during encoding."""


class DecoderError(CodecError):
    """An error occurring during decoding."""


class Codec(Generic[T], ABC):
    """A codec encodes a message to bytes and decodes bytes to a message."""

    @abstractmethod
    def encode(self, msg: T) -> Tuple[Bytes, List[Fd]]:
        """
        Encode message as binary data.

        Implementations may differ in the exact type of the message.

        Args:
            msg: A message to encode.

        Returns:
            A tuple (data, fds) where data are encoded data and fds are file descriptors
            to send along with the data.

        Raises:
            EncoderError: On failure.
        """
        raise NotImplementedError

    @abstractmethod
    def decode(self, data: Bytes, fds: List[Fd]) -> T:
        """
        Decode message from binary data.

        Implementations may differ in the exact type of the message.

        Args:
            data: Data to deserialize.
            fds: File descriptors to attach to decoded message.

        Returns:
             Decoded message.

        Raises:
            DecoderError: On failure.
        """
        raise NotImplementedError


class NativeCodec(Codec[NativeType]):
    """
    Native coded supports messages consisting of a subset of native Python types.

    See NativeType for supported types.
    """

    def encode(self, msg: NativeType) -> Tuple[Bytes, List[Fd]]:
        """
        Encode a message consisting of a subset of native Python types.

        See function serialize for details.
        """
        return serialize(msg)

    def decode(self, data: Bytes, fds: List[Fd]) -> NativeType:
        """
        Decode a message consisting of a subset of native Python types.

        See function deserialize for details.
        """
        return deserialize(data, fds)


def serialize(value: NativeType) -> Tuple[bytearray, List[Fd]]:
    """
    Serialize a subset of native Python types.

    See NativeType for supported types.

    Args:
        value: Data to serialize.

    Returns:
        A tuple (data, fds) where data are serialized data and fds are file descriptors
        to send along with the data.

    Raises:
        EncoderError: On failure.
    """
    data = bytearray()
    fds: List[Fd] = []
    _serialize(data, fds, value)
    return data, fds


def _serialize(buffer: bytearray, fds: List[Fd], value: NativeType) -> None:
    # TODO: refactor to reduce complexity
    if value is None:
        buffer += int32_to_bytes(Markers.NONE)
    elif value is True:
        buffer += int32_to_bytes(Markers.TRUE)
    elif value is False:
        buffer += int32_to_bytes(Markers.FALSE)
    elif isinstance(value, int):
        buffer += int32_to_bytes(Markers.INT64)
        buffer += int64_to_bytes(value)
    elif isinstance(value, float):
        buffer += int32_to_bytes(Markers.DOUBLE)
        buffer += float_to_bytes(value)
    elif isinstance(value, str):
        value = value.encode('utf-8')
        buffer += int32_to_bytes(Markers.STRING)
        buffer += int32_to_bytes(len(value))
        buffer += value
    elif isinstance(value, (bytes, memoryview)):
        buffer += int32_to_bytes(Markers.BYTES)
        buffer += int32_to_bytes(len(value))
        buffer += value
    elif isinstance(value, (list, tuple)):
        buffer += int32_to_bytes(Markers.ARRAY_START)
        for item in value:
            _serialize(buffer, fds, item)
        buffer += int32_to_bytes(Markers.ARRAY_END)
    elif isinstance(value, (dict, OrderedDict)):
        buffer += int32_to_bytes(Markers.DICT_START)
        for key, value in value.items():
            _serialize(buffer, fds, key)
            _serialize(buffer, fds, value)
        buffer += int32_to_bytes(Markers.DICT_END)
    elif isinstance(value, Fd):
        buffer += int32_to_bytes(Markers.FD)
        buffer += int32_to_bytes(len(fds))
        fds.append(value)
    else:
        raise EncoderError(f'Unsupported type {type(value)} for value {value!r}.')


def deserialize(data: Union[bytes, bytearray, memoryview], fds: List[Fd]) -> NativeType:
    """
    Deserialize data to subset of native Python types.

    See NativeType for supported types.

    Args:
        data: Data to deserialize.
        fds: File descriptors to attach to deserialized data.

    Returns:
         Deserialized data.

    Raises:
        DecoderError: On failure.
    """
    if not isinstance(data, memoryview):
        data = memoryview(data)

    try:
        end, value = _deserialize(fds, data)
    except (ValueError, IndexError, struct.error) as e:
        raise DecoderError(f'Decoder failure: {e}')
    if end:
        raise DecoderError(f'Decoding ended with extra data: {end.tobytes()}.')
    if isinstance(value, Markers):
        raise DecoderError(f'Value cannot be {value}.')
    return value


def _deserialize(fds: List[Fd], data: memoryview) -> Tuple[memoryview, Union[Markers, NativeType]]:
    # TODO: refactor to reduce complexity
    type_ = int_from_bytes(data[0:4])
    if type_ == Markers.NONE:
        return data[4:], None
    if type_ == Markers.FALSE:
        return data[4:], False
    if type_ == Markers.TRUE:
        return data[4:], True
    if type_ == Markers.FD:
        return data[8:], fds[int_from_bytes(data[4:8])]
    if type_ == Markers.INT64:
        return data[12:], int_from_bytes(data[4:12])
    if type_ == Markers.DOUBLE:
        return data[12:], float_from_bytes(data[4:12])
    if type_ == Markers.STRING:
        end = 8 + int_from_bytes(data[4:8])
        return data[end:], str(cast(bytes, data[8:end]), encoding='utf-8')
    if type_ == Markers.BYTES:
        end = 8 + int_from_bytes(data[4:8])
        return data[end:], data[8:end].tobytes()
    if type_ == Markers.ARRAY_START:
        result = []
        data = data[4:]

        while True:
            data, value = _deserialize(fds, data)
            if value is Markers.ARRAY_END:
                break
            if isinstance(value, Markers):
                raise DecoderError(f'Value cannot be {value}.')
            result.append(value)
        return data, result
    if type_ == Markers.DICT_START:
        result = {}
        data = data[4:]

        while True:
            data, key = _deserialize(fds, data)
            if key is Markers.DICT_END:
                break
            if isinstance(key, Markers):
                raise DecoderError(f'Value cannot be {key}.')

            data, value = _deserialize(fds, data)
            if isinstance(value, Markers):
                raise DecoderError(f'Value cannot be {value}.')
            result[key] = value
        return data, result

    if type_ == Markers.DICT_END:
        return data[4:], Markers.DICT_END
    if type_ == Markers.ARRAY_END:
        return data[4:], Markers.ARRAY_END
    raise DecoderError(f'Unknown data type: {type_}.')


