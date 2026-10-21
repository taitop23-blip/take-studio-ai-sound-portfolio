"""Preserve raw floating-point audio and create a playback-safe 24-bit take."""
from pathlib import Path

def export_audio(result):
    if not result.get('audio_path'):
        return result
    import numpy as np
    import soundfile as sf
    output = Path(result['audio_path'])
    raw = output.with_name(output.stem+'_raw.wav')
    samples, rate = sf.read(str(raw if raw.exists() else output),dtype='float32')
    if not samples.size or not np.isfinite(samples).all():
        raise RuntimeError('유효한 오디오가 생성되지 않았습니다.')
    peak = float(np.max(np.abs(samples)))
    if peak < 1e-6:
        raise RuntimeError('생성 결과가 무음입니다. 입력을 확인하고 다시 시도해 주세요.')
    gain = min(1.0, (10**(-1/20))/peak)
    if not raw.exists():
        sf.write(str(raw), samples, rate, subtype='FLOAT')
    sf.write(str(output),samples*gain,rate,subtype='PCM_24')
    result['raw_audio_path'] = str(raw)
    result.setdefault('settings',{}).update({
        'export_format':'WAV / PCM 24bit','raw_format':'WAV / Float32',
        'raw_peak_dbfs':round(20*np.log10(peak),3),
        'export_gain_db':round(20*np.log10(gain),3),
        'export_peak_dbfs':round(20*np.log10(peak*gain),3),
        'export_processing':'constant gain only; no compression, EQ, or resampling',
    })
    return result
