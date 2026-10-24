#!/usr/bin/env python3
"""Turn a plain-text briefing script into a podcast MP3 with Piper TTS.

Usage: make_audio.py SCRIPT.txt OUT.mp3 [--voice PATH_TO_ONNX]

Paragraphs (separated by blank lines) get a longer pause; a line that is
exactly '###' marks a section break and gets an extra-long pause.
"""
import argparse, io, os, re, subprocess, sys, tempfile, wave

from piper import PiperVoice

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_VOICE = os.path.join(HERE, "..", ".voices", "en_US-ryan-high.onnx")

PARA_PAUSE = 0.7
SECTION_PAUSE = 1.6


def clean(text: str) -> str:
    # Strip markdown leftovers and things a TTS engine reads badly.
    text = re.sub(r"[*_#`>]+", "", text)
    text = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = text.replace("&", " and ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("out")
    ap.add_argument("--voice", default=DEFAULT_VOICE)
    a = ap.parse_args()

    voice = PiperVoice.load(a.voice)
    rate = voice.config.sample_rate
    raw = open(a.script, encoding="utf-8").read()

    blocks = []
    for chunk in re.split(r"\n\s*\n", raw):
        chunk = chunk.strip()
        if not chunk:
            continue
        if chunk == "###":
            blocks.append(("pause", SECTION_PAUSE))
            continue
        blocks.append(("text", clean(chunk)))
        blocks.append(("pause", PARA_PAUSE))

    with tempfile.TemporaryDirectory() as td:
        wav_path = os.path.join(td, "all.wav")
        with wave.open(wav_path, "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(rate)
            for kind, val in blocks:
                if kind == "pause":
                    out.writeframes(b"\x00\x00" * int(rate * val))
                    continue
                if not val:
                    continue
                for ch in voice.synthesize(val):
                    out.writeframes(ch.audio_int16_bytes)
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-y", "-i", wav_path,
             "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
             "-ac", "1", "-ar", "44100", "-b:a", "64k", a.out],
            check=True,
        )
    dur = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", a.out], capture_output=True, text=True).stdout.strip()
    print(f"wrote {a.out}  duration={float(dur)/60:.1f} min  size={os.path.getsize(a.out)/1e6:.1f} MB")


if __name__ == "__main__":
    main()
