"""Offline speech-recognition spot check for generated portfolio examples."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = ROOT.parent / "voice_studio"
sys.path.insert(0, str(APP))
from engines.transcribe import run  # noqa: E402

records = json.loads((ROOT / "audio_samples" / "index.json").read_text(encoding="utf-8"))
for record in records:
    if record["status"] != "completed":
        continue
    audio = ROOT / "audio_samples" / record["file"]
    result = run({"source_path": str(audio), "language": record["language"]}, ROOT / "audio_samples")
    record["asr_spot_check"] = result["transcript"]
    print(record["name"], "=>", result["transcript"], flush=True)
(ROOT / "audio_samples" / "index.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
