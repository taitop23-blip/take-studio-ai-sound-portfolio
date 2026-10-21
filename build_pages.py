"""Build the editable SVG source pages imported into the Figma portfolio."""
from __future__ import annotations

import base64
import html
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "figma_pages"
OUT.mkdir(exist_ok=True)
IMG = ROOT / "assets" / "take-studio-ui.jpg"
W, H = 1600, 900
BG = "#0B1220"
CARD = "#172339"
CARD2 = "#1E2C44"
WHITE = "#F4F5F1"
MUTED = "#A7B5C8"
LIME = "#C7FF71"
CYAN = "#62D5D7"
LINE = "#344259"
FONT = "Malgun Gothic, Apple SD Gothic Neo, Noto Sans KR, Arial, sans-serif"
REPO = "https://github.com/taitop23-blip/take-studio-ai-sound-portfolio"


def esc(s: str) -> str:
    return html.escape(s, quote=True)


class Page:
    def __init__(self, no: int, category: str):
        self.no = no
        self.nodes: list[str] = []
        self.rect(0, 0, W, H, BG)
        self.rect(0, 0, 12, H, LIME)
        self.text(70, 53, "PARK JUNMIN  /  AI SOUND ENGINEER", 19, LIME, 700, spacing=1.7)
        self.text(1270, 53, category.upper(), 18, CYAN, 700, anchor="end", spacing=1.1)
        self.line(70, 75, 1530, 75, LINE, 1)
        self.line(70, 845, 1530, 845, LINE, 1)
        self.text(70, 874, "NETMARBLE  ·  AI SOUND ENGINEER APPLICATION", 16, MUTED, 500, spacing=1.0)
        self.text(1530, 874, f"{no:02d} / 10", 16, LIME, 700, anchor="end")

    def rect(self, x, y, w, h, fill, radius=0, stroke=None, sw=1):
        s = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}"'
        if stroke:
            s += f' stroke="{stroke}" stroke-width="{sw}"'
        self.nodes.append(s + "/>")

    def line(self, x1, y1, x2, y2, color=LINE, sw=1):
        self.nodes.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{sw}"/>')

    def text(self, x, y, s, size=24, color=WHITE, weight=400, anchor="start", spacing=0):
        self.nodes.append(f'<text x="{x}" y="{y}" fill="{color}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" letter-spacing="{spacing}">{esc(s)}</text>')

    def lines(self, x, y, items, size=24, color=WHITE, weight=400, leading=38):
        for i, item in enumerate(items):
            self.text(x, y + i * leading, item, size, color, weight)

    def pill(self, x, y, w, label, color=LIME):
        self.rect(x, y, w, 42, CARD2, 21)
        self.text(x + 20, y + 29, label, 18, color, 700)

    def card(self, x, y, w, h, eyebrow, title, body, accent=CYAN):
        self.rect(x, y, w, h, CARD, 22)
        self.text(x + 30, y + 44, eyebrow, 17, accent, 700, spacing=1)
        self.text(x + 30, y + 101, title, 32, WHITE, 700)
        self.lines(x + 30, y + 150, body, 20, MUTED, 400, 35)

    def title(self, kicker, title, subtitle=None):
        self.text(70, 130, kicker, 20, CYAN, 700, spacing=1)
        self.text(70, 215, title, 58, WHITE, 700)
        if subtitle:
            self.text(72, 265, subtitle, 23, MUTED)

    def image(self, x, y, w, h, path=IMG):
        raw = base64.b64encode(path.read_bytes()).decode("ascii")
        self.nodes.append(f'<image x="{x}" y="{y}" width="{w}" height="{h}" preserveAspectRatio="xMidYMid slice" href="data:image/jpeg;base64,{raw}"/>')

    def save(self, name):
        xml = f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{W}" height="{H}" viewBox="0 0 {W} {H}">' + "".join(self.nodes) + "</svg>"
        (OUT / f"{self.no:02d}_{name}.svg").write_text(xml, encoding="utf-8")


