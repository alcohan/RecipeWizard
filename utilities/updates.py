'''Update checking against RecipeWizard's GitHub Releases.

Framework-agnostic: the GUI runs these off the UI thread and decides
what to show. Nothing here touches Qt or QSettings.

    check_for_update(current, include_prereleases) → Release | None

uses the releases *list* endpoint, because /releases/latest skips
pre-releases and (for now) every release is one. Unauthenticated
calls are capped at 60 an hour per IP; when GitHub says the cap is hit
we raise RateLimited with the time it lifts, so callers can back off.

Installing in place (Windows, PyInstaller one-file exe): download the
release's .exe to a temp file, verify its SHA-256, then hand off to a
small batch script that waits for this process to exit, keeps the old
exe as RecipeWizard.old.exe, moves the new one in and relaunches it.
A running exe can't be overwritten, so the swap has to happen after
we're gone.
'''
import hashlib
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field

import requests


REPO = 'alcohan/RecipeWizard'
RELEASES_URL = f'https://api.github.com/repos/{REPO}/releases'
RELEASES_PAGE = f'https://github.com/{REPO}/releases'
TIMEOUT = 10


class UpdateError(Exception):
    '''Network trouble, a bad response, or a failed download/verify.'''


class RateLimited(UpdateError):
    '''GitHub's unauthenticated cap (60/hour) is used up. `reset_at`
    is the epoch second it lifts.'''

    def __init__(self, reset_at):
        self.reset_at = reset_at
        when = time.strftime('%H:%M', time.localtime(reset_at))
        super().__init__(f'GitHub is limiting update checks; try again after {when}.')


class Cancelled(UpdateError):
    pass


# --- versions --------------------------------------------------------

_VERSION_RE = re.compile(r'^v?(\d+)\.(\d+)(?:\.(\d+))?(?:[-.+]?(.+))?$', re.IGNORECASE)


def parse_version(text):
    '''"v1.2.3" / "1.2" / "v1.2.3-beta.1" → a sortable tuple, or None.
    A suffix ranks below the plain version (1.2.3-beta < 1.2.3).'''
    m = _VERSION_RE.match(str(text or '').strip())
    if not m:
        return None
    major, minor, patch, suffix = m.groups()
    nums = (int(major), int(minor), int(patch or 0))
    if suffix:
        # Split "beta.10" into ('beta', 10) so numbers compare as numbers.
        parts = tuple((0, int(p), '') if p.isdigit() else (1, 0, p.lower())
                      for p in re.split(r'[.\-]', suffix) if p)
        return nums + (0, parts)
    return nums + (1, ())


def is_newer(candidate, current):
    '''True when tag `candidate` is a later version than `current`.
    Unparseable tags are never newer.'''
    a, b = parse_version(candidate), parse_version(current)
    return a is not None and b is not None and a > b


# --- releases --------------------------------------------------------

@dataclass
class Asset:
    name: str
    url: str          # browser_download_url
    size: int = 0
    digest: str = ''  # GitHub's own "sha256:<hex>", when it has one


@dataclass
class Release:
    tag: str
    name: str
    notes: str
    page_url: str
    prerelease: bool
    published: str = ''
    assets: list = field(default_factory=list)

    @property
    def version(self):
        return self.tag[1:] if self.tag[:1] in 'vV' else self.tag

    def exe_asset(self):
        exes = [a for a in self.assets if a.name.lower().endswith('.exe')]
        named = [a for a in exes if a.name.lower() == 'recipewizard.exe']
        return (named or exes or [None])[0]

    def sha256_asset(self, exe):
        '''A "<exe>.sha256" asset, else any lone .sha256 one.'''
        sums = [a for a in self.assets if a.name.lower().endswith('.sha256')]
        exact = [a for a in sums if a.name.lower() == exe.name.lower() + '.sha256']
        if exact:
            return exact[0]
        return sums[0] if len(sums) == 1 else None


