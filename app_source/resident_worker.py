"""Preload TTS, then serve serial jobs until stdin closes or the parent exits."""
import json, os, sys, threading, time, traceback, importlib
from pathlib import Path
import worker  # Configures the offline environment before importing any model.

state_path = Path(sys.argv[1])
parent_pid = int(sys.argv[2])

def state(status, message):
    temp = state_path.with_suffix('.tmp')
    temp.write_text(json.dumps({'status':status,'message':message,'pid':os.getpid()},ensure_ascii=False),encoding='utf-8')
    temp.replace(state_path)

def watch_parent():
    import psutil
    parent = psutil.Process(parent_pid)
    created = parent.create_time()
    while True:
        time.sleep(2)
        try:
            if not parent.is_running() or parent.create_time() != created:
                os._exit(0)
        except psutil.Error:
            os._exit(0)

def main():
    threading.Thread(target=watch_parent,daemon=True).start()
    try:
        state('loading','음성 엔진을 시작합니다.')
        selected=os.environ.get('TAKE_TTS_ENGINE','higgs')
        if selected not in ('higgs','voxcpm2'): raise ValueError('지원하지 않는 음성 모델입니다.')
        engine=importlib.import_module('engines.'+selected)
        original_progress = engine._progress
        def progress(message):
            original_progress(message)
            state('loading',message)
        engine._progress = progress
        engine.warmup()
        engine._progress = original_progress
        state('ready','대사 생성 모델이 준비됐습니다.')
    except Exception as exc:
        traceback.print_exc()
        state('error',str(exc))
        return
    for line in sys.stdin:
        job = None
        try:
            job = Path(json.loads(line)['folder']).resolve()
            request = json.loads((job/'request.json').read_text(encoding='utf-8'))
            state('working','대사를 생성하고 있습니다.')
            from audio_export import export_audio
            result = export_audio(engine.run(request,job))
            result.setdefault('settings',{})['resident_model'] = True
            (job/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        except Exception as exc:
            traceback.print_exc()
            if job is not None:
                (job/'error.json').write_text(json.dumps({'error':str(exc)},ensure_ascii=False),encoding='utf-8')
        finally:
            state('ready','대사 생성 모델이 준비됐습니다.')

if __name__ == '__main__':
    main()
