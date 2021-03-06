from __future__ import annotations
import ctypes
import os
from typing import Any, Union

INT_SIZE = ctypes.sizeof(ctypes.c_int)
"""The size of an integer in bytes on current platform."""
INT32_SIZE = 4
"""The size of a 32bit integer in bytes."""
INT64_SIZE = 8
"""The size of a 64bit integer in bytes."""
INT32_MAX = 2147483647
"""The value of the largest 32bit signed integer."""
DOUBLE_SIZE = 8
"""The size of a double precision floating point number in bytes."""

Buffer = Union[bytearray, memoryview]
"""Types accepted as read-write byte buffers."""
Bytes = Union[bytes, bytearray, memoryview]
"""Types holding binary data which may be read only."""


class IPCError(Exception):
    """Inter-process communication error."""


class Fd:
    """
    File descriptor container with automatic closing.

    Args:
        value: The value of the file descriptor.
        duplicate: Whether to duplicate the file descriptor first.
    """

    _value: int
    _auto_close: bool

    def __init__(self, value: int, *, duplicate: bool = False):
        if value < 0:
            raise ValueError(f'Invalid file descriptor: {value}')
        if duplicate:
            value = os.dup(value)
        self._value = value
        self._auto_close = True

    @property
    def owned(self) -> bool:
        """
        Whether the file descriptor will be closed when the container is destroyed.

        You can transfer ownership with the `take` method.
        """
        return self._auto_close

    def get(self) -> int:
        """Get the value of the file descriptor."""
        return self._value

    def take(self) -> int:
        """
        Take the ownership of the file descriptor.

        Your responsibility is to close the file descriptor when not in use.

        Returns:
             The value of file descriptor.
        Raises:
            ValueError: If the value is empty.
        """
        if self._auto_close:
            self._auto_close = False
            return self._value

        return os.dup(self._value)

    def close(self) -> None:
        """Close the file descriptor early."""
        if self._auto_close:
            self._auto_close = False
            os.close(self._value)

    def __del__(self):
        self.close()

    def __str__(self) -> str:
        return f'fd:{self._value!r}'

    def __repr__(self) -> str:
        return f'Fd({self._value!r}, {self._auto_close!r})'

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, Fd) and other._value == self._value
