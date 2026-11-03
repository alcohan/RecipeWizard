'''"A new version is available": release notes plus Download, which
opens the release page in the browser, and — when running as the
packaged exe — Install and Restart.

Installing (install_update): offer a library backup first, since the
new version upgrades the database the first time it opens; download
the exe with progress and Cancel; check it against its SHA-256; then
close the window (which prompts for unsaved edits) and hand over to
utilities.updates' swap script, which relaunches the new version.
'''
import threading

from PySide6.QtCore import QEventLoop, QObject, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QMessageBox, QProgressDialog, QTextBrowser, QVBoxLayout,
)

import config
from gui.widgets import config_kit as kit
from gui.workers import run_async
from utilities import updates


class UpdateDialog(QDialog):
    '''exec() returns Accepted with `install` True when the user chose
    Install and Restart; the caller then runs install_update().'''

    def __init__(self, release, parent=None, installable=None):
        super().__init__(parent)
        self.release = release
        self.install = False
        if installable is None:
            installable = updates.can_install(release)
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
        # Install is the main action when it's possible; Download (the
        # release page) stays for a manual copy.
        self.download_btn = kit.button('Download…' if installable else 'Download',
                                       primary=not installable)
        self.download_btn.setToolTip(release.page_url)
        self.download_btn.clicked.connect(self._on_download)
        self.install_btn = None

        self.buttons = QHBoxLayout()
        self.buttons.addStretch()
        self.buttons.addWidget(self.later_btn)
        self.buttons.addWidget(self.download_btn)
        if installable:
            self.install_btn = kit.button('Install and Restart', primary=True)
            self.install_btn.clicked.connect(self._on_install)
            self.buttons.addWidget(self.install_btn)

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

    def _on_install(self):
        self.install = True
        self.accept()


def install_update(window, release, backup):
    '''Run the install from the main window. `backup()` makes a library
    backup and returns True when it worked. Returns True when the app
    is quitting so the swap script can take over.'''
    title = 'Install Update'
    answer = QMessageBox.question(
        window, title,
        f'Back up your library before installing {release.tag}?\n\n'
        'Your recipes stay where they are, but the new version upgrades the '
        'database the first time it opens. A backup lets you go back.',
        QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.Yes)
    if answer == QMessageBox.Cancel:
        return False
    if answer == QMessageBox.Yes and not backup():
        return False

    path = download_with_progress(window, release)
    if path is None:
        return False

    confirm = QMessageBox.question(
        window, title,
        f'RecipeWizard {release.tag} is downloaded and verified.\n\n'
        "Restart now to finish installing? You'll be asked to save any open edits.",
        QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Yes)
    # close() runs the window's own save prompts; Cancel there keeps
    # the app open and the install off.
    if confirm != QMessageBox.Yes or not window.close():
        updates.remove_quietly(path)
        return False
    try:
        script = updates.write_swap_script(updates.running_exe(), path,
                                           updates.processes_to_wait_for())
        updates.launch_swap_script(script)
    except Exception as exc:
        updates.remove_quietly(path)
        window.show()
        QMessageBox.critical(window, title, f"Couldn't start the installer.\n\n{exc}")
        return False
    QApplication.quit()
    return True


class _Progress(QObject):
    # Emitted on the worker thread, delivered queued on the UI thread.
    changed = Signal(object, object)


def download_with_progress(window, release):
    '''Download and verify under a modal progress dialog with Cancel.
    The local path, or None when cancelled or failed (failures are
    reported here).'''
    dlg = QProgressDialog(f'Downloading RecipeWizard {release.tag}…', 'Cancel', 0, 0, window)
    dlg.setWindowTitle('Install Update')
    dlg.setWindowModality(Qt.WindowModal)
    dlg.setMinimumDuration(0)
    dlg.setAutoClose(False)
    dlg.setAutoReset(False)
    cancel = threading.Event()
    progress = _Progress()

    def on_progress(done, total):
        if total and not cancel.is_set():
            dlg.setMaximum(1000)
            dlg.setValue(int(done * 1000 / total))
            dlg.setLabelText(f'Downloading RecipeWizard {release.tag}…  '
                             f'{done / 1e6:.0f} of {total / 1e6:.0f} MB')
    progress.changed.connect(on_progress)

    outcome = {}
    loop = QEventLoop()

    def finish(key, value):
        outcome[key] = value
        loop.quit()

    def on_cancel():
        # The worker notices between chunks, removes its partial file
        # and reports Cancelled through `failed`.
        cancel.set()
        dlg.setLabelText('Cancelling…')

    # The Cancel button emits canceled; Esc only rejects the dialog.
    dlg.canceled.connect(on_cancel)
    dlg.rejected.connect(on_cancel)
    run_async(lambda: updates.download_release(release, progress.changed.emit, cancel.is_set),
              lambda p: finish('path', p), lambda msg: finish('error', msg))
    dlg.show()
    loop.exec()
    # Closing the dialog ourselves emits both; neither is the user's.
    dlg.canceled.disconnect(on_cancel)
    dlg.rejected.disconnect(on_cancel)
    dlg.close()
    if 'error' in outcome:
        if not cancel.is_set():
            QMessageBox.warning(window, 'Install Update',
                                f"The update couldn't be downloaded.\n\n{outcome['error']}")
        return None
    if cancel.is_set():   # finished in the instant Cancel was pressed
        updates.remove_quietly(outcome['path'])
        return None
    return outcome['path']
