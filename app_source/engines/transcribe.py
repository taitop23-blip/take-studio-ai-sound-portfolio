"""Offline speech recognition on CPU, leaving GPU memory for speech generation."""
from pathlib import Path
import time
ROOT=Path(__file__).resolve().parents[1]

def run(request,jobdir):
    from faster_whisper import WhisperModel
    print('Whisper로 말씀하신 내용을 인식하고 있습니다.',flush=True)
    started=time.perf_counter()
    model=WhisperModel(str(ROOT/'models'/'whisper-turbo'),device='cpu',compute_type='int8',
                       cpu_threads=6,num_workers=1,local_files_only=True)
    language='ko' if request.get('language')=='Korean' else 'en'
    segments,info=model.transcribe(request['source_path'],language=language,task='transcribe',
        beam_size=5,temperature=0.0,condition_on_previous_text=False,vad_filter=False)
    segments=list(segments)
    usable=[s for s in segments if not(s.no_speech_prob>.6 and s.avg_logprob<-1)]
    transcript=' '.join(s.text.strip() for s in usable).strip()
    if not transcript:
        raise RuntimeError('말소리를 인식하지 못했습니다. 마이크 음량과 녹음을 확인해 주세요.')
    return {'transcript':transcript,'engine':'Whisper large-v3-turbo',
        'settings':{'language':language,'precision':'CPU int8','beam_size':5,'offline':True,
            'vad_filter':False,'seconds':round(time.perf_counter()-started,2)}}
