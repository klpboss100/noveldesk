# step5_consistency_check.py
#
# 목적: "성씨+계급" 패턴을 찾고, 챕터 순서상 계급이 역행하는 후보를 표시한다.
#
# 배경:
#   계급 체계와 순서는 소설마다 다르므로 코드에 박아두지 않고,
#   projects/<이름>/story_bible/world.json 의 rank_system.order에서 읽어온다.
#   (예: 전투경찰/의무경찰 계급 순서 이경(0) < 일경(1) < 상경(2) < 수경(3))
#   인물 지칭 형태: 성씨+계급 (예: 편일경, 마수경, 고상경)
#   챕터 번호 = 시간 순서 (1화가 가장 과거, 마지막 화가 가장 미래)
#
# 판단은 사람이 한다. 회상 장면이나 두 성씨 동음이인 가능성이 있으므로
# 코드는 "후보"만 제시하고 확정하지 않는다.
#
# world.json에 rank_system이 없는 소설(계급 체계가 없는 경우)에서는
# 이 체크 자체를 건너뛴다.
#
# 실행:
#   python step5_consistency_check.py --project 우도
#   python step5_consistency_check.py all_chapters --project 우도

import re
import os
import glob
import sys
from collections import defaultdict


def build_rank_pattern(ranks):
    """
    계급 목록으로부터 "성씨+계급" 정규식을 만든다.
    (?<![가-힣]) : 앞 글자가 한글이 아닌 곳에서 시작 (어절 앞 보장)
    [가-힣]{1,2} : 성씨 1~2자
    뒤 lookahead는 넣지 않는다 (편일경이, 편일경을 모두 잡아야 함).
    """
    rank_alt = '|'.join(re.escape(r) for r in ranks)
    return re.compile(rf'(?<![가-힣])([가-힣]{{1,2}})({rank_alt})')


# ── 유틸 ──────────────────────────────────────────────────

def get_chapter_num(filename: str) -> int:
    """파일명에서 화수 추출. 제10화.txt → 10"""
    m = re.search(r'제(\d+)화', filename)
    return int(m.group(1)) if m else 0


def split_sentences(text: str) -> list[str]:
    """마침표/물음표/느낌표 기준 단순 문장 분리 (구분선 제거 포함)"""
    text = re.sub(r'_{5,}', ' ', text)
    text = text.replace('\n', ' ')
    parts = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in parts if s.strip()]


def find_rank_refs(text: str, rank_pattern) -> list[tuple[str, str, str]]:
    """
    텍스트에서 (성씨, 계급, 해당 문장) 목록 반환.
    같은 문장 안에서 같은 성씨+계급이 여러 번 나오면 한 번만 기록한다.
    """
    seen = set()
    refs = []
    for sentence in split_sentences(text):
        for m in rank_pattern.finditer(sentence):
            surname, rank = m.group(1), m.group(2)
            key = (surname, rank, sentence)
            if key not in seen:
                seen.add(key)
                refs.append(key)
    return refs


# ── 데이터 로드 ────────────────────────────────────────────

def _load_from_single_file(path: str) -> dict[int, tuple[str, str]]:
    """단일 파일을 챕터 단위로 나눈다. 방식은 project_utils.split_single_file_chapters 참고."""
    from project_utils import split_single_file_chapters
    chapters_list, method = split_single_file_chapters(path)
    if method:
        print(f"  [챕터 구분 방식: {method}]")
    chapters = {}
    for ch_num, title, body in chapters_list:
        name = f'제{ch_num}화.txt' if method == 'pattern' else f'{ch_num:02d}_{title}.txt'
        chapters[ch_num] = (name, body)
    return chapters


def _load_from_folder(folder: str) -> dict[int, tuple[str, str]]:
    chapters = {}
    for path in sorted(glob.glob(os.path.join(folder, '*.txt'))):
        ch_num = get_chapter_num(os.path.basename(path))
        if ch_num == 0:
            print(f"  경고: 화수 추출 실패 → {os.path.basename(path)} (건너뜀)")
            continue
        with open(path, encoding='utf-8') as f:
            chapters[ch_num] = (os.path.basename(path), f.read())
    return chapters


def load_chapters(path: str, mode: str = 'auto') -> dict[int, tuple[str, str]]:
    """
    mode='auto' (기본): path가 파일이면 단일 파일 모드, 폴더면 폴더 모드.
    mode='file' / 'folder'로 강제 지정도 가능하다.
    반환 형태는 두 모드 모두 동일: {화수: (챕터명, 텍스트)}
    """
    if mode == 'auto':
        mode = 'file' if os.path.isfile(path) else 'folder'
    if mode == 'file':
        return _load_from_single_file(path)
    return _load_from_folder(path)


# ── 분석 ──────────────────────────────────────────────────

