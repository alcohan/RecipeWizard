'''PySide6 entry point for RecipeWizard.

Coexists with the legacy PySimpleGUI `app.py` during migration. Once parity
is reached this file is renamed to `app.py` and the old GUI deleted.'''
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


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(config.APPNAME)
    app.setWindowIcon(QIcon(config.ICON))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
