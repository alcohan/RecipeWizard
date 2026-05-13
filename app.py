'''RecipeWizard entry point. Initializes/migrates the SQLite database on
first import, then boots the PySide6 application.'''
import os
import sqlite3
import sys

import config
import setup


def _db_initialized():
    '''True if the database file exists and has the expected schema.'''
    if not os.path.exists(config.DATABASE):
        return False
    try:
        conn = sqlite3.connect(config.DATABASE)
        try:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Ingredients'")
            return cursor.fetchone() is not None
        finally:
            conn.close()
    except sqlite3.Error:
        return False


if not _db_initialized():
    print('Database not initialized — running first-time setup')
    setup.initializeDB()
else:
    setup.migrateDB()


from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from gui.main_window import MainWindow


def _set_windows_app_user_model_id(app_id):
    '''Tell Windows this process has its own taskbar grouping. Without this,
    Windows reuses the python.exe AppUserModelID and our setWindowIcon()
    call is overridden by the generic Python interpreter icon in the taskbar.'''
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception as exc:
        print(f'Could not set AppUserModelID: {exc}')


def main():
    _set_windows_app_user_model_id('AdrianCohan.RecipeWizard')
    app = QApplication(sys.argv)
    app.setApplicationName(config.APPNAME)
    app.setWindowIcon(QIcon(config.ICON))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
