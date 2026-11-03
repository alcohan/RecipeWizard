'''Backup and restore dialogs over utilities.backup.

    ask_backup_options(parent)        -> include photos? (None = cancelled)
    run_backup(parent, dest, images)  -> manifest, or None after an error box
    RestoreDialog(info)               -> .mode: 'overwrite' | 'merge'
    run_restore(parent, path, mode)   -> result, or None after an error box
    show_merge_summary(parent, report)

Whether to include photos is remembered in QSettings
('backup/includeImages'); Back up now uses it without asking once it's
been chosen.
'''
import datetime
import os

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QDialog, QDialogButtonBox, QLabel, QMessageBox,
    QProgressDialog, QRadioButton, QVBoxLayout,
)

import config
from utilities import backup

_INCLUDE_IMAGES = 'backup/includeImages'
_MUTED = '#5B625C'


def remembered_include_images():
    '''The last choice, or None if the user has never been asked.'''
    value = QSettings().value(_INCLUDE_IMAGES, None)
    if value is None:
        return None
    return str(value).lower() in ('true', '1')


def _megabytes(n):
    return f'{n / 1_000_000:,.0f} MB' if n >= 1_000_000 else f'{n / 1000:,.0f} KB'


class BackupOptionsDialog(QDialog):
    '''Include the ingredient photos or not; the choice is remembered.'''

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f'{config.APPNAME} | Back up library')
        photos = backup.image_files()
        heading = QLabel('Back up your library')
        heading.setStyleSheet('font-size: 15px; font-weight: 600;')
        body = QLabel('Recipes, ingredients, prices, suppliers and settings go into one '
                      f'{backup.EXTENSION} file.')
        body.setWordWrap(True)
        self.images = QCheckBox(f'Include ingredient photos ({len(photos)} photos, '
                                f'{_megabytes(backup.images_size())})')
        self.images.setEnabled(bool(photos))
        remembered = remembered_include_images()
        self.images.setChecked(bool(photos) and bool(remembered))
        note = QLabel('Photos make the file much larger. Without them, a restore keeps the photos '
                      'already on that computer.')
        note.setWordWrap(True)
        note.setStyleSheet(f'color: {_MUTED};')

        buttons = QDialogButtonBox()
        buttons.addButton('Back up', QDialogButtonBox.AcceptRole).setDefault(True)
        buttons.addButton(QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(body)
        layout.addSpacing(6)
        layout.addWidget(self.images)
        layout.addWidget(note)
        layout.addSpacing(6)
        layout.addWidget(buttons)
        self.setMinimumWidth(420)

    def accept(self):
        QSettings().setValue(_INCLUDE_IMAGES, self.images.isChecked())
        super().accept()


def ask_backup_options(parent):
    dlg = BackupOptionsDialog(parent)
    if dlg.exec() != QDialog.Accepted:
        return None
    return dlg.images.isChecked()


class _Progress:
    '''A modal progress box fed by utilities.backup's progress(done,
    total, text) callbacks. The work runs on the UI thread, so each
    update lets events through to keep the window painting.'''

    def __init__(self, parent, title):
        self.box = QProgressDialog(parent)
        self.box.setWindowTitle(title)
        self.box.setCancelButton(None)
        self.box.setWindowModality(Qt.WindowModal)
        self.box.setMinimumDuration(300)
        self.box.setAutoClose(False)
        self.box.setAutoReset(False)
        self.box.setMinimumWidth(360)

    def __call__(self, done, total, text):
        self.box.setMaximum(max(total, 1))
        self.box.setValue(min(done, max(total, 1)))
        self.box.setLabelText(text)
        QApplication.processEvents()

    def close(self):
        self.box.close()


def run_backup(parent, dest, include_images):
    progress = _Progress(parent, 'Backing up')
    try:
        return backup.create_backup(dest, include_images=include_images, progress=progress)
    except Exception as exc:
        QMessageBox.critical(parent, 'Backup failed', str(exc) or exc.__class__.__name__)
        return None
    finally:
        progress.close()


def describe(info):
    '''"Made Nov 3, 2026 2:05 PM · 123 ingredients · 28 recipes · 150 photos".'''
    parts = []
    try:
        when = datetime.datetime.fromisoformat(info.created)
        parts.append('Made ' + when.strftime('%b %d, %Y %I:%M %p').replace(' 0', ' '))
    except (TypeError, ValueError):
        pass
    counts = info.counts
    for key, label in (('ingredients', 'ingredients'), ('recipes', 'recipes'), ('suppliers', 'suppliers')):
        if key in counts:
            parts.append(f'{counts[key]} {label}')
    parts.append(f'{len(info.image_names)} photos' if info.has_images else 'no photos')
    return ' · '.join(parts)


class RestoreDialog(QDialog):
    '''Overwrite everything, or merge the backup into this library.'''

    def __init__(self, info, parent=None):
        super().__init__(parent)
        self.info = info
        self.setWindowTitle(f'{config.APPNAME} | Restore library')
        heading = QLabel(f'Restore from {os.path.basename(info.path)}')
        heading.setStyleSheet('font-size: 15px; font-weight: 600;')
        heading.setWordWrap(True)
        summary = QLabel(describe(info) + ('' if info.kind == 'rwbackup' else ' · older backup format'))
        summary.setStyleSheet(f'color: {_MUTED};')
        summary.setWordWrap(True)

        self.overwrite = QRadioButton('Overwrite everything')
        overwrite_note = QLabel(
            'Your library is replaced by the backup'
            + (', and photos with the same name are replaced by the backup\'s.' if info.has_images
               else '. Your photos stay as they are.'))
        self.merge = QRadioButton('Merge into this library')
        merge_note = QLabel(
            'Adds what the backup has that this library doesn\'t; nothing here is changed or '
            'deleted. Anything with the same name (an ingredient, recipe, supplier, tag, allergen, '
            'diet, saved view or comparison) keeps your current version, and the summary lists '
            'what was kept. Price history entries you don\'t have are added'
            + (', and photos you don\'t have are copied.' if info.has_images else '.'))
        for note in (overwrite_note, merge_note):
            note.setWordWrap(True)
            note.setStyleSheet(f'color: {_MUTED}; margin-left: 22px;')
        group = QButtonGroup(self)
        group.addButton(self.overwrite)
        group.addButton(self.merge)
        self.merge.setChecked(True)

        safety = QLabel('Either way, a backup of your current library is saved to the data folder first.')
        safety.setWordWrap(True)
        safety.setStyleSheet(f'color: {_MUTED};')

        buttons = QDialogButtonBox()
        self.restore_btn = buttons.addButton('Merge', QDialogButtonBox.AcceptRole)
        self.restore_btn.setDefault(True)
        buttons.addButton(QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.overwrite.toggled.connect(
            lambda on: self.restore_btn.setText('Overwrite' if on else 'Merge'))

        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(summary)
        layout.addSpacing(8)
        layout.addWidget(self.merge)
        layout.addWidget(merge_note)
        layout.addSpacing(4)
        layout.addWidget(self.overwrite)
        layout.addWidget(overwrite_note)
        layout.addSpacing(8)
        layout.addWidget(safety)
        layout.addWidget(buttons)
        self.setMinimumWidth(480)

    @property
    def mode(self):
        return 'overwrite' if self.overwrite.isChecked() else 'merge'


def run_restore(parent, path, mode):
    progress = _Progress(parent, 'Restoring' if mode == 'overwrite' else 'Merging')
    try:
        if mode == 'overwrite':
            return backup.restore_overwrite(path, progress=progress)
        return backup.restore_merge(path, progress=progress)
    except Exception as exc:
        QMessageBox.critical(parent, 'Restore failed',
                             f'{exc or exc.__class__.__name__}\n\nYour library was not changed.')
        return None
    finally:
        progress.close()


def merge_details(report):
    '''The names behind the summary, for the details pane.'''
    lines = []
    for key, label in backup.MergeReport.KINDS:
        for verb, names in (('Added', report.added[key]), ('Kept yours', report.kept[key])):
            if names:
                lines.append(f'{label} — {verb.lower()} ({len(names)}):')
                lines.extend(f'    {n}' for n in names)
    lines.append('')
    lines.append(f'Safety backup: {report.safety}')
    return '\n'.join(lines)


def show_merge_summary(parent, report):
    added = sum(len(v) for v in report.added.values())
    box = QMessageBox(QMessageBox.Information, 'Merge finished',
                      'Nothing new to add — this library already has everything in the backup.'
                      if not added and not report.prices_added and not report.images_copied
                      else 'The backup was merged into your library.', parent=parent)
    box.setInformativeText('\n'.join(report.summary_lines())
                           + '\n\nWhere a name was already here, your version was kept.')
    box.setDetailedText(merge_details(report))
    box.exec()
    return box
