"""Offline Higgs TTS 3 adapter, with NF4 language model and CPU audio codec.

Upstream inference port (unchanged checkpoint weights):
https://huggingface.co/multimodalart/higgs-audio-v3-tts-4b-transformers
Pinned revision: 30f01593ee6a12efa586c92455afe4b76e45095d
Codec: bosonai/higgs-audio-v2-tokenizer
Pinned revision: 403fbacf2f60caaa102f893fdfabb694619b2417

Importing this module does not load torch or initialize a GPU. The application
runs ``run`` in its isolated worker process, one model job at a time.
"""

from __future__ import annotations

import math
import os
import random
import time
from pathlib import Path
from types import MethodType
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "models" / "higgs-tts-3"
CODEC_PATH = ROOT / "models" / "higgs-tokenizer"
MODEL_REVISION = "30f01593ee6a12efa586c92455afe4b76e45095d"
CODEC_REVISION = "403fbacf2f60caaa102f893fdfabb694619b2417"
_loaded = None

EMOTIONS = {
    "normal": "",
    "determination": "<|emotion:determination|>",
    "anger": "<|emotion:anger|>",
    "fear": "<|emotion:fear|>",
    "sadness": "<|emotion:sadness|>",
    "relief": "<|emotion:relief|>",
    "enthusiasm": "<|emotion:enthusiasm|>",
}
DELIVERIES = {
    "normal": "",
    "whispering": "<|style:whispering|>",
    "shouting": "<|style:shouting|>",
}
SPEEDS = {
    "normal": "",
    "slow": "<|prosody:speed_slow|>",
    "fast": "<|prosody:speed_fast|>",
}


def _progress(message: str) -> None:
    print(message, flush=True)


def _choice(request: dict[str, Any], key: str, choices: dict[str, str]) -> str:
    value = request.get(key, "normal")
    if not isinstance(value, str) or value not in choices:
        raise ValueError(f"{key} 설정이 올바르지 않습니다.")
    return value


def prepare_request(request: dict[str, Any]) -> dict[str, Any]:
    """Validate UI values and build only the model's documented control tags."""
    dialogue = request.get("dialogue", "")
    if not isinstance(dialogue, str) or not dialogue.strip():
        raise ValueError("생성할 대사를 입력해 주세요.")
    dialogue = dialogue.strip()
    if len(dialogue) > 2000:
        raise ValueError("한 번에 2,000자 이내의 대사를 생성할 수 있습니다.")
    if "<|" in dialogue or "|>" in dialogue:
        raise ValueError("대사에는 읽을 문장만 입력하고 연기는 별도 설정에서 선택해 주세요.")

    emotion = _choice(request, "emotion", EMOTIONS)
    delivery = _choice(request, "delivery", DELIVERIES)
    speed = _choice(request, "speed", SPEEDS)
    try:
        seed = int(request.get("seed", 42))
        max_new_tokens = int(request.get("max_new_tokens", 512))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("시드와 생성 길이는 정수로 입력해 주세요.") from exc
    if not 0 <= seed <= 2**32 - 1:
        raise ValueError("시드는 0부터 4,294,967,295 사이여야 합니다.")
    if not 64 <= max_new_tokens <= 2048:
        raise ValueError("생성 길이는 64부터 2,048 사이여야 합니다.")

    reference_path = request.get("reference_path")
    if reference_path:
        reference_path = Path(reference_path).expanduser().resolve()
        if not reference_path.is_file():
            raise ValueError("참조 음성 파일을 찾을 수 없습니다.")
    reference_text = request.get("reference_text") or ""
    if not isinstance(reference_text, str):
        raise ValueError("참조 음성의 대사는 문자열이어야 합니다.")
    reference_text = reference_text.strip()
    if len(reference_text) > 2000:
        raise ValueError("참조 음성의 대사는 2,000자 이내로 입력해 주세요.")

    return {
        "dialogue": dialogue,
        "tagged_text": EMOTIONS[emotion] + DELIVERIES[delivery] + SPEEDS[speed] + dialogue,
        "emotion": emotion,
        "delivery": delivery,
        "speed": speed,
        "seed": seed,
        "max_new_tokens": max_new_tokens,
        "reference_path": reference_path,
        "reference_text": reference_text,
    }


