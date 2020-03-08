from __future__ import annotations
from pprint import pformat
import random
from typing import List, Any, Optional, Tuple

import trio

from ipc import NativeCodec
from ipc import Server
from ipc import Connection
from ipc import PacketTransport
from ipc import Fd, Bytes


def run(argv: List[str]):
    action, address = argv[1:3]
    assert address
    address = b'\0' + address.encode('utf-8')
    if action == 'listen':
        trio.run(run_server, address)
    elif action == 'write':
        trio.run(run_client, address, argv[3:])
    else:
        raise ValueError(f'Unknown action: {action!r}')


async def run_server(address: bytes):
    server = FileWriterServer()
    await server.serve(address)


async def run_client(address, paths: List[str]):
    data = {
        "string": True,
        b"binary": False,
        'int': 123,
        'double': 3.14,
        'array': [False, True, None, 123, 3.14, 'hello', b'world']
    }

    client = FileWriterClient()

    async with trio.open_nursery() as nursery:
        await nursery.start(client.connect, address)

        async with trio.open_nursery() as nursery2:
            for path in paths:
                nursery2.start_soon(client.write, path, [data] * random.randint(1, 10))

        await client.quit()


class FileWriterServer:
    def __init__(self):
        self.quit_event = trio.Event()
        self.codec = NativeCodec()
        self.server = Server(PacketTransport,
                             self._handle_request,
                             self._handle_notification,
                             self._handle_error)

    async def serve(self, address: bytes, *, task_status=trio.TASK_STATUS_IGNORED):
        async with trio.open_nursery() as n:

            async def wait_quit():
                await self.quit_event.wait()
                await trio.sleep(1)
                self.server.close()

            n.start_soon(wait_quit)
            await n.start(self.server.serve, address)
            print(f'Server starts: {self.server._socket}')
            task_status.started()

    def quit(self):
        self.quit_event.set()

    async def call(self, conn: Connection, method: str, *args: Any) -> Any:
        data, fds = self.codec.encode([method, *args])
        data, fds = await conn.send(data, fds)
        return self.codec.decode(data, fds)

    async def _handle_request(self, conn: Connection, data: Bytes, fds: List[Fd]) -> Tuple[Bytes, List[Fd]]:
        method, *args = self.codec.decode(data, fds)
        if method == "quit":
            print('Quit?')
            if await self.call(conn, 'quit?'):
                print('Quit!')
                self.quit()
            else:
                print('Nope!')
            result = True,
        elif method == "write":
            fd, content = args
            print(f'Writing to fd {fd.get()}.')
            try:
                with open(fd.take(), 'at') as fh:
                    written = fh.write(pformat(content) + '\n')
                    result = True, written
            except Exception as e:
                result = False, str(e)
        else:
            result = False, 'unknown method', method
        return self.codec.encode(result)

    async def _handle_notification(self, conn: Connection, data: Bytes, fds: List[Fd]) -> None:
        raise NotImplementedError

    async def _handle_error(self, conn: Connection, err: Exception):
        print('Error:', conn, err)
        self.quit()
        raise err


class FileWriterClient:
    _nursery: Optional[trio.Nursery] = None

    def __init__(self, ):
        self.conn = Connection(0, PacketTransport, self._handle_request, self._handle_notification)
        self.codec = NativeCodec()
        self._quit_event = None

    async def _handle_request(self, _conn: Connection, data: Bytes, fds: List[Fd]) -> Tuple[Bytes, List[Fd]]:
        method, *args = self.codec.decode(data, fds)
        if method == "quit?":
            result = random.choice([True, False, None])
        else:
            result = None
        return self.codec.encode(result)

    async def _handle_notification(self, conn: Connection, data: Bytes, fds: List[Fd]) -> None:
        raise NotImplementedError

    async def connect(self, address: bytes, *, task_status=trio.TASK_STATUS_IGNORED):
        print(f'Connecting to {address!r}.')
        await self.conn.connect(address, task_status=task_status)

    def close(self):
        if self._nursery is not None:
            self._nursery.cancel_scope.cancel()
            self._nursery = None
        self.conn.close()

    async def quit(self):
        await self.call('quit')
        print('Closing connection.')
        self.close()

    async def write(self, path: str, data: Any) -> None:
        print(f'Asking server to write to {path!r}.')
        with open(path, 'wt') as fh:
            fh.write(f'# {path}\n')
            ok, result = await self.call('write', Fd(fh.fileno(), duplicate=True), data)

        if ok:
            print(f'{path}: {result} bytes written')
        else:
            print(f'Error: {result}')

    async def call(self, method: str, *args: Any) -> Any:
        data, fds = self.codec.encode([method, *args])
        data, fds = await self.conn.send(data, fds)
        return self.codec.decode(data, fds)
