# main.py
import sys
import os
from PyQt5 import QtCore, QtWidgets, QtWebEngineWidgets
from pkg_resources import resource_string


class Browser(QtWebEngineWidgets.QWebEngineView):

    def __init__(self, url):
        super().__init__()

        with open(url, 'r') as file:
            html = file.read()


        # With QWebEnginePage.setHtml, the html is loaded immediately.
        # baseUrl is used to resolve relative URLs in the document.
        # For whatever reason, it seems like the baseUrl resolves to
        # the parent of the path, not the baseUrl itself.  As a
        # workaround, either append a dummy directory to the base url
        # or start all relative paths in the html with the current
        # directory.
        # https://doc-snapshots.qt.io/qtforpython-5.15/PySide2/QtWebEngineWidgets/QWebEnginePage.html#PySide2.QtWebEngineWidgets.PySide2.QtWebEngineWidgets.QWebEnginePage.setHtml
        here = os.path.dirname(os.path.abspath(__file__)).replace('\\', '/')
        base_path = os.path.join(os.path.dirname(here), 'static/bogus').replace('\\', '/')
        print('base path: ', base_path)
        self.url = QtCore.QUrl('file:///' + base_path)
        self.page().setHtml(html, baseUrl=self.url)


class MainWindow(QtWidgets.QMainWindow):

    def __init__(self, url):
        super().__init__()

        self.init_widgets(url)
        self.init_layout()

    def init_widgets(self, url):
        self.browser = Browser(url)
        self.browser.loadFinished.connect(self.load_finished)

    def init_layout(self):
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.browser)

        centralWidget = QtWidgets.QWidget()
        centralWidget.setLayout(layout)
        self.setCentralWidget(centralWidget)

    def load_finished(self, status):
        self.msg = QtWidgets.QMessageBox()
        self.msg.setIcon(QtWidgets.QMessageBox.Information)
        self.msg.setWindowTitle('Load Status')



def render(url):
    app = QtWidgets.QApplication(sys.argv)
    main_window = MainWindow(url)
    main_window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    render('static/label.html')