from typing import Iterator, TypeVar, Generic, Optional

import trio

T = TypeVar('T')


class WrappedCounter(Iterator[int]):
    """
    A counter that wraps after the maximal value is reached.

    Args:
        start: The initial value.
        limit: The maximal value.

    Raises:
        ValueError: If start is not lesser than limit.
    """

    start: int
    """Initial value."""
    limit: int
    """The maximal value."""
    value: int
    """The next value to yield."""

    def __init__(self, start: int, limit: int):
        if start >= limit:
            raise ValueError(f'Start ({start}) must be lesser than limit ({limit}).')
        self.start = start
        self.limit = limit
        self.value = start

    def next(self) -> int:
        """Return the next value."""
        if self.value >= self.limit:
            self.value = self.start
            return self.limit

        value = self.value
        self.value += 1
        return value

    __next__ = next


class Result(Generic[T]):
    """
    Synchronization primitive for asynchronous result.

    The initiating tasks waits for the results via `wait` until another task sets value/error
    via `set`/`fail`.

    """

    value: Optional[T] = None
    """The result of an asynchronous task."""
    error: Optional[Exception] = None
    """The failure of an asynchronous task."""

    def __init__(self):
        self._event = trio.Event()

    def set(self, value: Optional[T] = None) -> None:
        """Set the result of an asynchronous task and mark it as finished."""
        self.value = value
        self._event.set()

    def fail(self, error: Exception) -> None:
        """Set the failure of an asynchronous task and mark it as finished."""
        self.error = error
        self._event.set()

    async def wait(self) -> Optional[T]:
        """
        Wait for the result of an asynchronous task.

        Returns: The value set with `set`.

        Raises:
            Exception: Any exception set with `fail`.
        """
        await self._event.wait()
        if self.error is not None:
            raise self.error
        return self.value
