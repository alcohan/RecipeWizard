'''New ingredient dialog, per the Framework canvas: look it up in USDA,
check the numbers, then save.

Left: the form — name, category, photo (drop or browse), unit, weight
per unit, portion tool, an optional first price (supplier, case price,
case yields → price per unit), nutrition per unit and allergens.
Right: the USDA lookup panel, which searches as you name the
ingredient and scales its values to the unit and weight you enter.
"Use these values" fills the nutrition (and the weight, if it was
empty) — nothing from USDA is saved without you seeing it.

One dialog for both entry points: New ingredient (USDA panel showing)
and New ingredient (Blank) (`show_usda=False`; the panel can still be
opened from the footer).

After exec(): `new_id` is the last ingredient created (0 if none),
`created_ids` every one — "Save and add another" can create several.
'''
import os
import shutil
from datetime import date

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QDoubleValidator, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

import config
import db
from gui.images import IMAGE_EXTENSIONS
from gui.thumbs import load_thumbnail
from gui.widgets.ingredient_fields import AllergenChecks, CategoryPills, NutritionGrid, StatementBox, num_text
from gui.widgets.portion_tool_field import attach_tool_picker
from gui.widgets.usda_panel import UsdaLookupPanel


_KALE = '#082c00'
_ROMAINE = '#347200'
_ROMAINE_HOVER = '#285900'
_MUTED = '#55624c'
_BORDER = '#ebe1cd'
_FIELD_BORDER = '#7d8771'
_BG = '#fffaf2'
_MONO = "ui-monospace, 'Cascadia Mono', Consolas, monospace"

_FIELD = f'''
    QLineEdit, QComboBox {{ min-height: 32px; padding: 0 10px; border: 1px solid {_FIELD_BORDER};
        border-radius: 4px; background: #ffffff; color: {_KALE}; }}
    QLineEdit:focus {{ border: 2px solid {_ROMAINE}; padding: 0 9px; }}
'''
_SECONDARY = f'''
    QPushButton {{ min-height: 34px; padding: 0 14px; border: 1px solid {_FIELD_BORDER};
        border-radius: 8px; background: #ffffff; color: {_KALE}; }}
    QPushButton:hover {{ background: #f3ece0; }}
'''


def _eyebrow(text):
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(f'color: {_MUTED}; font-size: 11px; font-weight: 600; letter-spacing: 1px;')
    return lbl


def _labelled(label, widget, width=None):
    col = QVBoxLayout()
    col.setSpacing(4)
    col.addWidget(_eyebrow(label))
    if width:
        widget.setFixedWidth(width)
    col.addWidget(widget)
    return col


class _PhotoDrop(QLabel):
    '''Drop a photo here, or click to browse. Photos are copied into the
    ingredients folder if they come from elsewhere.'''

    def __init__(self, on_file, parent=None):
        super().__init__(parent)
        self._on_file = on_file
        self.setAcceptDrops(True)
        self.setFixedSize(96, 96)
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)
        self.setCursor(Qt.PointingHandCursor)
        self.reset()

    def reset(self):
        self.setPixmap(QPixmap())
        self.setText('Photo\ndrop or browse')
        self.setStyleSheet(f'border: 1px dashed {_FIELD_BORDER}; border-radius: 8px;'
                           f' color: {_MUTED}; font-size: 11px; background: #ffffff;')

    def show_image(self, image):
        self.setText('')
        self.setStyleSheet('border: 0; border-radius: 8px;')
        self.setPixmap(QPixmap.fromImage(image))

    def mousePressEvent(self, event):
        exts = ' '.join(f'*{e}' for e in IMAGE_EXTENSIONS)
        path, _ = QFileDialog.getOpenFileName(self, 'Choose a photo', config.INGREDIENTS_PATH,
                                              f'Images ({exts})')
        if path:
            self._on_file(path)

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls()
        if urls and os.path.splitext(urls[0].toLocalFile())[1].lower() in IMAGE_EXTENSIONS:
            event.acceptProposedAction()

    def dropEvent(self, event):
        self._on_file(event.mimeData().urls()[0].toLocalFile())


