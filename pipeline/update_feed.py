#!/usr/bin/env python3
"""Add an episode to episodes.json and regenerate feed.xml deterministically.

Usage (from repo root):
  update_feed.py --mp3 episodes/2026-10-23.mp3 --title "..." --summary-file notes.txt [--date 2026-10-23]

Keeps the newest KEEP episodes in the feed and deletes older MP3 files
from episodes/ so the GitHub Pages site stays small.
"""
import argparse, datetime as dt, html, json, os, subprocess
from email.utils import format_datetime
from zoneinfo import ZoneInfo

BASE = "https://collateralguy.github.io/daily-briefing"
KEEP = 20
ET = ZoneInfo("America/New_York")

CHANNEL = {
    "title": "Daily News Brief",
    "description": ("A daily briefing on tokenization, collateral management, digital cash, "
                    "regulation, and blockchain infrastructure in financial markets."),
    "author": "CollateralGuy",
    "email": "collateralguy@gmail.com",
    "image": f"{BASE}/cover.jpg",
}


def esc(s):
    return html.escape(s, quote=True)


def duration_secs(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", path], capture_output=True, text=True).stdout
    return int(float(out.strip()))


def hms(sec):
    return f"{sec//3600:02d}:{sec%3600//60:02d}:{sec%60:02d}"


def build(episodes):
    items = []
    for e in episodes:
        items.append(f"""    <item>
      <title>{esc(e['title'])}</title>
      <description>{esc(e['summary'])}</description>
      <itunes:summary>{esc(e['summary'])}</itunes:summary>
      <pubDate>{e['pubDate']}</pubDate>
      <enclosure url="{BASE}/{e['file']}" length="{e['bytes']}" type="audio/mpeg"/>
      <guid isPermaLink="false">daily-news-brief-{e['date']}</guid>
      <itunes:duration>{hms(e['seconds'])}</itunes:duration>
      <itunes:episodeType>full</itunes:episodeType>
      <itunes:explicit>false</itunes:explicit>
    </item>""")
    c = CHANNEL
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{esc(c['title'])}</title>
    <link>{BASE}/</link>
    <atom:link href="{BASE}/feed.xml" rel="self" type="application/rss+xml"/>
    <description>{esc(c['description'])}</description>
    <language>en-us</language>
    <itunes:author>{esc(c['author'])}</itunes:author>
    <itunes:owner>
      <itunes:name>{esc(c['author'])}</itunes:name>
      <itunes:email>{c['email']}</itunes:email>
    </itunes:owner>
    <itunes:image href="{c['image']}"/>
    <itunes:category text="Business"/>
    <itunes:explicit>false</itunes:explicit>
    <itunes:type>episodic</itunes:type>
    <image>
      <url>{c['image']}</url>
      <title>{esc(c['title'])}</title>
      <link>{BASE}/</link>
    </image>
{chr(10).join(items)}
  </channel>
</rss>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mp3")
    ap.add_argument("--title")
    ap.add_argument("--summary-file")
    ap.add_argument("--date", default=dt.datetime.now(ET).date().isoformat())
    ap.add_argument("--rebuild-only", action="store_true")
    a = ap.parse_args()

    db = json.load(open("episodes.json")) if os.path.exists("episodes.json") else []

    if not a.rebuild_only:
        pub = dt.datetime.now(ET)
        if pub.date().isoformat() != a.date:
            pub = dt.datetime.fromisoformat(a.date).replace(hour=5, tzinfo=ET)
        summary = open(a.summary_file, encoding="utf-8").read().strip()
        entry = {
            "date": a.date,
            "title": a.title,
            "summary": summary,
            "file": a.mp3,
            "bytes": os.path.getsize(a.mp3),
            "seconds": duration_secs(a.mp3),
            "pubDate": format_datetime(pub),
        }
        db = [e for e in db if e["date"] != a.date] + [entry]

    db.sort(key=lambda e: e["date"], reverse=True)
    keep, drop = db[:KEEP], db[KEEP:]
    for e in drop:
        if os.path.exists(e["file"]):
            os.remove(e["file"])
            print("pruned", e["file"])

    json.dump(keep, open("episodes.json", "w"), indent=2)
    open("feed.xml", "w", encoding="utf-8").write(build(keep))
    print(f"feed.xml written with {len(keep)} episode(s)")


if __name__ == "__main__":
    main()
