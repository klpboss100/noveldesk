# app.py — NOVELDESK 웹앱의 심장부
#
# Flask란? 파이썬으로 웹 서버를 만들어주는 도구입니다.
# 쉽게 말해: 인터넷 브라우저와 우리 파이썬 코드를 연결해주는 다리입니다.
#
# 실행 방법:
#   1. 이 파일이 있는 폴더(web/)에서 터미널을 연다
#   2. pip install flask 를 입력해서 Flask 설치
#   3. python app.py 를 입력하면 서버 시작
#   4. 브라우저에서 http://127.0.0.1:5000 열기
#
# 127.0.0.1 이란? 내 컴퓨터 안에서만 접속되는 주소입니다.
# 인터넷에 공개되지 않으니 개인 전용으로 안전합니다.

import os
import sys
import json
import glob
import re
import shutil
import statistics
from collections import defaultdict, Counter
from pathlib import Path
from flask import (
    Flask, render_template, request,
    redirect, url_for, session, jsonify, send_from_directory
)

# ── 앱 기본 설정 ──────────────────────────────────────
app = Flask(__name__)
app.secret_key = 'noveldesk-personal-2026'  # 세션 암호화용 (개인 전용이라 간단히)

# 파일 저장 폴더 (이 파일 기준 상대 경로)
BASE_DIR   = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / 'uploads'
ENGINE_DIR = BASE_DIR.parent / 'engine'

# engine 폴더를 파이썬 경로에 추가 (기존 분석 코드를 import 하기 위해)
sys.path.insert(0, str(ENGINE_DIR))

app.config['UPLOAD_FOLDER'] = str(UPLOAD_DIR)
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 최대 200MB

# 지원 파일 형식
ALLOWED_EXTENSIONS = {'txt', 'docx', 'hwpx', 'hwp', 'pdf'}


# ── 유틸리티 함수 ──────────────────────────────────────

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_current_project():
    return session.get('project', None)

def get_project_stats(project_name):
    project_dir = BASE_DIR / 'uploads' / project_name
    stats = {
        'chapter_count': 0,
        'completed_steps': [],
        'results': {}
    }
    if not project_dir.exists():
        return stats

    txt_files = list((project_dir / 'chapters').glob('*.txt')) if (project_dir / 'chapters').exists() else []
    stats['chapter_count'] = len(txt_files)

    for step_num in range(1, 6):
        result_file = project_dir / f'step{step_num}_result.json'
        if result_file.exists():
            stats['completed_steps'].append(step_num)

    return stats


def load_txt_chapters(chapters_dir):
    """챕터 폴더에서 모든 txt 파일을 읽어서 {파일명: 텍스트} 형태로 반환"""
    chapters = {}
    paths = sorted(glob.glob(str(chapters_dir / '*.txt')), key=lambda p: _chapter_sort_key(os.path.basename(p)))
    for path in paths:
        with open(path, encoding='utf-8') as f:
            chapters[os.path.basename(path)] = f.read()
    return chapters

def _chapter_sort_key(filename):
    m = re.search(r'(\d+)', filename)
    return int(m.group(1)) if m else 0

def _chapter_label(filename):
    m = re.search(r'(\d+)', filename)
    return f"{int(m.group(1))}화" if m else filename


# ── 라우트(페이지) 정의 ────────────────────────────────

@app.route('/')
def index():
    project = get_current_project()
    stats = {}
    if project:
        stats = get_project_stats(project['name'])
    return render_template('index.html', project=project, stats=stats)


@app.route('/upload', methods=['POST'])
def upload():
    if 'files' not in request.files:
        return redirect(url_for('index'))

    files = request.files.getlist('files')
    project_name = request.form.get('project_name', '').strip()

    if not project_name:
        return redirect(url_for('index'))

    project_dir = UPLOAD_DIR / project_name / 'chapters'
    project_dir.mkdir(parents=True, exist_ok=True)

    saved_count = 0
    for file in files:
        if file and file.filename and allowed_file(file.filename):
            filename = file.filename
            file.save(str(project_dir / filename))
            saved_count += 1

    session['project'] = {
        'name': project_name,
        'dir': str(UPLOAD_DIR / project_name)
    }

    return redirect(url_for('index'))


