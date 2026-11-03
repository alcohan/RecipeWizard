'''"A new version is available": release notes plus Download, which
opens the release page in the browser.'''
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QHBoxLayout, QTextBrowser, QVBoxLayout

import config
from gui.widgets import config_kit as kit


class UpdateDialog(QDialog):
    def __init__(self, release, parent=None):
        super().__init__(parent)
        self.release = release
        self.setWindowTitle('Update available')
        self.resize(520, 420)

        title = kit.heading(f'RecipeWizard {release.tag} is available')
        details = [f'You have v{config.__version__}']
        if release.prerelease:
            details.append('pre-release')
        if release.published:
            details.append(f'published {release.published[:10]}')
        sub = kit.note(' · '.join(details))

        notes = QTextBrowser()
        notes.setOpenExternalLinks(True)
        notes.setMarkdown(release.notes.strip() or '_No release notes for this version._')
        notes.setStyleSheet(f'QTextBrowser {{ border: 1px solid {kit.BORDER}; border-radius: 6px;'
                            ' background: #ffffff; padding: 6px; }')

        self.later_btn = kit.button('Later')
        self.later_btn.clicked.connect(self.reject)
        self.download_btn = kit.button('Download', primary=True)
        self.download_btn.setToolTip(release.page_url)
        self.download_btn.clicked.connect(self._on_download)

        self.buttons = QHBoxLayout()
        self.buttons.addStretch()
        self.buttons.addWidget(self.later_btn)
        self.buttons.addWidget(self.download_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)
        layout.addWidget(title)
        layout.addWidget(sub)
        layout.addWidget(kit.eyebrow("What's new"))
        layout.addWidget(notes, stretch=1)
        layout.addLayout(self.buttons)

    def _on_download(self):
        QDesktopServices.openUrl(QUrl(self.release.page_url))
        self.accept()
