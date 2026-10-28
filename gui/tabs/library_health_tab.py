'''Library Health place — a to-do list of data-quality signals.

Shows one card per check: missing nutrition, stale prices, unused
ingredients, duplicate names. Each card carries a count badge and up
to five sample names so the user can tell at a glance what needs
attention. A separate card lists the files in the user's data folder
whose name contains "backup", so the latest backup is one click away.

Lazy-built: the first `showEvent` triggers refresh. The main window
re-reads whenever a model resets, so adding an ingredient from
elsewhere updates the counts next time this place is visible.
'''
import os
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

import config
import db


_CHECKS = (
    # (key, title, idle_label, description)
    ('missing_nutrition', 'Missing nutrition',
     'Every ingredient has calorie data',
     'Ingredients with no calories recorded. USDA search fills these in automatically.'),
    ('stale_prices', 'Stale prices',
     'All prices are fresh',
     'No supplier price newer than 90 days — add a current price or confirm the latest.'),
    ('unused_ingredients', 'Unused ingredients',
     'No orphans',
     'Not referenced by any recipe. Candidates for cleanup if intentionally retired.'),
    ('duplicate_names', 'Duplicate names',
     'No duplicates',
     'Two or more ingredients share a name (case-insensitive). Rename or merge.'),
)


class LibraryHealthTab(QWidget):
    '''Static report. Emits ingredientRequested when the user clicks a
    sample ingredient name so the main window can route to the
    Ingredients place (future wiring).'''

    ingredientRequested = Signal(str)   # ingredient name

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stale = True
        self._container = QWidget()
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(24, 24, 24, 24)
        self._container_layout.setSpacing(16)

        scroll = QScrollArea()
        scroll.setWidget(self._container)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

    def showEvent(self, event):
        super().showEvent(event)
        if self._stale:
            self.refresh()
            self._stale = False

    def mark_stale(self):
        '''Called by the main window on model-reset signals. Avoids
        querying when the place isn't visible.'''
        self._stale = True
        if self.isVisible():
            self.refresh()
            self._stale = False

    def refresh(self):
        # Tear down previous cards.
        while self._container_layout.count():
            item = self._container_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        heading = QLabel('Library Health')
        heading.setStyleSheet('font-size: 22px; font-weight: 700; color: #1E2320;'
                              ' letter-spacing: -0.01em;')
        subhead = QLabel("Data-quality signals, worst first. Address each when you have a moment.")
        subhead.setStyleSheet('color: #5B625C; padding-bottom: 4px;')
        self._container_layout.addWidget(heading)
        self._container_layout.addWidget(subhead)

        try:
            report = db.library_health_report()
        except Exception as exc:
            err = QLabel(f'Could not read the library: {exc}')
            err.setStyleSheet('color: #8A3F0C; background: #FBEADB; padding: 8px 12px;'
                              ' border-radius: 8px;')
            self._container_layout.addWidget(err)
            self._container_layout.addStretch()
            return

        # Sort cards by count desc so the worst-off checks come first;
        # zero-count checks sink to the bottom but still render as a
        # muted "all clear" line.
        card_order = sorted(_CHECKS, key=lambda c: -report[c[0]][0])
        for key, title, idle, description in card_order:
            count, sample = report[key]
            self._container_layout.addWidget(
                _HealthCard(title, count, sample, idle, description)
            )
        self._container_layout.addWidget(_BackupsCard())
        self._container_layout.addStretch()


