"""Pinned VoxCPM2 local inference. The app keeps dialogue and direction separate."""
import math, os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REVISION='32279effe8c19989596f05d353d1447f51d9e915'
_loaded=None

def _progress(message):
    print(message,flush=True)

def prepare_request(request):
    dialogue=request.get('dialogue','').strip()
    if not dialogue or len(dialogue)>1500:
        raise ValueError('1~1,500자의 읽을 대사를 입력해 주세요.')
    if '<|' in dialogue or '|>' in dialogue:
        raise ValueError('대사에는 읽을 문장만 입력해 주세요.')
    # VoxCPM2 documents a leading parenthesized description as its style channel.
    # Free-form analysis instructions are never sent to speech generation.
    descriptions=[]
    emotion={'determination':'firm and determined','anger':'angry','fear':'frightened',
             'sadness':'sad','relief':'relieved','enthusiasm':'enthusiastic'}.get(request.get('emotion'))
    delivery={'whispering':'whispering','shouting':'shouting'}.get(request.get('delivery'))
    speed={'slow':'speaking slowly','fast':'speaking quickly'}.get(request.get('speed'))
    descriptions.extend(v for v in [emotion,delivery,speed] if v)
    # Continuation concatenates reference text before target text internally. A style
    # prefix there becomes mid-sentence content and can be spoken aloud.
    continuation=bool(request.get('reference_path') and request.get('reference_text','').strip() and not descriptions)
    direction=', '.join(descriptions)
    return {'dialogue':dialogue,'direction':direction,'continuation':continuation,
            'model_text':f'({direction}){dialogue}' if direction else dialogue}

def warmup():
    global _loaded
    if _loaded is not None: return _loaded
    import torch
    from voxcpm import VoxCPM
    if not torch.cuda.is_available(): raise RuntimeError('CUDA 지원 NVIDIA GPU가 필요합니다.')
    free,_=torch.cuda.mem_get_info()
    if free<7*1024**3:
        raise RuntimeError('VoxCPM2는 약 8GB의 여유 GPU 메모리를 권장합니다. 다른 GPU 작업을 멈춘 뒤 모델을 다시 준비해 주세요.')
    _progress('VoxCPM2 음성 모델을 GPU에 불러오는 중입니다.')
    _loaded=VoxCPM.from_pretrained(str(ROOT/'models'/'voxcpm2'),load_denoiser=False,
                                  local_files_only=True,optimize=False,device='cuda')
    return _loaded

def run(request,jobdir):
    import numpy as np
    import torch
    import soundfile as sf
    prepared=prepare_request(request)
    model=warmup()
    seed=int(request.get('seed',42))
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    np.random.seed(seed)
    max_frames=max(32,math.ceil(int(request.get('max_new_tokens',512))/4))
    reference=request.get('reference_path') or None
    transcript=request.get('reference_text','').strip()
    kwargs={}
    if reference:
        kwargs['reference_wav_path']=reference
        if prepared['continuation']: kwargs.update(prompt_wav_path=reference,prompt_text=transcript)
    _progress('대사를 생성하고 있습니다.')
    with torch.inference_mode():
        wav=model.generate(text=prepared['model_text'],cfg_value=2.0,inference_timesteps=10,
            max_len=max_frames,normalize=False,denoise=False,retry_badcase=True,retry_badcase_max_times=1,**kwargs)
    audio=np.asarray(wav,dtype=np.float32).reshape(-1)
    rate=int(model.tts_model.sample_rate)
    if len(audio)<rate*.2 or not np.isfinite(audio).all():
        raise RuntimeError('정상적인 음성을 생성하지 못했습니다. 문장을 나누거나 다시 생성해 주세요.')
    out=Path(jobdir)/'output.wav'
    sf.write(out,audio,rate,subtype='FLOAT')
    return {'audio_path':str(out.resolve()),'duration':len(audio)/rate,'text':prepared['dialogue'],
            'engine':'VoxCPM2 · 2B · 48kHz','settings':{'model_revision':REVISION,'precision':'bfloat16',
            'style_direction':prepared['direction'],'reference_used':bool(reference),
            'reference_transcript_used':prepared['continuation'],'seed':seed,
            'max_audio_frames':max_frames,'cfg_value':2.0,'inference_timesteps':10,
            'length_limit_reached':len(audio)/rate>=max_frames/6.25-.4}}
