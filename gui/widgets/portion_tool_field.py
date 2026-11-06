'''Make an ingredient's Portion tool QLineEdit pick from Configure ›
Portion tools while still taking free text ("Half", "Portion Cup").

attach_tool_picker(edit) adds a completer of tool names and a ▾ button
listing the tools; the tooltip says what the text links to.
'''
from PySide6.QtCore import Qt, QStringListModel
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap, QPolygonF
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QCompleter, QLineEdit, QMenu

import db
from utilities import recipe_print


def _arrow_icon():
    pm = QPixmap(16, 16)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor('#55624c'))
    p.drawPolygon(QPolygonF([QPointF(4, 6), QPointF(12, 6), QPointF(8, 11)]))
    p.end()
    return QIcon(pm)


def _dot_icon(color):
    pm = QPixmap(14, 14)
    pm.fill(Qt.transparent)
    if color:
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QColor(0, 0, 0, 110))
        p.setBrush(QColor(color))
        p.drawEllipse(2, 2, 10, 10)
        p.end()
    return QIcon(pm)


def describe(tool):
    if tool is None:
        return 'Not a portion tool: prints only when a recipe uses exactly one unit.'
    if tool.sized:
        family = f' · {tool.family}' if tool.family else ''
        return f'{tool.name}: {recipe_print.fraction_text(tool.size_floz)} fl oz scoop{family}'
    return f'{tool.name}: prints by name'


def attach_tool_picker(edit: QLineEdit):
    try:
        tools = db.portion_tool_objects()
    except Exception:   # an old library mid-migration: plain text still works
        return
    completer = QCompleter(QStringListModel([t.name for t in tools], edit), edit)
    completer.setCaseSensitivity(Qt.CaseInsensitive)
    completer.setCompletionMode(QCompleter.PopupCompletion)
    edit.setCompleter(completer)

    menu = QMenu(edit)
    for t in tools:
        label = f'{t.name}   {recipe_print.fraction_text(t.size_floz)} fl oz' if t.sized else t.name
        action = menu.addAction(_dot_icon(t.color if t.sized else None), label)
        action.triggered.connect(lambda _c=False, name=t.name: edit.setText(name))
    button = QAction(_arrow_icon(), 'Pick a portion tool', edit)
    button.triggered.connect(lambda: menu.exec(edit.mapToGlobal(edit.rect().bottomLeft())))
    edit.addAction(button, QLineEdit.TrailingPosition)

    def sync(text):
        edit.setToolTip(describe(recipe_print.find_tool(text, tools)) if text.strip() else
                        'Pick a tool, or type how it’s portioned')
    edit.textChanged.connect(sync)
    sync(edit.text())