def _attach_cpu_codec(model: Any, codec: Any, torch: Any, torchaudio: Any) -> None:
    """Keep codec operations on CPU while preserving upstream prompt/generation.

    The upstream adapter moves codec tensors to ``self.device``. Patching these
    three I/O methods avoids moving the codec or its larger activations to CUDA.
    The autoregressive model, delay pattern and sampler are left unchanged.
    """

    def get_audio_codec(self: Any) -> Any:
        return codec

    @torch.no_grad()
    def encode_reference(self: Any, waveform: Any, sample_rate: int) -> Any:
        wav = waveform.detach().to(device="cpu", dtype=torch.float32)
        if wav.ndim == 2:
            wav = wav.mean(dim=0)
        if wav.ndim != 1:
            raise ValueError("참조 음성의 오디오 형식이 올바르지 않습니다.")
        if sample_rate != self.config.sample_rate:
            wav = torchaudio.functional.resample(wav, sample_rate, self.config.sample_rate)
        if wav.numel() < self.config.sample_rate:
            wav = torch.nn.functional.pad(wav, (0, self.config.sample_rate - wav.numel()))
        wav = wav.unsqueeze(0).unsqueeze(0).contiguous()
        codes = codec.encode(wav).audio_codes
        return codes.squeeze(0).transpose(0, 1).to(device="cpu", dtype=torch.long)

    @torch.no_grad()
    def decode_codes(self: Any, codes_tn: Any) -> Any:
        codec_vocab = self.codebook_vocab_size - 2
        codes_tn = codes_tn.to(device="cpu", dtype=torch.long)
        codes_tn = torch.where(codes_tn >= codec_vocab, torch.zeros_like(codes_tn), codes_tn)
        codes_bnt = codes_tn.transpose(0, 1).unsqueeze(0).contiguous()
        audio = codec.decode(codes_bnt).audio_values
        return audio.squeeze(0).squeeze(0).detach().cpu().float()

    model.get_audio_codec = MethodType(get_audio_codec, model)
    model._encode_reference = MethodType(encode_reference, model)
    model._decode_codes = MethodType(decode_codes, model)


def warmup():
    """Load once in the dedicated resident TTS process."""
    global _loaded
    if _loaded is not None:
        return _loaded
    import torch, torchaudio
    from transformers import AutoModel, AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    if not torch.cuda.is_available():
        raise RuntimeError('NVIDIA GPU를 사용할 수 없습니다. 드라이버를 확인해 주세요.')
    torch.set_num_threads(max(1, min(8, os.cpu_count() or 1)))
    _progress('Higgs TTS 모델을 GPU에 불러오는 중입니다.')
    tokenizer = AutoTokenizer.from_pretrained(str(MODEL_PATH), local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(str(MODEL_PATH),trust_remote_code=True,
        local_files_only=True,dtype=torch.bfloat16,device_map={'':'cuda:0'},attn_implementation='sdpa',
        quantization_config=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',
            bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=torch.bfloat16)).eval()
    model.config.audio_tokenizer_id = str(CODEC_PATH)
    _progress('음성 코덱을 준비하는 중입니다.')
    codec = AutoModel.from_pretrained(str(CODEC_PATH),trust_remote_code=False,local_files_only=True,
                                    dtype=torch.float32).to('cpu').eval()
    for parameter in codec.parameters():
        parameter.requires_grad_(False)
    _attach_cpu_codec(model, codec, torch, torchaudio)
    _loaded = tokenizer, model, codec
    return _loaded


