'''New recipe dialog, per the Framework canvas: name, a format card per
recipe format (its silhouette) plus "None · sub-recipe", a line saying
what that format's template adds, yield and unit, an optional menu
price, and where to start from — the template's items only, or a copy
of another recipe's components (switched to the chosen format the way
the editor switches formats).

"Create and open" (Ctrl+S or Enter) creates it; the caller opens it in
a tab beside Library. The last format picked is remembered, and the
unit follows the format ("bowl" for Bowl) until you type your own.
'''
from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtGui import QDoubleValidator, QImage, QKeySequence, QPainter, QPen, QPixmap, QColor, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QRadioButton, QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

import db
from gui.widgets.toolbar_controls import ToolbarCombo
from utilities import portions
from utilities.wedge_renderer import render_recipe


_KALE = '#082c00'
_ROMAINE = '#347200'
_ROMAINE_HOVER = '#285900'
_MUTED = '#55624c'
_BORDER = '#ebe1cd'
_FIELD_BORDER = '#7d8771'
_BG = '#fffaf2'
_WARN = '#8a4a00'
_MONO = "ui-monospace, 'Cascadia Mono', Consolas, monospace"
_ICON = 56
_FORMAT_KEY = 'newRecipe/format'
_NONE = 0        # the "None · sub-recipe" card's key (format tag ids are > 0)


def _eyebrow(text):
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(f'color: {_MUTED}; font-size: 11px; font-weight: 600; letter-spacing: 1px;')
    return lbl


def _field(width=None):
    edit = QLineEdit()
    edit.setStyleSheet(f'QLineEdit {{ min-height: 32px; padding: 0 10px; border: 1px solid {_FIELD_BORDER};'
                       f' border-radius: 4px; background: #ffffff; color: {_KALE}; }}'
                       f' QLineEdit:focus {{ border: 2px solid {_ROMAINE}; padding: 0 9px; }}')
    if width:
        edit.setFixedWidth(width)
    return edit


def _silhouette(shape, color):
    png = render_recipe([], size=_ICON, shape=shape, shape_color=color)
    image = QImage()
    if png and image.loadFromData(png) and not image.isNull():
        return QPixmap.fromImage(image)
    return _dashed_circle()


def _dashed_circle():
    pix = QPixmap(_ICON, _ICON)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(_FIELD_BORDER), 1.2)
    pen.setDashPattern([4, 4])
    p.setPen(pen)
    p.drawEllipse(5, 5, _ICON - 10, _ICON - 10)
    p.end()
    return pix


def _money(value):
    return f'${float(value or 0):.2f}'


class _FormatCard(QToolButton):
    def __init__(self, key, name, pixmap, dashed=False, parent=None):
        super().__init__(parent)
        self.key = key
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setText(name)
        self.setIcon(pixmap)
        self.setIconSize(QSize(_ICON, _ICON))
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.setMinimumSize(96, 96)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        border = 'dashed' if dashed else 'solid'
        self.setStyleSheet(f'''
            QToolButton {{ border: 1px {border} {_FIELD_BORDER if dashed else _BORDER}; border-radius: 8px;
                background: #ffffff; color: {_MUTED if dashed else _KALE}; padding: 8px 4px; }}
            QToolButton:hover {{ border-color: {_FIELD_BORDER}; }}
            QToolButton:checked {{ border: 2px solid {_ROMAINE}; background: #fff1da; color: {_KALE};
                font-weight: 600; padding: 7px 3px; }}
        ''')


