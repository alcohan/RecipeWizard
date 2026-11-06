from PySide6.QtGui import QFont, QGuiApplication


def test_text_sized_by_text_width_is_never_elided():
    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841
    from gui.widgets.text_fit import elide, text_width
    for size in (9, 10, 11, 12, 13):
        font = QFont()
        font.setPixelSize(size)
        font.setWeight(QFont.DemiBold)
        for word in ('Core', 'Bowl', 'Breakfast', 'Digital only', 'High protein'):
            assert elide(font, word, text_width(font, word)) == word
    assert elide(font, 'Digital only', 20).endswith('…')
