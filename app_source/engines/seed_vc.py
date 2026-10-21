"""Offline Seed-VC v2 adapter. Run in the dedicated .venv-vc process."""
from __future__ import annotations

import argparse
import gc
import json
import math
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "seed-vc"
MODEL_ROOT = ROOT / "models" / "seed-vc"
SOURCE_COMMIT = "51383efd921027683c89e5348211d93ff12ac2a8"


def _boolean(value):
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "on"}
    return bool(value)


def _number(request, key, default, lower, upper, *, integer=False):
    value = float(request.get(key, default))
    if not math.isfinite(value) or not lower <= value <= upper:
        raise ValueError(f"{key}: {lower}~{upper} 범위의 값이 필요합니다.")
    return int(value) if integer else value


def _offline_environment():
    cache = Path(os.environ.get('TAKE_DATA_DIR',str(ROOT))) / 'cache'
    os.environ["HF_HUB_CACHE"] = str(cache / "huggingface")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["DO_NOT_TRACK"] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    os.environ["MPLCONFIGDIR"] = str(cache / "matplotlib")


def _manifest():
    path = MODEL_ROOT / "model_manifest.json"
    if not path.is_file():
        raise RuntimeError("Seed-VC 모델 다운로드가 아직 완료되지 않았습니다.")
    return json.loads(path.read_text(encoding="utf-8"))["repositories"]


def _asset(repositories, repo, filename):
    record = repositories[repo]["files"][filename]
    path = Path(record["path"])
    if not path.is_absolute():
        path = ROOT/path
    if not path.is_file() or path.stat().st_size != record["bytes"]:
        raise RuntimeError(f"Seed-VC 모델 파일을 확인해 주세요: {repo}/{filename}")
    return str(path)


def _load_model(device, repositories):
    """Resolve every pretrained dependency to a downloaded local snapshot."""
    if str(VENDOR) not in sys.path:
        sys.path.insert(0, str(VENDOR))
    import torch
    import yaml
    from hydra.utils import instantiate
    from omegaconf import DictConfig
    import hf_utils

    def local_checkpoint(repo_id, model_filename="pytorch_model.bin", config_filename=None):
        weight = _asset(repositories, repo_id, model_filename)
        return (weight, _asset(repositories, repo_id, config_filename)) if config_filename else weight

    # Upstream passes a hard-coded cache directory to this helper. Resolve its
    # dependencies from our pinned manifest instead, with no network fallback.
    hf_utils.load_custom_model_from_hf = local_checkpoint
    config = yaml.safe_load((VENDOR / "configs" / "v2" / "vc_wrapper.yaml").read_text(encoding="utf-8"))
    whisper_dir = str(Path(_asset(repositories, "openai/whisper-small", "tokenizer_config.json")).parent)
    hubert_dir = str(Path(_asset(repositories, "facebook/hubert-large-ll60k", "config.json")).parent)
    for name in ("content_extractor_narrow", "content_extractor_wide"):
        config[name]["tokenizer_name"] = whisper_dir
        config[name]["ssl_model_name"] = hubert_dir
    config["vocoder"]["pretrained_model_name_or_path"] = str(Path(_asset(repositories, "nvidia/bigvgan_v2_22khz_80band_256x", "config.json")).parent)
    config["vocoder"]["use_cuda_kernel"] = False
    model = instantiate(DictConfig(config))
    model.load_checkpoints(
        ar_checkpoint_path=_asset(repositories, "Plachta/Seed-VC", "v2/ar_base.pth"),
        cfm_checkpoint_path=_asset(repositories, "Plachta/Seed-VC", "v2/cfm_small.pth"),
    )
    model.to(device).eval()
    model.setup_ar_caches(max_batch_size=1, max_seq_len=4096, dtype=torch.float16 if device.type == "cuda" else torch.float32, device=device)
    return model


