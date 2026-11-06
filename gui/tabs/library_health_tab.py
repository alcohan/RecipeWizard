'''Configure › Library health: what needs fixing in the library.

Only ingredients used in active recipes are checked, and each one's
category says whether it needs nutrition and a price (Configure ›
Ingredient categories), so Packaging never asks for calories.

  - Missing nutrition: one row per ingredient, with "0 is right" for
    the ones that really have no calories (spices, hot sauce).
  - Stale prices: one flag, however many prices, with a drilldown of
    each price, oldest first: New price…, or Still right to mark it
    checked without adding a price entry.
  - Duplicate names.

A Backups card lists the backups in the data folder. Built on first
show and again whenever the main window marks it stale.
'''
import os
from datetime import date, datetime

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget,
)

import config
import db
from gui.widgets import config_kit as kit
from utilities import backup

_CLEAR_BG = '#e9f1d9'
_CLEAR_BORDER = '#cfe0b1'


def _day(iso):
    if not iso:
        return ''
    try:
        d = date.fromisoformat(str(iso)[:10])
        return f'{d:%b} {d.day}, {d.year}'
    except ValueError:
        return str(iso)


def _esc(text):
    return (text or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _link(href, text, color=kit.ROMAINE):
    return f'<a href="{href}" style="color: {color}; text-decoration: none;">{_esc(text)}</a>'


def _rich(html, on_link, muted=False):
    lbl = QLabel(html)
    lbl.setTextFormat(Qt.RichText)
    lbl.setStyleSheet(f'color: {kit.MUTED if muted else kit.KALE}; background: transparent;')
    lbl.linkActivated.connect(on_link)
    return lbl


def _muted(text):
    lbl = QLabel(text)
    lbl.setStyleSheet(f'color: {kit.MUTED}; background: transparent;')
    return lbl


class LibraryHealthTab(QWidget):
    ingredientRequested = Signal(int)
    newPriceRequested = Signal(int)
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stale = True
        self._show_prices = False
        self._show_confirmed = False
        self.report = None
        self._container = QWidget()
        self._container.setObjectName('HealthPage')
        self._container.setStyleSheet(f'QWidget#HealthPage {{ background: {kit.BG}; }}')
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(28, 20, 28, 28)
        self._layout.setSpacing(16)

        scroll = QScrollArea()
        scroll.setWidget(self._container)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f'QScrollArea {{ background: {kit.BG}; border: 0; }}')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

    def showEvent(self, event):
        super().showEvent(event)
        if self._stale:
            self.refresh()
            self._stale = False

    def mark_stale(self):
        '''Called by the main window when the library changes; only
        re-reads while visible.'''
        self._stale = True
        if self.isVisible():
            self.refresh()
            self._stale = False

    # --- building ---

    def refresh(self):
        while self._layout.count():
            w = self._layout.takeAt(0).widget()
            if w is not None:
                w.hide()          # deleteLater alone leaves it painted until the next loop
                w.deleteLater()
        self._layout.addWidget(kit.heading('Library health'))
        self._layout.addWidget(kit.note('Ingredients in active recipes'))
        try:
            self.report = db.library_health()
        except Exception as exc:
            err = QLabel(f'Could not read the library: {exc}')
            err.setStyleSheet(f'color: {kit.WARN}; background: #fbeadb; padding: 8px 12px; border-radius: 8px;')
            self._layout.addWidget(err)
            self._layout.addStretch()
            return
        r = self.report
        cards = [
            (len(r['nutrition']), self._nutrition_card),
            (1 if r['prices'] else 0, self._prices_card),
            (len(r['duplicates']), self._duplicates_card),
        ]
        # Cards with something to fix first, then the all-clear ones.
        for _n, build in sorted(cards, key=lambda c: c[0] == 0):
            self._layout.addWidget(build())
        self._layout.addWidget(_BackupsCard())
        self._layout.addStretch()

    def _card(self, title, count, clear_text):
        '''A card with a title and a count badge, or a muted all-clear
        card. Returns (frame, layout).'''
        frame, layout = kit.card()
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(kit.subheading(title))
        if count:
            badge = QLabel(str(count))
            badge.setStyleSheet('background: #fbeadb; color: #8a3f0c; font-weight: 700;'
                                ' padding: 1px 9px; border-radius: 9px;')
            head.addWidget(badge)
        else:
            frame.setStyleSheet(f'QFrame#ConfigCard {{ background: {_CLEAR_BG}; border: 1px solid {_CLEAR_BORDER};'
                                ' border-radius: 8px; }')
            check = QLabel('✓')
            check.setStyleSheet(f'background: {_CLEAR_BORDER}; color: #24502a; font-weight: 700;'
                                ' padding: 1px 9px; border-radius: 9px;')
            head.addWidget(check)
        head.addStretch()
        layout.addLayout(head)
        if not count:
            layout.addWidget(_muted(clear_text))
        return frame, layout

    @staticmethod
    def _grid():
        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(6)
        return grid

    def _name(self, r):
        return _rich(_link(f'edit:{r["Id"]}', r['Name'], kit.KALE), self._on_link)

    def _nutrition_card(self):
        rows, confirmed = self.report['nutrition'], self.report['confirmed']
        frame, layout = self._card('Missing nutrition', len(rows), 'Every ingredient has calories')
        if rows:
            grid = self._grid()
            for i, r in enumerate(rows):
                grid.addWidget(self._name(r), i, 0)
                grid.addWidget(_muted(r['Category'] or ''), i, 1)
                grid.addWidget(_rich(_link(f'zero:{r["Id"]}', '0 is right'), self._on_link), i, 2)
            grid.setColumnStretch(3, 1)
            layout.addLayout(grid)
        if confirmed:
            toggle = 'Hide' if self._show_confirmed else 'Show'
            layout.addWidget(_rich(f'{len(confirmed)} marked as 0 calories &nbsp;' + _link('toggle-confirmed', toggle),
                                   self._on_link, muted=True))
            if self._show_confirmed:
                grid = self._grid()
                for i, r in enumerate(confirmed):
                    grid.addWidget(self._name(r), i, 0)
                    grid.addWidget(_muted(r['Category'] or ''), i, 1)
                    grid.addWidget(_rich(_link(f'unzero:{r["Id"]}', 'Undo'), self._on_link), i, 2)
                grid.setColumnStretch(3, 1)
                layout.addLayout(grid)
        return frame

    def _prices_card(self):
        rows, days = self.report['prices'], self.report['stale_days']
        frame, layout = self._card('Stale prices', len(rows), f'Every price is from the last {days} days')
        if not rows:
            return frame
        dated = [r['last_price'] for r in rows if r['last_price']]
        bits = [f"{len(rows)} price{'s' if len(rows) != 1 else ''} over {days} days old"]
        if dated:
            bits.append(f'oldest {_day(min(dated))}')
        toggle = 'Hide' if self._show_prices else 'Review'
        layout.addWidget(_rich(' · '.join(bits) + ' &nbsp;' + _link('toggle-prices', toggle), self._on_link))
        if self._show_prices:
            grid = self._grid()
            for i, r in enumerate(rows):
                grid.addWidget(self._name(r), i, 0)
                grid.addWidget(_muted(r['Category'] or ''), i, 1)
                price = (f"${float(r['unit_price']):.3f} / {r['Unit'] or 'unit'}"
                         if r['unit_price'] is not None else 'No price')
                grid.addWidget(_muted(price), i, 2)
                when = _day(r['last_price'])
                if r['checked'] and r['checked'] > (r['last_price'] or ''):
                    when = f"Checked {_day(r['checked'])}"
                grid.addWidget(_muted(when), i, 3)
                grid.addWidget(_muted(r['supplier'] or ''), i, 4)
                actions = _link(f'price:{r["Id"]}', 'New price…')
                if r['last_price']:
                    actions += ' &nbsp;·&nbsp; ' + _link(f'checked:{r["Id"]}', 'Still right')
                grid.addWidget(_rich(actions, self._on_link), i, 5)
            grid.setColumnStretch(6, 1)
            layout.addLayout(grid)
        return frame

    def _duplicates_card(self):
        names = self.report['duplicates']
        frame, layout = self._card('Duplicate names', len(names), 'No two ingredients share a name')
        if names:
            body = QLabel(', '.join(names))
            body.setWordWrap(True)
            body.setStyleSheet(f'color: {kit.KALE}; background: transparent;')
            layout.addWidget(body)
            layout.addWidget(kit.note('Rename or merge them'))
        return frame

    # --- actions ---

    def _on_link(self, href):
        action, _, arg = href.partition(':')
        if action == 'edit':
            self.ingredientRequested.emit(int(arg))
            return
        if action == 'price':
            self.newPriceRequested.emit(int(arg))
            return
        if action == 'toggle-prices':
            self._show_prices = not self._show_prices
        elif action == 'toggle-confirmed':
            self._show_confirmed = not self._show_confirmed
        elif action in ('zero', 'unzero'):
            db.set_nutrition_confirmed(int(arg), action == 'zero')
            self.changed.emit()
        elif action == 'checked':
            db.mark_price_checked(int(arg))
            self.changed.emit()
        self.refresh()


