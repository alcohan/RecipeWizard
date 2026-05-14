'''Pick an ingredient or sub-recipe to add as a component.

Uses a filterable QListWidget rather than QCompleter so the full eligible
set is visible up front (mirrors the old PySimpleGUI listbox UX) and so
Enter inside the filter input can't auto-pick the first item — selection
is always explicit.

A custom delegate paints a colored pill badge next to each row:
  - Sub-recipes always show a violet "recipe" badge.
  - Ingredients with a category tag show that tag in its color.
  - Untagged ingredients show no badge — the name slides to the left.
The badge text + mode + tag are all in item.text() so the typing filter
can narrow on any of them.'''
from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QDoubleValidator, QKeySequence, QPainter
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QStyle, QStyledItemDelegate, QVBoxLayout,
)

import config
import db
from gui.widgets.tag_badge import paint_tag_badge


# Sub-recipes always get a violet "recipe" badge regardless of which
# format tag they happen to have. Keeps the picker focused on the
# ingredient/sub-recipe distinction.
_RECIPE_BADGE_COLOR = '#7c3aed'
# Neutral fallback if an ingredient's tag color is somehow missing.
_DEFAULT_TAG_COLOR = '#64748b'


class _ComponentTypeBadgeDelegate(QStyledItemDelegate):
    '''Paints each row as: [colored tag badge] name (unit). Reads the row
    tuple (id, mode, name, unit, tag_name, tag_color) from Qt.UserRole.
    Doesn't paint item.text() — that's the filter-search target.'''

    ROW_HEIGHT = 32
    PAD_X = 8
    BADGE_GAP = 10

    def paint(self, painter, option, index):
        row_data = index.data(Qt.UserRole)
        if not row_data:
            super().paint(painter, option, index)
            return
        _id, mode, name, unit, tag_name, tag_color = row_data

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        # Standard selection background.
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
            text_color = option.palette.highlightedText().color()
        else:
            text_color = option.palette.text().color()

        # Badge: sub-recipes always show "recipe"; ingredients show their
        # category tag if they have one. Untagged ingredients get no badge —
        # the name slides over and the row reads as visually quieter.
        if mode == 'recipe':
            badge_text, badge_color = 'recipe', _RECIPE_BADGE_COLOR
        elif tag_name:
            badge_text, badge_color = tag_name, (tag_color or _DEFAULT_TAG_COLOR)
        else:
            badge_text, badge_color = None, None

        if badge_text is not None:
            badge_area = option.rect.adjusted(self.PAD_X, 0, 0, 0)
            badge_rect = paint_tag_badge(painter, badge_area, badge_text, badge_color, option.font)
            text_x = badge_rect.right() + self.BADGE_GAP
        else:
            text_x = option.rect.x() + self.PAD_X

        # Name + unit text after wherever the badge ended, elided to fit.
        painter.setPen(text_color)
        fm_text = painter.fontMetrics()
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

        # tuples come back as (id, mode, name, unit, tag_name, tag_color)
        self._eligible = db.get_eligible_ingredients(recipe_id)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(
            'Type to filter — name, "recipe", or a tag like "greens"…'
        )
        self.filter_edit.textChanged.connect(self._on_filter)

        self.results = QListWidget()
        self.results.setItemDelegate(_ComponentTypeBadgeDelegate(self.results))
        # Item text drives the typing filter only — the delegate ignores it
        # for display. Only include tokens that the user can actually see on
        # the row, so typing a word never returns invisible "matches":
        #   - sub-recipes carry "recipe" (their visible badge)
        #   - tagged ingredients carry their tag name
        #   - untagged ingredients carry only name + unit
        for row in self._eligible:
            child_id, mode, name, unit, tag_name, tag_color = row
            tokens = [unit]
            if mode == 'recipe':
                tokens.append('recipe')
            elif tag_name:
                tokens.append(tag_name)
            search_extras = ' '.join(filter(None, tokens))
            item = QListWidgetItem(f'{name} ({search_extras})')
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
        unit = current.data(Qt.UserRole)[3]
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
