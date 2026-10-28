#!/usr/bin/env python3
"""Pronunciation audit: run BEFORE voicing.

Lists every unusual word in the script (rare words, names, mixed-case brands)
exactly as the voice will receive it after lexicon.json and acronym spelling,
together with the phonemes (IPA) the voice will actually speak. Review the IPA,
and for anything that would come out wrong, add an entry to pipeline/lexicon.json
(written spelling -> a respelling the voice says correctly), then re-run until clean.

Words already checked and found fine are listed in pipeline/reviewed_words.txt
(one per line) and are skipped, so each day's review is short. After reviewing,
add the words that sound right with --mark-reviewed.

Usage: python3 pipeline/pron_audit.py SCRIPT.txt [--all] [--mark-reviewed]
  --all            also list lexicon-handled and already-reviewed words
  --mark-reviewed  append every word currently listed to reviewed_words.txt
                   (run this only AFTER fixing the wrong ones in lexicon.json)
"""
import os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from make_audio import clean, load_lexicon
from kokoro_onnx.tokenizer import Tokenizer
try:
    from wordfreq import zipf_frequency
except ImportError:
    sys.exit("pip install --break-system-packages wordfreq")

RARE = 3.2   # Zipf frequency below this counts as unusual (common words are ~4-7)

def main():
    path = sys.argv[1]; show_all = "--all" in sys.argv
    lex = load_lexicon()
    rp = os.path.join(HERE, "reviewed_words.txt")
    reviewed = set(open(rp).read().split()) if os.path.exists(rp) else set()
    raw = open(path, encoding="utf-8").read().replace("###", "")
    raw_words = set(re.findall(r"[A-Za-z][A-Za-z0-9'.\-]*[A-Za-z0-9]", raw))
    handled = {w for w in raw_words if any(re.fullmatch(re.escape(k) + r"('s|s)?", w) for k in lex)}
    spoken = clean(raw, lex)
    tok = Tokenizer()
    seen = {}
    for w in re.findall(r"[A-Za-z][A-Za-z']*[A-Za-z]", spoken):
        base = re.sub(r"'s$", "", w)
        z = zipf_frequency(base.lower(), "en")
        odd = z < RARE or re.search(r"[a-z][A-Z]", base) or (base[0].isupper() and z < 3.6)
        if odd and base not in seen:
            seen[base] = z
    rows, new = [], []
    for w, z in sorted(seen.items(), key=lambda x: x[1]):
        lexed = w not in raw_words or w in handled
        if (lexed or w in reviewed) and not show_all:
            continue
        new.append(w)
        rows.append(f"{z:4.1f}  {w:24s} {tok.phonemize(w, 'en-us')}")
    print(f"{len(rows)} words to review (Zipf frequency, word as sent to the voice, phonemes it will speak):")
    print("\n".join(rows))
    if "--mark-reviewed" in sys.argv and new:
        with open(rp, "a") as f:
            f.write("\n".join(new) + "\n")
        print(f"marked {len(new)} words as reviewed")

if __name__ == "__main__":
    main()
