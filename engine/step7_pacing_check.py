# step7_pacing_check.py
# 목적: 36챕터 전체의 "페이싱(속도감)"을 숫자로 측정한다. API 호출 없음, 순수 코드.
#
# 측정 지표 4가지:
#   1. 챕터별 글자수 (공백 제외)
#   2. 챕터별 문장 평균 길이 + 표준편차 (문장 구분: . ! ?)
#   3. 챕터별 대화 비중 = 큰따옴표 안 글자수 / 전체 글자수
#   4. 챕터별 장면 전환 횟수 (____ 구분선 개수)
#
# 이 리포트는 "여기를 다시 읽어봐라"는 힌트일 뿐이다.
# 늘어지는 게 실제로 문제인지, 의도된 느린 장면인지는 항상 작가가 직접 판단한다.

import re
import sys
import glob
import os
import statistics

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# 한글 폰트가 없으면 그래프의 한글 라벨이 깨지므로, 시스템에서 찾을 수 있는 한글 폰트를 사용한다.
def set_korean_font():
    candidates = ['Malgun Gothic', 'NanumGothic', 'AppleGothic', 'Noto Sans CJK KR']
    available = {f.name for f in fm.fontManager.ttflist}
    for name in candidates:
        if name in available:
            plt.rcParams['font.family'] = name
            return
    # 못 찾으면 기본값 유지 (한글이 깨질 수 있음)

set_korean_font()
plt.rcParams['axes.unicode_minus'] = False


