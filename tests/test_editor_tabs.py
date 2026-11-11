import os

import pytest


@pytest.fixture
def qapp():
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    QCoreApplication.setOrganizationName('RecipeWizardTests')
    QCoreApplication.setApplicationName('RecipeWizardTests')
    return app


@pytest.mark.parametrize('key', ['Tab', 'Backtab'])
def test_ctrl_shift_tab_cycles_back_through_library(lib, qapp, key):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget
    from gui.widgets.editor_tabs import EditorTabs

    first, second = lib.recipe('Cobb', 'Salad'), lib.recipe('Caesar', 'Salad')
    win = QWidget()
    tabs = EditorTabs(QLabel('library'))
    QVBoxLayout(win).addWidget(tabs)
    win.show()
    win.activateWindow()        # window shortcuts need the active window
    QTest.qWaitForWindowActive(win)
    tabs.open_recipe(first)
    tabs.open_recipe(second)

    def back():
        tabs.currentWidget().setFocus()
        QTest.keyClick(qapp.focusWidget() or tabs.currentWidget(), getattr(Qt, f'Key_{key}'),
                       Qt.ControlModifier | Qt.ShiftModifier)
        return tabs.currentIndex()

    tabs.setCurrentIndex(1)
    assert back() == 0          # the first recipe goes back to Library
    assert back() == 2          # and Library wraps to the last recipe
    QTest.keyClick(tabs.currentWidget(), Qt.Key_Tab, Qt.ControlModifier)
    assert tabs.currentIndex() == 0
    win.close()
