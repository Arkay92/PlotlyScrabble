"""Offline regional word validation with explicit, versioned sources."""
from functools import lru_cache
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent/'data'/'dictionaries'
DICTIONARIES = {
    'en_US': ('US English', 'American spellings'),
    'en_GB': ('UK English', 'British −ise spellings'),
    'en_CA': ('Canadian English', 'Canadian spellings'),
    'en_AU': ('Australian English', 'Australian spellings'),
}


@lru_cache(maxsize=4)
def words(dictionary):
    if dictionary not in DICTIONARIES:
        raise ValueError('Choose a dictionary before starting the game.')
    # Lowercase entries only: omit proper names, possessives, abbreviations,
    # accented forms and compounds, rather than silently accepting fragments.
    return frozenset(w.upper() for w in (ROOT/f'{dictionary}.txt').read_text(encoding='utf-8').splitlines()
                     if re.fullmatch(r'[a-z]{2,15}',w))


def contains(word, dictionary):
    return word.upper() in words(dictionary)