def run(request: dict[str, Any], jobdir: str | Path) -> dict[str, Any]:
    """Generate one local TTS result. No model or audio network access occurs."""
    spec = prepare_request(request)
    for path in (MODEL_PATH, CODEC_PATH):
        if not (path / "config.json").is_file() or not (path / "model.safetensors").is_file():
            raise RuntimeError(f"음성 모델 설치가 완료되지 않았습니다: {path.name}")

    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    _progress("음성 합성 엔진을 준비하고 있습니다.")
    import numpy as np
    import soundfile as sf
    import torch
    import torchaudio
    from transformers import AutoModel, AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    if not torch.cuda.is_available():
        raise RuntimeError("Higgs 4bit 음성 합성에는 CUDA를 지원하는 NVIDIA GPU가 필요합니다.")
    torch.set_num_threads(max(1, min(8, os.cpu_count() or 1)))
    random.seed(spec["seed"])
    np.random.seed(spec["seed"])
    torch.manual_seed(spec["seed"])
    torch.cuda.manual_seed_all(spec["seed"])
    torch.cuda.reset_peak_memory_stats()

    reference_audio = None
    reference_sr = None
    if spec["reference_path"]:
        info = sf.info(str(spec["reference_path"]))
        if not 0.5 <= info.duration <= 30.0:
            raise ValueError("참조 음성은 0.5초 이상 30초 이하로 준비해 주세요. 3~15초를 권장합니다.")
        data, reference_sr = sf.read(str(spec["reference_path"]), dtype="float32", always_2d=True)
        mono = data.mean(axis=1)
        if not np.isfinite(mono).all() or float(np.max(np.abs(mono))) < 1e-5:
            raise ValueError("참조 음성에 유효한 소리가 있는지 확인해 주세요.")
        reference_audio = torch.from_numpy(np.ascontiguousarray(mono))

    tokenizer, model, codec = warmup()

    kwargs = {
        "max_new_tokens": spec["max_new_tokens"],
        "temperature": 0.7,
        "top_p": 0.95,
        "top_k": 50,
    }
    if reference_audio is not None:
        kwargs.update(reference_audio=reference_audio, reference_sample_rate=reference_sr)
        if spec["reference_text"]:
            kwargs["reference_text"] = spec["reference_text"]

    _progress("대사를 생성하고 있습니다. 첫 생성은 잠시 시간이 걸릴 수 있습니다.")
    started = time.perf_counter()
    with torch.inference_mode():
        waveform = model.generate_speech(spec["tagged_text"], tokenizer, **kwargs)
    elapsed = time.perf_counter() - started
    audio = waveform.detach().cpu().float().numpy().reshape(-1)
    sample_rate = int(model.config.sample_rate)
    if audio.size == 0 or not np.isfinite(audio).all():
        raise RuntimeError("유효한 음성이 생성되지 않았습니다. 대사를 짧게 나누어 다시 시도해 주세요.")
    peak = float(np.max(np.abs(audio)))
    if not math.isfinite(peak) or peak < 1e-6:
        raise RuntimeError("생성 결과가 무음입니다. 시드를 바꾸거나 참조 음성을 확인해 주세요.")
    # Float WAV preserves the model output; do not normalize away A/B differences.
    output_dir = Path(jobdir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "output.wav"
    sf.write(str(output_path), audio, sample_rate, subtype="FLOAT")

    duration = audio.size / sample_rate
    settings = {
        "emotion": spec["emotion"],
        "delivery": spec["delivery"],
        "speed": spec["speed"],
        "seed": spec["seed"],
        "max_new_tokens": spec["max_new_tokens"],
        "model_input": spec["tagged_text"],
        "temperature": 0.7,
        "top_p": 0.95,
        "top_k": 50,
        "precision": "NF4 / BF16 compute",
        "codec": "CPU FP32",
        "sample_rate": sample_rate,
        "reference_used": reference_audio is not None,
        "model_revision": MODEL_REVISION,
        "codec_revision": CODEC_REVISION,
        "generation_seconds": round(elapsed, 3),
        "peak_dbfs": round(20 * math.log10(peak), 3),
        "peak_vram_gib": round(torch.cuda.max_memory_allocated() / 2**30, 3),
        "length_limit_reached": duration >= max(0, (spec["max_new_tokens"] - 16) / 25),
    }
    _progress(f"생성이 완료되었습니다. {duration:.1f}초 분량을 저장했습니다.")
    return {
        "audio_path": str(output_path),
        "text": spec["dialogue"],
        "engine": "Higgs TTS 3 · 4bit",
        "duration": round(duration, 3),
        "settings": settings,
    }
