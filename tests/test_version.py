import os
import re

import config

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_release_stamp_finds_exactly_one_version_line():
    # .github/workflows/release.yml replaces this line with the tag's version.
    text = open(os.path.join(ROOT, 'config.py'), encoding='utf-8').read()
    assert len(re.findall(r"(?m)^__version__ = '[^']*'", text)) == 1


def test_build_text(monkeypatch):
    monkeypatch.setattr(config, 'SOURCE', ('0.0.5', 3, '36aad67', True))
    assert config.build_text() == 'Source · 3 commits after v0.0.5 · 36aad67 · uncommitted changes'
    monkeypatch.setattr(config, 'SOURCE', ('0.0.5', 0, '36aad67', False))
    assert config.build_text() == 'Source · 36aad67'