def run(request: dict, jobdir) -> dict:
    _offline_environment()
    import numpy as np
    import soundfile as sf
    import torch

    source = Path(request.get("source_path", "")).expanduser().resolve()
    reference = Path(request.get("reference_path", "")).expanduser().resolve()
    if not source.is_file() or not reference.is_file():
        raise ValueError("원본 대사 녹음과 참조 목소리 파일을 모두 지정해 주세요.")
    source_info, reference_info = sf.info(source), sf.info(reference)
    if not 0.3 <= source_info.duration <= 120:
        raise ValueError("원본 대사는 0.3초 이상, 120초 이하로 입력해 주세요.")
    if not 1 <= reference_info.duration <= 120:
        raise ValueError("참조 음성은 1초 이상, 120초 이하로 입력해 주세요. 앞부분 최대 25초를 사용합니다.")
    output_dir = Path(jobdir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    style = _boolean(request.get("convert_style", False))
    settings = {
        "convert_style": style,
        "length_adjust": _number(request, "length_adjust", 1.0, 0.5, 2.0) if style else 1.0,
        "diffusion_steps": _number(request, "diffusion_steps", 30, 4, 100, integer=True),
        "intelligibility_cfg_rate": _number(request, "intelligibility_cfg_rate", 0.7, 0, 1.5),
        "similarity_cfg_rate": _number(request, "similarity_cfg_rate", 0.7, 0, 1.5),
        "top_p": _number(request, "top_p", 0.9, 0.1, 1),
        "temperature": _number(request, "temperature", 1.0, 0.1, 1.5),
        "repetition_penalty": _number(request, "repetition_penalty", 1.0, 1, 2),
        "seed": _number(request, "seed", 18802026, 0, 2147483647, integer=True),
        "reference_seconds_used": min(reference_info.duration, 25.0),
        "source_seconds": source_info.duration,
        "source_commit": SOURCE_COMMIT,
        "sample_rate": 22050,
    }
    use_cpu = _boolean(request.get("use_cpu", False))
    if not use_cpu and not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU를 사용할 수 없습니다. GPU 드라이버와 전용 실행 환경을 확인해 주세요.")
    device = torch.device("cpu" if use_cpu else "cuda")
    torch.manual_seed(settings["seed"])
    np.random.seed(settings["seed"])
    if device.type == "cuda":
        torch.cuda.manual_seed_all(settings["seed"])
        torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter()
    model = None
    try:
        model = _load_model(device, _manifest())
        result = None
        for _, full_audio in model.convert_voice_with_streaming(
            source_audio_path=str(source), target_audio_path=str(reference),
            diffusion_steps=settings["diffusion_steps"], length_adjust=settings["length_adjust"],
            intelligebility_cfg_rate=settings["intelligibility_cfg_rate"],
            similarity_cfg_rate=settings["similarity_cfg_rate"], top_p=settings["top_p"],
            temperature=settings["temperature"], repetition_penalty=settings["repetition_penalty"],
            convert_style=style, anonymization_only=False, device=device,
            dtype=torch.float16 if device.type == "cuda" else torch.float32, stream_output=False,
        ):
            if full_audio is not None:
                result = full_audio
        if result is None:
            raise RuntimeError("음성 변환 결과가 생성되지 않았습니다.")
        sample_rate, waveform = result
        waveform = np.asarray(waveform, dtype=np.float32).squeeze()
        if waveform.ndim != 1 or not waveform.size or not np.isfinite(waveform).all():
            raise RuntimeError("생성된 음성 데이터가 올바르지 않습니다.")
        output = output_dir / "output.wav"
        # Float WAV preserves the generated waveform without lossy compression.
        sf.write(output, waveform, sample_rate, subtype="FLOAT")
        report = {
            "audio_path": str(output), "engine": "Seed-VC v2",
            "duration": len(waveform) / sample_rate,
            "settings": settings, "elapsed_seconds": time.perf_counter() - started,
            "peak_gpu_gb": torch.cuda.max_memory_allocated() / (1024 ** 3) if device.type == "cuda" else 0,
        }
        (output_dir / "seed_vc_result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report
    finally:
        del model
        gc.collect()
        if device.type == "cuda":
            torch.cuda.empty_cache()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("request_json")
    parser.add_argument("jobdir")
    args = parser.parse_args()
    result = run(json.loads(Path(args.request_json).read_text(encoding="utf-8")), args.jobdir)
    print(json.dumps(result, ensure_ascii=False))