def parse_releases(payload):
    '''The /releases JSON list → [Release], drafts dropped.'''
    if not isinstance(payload, list):
        raise UpdateError('Unexpected response from GitHub.')
    releases = []
    for r in payload:
        if not isinstance(r, dict) or r.get('draft') or not r.get('tag_name'):
            continue
        assets = [
            Asset(name=a.get('name', ''), url=a.get('browser_download_url', ''),
                  size=int(a.get('size') or 0), digest=a.get('digest') or '')
            for a in r.get('assets') or [] if isinstance(a, dict)
        ]
        releases.append(Release(
            tag=r['tag_name'],
            name=r.get('name') or r['tag_name'],
            notes=r.get('body') or '',
            page_url=r.get('html_url') or f"{RELEASES_PAGE}/tag/{r['tag_name']}",
            prerelease=bool(r.get('prerelease')),
            published=r.get('published_at') or '',
            assets=assets,
        ))
    return releases


def newest_release(releases, current, include_prereleases=True):
    '''The highest-versioned release newer than `current`, or None.'''
    best = None
    for r in releases:
        if r.prerelease and not include_prereleases:
            continue
        if not is_newer(r.tag, current):
            continue
        if best is None or parse_version(r.tag) > parse_version(best.tag):
            best = r
    return best


def fetch_releases(get=requests.get):
    '''GET the releases list. Raises RateLimited when GitHub's cap is
    hit, UpdateError for anything else that goes wrong.'''
    try:
        resp = get(RELEASES_URL, timeout=TIMEOUT, params={'per_page': 30},
                   headers={'Accept': 'application/vnd.github+json',
                            'X-GitHub-Api-Version': '2022-11-28',
                            'User-Agent': 'RecipeWizard-updater'})
    except requests.RequestException as exc:
        raise UpdateError(f"Couldn't reach GitHub ({exc.__class__.__name__}).") from exc
    if resp.status_code in (403, 429):
        headers = resp.headers or {}
        if resp.status_code == 429 or headers.get('X-RateLimit-Remaining') == '0':
            reset = headers.get('X-RateLimit-Reset')
            retry = headers.get('Retry-After')
            if reset and str(reset).isdigit():
                reset_at = int(reset)
            elif retry and str(retry).isdigit():
                reset_at = int(time.time()) + int(retry)
            else:
                reset_at = int(time.time()) + 3600
            raise RateLimited(reset_at)
    if resp.status_code != 200:
        raise UpdateError(f'GitHub answered {resp.status_code}.')
    try:
        return parse_releases(resp.json())
    except ValueError as exc:
        raise UpdateError('Unexpected response from GitHub.') from exc


def check_for_update(current, include_prereleases=True, get=requests.get):
    '''The release to offer, or None when `current` is up to date.'''
    return newest_release(fetch_releases(get), current, include_prereleases)


# --- installing in place (Windows one-file exe) ----------------------

def running_exe():
    '''Path of the frozen exe we're running as, or None from source.'''
    if getattr(sys, 'frozen', False):
        return os.path.abspath(sys.executable)
    return None


def can_install(release):
    '''In-place install needs the frozen Windows exe, a folder we can
    write next to it (not, say, Program Files) and an exe asset.'''
    exe = running_exe()
    return sys.platform == 'win32' and exe is not None and _writable(os.path.dirname(exe)) \
        and release is not None and release.exe_asset() is not None


def _writable(folder):
    try:
        fd, probe = tempfile.mkstemp(prefix='.rw-write-test-', dir=folder)
    except OSError:
        return False
    os.close(fd)
    remove_quietly(probe)
    return True


