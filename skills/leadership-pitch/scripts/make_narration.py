"""Speak a demo video's voice-over, one audio file per step, with Piper (offline text to speech).

    PIPER=/path/to/piper PIPER_MODEL=/path/to/en_US-lessac-high.onnx \
        python make_narration.py narration.json out/video

narration.json holds {"lines": ["...", "..."]}, one line per storyboard step, in step order (see
assets/narration-example.json). Writes out/video/narration/NN.wav and durations.json (seconds per
line); presentation_storyboard.js then holds each step at least as long as its line and mixes the
audio into the video.

Install Piper apart from the project: `python -m venv tts && tts/bin/pip install piper-tts`, then
download a voice (.onnx and .onnx.json) from https://huggingface.co/rhasspy/piper-voices
(the original recording used en_US/lessac/high).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import wave
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    lines = json.loads(Path(sys.argv[1]).read_text())["lines"]
    out = Path(sys.argv[2]) / "narration"
    piper, model = os.environ.get("PIPER", "piper"), os.environ.get("PIPER_MODEL")
    if not model:
        print("Set PIPER_MODEL to a Piper voice (.onnx).", file=sys.stderr)
        return 1
    out.mkdir(parents=True, exist_ok=True)
    durations = []
    for i, line in enumerate(lines, 1):
        wav = out / f"{i:02d}.wav"
        subprocess.run(
            [piper, "-m", model, "-f", str(wav), "--sentence-silence", "0.25"],
            input=line.encode(),
            check=True,
            capture_output=True,
        )
        with wave.open(str(wav)) as w:
            durations.append(round(w.getnframes() / w.getframerate(), 2))
        print(f"{i:02d}  {durations[-1]:5.1f} s  {line[:70]}")
    (out / "durations.json").write_text(json.dumps(durations))
    print(f"{len(lines)} lines, {sum(durations):.0f} s of narration in {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
