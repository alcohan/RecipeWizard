'''Native FDA-style Nutrition Facts label rendered with QPainter.

Replaces the old Chrome shell-out (utils.open_nutrition_label). Produces a
single QPixmap that can be copied to the clipboard or saved as a PNG/JPG.
The label uses the FDA Nutrition Facts visual conventions: heavy black
ruled lines separating sections, big bold "Nutrition Facts" header, large
Calories row, indented sub-nutrients. There is no %DV column because the
underlying data doesn't include daily-value targets.'''
import os
import re

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QFontMetrics, QGuiApplication, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)

import config
import db


LABEL_WIDTH = 400
PADDING = 16
GAP = 4
LINE_W = {'thick': 8, 'med': 4, 'thin': 1}

NUTRIENT_ROWS = (
    # (display name, recipe key, unit suffix, top-level?)
    ('Total Fat', 'TTLFatGrams', 'g', True),
    ('Saturated Fat', 'SatFatGrams', 'g', False),
    ('Cholesterol', 'CholesterolMilligrams', 'mg', True),
    ('Sodium', 'SodiumMilligrams', 'mg', True),
    ('Total Carbohydrate', 'CarbGrams', 'g', True),
    ('Dietary Fiber', 'FiberGrams', 'g', False),
    ('Total Sugars', 'SugarGrams', 'g', False),
    ('Protein', 'ProteinGrams', 'g', True),
)


class NutritionLabelDialog(QDialog):
    def __init__(self, recipe_id, parent=None):
        super().__init__(parent)
        recipe = db.recipe_info(recipe_id)
        self._recipe_name = recipe['Name']
        ingredients = db.recipe_components(recipe_id)
        ingredients_str = ', '.join(i['Name'] for i in ingredients) or '—'

        self.setWindowTitle(f'{config.APPNAME} | Nutrition Label | {self._recipe_name}')

        self.pixmap = render_nutrition_label(recipe, ingredients_str)

        image_label = QLabel()
        image_label.setPixmap(self.pixmap)
        image_label.setAlignment(Qt.AlignCenter)
        image_label.setStyleSheet('background-color: #eee; padding: 12px;')

        copy_btn = QPushButton('Copy to Clipboard')
        copy_btn.clicked.connect(self._on_copy)
        save_btn = QPushButton('Save as Image…')
        save_btn.clicked.connect(self._on_save)
        close_btn = QPushButton('Close')
        close_btn.clicked.connect(self.reject)

        self.status_label = QLabel('')
        self.status_label.setStyleSheet('color: #2a7;')

        btn_row = QHBoxLayout()
        btn_row.addWidget(copy_btn)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(self.status_label)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(image_label, alignment=Qt.AlignCenter)
        layout.addLayout(btn_row)

        self.resize(self.pixmap.width() + 80, self.pixmap.height() + 100)

    def _on_copy(self):
        QGuiApplication.clipboard().setPixmap(self.pixmap)
        self._flash_status('✓ Copied to clipboard')

    def _on_save(self):
        default_name = _slugify(self._recipe_name) + '_nutrition.png'
        path, _selected = QFileDialog.getSaveFileName(
            self, 'Save Nutrition Label', default_name,
            'PNG Image (*.png);;JPEG Image (*.jpg *.jpeg)',
        )
        if not path:
            return
        if not path.lower().endswith(('.png', '.jpg', '.jpeg')):
            path += '.png'
        if self.pixmap.save(path):
            self._flash_status(f'✓ Saved {os.path.basename(path)}')
        else:
            self._flash_status('Save failed', success=False)

    def _flash_status(self, text, success=True):
        self.status_label.setStyleSheet('color: #2a7;' if success else 'color: #c0392b;')
        self.status_label.setText(text)
        QTimer.singleShot(2500, lambda: self.status_label.setText(''))


# --- renderer ----------------------------------------------------------------