class IngredientNewDialog(QDialog):
    def __init__(self, parent=None, name='', show_usda=True):
        super().__init__(parent)
        self.setWindowTitle(f'{config.APPNAME} | New ingredient')
        self.resize(1100 if show_usda else 700, 800)
        self.setStyleSheet(f'QDialog {{ background: #ffffff; }} QLabel {{ color: {_KALE}; }}'
                           f' QCheckBox {{ color: {_KALE}; }}')
        self.new_id = 0
        self.created_ids = []
        self.status_message = ''
        self._image = ''

        header = self._build_header()
        form = self._build_form()
        form_scroll = QScrollArea()
        form_scroll.setWidget(form)
        form_scroll.setWidgetResizable(True)
        form_scroll.setFrameShape(QFrame.NoFrame)

        self.usda = UsdaLookupPanel()
        self.usda.valuesChosen.connect(self._apply_usda)
        self.usda.setFixedWidth(420)
        self.usda.setStyleSheet(self.usda.styleSheet() + f' QFrame#UsdaPanel {{ border-left: 1px solid {_BORDER}; }}')
        self.usda.setVisible(show_usda)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(form_scroll, stretch=1)
        body.addWidget(self.usda)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
        layout.addLayout(body, stretch=1)
        layout.addWidget(self._build_footer())

        # The USDA search follows the name you type (debounced), until
        # you search for something else yourself.
        self._follow_name = True
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(700)
        self._search_timer.timeout.connect(self._search_from_name)
        self.usda.query.textEdited.connect(lambda _t: setattr(self, '_follow_name', False))

        QShortcut(QKeySequence.Save, self, activated=self._on_save)
        if name:
            self.name_edit.setText(name)
            self._search_from_name()
        self._sync_target()
        self._baseline = self._state()
        self.name_edit.setFocus()

    # --- building ------------------------------------------------------

    def _build_header(self):
        bar = QFrame()
        bar.setObjectName('Header')
        bar.setStyleSheet(f'QFrame#Header {{ background: #ffffff; border-bottom: 1px solid {_BORDER}; }}')
        title = QLabel('New ingredient')
        title.setStyleSheet(f'color: {_KALE}; font-size: 20px; font-weight: 650;')
        sub = QLabel('Look it up in USDA, check the numbers, then save')
        sub.setStyleSheet(f'color: {_MUTED}; font-size: 12px;')
        hl = QHBoxLayout(bar)
        hl.setContentsMargins(20, 14, 20, 14)
        hl.setSpacing(12)
        hl.addWidget(title)
        hl.addWidget(sub)
        hl.addStretch()
        return bar

    def _build_form(self):
        area = QWidget()
        area.setObjectName('Form')
        area.setStyleSheet('QWidget#Form { background: #ffffff; }' + _FIELD)
        layout = QVBoxLayout(area)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(18)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText('e.g. Baby kale')
        self.name_edit.textChanged.connect(lambda _t: self._follow_name and self._search_timer.start())
        layout.addLayout(_labelled('Name', self.name_edit))

        layout.addWidget(_eyebrow('Category'))
        self.category = CategoryPills()
        layout.addWidget(self.category)

        self.photo = _PhotoDrop(self._on_photo_file)
        self.photo_name = QLabel('')
        self.photo_name.setStyleSheet(f'color: {_MUTED}; font-family: {_MONO}; font-size: 12px;')
        self.unit_edit = QLineEdit()
        self.unit_edit.setPlaceholderText('oz')
        self.weight_edit = QLineEdit()
        self.weight_edit.setValidator(QDoubleValidator(0.0, 1_000_000.0, 4))
        self.weight_edit.setAlignment(Qt.AlignRight)
        self.portion_edit = QLineEdit()
        self.portion_edit.setPlaceholderText('e.g. Tongs')
        attach_tool_picker(self.portion_edit)
        for e in (self.unit_edit, self.weight_edit):
            e.textChanged.connect(lambda _t: self._on_unit_changed())
        facts = QHBoxLayout()
        facts.setSpacing(12)
        facts.addLayout(_labelled('Unit', self.unit_edit, 110))
        facts.addLayout(_labelled('Weight per unit (g)', self.weight_edit, 130))
        facts.addLayout(_labelled('Portion tool', self.portion_edit, 160))
        facts.addStretch()
        photo_col = QVBoxLayout()
        photo_col.setSpacing(4)
        photo_col.addWidget(self.photo)
        photo_col.addWidget(self.photo_name)
        top = QHBoxLayout()
        top.setSpacing(16)
        top.addLayout(facts, stretch=1)
        top.addLayout(photo_col)
        layout.addLayout(top)

        # --- first price ---
        price = QFrame()
        price.setObjectName('Section')
        price.setStyleSheet(f'QFrame#Section {{ border: 1px solid {_BORDER}; border-radius: 8px; }}')
        pl = QVBoxLayout(price)
        pl.setContentsMargins(16, 14, 16, 14)
        pl.setSpacing(10)
        ptitle = QLabel('First price')
        ptitle.setStyleSheet(f'color: {_KALE}; font-size: 15px; font-weight: 600;')
        pl.addWidget(ptitle)
        self.supplier = QComboBox()
        self.supplier.addItem('No supplier', None)
        for s in db.get_suppliers():
            self.supplier.addItem(s['name'], s['id'])
        self.case_price = QLineEdit()
        self.case_price.setValidator(QDoubleValidator(0.0, 1_000_000.0, 4))
        self.case_price.setPlaceholderText('$')
        self.case_yields = QLineEdit()
        self.case_yields.setValidator(QDoubleValidator(0.0, 1_000_000.0, 4))
        self.case_yields_label = _eyebrow('Case yields')
        for e in (self.case_price, self.case_yields):
            e.textChanged.connect(lambda _t: self._update_unit_price())
        self.unit_price = QLabel('')
        self.unit_price.setStyleSheet(f'color: {_KALE}; font-weight: 600;')
        prow = QHBoxLayout()
        prow.setSpacing(12)
        prow.addLayout(_labelled('Supplier', self.supplier, 200))
        prow.addLayout(_labelled('Case price', self.case_price, 110))
        ycol = QVBoxLayout()
        ycol.setSpacing(4)
        ycol.addWidget(self.case_yields_label)
        self.case_yields.setFixedWidth(110)
        ycol.addWidget(self.case_yields)
        prow.addLayout(ycol)
        prow.addWidget(self.unit_price, alignment=Qt.AlignBottom)
        prow.addStretch()
        pl.addLayout(prow)
        hint = QLabel('Optional. Skip it and the ingredient shows up in Library health under "No price".')
        hint.setWordWrap(True)
        hint.setStyleSheet(f'color: {_MUTED}; font-size: 12px;')
        pl.addWidget(hint)
        layout.addWidget(price)

        # --- nutrition ---
        self.nutrition_title = QLabel('Nutrition per unit')
        self.nutrition_title.setStyleSheet(f'color: {_KALE}; font-size: 15px; font-weight: 600;')
        layout.addWidget(self.nutrition_title)
        self.nutrition = NutritionGrid()
        layout.addWidget(self.nutrition)
        self.statement = StatementBox()
        layout.addWidget(self.statement)
        self.usda_note = QLabel('')
        self.usda_note.setWordWrap(True)
        self.usda_note.setStyleSheet(f'color: {_MUTED}; font-size: 12px;')
        self.usda_note.hide()
        layout.addWidget(self.usda_note)

        layout.addWidget(_eyebrow('Contains allergens'))
        self.allergens = AllergenChecks()
        layout.addWidget(self.allergens)
        layout.addStretch()
        self._update_unit_price()
        return area

    def _build_footer(self):
        bar = QFrame()
        bar.setObjectName('Footer')
        bar.setStyleSheet(f'QFrame#Footer {{ background: {_BG}; border-top: 1px solid {_BORDER}; }}')
        self.toggle_usda = QPushButton('')
        self.toggle_usda.setFlat(True)
        self.toggle_usda.setStyleSheet(f'color: {_ROMAINE}; border: 0; padding: 0 4px;')
        self.toggle_usda.clicked.connect(self._toggle_usda)
        cancel = QPushButton('Cancel')
        cancel.setStyleSheet(_SECONDARY)
        cancel.clicked.connect(self.reject)
        another = QPushButton('Save and add another')
        another.setStyleSheet(_SECONDARY)
        another.clicked.connect(self._on_save_another)
        save = QPushButton('Save ingredient   Ctrl+S')
        save.setStyleSheet(
            f'QPushButton {{ min-height: 34px; padding: 0 16px; border: 0; border-radius: 8px;'
            f' background: {_ROMAINE}; color: #ffffff; font-weight: 600; }}'
            f' QPushButton:hover {{ background: {_ROMAINE_HOVER}; }}')
        save.clicked.connect(self._on_save)
        for b in (cancel, another, save, self.toggle_usda):
            b.setAutoDefault(False)
        hl = QHBoxLayout(bar)
        hl.setContentsMargins(20, 12, 20, 12)
        hl.setSpacing(8)
        hl.addWidget(self.toggle_usda)
        hl.addStretch()
        hl.addWidget(cancel)
        hl.addWidget(another)
        hl.addWidget(save)
        QTimer.singleShot(0, self._sync_toggle_label)
        return bar

    # --- behaviour -----------------------------------------------------

    def _toggle_usda(self):
        show = not self.usda.isVisible()
        self.usda.setVisible(show)
        if show and self.width() < 1000:
            self.resize(1100, self.height())
        if show and self.name_edit.text().strip() and not self.usda.results.count():
            self._search_from_name()
        self._sync_toggle_label()

    def _sync_toggle_label(self):
        self.toggle_usda.setText('Hide USDA panel' if self.usda.isVisible() else 'Look up in USDA…')

    def _search_from_name(self):
        name = self.name_edit.text().strip()
        if not name or not self.usda.isVisible():
            return
        self.usda.set_query(name)
        self.usda.search()

    def _on_unit_changed(self):
        unit = self.unit_edit.text().strip() or 'unit'
        self.nutrition_title.setText(f'Nutrition per {unit}')
        self.case_yields_label.setText(f'CASE YIELDS ({unit.upper()})')
        self._sync_target()
        self._update_unit_price()

    def _sync_target(self):
        self.usda.set_target(self.unit_edit.text(), self.weight_edit.text())

    def _update_unit_price(self):
        try:
            cp, cy = float(self.case_price.text()), float(self.case_yields.text())
        except ValueError:
            self.unit_price.setText('')
            return
        unit = self.unit_edit.text().strip() or 'unit'
        self.unit_price.setText(f'= ${cp / cy:.3f} per {unit}' if cy > 0 else '')

    def _apply_usda(self, values, grams, note):
        self.nutrition.set_values(values)
        try:
            current = float(self.weight_edit.text())
        except ValueError:
            current = 0.0
        if abs(current - grams) > 0.01:
            # Empty, or the user scaled to a different weight than the
            # form had: the form's weight follows, so the nutrition and
            # the weight per unit agree.
            if current > 0:
                note += ' Weight per unit updated to match.'
            self.weight_edit.setText(num_text(round(grams, 2)))
        self.usda_note.setText(note + ' Edit anything before saving.')
        self.usda_note.show()

    def _on_photo_file(self, path):
        folder = os.path.normcase(os.path.abspath(config.INGREDIENTS_PATH))
        if os.path.normcase(os.path.dirname(os.path.abspath(path))) != folder:
            target = os.path.join(config.INGREDIENTS_PATH, os.path.basename(path))
            if os.path.exists(target) and QMessageBox.question(
                self, 'Replace photo?',
                f'"{os.path.basename(path)}" is already in the photos folder. Replace it?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            ) != QMessageBox.Yes:
                return
            try:
                shutil.copy(path, target)
            except OSError as exc:
                QMessageBox.warning(self, 'Photo not copied', str(exc))
                return
        self._image = os.path.basename(path)
        self.photo_name.setText(self._image)
        load_thumbnail(self._image, 96, self.photo.show_image)

    # --- saving --------------------------------------------------------

    def _state(self):
        return (self.name_edit.text().strip(), self.unit_edit.text(), self.weight_edit.text(),
                self.portion_edit.text(), self.category.selected(), self._image,
                self.case_price.text(), self.case_yields.text(),
                tuple(sorted(self.nutrition.values().items())), tuple(self.allergens.checked_ids()),
                tuple(self.allergens.facility_ids()), self.statement.text())

    def _save(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, 'Name needed', 'An ingredient needs a name.')
            self.name_edit.setFocus()
            return False
        price = None
        if self.case_price.text().strip() or self.case_yields.text().strip():
            try:
                cp, cy = float(self.case_price.text()), float(self.case_yields.text())
            except ValueError:
                cp = cy = 0
            if cp <= 0 or cy <= 0:
                QMessageBox.warning(self, 'Price incomplete',
                                    'Enter both a case price and how many units a case yields, '
                                    'or leave both empty.')
                return False
            price = (cp, cy)
        values = {key: v for key, v in self.nutrition.values().items()}
        values.update({
            'Name': name, 'Unit': self.unit_edit.text().strip(), 'Portion': self.portion_edit.text().strip(),
            'Weight': self.weight_edit.text(), 'Cost': f'{price[0] / price[1]:.6f}' if price else '0',
            'ImageFilename': self._image or None,
        })
        new_id = db.create_ingredient(values)
        db.set_ingredient_tag(new_id, self.category.selected())
        db.set_ingredient_allergens(new_id, self.allergens.checked_ids(), self.allergens.facility_ids())
        db.set_ingredient_statement(new_id, self.statement.text())
        if price:
            db.ingredient_price_new(new_id, (self.supplier.currentData(), price[0], price[1],
                                             date.today().isoformat(), ''))
        self.new_id = new_id
        self.created_ids.append(new_id)
        self.status_message = f"Created '{name}'"
        return True

    def _on_save(self):
        if self._save():
            self._baseline = self._state()
            self.accept()

    def _on_save_another(self):
        if not self._save():
            return
        # Keep the supplier (a run of entries is often one invoice);
        # clear everything specific to the ingredient.
        for e in (self.name_edit, self.weight_edit, self.portion_edit, self.case_price, self.case_yields,
                  self.statement):
            e.clear()
        self.nutrition.set_values({k: '' for k in self.nutrition.values()})
        self.allergens.set_checked([])
        self.category.set_selected(None)
        self._image = ''
        self.photo.reset()
        self.photo_name.setText('')
        self.usda_note.hide()
        self._follow_name = True
        self._baseline = self._state()
        self.name_edit.setFocus()

    def reject(self):
        if self._state() != self._baseline and QMessageBox.question(
            self, 'Discard new ingredient?', 'Close without saving this ingredient?',
            QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Cancel,
        ) != QMessageBox.Discard:
            return
        super().reject()
