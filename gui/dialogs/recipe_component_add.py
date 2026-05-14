'''Pick an ingredient or sub-recipe to add as a component.

Uses a filterable QListWidget rather than QCompleter so the full eligible
set is visible up front (mirrors the old PySimpleGUI listbox UX) and so
Enter inside the filter input can't auto-pick the first item — selection
is always explicit.

A custom delegate paints a colored pill badge ("ingredient" / "recipe")
next to each row. The mode text is also kept in item.text() so filter-by-
typing still works (a user can narrow to recipes by typing "recipe").'''
from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QDoubleValidator, QFont, QKeySequence, QPainter
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QStyle, QStyledItemDelegate, QVBoxLayout,
)

import config
import db


# Colors chosen for clear contrast with the white-on-color pill text and
# enough distinction from each other (selection highlight is usually a
# system-blue, which clashes with neither).
_INGREDIENT_BADGE = QColor('#16a34a')   # green
_RECIPE_BADGE = QColor('#7c3aed')        # violet


class _ComponentTypeBadgeDelegate(QStyledItemDelegate):
    '''Paints each row as: [pill badge] name (unit). Reads the row tuple
    (id, mode, name, unit) from Qt.UserRole. Doesn't paint item.text() —
    that's left containing the mode so the typing filter still matches.'''

    ROW_HEIGHT = 32
    PAD_X = 8
    BADGE_GAP = 10
    BADGE_PAD_X = 10
    BADGE_PAD_Y = 2

    def paint(self, painter, option, index):
        row_data = index.data(Qt.UserRole)
        if not row_data:
            super().paint(painter, option, index)
            return
        _id, mode, name, unit = row_data

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        # Standard selection / hover background.
        selected = bool(option.state & QStyle.State_Selected)
        if selected:
            painter.fillRect(option.rect, option.palette.highlight())
            text_color = option.palette.highlightedText().color()
        else:
            text_color = option.palette.text().color()

        base_font = QFont(option.font)
        badge_font = QFont(base_font)
        badge_font.setBold(True)
        badge_font.setPointSizeF(base_font.pointSizeF() * 0.85)

        # Badge geometry
        painter.setFont(badge_font)
        fm_badge = painter.fontMetrics()
        badge_text = mode  # "ingredient" or "recipe"
        badge_w = fm_badge.horizontalAdvance(badge_text) + self.BADGE_PAD_X * 2
        badge_h = fm_badge.height() + self.BADGE_PAD_Y * 2
        badge_x = option.rect.x() + self.PAD_X
        badge_y = option.rect.y() + (option.rect.height() - badge_h) // 2
        badge_rect = QRect(badge_x, badge_y, badge_w, badge_h)

        # Draw the pill
        badge_color = _RECIPE_BADGE if mode == 'recipe' else _INGREDIENT_BADGE
        painter.setPen(Qt.NoPen)
        painter.setBrush(badge_color)
        painter.drawRoundedRect(badge_rect, badge_h / 2, badge_h / 2)
        painter.setPen(Qt.white)
        painter.drawText(badge_rect, Qt.AlignCenter, badge_text)

        # Draw the name + unit text, elided if it doesn't fit
        painter.setFont(base_font)
        painter.setPen(text_color)
        fm_text = painter.fontMetrics()
        text_x = badge_rect.right() + self.BADGE_GAP
        text_w = option.rect.right() - text_x - self.PAD_X
        text_rect = QRect(text_x, option.rect.y(), text_w, option.rect.height())
        full_text = f'{name}  ({unit})' if unit else name
        elided = fm_text.elidedText(full_text, Qt.ElideRight, text_w)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, elided)

        painter.restore()

    def sizeHint(self, option, index):
        return QSize(option.rect.width() or 200, self.ROW_HEIGHT)


class RecipeComponentAddDialog(QDialog):
    def __init__(self, recipe_id, recipe_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f'{config.APPNAME} | {recipe_name} | > NEW <')
        self.resize(520, 520)

        self.recipe_id = recipe_id
        # `selected` and `qty` are populated on Accept.
        self.selected = None  # tuple (id, mode, name, unit)
        self.qty = None

        # tuples come back as (id, mode, name, unit)
        self._eligible = db.get_eligible_ingredients(recipe_id)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText('Type to filter (try "recipe" to narrow to sub-recipes)…')
        self.filter_edit.textChanged.connect(self._on_filter)

        self.results = QListWidget()
        self.results.setItemDelegate(_ComponentTypeBadgeDelegate(self.results))
        # Item text holds name + unit + mode so the substring filter still
        # matches mode keywords; the delegate ignores text() for display.
        for row in self._eligible:
            child_id, mode, name, unit = row
            item = QListWidgetItem(f'{name} ({unit}) {mode}')
            item.setData(Qt.UserRole, row)
            self.results.addItem(item)
        self.results.currentItemChanged.connect(self._on_selection_changed)
        self.results.itemActivated.connect(self._on_save)  # double-click or Enter on row

        self.qty_edit = QLineEdit('1')
        self.qty_edit.setValidator(QDoubleValidator(0.0, 1_000_000.0, 4))
        self.unit_label = QLabel('')

        qty_row = QFormLayout()
        qty_row.addRow('Qty', self.qty_edit)
        qty_row.addRow('', self.unit_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setShortcut(QKeySequence.Save)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        # Same fix as the USDA dialog: don't let Enter in the filter box
        # silently fire the dialog's accept button.
        for btn in buttons.buttons():
            btn.setAutoDefault(False)
            btn.setDefault(False)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f'Add to {recipe_name}'))
        layout.addWidget(self.filter_edit)
        layout.addWidget(self.results, stretch=1)
        layout.addLayout(qty_row)
        layout.addWidget(buttons)

    def _on_filter(self, text):
        needle = text.strip().lower()
        for i in range(self.results.count()):
            item = self.results.item(i)
            item.setHidden(bool(needle) and needle not in item.text().lower())

    def _on_selection_changed(self, current, _previous):
        if current is None:
            self.unit_label.setText('')
            return
        _, _, _, unit = current.data(Qt.UserRole)
        self.unit_label.setText(f'× {unit}')

    def _on_save(self, *_):
        current = self.results.currentItem()
        if current is None or current.isHidden():
            QMessageBox.warning(self, 'No Selection', 'Pick an ingredient or recipe to add.')
            return
        try:
            qty = float(self.qty_edit.text() or 0)
        except ValueError:
            QMessageBox.warning(self, 'Invalid Qty', 'Qty must be numeric.')
            return
        if qty <= 0:
            QMessageBox.warning(self, 'Invalid Qty', 'Qty must be greater than zero.')
            return
        self.selected = current.data(Qt.UserRole)
        self.qty = qty
        self.accept()
