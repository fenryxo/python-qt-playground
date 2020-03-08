from __future__ import annotations
import os

from typing import Type, Callable, Awaitable, Dict

import trio
from trio import ClosedResourceError, CancelScope

from ipc.connection import Connection, RequestHandler, NotificationHandler
from ipc.transport import Transport, SocketType
from ipc.types import INT32_MAX
from ipc.utils import WrappedCounter

ErrorHandler = Callable[[Connection, Exception], Awaitable[None]]


class Server:
    """
    A server accepting duplex client connections.

    Args:
        transport_factory: A callable to provide transport for client connections.
        request_handler: A callable to handle incoming requests. Any exception will close the connection.
        notification_handler: A callable to handle incoming notifications. Any exception will close the connection.
        error_handler: A callable to handle errors of individual client connections. An exception terminates the server.
        backlog: The number of client connections to be allowed to wait in a queue.
    """

    transport_factory: Type[Transport]
    """A callable to provide transport for client connections."""
    request_handler: RequestHandler
    """A callable to handle incoming requests. Any exception will close the connection."""
    notification_handler: NotificationHandler
    """A callable to handle incoming notifications. Any exception will close the connection."""
    error_handler: ErrorHandler
    """A callable to handle errors of individual client connections. An exception terminates the server."""
    backlog: int
    """The number of client connections to be allowed to wait in a queue."""
    address: bytes = None
    """Server address."""
    connections: Dict[int, Connection]
    """Client connections."""
    _socket: SocketType = None
    _scope: CancelScope = None
    _counter: WrappedCounter

    def __init__(self,
                 transport_factory: Type[Transport],
                 request_handler: RequestHandler,
                 notification_handler: NotificationHandler,
                 error_handler: ErrorHandler,
                 backlog: int = 0) -> None:
        self.transport_factory = transport_factory
        self.request_handler = request_handler
        self.notification_handler = notification_handler
        self.error_handler = error_handler
        self.backlog = backlog
        self.connections = {}
        self._counter = WrappedCounter(1, INT32_MAX)

    async def serve(self, address: bytes, *, task_status=trio.TASK_STATUS_IGNORED) -> None:
        """
        Listen for client connections.

        This method is an unconditional trio checkpoint.

        Args:
            address: The address to listen on.
            task_status: Passed by `trio.Nursery.start`.

        Raises:
            Exception: Any exception raised when binding an address or not handled with an error handler.
                       trio.ClosedResourceError is never raised.
        """
        await trio.sleep(0)
        self.address = address
        with CancelScope() as self._scope:
            # Abstract sockets address starts with a zero byte.
            # Other addresses are filesystem paths.
            if self.address[0]:
                # Remove dangling socket.
                try:
                    os.unlink(self.address)
                except FileNotFoundError:
                    pass

            self._socket = server_socket = self.transport_factory.create_socket()
            await server_socket.bind(self.address)
            server_socket.listen(self.backlog)
            task_status.started()

            async with trio.open_nursery() as nursery:
                while True:
                    try:
                        client_socket, address = await server_socket.accept()
                    except ClosedResourceError:
                        break
                    else:
                        nursery.start_soon(self._accept, client_socket, bytes)

    async def _accept(self, socket: SocketType, address: bytes) -> None:
        while True:
            num = next(self._counter)
            if num not in self.connections:
                break

        self.connections[num] = conn = Connection(
            num, self.transport_factory, self.request_handler, self.notification_handler)
        try:
            await conn.attach(socket, address)
        except Exception as e:
            await self.error_handler(conn, e)
        finally:
            del self.connections[num]

    def close(self) -> None:
        """Close the server and client connections."""
        if self._socket is not None:
            self._socket.close()
        for conn in self.connections.values():
            conn.close()
        if self._scope is not None:
            self._scope.cancel()