def expected_sha256(release, exe, get=requests.get):
    '''Hex digest to check the download against: GitHub's asset digest,
    else a .sha256 asset's first 64-hex token, else '' (unverified).'''
    if exe.digest.lower().startswith('sha256:'):
        return exe.digest.split(':', 1)[1].strip().lower()
    sums = release.sha256_asset(exe)
    if sums is None:
        return ''
    try:
        resp = get(sums.url, timeout=TIMEOUT, headers={'User-Agent': 'RecipeWizard-updater'})
    except requests.RequestException as exc:
        raise UpdateError("Couldn't fetch the checksum file.") from exc
    if resp.status_code != 200:
        raise UpdateError(f'Checksum file: GitHub answered {resp.status_code}.')
    m = re.search(r'\b[0-9a-fA-F]{64}\b', resp.text)
    if not m:
        raise UpdateError('The checksum file has no SHA-256 in it.')
    return m.group(0).lower()


def download(url, dest, progress=None, cancelled=lambda: False, expected_size=0,
             get=requests.get):
    '''Stream `url` to `dest` (via dest + ".part"). progress(done, total)
    after each chunk; cancelled() is polled between chunks. Returns the
    SHA-256 hex digest of what was written.'''
    part = dest + '.part'
    sha = hashlib.sha256()
    try:
        with get(url, stream=True, timeout=TIMEOUT,
                 headers={'User-Agent': 'RecipeWizard-updater'}) as resp:
            if resp.status_code != 200:
                raise UpdateError(f'Download: GitHub answered {resp.status_code}.')
            total = int(resp.headers.get('Content-Length') or expected_size or 0)
            done = 0
            with open(part, 'wb') as fh:
                for chunk in resp.iter_content(chunk_size=256 * 1024):
                    if cancelled():
                        raise Cancelled('Download cancelled.')
                    if not chunk:
                        continue
                    fh.write(chunk)
                    sha.update(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
        if total and done != total:
            raise UpdateError('The download ended early.')
        os.replace(part, dest)
    except requests.RequestException as exc:
        remove_quietly(part)
        raise UpdateError(f'Download failed ({exc.__class__.__name__}).') from exc
    except BaseException:
        remove_quietly(part)
        raise
    return sha.hexdigest()


def download_release(release, progress=None, cancelled=lambda: False, folder=None,
                     get=requests.get):
    '''Download and verify the release's exe. Returns its local path.'''
    exe = release.exe_asset()
    if exe is None:
        raise UpdateError('This release has no .exe to install.')
    expected = expected_sha256(release, exe, get=get)
    folder = folder or os.path.join(tempfile.gettempdir(), 'RecipeWizard-update')
    os.makedirs(folder, exist_ok=True)
    dest = os.path.join(folder, f'RecipeWizard-{release.version}.exe')
    actual = download(exe.url, dest, progress, cancelled, exe.size, get=get)
    if expected and actual != expected:
        remove_quietly(dest)
        raise UpdateError('The download doesn’t match its published checksum, so it was discarded.')
    return dest


def remove_quietly(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _bat_quote(path):
    # Inside a .cmd file % starts a variable; double it to keep it literal.
    return str(path).replace('%', '%%')


def write_swap_script(target, new_exe, pids, relaunch_args=(), wait_seconds=60, folder=None):
    '''Write the .cmd that finishes the install once `pids` have exited:
    target → <name>.old.exe, new_exe → target, relaunch target. If the
    swap fails it puts the old exe back and relaunches that. Returns
    the script path; it logs next to itself and deletes itself.'''
    target = os.path.abspath(target)
    base, ext = os.path.splitext(target)
    old = base + '.old' + ext
    folder = folder or os.path.dirname(os.path.abspath(new_exe))
    script = os.path.join(folder, 'RecipeWizard-swap.cmd')
    log = os.path.join(folder, 'RecipeWizard-swap.log')
    # Quote only what needs it: some programs don't take a quoted "/flag".
    args = ' '.join(_bat_quote(a) if re.fullmatch(r'[\w./:\\-]+', a) else f'"{_bat_quote(a)}"'
                    for a in relaunch_args)
    lines = [
        '@echo off',
        'chcp 65001 >nul',
        'setlocal EnableExtensions',
        f'set "TARGET={_bat_quote(target)}"',
        f'set "NEW={_bat_quote(os.path.abspath(new_exe))}"',
        f'set "OLD={_bat_quote(old)}"',
        f'set "LOG={_bat_quote(log)}"',
        # Full paths: a PATH with, say, Git's Unix find first would
        # silently break the wait loop.
        r'set "SYS=%SystemRoot%\System32"',
        'echo %DATE% %TIME% swap starting> "%LOG%"',
    ]
    # Wait for each process (the app, and under PyInstaller one-file its
    # bootloader parent, which holds the exe open) up to wait_seconds.
    for i, pid in enumerate(int(p) for p in pids):
        lines += [
            'set /a WAITED=0',
            f':wait{i}',
            rf'"%SYS%\tasklist.exe" /FI "PID eq {pid}" /NH 2>nul | "%SYS%\find.exe" " {pid} " >nul || goto waited{i}',
            f'if %WAITED% GEQ {int(wait_seconds)} goto waited{i}',
            'set /a WAITED+=1',
            r'"%SYS%\PING.EXE" -n 2 127.0.0.1 >nul',
            f'goto wait{i}',
            f':waited{i}',
        ]
    lines += [
        'echo %DATE% %TIME% app exited>> "%LOG%"',
        'if exist "%OLD%" del /f /q "%OLD%" >nul 2>&1',
        # The exe can stay locked a moment after its process is gone
        # (antivirus, the bootloader cleaning up); retry the first move.
        'set /a TRIES=0',
        ':move_old',
        'move /y "%TARGET%" "%OLD%" >nul 2>&1 && goto move_new',
        'set /a TRIES+=1',
        'if %TRIES% GEQ 20 goto fail',
        r'"%SYS%\PING.EXE" -n 2 127.0.0.1 >nul',
        'goto move_old',
        ':move_new',
        'move /y "%NEW%" "%TARGET%" >nul 2>&1 || goto restore',
        'echo %DATE% %TIME% swapped in new exe>> "%LOG%"',
        f'start "" "%TARGET%" {args}'.rstrip(),
        'goto done',
        ':restore',
        'move /y "%OLD%" "%TARGET%" >nul 2>&1',
        ':fail',
        'echo %DATE% %TIME% swap FAILED, relaunching the old exe>> "%LOG%"',
        'if exist "%TARGET%" start "" "%TARGET%"',
        ':done',
        # Delete this script: (goto) leaves the batch first so cmd
        # doesn't trip over its own file vanishing.
        '(goto) 2>nul & del "%~f0"',
    ]
    with open(script, 'w', encoding='utf-8', newline='\r\n') as fh:
        fh.write('\n'.join(lines) + '\n')
    return script


def launch_swap_script(script):
    '''Start the script detached and windowless. The caller quits next.'''
    env = dict(os.environ)
    # Don't let the relaunched one-file exe inherit this process's
    # PyInstaller bootstrap state (it would reuse our soon-gone _MEI dir).
    for key in list(env):
        if key.startswith('_PYI_') or key in ('_MEIPASS2', '_MEIPASS'):
            env.pop(key)
    env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    flags = 0
    if sys.platform == 'win32':
        # A hidden console (not DETACHED_PROCESS) so tasklist/ping/move
        # inherit it instead of each flashing a window of their own.
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    return subprocess.Popen(['cmd.exe', '/c', script], env=env, creationflags=flags,
                            close_fds=True, cwd=os.path.dirname(script))


def processes_to_wait_for():
    '''This process, plus the PyInstaller one-file bootloader parent
    that owns the exe file while we run.'''
    pids = [os.getpid()]
    # One-file unpacks to a temp _MEIPASS away from the exe; one-dir
    # runs beside it and has no bootloader parent to wait for.
    meipass = getattr(sys, '_MEIPASS', None)
    if getattr(sys, 'frozen', False) and meipass and not os.path.abspath(meipass).startswith(
            os.path.dirname(os.path.abspath(sys.executable))):
        pids.append(os.getppid())
    return pids