@app.route('/paste', methods=['POST'])
def paste():
    project_name = request.form.get('project_name', '').strip()
    content      = request.form.get('content', '').strip()
    chapter_name = request.form.get('chapter_name', '원고').strip()

    if not project_name or not content:
        return redirect(url_for('index'))

    project_dir = UPLOAD_DIR / project_name / 'chapters'
    project_dir.mkdir(parents=True, exist_ok=True)

    file_path = project_dir / f'{chapter_name}.txt'
    file_path.write_text(content, encoding='utf-8')

    session['project'] = {
        'name': project_name,
        'dir': str(UPLOAD_DIR / project_name)
    }

    return redirect(url_for('index'))


@app.route('/run-step/<int:step_num>', methods=['POST'])
def run_step(step_num):
    project = get_current_project()
    if not project:
        return jsonify({'error': '먼저 원고를 업로드해주세요.'}), 400

    project_dir  = Path(project['dir'])
    chapters_dir = project_dir / 'chapters'

    if not chapters_dir.exists():
        return jsonify({'error': '챕터 폴더를 찾을 수 없습니다.'}), 400

    txt_files = list(chapters_dir.glob('*.txt'))
    if not txt_files:
        return jsonify({'error': '.txt 챕터 파일이 없습니다. TXT 형식으로 업로드해주세요.'}), 400

    try:
        result = _run_engine_step(step_num, chapters_dir, project_dir)
        return jsonify({'success': True, 'step': step_num, 'result': result})
    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'detail': traceback.format_exc()}), 500


def _run_engine_step(step_num, chapters_dir, output_dir):
    """각 STEP별 분석 실행 후 결과를 JSON으로 저장하고 요약 반환"""

    if step_num == 1:
        return _run_step1(chapters_dir, output_dir)
    elif step_num == 2:
        return _run_step2(chapters_dir, output_dir)
    elif step_num == 3:
        return _run_step3(chapters_dir, output_dir)
    elif step_num == 4:
        return _run_step4(chapters_dir, output_dir)
    elif step_num == 5:
        return _run_step5(chapters_dir, output_dir)
    else:
        return {'message': f'STEP {step_num}은 아직 준비 중입니다.'}


# ── STEP 1: 반복 표현 탐지 ──────────────────────────────

def _run_step1(chapters_dir, output_dir):
    from step1_frequency_check import (
        find_repeated_endings, find_connective_patterns,
        find_descriptive_cliches, find_narration_verbs, find_action_cliches
    )

    chapters = load_txt_chapters(chapters_dir)
    if not chapters:
        raise ValueError('분석할 챕터가 없습니다.')

    # 전체 텍스트를 합쳐서 분석 (책 전체 기준)
    all_text = '\n'.join(chapters.values())

    result = {
        'chapter_count': len(chapters),
        'total_chars': len(re.sub(r'\s', '', all_text)),
        'B_endings':    find_repeated_endings(all_text),
        'C_connectives': find_connective_patterns(all_text),
        'D_cliches':    find_descriptive_cliches(all_text),
        'E_verbs':      find_narration_verbs(all_text),
        'F_action':     find_action_cliches(all_text),
    }

    # 총 발견 건수 계산
    total_found = sum(
        len(v) for k, v in result.items()
        if k.startswith(('B_', 'C_', 'D_', 'E_', 'F_'))
    )
    result['total_found'] = total_found

    out_path = output_dir / 'step1_result.json'
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')

    return {'found': total_found, 'chapters': len(chapters), 'message': f'반복 표현 {total_found}종 발견'}


# ── STEP 2: 챕터 간 비교 ───────────────────────────────

