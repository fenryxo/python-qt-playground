import random

from PySide2.QtCore import Slot, QUrl, QSize, QEvent
from PySide2.QtGui import QSurfaceFormat, QMouseEvent, QFocusEvent, \
    QExposeEvent, QKeyEvent, QWheelEvent, Qt
from PySide2.QtWidgets import QWidget, QPushButton, QLabel, QVBoxLayout, QOpenGLWidget, QTabWidget

from offscreen.gl import GLTextureRectangle
from offscreen.renderers import QmlOffscreenRenderer


class MainWindow(QTabWidget):
    def __init__(self, format: QSurfaceFormat):
        super().__init__()
        self.format = format
        self.hello = ["Hallo Welt", "Hei maailma", "Hola Mundo", "Привет мир"]
        self.button = QPushButton("Change greeting")
        self.text = QLabel("Hello World")
        self.text.setAlignment(Qt.AlignCenter)

        self.layout = QVBoxLayout()
        self.layout.addWidget(self.text)
        self.layout.addWidget(self.button)
        widget = QWidget()
        widget.setLayout(self.layout)
        self.addTab(widget, 'Greetings')

        self.button.clicked.connect(self._onButtonClicked)

    @Slot()
    def _onButtonClicked(self):
        self.text.setText(random.choice(self.hello))

    def addQmlView(self, label: str, url: str):
        renderer = QmlOffscreenRenderer(QUrl(url))
        widget = OffscreenWidget(renderer, self.format)
        self.addTab(widget, label)


class OffscreenWidget(QOpenGLWidget):
    def __init__(self, renderer: QmlOffscreenRenderer, format: QSurfaceFormat):
        super().__init__()
        self.setFormat(format)
        self.renderer = renderer
        self._textureId = None
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setMouseTracking(True)

    def _handleScreenChange(self):
        self.renderer.resize(self.size() * self.devicePixelRatio())

    def _textureRendered(self, textureId: int):
        self._textureId = textureId
        self.update()

    def initializeGL(self):
        print(f'MainWindow.initializeGL: {self.size()}')
        self.renderer.rendered.connect(self._textureRendered)
        self.rectangle = GLTextureRectangle()
        self.renderer.initialize(self.size() * self.devicePixelRatio(), self.context())

    def resizeGL(self, w: int, h: int):
        print(f"resizeGL: w, h: {(w, h)} size: {self.size()} pixel ratio: {self.devicePixelRatio()}")
        self.renderer.resize(QSize(w, h) * self.devicePixelRatio())

    def paintGL(self):
        if self._textureId:
            self.rectangle.draw(self._textureId)

    def mousePressEvent(self, event: QMouseEvent):
        self.renderer.sendEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self.renderer.sendEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        self.renderer.sendEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        self.renderer.sendEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        self.renderer.sendEvent(event)

    def focusInEvent(self, event: QFocusEvent):
        self.renderer.sendEvent(event)
        event.accept()
        return True

    def focusOutEvent(self, event: QFocusEvent):
        self.renderer.sendEvent(event)

    def exposeEvent(self, event: QExposeEvent):
        self.renderer.sendEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        self.renderer.sendEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        print(event.modifiers(), event.key(), event.nativeScanCode(), event.nativeVirtualKey(), event.text())
        self.renderer.sendEvent(event)

    def enterEvent(self, event: QEvent):
        self.renderer.sendEvent(event)

    def leaveEvent(self, event: QEvent):
        self.renderer.sendEvent(event)








