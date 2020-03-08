from __future__ import annotations

from enum import Flag
from typing import Type, Callable, Awaitable, Tuple, List, Dict

import trio
from trio import MemorySendChannel, MemoryReceiveChannel, CancelScope

from ipc.transport import Transport, SocketType, NoDataError, Message
from ipc.types import Bytes, Fd, INT32_MAX
from ipc.utils import Result, WrappedCounter

NotificationHandler = Callable[['Connection', Bytes, List[Fd]], Awaitable[None]]
RequestHandler = Callable[['Connection', Bytes, List[Fd]], Awaitable[Tuple[Bytes, List[Fd]]]]


class Flags(Flag):
    """Message flags."""

    NONE = 0
    """No flags."""
    REQUEST = 1 << 0
    """This message is a request."""
    RESPONSE = 1 << 1
    """This message is a response to a request."""
    NOTIFICATION = 1 << 2
    """This message is a notification not receiving any response."""


class Connection:
    """
    A duplex client <-> server connection.

    Args:
        num: Connection number.
        transport_factory: A callable to provide transport for this connection.
        request_handler: A callable to handle incoming requests. Any exception will close the connection.
        notification_handler: A callable to handle incoming notifications. Any exception will close the connection.
    """

    num: int
    """Connection number."""
    transport_factory: Type[Transport]
    """A callable to provide transport for this connection."""
    request_handler: RequestHandler
    """A callable to handle incoming requests."""
    notification_handler: NotificationHandler
    """A callable to handle incoming notifications."""
    address: bytes = None
    """The address of the remote endpoint or None."""
    _socket: SocketType = None
    _transport: Transport = None
    _error: Exception = None
    _scope: CancelScope = None
    _requests: Dict[int, Result[Tuple[Bytes, List[Fd]]]]
    _outbox_sender: MemorySendChannel[Tuple[Message, Result, bool]] = None
    _outbox_receiver: MemoryReceiveChannel[Tuple[Message, Result, bool]] = None

    def __init__(self,
                 num: int,
                 transport_factory: Type[Transport],
                 request_handler: RequestHandler,
                 notification_handler: NotificationHandler) -> None:
        self.num = num
        self.transport_factory = transport_factory
        self.request_handler = request_handler
        self.notification_handler = notification_handler
        self._requests = {}
        self._notification = {}
        self._counter = WrappedCounter(1, INT32_MAX)

    def __repr__(self) -> str:
        return f'Conn#{self.num}: {self._socket}'

    async def connect(self, address: bytes, *, task_status=trio.TASK_STATUS_IGNORED) -> None:
        """
        Connect to a remote endpoint.

        Typically used by client code to establish a new connection.

        This method is an unconditional trio checkpoint.

        Args:
            address: The address to connect to.
            task_status: Passed by `trio.Nursery.start`.

        Raises:
            Exception: Any exception raised when connecting and sending/receiving messages.
                       trio.ClosedResourceError is never raised.
        """
        await trio.sleep(0)
        socket = self.transport_factory.create_socket()
        await socket.connect(address)
        await self.attach(socket, address, task_status=task_status)

    async def attach(self, socket: SocketType, address: bytes, *, task_status=trio.TASK_STATUS_IGNORED) -> None:
        """
        Attach an already connected socket.

        Typically used by server code for an accepted client connection.

        This method is an unconditional trio checkpoint.

        Args:
            socket: The socket to attach to.
            address: The address of the remote endpoint.
            task_status: Passed by `trio.Nursery.start`.

        Raises:
            Exception: Any exception raised when sending/receiving messages.
                       trio.ClosedResourceError is never raised.
        """
        await trio.sleep(0)
        if self._scope is not None:
            raise RuntimeError('Already running.')

        self.address = address
        self._socket = socket
        self._transport = self.transport_factory(socket)
        self._outbox_sender, self._outbox_receiver = trio.open_memory_channel(0)
        task_status.started()

        try:
            with CancelScope() as self._scope:
                async with trio.open_nursery() as n:
                    n.start_soon(self._read_messages)
                    n.start_soon(self._write_messages)
        finally:
            with CancelScope() as s:
                s.shield = True
                await self._shutdown()

        if self._error is not None and not isinstance(self._error, trio.ClosedResourceError):
            raise self._error

    def close(self) -> None:
        """
        Close the connection.

        Cancels running `connect`/`attach` tasks.
        """
        if self._socket is not None:
            self._socket.close()
        if self._scope is not None:
            self._scope.cancel()

    async def send(self, data: Bytes, fds: List[Fd] = None) -> Tuple[Bytes, List[Fd]]:
        """
        Send a request and wait for response.

        This method is an unconditional trio checkpoint.

        Args:
            data: Data to send.
            fds: File descriptors to send.

        Returns: Response of the request.

        Raises:
            Exception: An error occurred when sending request or receiving response.
        """
        await self._check_not_closed()

        result = Result()
        while True:
            num = next(self._counter)
            if num not in self._requests:
                break

        self._requests[num] = result
        await self._outbox_sender.send((Message(num, Flags.REQUEST.value, data, fds or []), result, True))
        data, fds = await result.wait()
        del self._requests[num]
        return data, fds

    async def notify(self, data: Bytes, fds: List[Fd] = None) -> None:
        """
        Send a notification.

        This method is an unconditional trio checkpoint.

        Args:
            data: Data to send.
            fds: File descriptors to send.

        Raises:
            Exception: An error occurred when sending request or receiving response.
        """
        await self._check_not_closed()

        result = Result()
        await self._outbox_sender.send((Message(0, Flags.NOTIFICATION.value, data, fds or []), result, False))
        await result.wait()

    async def _check_not_closed(self):
        await trio.sleep(0)
        if self._error is not None:
            raise self._error
        if self._outbox_sender is None:
            raise trio.ClosedResourceError()

    async def _read_messages(self):
        async with trio.open_nursery() as n:
            while True:
                try:
                    msg = await self._transport.read()
                    n.start_soon(self._dispatch_message, msg)
                except Exception as e:
                    if isinstance(e, NoDataError):
                        e = trio.ClosedResourceError(str(e))
                    self._set_error(e)
                    self._scope.cancel()
                    break

    async def _dispatch_message(self, msg: Message):
        await trio.sleep(0)
        if msg.flags & Flags.REQUEST.value:
            data, fds = await self.request_handler(self, msg.data, msg.fds)
            result = Result()
            await self._outbox_sender.send((Message(msg.num, Flags.RESPONSE.value, data, fds or []), result, False))
            await result.wait()
        elif msg.flags & Flags.NOTIFICATION.value:
            await self.notification_handler(self, msg.data, msg.fds)
        elif msg.flags & Flags.RESPONSE.value:
            self._requests[msg.num].set((msg.data, msg.fds))
        else:
            raise RuntimeError('Unknown message type')

    async def _write_messages(self):
        while True:
            msg, result, needs_response = await self._outbox_receiver.receive()

            try:
                await self._transport.write(msg)
                if not needs_response:
                    result.set()
            except trio.Cancelled:
                result.fail(self._set_error(trio.ClosedResourceError()))
                raise
            except Exception as e:
                result.fail(self._set_error(e))
                self._scope.cancel()
                break

    def _set_error(self, error: Exception) -> Exception:
        if self._error is None:
            self._error = error
        return self._error

    async def _shutdown(self) -> None:
        error = self._set_error(trio.ClosedResourceError())

        if self._outbox_receiver is not None:
            while True:
                try:
                    _msg, result, _needs_response = await self._outbox_receiver.receive_nowait()
                    result.fail(error)
                except trio.WouldBlock:
                    break
            await self._outbox_receiver.aclose()

        self.close()