def _run_step2(chapters_dir, output_dir):
    from step1_frequency_check import (
        find_repeated_endings, find_connective_patterns,
        find_descriptive_cliches, find_narration_verbs, find_action_cliches
    )

    chapters = load_txt_chapters(chapters_dir)
    if not chapters:
        raise ValueError('분석할 챕터가 없습니다.')

    detectors = [
        ('B_endings', '종결어/AI 패턴', find_repeated_endings),
        ('C_connectives', '접속·대조 구조', find_connective_patterns),
        ('D_cliches', '묘사 클리셰', find_descriptive_cliches),
        ('E_verbs', '대화 서술동사', find_narration_verbs),
        ('F_action', '행동 묘사 클리셰', find_action_cliches),
    ]

    result = {'chapter_count': len(chapters), 'categories': {}}

    for key, label, detector_fn in detectors:
        combined = defaultdict(dict)
        for chapter_name, text in chapters.items():
            found = detector_fn(text)
            for pattern, count in found.items():
                combined[pattern][chapter_name] = count

        multi = {p: d for p, d in combined.items() if len(d) >= 2}
        single = {p: d for p, d in combined.items() if len(d) == 1}

        # 정렬: 등장 챕터 수 내림차순, 총 횟수 내림차순
        multi_sorted = sorted(multi.items(), key=lambda x: (-len(x[1]), -sum(x[1].values())))
        single_sorted = sorted(single.items(), key=lambda x: -sum(x[1].values()))

        result['categories'][key] = {
            'label': label,
            'multi': [{'pattern': p, 'chapters': d, 'total': sum(d.values())} for p, d in multi_sorted],
            'single': [{'pattern': p, 'chapters': d, 'total': sum(d.values())} for p, d in single_sorted],
        }

    total_multi = sum(len(cat['multi']) for cat in result['categories'].values())
    result['total_multi'] = total_multi

    out_path = output_dir / 'step2_result.json'
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')

    return {'found': total_multi, 'chapters': len(chapters), 'message': f'전 챕터 반복 표현 {total_multi}종'}


# ── STEP 3: 직급·계급·직책 체크 ──────────────────────────

def _run_step3(chapters_dir, output_dir):
    # world.json에서 rank_system 읽기 시도
    # 웹 앱은 uploads/<name>/ 구조이므로 story_bible 폴더 위치 확인
    world_json_path = output_dir / 'story_bible' / 'world.json'
    ranks = None
    if world_json_path.exists():
        try:
            world = json.loads(world_json_path.read_text(encoding='utf-8'))
            ranks = world.get('rank_system', {}).get('order', None)
        except Exception:
            pass

    result = {'has_rank_system': ranks is not None}

    if not ranks:
        result['message'] = 'world.json에 rank_system이 없습니다. 직급 체계가 없는 소설이면 이 STEP은 건너뛰세요.'
        result['regressions'] = []
        result['timeline'] = {}
        out_path = output_dir / 'step3_result.json'
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        return {'found': 0, 'message': '직급 체계 설정 없음 (world.json 확인)'}

    from step5_consistency_check import (
        build_rank_pattern, load_chapters, build_timeline,
        find_regressions, find_intra_chapter_conflicts
    )

    chapters = load_chapters(str(chapters_dir), mode='folder')
    rank_pattern = build_rank_pattern(ranks)
    rank_order = {r: i for i, r in enumerate(ranks)}
    timeline = build_timeline(chapters, rank_pattern)
    regressions = find_regressions(timeline, ranks, rank_order)
    conflicts = find_intra_chapter_conflicts(timeline, rank_order)

    result['ranks'] = ranks
    result['regressions'] = regressions
    result['conflicts'] = conflicts
    result['timeline'] = {
        name: [{'ch': ch, 'rank': rk, 'sentence': s} for ch, rk, s in refs]
        for name, refs in timeline.items()
    }

    out_path = output_dir / 'step3_result.json'
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')

    total_issues = len(regressions) + len(conflicts)
    return {'found': total_issues, 'message': f'검토 필요 항목 {total_issues}건'}