p = Page(1, "Portfolio / 2026")
p.text(72, 185, "SOUND  ×  GAME  ×  LOCAL AI", 24, CYAN, 700, spacing=2)
p.text(68, 330, "게임 속 경험을", 80, WHITE, 700)
p.text(68, 440, "소리로 설계합니다.", 80, WHITE, 700)
p.lines(72, 565, ["생성형 AI 사운드 디자인부터 UE5 인게임 적용까지.", "대사 음성은 로컬에서 만들고, 직접 듣고 검수합니다."], 27, MUTED, 400, 46)
p.rect(1100, 155, 385, 490, CARD, 26)
p.text(1140, 258, "박준민", 66, LIME, 700)
p.text(1144, 315, "AI 사운드 엔지니어", 28, WHITE, 700)
p.line(1142, 365, 1440, 365, LINE, 2)
p.lines(1142, 420, ["ProjectATM  ·  게임 사운드", "Take Studio  ·  로컬 AI 음성", "발매 음원  ·  믹싱 / 마스터링"], 20, MUTED, 400, 52)
p.pill(72, 720, 175, "PRO TOOLS")
p.pill(262, 720, 210, "UNREAL ENGINE 5")
p.pill(488, 720, 185, "LOCAL AI")
p.save("cover")

p = Page(2, "Contents")
p.title("읽는 순서", "목차", "직무에 가장 가까운 실무 사례부터 배치했습니다.")
toc = [
    ("03", "채용 직무와 연결", "요구 역량 → 실제 근거"),
    ("04", "ProjectATM", "생성형 AI 효과음 · 타이틀 음악 · UE5 적용"),
    ("05", "사운드 데이터 에셋 프레임워크", "이벤트 태그와 조건 기반 재생 구조"),
    ("06", "Take Studio", "로컬 대사 연기 · 보이스체인지 · 음성 분석"),
    ("07", "AI 음성 제작 및 QC", "한국어·영어 대사, 모델 선택과 검수 흐름"),
    ("08", "믹싱 · 마스터링", "발매 음원 2곡 / Pro Tools"),
    ("09", "게임 대사 샘플", "한·영 4개 대사 / 4개 화자 / 음성 검수"),
    ("10", "청취 · 코드 · 연락처", "직접 확인할 수 있는 링크"),
]
for i, (n, title, sub) in enumerate(toc):
    y = 345 + i * 67
    p.text(75, y, n, 23, LIME, 700)
    p.text(160, y, title, 28, WHITE, 700)
    p.text(760, y, sub, 20, MUTED)
    p.line(70, y + 20, 1530, y + 20, LINE)
p.save("contents")

p = Page(3, "Role fit")
p.title("넷마블 AI 사운드 엔지니어", "요구 역량에 맞춘 작업 증거", "공고의 제작·검수·게임 적용 축에 실제 수행한 작업을 대응했습니다.")
rows = [
    ("01", "DAW · 오디오 품질", "발매 음원 2곡 믹싱·마스터링", "Pro Tools / 공개 청취 링크"),
    ("02", "TTS · Voice Conversion", "Take Studio 대사 연기·보이스체인지", "한국어·영어 / 로컬 참조 음성"),
    ("03", "합성 음성 검수", "대사·발음·감정·신호 품질을 구분", "후보 테이크 비교와 사람의 최종 청취"),
    ("04", "게임 사운드 파이프라인", "ProjectATM 사운드 구조와 인게임 적용", "UE5 / 태그·데이터 에셋"),
]
for i, (n, req, evidence, proof) in enumerate(rows):
    y = 323 + i * 122
    p.rect(70, y, 1460, 104, CARD, 20)
    p.text(105, y + 65, n, 36, LIME, 700)
    p.text(205, y + 46, req, 27, WHITE, 700)
    p.text(205, y + 77, proof, 18, MUTED)
    p.text(1480, y + 59, evidence, 24, CYAN, 700, anchor="end")
p.save("role_fit")

p = Page(4, "ProjectATM")
p.title("TEAM PROJECT  /  2 MONTHS", "ProjectATM — 게임 사운드 제작", "생성, 작·편곡, 엔진 내 재생까지 한 프로젝트 안에서 담당했습니다.")
p.card(70, 320, 690, 202, "ROLE 01", "효과음 사운드 디자인", ["생성형 AI를 제작 과정에 활용", "게임 상황에 맞게 후보를 선별·적용"])
p.card(790, 320, 740, 202, "ROLE 02", "타이틀 음악 작·편곡", ["프로젝트의 분위기를 음악으로 설계", "타이틀 경험과 사운드 톤을 연결"])
p.card(70, 542, 690, 202, "ROLE 03", "UE5 사운드 파이프라인", ["이벤트 태그·데이터 에셋 기반 재생 구조", "상태와 환경에 따른 소재 선택"])
p.card(790, 542, 740, 202, "ROLE 04", "인게임 사운드 적용", ["도구 루프·환경음 전환 등 상황별 재생", "게임플레이 흐름 안에서 소리 점검"])
p.text(75, 805, "팀 프로젝트의 담당 범위만 기술했습니다. 비공개 저장소의 코드와 에셋은 공개하지 않습니다.", 18, MUTED)
p.save("project_atm")

