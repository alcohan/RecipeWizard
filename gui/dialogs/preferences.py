'''Configure › Preferences — currently just the USDA API key.

The key is stored in QSettings under 'usda/apiKey'. main_window pushes the
stored value into api.usda.set_api_key() at startup, and this page does
again whenever the key changes, so the running session picks it up
without a restart. Like the other Configure pages, it saves as you go
(when you leave the field); Test checks the key typed in without
saving it.

USDA keys are free and unlimited; we ship with no key and fall back to
the public DEMO_KEY (30 req/hour per IP) until the user provides one.
'''
from PySide6.QtCore import Qt, QSettings, Signal
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QVBoxLayout, QWidget

import api.usda
from gui.widgets import config_kit as kit


_KEY = 'usda/apiKey'
_OK = '#24502A'


class PreferencesPage(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        card, cl = kit.card()
        card.setMaximumWidth(720)
        cl.addWidget(kit.subheading('USDA FoodData Central'))
        intro = QLabel(
            'New ingredient looks up nutrition with the USDA FoodData Central API. Without a key it uses a'
            ' shared demo key capped at 30 searches an hour. Get a free key at '
            f'<a href="https://fdc.nal.usda.gov/api-key-signup.html" style="color: {kit.ROMAINE}">'
            'fdc.nal.usda.gov/api-key-signup.html</a> and paste it below.')
        intro.setWordWrap(True)
        intro.setOpenExternalLinks(True)
        intro.setTextInteractionFlags(Qt.TextBrowserInteraction)
        intro.setStyleSheet(f'color: {kit.KALE};')
        cl.addWidget(intro)

        self.key_edit = kit.field()
        self.key_edit.setPlaceholderText('Blank uses the shared demo key')
        self.key_edit.setText(QSettings().value(_KEY, '', type=str))
        self.key_edit.editingFinished.connect(self.save)
        self.test_btn = kit.button('Test')
        self.test_btn.setToolTip('Run a quick USDA search with the key above (doesn’t save it)')
        self.test_btn.clicked.connect(self.test)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.key_edit, stretch=1)
        row.addWidget(self.test_btn)
        col = QVBoxLayout()
        col.setSpacing(4)
        col.addWidget(kit.eyebrow('API key'))
        col.addLayout(row)
        cl.addLayout(col)
        self.status = QLabel('')
        self.status.setWordWrap(True)
        cl.addWidget(self.status)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 20, 28, 28)
        layout.setSpacing(12)
        layout.addWidget(kit.heading('Preferences'))
        layout.addWidget(kit.note('Settings for this computer. Changes save as you make them.'))
        layout.addWidget(card)
        layout.addStretch()
        self._show_saved()

    def has_key(self):
        return bool(QSettings().value(_KEY, '', type=str))

    def _say(self, text, color=kit.MUTED):
        self.status.setText(text)
        self.status.setStyleSheet(f'color: {color}; font-size: 12px;')

    def _show_saved(self):
        self._say('Saved · using your key' if self.has_key() else 'Using the shared demo key (30 searches an hour)')

    def save(self):
        value = self.key_edit.text().strip()
        if value == QSettings().value(_KEY, '', type=str):
            return
        QSettings().setValue(_KEY, value)
        api.usda.set_api_key(value)
        self._show_saved()
        self.changed.emit()

    def test(self):
        '''Search once with the key typed in (not necessarily saved).'''
        candidate = self.key_edit.text().strip()
        previous = QSettings().value(_KEY, '', type=str)
        api.usda.set_api_key(candidate)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            api.usda.search('apple')
        except Exception as exc:
            self._say(f'USDA didn’t accept it: {exc}', kit.WARN)
        else:
            self._say('The shared demo key works. Paste your own for more searches.' if not candidate
                      else 'Key works: USDA responded.', _OK)
        finally:
            QApplication.restoreOverrideCursor()
            api.usda.set_api_key(previous)
