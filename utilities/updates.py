'''Update checking against RecipeWizard's GitHub Releases.

Framework-agnostic: the GUI runs these off the UI thread and decides
what to show. Nothing here touches Qt or QSettings.

    check_for_update(current, include_prereleases) → Release | None

uses the releases *list* endpoint, because /releases/latest skips
pre-releases and (for now) every release is one. Unauthenticated
calls are capped at 60 an hour per IP; when GitHub says the cap is hit
we raise RateLimited with the time it lifts, so callers can back off.
'''
import re
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

    def exe_asset(self):
        exes = [a for a in self.assets if a.name.lower().endswith('.exe')]
        named = [a for a in exes if a.name.lower() == 'recipewizard.exe']
        return (named or exes or [None])[0]


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

