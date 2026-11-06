'''Forgiving text search for the filter boxes and Ctrl+K.

"jalapenos" finds "Jalapeños" (accents and case are ignored), and a
small typo still matches ("jalepeno", "romane"). Each word typed must
match somewhere in the text: as a plain substring, or as a word (or the
start of one) within a small edit distance: none for 1–3 letters, one
for 4–6, two for longer words.

score() is lower for better matches (None for no match), so callers can
rank results; matches() is the yes/no test.
'''
import re
import unicodedata
from functools import lru_cache

_SPLIT = re.compile(r'[^0-9a-z]+')


@lru_cache(maxsize=8192)
def normalize(text):
    '''Lowercase, accents stripped, punctuation turned into spaces.'''
    decomposed = unicodedata.normalize('NFKD', text or '')
    plain = ''.join(c for c in decomposed if not unicodedata.combining(c)).casefold()
    return ' '.join(w for w in _SPLIT.split(plain) if w)


def _allowed(n):
    return 0 if n <= 3 else 1 if n <= 6 else 2


def _distance(a, b, limit):
    '''Optimal string alignment distance (adjacent swaps count as one),
    or limit + 1 once it's clearly over.'''
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev2 = None
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        best = cur[0]
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and prev2 is not None and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
            best = min(best, cur[j])
        if best > limit:
            return limit + 1
        prev2, prev = prev, cur
    return prev[-1]


def _token_cost(token, text, words):
    '''0 for an exact substring at a word start, 1 elsewhere in a word,
    2 + edits for a near miss; None when it doesn't match.'''
    pos = text.find(token)
    if pos >= 0:
        return 0 if pos == 0 or text[pos - 1] == ' ' else 1
    limit = _allowed(len(token))
    if not limit:
        return None
    best = None
    for w in words:
        # the whole word, or its start (typing "jalepe" for "jalapenos")
        for cand in {w, w[:len(token)], w[:len(token) + 1], w[:max(1, len(token) - 1)]}:
            d = _distance(token, cand, limit)
            if d <= limit and (best is None or d < best):
                best = d
        if best == 1:
            break
    return None if best is None else 2 + best


def score(query, text):
    '''Lower is better; None when `text` doesn't match `query`.
    An empty query matches everything with score 0.'''
    tokens = normalize(query).split()
    if not tokens:
        return 0
    hay = normalize(text)
    words = hay.split()
    total = 0
    for t in tokens:
        c = _token_cost(t, hay, words)
        if c is None:
            return None
        total += c
    # Ties: earlier and shorter text first.
    first = hay.find(tokens[0])
    return total * 1000 + (first if first >= 0 else 500) + len(hay) / 1000


def matches(query, text):
    return score(query, text) is not None
