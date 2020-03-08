Python + Qt Playground
======================

Initialization
--------------

```
python3 -m venv venv
. venv/bin/activate
python3 -m pip install -U pip setuptools
python3 -m pip install -U -r requirements.txt
```

Examples
--------

* `python3 -m helloapp` - A simple hello app using QML.
* `python3 -m offscreen` - Offscreen rendering (buggy).
  In order to get focus, you need to click the content of *View* and *Web* tabs, then focus another
  window and finally click back. It also segfaults on window close.
* `python -m offproccess` - Work-in-progress offproccess rendering.
* IPC:
  * `python3 -m ipc listen addr` - file writer server on abstract Unix domain socket address `addr`.
  * `python3 -m ipc write addr /tmp/file1 /tmp/file2` - file writer client sends a file descriptors
    of passed files and data to be written by the server.
