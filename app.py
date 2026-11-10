'''RecipeWizard entry point. Shows the splash, initializes or migrates
the SQLite database, then builds the main window, reporting each stage
on the splash.

Only Qt is imported before the splash is up; config, the database and
the GUI modules load behind it.'''
import os
import sqlite3
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from gui.splash import Splash


def _db_initialized(path):
    '''True if the database file exists and has the expected schema.'''
    if not os.path.exists(path):
        return False
    try:
        conn = sqlite3.connect(path)
        try:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Ingredients'")
            return cursor.fetchone() is not None
        finally:
            conn.close()
    except sqlite3.Error:
        return False


def _set_windows_app_user_model_id(app_id):
    '''Tell Windows this process has its own taskbar grouping. Without this,
    Windows reuses the python.exe AppUserModelID and our setWindowIcon()
    call is overridden by the generic Python interpreter icon in the taskbar.

    Source runs only: RecipeWizard.exe already has its own identity, and
    an explicit ID would stop its window grouping with a pinned shortcut
    to the exe, so a pinned app would open as a second taskbar button.'''
    if sys.platform != 'win32' or getattr(sys, 'frozen', False):
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception as exc:
        print(f'Could not set AppUserModelID: {exc}')


def _start(app, splash):
    '''Everything between the splash appearing and the window showing.
    Progress fractions follow how long each stage takes on a warm start.'''
    splash.step('Starting…', 0.02)
    import config
    import setup
    splash.set_version(f'Version {config.__version__}')
    app.setWindowIcon(QIcon(config.ICON))

    if not _db_initialized(config.DATABASE):
        print('Database not initialized — running first-time setup')
        splash.step('Creating your library…', 0.2)
        setup.initializeDB()
    else:
        splash.step('Opening your library…', 0.2)
        setup.migrateDB()

    splash.step('Loading…', 0.24)
    from gui.main_window import MainWindow
    window = MainWindow(progress=splash.step)
    window.show()
    splash.finish(window)
    return window


def main():
    _set_windows_app_user_model_id('AdrianCohan.RecipeWizard')
    app = QApplication(sys.argv)
    # Organization + application names back QSettings (window geometry,
    # splitter state, last-active tab) under HKCU\Software\AdrianCohan\RecipeWizard
    # on Windows.
    app.setOrganizationName('AdrianCohan')
    app.setApplicationName('RecipeWizard')
    splash = Splash()
    splash.show()
    try:
        window = _start(app, splash)
    except Exception as exc:
        splash.close()
        QMessageBox.critical(None, 'RecipeWizard', f"RecipeWizard couldn't start.\n\n{exc}")
        raise
    # After the upgrade to portion rules, offer the review once.
    QTimer.singleShot(0, window.show_portion_review_if_new)
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
