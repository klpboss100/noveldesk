# NOVELDESK — 소설 분석 웹앱 (Streamlit 버전)
# streamlit run streamlit_app.py
# 배포: https://share.streamlit.io

import streamlit as st
import sys
import os
import re
import json
import glob
import tempfile
import shutil
import statistics
import io
from pathlib import Path
from collections import defaultdict, Counter

# ── 경로 설정 ──────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
ENGINE_DIR = BASE_DIR / 'engine'
sys.path.insert(0, str(ENGINE_DIR))

# ── 페이지 기본 설정 ───────────────────────────────────────
st.set_page_config(
    page_title="NOVELDESK — 소설 분석 도구",
    page_icon="N",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={'About': 'NOVELDESK — 한국어 소설 반복 표현 탐지 & 분석 도구'}
)

# ── Design C: 편집자형 (흰 배경, 검정, 빨강) ───────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@400;700&display=swap');

  html, body, [class*="css"] { font-family: 'Malgun Gothic', -apple-system, sans-serif; }

  /* 사이드바 */
  [data-testid="stSidebar"] { background: #111 !important; }
  [data-testid="stSidebar"] * { color: #FAFAF8 !important; }
  [data-testid="stSidebar"] .stFileUploader label { color: #FAFAF8 !important; }

  /* 헤더 */
  .nd-logo { font-family: Georgia, serif; font-size: 1.6rem; letter-spacing: 0.15em; text-transform: uppercase; color: #111; font-weight: 400; border-bottom: 2px solid #111; padding-bottom: 12px; margin-bottom: 0; }
  .nd-tagline { font-size: 0.78rem; color: #888; margin-top: 6px; margin-bottom: 24px; letter-spacing: 0.03em; }

  /* STEP 카드 */
  .step-card { background: #fff; border: 1px solid #E0E0DC; border-radius: 6px; padding: 14px 18px; margin-bottom: 10px; }
  .step-card:hover { border-color: #111; }
  .step-num { font-family: Georgia, serif; font-size: 2rem; color: #111; line-height: 1; float: left; margin-right: 14px; }
  .step-info h3 { font-size: 0.9rem; font-weight: 800; margin: 0 0 2px 0; }
  .step-info p { font-size: 0.78rem; color: #666; margin: 0; }
  .step-badge-free { display: inline-block; font-size: 0.65rem; font-weight: 700; padding: 1px 7px; border-radius: 20px; border: 1px solid #2A6A3A; color: #2A6A3A; background: #ECF7EF; margin-left: 6px; }
  .step-badge-paid { display: inline-block; font-size: 0.65rem; font-weight: 700; padding: 1px 7px; border-radius: 20px; border: 1px solid #C41E1E; color: #C41E1E; background: #FFF0F0; margin-left: 6px; }

  /* 빨강 강조 */
  .red { color: #C41E1E; }
  .red-big { color: #C41E1E; font-family: Georgia, serif; font-size: 1.8rem; font-weight: 700; }

  /* 결과 섹션 헤더 */
  .result-label { font-size: 0.7rem; font-weight: 700; letter-spacing: 0.07em; color: #C41E1E; text-transform: uppercase; margin-bottom: 4px; }
  .result-title { font-size: 1.05rem; font-weight: 800; margin-bottom: 12px; color: #111; }

  /* 구분선 */
  .section-divider { border: none; border-top: 1px solid #E0E0DC; margin: 20px 0; }

  /* 경고 박스 */
  .warn-box { background: #FFF8E1; border: 1px solid #e0c060; border-radius: 6px; padding: 12px 16px; font-size: 0.84rem; color: #7a5c00; margin-bottom: 16px; }
  .ok-box   { background: #ECF7EF; border: 1px solid #c3e6cb; border-radius: 6px; padding: 12px 16px; font-size: 0.84rem; color: #2A6A3A; margin-bottom: 16px; }

  /* 매뉴얼 */
  .manual-step { border-left: 3px solid #C41E1E; padding: 10px 16px; margin-bottom: 14px; background: #fff; }
  .manual-step-num { font-family: Georgia, serif; font-size: 1.2rem; color: #C41E1E; font-weight: 700; }
  .manual-step-title { font-weight: 800; font-size: 0.92rem; margin: 2px 0; }
  .manual-step-body { font-size: 0.82rem; color: #444; line-height: 1.65; }

  /* 인물 카드 그리드 */
  .char-cards { display: flex; flex-wrap: wrap; gap: 10px; }
  .char-card { background: #FAFAF8; border: 1px solid #E0E0DC; border-radius: 6px; padding: 12px 14px; min-width: 120px; }
  .char-name { font-weight: 800; font-size: 1.1rem; }
  .char-count { font-family: Georgia, serif; font-size: 1.5rem; color: #C41E1E; }
  .char-meta { font-size: 0.72rem; color: #888; }

  div[data-testid="stExpander"] { border: 1px solid #E0E0DC !important; border-radius: 6px !important; }
</style>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════
# 유틸리티 함수
# ════════════════════════════════════════════════

def chapter_sort_key(name):
    m = re.search(r'(\d+)', name)
    return int(m.group(1)) if m else 0

def chapter_label(name):
    m = re.search(r'(\d+)', name)
    return f"{int(m.group(1))}화" if m else name

def extract_txt(text):
    return text

def extract_docx(file_bytes):
    from docx import Document
    doc = Document(io.BytesIO(file_bytes))
    return '\n'.join(p.text for p in doc.paragraphs if p.text.strip())

def extract_pdf(file_bytes):
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            return '\n'.join(page.extract_text() or '' for page in pdf.pages)
    except ImportError:
        return None

def split_by_chapter_pattern(text):
    """제N화 패턴으로 텍스트를 챕터로 분리 → {챕터명: 텍스트}"""
    pattern = re.compile(r'(?:^|\n)(제\s*(\d+)\s*화[^\n]*)', re.MULTILINE)
    matches = list(pattern.finditer(text))
    if not matches:
        return {'원고.txt': text.strip()}

    chapters = {}
    for i, m in enumerate(matches):
        num = int(m.group(2))
        start = m.end()
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            chapters[f'제{num:02d}화.txt'] = body

    return chapters

def process_uploaded_files(uploaded_files):
    """업로드된 파일들을 챕터 딕셔너리로 변환 {파일명: 텍스트}"""
    chapters = {}
    errors = []

    for uf in uploaded_files:
        name = uf.name
        ext  = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
        file_bytes = uf.read()

        try:
            if ext == 'txt':
                try:
                    text = file_bytes.decode('utf-8')
                except UnicodeDecodeError:
                    text = file_bytes.decode('cp949', errors='ignore')
                # 단일 파일에 여러 챕터가 있으면 분리
                split = split_by_chapter_pattern(text)
                if len(split) > 1:
                    chapters.update(split)
                else:
                    chapters[name] = text.strip()

            elif ext == 'docx':
                text = extract_docx(file_bytes)
                split = split_by_chapter_pattern(text)
                if len(split) > 1:
                    chapters.update(split)
                    st.success(f"📄 {name} → {len(split)}개 챕터 자동 분리 완료")
                else:
                    chapters[name.replace('.docx', '.txt')] = text.strip()

            elif ext == 'pdf':
                text = extract_pdf(file_bytes)
                if text:
                    split = split_by_chapter_pattern(text)
                    chapters.update(split) if len(split) > 1 else chapters.update({name.replace('.pdf','.txt'): text})
                else:
                    errors.append(f"{name}: PDF 텍스트 추출 실패 (pdfplumber 미설치)")

            elif ext in ('hwpx', 'hwp'):
                errors.append(f"{name}: HWP/HWPX는 현재 직접 지원되지 않습니다. TXT나 DOCX로 변환 후 업로드해주세요.")

            else:
                errors.append(f"{name}: 지원하지 않는 형식입니다.")

        except Exception as e:
            errors.append(f"{name}: {e}")

    return chapters, errors


# ════════════════════════════════════════════════
# 엔진 분석 함수
# ════════════════════════════════════════════════

def run_step1(chapters):
    from step1_frequency_check import (
        find_repeated_endings, find_connective_patterns,
        find_descriptive_cliches, find_narration_verbs, find_action_cliches
    )
    all_text = '\n'.join(chapters.values())
    return {
        'chapter_count': len(chapters),
        'total_chars': len(re.sub(r'\s', '', all_text)),
        'B_endings':    find_repeated_endings(all_text),
        'C_connectives': find_connective_patterns(all_text),
        'D_cliches':    find_descriptive_cliches(all_text),
        'E_verbs':      find_narration_verbs(all_text),
        'F_action':     find_action_cliches(all_text),
    }

def run_step2(chapters):
    from step1_frequency_check import (
        find_repeated_endings, find_connective_patterns,
        find_descriptive_cliches, find_narration_verbs, find_action_cliches
    )
    detectors = [
        ('B_endings',    'AI 의심 종결어·단어',   find_repeated_endings),
        ('C_connectives','접속·대조 구조',         find_connective_patterns),
        ('D_cliches',    '묘사 클리셰',            find_descriptive_cliches),
        ('E_verbs',      '대화 서술동사',           find_narration_verbs),
        ('F_action',     '행동 묘사 클리셰',        find_action_cliches),
    ]
    cats = {}
    for key, label, fn in detectors:
        combined = defaultdict(dict)
        for ch_name, text in chapters.items():
            for pattern, count in fn(text).items():
                combined[pattern][chapter_label(ch_name)] = count
        multi  = {p: d for p, d in combined.items() if len(d) >= 2}
        single = {p: d for p, d in combined.items() if len(d) == 1}
        cats[key] = {
            'label': label,
            'multi':  sorted(multi.items(),  key=lambda x: (-len(x[1]), -sum(x[1].values()))),
            'single': sorted(single.items(), key=lambda x: -sum(x[1].values())),
        }
    return {'chapter_count': len(chapters), 'categories': cats}

def run_step3(chapters, ranks):
    from step5_consistency_check import (
        build_rank_pattern, build_timeline,
        find_regressions, find_intra_chapter_conflicts
    )
    # step5가 폴더 기반이므로 챕터 딕셔너리를 직접 사용하는 형태로 래핑
    rank_pattern = build_rank_pattern(ranks)
    rank_order   = {r: i for i, r in enumerate(ranks)}

    # build_timeline은 {ch_num: (filename, text)} 형태를 기대 — 직접 구성
    from step5_consistency_check import find_rank_refs, get_chapter_num
    timeline = defaultdict(list)
    for ch_name in sorted(chapters.keys(), key=chapter_sort_key):
        ch_num = chapter_sort_key(ch_name)
        text = chapters[ch_name]
        refs = find_rank_refs(text, rank_pattern)
        for surname, rank, sentence in refs:
            timeline[surname].append((ch_num, rank, sentence))

    regressions = []
    for name, refs in timeline.items():
        prev_rank_idx = None
        prev_ch = None
        for ch, rank, sentence in refs:
            curr_idx = rank_order.get(rank, -1)
            if prev_rank_idx is not None and curr_idx < prev_rank_idx:
                regressions.append({
                    'name': name,
                    'prev_ch': prev_ch, 'prev_rank': ranks[prev_rank_idx],
                    'curr_ch': ch,      'curr_rank': rank,
                    'sentence': sentence
                })
            if curr_idx >= 0:
                prev_rank_idx = curr_idx
                prev_ch = ch

    return {
        'ranks': ranks,
        'regressions': regressions,
        'timeline': dict(timeline),
    }

def run_step4(chapters):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm

    candidates = ['Malgun Gothic', 'NanumGothic', 'AppleGothic', 'Noto Sans KR']
    available  = {f.name for f in fm.fontManager.ttflist}
    for name in candidates:
        if name in available:
            plt.rcParams['font.family'] = name
            break
    plt.rcParams['axes.unicode_minus'] = False

    from step7_pacing_check import (
        char_count_no_space, sentence_length_stats,
        dialogue_ratio, scene_break_count
    )

    rows = []
    for ch_name in sorted(chapters.keys(), key=chapter_sort_key):
        text = chapters[ch_name]
        chars = char_count_no_space(text)
        sent_mean, sent_stdev = sentence_length_stats(text)
        dia = dialogue_ratio(text)
        rows.append({
            'file': ch_name,
            'label': chapter_label(ch_name),
            'chars': chars,
            'sent_mean': sent_mean,
            'dialogue_ratio': dia * 100,
        })

    if not rows:
        return None, None

    labels     = [r['label'] for r in rows]
    chars_vals = [r['chars'] for r in rows]
    sent_vals  = [r['sent_mean'] for r in rows]
    dia_vals   = [r['dialogue_ratio'] for r in rows]
    x = list(range(len(rows)))

    fig, axes = plt.subplots(3, 1, figsize=(max(10, len(rows)*0.7+2), 11), sharex=True)
    fig.patch.set_facecolor('#FAFAF8')

    specs = [
        (axes[0], chars_vals, '#1A1A1A', '글자수 (공백 제외)',  '글자수',    lambda v: f'{r["label"]}-{v:,}자'),
        (axes[1], sent_vals,  '#C41E1E', '문장 평균 길이',       '평균 길이(자)', lambda v: f'{r["label"]}-{v:.0f}자'),
        (axes[2], dia_vals,   '#2A6A3A', '대화 비중 (%)',        '대화 비중(%)',  lambda v: f'{r["label"]}-{v:.0f}%'),
    ]

    for ax, vals, color, title, ylabel, _ in specs:
        ax.set_facecolor('#FFFFFF')
        ax.plot(x, vals, marker='o', color=color, linewidth=1.8, markersize=5)
        avg = statistics.mean(vals)
        ax.axhline(avg, color='#AAAAAA', linestyle='--', linewidth=1)
        ax.set_title(title, fontsize=10, fontweight='bold', color='#111', pad=6)
        ax.set_ylabel(ylabel, fontsize=8)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.tick_params(labelsize=8)

        # 꼭지점 라벨 (간격이 좁으면 짝수만)
        step = max(1, len(rows) // 20)
        for i, (v, r) in enumerate(zip(vals, rows)):
            if i % step == 0:
                lbl = f'{r["label"]}-{v:,}자' if ylabel == '글자수' else (
                      f'{r["label"]}-{v:.0f}자' if ylabel != '대화 비중(%)' else
                      f'{r["label"]}-{v:.0f}%')
                ax.annotate(lbl, (i, v), textcoords='offset points', xytext=(0, 7),
                            ha='center', fontsize=6.5, color='#555')

    axes[-1].set_xticks(x)
    axes[-1].set_xticklabels(labels, rotation=45, ha='right', fontsize=8)
    fig.tight_layout(pad=2.0)

    return fig, rows

def run_step5(chapters):
    word_pattern = re.compile(r'[가-힣]{2,4}')
    exclude = {
        '그는','그녀','그가','그를','그의','그녀의','그녀가','그녀를','아니','이제',
        '그런','정말','이런','하지만','그래','그리고','우리','모두','자신','조금',
        '정도','생각','눈길','시선','목소리','발걸음','얼굴','표정','눈빛','마음',
        '마치','결국','사실','기억','순간','여전히','여기','저기','거기','무언가',
        '뭔가','아무','어느','한번','그때','지금','나중','이미','아직','오래',
        '다시','계속','혼자','함께','천천히','갑자기','조용히','가만히','살짝',
        '그냥','항상','매번','결코','전혀','너무','매우','때문','경우','사람',
        '인간','시간','공간','장소','소리','느낌','기분','것이','것도','것을',
        '하나','두개','사이','거의','이상','이하','다음','이전','이후','무슨',
    }
    word_ch = defaultdict(lambda: defaultdict(int))
    for ch_name, text in chapters.items():
        lbl = chapter_label(ch_name)
        for w in word_pattern.findall(text):
            if w not in exclude:
                word_ch[w][lbl] += 1

    candidates = [
        {'name': w, 'total': sum(d.values()), 'chapter_count': len(d), 'chapters': dict(d)}
        for w, d in word_ch.items()
        if len(d) >= 2 and sum(d.values()) >= 10
    ]
    candidates.sort(key=lambda x: -x['total'])
    return candidates[:30]


# ════════════════════════════════════════════════
# 사이드바: 원고 입력
# ════════════════════════════════════════════════

with st.sidebar:
    st.markdown('<div style="font-family:Georgia,serif;font-size:1.1rem;letter-spacing:0.15em;color:#FAFAF8;font-weight:400;border-bottom:1px solid #444;padding-bottom:10px;margin-bottom:16px">NOVELDESK</div>', unsafe_allow_html=True)

    st.markdown("#### 소설 이름")
    project_name = st.text_input("", placeholder="예: 우도, 달빛소나타...", label_visibility="collapsed", key="project_name_input")

    st.markdown("#### 원고 업로드")
    st.caption("TXT · DOCX · PDF 지원 | 여러 파일 동시 업로드 가능")
    st.caption("✅ DOCX 한 파일에 전체 원고: 제N화 패턴으로 자동 분리")

    uploaded = st.file_uploader(
        "파일 선택",
        type=['txt', 'docx', 'pdf'],
        accept_multiple_files=True,
        label_visibility="collapsed",
        key="file_uploader"
    )

    st.markdown("---")
    st.markdown("#### 또는 텍스트 붙여넣기")
    paste_title = st.text_input("챕터 이름", placeholder="제1화", key="paste_title")
    paste_text  = st.text_area("텍스트 붙여넣기", height=120, placeholder="원고를 여기에 붙여넣으세요...", key="paste_text")
    if st.button("붙여넣기 등록", use_container_width=True):
        if paste_text.strip():
            title = paste_title.strip() or "원고"
            if 'chapters' not in st.session_state:
                st.session_state.chapters = {}
            st.session_state.chapters[f'{title}.txt'] = paste_text.strip()
            st.success(f"'{title}' 등록 완료!")
        else:
            st.warning("텍스트를 입력해주세요.")

    st.markdown("---")
    if st.button("새 소설 시작 (초기화)", use_container_width=True):
        for key in ['chapters', 'step1_result', 'step2_result', 'step3_result',
                    'step4_result', 'step4_fig', 'step5_result', 'ranks_input']:
            st.session_state.pop(key, None)
        st.rerun()

    st.markdown("---")
    st.markdown('<div style="font-size:0.72rem;color:#888">지원 형식</div>', unsafe_allow_html=True)
    st.markdown("""
    <div style="font-size:0.75rem;color:#aaa;line-height:1.7">
    ✅ TXT — 텍스트 파일<br>
    ✅ DOCX — 워드 문서<br>
    ✅ PDF — PDF 문서<br>
    🔜 HWP/HWPX — 한글 (TXT로 변환 필요)<br>
    🔜 Google Docs — URL로 공유 후 DOCX 저장
    </div>
    """, unsafe_allow_html=True)


# ════════════════════════════════════════════════
# 파일 처리 (업로드 감지)
# ════════════════════════════════════════════════

if uploaded:
    chapters, errors = process_uploaded_files(uploaded)
    if chapters:
        if 'chapters' not in st.session_state:
            st.session_state.chapters = {}
        st.session_state.chapters.update(chapters)
    if errors:
        for e in errors:
            st.sidebar.error(e)


# ════════════════════════════════════════════════
# 메인 화면
# ════════════════════════════════════════════════

st.markdown('<div class="nd-logo">NOVELDESK</div>', unsafe_allow_html=True)
st.markdown('<div class="nd-tagline">한국어 소설 반복 표현 탐지 & 분석 도구 — 개인 전용</div>', unsafe_allow_html=True)

chapters = st.session_state.get('chapters', {})


# ── 원고 없을 때: 환영 화면 + 매뉴얼 ──────────────────────
if not chapters:
    st.markdown("---")

    col1, col2 = st.columns([1.2, 1])

    with col1:
        st.markdown("### 처음 사용하신가요? 3단계로 시작하세요")
        st.markdown("""
        <div class="manual-step">
          <div class="manual-step-num">1</div>
          <div class="manual-step-title">소설 이름을 입력하세요</div>
          <div class="manual-step-body">왼쪽 사이드바의 "소설 이름" 칸에 소설 제목을 입력합니다.<br>예: 우도, 달빛소나타, 강철의 전사</div>
        </div>
        <div class="manual-step">
          <div class="manual-step-num">2</div>
          <div class="manual-step-title">원고 파일을 업로드하세요</div>
          <div class="manual-step-body">
            TXT, DOCX(워드), PDF 파일을 업로드할 수 있어요.<br>
            <strong>전체 원고가 하나의 DOCX 파일?</strong> 그대로 올리면 됩니다.<br>
            '제1화', '제2화'... 패턴이 있으면 자동으로 챕터를 나눠줍니다.<br>
            챕터별로 여러 파일이라면 한꺼번에 여러 개 선택하세요.
          </div>
        </div>
        <div class="manual-step">
          <div class="manual-step-num">3</div>
          <div class="manual-step-title">STEP 버튼을 눌러 분석하세요</div>
          <div class="manual-step-body">
            원고가 등록되면 아래에 STEP 1~5(무료) 버튼이 나타납니다.<br>
            STEP 번호 순서대로 실행하는 것을 권장합니다.<br>
            각 STEP은 독립적으로 실행할 수도 있습니다.
          </div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown("### 각 STEP은 무엇을 하나요?")
        steps_info = [
            (1, "FREE", "반복 표현 탐지", "책 전체에서 AI 글쓰기 의심 패턴, 반복 종결어, 묘사 클리셰, 대화 서술동사를 찾아냅니다."),
            (2, "FREE", "챕터 간 비교", "반복 표현이 단 한 챕터에서만 나오는지, 아니면 여러 챕터에 걸쳐 나오는지 구분합니다. 여러 챕터 반복이 진짜 문제입니다."),
            (3, "FREE", "직급·계급 체크", "군계급(이병→일병→상병→병장) 또는 직장직급(사원→대리→과장→부장)이 챕터 순서상 역행하는지 확인합니다."),
            (4, "FREE", "페이싱 차트", "챕터별 글자수, 문장 평균 길이, 대화 비중을 그래프로 보여줍니다. 리듬이 무너진 챕터를 한눈에 파악할 수 있습니다."),
            (5, "FREE", "인물 관계도", "여러 챕터에 걸쳐 자주 등장하는 단어를 인물 후보로 추출하고 챕터별 등장 빈도를 보여줍니다."),
            (6, "AI", "AI 반복 진단", "Claude AI가 반복 표현 각각에 대해 진단과 대안 표현을 제안합니다. (API 비용 발생)"),
            (7, "AI", "복선 탐지", "전반부에서 나중에 회수되어야 할 설정·암시·약속을 Claude AI가 찾아냅니다."),
            (8, "AI", "복선 회수 확인", "앞에서 탐지한 복선이 후반부에서 실제로 회수됐는지 확인합니다."),
            (9, "AI", "페이싱 AI 판단", "페이싱이 이상한 챕터만 골라 Claude AI가 늘어지는지, 의도된 것인지 판단합니다."),
            (10, "AI", "출판 자료", "소설 소개, 줄거리 요약, 인물 소개 등 출판사 제출용 자료를 생성합니다."),
        ]
        for num, badge, name, desc in steps_info:
            badge_html = f'<span class="step-badge-free">무료</span>' if badge == "FREE" else f'<span class="step-badge-paid">AI 유료</span>'
            st.markdown(f"""
            <div style="display:flex;gap:12px;align-items:flex-start;margin-bottom:10px;padding:10px;background:#fff;border:1px solid #E0E0DC;border-radius:5px">
              <div style="font-family:Georgia,serif;font-size:1.3rem;min-width:30px;color:#111;font-weight:400;line-height:1.2">{num}</div>
              <div>
                <div style="font-size:0.86rem;font-weight:800">{name} {badge_html}</div>
                <div style="font-size:0.76rem;color:#666;line-height:1.55;margin-top:2px">{desc}</div>
              </div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### HWP/HWPX 파일을 TXT로 변환하는 방법")
    with st.expander("HWP → TXT 변환 가이드 (클릭해서 펼치기)"):
        st.markdown("""
        한글(HWP) 프로그램에서 직접 변환:
        1. 한글 프로그램에서 원고 파일 열기
        2. 메뉴: **파일 → 다른 이름으로 저장**
        3. 파일 형식을 **텍스트 문서 (*.txt)** 로 선택
        4. 저장 후 NOVELDESK에 업로드

        또는 DOCX 형식으로 저장해도 됩니다:
        1. 파일 → 다른 이름으로 저장 → **MS 워드 (*.docx)**
        """)

    st.stop()


# ════════════════════════════════════════════════
# 원고 있을 때: 프로젝트 현황 + STEP 실행
# ════════════════════════════════════════════════

sorted_chapters = sorted(chapters.keys(), key=chapter_sort_key)

# 현황 요약
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("프로젝트", project_name or "(이름 없음)")
with col2:
    total_chars = sum(len(re.sub(r'\s', '', t)) for t in chapters.values())
    st.metric("전체 글자수", f"{total_chars:,}자")
with col3:
    st.metric("챕터 수", f"{len(chapters)}개")

st.markdown(f"**등록된 챕터:** {', '.join(chapter_label(c) for c in sorted_chapters[:10])}"
            + (f" 외 {len(chapters)-10}개..." if len(chapters) > 10 else ""))

st.markdown("---")


# ════════════════════════════════════════════════
# STEP 1–5 (무료 분석)
# ════════════════════════════════════════════════

st.markdown("## 무료 분석 STEP 1–5")

# ── STEP 1 ─────────────────────────────────────
with st.expander("**STEP 1 — 반복 표현 탐지**  |  책 전체에서 반복되는 표현·패턴 탐지", expanded=False):
    st.markdown("""
    **무엇을 찾나요?**
    - **[B] AI 의심 종결어**: `듯했다`, `것 같았다`, `문득`, `공허` 등 AI 글쓰기에서 자주 나오는 표현
    - **[C] 접속·대조 구조**: `지만`, `그러나`, `하지만` 등 — 매 문장마다 반복되면 단조롭게 느껴집니다
    - **[D] 묘사 클리셰**: `텅 빈`, `공허한`, `짙은 어둠` 등 진부한 수식 표현
    - **[E] 대화 서술동사**: `말했다`, `외쳤다`, `쏘아붙였다` 등의 빈도
    - **[F] 행동 묘사 클리셰**: `발길을 재촉했다` 류의 2~3어절 반복 표현
    """)

    if st.button("STEP 1 실행", key="run_step1", type="primary"):
        with st.spinner("분석 중... 잠시 기다려주세요"):
            try:
                result = run_step1(chapters)
                st.session_state.step1_result = result
                st.success(f"완료! {result['chapter_count']}개 챕터, {result['total_chars']:,}자 분석")
            except Exception as e:
                st.error(f"오류: {e}")

    if 'step1_result' in st.session_state:
        r = st.session_state.step1_result
        st.markdown("---")
        cols = st.columns(3)
        cols[0].metric("분석 챕터", f"{r['chapter_count']}개")
        cols[1].metric("전체 글자수", f"{r['total_chars']:,}자")

        cats = [
            ('B_endings',    '[B] AI 의심 종결어·단어'),
            ('C_connectives','[C] 접속·대조 구조'),
            ('D_cliches',    '[D] 묘사 클리셰'),
            ('E_verbs',      '[E] 대화 서술동사'),
            ('F_action',     '[F] 행동 묘사 클리셰'),
        ]
        for key, label in cats:
            items = r.get(key, {})
            if items:
                sorted_items = sorted(items.items(), key=lambda x: -x[1])
                import pandas as pd
                df = pd.DataFrame(sorted_items, columns=['표현', '횟수'])
                st.markdown(f"**{label}** — {len(items)}종 발견")
                st.dataframe(df, use_container_width=True, hide_index=True)


# ── STEP 2 ─────────────────────────────────────
with st.expander("**STEP 2 — 챕터 간 비교 리포트**  |  전 챕터 반복 vs 단일 챕터 패턴 구분", expanded=False):
    st.markdown("""
    **STEP 1과의 차이점:**
    STEP 1은 책 전체에서 반복되는 표현 목록을 보여줍니다.
    STEP 2는 거기서 한 발 더 나아가, **어떤 챕터에서 몇 번이나 나왔는지**를 비교합니다.

    - **전 챕터 반복** = 2개 이상 챕터에서 등장 → 진짜 습관적 패턴
    - **단일 챕터** = 1개 챕터에서만 등장 → 그 챕터만의 특징일 수 있음

    STEP 1 결과를 먼저 실행한 뒤 이 STEP을 실행하면 더 자세한 분석이 가능합니다.
    """)

    if st.button("STEP 2 실행", key="run_step2", type="primary"):
        with st.spinner("챕터 간 비교 중..."):
            try:
                result = run_step2(chapters)
                st.session_state.step2_result = result
                total_multi = sum(len(cat['multi']) for cat in result['categories'].values())
                st.success(f"완료! 전 챕터 반복 패턴 {total_multi}종 발견")
            except Exception as e:
                st.error(f"오류: {e}")

    if 'step2_result' in st.session_state:
        import pandas as pd
        r = st.session_state.step2_result
        st.markdown("---")
        st.markdown('<div class="warn-box">아래 "전 챕터 반복" 항목은 책 전체에서 습관적으로 나오는 패턴입니다. 고칠지 말지는 작가가 직접 판단하세요.</div>', unsafe_allow_html=True)

        for key, cat in r['categories'].items():
            if cat['multi']:
                rows = []
                for pattern, ch_dict in cat['multi']:
                    ch_str = ', '.join(f"{ch}:{cnt}회" for ch, cnt in ch_dict.items())
                    rows.append({'표현': pattern, '등장 챕터 수': len(ch_dict), '총 횟수': sum(ch_dict.values()), '챕터별 분포': ch_str})
                df = pd.DataFrame(rows)
                st.markdown(f"**{cat['label']}** — 전 챕터 반복 {len(cat['multi'])}종")
                st.dataframe(df, use_container_width=True, hide_index=True)


# ── STEP 3 ─────────────────────────────────────
with st.expander("**STEP 3 — 직급·계급·직책 체크**  |  챕터 순서상 계급 역행 탐지", expanded=False):
    st.markdown("""
    **무엇을 찾나요?**
    군계급(이병→일병→상병→병장) 또는 직장직급(사원→대리→과장→부장→사장)이
    챕터 진행에서 역행하는 경우를 찾습니다.

    **사용 전 필수 설정:** 아래에 계급 순서를 입력해주세요 (낮은 계급→높은 계급 순서).
    계급 체계가 없는 소설이라면 이 STEP은 건너뛰세요.
    """)

    ranks_input = st.text_input(
        "계급 순서 입력 (쉼표로 구분, 낮은 계급→높은 계급)",
        placeholder="예: 이병,일병,상병,병장 또는 사원,대리,과장,부장,사장",
        key="ranks_input"
    )

    if st.button("STEP 3 실행", key="run_step3", type="primary"):
        if not ranks_input.strip():
            st.warning("계급 순서를 먼저 입력해주세요. 계급 체계가 없는 소설은 이 STEP을 건너뛰세요.")
        else:
            ranks = [r.strip() for r in ranks_input.split(',') if r.strip()]
            with st.spinner("직급 체크 중..."):
                try:
                    result = run_step3(chapters, ranks)
                    st.session_state.step3_result = result
                    n = len(result['regressions'])
                    st.success(f"완료! {'계급 역행 의심 ' + str(n) + '건 발견' if n else '계급 역행 없음'}")
                except Exception as e:
                    st.error(f"오류: {e}")

    if 'step3_result' in st.session_state:
        import pandas as pd
        r = st.session_state.step3_result
        st.markdown("---")
        if r['regressions']:
            st.markdown('<div class="warn-box">아래는 계급 역행 의심 사례입니다. 회상 장면이나 동명이인일 수도 있으니 직접 확인하세요.</div>', unsafe_allow_html=True)
            for issue in r['regressions']:
                st.error(f"**{issue['name']}** : {issue['prev_rank']}({issue['prev_ch']}화) → {issue['curr_rank']}({issue['curr_ch']}화) — 역행 가능성\n\n_{issue.get('sentence','')[:100]}_")
        else:
            st.success("계급 역행 없음 — 이상 없습니다")

        if r.get('timeline'):
            rows = []
            for name, refs in r['timeline'].items():
                for ch, rank, _ in refs:
                    rows.append({'인물': name, '챕터': f'{ch}화', '계급': rank})
            if rows:
                st.markdown("**인물별 계급 타임라인**")
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ── STEP 4 ─────────────────────────────────────
with st.expander("**STEP 4 — 페이싱 차트**  |  글자수·문장길이·대화비중 그래프", expanded=False):
    st.markdown("""
    **무엇을 보여주나요?**
    챕터별로 3가지 지표를 그래프로 시각화합니다:
    - **글자수**: 챕터가 너무 짧거나 너무 길지 않은지
    - **문장 평균 길이**: 문장이 전반적으로 길어지거나 짧아지는 경향
    - **대화 비중**: 지문 위주 vs 대화 위주 챕터 파악

    그래프의 점마다 "N화-수치" 라벨이 표시됩니다.
    평균선(회색 점선)에서 크게 벗어난 챕터를 우선 검토해보세요.
    """)

    if st.button("STEP 4 실행", key="run_step4", type="primary"):
        with st.spinner("페이싱 분석 중..."):
            try:
                fig, rows = run_step4(chapters)
                if fig:
                    st.session_state.step4_fig  = fig
                    st.session_state.step4_result = rows
                    st.success(f"완료! {len(rows)}개 챕터 차트 생성")
                else:
                    st.error("분석할 챕터가 없습니다.")
            except Exception as e:
                st.error(f"오류: {e}")

    if 'step4_fig' in st.session_state:
        import pandas as pd
        st.markdown("---")
        st.pyplot(st.session_state.step4_fig)

        rows = st.session_state.step4_result
        df = pd.DataFrame([{
            '챕터': r['label'],
            '글자수': f"{r['chars']:,}",
            '문장 평균 길이': f"{r['sent_mean']:.1f}자",
            '대화 비중': f"{r['dialogue_ratio']:.1f}%",
        } for r in rows])
        st.dataframe(df, use_container_width=True, hide_index=True)


# ── STEP 5 ─────────────────────────────────────
with st.expander("**STEP 5 — 인물 관계도**  |  여러 챕터 등장 인물 빈도 분석", expanded=False):
    st.markdown("""
    **무엇을 보여주나요?**
    소설 전체에서 2~4글자 한글 단어 중 여러 챕터에 걸쳐 자주 등장하는 것을
    인물 후보로 자동 추출합니다.

    **참고:** 자동 추출이므로 실제 인물명이 아닌 단어가 섞일 수 있습니다.
    등장 빈도와 챕터 분포를 참고해서 주요 인물을 파악하는 용도로 사용하세요.
    """)

    if st.button("STEP 5 실행", key="run_step5", type="primary"):
        with st.spinner("인물 분석 중..."):
            try:
                candidates = run_step5(chapters)
                st.session_state.step5_result = candidates
                st.success(f"완료! 인물 후보 {len(candidates)}명 추출")
            except Exception as e:
                st.error(f"오류: {e}")

    if 'step5_result' in st.session_state:
        import pandas as pd
        candidates = st.session_state.step5_result
        st.markdown("---")
        st.markdown('<div class="warn-box">인물 이름처럼 보이는 단어를 자동으로 추출했습니다. 실제 인물명이 아닌 것도 섞여 있을 수 있습니다.</div>', unsafe_allow_html=True)

        if candidates:
            max_total = candidates[0]['total']

            # 상위 인물 카드 (상위 10명)
            cols = st.columns(5)
            for i, char in enumerate(candidates[:10]):
                with cols[i % 5]:
                    pct = int(char['total'] / max_total * 100)
                    st.markdown(f"""
                    <div class="char-card">
                      <div class="char-name">{char['name']}</div>
                      <div class="char-count">{char['total']}회</div>
                      <div class="char-meta">{char['chapter_count']}개 챕터</div>
                      <div style="height:3px;background:#E0E0DC;border-radius:2px;margin-top:8px">
                        <div style="width:{pct}%;height:100%;background:#C41E1E;border-radius:2px"></div>
                      </div>
                    </div>
                    """, unsafe_allow_html=True)

            # 전체 테이블
            st.markdown("**전체 목록**")
            rows = []
            for char in candidates:
                ch_str = ', '.join(f"{ch}:{cnt}회" for ch, cnt in sorted(char['chapters'].items()))
                rows.append({'이름': char['name'], '총 등장': char['total'],
                             '등장 챕터': char['chapter_count'], '챕터별 분포': ch_str})
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


st.markdown("---")

# ════════════════════════════════════════════════
# STEP 6–10 (AI 유료)
# ════════════════════════════════════════════════

st.markdown("## AI 유료 분석 STEP 6–10")
st.markdown('<div class="warn-box">STEP 6–10은 Claude AI API를 사용하는 유료 분석입니다. API 비용이 발생합니다. 현재 준비 중입니다.</div>', unsafe_allow_html=True)

paid_steps = [
    (6, "AI 반복 표현 진단",   "STEP 1~2에서 찾은 반복 표현을 Claude AI가 직접 읽고, 각 표현이 왜 문제인지, 어떤 대안이 있는지 제안합니다."),
    (7, "복선 탐지",           "전반부 챕터를 AI가 읽고 나중에 회수되어야 할 설정·암시·약속(복선)을 찾아냅니다."),
    (8, "복선 회수 확인",      "앞에서 찾은 복선이 후반부에서 실제로 회수됐는지 AI가 확인합니다. 회수 안 된 복선을 알려줍니다."),
    (9, "페이싱 AI 판단",      "STEP 4에서 이상 신호가 나온 챕터만 AI가 읽고, 실제로 늘어지는지 의도된 장면인지 판단합니다."),
    (10, "출판 자료 생성",     "소설 소개글, 줄거리 요약, 주요 인물 소개 등 출판사 제출용 자료를 AI가 자동 생성합니다."),
]

for num, name, desc in paid_steps:
    with st.expander(f"**STEP {num} — {name}**  |  Claude AI 분석", expanded=False):
        st.markdown(f"**{desc}**")
        st.markdown(f"*STEP {num}은 현재 준비 중입니다. 곧 추가됩니다.*")
        st.button(f"STEP {num} 실행 (준비 중)", key=f"run_step{num}", disabled=True)


st.markdown("---")
st.markdown('<div style="text-align:center;font-size:0.75rem;color:#BBB;padding:20px">NOVELDESK — 개인 전용 소설 분석 도구</div>', unsafe_allow_html=True)
