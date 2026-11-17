"""Speak the presentation demo's voice-over, one audio file per step, with Piper (offline text to speech).

    PIPER=/path/to/piper PIPER_MODEL=/path/to/en_US-lessac-high.onnx \
        python scripts/make_narration.py [outDir]

Reads scripts/presentation_narration.json and writes outDir/narration/NN.wav (default outDir:
reports/presentation/video) plus durations.json (seconds per line). scripts/presentation_storyboard.js
then holds each step at least as long as its line and mixes the audio into the video.

Piper is not a project dependency. Install it apart, for example in a virtual environment:
`pip install piper-tts`, and download a voice (the .onnx file and its .onnx.json) from
https://huggingface.co/rhasspy/piper-voices (the recording used en_US/lessac/high).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    out = (
        Path(
            sys.argv[1]
            if len(sys.argv) > 1
            else ROOT / "reports" / "presentation" / "video"
        )
        / "narration"
    )
    piper, model = os.environ.get("PIPER", "piper"), os.environ.get("PIPER_MODEL")
    if not model:
        print(
            "Set PIPER_MODEL to a Piper voice (.onnx); see the docstring.",
            file=sys.stderr,
        )
        return 1
    lines = json.loads((ROOT / "scripts" / "presentation_narration.json").read_text())[
        "lines"
    ]
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