# ── STEP 4: 페이싱 차트 (3개: 글자수, 문장평균길이, 대화비중) ──

def _run_step4(chapters_dir, output_dir):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm

    # 한글 폰트 설정
    candidates = ['Malgun Gothic', 'NanumGothic', 'AppleGothic', 'Noto Sans CJK KR']
    available = {f.name for f in fm.fontManager.ttflist}
    for name in candidates:
        if name in available:
            plt.rcParams['font.family'] = name
            break
    plt.rcParams['axes.unicode_minus'] = False

    from step7_pacing_check import analyze_chapter, chapter_sort_key

    paths = sorted(glob.glob(str(chapters_dir / '*.txt')), key=lambda p: chapter_sort_key(p))
    if not paths:
        raise ValueError('.txt 파일이 없습니다.')

    rows = [analyze_chapter(p) for p in paths]

    # 3개 차트 생성 (장면전환 제외)
    labels = [_chapter_label(r['file']) for r in rows]
    chars_vals = [r['chars'] for r in rows]
    sent_mean_vals = [r['sent_mean'] for r in rows]
    dia_vals = [r['dialogue_ratio'] * 100 for r in rows]

    fig, axes = plt.subplots(3, 1, figsize=(max(10, len(rows) * 0.6 + 2), 12), sharex=True)
    fig.patch.set_facecolor('#FAFAF8')

    colors = ['#1A1A1A', '#C41E1E', '#2A6A3A']
    titles = ['글자수 (공백 제외)', '문장 평균 길이', '대화 비중 (%)']
    data_sets = [chars_vals, sent_mean_vals, dia_vals]
    y_labels_text = ['글자수', '평균 길이(자)', '대화 비중(%)']

    x = list(range(len(rows)))

    for ax, vals, color, title, ylabel in zip(axes, data_sets, colors, titles, y_labels_text):
        ax.set_facecolor('#FFFFFF')
        ax.plot(x, vals, marker='o', color=color, linewidth=1.5, markersize=5)
        avg = statistics.mean(vals)
        ax.axhline(avg, color='#AAAAAA', linestyle='--', linewidth=1)

        # 각 데이터 포인트 라벨 (예: "1화-4200자")
        for i, (v, lbl) in enumerate(zip(vals, labels)):
            if title == '글자수 (공백 제외)':
                point_label = f'{lbl}-{v:,}자'
            elif title == '문장 평균 길이':
                point_label = f'{lbl}-{v:.0f}자'
            else:
                point_label = f'{lbl}-{v:.0f}%'
            ax.annotate(point_label, (i, v),
                        textcoords='offset points', xytext=(0, 7),
                        ha='center', fontsize=7, color='#444444')

        ax.set_title(title, fontsize=11, fontweight='bold', color='#111111', pad=8)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.tick_params(axis='both', labelsize=8)

    axes[-1].set_xticks(x)
    axes[-1].set_xticklabels(labels, rotation=45, ha='right', fontsize=8)
    axes[-1].set_xlabel('챕터', fontsize=9)

    fig.tight_layout(pad=2.0)

    chart_path = output_dir / 'step4_chart.png'
    fig.savefig(str(chart_path), dpi=150, facecolor='#FAFAF8')
    plt.close(fig)

    result = {
        'chapter_count': len(rows),
        'rows': rows,
        'chart_file': 'step4_chart.png',
        'averages': {
            'chars': statistics.mean(chars_vals),
            'sent_mean': statistics.mean(sent_mean_vals),
            'dialogue_ratio': statistics.mean(dia_vals),
        }
    }

    out_path = output_dir / 'step4_result.json'
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')

    return {'chapters': len(rows), 'message': f'{len(rows)}개 챕터 페이싱 차트 생성 완료'}


# ── STEP 5: 인물 관계도 (등장 빈도 기반) ──────────────────

