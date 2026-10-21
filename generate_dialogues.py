"""Generate original game dialogue demos with the running local Take Studio app.

No cloud API is used. Run only while Take Studio is serving 127.0.0.1:38765.
"""
from __future__ import annotations

import json
import shutil
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:38765"
ROOT = Path(__file__).resolve().parent
APP = ROOT.parent / "voice_studio"
OUT = ROOT / "audio_samples"
OUT.mkdir(exist_ok=True)

SPECS = [
    {
        "name": "01_ko_tactical_guard",
        "label": "전투 · 방어선 / 강현",
        "dialogue": "방벽이 무너진다. 부상자부터 이동시켜. 내가 마지막까지 길을 막겠다.",
        "language": "Korean", "emotion": "determination", "delivery": "normal",
        "voice_id": "male-steadfast", "seed": 411,
    },
    {
        "name": "02_ko_reassurance",
        "label": "구조 · 안심 / 서윤",
        "dialogue": "괜찮아. 여기까지 잘 왔어. 이제 숨을 고르고, 내 목소리만 따라와.",
        "language": "Korean", "emotion": "relief", "delivery": "normal",
        "voice_id": "female-warm", "seed": 1039,
    },
    {
        "name": "03_en_scout_command",
        "label": "탐색 · 지시 / 준서",
        "dialogue": "The signal is back. Hold your position until I give the word.",
        "language": "English", "emotion": "determination", "delivery": "normal",
        "voice_id": "male-bright", "seed": 707,
    },
    {
        "name": "04_en_gate_discovery",
        "label": "발견 · 긴장 / 하린",
        "dialogue": "Wait. I can hear it. The gate is opening beneath us.",
        "language": "English", "emotion": "fear", "delivery": "normal",
        "voice_id": "female-bright", "seed": 1489,
    },
]


def api(method: str, path: str, payload=None):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(BASE + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


records = []
for spec in SPECS:
    body = {key: value for key, value in spec.items() if key not in ("name", "label")}
    body.update(mode="tts", tts_engine="voxcpm2", speed="normal", max_new_tokens=384)
    job = api("POST", "/api/jobs", body)
    print("START", spec["name"], job["id"], flush=True)
    last_stage = None
    for _ in range(240):
        state = api("GET", "/api/jobs/" + job["id"])
        if state.get("stage") != last_stage:
            print(spec["name"], state.get("stage"), state.get("message"), flush=True)
            last_stage = state.get("stage")
        if state["status"] in ("completed", "failed", "cancelled"):
            break
        time.sleep(3)
    else:
        raise TimeoutError(spec["name"])
    (OUT / (spec["name"] + ".json")).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    if state["status"] != "completed":
        print("FAILED", spec["name"], state.get("message"), flush=True)
        records.append({"name": spec["name"], "status": state["status"], "message": state.get("message")})
        continue
    sound = APP / "data" / "jobs" / job["id"] / "inference" / "output.wav"
    if not sound.is_file():
        raise FileNotFoundError(sound)
    destination = OUT / (spec["name"] + ".wav")
    shutil.copyfile(sound, destination)
    records.append({**spec, "mode": "tts", "engine": "VoxCPM2", "status": "completed",
                    "job_id": job["id"], "duration": state.get("result", {}).get("duration"),
                    "file": destination.name})
    print("SAVED", destination.name, destination.stat().st_size, flush=True)

(OUT / "index.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
print("COMPLETE", len([r for r in records if r["status"] == "completed"]), "/", len(SPECS), flush=True)
