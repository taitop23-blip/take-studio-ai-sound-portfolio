"""One inference process per job: process exit releases GPU memory."""
import json, os, sys, time, traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
cache = Path(os.environ.get('TAKE_DATA_DIR',str(ROOT)))/'cache'/'huggingface'
os.environ.update(HF_HOME=str(cache), HF_HUB_OFFLINE='1',
    TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1', DO_NOT_TRACK='1',
    TOKENIZERS_PARALLELISM='false', PYTHONUTF8='1')

def main():
    job = Path(sys.argv[1]).resolve()
    request = json.loads((job/'request.json').read_text(encoding='utf-8'))
    start = time.perf_counter()
    try:
        if request['mode'] == 'tts':
            if request.get('tts_engine')=='voxcpm2':
                from engines.voxcpm2 import run
            else:
                from engines.higgs import run
        elif request['mode'] == 'convert':
            from engines.seed_vc import run
        elif request['mode'] == 'transcribe':
            from engines.transcribe import run
        elif request['mode'] == 'reply':
            from engines.qwen_chat import run
        else:
            from engines.qwen_audio import run
        result = run(request, job)
        from audio_export import export_audio
        result = export_audio(result)
        result['elapsed_seconds'] = round(time.perf_counter()-start, 2)
        (job/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print('작업 완료', flush=True)
    except Exception as exc:
        traceback.print_exc()
        (job/'error.json').write_text(json.dumps({'error':str(exc)}, ensure_ascii=False), encoding='utf-8')
        sys.exit(1)

if __name__ == '__main__':
    main()