class _HealthCard(QFrame):
    '''Rounded card: title + count badge + a line of sample item names
    + a one-line description. Zero-count cards render as a muted
    "all clear" row — same shape, different color.'''

    def __init__(self, title, count, sample_names, idle_label, description, parent=None):
        super().__init__(parent)
        all_clear = count == 0
        self.setObjectName('HealthCard')
        bg, border, title_fg = ('#FFFFFF', '#E2E0D9', '#1E2320')
        if all_clear:
            # Muted green for cleared checks — reads as "already fine".
            bg, border, title_fg = ('#F3F6F0', '#CFDBC8', '#3F4641')
        self.setStyleSheet(f'''
            QFrame#HealthCard {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 12px;
            }}
            QFrame#HealthCard QLabel {{ background: transparent; border: 0; }}
        ''')

        title_label = QLabel(title)
        title_label.setStyleSheet(f'font-weight: 600; font-size: 15px; color: {title_fg};')

        if all_clear:
            badge = QLabel('✓')
            badge.setStyleSheet('background: #CFDBC8; color: #24502A; font-weight: 700;'
                                ' padding: 2px 10px; border-radius: 10px;')
        else:
            badge = QLabel(str(count))
            # Amber for small issues, red for lots.
            is_many = count >= 5
            badge.setStyleSheet(
                f'background: {"#F5E2DC" if is_many else "#FBEADB"};'
                f' color: {"#7B2D1E" if is_many else "#8A3F0C"};'
                ' font-weight: 700; padding: 2px 10px; border-radius: 10px;'
            )

        header_row = QHBoxLayout()
        header_row.addWidget(title_label)
        header_row.addWidget(badge)
        header_row.addStretch()

        if all_clear:
            body = QLabel(idle_label)
            body.setStyleSheet('color: #3F4641;')
        else:
            if sample_names:
                shown = ', '.join(sample_names)
                if count > len(sample_names):
                    shown += f', and {count - len(sample_names)} more'
                body = QLabel(shown)
            else:
                body = QLabel(description)
            body.setStyleSheet('color: #1E2320;')
            body.setWordWrap(True)

        desc = QLabel(description) if not all_clear else None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)
        layout.addLayout(header_row)
        layout.addWidget(body)
        if desc is not None:
            desc.setStyleSheet('color: #5B625C; font-size: 12px;')
            desc.setWordWrap(True)
            layout.addWidget(desc)


class _BackupsCard(QFrame):
    '''Lists .db files in the user's data folder whose name contains
    "backup", newest first. Click a filename to open the containing
    folder (same UX as Tools > Open Data Folder).'''

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('HealthCard')
        self.setStyleSheet('''
            QFrame#HealthCard {
                background: #FFFFFF;
                border: 1px solid #E2E0D9;
                border-radius: 12px;
            }
            QFrame#HealthCard QLabel { background: transparent; border: 0; }
        ''')

        title = QLabel('Backups')
        title.setStyleSheet('font-weight: 600; font-size: 15px; color: #1E2320;')

        files = _list_backups()
        count_label = QLabel(str(len(files)) if files else '0')
        count_label.setStyleSheet(
            'background: #ECEAE4; color: #3F4641;'
            ' font-weight: 700; padding: 2px 10px; border-radius: 10px;'
        )
        header_row = QHBoxLayout()
        header_row.addWidget(title)
        header_row.addWidget(count_label)
        header_row.addStretch()
        open_btn = QPushButton('Open folder')
        open_btn.setCursor(Qt.PointingHandCursor)
        open_btn.setStyleSheet(
            'QPushButton { background: #FFFFFF; border: 1px solid #D9D6CD;'
            ' border-radius: 6px; padding: 4px 10px; } '
            'QPushButton:hover { background: #F5FFF5; border-color: #2a7; }'
        )
        open_btn.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(config.user_data_dir())))
        header_row.addWidget(open_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)
        layout.addLayout(header_row)
        if not files:
            body = QLabel('No backup files yet — Tools > Backup Database makes one.')
            body.setStyleSheet('color: #5B625C;')
            layout.addWidget(body)
            return
        for name, when in files[:5]:
            line = QLabel(f'<b>{name}</b> &nbsp; <span style="color:#5B625C">{when}</span>')
            line.setTextFormat(Qt.RichText)
            layout.addWidget(line)
        if len(files) > 5:
            more = QLabel(f'and {len(files) - 5} more')
            more.setStyleSheet('color: #5B625C; padding-top: 2px;')
            layout.addWidget(more)


def _list_backups():
    '''Return [(filename, when-string)], newest first.'''
    data_dir = config.user_data_dir()
    out = []
    try:
        for entry in os.listdir(data_dir):
            if 'backup' not in entry.lower() or not entry.endswith('.db'):
                continue
            full = os.path.join(data_dir, entry)
            if os.path.isfile(full):
                out.append((entry, os.path.getmtime(full)))
    except OSError:
        return []
    out.sort(key=lambda t: -t[1])
    return [(name, datetime.fromtimestamp(mtime).strftime('%b %d, %Y %H:%M'))
            for name, mtime in out]