def render_nutrition_label(recipe, ingredients_str, width=LABEL_WIDTH):
    '''Return a QPixmap of the Nutrition Facts panel for `recipe`.

    `recipe` is the dict returned by db.recipe_info(id) (Cost may be a
    pre-formatted "$ X.XX" string; we don't display Cost on the label).
    `ingredients_str` is the comma-joined direct-component names; nested
    sub-recipes are NOT expanded — that matches the old Chrome label.'''
    # Oversized canvas; we crop to the actual drawn height at the end.
    canvas = QPixmap(width, 3000)
    canvas.fill(Qt.white)
    p = QPainter(canvas)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)

    state = {'y': PADDING}
    inner_w = width - 2 * PADDING

    def draw_text(font, text_left, text_right=None, indent=0):
        p.setFont(font)
        fm = QFontMetrics(font)
        y = state['y']
        p.drawText(PADDING + indent, y + fm.ascent(), text_left)
        if text_right is not None:
            tw = fm.horizontalAdvance(text_right)
            p.drawText(width - PADDING - tw, y + fm.ascent(), text_right)
        state['y'] = y + fm.height()

    def rule(thickness):
        w = LINE_W[thickness]
        pen = QPen(Qt.black)
        pen.setWidth(w)
        p.setPen(pen)
        line_y = state['y'] + w // 2
        p.drawLine(PADDING, line_y, width - PADDING, line_y)
        state['y'] += w + GAP

    def gap(px=GAP):
        state['y'] += px

    name_font = QFont('Arial', 20); name_font.setBold(True)
    title_font = QFont('Arial', 24); title_font.setWeight(QFont.Black)
    serving_font = QFont('Arial', 11)
    bold_font = QFont('Arial', 11); bold_font.setBold(True)
    cal_font = QFont('Arial', 22); cal_font.setWeight(QFont.Black)
    row_font = QFont('Arial', 11)
    row_bold = QFont('Arial', 11); row_bold.setBold(True)
    small_bold = QFont('Arial', 10); small_bold.setBold(True)
    small_font = QFont('Arial', 10)

    recipe_name = recipe.get('Name') or ''
    if recipe_name:
        p.setFont(name_font)
        fm = QFontMetrics(name_font)
        name_rect = fm.boundingRect(
            PADDING, state['y'], inner_w, 200,
            Qt.TextWordWrap | Qt.AlignHCenter, recipe_name,
        )
        p.drawText(
            PADDING, state['y'], inner_w, name_rect.height(),
            Qt.TextWordWrap | Qt.AlignHCenter, recipe_name,
        )
        state['y'] += name_rect.height() + GAP

    draw_text(title_font, 'Nutrition Facts')
    rule('thick')

    serving = f"Serving Size: {_format_num(recipe.get('OutputQty'))} {recipe.get('Unit', '')}".strip()
    draw_text(serving_font, serving)
    rule('thick')

    draw_text(bold_font, 'Amount Per Serving')
    gap(2)
    draw_text(cal_font, 'Calories', str(_format_int(recipe.get('Calories'))))
    rule('med')

    for name, key, unit, top_level in NUTRIENT_ROWS:
        font = row_bold if top_level else row_font
        indent = 0 if top_level else 14
        value_str = f'{_format_num(recipe.get(key))} {unit}'
        draw_text(font, name, value_str, indent=indent)
        rule('thin')

    gap(2)
    rule('thick')
    gap(2)
    draw_text(small_bold, 'Ingredients:')

    p.setFont(small_font)
    fm = QFontMetrics(small_font)
    ingredients_rect = fm.boundingRect(
        PADDING, state['y'], inner_w, 3000 - state['y'],
        Qt.TextWordWrap, ingredients_str,
    )
    p.drawText(
        PADDING, state['y'], inner_w, ingredients_rect.height() + fm.descent(),
        Qt.TextWordWrap, ingredients_str,
    )
    state['y'] += ingredients_rect.height() + PADDING

    p.end()

    return canvas.copy(0, 0, width, min(state['y'], canvas.height()))


def _format_num(value):
    try:
        n = float(value)
    except (TypeError, ValueError):
        return '0'
    if n == int(n):
        return str(int(n))
    return f'{n:.1f}'


def _format_int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _slugify(name):
    return re.sub(r'[^a-z0-9]+', '_', (name or 'recipe').lower()).strip('_') or 'recipe'
