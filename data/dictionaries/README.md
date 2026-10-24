# Dictionary sources and permissions

Downloaded on 24 October 2026 from the English Speller Database's generated
word lists, pinned to release `rel-2026.02.25`:

- [US English](https://raw.githubusercontent.com/en-wl/wordlist-diff/refs/tags/rel-2026.02.25/en_US.txt)
- [UK English, traditional -ise](https://raw.githubusercontent.com/en-wl/wordlist-diff/refs/tags/rel-2026.02.25/en_GB-ise.txt), saved as `en_GB.txt`
- [Canadian English](https://raw.githubusercontent.com/en-wl/wordlist-diff/refs/tags/rel-2026.02.25/en_CA.txt)
- [Australian English](https://raw.githubusercontent.com/en-wl/wordlist-diff/refs/tags/rel-2026.02.25/en_AU.txt)

Copyright 2000-2026 by Kevin Atkinson. Permission to use, copy, modify,
distribute, and sell the data is granted under the accompanying
[Copyright](Copyright) notice, retained in full along with upstream source
acknowledgments. Keep that notice with all distributed dictionary copies.

These are ESDB regional spell-checker lists used here for casual word play;
they are not NWL or Collins Scrabble Words tournament lexicons.

The app loads entries matching `[a-z]{2,15}` and uppercases those entries for
comparison. It does not split apostrophes or punctuation into additional words.
The complete upstream text files are retained, and filtering happens locally.
See `manifest.json` for source URLs, SHA-256 hashes and playable-word counts.

Upstream project and documentation:

- [ESDB source](https://github.com/en-wl/wordlist)
- [Generated lists](https://github.com/en-wl/wordlist-diff)
- [Dictionary documentation](https://wordlist.aspell.net/hunspell-readme/)
