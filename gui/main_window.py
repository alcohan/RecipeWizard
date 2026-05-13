from PySide6.QtWidgets import QLabel, QMainWindow

import config


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(config.APPNAME)
        self.resize(900, 600)
        self.setCentralWidget(QLabel('PySide6 main window — Phase 0 scaffold'))
