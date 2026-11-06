'''Configure › Preferences — the USDA API key and update checks.

The key is stored in QSettings under 'usda/apiKey'. main_window pushes the
stored value into api.usda.set_api_key() at startup, and this page does
again whenever the key changes, so the running session picks it up
without a restart. Like the other Configure pages, it saves as you go
(when you leave the field); Test checks the key typed in without
saving it.

USDA keys are free and unlimited; we ship with no key and fall back to
the public DEMO_KEY (30 req/hour per IP) until the user provides one.

Updates: whether to check GitHub once a day at startup, and whether
pre-releases count (on by default while every release is one). Both
are read by gui.services.updates at check time.

Food cost target: the percent recipes are flagged over, or off
(gui.services.food_cost). `foodCostChanged` tells the main window to
redraw what shows it.
'''
from PySide6.QtCore import Qt, QSettings, Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDoubleSpinBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

import api.usda
import config
from gui.services import food_cost
from gui.services import updates as update_prefs
from gui.widgets import config_kit as kit


_KEY = 'usda/apiKey'
_OK = '#24502A'


class PreferencesPage(QWidget):
    changed = Signal()
    foodCostChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        card, cl = kit.card()
        card.setMaximumWidth(720)
        cl.addWidget(kit.subheading('USDA FoodData Central'))
        intro = QLabel(
            'Without a key, a shared demo key allows 30 searches an hour. Get a free key at '
            f'<a href="https://fdc.nal.usda.gov/api-key-signup.html" style="color: {kit.ROMAINE}">'
            'fdc.nal.usda.gov</a>.')
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
        layout.addWidget(self._food_cost_card())
        layout.addWidget(card)
        layout.addWidget(self._updates_card())
        layout.addStretch()
        self._show_saved()

    def _food_cost_card(self):
        card, cl = kit.card()
        card.setMaximumWidth(720)
        cl.addWidget(kit.subheading('Food cost target'))
        cl.addWidget(kit.note('Recipes over target get ▲ and appear in Needs review'))
        self.fc_enabled = QCheckBox('Flag recipes over a food-cost target')
        self.fc_enabled.setStyleSheet(f'color: {kit.KALE};')
        self.fc_enabled.setChecked(food_cost.enabled())
        self.fc_target = QDoubleSpinBox()
        self.fc_target.setRange(5.0, 80.0)
        self.fc_target.setDecimals(1)
        self.fc_target.setSingleStep(0.5)
        self.fc_target.setSuffix(' %')
        self.fc_target.setKeyboardTracking(False)
        self.fc_target.setMinimumHeight(30)
        self.fc_target.setValue(food_cost.stored_fraction() * 100)
        self.fc_target.setEnabled(self.fc_enabled.isChecked())
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.fc_enabled)
        row.addSpacing(12)
        row.addWidget(kit.eyebrow('Target'))
        row.addWidget(self.fc_target)
        row.addStretch()
        cl.addLayout(row)
        self.fc_enabled.toggled.connect(self._save_food_cost)
        self.fc_target.valueChanged.connect(self._save_food_cost)
        return card

    def _save_food_cost(self, *_):
        self.fc_target.setEnabled(self.fc_enabled.isChecked())
        food_cost.save(self.fc_enabled.isChecked(), self.fc_target.value() / 100)
        self.foodCostChanged.emit()

    def _updates_card(self):
        card, cl = kit.card()
        card.setMaximumWidth(720)
        cl.addWidget(kit.subheading('Updates'))
        cl.addWidget(kit.note(f'Version {config.__version__}'))
        self.auto_check = QCheckBox('Check for updates once a day when RecipeWizard starts')
        self.auto_check.setChecked(update_prefs.check_automatically())
        self.auto_check.toggled.connect(
            lambda on: QSettings().setValue(update_prefs.KEY_AUTO, on))
        self.prereleases = QCheckBox('Include pre-releases')
        self.prereleases.setToolTip('Test builds published ahead of a full release')
        self.prereleases.setChecked(update_prefs.include_prereleases())
        self.prereleases.toggled.connect(
            lambda on: QSettings().setValue(update_prefs.KEY_PRERELEASES, on))
        for box in (self.auto_check, self.prereleases):
            box.setStyleSheet(f'color: {kit.KALE};')
            cl.addWidget(box)
        return card

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
            self._say('Demo key works' if not candidate
                      else 'Key works: USDA responded.', _OK)
        finally:
            QApplication.restoreOverrideCursor()
            api.usda.set_api_key(previous)
