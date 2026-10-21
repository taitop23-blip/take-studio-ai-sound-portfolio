"""Local instruction-following 7B model for replies and analysis presentation."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def run(request,jobdir):
    import torch
    from transformers import AutoTokenizer,AutoModelForCausalLM,BitsAndBytesConfig
    torch.cuda.reset_peak_memory_stats()
    print('대화 모델을 준비하고 있습니다.',flush=True)
    path=str(ROOT/'models'/'qwen-chat')
    tokenizer=AutoTokenizer.from_pretrained(path,local_files_only=True)
    model=AutoModelForCausalLM.from_pretrained(path,local_files_only=True,dtype=torch.bfloat16,
        device_map={'':'cuda:0'},attn_implementation='sdpa',
        quantization_config=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',
            bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=torch.bfloat16)).eval()
    korean=request.get('language')=='Korean'
    language='한국어' if korean else '영어'
    analysis=bool(request.get('analysis_draft'))
    if analysis:
        from engines.analysis_report import SYSTEM, format_analysis
        system=SYSTEM
        user=request['analysis_draft']
    else:
        system=(f'당신은 사용자의 말에 자연스럽게 답하는 음성 대화 도우미입니다. 반드시 {language}로 답하세요. '
                '상황에 맞게 직접 대화하세요. 전사 내용을 설명하거나 번역하지 마세요. '
                '게임 속 대사이면 상대 캐릭터처럼 짧게 응답하고, 제작에 관한 질문에는 구체적으로 도움을 주세요. '
                '최대 세 문장으로 말하세요.')
        user=request.get('transcript','').strip()
        if request.get('instruction'):
            user+='\n\n추가 요청: '+request['instruction']
        if not user:
            raise ValueError('인식된 발화가 없습니다.')
    messages=[{'role':'system','content':system}]
    if not analysis:
        for item in request.get('history',[])[-8:]:
            if item.get('role') in ('user','assistant'):
                messages.append({'role':item['role'],'content':str(item.get('content',''))[:2000]})
    messages.append({'role':'user','content':user})
    text=tokenizer.apply_chat_template(messages,tokenize=False,add_generation_prompt=True)
    inputs=tokenizer(text,return_tensors='pt').to('cuda:0')
    print('답변을 작성하고 있습니다.',flush=True)
    with torch.inference_mode():
        output=model.generate(**inputs,max_new_tokens=160 if analysis else 256,do_sample=False)
    answer=tokenizer.decode(output[0,inputs.input_ids.shape[1]:],skip_special_tokens=True).strip()
    if not answer:
        raise RuntimeError('답변을 만들지 못했습니다. 다시 시도해 주세요.')
    if analysis:
        answer, observations = format_analysis(answer, korean)
    result = {'text':answer,'engine':'Qwen2.5 7B · NF4','settings':{
        'mode':'analysis summary' if analysis else 'conversation','language':request.get('language','Korean'),
        'quantization':'NF4','offline':True,'peak_vram_gib':round(torch.cuda.max_memory_allocated()/2**30,3)}}
    if analysis:
        result['analysis_original'] = request['analysis_draft']
        result['settings']['observations'] = observations
        result['settings']['report_rendering'] = 'Model-extracted categories rendered as fixed Korean/English phrases; original report retained.'
        if all(v == 'unknown' for v in observations.values()):
            result['warning'] = '분석 항목을 정리하지 못했습니다. 분석 원문을 확인해 주세요.' if korean else 'Could not structure the report. Review the original analysis.'
    return result
