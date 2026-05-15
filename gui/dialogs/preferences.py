'''Preferences dialog — currently just the USDA API key.

The key is stored in QSettings under 'usda/apiKey'. main_window pushes the
stored value into api.usda.set_api_key() at startup and again every time
this dialog accepts a change, so the running session picks it up without
a restart.

USDA keys are free and unlimited; we ship with no key and fall back to
the public DEMO_KEY (30 req/hour per IP) until the user provides one.
'''
from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QVBoxLayout,
)

import api.usda


class PreferencesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Preferences')
        self.resize(520, 200)

        intro = QLabel(
            'RecipeWizard uses the <b>USDA FoodData Central</b> API to look up '
            'nutrition data when creating ingredients. Without a key, requests '
            'fall back to a shared demo key capped at 30 requests/hour.'
            '<br><br>'
            'Get a free, unlimited key at '
            '<a href="https://fdc.nal.usda.gov/api-key-signup.html">'
            'fdc.nal.usda.gov/api-key-signup.html</a> '
            'and paste it below.'
        )
        intro.setWordWrap(True)
        intro.setOpenExternalLinks(True)
        intro.setTextInteractionFlags(Qt.TextBrowserInteraction)

        self.key_edit = QLineEdit()
        self.key_edit.setPlaceholderText('Leave blank to use the shared demo key')
        self.key_edit.setText(QSettings().value('usda/apiKey', '', type=str))

        self.test_btn = QPushButton('Test')
        self.test_btn.setToolTip('Verify the key by running a quick USDA search.')
        self.test_btn.clicked.connect(self._on_test)

        key_row = QHBoxLayout()
        key_row.addWidget(self.key_edit, stretch=1)
        key_row.addWidget(self.test_btn)

        form = QFormLayout()
        form.addRow('USDA API key:', key_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addSpacing(8)
        layout.addLayout(form)
        layout.addStretch()
        layout.addWidget(buttons)

    def _on_test(self):
        '''Run a one-off search with the currently-entered value (not the
        saved one) so the user can verify a key before committing.'''
        candidate = self.key_edit.text().strip()
        previous = QSettings().value('usda/apiKey', '', type=str)
        api.usda.set_api_key(candidate)
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                api.usda.search('apple')
            finally:
                QApplication.restoreOverrideCursor()
        except Exception as exc:
            QMessageBox.warning(self, 'USDA Key Test Failed', str(exc))
        else:
            if not candidate:
                QMessageBox.information(
                    self, 'USDA Key Test',
                    'The shared demo key worked. For higher rate limits, paste your own key.',
                )
            else:
                QMessageBox.information(self, 'USDA Key Test', 'Key accepted — USDA responded successfully.')
        finally:
            # Restore whatever was actually saved; the Test button is non-committal.
            api.usda.set_api_key(previous)

    def _on_save(self):
        value = self.key_edit.text().strip()
        QSettings().setValue('usda/apiKey', value)
        api.usda.set_api_key(value)
        self.accept()
