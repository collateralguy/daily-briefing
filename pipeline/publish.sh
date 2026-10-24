#!/usr/bin/env bash
# Voice script.txt, add the episode to the feed, and push to GitHub Pages.
# Usage (from repo root): pipeline/publish.sh /path/to/script.txt /path/to/notes.txt "Episode title" [YYYY-MM-DD]
set -euo pipefail
SCRIPT="$1"; NOTES="$2"; TITLE="$3"
DATE="${4:-$(TZ=America/New_York date +%F)}"
VOICE="$(cat pipeline/voice.txt 2>/dev/null || echo am_michael)"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"

# 1. Voice engine (Kokoro) + speech checker (Whisper), installed fresh each session
python3 -c "import kokoro_onnx, faster_whisper, num2words" 2>/dev/null || \
  pip install -q --break-system-packages kokoro-onnx faster-whisper num2words soundfile
mkdir -p .voices
for f in kokoro-v1.0.onnx voices-v1.0.bin; do
  [ -s ".voices/$f" ] || curl -sfL -o ".voices/$f" "https://huggingface.co/fastrtc/kokoro-onnx/resolve/main/$f"
done

# 2. Audio (every chunk is checked by speech recognition; failures are regenerated)
mkdir -p episodes
MP3="episodes/$DATE.mp3"
python3 pipeline/make_audio.py "$SCRIPT" "$MP3" --voice "$VOICE"
mv "episodes/$DATE.qa.txt" "/tmp/$DATE.qa.txt" 2>/dev/null || true

# 3. Feed
python3 pipeline/update_feed.py --mp3 "$MP3" --title "$TITLE" --summary-file "$NOTES" --date "$DATE"
python3 -c "import xml.dom.minidom; xml.dom.minidom.parse('feed.xml')" && echo "feed.xml is valid XML"

# 4. Publish
git config user.email noreply@anthropic.com; git config user.name Claude
git add -A episodes episodes.json feed.xml
git commit -q -m "Episode $DATE" || true
git push -q origin HEAD:main
echo "published $MP3 (QA report: /tmp/$DATE.qa.txt)"

# 5. Keep the repo small: if history grows past ~400 MB, squash to one commit.
SIZE=$(du -sm .git | cut -f1)
if [ "$SIZE" -gt 400 ]; then
  git checkout -q --orphan squash && git add -A && git commit -q -m "Squash history ($DATE)"
  git push -q -f origin squash:main && git checkout -q -B main squash
  echo "history squashed (was ${SIZE} MB)"
fi
