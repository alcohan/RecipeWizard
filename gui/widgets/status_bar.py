'''RecipeWizard's custom status bar.

Replaces Qt's default status bar with a fixed-content strip at the
bottom of the main window: library counts, latest supplier-price
date, last backup, and a compare-tray link on the right.

Each section is a QLabel so the main window can bump its text without
rebuilding anything. refresh() recomputes all three from the DB.
'''
import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy

import config
import db


class RecipeWizardStatusBar(QFrame):
    '''Thin band pinned at the bottom of the main window. Content is
    read-only; the right-side "Compare tray" entry is a signal-emitting
    link so the main window can route the click to its place switcher.'''

    compareTrayClicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('RecipeWizardStatusBar')
        self.setStyleSheet('''
            QFrame#RecipeWizardStatusBar {
                background: #fffaf2;
                border-top: 1px solid #ebe1cd;
            }
            QFrame#RecipeWizardStatusBar QLabel {
                color: #55624c;
                font-size: 12px;
            }
            QFrame#RecipeWizardStatusBar QLabel[role="link"] {
                color: #ffffff;
                background: #347200;
                padding: 2px 10px;
                border-radius: 4px;
                font-weight: 600;
            }
        ''')
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        self._counts_label = QLabel('')
        self._prices_label = QLabel('')
        self._backup_label = QLabel('')
        self._tray_label = QLabel('')
        self._tray_label.setProperty('role', 'link')
        self._tray_label.setCursor(Qt.PointingHandCursor)
        self._tray_label.mousePressEvent = self._on_tray_click
        self._tray_label.hide()  # Shown by set_compare_tray_count when there's one

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 6, 16, 6)
        layout.setSpacing(18)
        layout.addWidget(self._counts_label)
        layout.addWidget(self._prices_label)
        layout.addWidget(self._backup_label)
        layout.addStretch()
        layout.addWidget(self._tray_label)

    def refresh(self):
        '''Rebuild all three left-side sections. Called by the main
        window after any model reset.'''
        try:
            ing_n = db.query('SELECT COUNT(*) AS n FROM Ingredients', one=True)['n']
            rec_n = db.query('SELECT COUNT(*) AS n FROM Recipes', one=True)['n']
        except Exception:
            ing_n = rec_n = 0
        self._counts_label.setText(f'{rec_n} recipes · {ing_n} ingredients')

        prices_as_of = _latest_price_date()
        if prices_as_of:
            # Green dot (●) when the data looks fresh (<30 days old) and
            # amber otherwise. For now treat anything we have as fresh
            # — a staleness threshold can come later.
            dot = '●'
            self._prices_label.setText(
                f'<span style="color: #3E7D3A">{dot}</span> '
                f'Supplier prices as of {prices_as_of}'
            )
            self._prices_label.setTextFormat(Qt.RichText)
        else:
            self._prices_label.setText('No supplier prices yet')

        last_backup = _last_backup_label()
        self._backup_label.setText(last_backup)

    def set_compare_tray_count(self, n):
        '''Called by the compare-tray service when membership changes.
        Hides the label at zero so an idle status bar is clean.'''
        if n <= 0:
            self._tray_label.hide()
        else:
            self._tray_label.setText(f'Compare tray · {n} →')
            self._tray_label.show()

    def _on_tray_click(self, _event):
        self.compareTrayClicked.emit()


def _latest_price_date():
    '''Return a human-readable date string ("Oct 14") for the most
    recent ingredient_prices.effective_date, or None when there are
    no prices stored.'''
    try:
        row = db.query(
            'SELECT MAX(effective_date) AS d FROM ingredient_prices',
            one=True,
        )
    except Exception:
        return None
    d = (row or {}).get('d')
    if not d:
        return None
    # effective_date is a sqlite DATE: 'YYYY-MM-DD'. Format compactly.
    from datetime import datetime
    try:
        return datetime.strptime(d, '%Y-%m-%d').strftime('%b %d')
    except ValueError:
        return str(d)


def _last_backup_label():
    '''Pull the most recent backup file timestamp from the user's data
    directory. If none, say so plainly rather than hiding the row.'''
    data_dir = config.user_data_dir()
    newest_mtime = 0.0
    try:
        for entry in os.listdir(data_dir):
            if 'backup' not in entry.lower() or not entry.endswith('.db'):
                continue
            full = os.path.join(data_dir, entry)
            if os.path.isfile(full):
                newest_mtime = max(newest_mtime, os.path.getmtime(full))
    except OSError:
        pass
    if newest_mtime == 0:
        return 'No backup yet'
    from datetime import datetime, date
    when = datetime.fromtimestamp(newest_mtime)
    if when.date() == date.today():
        return f'Last backup today, {when.strftime("%I:%M %p").lstrip("0")}'
    return f'Last backup {when.strftime("%b %d, %I:%M %p").replace(" 0", " ")}'