def build_timeline(chapters: dict, rank_pattern) -> dict:
    """
    {성씨: {화수: [(계급, 문장), ...]}}
    성씨별로, 각 챕터에서 발견된 계급과 문장을 저장한다.
    """
    timeline: dict[str, dict[int, list]] = defaultdict(lambda: defaultdict(list))
    for ch_num in sorted(chapters):
        _, text = chapters[ch_num]
        for surname, rank, sentence in find_rank_refs(text, rank_pattern):
            timeline[surname][ch_num].append((rank, sentence))
    return timeline


def find_regressions(timeline: dict, ranks: list, rank_order: dict) -> list[dict]:
    """
    챕터 순서상 계급이 역행하는 후보를 찾는다.

    알고리즘:
    - 성씨별로 챕터를 시간 순(오름차순)으로 스캔
    - 지금까지 본 최고 계급(max_rank_idx)을 추적
    - 현재 챕터에 max_rank_idx보다 낮은 계급이 등장하면 후보로 기록
    """
    issues = []
    for surname, ch_data in sorted(timeline.items()):
        max_rank_idx = -1
        max_rank_ch = None

        for ch_num in sorted(ch_data):
            refs = ch_data[ch_num]
            suspect = [(r, s) for r, s in refs if rank_order[r] < max_rank_idx]
            if suspect:
                issues.append({
                    'surname': surname,
                    'peak_ch': max_rank_ch,
                    'peak_rank': ranks[max_rank_idx],
                    'curr_ch': ch_num,
                    'suspect_refs': suspect,
                })

            # 이 챕터에서 최고 계급으로 max 갱신
            ch_max = max(rank_order[r] for r, _ in refs)
            if ch_max > max_rank_idx:
                max_rank_idx = ch_max
                max_rank_ch = ch_num

    return issues


def find_intra_chapter_conflicts(timeline: dict, rank_order: dict) -> list[dict]:
    """
    같은 챕터 안에서 동일 성씨가 두 가지 이상의 계급으로 등장하는 경우.
    진급 장면일 수도 있고, 동명이성(同名異姓)일 수도 있으므로 참고용으로만 제공.
    """
    conflicts = []
    for surname, ch_data in sorted(timeline.items()):
        for ch_num, refs in sorted(ch_data.items()):
            unique_ranks = sorted(set(r for r, _ in refs), key=lambda r: rank_order[r])
            if len(unique_ranks) > 1:
                conflicts.append({
                    'surname': surname,
                    'ch_num': ch_num,
                    'ranks': unique_ranks,
                    'refs': refs,
                })
    return conflicts


# ── 리포트 출력 ────────────────────────────────────────────

def write_report(
    timeline: dict,
    regressions: list,
    conflicts: list,
    out_path: str,
    folder: str,
    total_chapters: int,
    rank_order: dict,
) -> None:
    lines = [
        f'# 계급 진급 체크 리포트\n',
        f'- 분석 폴더: `{folder}`',
        f'- 분석 챕터: {total_chapters}개',
        f'- 발견된 성씨: {len(timeline)}명 후보',
        f'- 역행 후보: {len(regressions)}건',
        f'- 동일 챕터 내 복수 계급: {len(conflicts)}건',
        '',
    ]

    # ── 섹션 1: 역행 후보 (주요 출력) ─────────────────────
    lines.append('---\n')
    lines.append('## 1. 검토 필요 — 계급 역행 후보\n')
    lines.append(
        '> 앞 챕터에서 본 최고 계급보다 낮은 계급이 뒤 챕터에 등장한 경우입니다.\n'
        '> 회상 장면이거나 동명이성(同名異姓)일 수 있으니 실제 문장을 확인하세요.\n'
    )

    if not regressions:
        lines.append('**(역행 후보 없음)**\n')
    else:
        for issue in regressions:
            header = (
                f"### [{issue['surname']}] "
                f"{issue['peak_ch']}화 **{issue['peak_rank']}** 이후 → "
                f"{issue['curr_ch']}화에 **{issue['suspect_refs'][0][0]}** 등장"
            )
            lines.append(header)
            lines.append(
                f'\n{issue["peak_ch"]}화에서 **{issue["peak_rank"]}**이 확인된 뒤, '
                f'{issue["curr_ch"]}화에 더 낮은 계급이 나옵니다.\n'
            )
            lines.append('**등장 문장:**')
            for rank, sentence in issue['suspect_refs']:
                display = sentence if len(sentence) <= 150 else sentence[:150] + '...'
                lines.append(f'- `{issue["surname"]}{rank}` → {display}')
            lines.append('')

    # ── 섹션 2: 인물별 계급 타임라인 ────────────────────────
    lines.append('---\n')
    lines.append('## 2. 인물별 계급 타임라인\n')
    lines.append(
        '> 화수 순서대로 발견된 계급을 나열합니다.\n'
        '> 같은 화에서 여러 계급이 나오면 `/`로 구분합니다.\n'
        '> ⚠️ 표시는 역행 후보가 있는 화입니다.\n'
    )

    regression_lookup: set[tuple] = set()
    for issue in regressions:
        regression_lookup.add((issue['surname'], issue['curr_ch']))

    for surname, ch_data in sorted(timeline.items()):
        parts = []
        for ch_num in sorted(ch_data):
            ranks = sorted(set(r for r, _ in ch_data[ch_num]), key=lambda r: rank_order[r])
            flag = ' ⚠️' if (surname, ch_num) in regression_lookup else ''
            parts.append(f'{ch_num}화: {"/".join(ranks)}{flag}')
        lines.append(f'- **{surname}**: {" → ".join(parts)}')

    # ── 섹션 3: 동일 챕터 내 복수 계급 (참고) ───────────────
    lines.append('\n---\n')
    lines.append('## 3. 참고 — 동일 챕터 내 복수 계급\n')
    lines.append(
        '> 같은 화 안에서 동일 성씨가 둘 이상의 계급으로 등장합니다.\n'
        '> 진급 장면, 회상, 또는 동명이성일 수 있습니다.\n'
    )

    if not conflicts:
        lines.append('(없음)\n')
    else:
        for c in conflicts:
            lines.append(
                f"- **{c['surname']}** ({c['ch_num']}화): {' / '.join(c['ranks'])}"
            )
            for rank, sentence in c['refs']:
                display = sentence if len(sentence) <= 120 else sentence[:120] + '...'
                lines.append(f"  - `{c['surname']}{rank}` → {display}")

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


