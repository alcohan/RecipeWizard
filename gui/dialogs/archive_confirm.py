'''Archive guard shared by the Library and the recipe tab: archiving a
sub-recipe that recipes on the menu still use asks first, since your
prep still makes it.'''
from PySide6.QtWidgets import QMessageBox

import db


def confirm_archive(parent, recipe_id, name):
    '''True to go ahead and archive. Only asks when live recipes use it.'''
    live = [p['Name'] for p in db.get_parent_recipes(recipe_id) if p.get('Status') != 'archived']
    if not live:
        return True
    n = len(live)
    names = ', '.join(live[:5]) + (f' and {n - 5} more' if n > 5 else '')
    box = QMessageBox(QMessageBox.Warning, 'Archive sub-recipe',
                      f"{name} is used in {n} recipe{'s' if n != 1 else ''} on the menu: {names}.",
                      parent=parent)
    box.setInformativeText('Archiving hides it from the Library, but those recipes keep using it'
                           ' and their costs still include it.')
    archive = box.addButton('Archive anyway', QMessageBox.AcceptRole)
    box.addButton(QMessageBox.Cancel)
    box.setDefaultButton(QMessageBox.Cancel)
    box.exec()
    return box.clickedButton() is archive