def load_text(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def chapter_sort_key(path):
    """파일명에서 챕터 번호를 뽑아 자연수 순으로 정렬하기 위한 키."""
    m = re.search(r'(\d+)', os.path.basename(path))
    return int(m.group(1)) if m else 0


def char_count_no_space(text):
    """공백(스페이스, 탭, 줄바꿈 등) 제외 글자수."""
    return len(re.sub(r'\s', '', text))


def split_sentences(text):
    """. ! ? 기준으로 문장을 분리한다. 빈 문장은 제외."""
    # 줄바꿈을 공백으로 바꿔서 문장이 줄 단위로 잘리지 않게 한다.
    flat = text.replace('\n', ' ')
    sentences = re.split(r'[.!?]+', flat)
    sentences = [s.strip() for s in sentences if s.strip()]
    return sentences


def sentence_length_stats(text):
    """문장 평균 길이(글자수, 공백 제외)와 표준편차."""
    sentences = split_sentences(text)
    lengths = [char_count_no_space(s) for s in sentences]
    if not lengths:
        return 0.0, 0.0
    mean = statistics.mean(lengths)
    stdev = statistics.stdev(lengths) if len(lengths) > 1 else 0.0
    return mean, stdev


def dialogue_ratio(text):
    """큰따옴표(직선 " 또는 곡선 “ ”) 안에 있는 글자수 / 전체 글자수(공백 제외)."""
    total = char_count_no_space(text)
    if total == 0:
        return 0.0

    dialogue_chars = 0
    # 직선 큰따옴표 " ... "
    for m in re.findall(r'"([^"]*)"', text):
        dialogue_chars += char_count_no_space(m)
    # 곡선 큰따옴표 “ ... ”
    for m in re.findall(r'“([^”]*)”', text):
        dialogue_chars += char_count_no_space(m)

    return dialogue_chars / total


def scene_break_count(text):
    """장면 전환 구분선(____ 연속된 줄) 개수."""
    return len(re.findall(r'_{4,}', text))


def analyze_chapter(path):
    text = load_text(path)
    chars = char_count_no_space(text)
    sent_mean, sent_stdev = sentence_length_stats(text)
    dia_ratio = dialogue_ratio(text)
    breaks = scene_break_count(text)
    return {
        'file': os.path.basename(path),
        'chars': chars,
        'sent_mean': sent_mean,
        'sent_stdev': sent_stdev,
        'dialogue_ratio': dia_ratio,
        'scene_breaks': breaks,
    }


def flag_outliers(values, factor=1.5):
    """평균에서 factor배 이상 벗어나는 인덱스 집합을 반환."""
    avg = statistics.mean(values) if values else 0
    flags = []
    for v in values:
        if avg == 0:
            flags.append(False)
            continue
        flags.append(v >= avg * factor or v <= avg / factor)
    return flags, avg


def chapter_label(filename):
    m = re.search(r'(\d+)', filename)
    return f"{int(m.group(1))}화" if m else filename


def build_report(rows, out_md):
    chars_vals = [r['chars'] for r in rows]
    sent_mean_vals = [r['sent_mean'] for r in rows]
    sent_stdev_vals = [r['sent_stdev'] for r in rows]
    dia_vals = [r['dialogue_ratio'] for r in rows]
    break_vals = [r['scene_breaks'] for r in rows]

    chars_flags, chars_avg = flag_outliers(chars_vals)
    sent_flags, sent_avg = flag_outliers(sent_mean_vals)
    dia_flags, dia_avg = flag_outliers(dia_vals)
    break_flags, break_avg = flag_outliers(break_vals)

    lines = []
    lines.append('# 페이싱(속도감) 체크 리포트')
    lines.append('')
    lines.append(f'- 분석 챕터: {len(rows)}개')
    lines.append('')
    lines.append('## 주의')
    lines.append('')
    lines.append('이 리포트는 "여기를 다시 읽어봐라"는 힌트일 뿐입니다.')
    lines.append('평균에서 벗어났다고 해서 그 챕터가 잘못됐다는 뜻은 아닙니다.')
    lines.append('느린 회상 장면, 긴 대화 장면, 긴박한 액션 장면은 의도적으로 평균과 다를 수 있습니다.')
    lines.append('표시(⚠️)는 단지 "다시 한번 살펴볼 만한 챕터"를 가리킬 뿐이며,')
    lines.append('실제로 늘어지는지, 의도된 리듬인지는 작가가 직접 판단해야 합니다.')
    lines.append('')
    lines.append('## 전체 평균')
    lines.append('')
    lines.append(f'- 글자수(공백 제외) 평균: {chars_avg:,.0f}자')
    lines.append(f'- 문장 평균 길이 평균: {sent_avg:.1f}자')
    lines.append(f'- 대화 비중 평균: {dia_avg*100:.1f}%')
    lines.append(f'- 장면 전환 횟수 평균: {break_avg:.1f}회')
    lines.append('')
    lines.append('## 챕터별 지표')
    lines.append('')
    lines.append('> ⚠️ = 해당 지표 전체 평균의 1.5배 이상이거나 1/1.5배(=0.67배) 이하인 챕터')
    lines.append('')
    lines.append('| 챕터 | 글자수(공백제외) | 문장평균길이 | 문장길이 표준편차 | 대화비중 | 장면전환횟수 |')
    lines.append('|---|---|---|---|---|---|')

    for i, r in enumerate(rows):
        label = chapter_label(r['file'])
        chars_mark = ' ⚠️' if chars_flags[i] else ''
        sent_mark = ' ⚠️' if sent_flags[i] else ''
        dia_mark = ' ⚠️' if dia_flags[i] else ''
        break_mark = ' ⚠️' if break_flags[i] else ''
        lines.append(
            f"| {label} | {r['chars']:,}{chars_mark} | "
            f"{r['sent_mean']:.1f}{sent_mark} | {r['sent_stdev']:.1f} | "
            f"{r['dialogue_ratio']*100:.1f}%{dia_mark} | "
            f"{r['scene_breaks']}{break_mark} |"
        )

    lines.append('')
    lines.append('## 다시 살펴볼 만한 챕터 모아보기')
    lines.append('')
    for name, flags in [
        ('글자수', chars_flags),
        ('문장 평균 길이', sent_flags),
        ('대화 비중', dia_flags),
        ('장면 전환 횟수', break_flags),
    ]:
        flagged = [chapter_label(rows[i]['file']) for i, f in enumerate(flags) if f]
        if flagged:
            lines.append(f'- **{name}** 이상치: {", ".join(flagged)}')
        else:
            lines.append(f'- **{name}** 이상치: 없음')

    lines.append('')
    lines.append('## 그래프')
    lines.append('')
    lines.append('![페이싱 그래프](pacing_chart.png)')
    lines.append('')

    with open(out_md, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def build_chart(rows, out_png):
    labels = [chapter_label(r['file']) for r in rows]
    x = [int(re.search(r'(\d+)', r['file']).group(1)) for r in rows]
    chars_vals = [r['chars'] for r in rows]
    sent_mean_vals = [r['sent_mean'] for r in rows]
    dia_vals = [r['dialogue_ratio'] * 100 for r in rows]
    break_vals = [r['scene_breaks'] for r in rows]

    fig, axes = plt.subplots(4, 1, figsize=(12, 16), sharex=True)

    axes[0].plot(x, chars_vals, marker='o', color='tab:blue')
    axes[0].axhline(statistics.mean(chars_vals), color='gray', linestyle='--', linewidth=1)
    axes[0].set_ylabel('글자수(공백제외)')
    axes[0].set_title('챕터별 글자수')

    axes[1].plot(x, sent_mean_vals, marker='o', color='tab:orange')
    axes[1].axhline(statistics.mean(sent_mean_vals), color='gray', linestyle='--', linewidth=1)
    axes[1].set_ylabel('문장 평균 길이')
    axes[1].set_title('챕터별 문장 평균 길이')

    axes[2].plot(x, dia_vals, marker='o', color='tab:green')
    axes[2].axhline(statistics.mean(dia_vals), color='gray', linestyle='--', linewidth=1)
    axes[2].set_ylabel('대화 비중(%)')
    axes[2].set_title('챕터별 대화 비중')

    axes[3].plot(x, break_vals, marker='o', color='tab:red')
    axes[3].axhline(statistics.mean(break_vals), color='gray', linestyle='--', linewidth=1)
    axes[3].set_ylabel('장면 전환 횟수')
    axes[3].set_title('챕터별 장면 전환 횟수')
    axes[3].set_xlabel('챕터 번호')

    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    plt.close(fig)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="페이싱(속도감) 체크")
    parser.add_argument('folder', nargs='?', default=None, help="챕터 폴더 (기본: --project의 all_chapters)")
    parser.add_argument('--project', default=None, help="projects/<이름> 기준으로 기본 경로를 잡는다")
    args = parser.parse_args()

    if args.folder:
        folder = args.folder
    elif args.project:
        from project_utils import default_chapters_folder
        folder = default_chapters_folder(args.project)
    else:
        folder = 'all_chapters'

    paths = sorted(glob.glob(os.path.join(folder, '*.txt')), key=chapter_sort_key)

    if not paths:
        print(f"'{folder}' 폴더에 .txt 파일이 없습니다.")
        return

    rows = [analyze_chapter(p) for p in paths]

    if args.project:
        from project_utils import project_path
        out_md = project_path(args.project, 'pacing_report.md')
        out_png = project_path(args.project, 'pacing_chart.png')
    else:
        out_md = 'pacing_report.md'
        out_png = 'pacing_chart.png'

    build_report(rows, out_md)
    build_chart(rows, out_png)

    print(f"분석 완료: {len(rows)}개 챕터")
    print(f"리포트: {out_md}")
    print(f"그래프: {out_png}")


if __name__ == '__main__':
    main()
