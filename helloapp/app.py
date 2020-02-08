import os.path
import sys

from PySide2.QtWidgets import QApplication
from PySide2.QtQuick import QQuickView
from PySide2.QtCore import QUrl


def run():
    app = QApplication(sys.argv)
    view = QQuickView()
    url = QUrl(os.path.join(os.path.dirname(__file__), 'view.qml'))

    view.setSource(url)
    view.setResizeMode(QQuickView.SizeRootObjectToView)
    view.show()
    app.exec_()
