# 박준민 · AI 사운드 엔지니어 포트폴리오

게임 속 경험을 소리로 설계합니다. 생성형 AI 효과음 디자인, 타이틀 음악 작·편곡, Unreal Engine 5 인게임 사운드 적용, 로컬 AI 음성 도구 개발 경험을 넷마블 AI 사운드 엔지니어 직무에 맞춰 정리했습니다.

**[피그마 포트폴리오 보기](https://www.figma.com/design/rypMoQBLath1k7iPY1G8ho?node-id=2-910)** · **[제출용 PDF](output/pdf/ParkJunmin_AI_Sound_Engineer_Portfolio.pdf)** · **[한·영 게임 대사 4개 바로 듣기](https://taitop23-blip.github.io/take-studio-ai-sound-portfolio/listen.html)** · [연락처](mailto:taito.p23@gmail.com)

## 작업 사례

| 사례 | 직접 맡은 일 | 확인 자료 |
|---|---|---|
| ProjectATM · 2개월 팀 프로젝트 | 생성형 AI 효과음 사운드 디자인, 타이틀 음악 작·편곡, UE5 사운드 파이프라인 구축 및 인게임 적용 | [포트폴리오 4–5쪽](figma_pages/)의 구조 설명. 팀의 비공개 코드·에셋은 포함하지 않음 |
| Take Studio · 개인 로컬 도구 | 한국어·영어 게임 대사 TTS, 보이스체인지, 녹음 분석, 화자 선택, WAV·설정 내보내기 | [앱 소스](app_source/) · [앱 화면](assets/take-studio-ui.jpg) · [대사 샘플](audio_samples/) |
| 발매 음원 2곡 | Pro Tools 믹싱·마스터링 | [난로](https://www.youtube.com/watch?v=lJyOIjUblrU) · [새벽편지](https://www.youtube.com/watch?v=melVFdUn6LA) |

## Take Studio의 설계

음성 파일을 외부 API에 업로드하지 않는 로컬 제작 환경을 선택했습니다. 대사 원문과 연기 지시를 분리하고, 한국어·영어 TTS 후보를 만든 뒤 발음과 전달력을 직접 듣고 고릅니다. 직접 녹음한 연기의 리듬을 유지해야 할 때는 참조 음색으로 보이스체인지를 사용합니다. Windows EXE는 로컬 서버에 자동 연결되며, 이 저장소에는 **가중치와 오프라인 패키지를 포함하지 않은 소스와 작업 샘플**을 공개합니다.

- TTS: Higgs TTS 3, VoxCPM2
- Voice conversion: Seed-VC v2
- 인식·분석: Whisper large-v3-turbo, Qwen2-Audio 7B, Qwen2.5 7B
- 출력: 24-bit WAV 및 생성 설정 JSON
- 현재 상태: 개인 PC에서 검증한 `1.0.0-rc1` 로컬 빌드

모델은 한국어·영어 지원, 연기 제어, 참조 음색, 12GB GPU에서의 실행 가능성을 함께 고려해 선택했습니다. 모델 분석 결과는 제작 판단의 보조 자료이며, 최종 연기·발음·음질은 사람이 확인합니다. 자세한 사용 범위와 출처는 [Third-party notices](THIRD_PARTY_NOTICES.md)에 적었습니다.

## 네 가지 대사

| 언어 / 장면 | 화자 | 대사 | WAV |
|---|---|---|---|
| 한국어 · 방어선 | 강현 | 방벽이 무너진다. 부상자부터 이동시켜. 내가 마지막까지 길을 막겠다. | [듣기](audio_samples/01_ko_tactical_guard.wav) |
| 한국어 · 구조 | 서윤 | 괜찮아. 여기까지 잘 왔어. 이제 숨을 고르고, 내 목소리만 따라와. | [듣기](audio_samples/02_ko_reassurance.wav) |
| English · scouting | 준서 | The signal is back. Hold your position until I give the word. | [Listen](audio_samples/03_en_scout_command.wav) |
| English · discovery | 하린 | Wait. I can hear it. The gate is opening beneath us. | [Listen](audio_samples/04_en_gate_discovery.wav) |

네 파일은 Take Studio의 VoxCPM2와 로컬 합성 화자 프리셋으로 생성했습니다. [설정과 ASR 점검 결과](audio_samples/index.json)를 함께 보관했습니다. 등장 인물과 대사는 이 포트폴리오용으로 작성한 가상 장면입니다.

## 저장소 구성

```text
app_source/       Take Studio Python 서버·엔진 연동·Windows 셸·웹 UI 소스
assets/           실제 앱 화면
audio_samples/    네 가지 WAV와 생성 설정·점검 기록
figma_pages/      피그마에 가져온 편집 가능한 SVG 10장
listen.html       브라우저 청취 페이지
output/pdf/       제출용 PDF (10장, 청취·코드 링크 포함)
```

실행 가능한 오프라인 패키지와 모델 파일은 용량 및 사용 조건 때문에 이 저장소에 넣지 않았습니다. ProjectATM 팀 저장소의 코드·게임 에셋도 포함하지 않습니다.

**박준민** · [taito.p23@gmail.com](mailto:taito.p23@gmail.com)
