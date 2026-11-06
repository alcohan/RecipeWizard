'''Help › About: version and build, links to the release notes, updates
and the data folder, and the nutrition data credit.'''
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QVBoxLayout

import config
from gui.widgets import config_kit as kit
from utilities import updates


class AboutDialog(QDialog):
    def __init__(self, parent=None, on_check_updates=None):
        super().__init__(parent)
        self.setWindowTitle('About RecipeWizard')
        self.setMinimumWidth(400)
        self.setStyleSheet(f'QDialog {{ background: {kit.BG}; }}')
        self._on_check_updates = on_check_updates

        title = kit.heading('RecipeWizard')
        version = QLabel(f'Version {config.__version__}')
        version.setStyleSheet(f'color: {kit.KALE}; font-size: 15px; font-weight: 600;')
        build = kit.note(config.build_text())

        link = f'color: {kit.ROMAINE}'
        links = [f'<a href="notes" style="{link}">Release notes</a>',
                 f'<a href="data" style="{link}">Data folder</a>']
        if on_check_updates is not None:
            links.insert(1, f'<a href="updates" style="{link}">Check for updates</a>')
        actions = QLabel(' &nbsp;·&nbsp; '.join(links))
        actions.setTextFormat(Qt.RichText)
        actions.linkActivated.connect(self._on_link)

        credit = QLabel(f'Nutrition data from <a href="https://fdc.nal.usda.gov" style="{link}">'
                        'USDA FoodData Central</a>')
        credit.setTextFormat(Qt.RichText)
        credit.setOpenExternalLinks(True)
        credit.setStyleSheet(f'color: {kit.MUTED};')
        author = kit.note('By Adrian Cohan')

        close = kit.button('Close', primary=True)
        close.clicked.connect(self.accept)
        foot = QHBoxLayout()
        foot.addStretch()
        foot.addWidget(close)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(6)
        layout.addWidget(title)
        layout.addWidget(version)
        layout.addWidget(build)
        layout.addSpacing(10)
        layout.addWidget(actions)
        layout.addSpacing(14)
        layout.addWidget(credit)
        layout.addWidget(author)
        layout.addSpacing(10)
        layout.addLayout(foot)

    def _on_link(self, href):
        if href == 'notes':
            QDesktopServices.openUrl(QUrl(f'{updates.RELEASES_PAGE}/tag/v{config.__version__}'))
        elif href == 'data':
            QDesktopServices.openUrl(QUrl.fromLocalFile(config.user_data_dir()))
        elif href == 'updates' and self._on_check_updates is not None:
            self.accept()
            self._on_check_updates()
