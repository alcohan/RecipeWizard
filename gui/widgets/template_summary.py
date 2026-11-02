'''One-line summary of a recipe's format template, with a Details
flyout listing the template's auto-add items and portion overrides.

Sits under the recipe editor's components grid:

    Bowl template · 3 items · $0.34 · 2 overrides · Details

Template items include packaging, which the grid and wedge don't list,
so this line is also where those items are named. With no format the
line falls back to the cost of any unlisted packaging, or hides.

Updated by the recipe editor's _refresh() — whenever the recipe's
format changes (via the selector or via undo/redo), refresh() re-reads
the template, recomputes the stats, and closes any open flyout so its
content can't drift behind the line.'''
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

import db


_KALE = '#082c00'
_ROMAINE = '#347200'
_MUTED = '#55624c'
_BORDER = '#ebe1cd'
_RULE = '#f3ece0'


class TemplateSummaryLine(QLabel):
    def __init__(self, recipe_id, parent=None):
        super().__init__(parent)
        self.recipe_id = recipe_id
        self._popup = None
        # Cache the items/multipliers from the last refresh so opening the
        # flyout doesn't have to round-trip to the DB.
        self._tag = None
        self._items = []
        self._mults = []
        self.setTextFormat(Qt.RichText)
        self.setWordWrap(True)
        self.setStyleSheet(f'color: {_MUTED}; font-size: 12px; padding: 6px 16px;')
        self.linkActivated.connect(lambda _h: self._toggle_popup())

    def refresh(self, unlisted_cost=0.0):
        '''Re-read the current format + its items. `unlisted_cost` is
        the recipe cost the grid doesn't show (packaging), used when
        there's no format to explain it.'''
        self._close_popup()
        tag = db.get_recipe_tag(self.recipe_id)
        self._tag = tag
        if not tag:
            self._items, self._mults = [], []
            if unlisted_cost >= 0.005:
                self.setText(f'Also in cost, not listed: packaging · ${unlisted_cost:.2f}')
                self.show()
            else:
                self.hide()
            return

        self._items = db.get_tag_components(tag['id'])
        self._mults = [m for m in db.get_tag_category_multipliers(tag['id'])
                       if abs(m['multiplier'] - 1.0) > 1e-9]
        total = sum(float(it.get('UnitCost') or 0) * float(it.get('quantity') or 0)
                    for it in self._items)
        color = _color(tag)
        parts = [f'<span style="color: {color}">■</span> <b style="color: {_KALE}">'
                 f'{_esc(tag["name"])}</b> template']
        n = len(self._items)
        parts.append(f"{n} item{'' if n == 1 else 's'}")
        if self._items:
            parts.append(f'${total:.2f}')
        if self._mults:
            m = len(self._mults)
            parts.append(f"{m} portion override{'' if m == 1 else 's'}")
        text = ' · '.join(parts)
        if self._items or self._mults:
            text += f' · <a href="details" style="color: {_ROMAINE}">Details</a>'
        self.setText(text)
        self.setToolTip('Items this format adds to every recipe, and how it scales'
                        ' portions. Edit in Configure › Formats & templates.')
        self.show()

    # --- flyout --------------------------------------------------------

    def _toggle_popup(self):
        if self._popup_is_visible():
            self._close_popup()
            return
        # Stale ref (popup was deleted by Qt.Popup auto-close earlier) —
        # drop it before creating a fresh popup.
        self._popup = _TemplateDetailsPopup(self._tag, self._items, self._mults, self)
        self._popup.destroyed.connect(self._on_popup_destroyed)
        # Open upward if there's no room below (the line sits at the
        # bottom of the components card).
        self._popup.adjustSize()
        below = self.mapToGlobal(QPoint(16, self.height()))
        screen = self.screen().availableGeometry() if self.screen() else None
        if screen is not None and below.y() + self._popup.height() > screen.bottom():
            below = self.mapToGlobal(QPoint(16, -self._popup.height()))
        self._popup.move(below)
        self._popup.show()

    def _popup_is_visible(self):
        '''True iff self._popup is alive and shown. Catches the
        RuntimeError raised when Qt.Popup + WA_DeleteOnClose has already
        deleted the C++ object behind the Python ref.'''
        if self._popup is None:
            return False
        try:
            return self._popup.isVisible()
        except RuntimeError:
            self._popup = None
            return False

    def _close_popup(self):
        if self._popup is None:
            return
        try:
            self._popup.close()
        except RuntimeError:
            pass
        self._popup = None

    def _on_popup_destroyed(self, *_):
        self._popup = None


class _TemplateDetailsPopup(QWidget):
    '''Flyout for the Details link. Qt.Popup dismisses it on
    click-outside, Escape, or focus loss; WA_DeleteOnClose drops the
    C++ object so the line's ref goes stale and is cleared via the
    destroyed signal.

    Content: "<format> adds" → a table of items (name, qty × unit,
    cost) → "Portion overrides" with any non-×1 category multipliers.'''

    POPUP_WIDTH = 360

    def __init__(self, tag, items, multipliers, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_DeleteOnClose)

        frame = QFrame(self)
        frame.setObjectName('TemplatePopup')
        frame.setStyleSheet(f'QFrame#TemplatePopup {{ background: #ffffff;'
                            f' border: 1px solid {_BORDER}; border-radius: 8px; }}'
                            f' QLabel {{ color: {_KALE}; }}')
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        layout.addWidget(QLabel(
            f'<span style="color: {_color(tag)}">■</span> <b>{_esc(tag["name"])}</b> adds'))

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)
        if not items:
            grid.addWidget(_muted('No items'), 0, 0)
        for r, it in enumerate(items):
            qty = _fmt_qty(it['quantity'])
            cost = float(it.get('UnitCost') or 0) * float(it.get('quantity') or 0)
            grid.addWidget(QLabel(_esc(it['Name'])), r, 0)
            grid.addWidget(_muted(f"× {qty} {_esc(it.get('Unit') or '')}".rstrip()), r, 1)
            price = QLabel(f'${cost:.2f}')
            price.setAlignment(Qt.AlignRight)
            grid.addWidget(price, r, 2)
        grid.setColumnStretch(0, 1)
        layout.addLayout(grid)

        if multipliers:
            rule = QFrame()
            rule.setFixedHeight(1)
            rule.setStyleSheet(f'background: {_RULE};')
            layout.addWidget(rule)
            layout.addWidget(QLabel('<b>Portion overrides</b>'))
            for m in multipliers:
                layout.addWidget(QLabel(
                    f'<span style="color: {m.get("category_color") or _MUTED}">●</span> '
                    f'{_esc(m["category_name"])} × {_fmt_qty(m["multiplier"])}'))

        layout.addWidget(_muted('Edit in Configure › Formats & templates.'))
        self.setFixedWidth(self.POPUP_WIDTH)


def _muted(text):
    lbl = QLabel(text)
    lbl.setStyleSheet(f'color: {_MUTED}; font-size: 12px;')
    return lbl


def _color(tag):
    color = QColor((tag or {}).get('color') or '#94a3b8')
    return color.name() if color.isValid() else '#94a3b8'


def _esc(text):
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _fmt_qty(value):
    if value is None:
        return ''
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f'{n:.4f}'.rstrip('0').rstrip('.')
