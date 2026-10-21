"""Take Studio: loopback-only audio workbench with a single GPU queue."""
import json, os, queue, re, subprocess, sys, threading, time, uuid, secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('TAKE_DATA_DIR', str(ROOT/'data')))
PORT = int(os.environ.get('TAKE_PORT','38765'))
SESSION_TOKEN = os.environ.get('TAKE_SESSION_TOKEN','')
VERSION = '1.0.0-rc1'
UPLOADS = DATA/'uploads'
JOBS = DATA/'jobs'
VOICE_PRESETS = ROOT/'models'/'voice-presets'
for directory in (UPLOADS, JOBS):
    directory.mkdir(parents=True, exist_ok=True)
HIDDEN = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
ID = re.compile(r'^[a-f0-9]{32}$')
pending = queue.Queue()
lock = threading.RLock()
records = {}
processes = {}
cancelled = set()

def engine_python(convert=False):
    bundled = ROOT.parent/'runtime'/('python-vc' if convert else 'python')/'python.exe'
    return bundled if bundled.is_file() else ROOT/('.venv-vc' if convert else '.venv')/'Scripts'/'python.exe'

from resident_engine import ResidentEngine
resident = ResidentEngine(ROOT, DATA, engine_python())
try:
    saved_engine=json.loads((DATA/'preferences.json').read_text(encoding='utf-8')).get('tts_engine','higgs')
    if saved_engine in ('higgs','voxcpm2'): resident.engine=saved_engine
except (OSError,ValueError): pass

def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))

def persist(record):
    path = JOBS/record['id']/'job.json'
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)

def update(jobid, **values):
    with lock:
        records[jobid].update(values)
        persist(records[jobid])

def model_status():
    manifest_path = ROOT/'models'/'manifest.json'
    try:
        manifest = read_json(manifest_path)
    except (OSError, ValueError):
        manifest = {}
    def complete(name):
        folder = ROOT/'models'/name
        if name not in manifest or not (folder/'config.json').exists():
            return False
        single = folder/'model.safetensors'
        if single.exists() and single.stat().st_size > 1000000:
            return True
        index = folder/'model.safetensors.index.json'
        try:
            shards = set(read_json(index)['weight_map'].values())
            return bool(shards) and all((folder/s).is_file() and (folder/s).stat().st_size > 1000000 for s in shards)
        except (OSError,ValueError,KeyError):
            return False
    vc_ready = (ROOT/'models'/'seed-vc'/'ready.json').exists()
    chat_ready = all((ROOT/'models'/name/'ready.json').exists() for name in ('qwen-chat','whisper-turbo'))
    higgs_ready=all(complete(k) for k in ('higgs-tts-3','higgs-tokenizer'))
    vox_dir=ROOT/'models/voxcpm2'
    vox_ready=(vox_dir/'ready.json').is_file() and (vox_dir/'config.json').is_file() and all(
        (vox_dir/name).is_file() and (vox_dir/name).stat().st_size==size
        for name,size in [('model.safetensors',4580080592),('audiovae.pth',376951122)])
    return [
        {'id':'tts','name':'대사 합성 · Higgs / VoxCPM2' if vox_ready else 'Higgs TTS 3 · 4B','ready':higgs_ready or vox_ready,
         'higgs_ready':higgs_ready,'voxcpm2_ready':vox_ready,'detail':'감정·발성 설정과 참조 목소리'},
        {'id':'convert','name':'Seed-VC v2','ready':vc_ready,'detail':'원본 대사·연기를 유지하는 음색 변환'},
        {'id':'chat','name':'음성 대화·분석 · Qwen 7B','ready':complete('qwen2-audio') and chat_ready,
         'detail':'Whisper 인식 / Qwen2.5 대화 / Qwen2-Audio 분석'},
    ]