def _run_step5(chapters_dir, output_dir):
    chapters = load_txt_chapters(chapters_dir)
    if not chapters:
        raise ValueError('분석할 챕터가 없습니다.')

    # 2~4글자 한글 단어 중 여러 챕터에 자주 등장하는 것을 인물 후보로 추출
    # (한국어 인물명은 대부분 2~3자)
    word_pattern = re.compile(r'[가-힣]{2,4}')

    # 단어별 챕터 등장 빈도
    word_chapter_counts = defaultdict(lambda: defaultdict(int))
    for ch_name, text in chapters.items():
        label = _chapter_label(ch_name)
        words = word_pattern.findall(text)
        for word in words:
            word_chapter_counts[word][label] += 1

    # 제외할 일반 명사/부사/조사 조각 (자주 등장하지만 인물명이 아닌 것)
    exclude_words = {
        '그는', '그녀', '그가', '그를', '그의', '그녀의', '그녀가', '그녀를',
        '아니', '이제', '그런', '정말', '이런', '하지만', '그래', '그리고',
        '우리', '모두', '자신', '조금', '정도', '생각', '눈길', '시선',
        '목소리', '발걸음', '얼굴', '표정', '눈빛', '마음', '마치', '결국',
        '사실', '기억', '순간', '여전히', '여기', '저기', '거기', '무언가',
        '뭔가', '아무', '어느', '한번', '그때', '지금', '나중', '이미',
        '아직', '오래', '다시', '계속', '혼자', '함께', '천천히', '갑자기',
        '조용히', '가만히', '살짝', '그냥', '항상', '매번', '결코', '전혀',
        '너무', '매우', '정도', '부분', '때문', '경우', '사람', '인간',
        '시간', '공간', '장소', '소리', '느낌', '기분',
    }

    # 2개 이상 챕터에서 10회 이상 등장하는 단어만 인물 후보로
    candidates = {}
    for word, chapter_counts in word_chapter_counts.items():
        if word in exclude_words:
            continue
        if len(chapter_counts) >= 2:
            total = sum(chapter_counts.values())
            if total >= 10:
                candidates[word] = {
                    'total': total,
                    'chapters': dict(chapter_counts),
                    'chapter_count': len(chapter_counts)
                }

    # 총 등장 횟수 내림차순 정렬, 상위 30개
    sorted_candidates = sorted(candidates.items(), key=lambda x: -x[1]['total'])[:30]

    result = {
        'chapter_count': len(chapters),
        'character_candidates': [
            {'name': name, **data}
            for name, data in sorted_candidates
        ],
        'total_candidates': len(sorted_candidates)
    }

    out_path = output_dir / 'step5_result.json'
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')

    return {'found': len(sorted_candidates), 'message': f'인물 후보 {len(sorted_candidates)}명 분석 완료'}


# ── 결과 페이지 ───────────────────────────────────────────

@app.route('/results/<int:step_num>')
def results(step_num):
    project = get_current_project()
    result_data = None

    if project:
        result_file = Path(project['dir']) / f'step{step_num}_result.json'
        if result_file.exists():
            result_data = json.loads(result_file.read_text(encoding='utf-8'))

    return render_template('results.html', step=step_num, project=project, data=result_data)


@app.route('/uploads/<project_name>/<filename>')
def serve_upload(project_name, filename):
    """업로드 폴더 내 파일 (차트 이미지 등)을 서비스"""
    return send_from_directory(UPLOAD_DIR / project_name, filename)


@app.route('/clear-project')
def clear_project():
    session.pop('project', None)
    return redirect(url_for('index'))


# ── 서버 시작 ──────────────────────────────────────────
if __name__ == '__main__':
    UPLOAD_DIR.mkdir(exist_ok=True)

    print("=" * 50)
    print("  NOVELDESK 웹 서버 시작!")
    print("  브라우저에서 아래 주소를 열어주세요:")
    print("  http://127.0.0.1:5000")
    print("=" * 50)

    app.run(debug=True, host='127.0.0.1', port=5000)