# ── 메인 ──────────────────────────────────────────────────

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="계급 진급 일관성 체크")
    parser.add_argument('folder', nargs='?', default=None, help="챕터 폴더 (기본: --project의 all_chapters)")
    parser.add_argument('out_path', nargs='?', default=None, help="출력 리포트 경로")
    parser.add_argument('--project', default=None, help="projects/<이름> 기준으로 ranks/기본 경로를 잡는다")
    args = parser.parse_args()

    if args.folder:
        folder = args.folder
    elif args.project:
        from project_utils import default_chapters_folder
        folder = default_chapters_folder(args.project)
    else:
        folder = 'all_chapters'

    if args.out_path:
        out_path = args.out_path
    elif args.project:
        from project_utils import project_path
        out_path = project_path(args.project, 'rank_check_report.md')
    else:
        out_path = 'rank_check_report.md'

    if not args.project:
        sys.exit("계급 체계는 소설마다 다르므로 --project <소설이름>이 필요합니다 "
                  "(projects/<이름>/story_bible/world.json의 rank_system.order를 읽습니다).")

    from project_utils import load_rank_order
    ranks = load_rank_order(args.project)
    if not ranks:
        print(f"'{args.project}' 프로젝트의 story_bible/world.json에 rank_system.order가 없습니다. "
              "계급 체계가 없는 소설로 보고 이 체크를 건너뜁니다.")
        return
    rank_order = {r: i for i, r in enumerate(ranks)}
    rank_pattern = build_rank_pattern(ranks)

    print(f'분석 폴더: {folder}')
    print(f'계급 순서: {" < ".join(ranks)}')
    chapters = load_chapters(folder)
    if not chapters:
        print(f'오류: {folder} 폴더에 .txt 파일이 없습니다.')
        sys.exit(1)

    ch_nums = sorted(chapters)
    print(f'로드된 챕터: {len(chapters)}개 ({ch_nums[0]}화 ~ {ch_nums[-1]}화)\n')

    timeline = build_timeline(chapters, rank_pattern)
    print(f'발견된 성씨 후보: {len(timeline)}명')
    for surname, ch_data in sorted(timeline.items()):
        total_refs = sum(len(v) for v in ch_data.values())
        rank_summary = {}
        for ch_num, refs in ch_data.items():
            for r, _ in refs:
                rank_summary[r] = rank_summary.get(r, 0) + 1
        summary_str = ', '.join(f'{r}:{cnt}' for r, cnt in sorted(rank_summary.items(), key=lambda x: rank_order[x[0]]))
        print(f'  {surname}: {len(ch_data)}개 챕터, 총 {total_refs}회 [{summary_str}]')

    regressions = find_regressions(timeline, ranks, rank_order)
    conflicts = find_intra_chapter_conflicts(timeline, rank_order)

    print(f'\n역행 후보: {len(regressions)}건')
    for issue in regressions:
        print(
            f"  [{issue['surname']}] "
            f"{issue['peak_ch']}화 {issue['peak_rank']} → "
            f"{issue['curr_ch']}화 {issue['suspect_refs'][0][0]}"
        )

    print(f'동일 챕터 내 복수 계급: {len(conflicts)}건')
    for c in conflicts:
        print(f"  [{c['surname']}] {c['ch_num']}화: {'/'.join(c['ranks'])}")

    write_report(timeline, regressions, conflicts, out_path, folder, len(chapters), rank_order)
    print(f'\n완료: {out_path}')


if __name__ == '__main__':
    main()
