"""Own the single GPU-resident TTS engine and expose observable readiness."""
import json, os, subprocess, threading, time, uuid
from pathlib import Path

class ResidentEngine:
    def __init__(self, root, data, python):
        self.root, self.data, self.python = Path(root), Path(data), Path(python)
        self.process = None
        self.state_file = None
        self.log = None
        self.guard = threading.RLock()
        self.engine = 'higgs'

    def snapshot(self):
        if self.state_file:
            try:
                result = json.loads(self.state_file.read_text(encoding='utf-8'))
                if self.process and self.process.poll() is None:
                    return result
                if result.get('status') == 'error': return result
                if self.process:
                    return {'status':'error','message':'음성 엔진이 종료됐습니다. 모델 다시 준비를 눌러 재시작해 주세요.'}
            except (OSError,ValueError): pass
        return {'status':'stopped','message':'대사 생성 시 모델을 준비합니다.'}

    def start(self, engine=None):
        with self.guard:
            selected = engine or self.engine
            if selected not in ('higgs','voxcpm2'): raise ValueError('지원하지 않는 음성 모델입니다.')
            if self.process and self.process.poll() is None:
                if selected == self.engine: return
                self.stop()
            self.engine = selected
            folder = self.data/'runtime'/uuid.uuid4().hex
            folder.mkdir(parents=True,exist_ok=True)
            self.state_file = folder/'state.json'
            self.state_file.write_text(json.dumps({'status':'loading','message':'음성 엔진을 시작합니다.'},ensure_ascii=False),encoding='utf-8')
            if self.log: self.log.close()
            self.log = (folder/'engine.log').open('w',encoding='utf-8')
            env=dict(os.environ,PYTHONUTF8='1',PYTHONUNBUFFERED='1')
            env['TAKE_TTS_ENGINE']=selected
            env.pop('PYTHONHOME',None)
            env.pop('PYTHONPATH',None)
            self.process=subprocess.Popen([str(self.python),'-u',str(self.root/'resident_worker.py'),str(self.state_file),str(os.getpid())],
                cwd=self.root,env=env,stdin=subprocess.PIPE,stdout=self.log,stderr=subprocess.STDOUT,
                text=True,encoding='utf-8',creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)

    def stop(self):
        with self.guard:
            if self.process and self.process.poll() is None:
                subprocess.run(['taskkill','/PID',str(self.process.pid),'/T','/F'],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
                self.process.wait(timeout=20)
            self.process=None
            self.state_file=None
            if self.log: self.log.close(); self.log=None

    def run(self, folder, cancelled):
        request=json.loads((folder/'request.json').read_text(encoding='utf-8'))
        self.start(request.get('tts_engine','higgs'))
        started=time.monotonic()
        while True:
            if cancelled(): self.stop(); return None
            status=self.snapshot()
            if status['status']=='ready': break
            if status['status'] in ('error','stopped'): raise RuntimeError(status['message'])
            if time.monotonic()-started>600: self.stop(); raise RuntimeError('모델 준비 시간이 초과됐습니다. GPU 메모리를 확인하고 다시 시도해 주세요.')
            time.sleep(.25)
        self.process.stdin.write(json.dumps({'folder':str(folder)})+'\n')
        self.process.stdin.flush()
        while True:
            if cancelled(): self.stop(); return None
            if (folder/'error.json').exists():
                raise RuntimeError(json.loads((folder/'error.json').read_text(encoding='utf-8'))['error'])
            if (folder/'result.json').exists():
                try: return json.loads((folder/'result.json').read_text(encoding='utf-8'))
                except ValueError: pass
            if self.process.poll() is not None: raise RuntimeError('음성 엔진이 종료됐습니다. 다시 생성하면 재시작합니다.')
            if time.monotonic()-started>1800: self.stop(); raise RuntimeError('생성 시간이 초과됐습니다. 대사를 나누어 다시 시도해 주세요.')
            time.sleep(.25)