class _BackupsCard(QFrame):
    '''Lists backups in the user's data folder (.rwbackup files, and
    older *backup*.db copies), newest first, with Open folder.'''

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('HealthCard')
        self.setStyleSheet(f'''
            QFrame#HealthCard {{ background: #ffffff; border: 1px solid {kit.BORDER}; border-radius: 8px; }}
            QFrame#HealthCard QLabel {{ background: transparent; border: 0; }}
        ''')
        files = _list_backups()
        count_label = QLabel(str(len(files)))
        count_label.setStyleSheet(f'background: {kit.SELECTED}; color: {kit.MUTED};'
                                  ' font-weight: 700; padding: 1px 9px; border-radius: 9px;')
        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        header_row.addWidget(kit.subheading('Backups'))
        header_row.addWidget(count_label)
        header_row.addStretch()
        open_btn = kit.button('Open folder')
        open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(config.user_data_dir())))
        header_row.addWidget(open_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(6)
        layout.addLayout(header_row)
        if not files:
            layout.addWidget(_muted('No backups yet'))
            return
        for name, when in files[:5]:
            line = QLabel(f'<b>{_esc(name)}</b> &nbsp; <span style="color:{kit.MUTED}">{when}</span>')
            line.setTextFormat(Qt.RichText)
            line.setStyleSheet(f'color: {kit.KALE};')
            layout.addWidget(line)
        if len(files) > 5:
            layout.addWidget(_muted(f'and {len(files) - 5} more'))


def _list_backups():
    '''Return [(filename, when-string)], newest first.'''
    return [(os.path.basename(path), datetime.fromtimestamp(mtime).strftime('%b %d, %Y %H:%M'))
            for path, mtime in backup.list_backups()]
