#!/usr/bin/env python3
"""Turn a plain-text briefing script into a podcast MP3 with Kokoro TTS,
checking every chunk with Whisper speech recognition so garbled audio is
caught and re-generated instead of published.

Usage: make_audio.py SCRIPT.txt OUT.mp3 [--voice am_michael] [--models DIR]

Blank lines separate paragraphs; a line that is exactly '###' is a section break.
Writes a QA report next to the MP3 (OUT.qa.txt).
"""
import argparse, difflib, json, os, re, subprocess, sys

import numpy as np
from kokoro_onnx import Kokoro

HERE = os.path.dirname(os.path.abspath(__file__))
SR_OUT = 24000
PARA_PAUSE, SECTION_PAUSE, CHUNK_PAUSE = 0.55, 1.4, 0.18
MAX_CHARS = 280          # chunk size: 1–3 sentences
PASS = 0.72              # min word-match ratio vs. the script text


def load_lexicon():
    p = os.path.join(HERE, "lexicon.json")
    return json.load(open(p)) if os.path.exists(p) else {}


def clean(text, lex):
    text = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[*_#`>]+", "", text)
    text = text.replace("&", " and ").replace("—", ", ").replace("–", ", ")
    text = re.sub(r"[()]", ", ", text)
    for k in sorted(lex, key=len, reverse=True):
        v = lex[k]
        text = re.sub(rf"(?<![\w-]){re.escape(k)}(?![\w-])", v, text)
    text = re.sub(r"\s+,", ",", text)
    return re.sub(r"\s+", " ", text).strip()


def chunks_of(par):
    sents = re.split(r"(?<=[.!?])\s+(?=[A-Z\"'])", par)
    out, cur = [], ""
    for s in sents:
        if cur and len(cur) + len(s) + 1 > MAX_CHARS:
            out.append(cur); cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        out.append(cur)
    return out


_W = None
def words(s):
    s = s.lower().replace("-", " ")
    return re.findall(r"[a-z]+|\d+", s)


def num_norm(ws):
    try:
        from num2words import num2words
    except ImportError:
        return ws
    out = []
    for w in ws:
        out += words(num2words(int(w))) if w.isdigit() and len(w) < 10 else [w]
    return out


def score(asr, audio, text):
    a16 = np.interp(np.arange(0, len(audio), SR_OUT / 16000), np.arange(len(audio)), audio).astype(np.float32)
    heard = " ".join(s.text for s in asr.transcribe(a16, beam_size=1, language="en")[0])
    # compare letters only (no spaces), so "R C H K D" == "RCHKD" and "stablecoin" == "stable coin"
    a_s = "".join(num_norm(words(text))); b_s = "".join(num_norm(words(heard)))
    r = difflib.SequenceMatcher(None, a_s, b_s, autojunk=False).ratio()
    return r, heard


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script"); ap.add_argument("out")
    ap.add_argument("--voice", default="am_michael")
    ap.add_argument("--models", default=os.path.join(HERE, "..", ".voices"))
    ap.add_argument("--speed", type=float, default=1.0)
    a = ap.parse_args()

    from faster_whisper import WhisperModel
    asr = WhisperModel("base.en", device="cpu", compute_type="int8")
    tts = Kokoro(os.path.join(a.models, "kokoro-v1.0.onnx"), os.path.join(a.models, "voices-v1.0.bin"))
    lex = load_lexicon()

    plan = []
    for block in re.split(r"\n\s*\n", open(a.script, encoding="utf-8").read()):
        block = block.strip()
        if not block:
            continue
        if block == "###":
            plan.append(("pause", SECTION_PAUSE)); continue
        cs = chunks_of(clean(block, lex))
        for i, c in enumerate(cs):
            plan.append(("text", c))
            plan.append(("pause", CHUNK_PAUSE if i < len(cs) - 1 else PARA_PAUSE))

    def synth(t, speed):
        audio, sr = tts.create(t, voice=a.voice, speed=speed, lang="en-us")
        assert sr == SR_OUT
        return audio.astype(np.float32)

    pieces, qa, fixed, flagged = [], [], 0, 0
    n_text = sum(1 for k, _ in plan if k == "text")
    done = 0
    for kind, val in plan:
        if kind == "pause":
            pieces.append(np.zeros(int(SR_OUT * val), np.float32)); continue
        done += 1
        best = None
        # attempt 1: chunk as written; 2: slightly slower; 3: sentence by sentence
        for attempt in range(3):
            if attempt < 2:
                audio = synth(val, a.speed * (1.0 if attempt == 0 else 0.92))
            else:
                parts = re.split(r"(?<=[.!?,;])\s+", val)
                audio = np.concatenate([np.concatenate([synth(p, a.speed), np.zeros(int(SR_OUT * 0.12), np.float32)]) for p in parts if p.strip()])
            r, heard = score(asr, audio, val)
            if best is None or r > best[0]:
                best = (r, audio, heard, attempt)
            if r >= PASS:
                break
        r, audio, heard, attempt = best
        if attempt > 0 and r >= PASS:
            fixed += 1
        if r < PASS:
            flagged += 1
            qa.append(f"FLAGGED ratio={r:.2f}\n  SCRIPT: {val}\n  HEARD:  {heard.strip()}")
        pieces.append(audio)
        if done % 25 == 0:
            print(f"  {done}/{n_text} chunks", flush=True)

    full = np.concatenate(pieces)
    pcm = (np.clip(full, -1, 1) * 32767).astype(np.int16).tobytes()
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "s16le", "-ar", str(SR_OUT), "-ac", "1", "-i", "-",
                    "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "44100", "-ac", "1", "-b:a", "96k", a.out],
                   input=pcm, check=True)
    report = f"chunks={n_text} regenerated_ok={fixed} flagged={flagged}\n" + "\n".join(qa)
    open(os.path.splitext(a.out)[0] + ".qa.txt", "w").write(report + "\n")
    print(f"wrote {a.out}  duration={len(full)/SR_OUT/60:.1f} min  size={os.path.getsize(a.out)/1e6:.1f} MB")
    print(report.splitlines()[0])
    if flagged:
        print("WARNING: some chunks failed the speech check; see the .qa.txt report", file=sys.stderr)


if __name__ == "__main__":
    main()
