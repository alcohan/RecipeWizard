from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('About')
        self.resize(380, 200)

        title = QLabel('<b>RecipeWizard</b> &nbsp; v0.0.1')
        title.setAlignment(Qt.AlignCenter)
        author = QLabel('by Adrian Cohan')
        author.setAlignment(Qt.AlignCenter)
        attribution = QLabel(
            'Nutrition data sourced from<br>'
            'USDA FoodData Central<br>'
            '<a href="https://fdc.nal.usda.gov">https://fdc.nal.usda.gov</a>'
        )
        attribution.setAlignment(Qt.AlignCenter)
        attribution.setOpenExternalLinks(True)
        attribution.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(author)
        layout.addSpacing(16)
        layout.addWidget(attribution)
        layout.addStretch()
        layout.addWidget(buttons)