p = Page(5, "Sound framework")
p.title("UE5 / SOUND DATA ASSETS", "사운드 데이터 에셋 프레임워크", "게임 로직과 오디오 소재를 분리해 상황별 재생을 구성했습니다.")
steps = [
    (80, "01", "이벤트 입력", ["게임플레이가 이벤트 태그 전달", "예: 도구 사용·환경 변화"]),
    (450, "02", "조건 판정", ["현재 상태·환경 태그를 조회", "필수 조건과 후보의 구체성 비교"]),
    (820, "03", "소재 선택", ["데이터 에셋에서 재생 후보 결정", "음원·재생 방식·설정 연결"]),
    (1190, "04", "출력·수명 관리", ["2D / 위치 / 액터 부착 재생", "루프 정지·전환·페이드 제어"]),
]
for x, n, title, body in steps:
    p.rect(x, 332, 330, 235, CARD, 20)
    p.text(x + 25, 380, n, 30, LIME, 700)
    p.text(x + 25, 432, title, 28, WHITE, 700)
    p.lines(x + 25, 478, body, 18, MUTED, 400, 33)
for x in (420, 790, 1160):
    p.text(x, 455, "→", 28, CYAN, 700)
p.rect(80, 605, 1440, 161, CARD2, 18)
p.text(112, 648, "설계 포인트", 21, CYAN, 700)
p.lines(112, 697, ["사운드 작업자는 소재와 조건을 데이터에서 조정하고, 게임 로직은 이벤트를 전달합니다.", "도구의 시작·지속·종료음과 수면 위·아래 환경음처럼 전환이 중요한 상황을 관리합니다."], 21, WHITE, 400, 36)
p.save("sound_framework")

p = Page(6, "Take Studio")
p.title("PERSONAL TOOL  /  WINDOWS  /  LOCAL", "Take Studio — 로컬 게임 대사 작업실", "대사 연기, 보이스체인지, 녹음 분석을 한 화면에서 다룹니다.")
p.rect(70, 314, 965, 483, CARD, 18)
p.image(86, 330, 933, 451)
p.rect(1060, 314, 470, 483, CARD, 18)
p.text(1095, 370, "핵심 기능", 26, LIME, 700)
p.lines(1095, 422, ["01  한국어·영어 TTS 대사 연기", "02  원본 연기를 살리는 보이스체인지", "03  음성 대화·녹음 분석", "04  남녀 각 2개 내장 화자 선택", "05  24bit WAV + 설정 JSON 저장"], 20, WHITE, 400, 57)
p.line(1095, 705, 1490, 705, LINE)
p.lines(1095, 746, ["127.0.0.1 로컬 서버 · 실행 시 자동 연결", "모델 가중치와 음성 파일은 공개 저장소 제외"], 17, MUTED, 400, 29)
p.save("take_studio")

p = Page(7, "Voice production")
p.title("TTS / VC / REVIEW", "게임 대사를 만드는 세 가지 경로", "연기 의도는 설정하고, 전달력은 듣고 결정합니다.")
p.card(70, 315, 465, 355, "01  /  TEXT TO SPEECH", "대사 연기", ["대사와 연기 설정을 분리", "감정·발성·속도·화자 선택", "Higgs TTS 3 / VoxCPM2", "한국어·영어 후보 테이크 생성"], LIME)
p.card(565, 315, 465, 355, "02  /  VOICE CONVERSION", "보이스체인지", ["직접 연기한 원본 녹음 입력", "참조 음색으로 변환", "Seed-VC v2", "말의 리듬과 타이밍을 우선 보존"], CYAN)
p.card(1060, 315, 470, 355, "03  /  AUDIO ANALYSIS", "녹음 분석", ["Whisper로 발화 확인", "Qwen2-Audio로 청취 분석", "발음·속도·쉼·녹음 품질 점검", "최종 판단은 사람의 청취"], LIME)
p.rect(70, 713, 1460, 88, CARD2, 16)
p.text(100, 768, "모델 선택 기준", 23, LIME, 700)
p.text(325, 768, "한·영 지원  ·  연기 제어  ·  참조 음성  ·  현재 PC 12GB GPU에서의 실행 가능성", 23, WHITE)
p.save("voice_workflow")

