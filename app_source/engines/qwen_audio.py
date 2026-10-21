"""Local acoustic analysis; conversational replies use a separate text model."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def run(request, jobdir):
    import librosa
    import numpy as np
    import torch
    from transformers import AutoProcessor, Qwen2AudioForConditionalGeneration, BitsAndBytesConfig
    print('녹음 분석 모델을 준비하고 있습니다.',flush=True)
    torch.cuda.reset_peak_memory_stats()
    path = str(ROOT/'models'/'qwen2-audio')
    processor = AutoProcessor.from_pretrained(path,local_files_only=True)
    audio = librosa.load(request['source_path'],sr=processor.feature_extractor.sampling_rate)[0]
    if len(audio) > 30*processor.feature_extractor.sampling_rate:
        raise ValueError('녹음 분석에는 30초 이하의 음성을 사용해 주세요.')
    model = Qwen2AudioForConditionalGeneration.from_pretrained(path,
        quantization_config=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',
            bnb_4bit_compute_dtype=torch.bfloat16,llm_int8_skip_modules=['audio_tower','multi_modal_projector']),
        device_map={'':'cuda:0'},dtype=torch.bfloat16,attn_implementation='sdpa',local_files_only=True).eval()
    task = ('Describe the audible speaking pace, pauses, intonation, loudness and recording artifacts. '
            'Focus on the performance in this game dialogue. Avoid claims about the speaker age, gender, '
            'identity or personal characteristics. Acknowledge uncertainty. Use English. '
            +request.get('instruction',''))
    conversation = [{'role':'system','content':'You are a helpful audio analysis assistant.'},
        {'role':'user','content':[{'type':'audio','audio_url':request['source_path']},{'type':'text','text':task}]}]
    text = processor.apply_chat_template(conversation,add_generation_prompt=True,tokenize=False)
    inputs = processor(text=text,audio=[audio],sampling_rate=processor.feature_extractor.sampling_rate,
                       return_tensors='pt',padding=True).to('cuda:0')
    inputs['input_features'] = inputs['input_features'].to(model.audio_tower.dtype)
    print('녹음의 말투와 소리를 분석하고 있습니다.',flush=True)
    with torch.inference_mode():
        generated = model.generate(**inputs,max_new_tokens=384,do_sample=False)
    answer = processor.batch_decode(generated[:,inputs.input_ids.size(1):],skip_special_tokens=True)[0].strip()
    if not answer:
        raise RuntimeError('분석 결과를 만들지 못했습니다. 선명한 녹음으로 다시 시도해 주세요.')
    peak = float(np.max(np.abs(audio)))
    rms = float(np.sqrt(np.mean(audio**2)))
    return {'text':answer,'engine':'Qwen2-Audio 7B · NF4',
        'settings':{'mode':'analyze','quantization':'NF4','offline':True,
            'peak_vram_gib':round(torch.cuda.max_memory_allocated()/2**30,3),
            'analysis_type':'model listening observations; not an objective acting score',
            'input_duration':len(audio)/processor.feature_extractor.sampling_rate,
            'input_sample_peak_dbfs':round(20*np.log10(max(peak,1e-9)),2),
            'input_rms_dbfs':round(20*np.log10(max(rms,1e-9)),2)}}
