'''Edit-ingredient dialog: demographic + nutrition fields, allergen grid
(auto-saves on toggle), image picker with thumbnail preview, and entry
points for the price edit / price history flows.'''
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

import config
import db
from gui.dialogs.ingredient_price_edit import IngredientPriceEditDialog
from gui.dialogs.price_history import PriceHistoryDialog
from gui.images import available_images
from gui.widgets.allergen_checkbox_grid import AllergenCheckboxGrid


PREVIEW_SIZE = 200


def _image_pixmap(filename):
    if not filename:
        return None
    path = os.path.join(config.INGREDIENTS_PATH, filename)
    if not os.path.isfile(path):
        return None
    pixmap = QPixmap(path)
    if pixmap.isNull():
        return None
    return pixmap.scaled(PREVIEW_SIZE, PREVIEW_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)


class IngredientEditDialog(QDialog):
    def __init__(self, ingredient_id, parent=None):
        super().__init__(parent)
        self.ingredient_id = ingredient_id
        self.modified = False  # parent should refresh if True after exec()
        self.status_message = ''

        row = db.get_ingredients(ingredient_id)
        self.setWindowTitle(f"{config.APPNAME} | {row['Name']}")

        self._inputs = {}

        demographic_box = self._build_demographic(row)
        nutrition_box = self._build_nutrition(row)
        self.allergen_grid = AllergenCheckboxGrid(ingredient_id)
        self.allergen_grid.changed.connect(self._mark_modified)
        image_box = self._build_image(row.get('ImageFilename') or '')
        used_in_box = self._build_used_in()

        button_box = QDialogButtonBox()
        save_btn = button_box.addButton('Save', QDialogButtonBox.AcceptRole)
        save_btn.setShortcut(QKeySequence.Save)
        delete_btn = button_box.addButton('Delete Ingredient', QDialogButtonBox.DestructiveRole)
        delete_btn.setStyleSheet('background-color: #c0392b; color: white; padding: 4px 10px;')
        close_btn = button_box.addButton('Close', QDialogButtonBox.RejectRole)
        save_btn.clicked.connect(self._on_save)
        delete_btn.clicked.connect(self._on_delete)
        close_btn.clicked.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(demographic_box)
        layout.addWidget(nutrition_box)
        layout.addWidget(self.allergen_grid)
        layout.addWidget(image_box)
        layout.addWidget(used_in_box)
        layout.addWidget(button_box)

    def _build_demographic(self, row):
        box = QGroupBox('Demographic')
        form = QFormLayout(box)
        for key, label in config.ingredient_demographic_fields.items():
            if key == 'Cost':
                self.cost_edit = QLineEdit('$ {:.4f}'.format(row.get('Cost') or 0))
                self.cost_edit.setReadOnly(True)
                change_btn = QPushButton('Change')
                change_btn.clicked.connect(self._on_change_cost)
                history_btn = QPushButton('History')
                history_btn.clicked.connect(self._on_history)
                wrap = QWidget()
                wrap_layout = QHBoxLayout(wrap)
                wrap_layout.setContentsMargins(0, 0, 0, 0)
                wrap_layout.addWidget(self.cost_edit, stretch=1)
                wrap_layout.addWidget(change_btn)
                wrap_layout.addWidget(history_btn)
                self._inputs['Cost'] = self.cost_edit
                form.addRow(label, wrap)
            else:
                edit = QLineEdit(str(row.get(key) or ''))
                if key == 'Weight':
                    edit.setValidator(QDoubleValidator(0.0, 1_000_000.0, 4))
                self._inputs[key] = edit
                form.addRow(label, edit)
        return box

    def _build_nutrition(self, row):
        box = QGroupBox('Nutrition')
        form = QFormLayout(box)
        for key, label in config.nutrition_fields.items():
            edit = QLineEdit(str(row.get(key) or ''))
            edit.setValidator(QDoubleValidator(0.0, 1_000_000.0, 4))
            self._inputs[key] = edit
            form.addRow(label, edit)
        return box

    def _build_used_in(self):
        '''List of recipes that directly use this ingredient. Double-click
        opens that recipe's edit dialog (the panel re-fetches on return so
        removing the ingredient from a recipe is reflected immediately).'''
        box = QGroupBox('Used in recipes')
        self.used_in_list = QListWidget()
        self.used_in_list.setMaximumHeight(120)
        self.used_in_list.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.used_in_list.itemActivated.connect(self._on_used_in_activated)

        self.used_in_empty = QLabel('(not used in any recipes)')
        self.used_in_empty.setEnabled(False)

        self.used_in_stack = QStackedWidget()
        self.used_in_stack.addWidget(self.used_in_list)   # index 0
        self.used_in_stack.addWidget(self.used_in_empty)  # index 1

        layout = QVBoxLayout(box)
        layout.addWidget(self.used_in_stack)

        self._refresh_used_in()
        return box

    def _refresh_used_in(self):
        recipes = db.get_recipes_using_ingredient(self.ingredient_id)
        self.used_in_list.clear()
        if not recipes:
            self.used_in_stack.setCurrentIndex(1)
            return
        self.used_in_stack.setCurrentIndex(0)
        for r in recipes:
            item = QListWidgetItem(r['Name'])
            item.setData(Qt.UserRole, r['Id'])
            self.used_in_list.addItem(item)

    def _on_used_in_activated(self, item):
        recipe_id = item.data(Qt.UserRole)
        # Lazy import: ingredient_edit and recipe_edit would otherwise risk
        # a cycle if recipe_edit ever needed to open an ingredient.
        from gui.dialogs.recipe_edit import RecipeEditDialog
        dlg = RecipeEditDialog(recipe_id, parent=self)
        dlg.exec()
        if dlg.modified:
            # The recipe may have removed this ingredient — re-query so the
            # list reflects current state. Also bubble up so the main window
            # refreshes after this dialog closes.
            self.modified = True
            self._refresh_used_in()

    def _build_image(self, current_filename):
        box = QGroupBox('Image')
        self.image_combo = QComboBox()
        self.image_combo.addItems(available_images())
        idx = self.image_combo.findText(current_filename)
        if idx >= 0:
            self.image_combo.setCurrentIndex(idx)
        self.image_combo.currentTextChanged.connect(self._on_image_changed)

        refresh_btn = QPushButton('Refresh')
        refresh_btn.clicked.connect(self._on_refresh_images)

        self.image_preview = QLabel()
        self.image_preview.setFixedSize(PREVIEW_SIZE, PREVIEW_SIZE)
        self.image_preview.setAlignment(Qt.AlignCenter)
        self.image_preview.setStyleSheet('border: 1px solid #ccc;')
        self._set_preview(current_filename)

        file_row = QHBoxLayout()
        file_row.addWidget(QLabel('File'))
        file_row.addWidget(self.image_combo, stretch=1)
        file_row.addWidget(refresh_btn)

        layout = QVBoxLayout(box)
        layout.addLayout(file_row)
        layout.addWidget(self.image_preview, alignment=Qt.AlignCenter)
        return box

    # --- helpers ---

    def _set_preview(self, filename):
        pixmap = _image_pixmap(filename)
        if pixmap is None:
            self.image_preview.clear()
            self.image_preview.setText('(no image)')
        else:
            self.image_preview.setPixmap(pixmap)

    def _collect_values(self):
        values = {key: edit.text() for key, edit in self._inputs.items()}
        values['ImageFilename'] = self.image_combo.currentText() or None
        return values

    def _mark_modified(self, *_):
        self.modified = True

    # --- handlers ---

    def _on_save(self):
        values = self._collect_values()
        db.update_ingredient(self.ingredient_id, values)
        self.modified = True
        self.status_message = f"Saved '{values.get('Name', '') or 'ingredient'}'"
        self.accept()

    def _on_delete(self):
        name = self._inputs['Name'].text()
        if QMessageBox.question(
            self, 'Delete', f'Delete {name}?',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        try:
            db.delete_ingredient(self.ingredient_id)
        except Exception as exc:
            QMessageBox.warning(self, 'Ingredient In Use', str(exc))
            return
        self.modified = True
        self.status_message = f"Deleted '{name}'"
        self.accept()

    def _on_change_cost(self):
        dlg = IngredientPriceEditDialog(self.ingredient_id, parent=self)
        if dlg.exec() == QDialog.Accepted:
            self.modified = True
            row = db.get_ingredients(self.ingredient_id)
            self.cost_edit.setText('$ {:.4f}'.format(row.get('Cost') or 0))

    def _on_history(self):
        name = self._inputs['Name'].text()
        dlg = PriceHistoryDialog(self.ingredient_id, name, parent=self)
        dlg.exec()

    def _on_refresh_images(self):
        current = self.image_combo.currentText()
        self.image_combo.blockSignals(True)
        self.image_combo.clear()
        self.image_combo.addItems(available_images())
        idx = self.image_combo.findText(current)
        if idx >= 0:
            self.image_combo.setCurrentIndex(idx)
        self.image_combo.blockSignals(False)
        self._set_preview(self.image_combo.currentText())

    def _on_image_changed(self, filename):
        self._set_preview(filename)