class RecipeCreateDialog(QDialog):
    '''After exec() == Accepted, `new_id` is the new recipe.
    `edit_templates` (optional) opens Formats & templates; the dialog
    re-reads formats when it returns.'''


    def __init__(self, parent=None, edit_templates=None):
        super().__init__(parent)
        self.setWindowTitle('New recipe')
        self.setModal(True)
        self.resize(720, 640)
        self.new_id = 0
        self.status_message = ''
        self._edit_templates = edit_templates
        self._unit_touched = False
        self.setObjectName('NewRecipe')
        self.setStyleSheet(f'QDialog#NewRecipe {{ background: #ffffff; }} QLabel {{ color: {_KALE}; }}'
                           f' QRadioButton {{ color: {_KALE}; spacing: 8px; }}')

        # header
        head = QHBoxLayout()
        head.setContentsMargins(20, 16, 20, 16)
        head.setSpacing(12)
        title = QLabel('New recipe')
        title.setStyleSheet(f'color: {_KALE}; font-size: 20px; font-weight: 650;')
        head.addWidget(title)
        head.addStretch()
        head_wrap = QFrame()
        head_wrap.setObjectName('NRHead')
        head_wrap.setStyleSheet(f'QFrame#NRHead {{ border-bottom: 1px solid {_BORDER}; }}')
        head_wrap.setLayout(head)

        # name
        self.name_edit = _field()
        self.name_edit.setStyleSheet(self.name_edit.styleSheet() + ' QLineEdit { font-size: 16px; min-height: 36px; }')
        self.name_edit.setPlaceholderText('e.g. Autumn Grain Bowl')
        self.name_edit.textChanged.connect(self._validate)
        self.name_note = QLabel('')
        self.name_note.setStyleSheet(f'color: {_WARN}; font-size: 12px;')
        self.name_note.hide()
        self._names = {r['Name'].strip().lower() for r in db.recipe_info()}

        # formats
        self._cards = QButtonGroup(self)
        self._cards.setExclusive(True)
        self._cards.idToggled.connect(lambda _i, on: on and self._on_format())
        self._card_grid = QGridLayout()
        self._card_grid.setSpacing(8)
        self.template_note = QLabel('')
        self.template_note.setWordWrap(True)
        self.template_note.setTextFormat(Qt.RichText)
        self.template_note.setStyleSheet(f'background: {_BG}; border: 1px solid {_BORDER}; border-radius: 8px;'
                                         ' padding: 10px 12px; font-size: 13px;')
        self.template_note.linkActivated.connect(self._on_edit_templates)

        # yield, unit, menu price
        self.yield_edit = _field(80)
        self.yield_edit.setAlignment(Qt.AlignRight)
        self.yield_edit.setValidator(QDoubleValidator(0.0, 1_000_000.0, 4))
        self.yield_edit.setText('1')
        self.yield_edit.textChanged.connect(self._validate)
        self.unit_edit = _field(130)
        self.unit_edit.textEdited.connect(self._on_unit_edited)
        self.price_edit = _field(150)
        self.price_edit.setPlaceholderText('Not on menu')
        self.price_edit.textChanged.connect(self._validate)
        sizes = QHBoxLayout()
        sizes.setSpacing(16)
        for label, edit in (('Yields', self.yield_edit), ('Unit', self.unit_edit),
                            ('Menu price · optional', self.price_edit)):
            col = QVBoxLayout()
            col.setSpacing(4)
            col.addWidget(_eyebrow(label))
            col.addWidget(edit)
            sizes.addLayout(col)
        sizes.addStretch()

        # start from
        self.start_template = QRadioButton('Template items only')
        self.start_copy = QRadioButton('Copy components from')
        self.start_template.setChecked(True)
        self.copy_combo = ToolbarCombo()
        self.copy_combo.setMinimumWidth(240)
        for r in sorted(db.recipe_info(), key=lambda r: r['Name'].lower()):
            if r.get('Status') != 'archived':
                self.copy_combo.addItem(r['Name'], r['Id'])
        self.copy_combo.setEnabled(False)
        self.copy_combo.activated.connect(lambda _i: self.start_copy.setChecked(True))
        self.start_copy.toggled.connect(self.copy_combo.setEnabled)
        self.start_copy.setEnabled(self.copy_combo.count() > 0)
        copy_row = QHBoxLayout()
        copy_row.setSpacing(8)
        copy_row.addWidget(self.start_copy)
        copy_row.addWidget(self.copy_combo)
        copy_row.addStretch()

        body = QVBoxLayout()
        body.setContentsMargins(20, 20, 20, 20)
        body.setSpacing(20)
        name_col = QVBoxLayout()
        name_col.setSpacing(4)
        name_col.addWidget(_eyebrow('Name'))
        name_col.addWidget(self.name_edit)
        name_col.addWidget(self.name_note)
        body.addLayout(name_col)
        fmt_col = QVBoxLayout()
        fmt_col.setSpacing(8)
        fmt_col.addWidget(_eyebrow('Format'))
        fmt_col.addLayout(self._card_grid)
        fmt_col.addWidget(self.template_note)
        body.addLayout(fmt_col)
        body.addLayout(sizes)
        start_col = QVBoxLayout()
        start_col.setSpacing(8)
        start_col.addWidget(_eyebrow('Start from'))
        start_col.addWidget(self.start_template)
        start_col.addLayout(copy_row)
        body.addLayout(start_col)
        body.addStretch()

        # footer
        cancel = QPushButton('Cancel')
        cancel.setAutoDefault(False)
        cancel.setStyleSheet(f'QPushButton {{ min-height: 34px; padding: 0 14px; border: 1px solid {_FIELD_BORDER};'
                             f' border-radius: 8px; background: #ffffff; color: {_KALE}; }}'
                             ' QPushButton:hover { background: #f3ece0; }')
        cancel.clicked.connect(self.reject)
        self.create_btn = QPushButton('Create and open   Ctrl+S')
        self.create_btn.setDefault(True)
        self.create_btn.setStyleSheet(
            f'QPushButton {{ min-height: 34px; padding: 0 16px; border: 0; border-radius: 8px;'
            f' background: {_ROMAINE}; color: #ffffff; font-weight: 600; }}'
            f' QPushButton:hover {{ background: {_ROMAINE_HOVER}; }}'
            ' QPushButton:disabled { background: #c9c2b2; }')
        self.create_btn.clicked.connect(self._on_create)
        QShortcut(QKeySequence.Save, self, activated=self._on_create)
        foot = QHBoxLayout()
        foot.setContentsMargins(20, 14, 20, 14)
        foot.setSpacing(8)
        foot.addStretch()
        foot.addWidget(cancel)
        foot.addWidget(self.create_btn)
        foot_wrap = QFrame()
        foot_wrap.setObjectName('NRFoot')
        foot_wrap.setStyleSheet(f'QFrame#NRFoot {{ background: {_BG}; border-top: 1px solid {_BORDER}; }}')
        foot_wrap.setLayout(foot)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(head_wrap)
        body_wrap = QWidget()
        body_wrap.setLayout(body)
        layout.addWidget(body_wrap, stretch=1)
        layout.addWidget(foot_wrap)

        self._build_cards(QSettings().value(_FORMAT_KEY, None))
        self._validate()
        self.name_edit.setFocus()

    # --- formats -------------------------------------------------------

    def _build_cards(self, select=None):
        for card in self._cards.buttons():
            self._cards.removeButton(card)
            card.deleteLater()
        self._formats = {t['id']: t for t in db.get_tags('recipe')}
        cards = [_FormatCard(tid, t['name'], _silhouette(t.get('shape'), t.get('color')))
                 for tid, t in self._formats.items()]
        cards.append(_FormatCard(_NONE, 'None · sub-recipe', _dashed_circle(), dashed=True))
        cards[-1].setToolTip('For sub-recipes like dressings')
        cols = 5
        for c in range(cols):
            self._card_grid.setColumnStretch(c, 1)
        for i, card in enumerate(cards):
            self._cards.addButton(card, card.key)
            self._card_grid.addWidget(card, i // cols, i % cols)
        try:
            select = int(select) if select is not None else None
        except (TypeError, ValueError):
            select = None
        if select not in self._formats and select != _NONE:
            select = next(iter(self._formats), _NONE)
        self._cards.button(select).setChecked(True)
        self._on_format()

    def format_tag_id(self):
        key = self._cards.checkedId()
        return key if key in self._formats else None

    def _on_format(self):
        tag = self._formats.get(self._cards.checkedId())
        if not self._unit_touched:
            self.unit_edit.setText(tag['name'].lower() if tag else 'batch')
        self.start_template.setText('Template items only' if tag else 'Empty')
        if tag is None:
            self.template_note.setText('Starts empty')
            return
        items = db.get_tag_components(tag['id'])
        rules = db.get_portion_rules(tag['id'])
        name = f'<b>{_esc(tag["name"])} template</b>'
        if items:
            total = sum(float(it.get('UnitCost') or 0) * float(it.get('quantity') or 0) for it in items)
            n = len(items)
            text = (f'{name} adds {n} item{"s" if n != 1 else ""}: '
                    f'{", ".join(_esc(it["Name"]) for it in items)} ({_money(total)}).')
        else:
            text = f'{name} adds no items.'
        if rules:
            text += ' ' + ' '.join(_esc(portions.describe_rule(r['category_name'], r['mode'], r['amount'],
                                                               r['measure'])) for r in rules)
        if self._edit_templates is not None:
            text += f' <a href="edit" style="color: {_ROMAINE}">Edit template</a>'
        self.template_note.setText(text)

    def _on_edit_templates(self, _href):
        if self._edit_templates is None:
            return
        keep = self._cards.checkedId()
        self._edit_templates()
        self._build_cards(keep)

    def _on_unit_edited(self, text):
        self._unit_touched = bool(text.strip())

    # --- create --------------------------------------------------------

    def _parsed(self):
        '''(name, yield, menu price) or None where invalid, plus a
        problem message for the button tooltip.'''
        name = self.name_edit.text().strip()
        try:
            qty = float(self.yield_edit.text())
        except ValueError:
            qty = 0
        text = self.price_edit.text().strip().lstrip('$').strip()
        try:
            price = float(text) if text else None
        except ValueError:
            price = 'bad'
        problem = ('Name the recipe' if not name else
                   'Yield must be more than 0' if qty <= 0 else
                   'Menu price must be a number, like 12.95' if price == 'bad' else '')
        return name, qty, price, problem

    def _validate(self, *_args):
        name, _qty, _price, problem = self._parsed()
        dup = name.lower() in self._names
        self.name_note.setText(f'A recipe called “{name}” already exists' if dup else '')
        self.name_note.setVisible(dup)
        self.create_btn.setEnabled(not problem)
        self.create_btn.setToolTip(problem)

    def _on_create(self):
        name, qty, price, problem = self._parsed()
        if problem:
            return
        fmt = self.format_tag_id()
        copy_from = self.copy_combo.currentData() if self.start_copy.isChecked() else None
        self.new_id = db.create_recipe_with(name, self.unit_edit.text().strip(), qty, menu_price=price,
                                            format_tag_id=fmt, copy_from=copy_from)
        QSettings().setValue(_FORMAT_KEY, fmt if fmt is not None else _NONE)
        self.status_message = f"Created '{name}'"
        self.accept()


def _esc(text):
    return (str(text or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))
