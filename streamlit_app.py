# NOVELDESK — 소설 분석 웹앱 (Streamlit)
# 배포: https://noveldesk-l2xfbasbodfbvaendzic2x.streamlit.app/

import streamlit as st
import sys, os, re, json, io, glob, statistics, tempfile, shutil
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter

BASE_DIR   = Path(__file__).parent
ENGINE_DIR = BASE_DIR / 'engine'
sys.path.insert(0, str(ENGINE_DIR))

# 로컬 실행 여부 — projects 폴더가 있으면 로컬
LOCAL_PROJECTS = BASE_DIR / 'projects'
IS_LOCAL = LOCAL_PROJECTS.exists()

st.set_page_config(
    page_title="NOVELDESK — 소설 분석",
    page_icon="N",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  /* 사이드바 — 흰 배경, 검정 글씨 */
  [data-testid="stSidebar"] { background:#FAFAF8 !important; }
  [data-testid="stSidebar"] button { background:#111 !important; color:#FAFAF8 !important; border:none !important; }
  [data-testid="stSidebar"] button:hover { background:#333 !important; }
  /* 입력창 박스 — 기존 회색 유지 */
  [data-testid="stSidebar"] input,
  [data-testid="stSidebar"] textarea { background:#E8E8E6 !important; color:#111 !important; border:1px solid #ccc !important; }

  /* 메인 영역 — 기본 검정 글씨 */
  .nd-logo { font-family:Georgia,serif; font-size:1.5rem; letter-spacing:.15em;
             text-transform:uppercase; color:#111; border-bottom:2px solid #111;
             padding-bottom:10px; margin-bottom:4px; }
  .nd-sub  { font-size:.78rem; color:#555; margin-bottom:20px; }
  .warn { background:#FFF8E1; border:1px solid #e0c060; border-radius:6px;
          padding:10px 14px; font-size:.83rem; color:#7a5c00; }
  .ok   { background:#ECF7EF; border:1px solid #c3e6cb; border-radius:6px;
          padding:10px 14px; font-size:.83rem; color:#2A6A3A; }
  div[data-testid="stExpander"] { border:1px solid #E0E0DC !important; border-radius:6px !important; }
  .char-card { background:#F5F5F3; border:1px solid #E0E0DC; border-radius:6px;
               padding:10px 12px; text-align:center; }
  .char-name { font-weight:800; font-size:1rem; color:#111; }
  .char-cnt  { font-family:Georgia,serif; font-size:1.4rem; color:#C41E1E; }
</style>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════
# 유틸 함수
# ════════════════════════════════════════════════════════════

def ch_sort(name):
    m = re.search(r'(\d+)', name); return int(m.group(1)) if m else 0

def ch_label(name):
    m = re.search(r'(\d+)', name); return f"{int(m.group(1))}화" if m else name

def split_by_chapter(text):
    pat = re.compile(r'(?:^|\n)(제\s*(\d+)\s*화[^\n]*)', re.MULTILINE)
    matches = list(pat.finditer(text))
    if not matches:
        return {'원고.txt': text.strip()}
    chapters = {}
    for i, m in enumerate(matches):
        num = int(m.group(2))
        start = m.end()
        end   = matches[i+1].start() if i+1 < len(matches) else len(text)
        body  = text[start:end].strip()
        if body:
            chapters[f'제{num:03d}화.txt'] = body
    return chapters

def extract_docx(b):
    from docx import Document
    doc = Document(io.BytesIO(b))
    return '\n'.join(p.text for p in doc.paragraphs if p.text.strip())

def extract_pdf(b):
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(b)) as pdf:
            return '\n'.join(page.extract_text() or '' for page in pdf.pages)
    except Exception:
        return None

def process_files(uploaded_files):
    chapters, errors = {}, []
    for uf in uploaded_files:
        ext = uf.name.rsplit('.',1)[-1].lower() if '.' in uf.name else ''
        b   = uf.read()
        try:
            if ext == 'txt':
                try:    text = b.decode('utf-8')
                except: text = b.decode('cp949', errors='ignore')
            elif ext == 'docx':
                text = extract_docx(b)
            elif ext == 'pdf':
                text = extract_pdf(b)
                if not text:
                    errors.append(f"{uf.name}: PDF 텍스트 추출 실패"); continue
            elif ext in ('hwp','hwpx'):
                errors.append(f"{uf.name}: HWP → TXT 또는 DOCX로 변환 후 업로드하세요"); continue
            else:
                errors.append(f"{uf.name}: 지원하지 않는 형식"); continue

            split = split_by_chapter(text)
            if len(split) > 1:
                chapters.update(split)
                st.sidebar.success(f"📄 {uf.name} → {len(split)}개 챕터 자동 분리")
            else:
                key = uf.name.rsplit('.',1)[0] + '.txt'
                chapters[key] = text.strip()
        except Exception as e:
            errors.append(f"{uf.name}: {e}")
    return chapters, errors

def make_report_dir(project_name):
    """로컬 실행 시 날짜 폴더 생성. 클라우드에선 None 반환."""
    if not IS_LOCAL:
        return None
    date_str = datetime.now().strftime('%Y%m%d')
    folder   = LOCAL_PROJECTS / project_name / f'분석리포트_{date_str}'
    folder.mkdir(parents=True, exist_ok=True)
    return folder

def save_local(folder, filename, data_bytes):
    if folder:
        (folder / filename).write_bytes(data_bytes)


# ════════════════════════════════════════════════════════════
# 엔진 함수
# ════════════════════════════════════════════════════════════

def run_step1(chapters):
    from step1_frequency_check import (
        find_repeated_endings, find_connective_patterns,
        find_descriptive_cliches, find_narration_verbs, find_action_cliches
    )
    all_text = '\n'.join(chapters.values())
    return {
        'chapter_count': len(chapters),
        'total_chars':   len(re.sub(r'\s','',all_text)),
        'B': find_repeated_endings(all_text),
        'C': find_connective_patterns(all_text),
        'D': find_descriptive_cliches(all_text),
        'E': find_narration_verbs(all_text),
        'F': find_action_cliches(all_text),
    }

def run_step2_excel(chapters, use_api=False, api_key=None):
    """
    챕터 간 비교 + 컨텍스트 수집 + 유의어 추천 → Excel bytes 반환
    """
    import openpyxl
    from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
    from step1_frequency_check import (
        find_repeated_endings, find_connective_patterns,
        find_descriptive_cliches, find_narration_verbs, find_action_cliches
    )
    from step3_context_report import get_synonyms_static, find_phrase_contexts

    detectors = [
        ('AI 의심 종결어·단어', find_repeated_endings),
        ('접속·대조 구조',      find_connective_patterns),
        ('묘사 클리셰',         find_descriptive_cliches),
        ('대화 서술동사',       find_narration_verbs),
        ('행동 묘사 클리셰',    find_action_cliches),
    ]

    # 챕터 간 비교 — 2개 이상 챕터 반복만 추출
    combined_multi = {}  # pattern → {ch_label: count}
    pattern_category = {}

    for cat_label, fn in detectors:
        ch_data = defaultdict(dict)
        for ch_name, text in chapters.items():
            for p, c in fn(text).items():
                ch_data[p][ch_label(ch_name)] = c
        for p, d in ch_data.items():
            if len(d) >= 2:
                combined_multi[p] = d
                pattern_category[p] = cat_label

    # 컨텍스트 수집 (표현이 들어간 실제 문장)
    all_sentences = []
    for text in chapters.values():
        sents = re.split(r'[.!?。]\s+', text.replace('\n',' '))
        all_sentences.extend(s.strip() for s in sents if s.strip())

    def get_contexts(pattern, max_n=3):
        hits = [s for s in all_sentences if pattern in s]
        return hits[:max_n]

    # 유의어 (API 또는 정적 사전)
    synonyms = {}
    if use_api and api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            for p in list(combined_multi.keys())[:30]:
                ctxs = get_contexts(p, 3)
                ctx_text = '\n'.join(f'- {s[:100]}' for s in ctxs)
                resp = client.messages.create(
                    model='claude-haiku-4-5-20251001',
                    max_tokens=60,
                    messages=[{"role":"user","content":
                        f"소설에서 '{p}'을 대체할 유의어 3개를 '/'로 구분해서만 출력:\n{ctx_text}"}]
                )
                synonyms[p] = resp.content[0].text.strip()
        except Exception as e:
            st.warning(f"API 유의어 생성 오류: {e} → 내장 사전으로 대체")
            use_api = False

    if not use_api:
        for p in combined_multi:
            synonyms[p] = get_synonyms_static(p)

    # 가나다 순 정렬
    sorted_patterns = sorted(combined_multi.items(), key=lambda x: x[0])

    # Excel 생성
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = '반복표현_챕터간비교'

    # 헤더 색상
    header_fill = PatternFill('solid', fgColor='111111')
    header_font = Font(color='FAFAF8', bold=True, size=10)
    red_fill    = PatternFill('solid', fgColor='FFF0F0')
    thin = Border(
        left=Side(style='thin', color='E0E0DC'),
        right=Side(style='thin', color='E0E0DC'),
        top=Side(style='thin', color='E0E0DC'),
        bottom=Side(style='thin', color='E0E0DC'),
    )

    headers = ['표현', '카테고리', '등장 챕터 수', '총 횟수', '챕터별 분포', '실제 문장 예시', '유의어 추천 3가지']
    for ci, h in enumerate(headers, 1):
        cell = ws.cell(1, ci, h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = thin

    ws.row_dimensions[1].height = 22

    for ri, (pattern, ch_dict) in enumerate(sorted_patterns, 2):
        dist_str = ', '.join(f"{ch}:{cnt}회" for ch, cnt in sorted(ch_dict.items()))
        ctx_str  = ' | '.join(get_contexts(pattern, 2))
        syn_str  = synonyms.get(pattern, '')
        total    = sum(ch_dict.values())
        n_ch     = len(ch_dict)

        row_data = [pattern, pattern_category.get(pattern,''), n_ch, total, dist_str, ctx_str, syn_str]
        for ci, val in enumerate(row_data, 1):
            cell = ws.cell(ri, ci, val)
            cell.alignment = Alignment(wrap_text=True, vertical='top')
            cell.border = thin
            if n_ch >= 3:
                cell.fill = red_fill  # 3개 이상 챕터 = 빨강 강조

    # 열 너비
    ws.column_dimensions['A'].width = 18
    ws.column_dimensions['B'].width = 18
    ws.column_dimensions['C'].width = 10
    ws.column_dimensions['D'].width = 8
    ws.column_dimensions['E'].width = 35
    ws.column_dimensions['F'].width = 50
    ws.column_dimensions['G'].width = 30

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue(), len(sorted_patterns)

def run_step3(chapters, ranks):
    from step5_consistency_check import find_rank_refs, build_rank_pattern
    rank_pattern = build_rank_pattern(ranks)
    rank_order   = {r: i for i, r in enumerate(ranks)}

    timeline = defaultdict(list)
    for ch_name in sorted(chapters.keys(), key=ch_sort):
        ch_num = ch_sort(ch_name)
        for surname, rank, sentence in find_rank_refs(chapters[ch_name], rank_pattern):
            timeline[surname].append((ch_num, rank, sentence))

    regressions = []
    for name, refs in timeline.items():
        prev_idx, prev_ch = None, None
        for ch, rank, sent in refs:
            curr_idx = rank_order.get(rank, -1)
            if prev_idx is not None and curr_idx < prev_idx:
                regressions.append({'name':name,'prev_ch':prev_ch,'prev_rank':ranks[prev_idx],
                                    'curr_ch':ch,'curr_rank':rank,'sentence':sent})
            if curr_idx >= 0:
                prev_idx, prev_ch = curr_idx, ch
    return {'ranks':ranks, 'regressions':regressions, 'timeline':dict(timeline)}

def run_step4_chart(chapters):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm

    for name in ['Malgun Gothic','NanumGothic','AppleGothic','Noto Sans KR']:
        if name in {f.name for f in fm.fontManager.ttflist}:
            plt.rcParams['font.family'] = name; break
    plt.rcParams['axes.unicode_minus'] = False

    from step7_pacing_check import char_count_no_space, sentence_length_stats, dialogue_ratio

    rows = []
    for ch_name in sorted(chapters.keys(), key=ch_sort):
        text = chapters[ch_name]
        chars     = char_count_no_space(text)
        sent_mean, _ = sentence_length_stats(text)
        dia       = dialogue_ratio(text) * 100
        rows.append({'label': ch_label(ch_name), 'chars': chars, 'sent_mean': sent_mean, 'dia': dia})

    if not rows:
        return None, None

    n = len(rows)
    labels = [r['label'] for r in rows]
    x      = list(range(n))

    # A4 가로 비율, 최소 2000px → figsize in inches at 100dpi
    # 가로 최소 20인치(=2000px@100dpi), 챕터 많을수록 더 넓게
    fig_w = max(20, n * 0.55)
    fig_h = fig_w * 0.55   # A4 가로 황금 비율

    fig, axes = plt.subplots(3, 1, figsize=(fig_w, fig_h), sharex=True, dpi=100)
    fig.patch.set_facecolor('#FAFAF8')

    specs = [
        (axes[0], [r['chars']     for r in rows], '#1A1A1A', '글자수 (공백 제외)', '글자수'),
        (axes[1], [r['sent_mean'] for r in rows], '#C41E1E', '문장 평균 길이',      '평균 길이(자)'),
        (axes[2], [r['dia']       for r in rows], '#2A6A3A', '대화 비중 (%)',        '대화 비중(%)'),
    ]

    for ax, vals, color, title, ylabel in specs:
        ax.set_facecolor('#FFFFFF')
        ax.plot(x, vals, marker='o', color=color, linewidth=2, markersize=6)
        avg = statistics.mean(vals)
        ax.axhline(avg, color='#AAAAAA', linestyle='--', linewidth=1)

        # 꼭지점 라벨 — 챕터 수에 따라 폰트 크기 조절
        fs = max(6, min(9, int(140 / n)))
        for i, (v, r) in enumerate(zip(vals, rows)):
            if ylabel == '글자수':
                lbl = f"{r['label']}-{v:,}자"
            elif ylabel == '대화 비중(%)':
                lbl = f"{r['label']}-{v:.0f}%"
            else:
                lbl = f"{r['label']}-{v:.0f}자"
            ax.annotate(lbl, (i, v), textcoords='offset points', xytext=(0,8),
                        ha='center', fontsize=fs, color='#333')

        ax.set_title(title, fontsize=13, fontweight='bold', color='#111', pad=8)
        ax.set_ylabel(ylabel, fontsize=10)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.tick_params(labelsize=9)

    axes[-1].set_xticks(x)
    axes[-1].set_xticklabels(labels, rotation=45, ha='right', fontsize=9)
    axes[-1].set_xlabel('챕터', fontsize=10)
    fig.tight_layout(pad=2.5)

    # PNG bytes
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=100, facecolor='#FAFAF8', bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue(), rows

def run_step5_characters(chapters, char_names_input):
    """사용자가 입력한 인물 이름으로 챕터별 등장 빈도 추적"""
    names = [n.strip() for n in re.split(r'[,，\s]+', char_names_input) if n.strip()]
    if not names:
        return None, []

    # 각 인물의 챕터별 등장 횟수
    data = {}  # name → {ch_label: count}
    for name in names:
        data[name] = {}
        for ch_name in sorted(chapters.keys(), key=ch_sort):
            cnt = chapters[ch_name].count(name)
            if cnt > 0:
                data[name][ch_label(ch_name)] = cnt

    # 공동 등장 챕터 (두 인물이 같은 챕터에 등장)
    all_ch_labels = sorted({ch_label(c) for c in chapters.keys()}, key=lambda x: ch_sort(x+'0'))
    co_appear = defaultdict(int)
    for i, n1 in enumerate(names):
        for n2 in names[i+1:]:
            shared = set(data[n1].keys()) & set(data[n2].keys())
            co_appear[(n1,n2)] = len(shared)

    return data, all_ch_labels, co_appear

def run_step6_ai_suggest(chapters, api_key, model='claude-haiku-4-5-20251001'):
    """STEP 6: Claude API로 반복 표현 진단 + 대안 제안"""
    from step1_frequency_check import (
        find_repeated_endings, find_connective_patterns,
        find_descriptive_cliches, find_narration_verbs
    )
    all_text = '\n'.join(chapters.values())
    patterns = {}
    for fn in [find_repeated_endings, find_connective_patterns, find_descriptive_cliches, find_narration_verbs]:
        for p, c in fn(all_text).items():
            if c >= 3:
                patterns[p] = c

    if not patterns:
        return {}

    # 컨텍스트 수집
    sents = re.split(r'[.!?]\s+', all_text.replace('\n',' '))
    sents = [s.strip() for s in sents if len(s.strip()) > 10]

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    results = {}
    items   = sorted(patterns.items(), key=lambda x: -x[1])[:20]
    progress = st.progress(0, text="AI 분석 중...")

    for idx, (p, cnt) in enumerate(items):
        ctx = [s for s in sents if p in s][:3]
        ctx_text = '\n'.join(f'- {s[:120]}' for s in ctx)
        try:
            resp = client.messages.create(
                model=model, max_tokens=150,
                messages=[{"role":"user","content":
                    f"""소설에서 '{p}'이(가) {cnt}회 반복됩니다.
실제 문장:
{ctx_text}

아래 형식으로만 답하세요:
진단: (한 줄)
대안: 대체어1 / 대체어2 / 대체어3"""}]
            )
            results[p] = {'count': cnt, 'response': resp.content[0].text.strip(), 'contexts': ctx}
        except Exception as e:
            results[p] = {'count': cnt, 'response': f'오류: {e}', 'contexts': ctx}
        progress.progress((idx+1)/len(items), text=f"AI 분석 중... ({idx+1}/{len(items)})")

    progress.empty()
    return results


# ════════════════════════════════════════════════════════════
# 사이드바
# ════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown('<div style="font-family:Georgia,serif;font-size:1.05rem;'
                'letter-spacing:.15em;border-bottom:1px solid #ccc;'
                'padding-bottom:10px;margin-bottom:14px;color:#111">NOVELDESK</div>',
                unsafe_allow_html=True)

    # ── 새 소설 시작 버튼 (소설 이름 위) ──
    if st.button("새 소설 시작 (초기화)", use_container_width=True):
        for k in list(st.session_state.keys()):
            if k not in ('proj', 'api_key'):
                del st.session_state[k]
        st.rerun()

    st.markdown("---")
    project_name = st.text_input("소설 이름", placeholder="예: 우도", key="proj")

    st.markdown("#### 원고 업로드")
    st.caption("TXT · DOCX · PDF | 한 파일에 전권 OK — 제N화 패턴 자동 분리")
    uploaded = st.file_uploader("파일 선택", type=['txt','docx','pdf'],
                                accept_multiple_files=True, label_visibility="collapsed")

    st.markdown("---")
    st.markdown("#### 또는 텍스트 붙여넣기")
    paste_title = st.text_input("챕터 이름", placeholder="제1화", key="ptitle")
    paste_text  = st.text_area("원고 붙여넣기", height=100,
                               placeholder="텍스트를 여기에 붙여넣으세요", key="ptext",
                               label_visibility="collapsed")
    if st.button("붙여넣기 등록", use_container_width=True):
        if paste_text.strip():
            if 'chapters' not in st.session_state:
                st.session_state.chapters = {}
            t = paste_title.strip() or '원고'
            st.session_state.chapters[f'{t}.txt'] = paste_text.strip()
            st.success(f"'{t}' 등록!")

    st.markdown("---")
    st.markdown("#### Claude API 키 (STEP 6 전용)")
    api_key_input = st.text_input("API Key", type="password",
                                  placeholder="sk-ant-...",
                                  help="STEP 6 AI 분석에만 사용. STEP 1-5는 불필요.",
                                  key="api_key")
    if api_key_input:
        st.caption("✅ API 키 입력됨 — STEP 6 사용 가능")
    else:
        st.caption("STEP 1~5는 API 키 없이 무료 사용 가능")

    st.markdown("---")
    st.markdown("""
    <div style="font-size:.72rem;color:#666;line-height:1.8">
    ✅ TXT — 텍스트 파일<br>
    ✅ DOCX — 워드 (전권 가능)<br>
    ✅ PDF — PDF 문서<br>
    🔜 HWP/HWPX → DOCX로 변환 후<br>
    🔜 Google Docs → DOCX 저장 후
    </div>
    """, unsafe_allow_html=True)

    if IS_LOCAL:
        st.markdown("---")
        st.caption(f"💾 로컬 저장: `{LOCAL_PROJECTS}`")

# ── 파일 처리 ──
if uploaded:
    ch, errs = process_files(uploaded)
    if ch:
        if 'chapters' not in st.session_state:
            st.session_state.chapters = {}
        st.session_state.chapters.update(ch)
    for e in errs:
        st.sidebar.error(e)

chapters  = st.session_state.get('chapters', {})
proj_name = (project_name or 'untitled').strip()

# ════════════════════════════════════════════════════════════
# 메인
# ════════════════════════════════════════════════════════════

st.markdown('<div class="nd-logo">NOVELDESK</div>', unsafe_allow_html=True)
st.markdown('<div class="nd-sub">한국어 소설 반복 표현 탐지 & 분석 — 개인 전용</div>',
            unsafe_allow_html=True)

# ── 원고 없을 때 안내 ──
if not chapters:
    st.markdown("---")
    col1, col2 = st.columns([1.1, 1])
    with col1:
        st.markdown("### 시작 방법")
        for num, title, body in [
            (1, "소설 이름 입력", "왼쪽 사이드바에 소설 제목을 입력하세요."),
            (2, "원고 업로드",
             "TXT, DOCX, PDF를 업로드하세요.<br>"
             "<b>전체 원고가 DOCX 하나?</b> 그대로 올리면 됩니다.<br>"
             "'제1화', '제2화'... 패턴이 있으면 자동으로 챕터를 나눠줍니다.<br>"
             "별도 챕터 폴더를 만들 필요 없습니다."),
            (3, "STEP 실행",
             "원고가 등록되면 STEP 1~6 버튼이 나타납니다.<br>"
             "순서대로 실행하거나 원하는 STEP만 골라 실행하세요."),
        ]:
            st.markdown(f"""
            <div style="border-left:3px solid #C41E1E;padding:10px 16px;
                        margin-bottom:12px;background:#fff">
              <div style="font-family:Georgia;font-size:1.1rem;color:#C41E1E">{num}</div>
              <div style="font-weight:800;font-size:.92rem">{title}</div>
              <div style="font-size:.81rem;color:#444;line-height:1.65">{body}</div>
            </div>""", unsafe_allow_html=True)

    with col2:
        st.markdown("### 각 STEP 설명")
        items = [
            (1, "FREE", "반복 표현 탐지",
             "책 전체 텍스트를 하나로 합쳐서 AI 의심 패턴, 반복 종결어, 묘사 클리셰, 대화 서술동사를 찾습니다."),
            (2, "FREE", "챕터 간 비교 + Excel 저장",
             "챕터별로 따로 분석해서 2개 이상 챕터에 반복되는 표현만 걸러냅니다. "
             "가나다 순 정렬 + 유의어 3개 추천 → Excel 파일로 저장."),
            (3, "FREE", "직급·계급 체크",
             "군계급·직장직급이 챕터 순서상 역행하는지 확인합니다."),
            (4, "FREE", "페이싱 차트",
             "챕터별 글자수·문장길이·대화비중을 큰 그래프로 시각화합니다. (2000px 이상)"),
            (5, "FREE", "인물 등장 추적",
             "인물 이름을 직접 입력하면 챕터별 등장 횟수와 공동 등장 관계를 보여줍니다."),
            (6, "AI", "AI 반복 표현 진단",
             "Claude AI가 각 반복 표현의 진단과 대안 표현 3개를 제안합니다. API 키 필요."),
        ]
        for num, badge, name, desc in items:
            bc = '#ECF7EF' if badge=='FREE' else '#FFF0F0'
            fc = '#2A6A3A' if badge=='FREE' else '#C41E1E'
            st.markdown(f"""
            <div style="display:flex;gap:10px;align-items:flex-start;
                        margin-bottom:8px;padding:8px 10px;background:#fff;
                        border:1px solid #E0E0DC;border-radius:5px">
              <div style="font-family:Georgia;font-size:1.2rem;min-width:24px;
                          color:#111;line-height:1.3">{num}</div>
              <div>
                <span style="font-weight:800;font-size:.86rem">{name}</span>
                <span style="font-size:.65rem;font-weight:700;padding:1px 7px;
                             border-radius:20px;background:{bc};color:{fc};
                             margin-left:6px">{badge}</span>
                <div style="font-size:.76rem;color:#666;line-height:1.55;
                            margin-top:2px">{desc}</div>
              </div>
            </div>""", unsafe_allow_html=True)

    with st.expander("HWP 파일 → TXT/DOCX 변환 방법"):
        st.markdown("""
        **한글(HWP) 프로그램에서:**
        1. 파일 → 다른 이름으로 저장
        2. 파일 형식: **MS 워드 (*.docx)** 또는 **텍스트 문서 (*.txt)**
        3. 저장 후 NOVELDESK에 업로드
        """)
    st.stop()

# ── 현황 요약 ──
sorted_chapters = sorted(chapters.keys(), key=ch_sort)
total_chars = sum(len(re.sub(r'\s','',t)) for t in chapters.values())
report_dir  = make_report_dir(proj_name) if IS_LOCAL else None

c1, c2, c3 = st.columns(3)
c1.metric("프로젝트", proj_name)
c2.metric("전체 글자수", f"{total_chars:,}자")
c3.metric("챕터 수", f"{len(chapters)}개")

ch_preview = ', '.join(ch_label(c) for c in sorted_chapters[:12])
if len(chapters) > 12:
    ch_preview += f" 외 {len(chapters)-12}개"
st.caption(f"등록 챕터: {ch_preview}")

if IS_LOCAL and report_dir:
    st.caption(f"💾 결과 자동 저장 위치: `{report_dir}`")

st.markdown("---")
st.markdown("## STEP 1–5 &nbsp; 무료 분석")


# ════════════════════════════════════════════════════════════
# STEP 1 — 반복 표현 탐지 (책 전체)
# ════════════════════════════════════════════════════════════

with st.expander("**STEP 1 — 반복 표현 탐지** &nbsp;|&nbsp; 책 전체 패턴 탐지 (API 불필요)"):
    st.markdown("""
    책 전체 텍스트를 **하나로 합쳐서** 반복 표현을 탐지합니다.
    - **[B]** AI 의심 종결어: `듯했다`, `것 같았다`, `문득` 등
    - **[C]** 접속·대조 구조: `지만`, `그러나`, `하지만` 등
    - **[D]** 묘사 클리셰: `텅 빈`, `공허한` 등
    - **[E]** 대화 서술동사: `말했다`, `외쳤다` 등
    - **[F]** 행동 묘사 클리셰: `발길을 재촉했다` 류

    > **STEP 1 vs STEP 2 차이:** STEP 1은 "책 전체에서 몇 번"을 셉니다.
    > STEP 2는 "어느 챕터에서 몇 번씩"인지를 비교해서
    > **2개 이상 챕터에 걸쳐 반복되는 것만** 걸러냅니다 — 이것이 진짜 습관적 패턴입니다.
    """)

    if st.button("STEP 1 실행", key="r1", type="primary"):
        with st.spinner("분석 중..."):
            try:
                r = run_step1(chapters)
                st.session_state.s1 = r
                st.success(f"완료 — {r['chapter_count']}개 챕터 · {r['total_chars']:,}자")
            except Exception as e:
                st.error(f"오류: {e}")

    if 'S1' in {k.upper() for k in st.session_state} and 's1' in st.session_state:
        import pandas as pd
        r = st.session_state.s1
        cols = st.columns(3)
        cols[0].metric("챕터", r['chapter_count'])
        cols[1].metric("글자수", f"{r['total_chars']:,}")
        total_found = sum(len(v) for k,v in r.items() if k in 'BCDEF')
        cols[2].metric("발견 패턴", f"{total_found}종")

        cat_labels = {'B':'[B] AI 의심 종결어','C':'[C] 접속·대조','D':'[D] 묘사 클리셰',
                      'E':'[E] 대화 서술동사','F':'[F] 행동 클리셰'}
        all_rows = []
        for k, lbl in cat_labels.items():
            items = sorted(r.get(k,{}).items(), key=lambda x:-x[1])
            for p, c in items:
                all_rows.append({'카테고리':lbl,'표현':p,'횟수':c})
        if all_rows:
            df = pd.DataFrame(all_rows)
            st.dataframe(df, use_container_width=True, hide_index=True)

            # 저장
            json_bytes = json.dumps(r, ensure_ascii=False, indent=2).encode('utf-8')
            st.download_button("⬇ STEP1 결과 JSON 저장", json_bytes,
                               f"step1_{proj_name}.json", "application/json")
            save_local(report_dir, f"step1_{proj_name}.json", json_bytes)


# ════════════════════════════════════════════════════════════
# STEP 2 — 챕터 간 비교 + Excel (가나다 순 + 유의어)
# ════════════════════════════════════════════════════════════

with st.expander("**STEP 2 — 챕터 간 비교 + Excel 저장** &nbsp;|&nbsp; 가나다 순 · 유의어 3개"):
    st.markdown("""
    **챕터별로 따로 분석**해서 2개 이상 챕터에 반복되는 표현만 추출합니다.
    결과를 **가나다 순**으로 정렬하고 **유의어 3개**를 함께 Excel로 저장합니다.

    Excel 열 구성: `표현 | 카테고리 | 등장챕터수 | 총횟수 | 챕터별분포 | 실제문장 | 유의어추천`

    - **무료 유의어**: 내장 사전 (즉시, API 불필요)
    - **AI 유의어**: 사이드바에 API 키 입력 → 체크박스 활성화
    """)

    use_api_synonyms = False
    if st.session_state.get('api_key'):
        use_api_synonyms = st.checkbox("Claude AI 유의어 사용 (API 키 필요, 소량 비용 발생)", value=False)

    if st.button("STEP 2 실행 + Excel 생성", key="r2", type="primary"):
        with st.spinner("챕터 간 비교 중 + Excel 생성 중..."):
            try:
                xlsx_bytes, n = run_step2_excel(
                    chapters,
                    use_api=use_api_synonyms,
                    api_key=st.session_state.get('api_key','')
                )
                st.session_state.s2_xlsx = xlsx_bytes
                st.session_state.s2_count = n
                save_local(report_dir, f"분석리포트_{proj_name}.xlsx", xlsx_bytes)
                st.success(f"완료 — 전 챕터 반복 표현 {n}종")
            except Exception as e:
                st.error(f"오류: {e}")
                import traceback; st.code(traceback.format_exc())

    if 's2_xlsx' in st.session_state:
        st.success(f"전 챕터 반복 패턴 {st.session_state.s2_count}종 → Excel 준비됨")
        st.download_button(
            "⬇ Excel 다운로드 (가나다 순 · 유의어 포함)",
            st.session_state.s2_xlsx,
            f"분석리포트_{proj_name}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        if IS_LOCAL and report_dir:
            st.caption(f"💾 자동 저장됨: `{report_dir / f'분석리포트_{proj_name}.xlsx'}`")


# ════════════════════════════════════════════════════════════
# STEP 3 — 직급·계급 체크
# ════════════════════════════════════════════════════════════

with st.expander("**STEP 3 — 직급·계급·직책 체크** &nbsp;|&nbsp; 챕터 순서 역행 탐지"):
    st.markdown("""
    군계급(이병→일병→상병→병장) 또는 직장직급(사원→대리→과장→부장)이
    챕터 진행상 역행하는 경우를 찾습니다.
    계급 체계가 없는 소설은 이 STEP을 건너뛰세요.
    """)

    ranks_input = st.text_input(
        "계급 순서 (낮은 → 높은, 쉼표 구분)",
        placeholder="예: 이병,일병,상병,병장  또는  사원,대리,과장,부장,사장",
        key="ranks"
    )
    if st.button("STEP 3 실행", key="r3", type="primary"):
        if not ranks_input.strip():
            st.warning("계급 순서를 입력하거나, 없으면 건너뛰세요.")
        else:
            ranks = [r.strip() for r in ranks_input.split(',') if r.strip()]
            with st.spinner("직급 체크 중..."):
                try:
                    r = run_step3(chapters, ranks)
                    st.session_state.s3 = r
                    n = len(r['regressions'])
                    st.success(f"완료 — {'역행 의심 ' + str(n) + '건' if n else '이상 없음'}")
                except Exception as e:
                    st.error(f"오류: {e}")

    if 's3' in st.session_state:
        import pandas as pd
        r = st.session_state.s3
        st.markdown("---")
        if r['regressions']:
            st.markdown('<div class="warn">아래 항목을 직접 확인하세요. 회상 장면이나 동명이인일 수 있습니다.</div>',
                        unsafe_allow_html=True)
            for iss in r['regressions']:
                st.error(f"**{iss['name']}**: {iss['prev_rank']}({iss['prev_ch']}화) → "
                         f"{iss['curr_rank']}({iss['curr_ch']}화)  _{iss.get('sentence','')[:80]}_")
        else:
            st.markdown('<div class="ok">계급 역행 없음 — 이상 없습니다</div>', unsafe_allow_html=True)

        if r.get('timeline'):
            rows = [{'인물':name,'챕터':f'{ch}화','계급':rank}
                    for name, refs in r['timeline'].items()
                    for ch,rank,_ in refs]
            if rows:
                st.markdown("**인물별 계급 타임라인**")
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════════════════
# STEP 4 — 페이싱 차트 (2000px 이상, A4 비율)
# ════════════════════════════════════════════════════════════

with st.expander("**STEP 4 — 페이싱 차트** &nbsp;|&nbsp; 글자수·문장길이·대화비중 그래프"):
    st.markdown("""
    챕터별 3가지 지표를 **큰 그래프(2000px 이상, A4 비율)**로 시각화합니다.
    각 꼭지점에 "N화-수치" 라벨이 표시됩니다.
    평균선(회색 점선)에서 크게 벗어난 챕터를 검토해보세요.
    """)

    if st.button("STEP 4 실행", key="r4", type="primary"):
        with st.spinner("차트 생성 중..."):
            try:
                png_bytes, rows = run_step4_chart(chapters)
                if png_bytes:
                    st.session_state.s4_png  = png_bytes
                    st.session_state.s4_rows = rows
                    save_local(report_dir, f"페이싱차트_{proj_name}.png", png_bytes)
                    st.success(f"완료 — {len(rows)}개 챕터")
            except Exception as e:
                st.error(f"오류: {e}")
                import traceback; st.code(traceback.format_exc())

    if 's4_png' in st.session_state:
        import pandas as pd
        st.image(st.session_state.s4_png, use_container_width=True)
        st.download_button("⬇ 차트 PNG 다운로드 (고해상도)",
                           st.session_state.s4_png,
                           f"페이싱차트_{proj_name}.png", "image/png")
        if IS_LOCAL and report_dir:
            st.caption(f"💾 자동 저장됨: `{report_dir / f'페이싱차트_{proj_name}.png'}`")

        rows = st.session_state.s4_rows
        df = pd.DataFrame([{'챕터':r['label'],'글자수':f"{r['chars']:,}",
                             '문장평균길이':f"{r['sent_mean']:.1f}자",
                             '대화비중':f"{r['dia']:.1f}%"} for r in rows])
        st.dataframe(df, use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════════════════
# STEP 5 — 인물 등장 추적 (이름 직접 입력)
# ════════════════════════════════════════════════════════════

with st.expander("**STEP 5 — 인물 등장 추적** &nbsp;|&nbsp; 인물 이름 입력 → 챕터별 등장 횟수"):
    st.markdown("""
    분석하고 싶은 **인물 이름을 직접 입력**하면,
    각 인물이 어느 챕터에 몇 번 등장했는지, 두 인물이 같이 등장한 챕터는 어디인지 보여줍니다.

    예: `강민준, 서하은, 이대리, 최부장`
    """)

    char_input = st.text_input("인물 이름 (쉼표 또는 공백으로 구분)",
                               placeholder="예: 강민준, 서하은, 이대리",
                               key="char_names")

    if st.button("STEP 5 실행", key="r5", type="primary"):
        if not char_input.strip():
            st.warning("인물 이름을 입력해주세요.")
        else:
            with st.spinner("인물 추적 중..."):
                try:
                    result = run_step5_characters(chapters, char_input)
                    if result and result[0]:
                        st.session_state.s5 = result
                        data, all_labels, co = result
                        st.success(f"완료 — {len(data)}명 추적")
                    else:
                        st.warning("이름을 찾을 수 없습니다. 소설에 실제로 등장하는 이름인지 확인하세요.")
                except Exception as e:
                    st.error(f"오류: {e}")

    if 's5' in st.session_state:
        import pandas as pd
        data, all_labels, co = st.session_state.s5
        names = list(data.keys())

        st.markdown("---")
        st.markdown("**챕터별 등장 횟수**")
        # 인물 카드
        cols = st.columns(min(len(names), 5))
        for i, name in enumerate(names):
            total = sum(data[name].values())
            ch_cnt = len(data[name])
            with cols[i % len(cols)]:
                st.markdown(f"""
                <div class="char-card">
                  <div class="char-name">{name}</div>
                  <div class="char-cnt">{total}회</div>
                  <div style="font-size:.72rem;color:#888">{ch_cnt}개 챕터</div>
                </div>""", unsafe_allow_html=True)

        # 챕터 × 인물 매트릭스
        matrix = []
        for ch in all_labels:
            row = {'챕터': ch}
            for name in names:
                row[name] = data[name].get(ch, 0)
            matrix.append(row)
        df = pd.DataFrame(matrix)
        st.dataframe(df, use_container_width=True, hide_index=True)

        # 공동 등장 관계
        if co:
            st.markdown("**공동 등장 챕터 수** (두 인물이 같은 챕터에 나오는 경우)")
            co_rows = [{'인물 A': a, '인물 B': b, '공동 등장 챕터 수': n}
                       for (a,b),n in sorted(co.items(), key=lambda x:-x[1]) if n > 0]
            if co_rows:
                st.dataframe(pd.DataFrame(co_rows), use_container_width=True, hide_index=True)

        # 저장
        json_bytes = json.dumps({'characters': {n: data[n] for n in names}},
                                ensure_ascii=False, indent=2).encode('utf-8')
        st.download_button("⬇ 인물 추적 결과 JSON 저장", json_bytes,
                           f"인물추적_{proj_name}.json", "application/json")
        save_local(report_dir, f"인물추적_{proj_name}.json", json_bytes)


st.markdown("---")
st.markdown("## STEP 6 &nbsp; AI 분석")


# ════════════════════════════════════════════════════════════
# STEP 6 — AI 반복 표현 진단
# ════════════════════════════════════════════════════════════

with st.expander("**STEP 6 — AI 반복 표현 진단** &nbsp;|&nbsp; Claude AI 진단 + 대안 표현"):
    st.markdown("""
    STEP 1~2에서 찾은 반복 표현을 Claude AI가 직접 읽고
    **진단(왜 문제인지) + 대안 표현 3개**를 제안합니다.

    - 모델: `claude-haiku` (가장 저렴, 빠름)
    - 비용: 표현 20개 기준 약 $0.01~$0.05 (약 15~70원)
    - **사이드바에 API 키 입력 필요**

    > 💡 Claude Code 구독자라면 Claude Code 터미널에서 `step4_api_suggestions.py`를
    > 실행하면 **API 비용 없이** 동일한 분석이 가능합니다.
    """)

    if not st.session_state.get('api_key'):
        st.markdown('<div class="warn">왼쪽 사이드바에 Claude API 키를 입력해야 실행할 수 있습니다.</div>',
                    unsafe_allow_html=True)
    else:
        if st.button("STEP 6 실행 (AI 분석)", key="r6", type="primary"):
            with st.spinner("Claude AI 분석 중..."):
                try:
                    result = run_step6_ai_suggest(chapters, st.session_state.api_key)
                    st.session_state.s6 = result
                    st.success(f"완료 — {len(result)}개 표현 진단")
                except Exception as e:
                    st.error(f"오류: {e}")

    if 's6' in st.session_state:
        import pandas as pd
        result = st.session_state.s6
        st.markdown("---")
        rows = []
        for p, info in result.items():
            rows.append({'표현': p, '횟수': info['count'], 'AI 진단 + 대안': info['response']})
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

        # Excel 저장
        try:
            import openpyxl
            from openpyxl.styles import Font, Alignment
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = 'AI진단'
            ws.append(['표현', '횟수', 'AI 진단 + 대안', '실제 문장 예시'])
            ws.column_dimensions['A'].width = 18
            ws.column_dimensions['C'].width = 50
            ws.column_dimensions['D'].width = 60
            for p, info in result.items():
                ctx = ' | '.join(info.get('contexts',[])[:2])
                ws.append([p, info['count'], info['response'], ctx])
            for row in ws.iter_rows(min_row=2):
                for cell in row:
                    cell.alignment = Alignment(wrap_text=True, vertical='top')
            buf = io.BytesIO(); wb.save(buf)
            xlsx_bytes = buf.getvalue()
            st.download_button("⬇ AI 진단 Excel 저장", xlsx_bytes,
                               f"AI진단_{proj_name}.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            save_local(report_dir, f"AI진단_{proj_name}.xlsx", xlsx_bytes)
        except Exception:
            pass


st.markdown("---")
st.markdown("## STEP 7–10 &nbsp; 고급 AI 분석 (준비 중)")

for num, name, desc in [
    (7, "복선 탐지",     "전반부에서 회수되어야 할 설정·암시·약속을 AI가 찾아냅니다."),
    (8, "복선 회수 확인","앞에서 찾은 복선이 후반부에서 실제로 회수됐는지 확인합니다."),
    (9, "페이싱 AI 판단","이상 챕터만 골라 AI가 의도된 것인지 판단합니다."),
    (10,"출판 자료",     "소개글·줄거리·인물 소개 등 출판사 제출용 자료를 생성합니다."),
]:
    with st.expander(f"**STEP {num} — {name}** &nbsp;|&nbsp; 준비 중"):
        st.markdown(f"**{desc}**")
        st.caption("곧 추가됩니다.")
        st.button(f"STEP {num} 실행", key=f"r{num}", disabled=True)

st.markdown("---")
st.markdown('<div style="text-align:center;font-size:.72rem;color:#BBB;padding:16px">'
            'NOVELDESK — 개인 전용 소설 분석 도구</div>', unsafe_allow_html=True)
