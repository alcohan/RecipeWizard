'''Print recipe pages through the system print dialog.

print_recipes(parent, recipe_ids) shows the native print dialog (on
Windows, the usual one: printer, copies, preferences) and prints every
recipe's pages to the chosen printer. To get a PDF, pick "Microsoft
Print to PDF". Pages are always Letter-or-printer-size portrait; the
layout doesn't have a landscape form.

Data is read when printing starts, so it's whatever is in the library
right then (recipe tab edits are saved to the library as they're made).
'''
from PySide6.QtCore import Qt
from PySide6.QtGui import QPageSize
from PySide6.QtPrintSupport import QAbstractPrintDialog, QPrintDialog, QPrinter
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

import db
from gui.printing.recipe_page import page_layout_for, paint_recipes
from gui.services import print_branding


def recipe_pages_data(recipe_ids):
    datas = []
    for rid in recipe_ids:
        data = db.recipe_print_data(rid)
        if data is not None:
            datas.append(data)
    return datas


def save_pdf(path, datas, branding=None):
    '''Write the pages straight to a PDF file (tests and scripts).'''
    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(path)
    printer.setPageSize(QPageSize(QPageSize.Letter))
    page_layout_for(printer)
    paint_recipes(printer, datas, branding or print_branding.current())


def print_recipes(parent, recipe_ids):
    '''Ask where to print, then print. Returns True if pages were sent.'''
    datas = recipe_pages_data(recipe_ids)
    if not datas:
        QMessageBox.information(parent, 'Print', 'There’s no recipe to print.')
        return False

    printer = QPrinter(QPrinter.HighResolution)
    printer.setPageSize(QPageSize(QPageSize.Letter))
    printer.setDocName(datas[0]['name'] if len(datas) == 1 else f'{len(datas)} recipes')

    dialog = QPrintDialog(printer, parent)
    dialog.setWindowTitle(f"Print {datas[0]['name']}" if len(datas) == 1 else f'Print {len(datas)} recipes')
    # Whole recipes only: no page ranges, selection or current page.
    dialog.setOption(QAbstractPrintDialog.PrintPageRange, False)
    dialog.setOption(QAbstractPrintDialog.PrintSelection, False)
    dialog.setOption(QAbstractPrintDialog.PrintCurrentPage, False)
    if dialog.exec() != QDialog.Accepted:
        return False

    # The printer's preferences may have switched to landscape; the
    # page is laid out for portrait only.
    page_layout_for(printer)
    QApplication.setOverrideCursor(Qt.WaitCursor)
    try:
        paint_recipes(printer, datas, print_branding.current())
    except Exception as exc:
        QApplication.restoreOverrideCursor()
        QMessageBox.warning(parent, 'Print', f'Couldn’t print:\n{exc}')
        return False
    QApplication.restoreOverrideCursor()
    return True
