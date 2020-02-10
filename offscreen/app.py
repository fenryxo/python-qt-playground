import os
from typing import List

from PySide2.QtGui import QSurfaceFormat
from PySide2.QtWebEngine import QtWebEngine
from PySide2.QtWidgets import QApplication

from offscreen.gui import MainWindow


class Application(QApplication):
    def __init__(self, argv: List[str]):
        super().__init__(argv)
        self.setApplicationName('Qt Offscreen Rendering')

        format = QSurfaceFormat()
        format.setDepthBufferSize(16)
        format.setStencilBufferSize(8)

        self.window = MainWindow(format)
        self.window.addQmlView('View', os.path.join(os.path.dirname(__file__), 'view.qml'))
        self.window.addQmlView('Web', os.path.join(os.path.dirname(__file__), 'web.qml'))

    def exec(self) -> int:
        self.window.resize(400, 400)
        self.window.show()
        return self.exec_()

    @classmethod
    def run(cls, argv: List[str]) -> int:
        QtWebEngine.initialize()
        app = cls(argv)
        return app.exec()