p = Page(8, "Released audio")
p.title("PRO TOOLS  /  MIXING + MASTERING", "발매 음원에서 쌓은 청취 판단", "두 곡의 믹싱과 마스터링을 직접 담당했습니다.")
p.rect(70, 325, 710, 337, CARD, 24)
p.text(107, 380, "TRACK 01", 20, CYAN, 700)
p.text(107, 448, "난로 (Vocal. Galaxy)", 36, WHITE, 700)
p.text(107, 505, "심가영  ·  「눈 내리는 밤에」 수록", 22, MUTED)
p.text(107, 564, "MIXING / MASTERING  ·  PRO TOOLS", 19, LIME, 700)
p.text(107, 615, "youtube.com/watch?v=lJyOIjUblrU", 19, WHITE)
p.rect(820, 325, 710, 337, CARD, 24)
p.text(857, 380, "TRACK 02", 20, CYAN, 700)
p.text(857, 448, "새벽편지 (Vocal. 조수현)", 36, WHITE, 700)
p.text(857, 505, "심가영  ·  「눈 내리는 밤에」 수록", 22, MUTED)
p.text(857, 564, "MIXING / MASTERING  ·  PRO TOOLS", 19, LIME, 700)
p.text(857, 615, "youtube.com/watch?v=melVFdUn6LA", 19, WHITE)
p.rect(70, 709, 1460, 90, CARD2, 18)
p.text(105, 765, "청취 포인트", 23, LIME, 700)
p.text(290, 765, "보컬 명료도  ·  악기 간 균형  ·  저음역 정리  ·  전체 다이내믹스", 23, WHITE)
p.save("released_audio")

p = Page(9, "Voice samples")
p.title("TAKE STUDIO  /  FOUR GAME DIALOGUES", "한·영 게임 대사, 네 가지 장면", "서로 다른 화자와 상황으로 생성하고 대사 일치 여부를 확인했습니다.")
samples = [
    ("01", "방어선 / 강현", "방벽이 무너진다. 부상자부터 이동시켜.", "한국어 · 남성 · 결의 / 5.92초"),
    ("02", "구조 / 서윤", "괜찮아. 여기까지 잘 왔어.", "한국어 · 여성 · 안심 / 4.64초"),
    ("03", "탐색 / 준서", "The signal is back. Hold your position.", "영어 · 남성 · 지시 / 3.20초"),
    ("04", "발견 / 하린", "Wait. I can hear it. The gate is opening.", "영어 · 여성 · 긴장 / 3.68초"),
]
for i, (n, name, line, detail) in enumerate(samples):
    x = 70 if i % 2 == 0 else 815
    y = 325 if i < 2 else 548
    p.rect(x, y, 715, 202, CARD, 22)
    p.text(x + 30, y + 45, n, 22, LIME, 700)
    p.text(x + 85, y + 45, name, 27, WHITE, 700)
    p.text(x + 30, y + 100, line, 20, WHITE)
    p.text(x + 30, y + 157, detail, 19, CYAN)
p.text(72, 806, "원본 WAV 4개와 생성 설정·대사·ASR 점검 결과: GitHub 저장소의 audio_samples/", 20, MUTED)
p.save("voice_samples")

p = Page(10, "Links / Contact")
p.title("LISTEN  /  REVIEW  /  CONTACT", "소리와 작업 과정을 직접 확인하세요", "게임 대사와 발매 음원, 제작 소스를 한곳에 모았습니다.")
p.rect(70, 315, 1460, 482, CARD, 24)
link_rows = [
    ("01", "게임 대사 4개 바로 듣기", "https://taitop23-blip.github.io/take-studio-ai-sound-portfolio/listen.html"),
    ("02", "Take Studio 소스·생성 설정", REPO),
    ("03", "난로 — 믹싱·마스터링", "https://www.youtube.com/watch?v=lJyOIjUblrU"),
    ("04", "새벽편지 — 믹싱·마스터링", "https://www.youtube.com/watch?v=melVFdUn6LA"),
    ("05", "연락처", "taito.p23@gmail.com"),
]
for i, (n, label, link) in enumerate(link_rows):
    y = 367 + i * 83
    p.text(109, y, n, 22, LIME, 700)
    p.text(179, y, label, 24, WHITE, 700)
    p.text(179, y + 31, link, 18, CYAN)
    if i < len(link_rows) - 1:
        p.line(110, y + 45, 1490, y + 45, LINE)
p.text(76, 820, "ProjectATM은 비공개 팀 저장소입니다. 공개 가능한 구조 설명만 이 포트폴리오에 담았습니다.", 18, MUTED)
p.save("links")

print(f"Built {len(list(OUT.glob('*.svg')))} SVG pages in {OUT}")
