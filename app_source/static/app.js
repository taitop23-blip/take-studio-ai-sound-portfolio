'use strict';

(() => {
  const $ = (id) => document.getElementById(id);
  const state = { tab: 'tts', uploads: {}, uploading: new Set(), voices: [], status: null, activeJob: null, jobs: new Map(), jobInputs: new Map(), history: [], conversation: [], session: 0, recorder: null, recordingStream: null, recordingTimer: null, recordingStart: 0, recordingPending: false, submitting: false, pollTimer: null, pollErrors: 0, statusPending: false };
  try { state.voiceChoices = JSON.parse(localStorage.getItem('take-studio-voices-v1') || '{}'); } catch { state.voiceChoices = {}; }
  if (!state.voiceChoices || typeof state.voiceChoices !== 'object' || Array.isArray(state.voiceChoices)) state.voiceChoices = {};
  const modes = { tts: '대사 연기', convert: '보이스 체인지', chat: '음성 대화', analyze: '음성 분석' };
  const terminal = new Set(['completed', 'failed', 'cancelled']);
  const safeUrl = (value) => { if (typeof value !== 'string' || !value) return null; try { const u = new URL(value, location.origin); return u.origin === location.origin && ['http:', 'https:'].includes(u.protocol) ? u.href : null; } catch { return null; } };
  const time = (seconds) => { const n = Math.max(0, Math.floor(Number(seconds) || 0)); return `${Math.floor(n / 60)}:${String(n % 60).padStart(2, '0')}`; };
  const durationText = (seconds) => Number.isFinite(Number(seconds)) && seconds !== null ? `${Number(seconds).toFixed(1)}초` : '';
  const text = (tag, value, className) => { const node = document.createElement(tag); node.textContent = value; if (className) node.className = className; return node; };
  const showNotice = (message) => { $('notice-text').textContent = message; $('notice').hidden = false; };
  const hideNotice = () => { $('notice').hidden = true; };

  async function api(path, options = {}) {
    let response;
    try { response = await fetch(path, { ...options, headers: { ...(options.body && !(options.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}), ...options.headers } }); }
    catch { throw new Error('로컬 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인한 뒤 다시 시도해 주세요.'); }
    let data;
    try { data = await response.json(); } catch { throw new Error('서버 응답을 읽을 수 없습니다. 잠시 후 다시 시도해 주세요.'); }
    if (!response.ok) {
      const detail = data.error || data.message || data.detail;
      const readable = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map(x => x.msg || '').filter(Boolean).join(' / ') : '';
      throw new Error(readable || `요청을 처리하지 못했습니다 (${response.status}). 입력값을 확인해 주세요.`);
    }
    return data;
  }

  function selectedMode() { return state.tab === 'voice' ? document.querySelector('input[name="voice-mode"]:checked').value : state.tab; }
  function updateButton() {
    const mode = selectedMode();
    const busy = state.submitting || !!state.activeJob || !!state.status?.busy;
    $('generate-button').disabled = busy || state.uploading.size > 0 || !!state.recorder || state.recordingPending;
    $('generate-label').textContent = state.submitting ? '요청하는 중' : state.activeJob ? '작업 진행 중' : state.status?.busy ? '다른 작업 진행 중' : { tts: '음성 생성', convert: '목소리 변환', chat: '음성으로 대화', analyze: '음성 분석' }[mode];
    $('generate-hint').textContent = busy ? '현재 작업을 마치면 다음 테이크를 만들 수 있습니다.' : { tts: '설정한 조건으로 새 테이크를 만듭니다.', convert: '원본 연기를 기준으로 목소리를 바꿉니다.', chat: '음성을 듣고 대화를 이어갑니다.', analyze: '음성을 살펴보고 결과를 정리합니다.' }[mode];
    $('settings-title').textContent = { tts: '연기 설정', convert: '변환 설정', voice: '응답 설정' }[state.tab];
    $('response-voice').disabled = !$('read-response').checked;
    $('new-session').disabled = !!state.activeJob || state.submitting;
  }

  function setTab(tab, focus = false) {
    if (!['tts', 'convert', 'voice'].includes(tab)) return;
    if (state.recorder && state.tab !== tab) stopRecording();
    state.tab = tab;
    const pages = {tts:['대사 제작','한 줄의 대사에서, 캐릭터의 목소리까지.'],convert:['보이스체인지','직접 연기한 호흡과 타이밍을 새로운 목소리로.'],voice:['음성 대화·분석','말을 건네고, 녹음을 살펴보고, 다음 테이크를 준비하세요.']};
    $('page-title').textContent = pages[tab][0]; $('page-subtitle').textContent = pages[tab][1]; $('workspace-mode').textContent = pages[tab][0];
    for (const button of document.querySelectorAll('[data-tab]')) { const active = button.dataset.tab === tab; button.classList.toggle('active', active); button.setAttribute('aria-selected', String(active)); button.tabIndex = active ? 0 : -1; }
    for (const name of ['tts', 'convert', 'voice']) { $(`panel-${name}`).hidden = name !== tab; $(`${name}-settings`).hidden = name !== tab; }
    updateButton();
    if (focus) $(`tab-${tab}`).focus();
  }

  function renderVoiceChoice(kind) {
    const value = $(`${kind}-voice`).value;
    state.voiceChoices[kind] = value;
    try { localStorage.setItem('take-studio-voices-v1', JSON.stringify(state.voiceChoices)); } catch { /* Choosing a voice still works without storage. */ }
    const voice = state.voices.find(item => item.id === value);
    const preview = $(`${kind}-voice-preview`);
    preview.pause();
    preview.hidden = !voice;
    preview.removeAttribute('src');
    if (voice) preview.src = `/api/voices/${encodeURIComponent(voice.id)}/audio`;
    if (kind !== 'response') $(`${kind}-custom-reference`).hidden = value !== 'custom';
    $(`${kind}-voice-note`).textContent = voice ? `${voice.gender} · ${voice.description} · 한국어/영어` :
      value === 'custom' ? '사용 허락을 받은 한 사람의 선명한 녹음을 넣어주세요. 5~15초를 권장합니다.' : '기본 모델 화자를 사용합니다.';
  }

  function renderVoiceOptions(voices) {
    const signature = JSON.stringify(voices);
    if (state.voiceSignature === signature) return;
    state.voiceSignature = signature;
    state.voices = voices;
    for (const kind of ['tts','convert','response']) {
      const select = $(`${kind}-voice`);
      const selected = state.voiceChoices[kind] || select.value;
      const options = [];
      if (kind !== 'convert') {const option = document.createElement('option'); option.value = 'default'; option.textContent = '기본 화자'; options.push(option);}
      for (const gender of ['남성','여성']) {
        const group = document.createElement('optgroup'); group.label = gender;
        for (const voice of voices.filter(item => item.gender === gender)) {const option = document.createElement('option'); option.value = voice.id; option.textContent = `${voice.name} · ${voice.description}`; group.append(option);}
        if (group.children.length) options.push(group);
      }
      if (kind !== 'response') {const custom = document.createElement('option'); custom.value = 'custom'; custom.textContent = '직접 음성 올리기'; options.push(custom);}
      select.replaceChildren(...options);
      select.value = [...select.options].some(option => option.value === selected) ? selected : (kind === 'convert' ? 'custom' : 'default');
      renderVoiceChoice(kind);
    }
  }

  async function refreshStatus(silent = true) {
    if (state.statusPending) return;
    state.statusPending = true;
    try {
      const data = await api('/api/status');
      const wasBusy = !!state.status?.busy;
      state.status = data;
      renderVoiceOptions(Array.isArray(data.voices) ? data.voices : []);
      const choices = data.tts_engines || [{id:'higgs',name:'Higgs TTS 3 · 4B / 24kHz',ready:true}];
      const signature = JSON.stringify(choices);
      const modelSelect=$('tts-engine');
      if(modelSelect.dataset.choices !== signature) {
        modelSelect.replaceChildren(...choices.filter(choice=>choice.ready).map(choice=>{const option=document.createElement('option');option.value=choice.id;option.textContent=choice.name;return option;}));
        modelSelect.dataset.choices=signature;
      }
      if(data.selected_tts_engine) modelSelect.value=data.selected_tts_engine;
      modelSelect.disabled=!!data.busy;
      $('tts-engine-note').textContent=modelSelect.value==='voxcpm2'?'48kHz 출력 · 참조 목소리와 스타일 제어. 약 8GB의 여유 GPU 메모리를 권장합니다.':'감정·발성 태그와 참조 목소리 · 24kHz 출력.';
      $('reference-mode-note').hidden=modelSelect.value!=='voxcpm2';
      const engine = data.engine || {status:'stopped',message:'대사 생성 시 모델을 준비합니다.'};
      $('engine-strip').dataset.state = engine.status;
      $('engine-title').textContent = {ready:'대사 생성 준비 완료',loading:'음성 모델을 준비하고 있습니다',working:'대사를 생성하고 있습니다',error:'모델 준비를 마치지 못했습니다',stopped:'필요할 때 모델을 불러옵니다'}[engine.status] || '음성 엔진';
      $('engine-message').textContent = engine.message;
      $('retry-engine').hidden = !['error','stopped'].includes(engine.status);
      $('retry-engine').disabled = !!data.busy;
      $('release-engine').disabled = !!data.busy || engine.status === 'stopped';
      $('connection-dot').className = `status-dot ${data.busy ? 'busy' : 'online'}`;
      $('system-state').textContent = data.busy ? '작업 진행 중' : '서버 연결됨';
      $('footer-status').textContent = data.busy ? '생성 작업 진행 중' : '로컬 서버 연결됨';
      const models = Array.isArray(data.models) ? data.models : [];
      $('model-count').textContent = `${models.filter(model => model.ready).length}/${models.length} 준비됨`;
      $('model-list').replaceChildren();
      if (!models.length) $('model-list').append(text('li', '사용 가능한 모델 정보가 없습니다.'));
      for (const model of models) {
        const item = document.createElement('li'); const row = document.createElement('div'); row.className = 'model-name'; row.append(text('span', model.name || model.id || '음성 모델'), text('span', model.ready ? '준비됨' : '준비 필요', `model-badge${model.ready ? '' : ' not-ready'}`)); item.append(row); if (model.detail) item.append(text('span', String(model.detail), 'model-detail')); $('model-list').append(item);
      }
      const gpu = data.gpu || {};
      $('gpu-info').textContent = gpu.name ? `${gpu.name}${gpu.free_mb != null && gpu.total_mb != null && Number.isFinite(Number(gpu.free_mb)) && Number.isFinite(Number(gpu.total_mb)) ? ` · 여유 ${(Number(gpu.free_mb) / 1024).toFixed(1)} / ${(Number(gpu.total_mb) / 1024).toFixed(1)} GB` : ''}` : 'GPU 정보를 확인할 수 없습니다.';
      if (!state.activeJob && (data.busy || wasBusy)) await refreshJobs(true);
    } catch (error) {
      $('connection-dot').className = 'status-dot offline'; $('system-state').textContent = '서버 연결 확인 필요'; $('footer-status').textContent = '연결 확인 필요'; $('model-count').textContent = '연결 대기';
      if (!silent) showNotice(error.message);
    } finally { state.statusPending = false; updateButton(); }
  }

  function pauseOtherAudio(current) { document.querySelectorAll('audio').forEach(audio => { if (audio !== current) audio.pause(); }); }
  function audioElement(url, label) { const audio = document.createElement('audio'); audio.controls = true; audio.preload = 'metadata'; audio.src = url; audio.setAttribute('aria-label', label); audio.addEventListener('play', () => pauseOtherAudio(audio)); return audio; }

  function renderUpload(slot) {
    const zone = document.querySelector(`[data-upload="${slot}"]`); const preview = zone.querySelector('.upload-preview'); const label = zone.querySelector('.upload-label'); const upload = state.uploads[slot];
    preview.querySelector('audio')?.pause(); preview.replaceChildren(); preview.hidden = !upload; label.hidden = !!upload;
    if (!upload) return;
    const head = document.createElement('div'); head.className = 'upload-file-head'; const info = document.createElement('div'); info.append(text('p', upload.name || '업로드한 음성', 'upload-name')); if (upload.duration != null) info.append(text('p', durationText(upload.duration), 'upload-duration'));
    const remove = text('button', '제거', 'remove-upload'); remove.type = 'button'; remove.setAttribute('aria-label', `${upload.name || '음성 파일'} 제거`); remove.addEventListener('click', () => { preview.querySelector('audio')?.pause(); delete state.uploads[slot]; zone.querySelector('input').value = ''; renderUpload(slot); });
    head.append(info, remove); preview.append(head); const url = safeUrl(upload.url); if (url) preview.append(audioElement(url, `${upload.name || '업로드한 음성'} 미리 듣기`));
  }

  async function uploadFile(slot, file) {
    if (!file || state.uploading.has(slot)) return false;
    if (!/\.(wav|mp3|flac|m4a|ogg|webm|aac|mp4)$/i.test(file.name)) { showNotice('WAV, MP3, FLAC, OGG, M4A, WebM, AAC, MP4 형식의 음성 파일을 선택해 주세요.'); return false; }
    if (!file.size) { showNotice('내용이 없는 파일입니다. 다른 음성 파일을 선택해 주세요.'); return; }
    if (file.size > 64 * 1024 * 1024) { showNotice('64MB 이하의 음성 파일을 선택해 주세요.'); return false; }
    const zone = document.querySelector(`[data-upload="${slot}"]`); const label = zone.querySelector('.upload-label>span'); const priorLabel = label.textContent;
    state.uploading.add(slot); zone.classList.add('upload-busy'); zone.setAttribute('aria-busy', 'true'); label.textContent = '음성 업로드 중'; updateButton(); hideNotice();
    try { const form = new FormData(); form.append('file', file); const uploaded = await api('/api/uploads', { method: 'POST', body: form }); if (!uploaded.id) throw new Error('파일을 저장했는지 확인할 수 없습니다. 다시 업로드해 주세요.'); const limit = slot === 'convert-source' ? 120 : 30; if (Number(uploaded.duration) > limit) throw new Error(`${slot === 'voice-source' ? '대화·분석' : slot === 'convert-source' ? '보이스 체인지 원본' : '참조 목소리'}에는 ${limit}초 이하의 음성을 사용해 주세요. 음성을 짧게 편집한 뒤 다시 선택할 수 있습니다.`); state.uploads[slot] = uploaded; renderUpload(slot); $('job-announcement').textContent = `${uploaded.name || file.name} 업로드 완료`; return true; }
    catch (error) { showNotice(error.message); return false; }
    finally { state.uploading.delete(slot); zone.classList.remove('upload-busy'); zone.removeAttribute('aria-busy'); label.textContent = priorLabel; zone.querySelector('input').value = ''; updateButton(); }
  }

  function bindUploads() {
    document.querySelectorAll('[data-upload]').forEach(zone => {
      const slot = zone.dataset.upload;
      zone.querySelector('input').addEventListener('change', event => uploadFile(slot, event.target.files[0]));
      let dragDepth = 0;
      zone.addEventListener('dragenter', event => { event.preventDefault(); dragDepth += 1; zone.classList.add('dragging'); });
      zone.addEventListener('dragover', event => event.preventDefault());
      zone.addEventListener('dragleave', () => { dragDepth -= 1; if (dragDepth <= 0) zone.classList.remove('dragging'); });
      zone.addEventListener('drop', event => { event.preventDefault(); dragDepth = 0; zone.classList.remove('dragging'); uploadFile(slot, event.dataTransfer.files[0]); });
    });
  }

  async function startRecording(slot = 'voice-source', limit = 30) {
    if (state.recorder) { stopRecording(); return; }
    if (state.recordingPending) return;
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) { showNotice('이 브라우저에서는 녹음을 사용할 수 없습니다. 음성 파일을 업로드하거나 Chrome·Edge에서 로컬 주소를 열어 주세요.'); return; }
    if (state.uploading.has(slot)) return;
    const mimeType = ['audio/webm;codecs=opus', 'audio/webm'].find(type => MediaRecorder.isTypeSupported(type));
    if (!mimeType) { showNotice('이 브라우저는 WebM 녹음을 지원하지 않습니다. Chrome·Edge를 사용하거나 음성 파일을 업로드해 주세요.'); return; }
    const button = $(slot === 'convert-source' ? 'convert-record-button' : 'record-button');
    const label = $(slot === 'convert-source' ? 'convert-record-label' : 'record-label');
    const status = $(slot === 'convert-source' ? 'convert-record-status' : 'record-status');
    const originalTab = state.tab;
    state.recordingPending = true; button.disabled = true; updateButton();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true }); if (state.tab !== originalTab) { stream.getTracks().forEach(track => track.stop()); return; } state.recordingStream = stream;
      const recorder = new MediaRecorder(stream, { mimeType }); const chunks = []; let failed = false;
      recorder.addEventListener('dataavailable', event => { if (event.data.size) chunks.push(event.data); });
      recorder.addEventListener('error', () => { failed = true; showNotice('녹음이 중단되었습니다. 마이크 연결을 확인하고 다시 녹음해 주세요.'); stopRecording(); });
      recorder.addEventListener('stop', async () => {
        stream.getTracks().forEach(track => track.stop()); state.recordingStream = null; state.recorder = null; clearInterval(state.recordingTimer); button.classList.remove('recording'); label.textContent = '직접 녹음'; status.textContent = '녹음을 마쳤습니다. 음성을 업로드하고 있습니다.'; updateButton();
        if (!failed && chunks.length) { const blob = new Blob(chunks, { type: mimeType }); const stamp = new Date().toISOString().replace(/[:.]/g, '-'); const uploaded = await uploadFile(slot, new File([blob], `녹음_${stamp}.webm`, { type: mimeType })); status.textContent = uploaded ? '녹음한 음성을 미리 듣고 사용하세요.' : '업로드를 완료하지 못했습니다. 알림을 확인하고 다시 녹음해 주세요.'; }
        else status.textContent = '녹음된 음성이 없습니다. 다시 녹음해 주세요.';
      });
      state.recorder = recorder; state.recordingStart = Date.now(); recorder.start(250); button.classList.add('recording'); label.textContent = '녹음 마치기'; status.textContent = `녹음 중 0:00 / ${time(limit)}`; state.recordingTimer = setInterval(() => { const elapsed = (Date.now() - state.recordingStart) / 1000; status.textContent = `녹음 중 ${time(elapsed)} / ${time(limit)}`; if (elapsed >= limit - .3) stopRecording(); }, 100); updateButton();
    } catch (error) {
      state.recordingStream?.getTracks().forEach(track => track.stop()); state.recordingStream = null; state.recorder = null;
      showNotice(error.name === 'NotAllowedError' ? '마이크 사용이 허용되지 않았습니다. 브라우저의 사이트 권한에서 마이크를 허용하거나 음성 파일을 업로드해 주세요.' : '마이크를 사용할 수 없습니다. 입력 장치가 연결되어 있고 다른 앱에서 사용 중인지 확인해 주세요.');
    } finally { state.recordingPending = false; button.disabled = false; updateButton(); }
  }
  function stopRecording() { if (state.recorder && state.recorder.state !== 'inactive') state.recorder.stop(); }

  function getPayload() {
    const mode = selectedMode(); const seed = Number($('seed').value); const tokens = Number($('max-tokens').value);
    if (!Number.isInteger(seed) || seed < 0 || seed > 2147483647) { $('seed').closest('details').open = true; $('seed').focus(); throw new Error('시드는 0부터 2147483647 사이의 정수로 입력해 주세요.'); }
    if (!Number.isInteger(tokens) || tokens < 128 || tokens > 1536) { $('max-tokens').closest('details').open = true; $('max-tokens').focus(); throw new Error('최대 생성 토큰을 128부터 1536 사이의 정수로 입력해 주세요.'); }
    const payload = { mode, tts_engine:$('tts-engine').value || 'higgs', dialogue: '', language: $('language').value, emotion: 'normal', delivery: 'normal', speed: 'normal', seed, max_new_tokens: tokens, voice_id: null, reference_id: null, reference_text: '', source_id: null, instruction: '', read_response: false, history: [] };
    if (mode === 'tts') {
      payload.dialogue = $('dialogue').value.trim(); if (!payload.dialogue) { $('dialogue').focus(); throw new Error('먼저 읽을 대사를 입력해 주세요. 연기 지시는 오른쪽 설정에서 고를 수 있습니다.'); } if (payload.dialogue.length > 1500) throw new Error('대사는 한 번에 1,500자까지 생성할 수 있습니다. 문장을 나누어 입력해 주세요.');
      payload.emotion = $('emotion').value; payload.delivery = document.querySelector('input[name="delivery"]:checked').value; payload.speed = document.querySelector('input[name="speed"]:checked').value;
      const voice = $('tts-voice').value;
      if (voice === 'custom') {payload.reference_id = state.uploads['tts-reference']?.id || null; payload.reference_text = $('reference-text').value.trim(); if (!payload.reference_id) throw new Error('직접 음성을 사용하려면 참조 녹음을 올려주세요.');}
      else if (voice !== 'default') payload.voice_id = voice;
    } else if (mode === 'convert') {
      payload.source_id = state.uploads['convert-source']?.id || null;
      if ($('convert-voice').value === 'custom') payload.reference_id = state.uploads['convert-reference']?.id || null;
      else payload.voice_id = $('convert-voice').value;
      if (!payload.source_id) throw new Error('연기가 담긴 원본 음성을 먼저 선택해 주세요.'); if (!payload.reference_id && !payload.voice_id) throw new Error('변환할 목표 목소리의 참조 음성을 선택해 주세요.');
    } else {
      payload.source_id = state.uploads['voice-source']?.id || null; if (!payload.source_id) throw new Error('대화하거나 분석할 음성을 녹음하거나 업로드해 주세요.'); payload.instruction = $('voice-instruction').value.trim(); payload.read_response = $('read-response').checked; if (payload.read_response && $('response-voice').value !== 'default') payload.voice_id = $('response-voice').value; payload.history = mode === 'chat' ? state.history.slice(-16).map(message => ({ role: message.role, content: message.content })) : [];
    }
    return payload;
  }

  async function submitJob(event) {
    event?.preventDefault(); if (state.submitting || state.activeJob || state.uploading.size || state.recorder || state.recordingPending || state.status?.busy) return;
    hideNotice(); let payload; try { payload = getPayload(); } catch (error) { showNotice(error.message); return; }
    const sourceName = state.uploads['voice-source']?.name || '음성 메시지';
    state.submitting = true; updateButton();
    try {
      const job = await api('/api/jobs', { method: 'POST', body: JSON.stringify(payload) }); if (!job.id) throw new Error('작업 번호를 확인할 수 없습니다. 작업 목록을 새로고침해 주세요.');
      state.jobInputs.set(job.id, { ...payload, session: state.session, sourceName });
      state.activeJob = { ...job, startedAt: Date.now(), mode: payload.mode }; state.pollErrors = 0; renderProgress(job); pollJob(job.id); refreshStatus();
    } catch (error) { showNotice(error.message); } finally { state.submitting = false; updateButton(); }
  }

  function renderProgress(job) {
    $('progress-panel').hidden = false;
    const stage = typeof job.stage === 'string' ? job.stage : '';
    const names = { queued: '작업 대기 중', running: '음성 작업 진행 중', loading: '모델을 불러오는 중', generating: '음성을 생성하는 중', listening: '음성을 듣는 중', transcribing: '음성을 듣는 중', converting: '목소리를 변환하는 중', analyzing: '음성을 분석하는 중', replying: '답변을 준비하는 중', thinking: '답변을 준비하는 중', speaking: '답변 음성을 만드는 중', saving: '결과를 저장하는 중' };
    const title = names[stage] || names[job.status] || (stage && /[가-힣]/.test(stage) ? stage : '작업 진행 중');
    if ($('progress-title').textContent !== title) $('job-announcement').textContent = title;
    $('progress-title').textContent = title; $('progress-message').textContent = job.message || '첫 실행에는 모델을 불러오는 시간이 필요할 수 있습니다.'; $('progress-time').textContent = time((Date.now() - (state.activeJob?.startedAt || Date.now())) / 1000); $('cancel-job').disabled = false;
  }

  async function pollJob(id) {
    if (state.activeJob?.id !== id) return;
    try {
      const job = await api(`/api/jobs/${encodeURIComponent(id)}`); state.pollErrors = 0; state.jobs.set(id, job);
      if (terminal.has(job.status)) {
        const input = state.jobInputs.get(id); state.activeJob = null; $('progress-panel').hidden = true;
        if (job.status === 'completed') { $('job-announcement').textContent = '작업이 완료되었습니다. 테이크 보관함에서 결과를 확인하세요.'; if (input && ['chat', 'analyze'].includes(input.mode)) addConversation(job, input); renderTakes(); if (job.result?.warning) showNotice(String(job.result.warning)); }
        else if (job.status === 'failed') showNotice(`작업을 완료하지 못했습니다. ${job.error || job.message || '모델 준비 상태와 입력 파일을 확인하고 다시 시도해 주세요.'}`);
        else $('job-announcement').textContent = '작업을 취소했습니다.';
        updateButton(); await refreshStatus(); return;
      }
      renderProgress(job);
    } catch (error) { state.pollErrors += 1; $('progress-message').textContent = `서버 연결을 다시 확인하고 있습니다. 입력과 작업 번호는 유지됩니다. (${state.pollErrors})`; if (state.pollErrors === 3) showNotice(`${error.message} 연결되면 진행 상황을 다시 확인합니다.`); }
    if (state.activeJob?.id === id) state.pollTimer = setTimeout(() => pollJob(id), state.pollErrors ? 4000 : 1200);
  }

  async function cancelJob() {
    if (!state.activeJob) return; $('cancel-job').disabled = true;
    try { await api(`/api/jobs/${encodeURIComponent(state.activeJob.id)}/cancel`, { method: 'POST' }); $('progress-message').textContent = '취소를 요청했습니다. 현재 처리 단계가 정리될 때까지 잠시 기다려 주세요.'; }
    catch (error) { showNotice(error.message); $('cancel-job').disabled = false; }
  }

  function addConversation(job, input) {
    if (input.session !== state.session) return;
    const result = job.result || {}; const transcript = result.transcript || result.input_text; const userContent = transcript ? `${transcript}${input.instruction ? `\n\n요청: ${input.instruction}` : ''}` : input.instruction || `음성 파일: ${input.sourceName}`;
    const assistantContent = result.text || '음성 답변이 생성되었습니다.';
    state.conversation.push({ role: 'user', content: userContent }, { role: 'assistant', content: assistantContent, audio_url: result.audio_url, mode: input.mode });
    if (input.mode === 'chat') state.history.push({ role: 'user', content: userContent }, { role: 'assistant', content: assistantContent });
    renderConversation();
  }
  function renderConversation() {
    const container = $('conversation'); container.querySelectorAll('audio').forEach(audio => audio.pause()); container.replaceChildren(); $('conversation-count').textContent = `${state.conversation.length}개 메시지`;
    if (!state.conversation.length) { container.append(text('p', '음성을 보내면 이곳에 대화가 쌓입니다.', 'conversation-empty')); return; }
    for (const message of state.conversation) { const article = document.createElement('article'); article.className = `message ${message.role}`; article.append(text('div', message.role === 'user' ? '내 음성' : message.mode === 'analyze' ? '분석 결과' : 'Take Studio', 'message-label'), text('p', message.content, 'message-content')); const url = safeUrl(message.audio_url); if (url) article.append(audioElement(url, '대화 응답 음성')); container.append(article); }
    container.scrollTop = container.scrollHeight;
  }

  function resultLink(label, value, filename) { const url = safeUrl(value); if (!url) return null; const link = text('a', label); link.href = url; link.download = filename; return link; }
  function renderTakes() {
    const all = [...state.jobs.values()].filter(job => job.status === 'completed' && job.result).sort((a, b) => (Number(b.created_at) || 0) - (Number(a.created_at) || 0)); $('takes-count').textContent = String(all.length);
    const query = $('take-search').value.trim().toLocaleLowerCase(); const filter = $('take-filter').value;
    const completed = all.filter(job => (filter === 'all' || job.mode === filter) && (!query || `${job.title || ''} ${job.result.text || ''}`.toLocaleLowerCase().includes(query)));
    const list = $('takes-list'); list.querySelectorAll('audio').forEach(audio => audio.pause()); list.replaceChildren();
    if (!completed.length) {const empty = document.createElement('div'); empty.className='takes-empty'; empty.append(text('p',all.length ? '검색 조건에 맞는 테이크가 없습니다.' : '첫 테이크를 만들어 보세요. 완성된 음성과 설정이 이곳에 저장됩니다.')); list.append(empty); return;}
    for (let index = 0; index < completed.length; index += 1) {
      const job = completed[index]; const result = job.result; const input = state.jobInputs.get(job.id); const mode = input?.mode || job.mode || result.mode; const card = document.createElement('article'); card.className = 'take-card'; const info = document.createElement('div'); info.className = 'take-info';
      const modeLabel = modes[mode] || '생성 결과';
      const fullTitle = typeof job.title === 'string' ? job.title.trim() : '';
      const titleChars = Array.from(fullTitle);
      const takeTitle = fullTitle ? titleChars.length > 60 ? `${titleChars.slice(0, 59).join('')}…` : fullTitle : modeLabel;
      const titleNode = text('h3', takeTitle); if (fullTitle) titleNode.title = fullTitle;
      const takeNumber = all.length - all.indexOf(job);
      info.append(text('span', `Take ${String(takeNumber).padStart(2, '0')}`, 'take-number'));
      if (fullTitle) info.append(text('span', modeLabel, 'take-mode-label'));
      info.append(titleNode);
      const metadata = [result.engine, durationText(result.duration), result.elapsed_seconds != null ? `생성 ${durationText(result.elapsed_seconds)}` : ''].filter(Boolean).join(' · '); info.append(text('p', metadata || '생성 완료')); card.append(info);
      const audioBox = document.createElement('div'); audioBox.className = 'take-audio'; const audioUrl = safeUrl(result.audio_url); if (audioUrl) audioBox.append(audioElement(audioUrl, `Take ${takeNumber} 결과 음성`)); else if (result.text) audioBox.append(text('p', result.text, 'take-text')); else audioBox.append(text('p', '결과 파일 정보가 없습니다.', 'help-text')); card.append(audioBox);
      const actions = document.createElement('div'); actions.className = 'take-actions';
      const isPcm24 = typeof result.settings?.export_format === 'string' && result.settings.export_format.trim().toLowerCase() === 'wav / pcm 24bit';
      const audioLink = resultLink(isPcm24 ? 'WAV 24bit' : 'WAV 저장', result.audio_url, `Take_${job.id}.wav`);
      const rawLink = resultLink('원본 Float WAV', result.raw_audio_url, `Take_${job.id}_raw_float.wav`);
      const settingsLink = resultLink('설정 저장', result.settings_url, `Take_${job.id}_settings.json`);
      if (audioLink) actions.append(audioLink); if (rawLink) actions.append(rawLink); if (settingsLink) actions.append(settingsLink); card.append(actions);
      if (audioUrl && result.text) { const detail = document.createElement('details'); detail.className = 'take-text-details'; detail.append(text('summary', mode === 'tts' ? '대사 보기' : '응답 텍스트 보기'), text('p', result.text, 'take-text')); card.append(detail); }
      if (typeof result.transcript === 'string' && result.transcript.trim()) { const detail = document.createElement('details'); detail.className = 'take-text-details'; detail.append(text('summary', '입력 음성의 전사 보기'), text('p', result.transcript, 'take-text')); card.append(detail); }
      if (typeof result.analysis_original === 'string' && result.analysis_original.trim()) { const detail = document.createElement('details'); detail.className = 'take-text-details'; detail.append(text('summary', '분석 원문 보기'), text('p', result.analysis_original, 'take-text')); card.append(detail); }
      const warning = typeof result.warning === 'string' ? result.warning.trim() : '';
      const reachedLimit = result.settings?.length_limit_reached === true || result.settings?.speech?.length_limit_reached === true;
      if (warning || reachedLimit) {
        const notes = document.createElement('div'); notes.className = 'take-notes';
        if (warning) notes.append(text('p', warning, 'take-warning'));
        if (reachedLimit) notes.append(text('p', '끝이 잘렸다면 생성 길이를 늘리거나 문장을 나누어 주세요.', 'take-length-note'));
        card.append(notes);
      }
      list.append(card);
    }
  }

  async function refreshJobs(silent = false) {
    $('refresh-takes').disabled = true;
    try {
      const response = await api('/api/jobs'); const jobs = Array.isArray(response.jobs) ? response.jobs : [];
      for (const job of jobs) if (job.id) state.jobs.set(job.id, job);
      renderTakes();
      if (!state.activeJob) { const pending = jobs.find(job => job.status === 'running') || jobs.find(job => job.status === 'queued'); if (pending) { state.activeJob = { ...pending, startedAt: Date.now() }; renderProgress(pending); pollJob(pending.id); } }
    } catch (error) { if (!silent) showNotice(error.message); } finally { $('refresh-takes').disabled = false; updateButton(); }
  }

  document.querySelectorAll('[data-tab]').forEach(button => {
    button.addEventListener('click', () => setTab(button.dataset.tab));
    button.addEventListener('keydown', event => { const tabs = ['tts', 'convert', 'voice']; let index = tabs.indexOf(state.tab); if (event.key === 'ArrowRight') index = (index + 1) % tabs.length; else if (event.key === 'ArrowLeft') index = (index + tabs.length - 1) % tabs.length; else if (event.key === 'Home') index = 0; else if (event.key === 'End') index = tabs.length - 1; else return; event.preventDefault(); setTab(tabs[index], true); });
  });
  $('dialogue').addEventListener('input', () => { $('dialogue-count').textContent = `${$('dialogue').value.length.toLocaleString('ko-KR')} / 1,500자`; });
  $('studio-form').addEventListener('submit', submitJob);
  document.addEventListener('keydown', event => { if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') { event.preventDefault(); submitJob(); } });
  document.querySelectorAll('[name="voice-mode"]').forEach(input => input.addEventListener('change', updateButton));
  $('record-button').addEventListener('click', () => startRecording('voice-source', 30));
  $('read-response').addEventListener('change', updateButton);
  $('convert-record-button').addEventListener('click', () => startRecording('convert-source', 120));
  $('cancel-job').addEventListener('click', cancelJob);
  $('dismiss-notice').addEventListener('click', hideNotice);
  $('refresh-status').addEventListener('click', () => refreshStatus(false));
  $('refresh-takes').addEventListener('click', () => refreshJobs(false));
  $('take-search').addEventListener('input', renderTakes);
  $('take-filter').addEventListener('change', renderTakes);
  for (const kind of ['tts','convert','response']) $(`${kind}-voice`).addEventListener('change', () => renderVoiceChoice(kind));
  $('tts-engine').addEventListener('change', async ()=>{const selected=$('tts-engine').value;$('tts-engine').disabled=true;try{await api('/api/engine/select',{method:'POST',body:JSON.stringify({tts_engine:selected})});}catch(error){showNotice(error.message);}finally{await refreshStatus(false);}});
  $('retry-engine').addEventListener('click', async () => {try {await api('/api/engine/retry',{method:'POST'}); await refreshStatus(false);} catch(error) {showNotice(error.message);}});
  $('release-engine').addEventListener('click', async () => {try {await api('/api/engine/release',{method:'POST'}); await refreshStatus(false);} catch(error) {showNotice(error.message);}});
  $('new-session').addEventListener('click', () => { if (state.activeJob || state.submitting) return; state.session += 1; state.history = []; state.conversation = []; $('voice-instruction').value = ''; renderConversation(); $('job-announcement').textContent = '새 대화를 시작했습니다.'; });
  window.addEventListener('beforeunload', () => { state.recordingStream?.getTracks().forEach(track => track.stop()); });
  const draftFields = ['dialogue','reference-text','voice-instruction','language','emotion','seed','max-tokens'];
  let draftTimer;
  function saveDraft() {
    try {const draft={fields:Object.fromEntries(draftFields.map(id=>[id,$(id).value])), radios:[...document.querySelectorAll('input[type=radio]:checked')].map(input=>[input.name,input.value])}; localStorage.setItem('take-studio-draft-v1',JSON.stringify(draft)); $('draft-status').textContent='초안 저장됨 · 이 PC';} catch { $('draft-status').textContent='초안 자동 저장을 사용할 수 없습니다'; }
  }
  try {const draft=JSON.parse(localStorage.getItem('take-studio-draft-v1') || 'null'); if(draft?.fields) {for(const id of draftFields) if(typeof draft.fields[id]==='string') $(id).value=draft.fields[id]; for(const [name,value] of draft.radios||[]) {for(const input of document.querySelectorAll('input[type=radio]')) if(input.name===name && input.value===value) input.checked=true;} $('dialogue-count').textContent=`${$('dialogue').value.length.toLocaleString('ko-KR')} / 1,500자`;}} catch { /* A damaged draft never prevents the app from opening. */ }
  $('studio-form').addEventListener('input',()=>{clearTimeout(draftTimer);draftTimer=setTimeout(saveDraft,350);});
  $('studio-form').addEventListener('change',saveDraft);
  window.addEventListener('beforeunload',saveDraft);
  bindUploads(); updateButton(); refreshStatus(); refreshJobs(true);
  setInterval(() => { if (!document.hidden) refreshStatus(); }, 4000);
})();