def tts_options():
    info=model_status()[0]
    return [{'id':'higgs','name':'Higgs TTS 3 · 4B / 24kHz','ready':info.get('higgs_ready',info['ready'])},
            {'id':'voxcpm2','name':'VoxCPM2 · 2B / 48kHz · 비교용','ready':info.get('voxcpm2_ready',False)}]

def gpu_status():
    try:
        result = subprocess.run(['nvidia-smi','--query-gpu=name,memory.free,memory.total',
            '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=5, creationflags=HIDDEN)
        name, free, total = result.stdout.strip().splitlines()[0].split(',')
        return {'name':name.strip(),'free_mb':int(free),'total_mb':int(total)}
    except Exception:
        return {'name':'GPU 상태 확인 중','free_mb':None,'total_mb':None}

def upload_path(uploadid):
    if not uploadid or not ID.fullmatch(uploadid):
        raise HTTPException(400, '오디오 파일을 먼저 선택해 주세요.')
    path = UPLOADS/uploadid/'audio.wav'
    if not path.exists():
        raise HTTPException(404, '선택한 오디오 파일이 없습니다. 다시 업로드해 주세요.')
    return path

def preset_voices():
    """Only expose shipped, verified synthetic reference clips."""
    import hashlib
    try:
        entries = read_json(VOICE_PRESETS/'manifest.json')['voices']
    except (OSError, ValueError, KeyError, TypeError):
        return []
    voices = []
    for item in entries:
        if not isinstance(item, dict) or not re.fullmatch(r'[a-z0-9-]{1,40}', str(item.get('id',''))):
            continue
        filename = item['id'] + '.wav'
        if item.get('file') != filename:
            continue
        path = VOICE_PRESETS/filename
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item.get('sha256'):
            continue
        voices.append({key:item[key] for key in ('id','name','gender','description','language','text','duration')})
    return voices

def preset_voice(voice_id):
    if not voice_id or not re.fullmatch(r'[a-z0-9-]{1,40}', voice_id):
        raise HTTPException(400, '화자를 다시 선택해 주세요.')
    for voice in preset_voices():
        if voice['id'] == voice_id:
            return voice, VOICE_PRESETS/(voice_id+'.wav')
    raise HTTPException(404, '선택한 화자 음성을 찾을 수 없습니다.')

class JobRequest(BaseModel):
    mode: Literal['tts','convert','chat','analyze']
    tts_engine: Literal['higgs','voxcpm2'] = 'higgs'
    dialogue: str = Field(default='', max_length=1500)
    language: Literal['Korean','English'] = 'Korean'
    emotion: Literal['normal','determination','anger','fear','sadness','relief','enthusiasm'] = 'normal'
    delivery: Literal['normal','whispering','shouting'] = 'normal'
    speed: Literal['normal','slow','fast'] = 'normal'
    seed: int = Field(default=42, ge=0, le=2147483647)
    max_new_tokens: int = Field(default=512, ge=128, le=1536)
    source_id: str | None = None
    reference_id: str | None = None
    voice_id: str | None = None
    reference_text: str = Field(default='', max_length=2000)
    instruction: str = Field(default='', max_length=2000)
    read_response: bool = False
    history: list[dict] = Field(default_factory=list, max_length=16)
    convert_style: bool = False

def run_process(jobid, folder, request):
    folder.mkdir(parents=True, exist_ok=True)
    (folder/'request.json').write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding='utf-8')
    if jobid in cancelled: return None
    if request['mode'] == 'tts' and os.environ.get('TAKE_RESIDENT','1') != '0':
        return resident.run(folder, lambda: jobid in cancelled)
    resident.stop()
    python = engine_python(request['mode'] == 'convert')
    env = dict(os.environ, PYTHONUTF8='1', PYTHONUNBUFFERED='1', HF_HUB_OFFLINE='1',
               TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1', DO_NOT_TRACK='1')
    with (folder/'worker.log').open('w',encoding='utf-8') as output:
        with lock:
            if jobid in cancelled:
                return None
            process = subprocess.Popen([str(python),'-u',str(ROOT/'worker.py'),str(folder)],
                cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, env=env, creationflags=HIDDEN)
            processes[jobid] = process
        start = time.monotonic()
        while process.poll() is None:
            if jobid in cancelled or time.monotonic()-start > 1800:
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'], capture_output=True, creationflags=HIDDEN)
                process.wait(timeout=15)
                if jobid not in cancelled:
                    raise RuntimeError('30분 내에 작업이 끝나지 않았습니다. 짧은 대사로 다시 시도해 주세요.')
                return None
            time.sleep(.4)
        with lock:
            processes.pop(jobid, None)
        if jobid in cancelled:
            return None
        if process.returncode:
            errorfile = folder/'error.json'
            message = read_json(errorfile)['error'] if errorfile.exists() else '음성 엔진 실행에 실패했습니다. 작업 로그를 확인해 주세요.'
            if 'out of memory' in message.lower():
                message = 'GPU 메모리가 부족합니다. 다른 GPU 작업을 멈춘 뒤 다시 시도해 주세요.'
            raise RuntimeError(message)
    return read_json(folder/'result.json')

def worker_loop():
    while True:
        jobid, request = pending.get()
        try:
            if jobid in cancelled:
                continue
            update(jobid, status='running',stage='preparing',message='모델을 불러와 작업을 시작합니다.')
            folder = JOBS/jobid
            started = time.monotonic()
            if request['mode'] == 'chat':
                update(jobid,stage='listening',message='말씀하신 내용을 인식합니다.')
                recognized = run_process(jobid,folder/'transcription',dict(request,mode='transcribe'))
                if recognized is None:
                    result = None
                else:
                    update(jobid,stage='replying',message='인식한 내용에 대한 답변을 작성합니다.')
                    result = run_process(jobid,folder/'inference',dict(request,mode='reply',transcript=recognized['transcript']))
                    if result is not None:
                        result['transcript'] = recognized['transcript']
                        result['engine'] = recognized['engine']+' + '+result['engine']
                        result.setdefault('settings',{})['recognition'] = recognized.get('settings',{})
            elif request['mode'] == 'analyze':
                update(jobid,stage='analyzing',message='녹음의 말투와 소리를 분석합니다.')
                draft = run_process(jobid,folder/'analysis',dict(request,language='English'))
                if draft is None:
                    result = None
                else:
                    update(jobid,stage='replying',message='분석 결과를 선택한 언어로 정리합니다.')
                    result = run_process(jobid,folder/'inference',dict(request,mode='reply',analysis_draft=draft['text']))
                    if result is not None:
                        result['engine'] = draft['engine']+' + '+result['engine']
                        result.setdefault('settings',{})['analysis'] = draft.get('settings',{})
            else:
                result = run_process(jobid, folder/'inference', request)
            if result is None:
                update(jobid, status='cancelled',stage='cancelled',message='작업을 취소했습니다.')
                continue
            if request['mode'] in ('chat','analyze') and request['read_response']:
                update(jobid,stage='speaking',message='답변을 음성으로 만들고 있습니다.')
                ttsrequest = dict(request, mode='tts', dialogue=result['text'][:1500])
                if ttsrequest.get('voice_id'):
                    voice, path = preset_voice(ttsrequest['voice_id'])
                    ttsrequest['reference_path'] = str(path)
                    ttsrequest['reference_text'] = voice['text']
                try:
                    spoken = run_process(jobid, folder/'response', ttsrequest)
                    if spoken:
                        result['audio_path'] = spoken.get('audio_path')
                        result['raw_audio_path'] = spoken.get('raw_audio_path')
                        result['duration'] = spoken.get('duration')
                        result.setdefault('settings',{})['speech'] = spoken.get('settings',{})
                        result['settings']['export_format'] = spoken.get('settings',{}).get('export_format','')
                        result['engine'] += ' + '+spoken.get('engine','TTS')
                except Exception as exc:
                    result['warning'] = f'텍스트 답변은 완료했지만 음성 생성에 실패했습니다: {exc}'
            if jobid in cancelled:
                update(jobid,status='cancelled',stage='cancelled',message='작업을 취소했습니다.')
                continue
            audio_path = result.pop('audio_path',None)
            raw_audio_path = result.pop('raw_audio_path',None)
            if audio_path:
                audio = Path(audio_path).resolve()
                if not audio.is_relative_to(folder.resolve()):
                    raise RuntimeError('결과 오디오 경로가 잘못되었습니다.')
                result['audio_url'] = '/media/jobs/'+jobid+'/'+audio.relative_to(folder).as_posix()
            if raw_audio_path:
                raw_audio = Path(raw_audio_path).resolve()
                if raw_audio.is_relative_to(folder.resolve()):
                    result['raw_audio_url'] = '/media/jobs/'+jobid+'/'+raw_audio.relative_to(folder).as_posix()
            result['elapsed_seconds'] = round(time.monotonic()-started,2)
            result['settings_url'] = '/media/jobs/'+jobid+'/settings.json'
            settings = dict(request)
            for key in ('source_path','reference_path'):
                settings.pop(key,None)
            (folder/'settings.json').write_text(json.dumps({'request':settings,'result':result},ensure_ascii=False,indent=2),encoding='utf-8')
            update(jobid,status='completed',stage='completed',message='작업을 완료했습니다.',result=result)
        except Exception as exc:
            update(jobid,status='failed',stage='failed',message='작업을 완료하지 못했습니다.',error=str(exc))
        finally:
            processes.pop(jobid,None)
            pending.task_done()

@asynccontextmanager
async def lifespan(app):
    for path in JOBS.glob('*/job.json'):
        try:
            record = read_json(path)
            if record['status'] in ('running','queued'):
                record.update(status='failed',error='앱이 종료되어 작업이 중단됐습니다. 다시 실행해 주세요.')
                persist(record)
            records[record['id']] = record
        except (OSError, ValueError, KeyError):
            continue
    threading.Thread(target=worker_loop, daemon=True).start()
    if os.environ.get('TAKE_PRELOAD','1') == '1' and model_status()[0]['ready']:
        options={m['id']:m['ready'] for m in tts_options()}
        if not options.get(resident.engine):resident.engine=next(k for k,v in options.items() if v)
        resident.start()
    yield
    with lock:
        cancelled.update(processes)
    resident.stop()

app = FastAPI(title='Take Studio', lifespan=lifespan)

@app.middleware('http')
async def local_only(request: Request, call_next):
    from fastapi.responses import JSONResponse
    host = request.headers.get('host','').split(':')[0]
    origin = request.headers.get('origin')
    if host not in ('127.0.0.1','localhost','testserver'):
        return JSONResponse({'detail':'이 앱은 로컬 PC에서만 열 수 있습니다.'},403)
    if origin and origin != f'http://{request.headers.get("host")}' and origin != f'https://{request.headers.get("host")}':
        return JSONResponse({'detail':'앱 화면에서 다시 시도해 주세요.'},403)
    if SESSION_TOKEN and request.url.path.startswith(('/api/','/media/')):
        supplied = request.headers.get('x-take-token') or request.cookies.get('take_session','')
        if not secrets.compare_digest(supplied, SESSION_TOKEN):
            return JSONResponse({'detail':'Take Studio 실행 파일에서 앱을 열어 주세요.'},401)
    return await call_next(request)

@app.get('/api/status')
def status():
    with lock:
        busy = any(r['status'] in ('running','queued') for r in records.values())
    return {'app':'take-studio','version':VERSION,'busy':busy,'models':model_status(),'gpu':gpu_status(),
            'engine':resident.snapshot(),'desktop':bool(SESSION_TOKEN),
            'tts_engines':tts_options(),'selected_tts_engine':resident.engine,
            'voices':preset_voices()}

@app.get('/api/voices/{voice_id}/audio')
def voice_preview(voice_id: str):
    _, path = preset_voice(voice_id)
    return FileResponse(path, media_type='audio/wav')

class EngineSelection(BaseModel):
    tts_engine: Literal['higgs','voxcpm2']

@app.post('/api/engine/select')
def select_engine(body: EngineSelection):
    with lock:
        if any(r['status'] in ('running','queued') for r in records.values()):
            raise HTTPException(409,'현재 작업을 마친 뒤 모델을 바꿔 주세요.')
        if not next(m['ready'] for m in tts_options() if m['id']==body.tts_engine):
            raise HTTPException(409,'선택한 모델이 이 패키지에 준비되어 있지 않습니다.')
        resident.start(body.tts_engine)
        temp=DATA/'preferences.tmp'
        temp.write_text(json.dumps({'tts_engine':body.tts_engine}),encoding='utf-8')
        temp.replace(DATA/'preferences.json')
    return {'selected_tts_engine':body.tts_engine}

@app.post('/api/engine/retry')
def retry_engine():
    with lock:
        if any(r['status'] in ('running','queued') for r in records.values()):
            raise HTTPException(409,'진행 중인 작업이 끝난 뒤 다시 시도해 주세요.')
        resident.stop()
        resident.start()
    return {'started':True}

@app.post('/api/engine/release')
def release_engine():
    with lock:
        if any(r['status'] in ('running','queued') for r in records.values()):
            raise HTTPException(409,'진행 중인 작업이 끝난 뒤 메모리를 해제할 수 있습니다.')
        resident.stop()
    return {'released':True}

@app.post('/api/uploads')
def upload(file: UploadFile = File(...)):
    import imageio_ffmpeg
    import soundfile as sf
    suffix = Path(file.filename or '').suffix.lower()
    if suffix not in ('.wav','.mp3','.flac','.ogg','.m4a','.webm','.mp4','.aac'):
        raise HTTPException(400,'WAV, MP3, FLAC, OGG, M4A, WebM 파일을 선택해 주세요.')
    uploadid = uuid.uuid4().hex
    folder = UPLOADS/uploadid
    folder.mkdir()
    source = folder/('source'+suffix)
    total = 0
    with source.open('wb') as output:
        while chunk := file.file.read(1024*1024):
            total += len(chunk)
            if total > 64*1024*1024:
                output.close()
                source.unlink(missing_ok=True)
                raise HTTPException(413,'64MB 이하의 파일을 선택해 주세요.')
            output.write(chunk)
    try:
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-nostdin','-y','-i',str(source),
            '-t','121','-vn','-ac','1','-ar','24000','-c:a','pcm_s24le',str(folder/'audio.wav')],
            capture_output=True,check=True,timeout=45,creationflags=HIDDEN)
        info = sf.info(str(folder/'audio.wav'))
        if not .4 <= info.duration <= 120:
            raise ValueError('0.4초 이상 2분 이하의 녹음을 선택해 주세요.')
    except (subprocess.SubprocessError,RuntimeError,ValueError) as exc:
        (folder/'audio.wav').unlink(missing_ok=True)
        raise HTTPException(400, str(exc) if isinstance(exc, ValueError) else '오디오를 읽지 못했습니다. WAV 파일로 다시 시도해 주세요.')
    result = {'id':uploadid,'name':Path(file.filename or '녹음.webm').name,'duration':round(info.duration,2),
              'url':f'/media/uploads/{uploadid}/audio.wav'}
    (folder/'info.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
    return result

@app.post('/api/jobs')
def create_job(body: JobRequest):
    request = body.model_dump()
    if body.voice_id and body.reference_id:
        raise HTTPException(400, '내장 화자와 직접 올린 참조 음성 중 하나만 선택해 주세요.')
    if body.mode == 'tts' and not body.dialogue.strip():
        raise HTTPException(400,'읽을 대사를 입력해 주세요.')
    if '<|' in body.dialogue or '|>' in body.dialogue:
        raise HTTPException(400,'대사에는 읽을 문장만 입력하고 연기 설정은 오른쪽에서 선택해 주세요.')
    if body.mode != 'tts':
        request['source_path'] = str(upload_path(body.source_id))
        if body.mode in ('chat','analyze') and read_json(Path(request['source_path']).parent/'info.json')['duration'] > 30:
            raise HTTPException(400,'음성 대화·분석에는 30초 이하의 녹음을 사용해 주세요.')
    if body.voice_id:
        voice, path = preset_voice(body.voice_id)
        if body.mode in ('chat','analyze'):
            if not body.read_response:
                raise HTTPException(400, '음성 답변을 켠 뒤 응답 화자를 선택해 주세요.')
        else:
            request['reference_path'] = str(path)
            request['reference_text'] = voice['text'] if body.mode == 'tts' else ''
    elif body.reference_id:
        ref = upload_path(body.reference_id)
        if read_json(ref.parent/'info.json')['duration'] > 30:
            raise HTTPException(400,'참조 목소리는 30초 이하의 녹음을 선택해 주세요. 5~15초를 권장합니다.')
        request['reference_path'] = str(ref)
    elif body.mode == 'convert':
        raise HTTPException(400,'바꿀 목소리의 참조 녹음을 선택해 주세요.')
    modelid = 'chat' if body.mode == 'analyze' else body.mode
    models = {m['id']:m for m in model_status()}
    required = [modelid] + (['tts'] if body.read_response and body.mode in ('chat','analyze') else [])
    if any(not models[m]['ready'] for m in required):
        raise HTTPException(409,'필요한 모델을 아직 준비하고 있습니다. 다운로드가 완료된 뒤 다시 시도해 주세요.')
    if 'tts' in required and not next(m['ready'] for m in tts_options() if m['id']==body.tts_engine):
        raise HTTPException(409,'선택한 대사 생성 모델이 준비되어 있지 않습니다.')
    with lock:
        if sum(r['status'] in ('queued','running') for r in records.values()) >= 8:
            raise HTTPException(429,'대기 작업이 8개 있습니다. 완료된 뒤 추가해 주세요.')
        jobid = uuid.uuid4().hex
        (JOBS/jobid).mkdir()
        record = {'id':jobid,'mode':body.mode,'status':'queued','stage':'queued','message':'앞선 작업이 끝나면 시작합니다.',
                  'created_at':time.time(),'title':(body.dialogue or body.instruction or {'convert':'보이스체인지','chat':'음성 대화','analyze':'음성 분석'}.get(body.mode,''))[:80]}
        records[jobid] = record
        persist(record)
        pending.put((jobid,request))
    return record

@app.get('/api/jobs')
def jobs():
    with lock:
        return {'jobs':sorted((r for r in records.values() if not r.get('archived')),key=lambda x:x['created_at'],reverse=True)[:50]}

@app.get('/api/jobs/{jobid}')
def job(jobid: str):
    with lock:
        if jobid not in records:
            raise HTTPException(404,'작업을 찾을 수 없습니다.')
        return dict(records[jobid])

@app.post('/api/jobs/{jobid}/cancel')
def cancel(jobid: str):
    with lock:
        if jobid not in records:
            raise HTTPException(404,'작업을 찾을 수 없습니다.')
        if records[jobid]['status'] in ('queued','running'):
            cancelled.add(jobid)
            if records[jobid]['status'] == 'queued':
                update(jobid,status='cancelled',stage='cancelled',message='작업을 취소했습니다.')
            else:
                update(jobid,message='작업을 멈추고 GPU 메모리를 정리합니다.')
        return records[jobid]

app.mount('/media',StaticFiles(directory=DATA),name='media')
app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')

@app.get('/')
def index():
    return FileResponse(ROOT/'static'/'index.html')

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=PORT,access_log=False)
