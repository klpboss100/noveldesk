# step2_cross_chapter.py
# 목적: 1단계에서 만든 탐지 함수들을 여러 챕터에 적용하고,
#       "한 챕터에서만 나오는 표현"과 "여러 챕터에 걸쳐 나오는 표현"을 구분해서 보여준다.
# 후자가 진짜 "책 전체 통일감 문제"의 증거다.

import os
import re
import glob
from collections import defaultdict
from step1_frequency_check import (
    find_repeated_endings, find_connective_patterns,
    find_descriptive_cliches, find_narration_verbs, find_action_cliches
)

def _load_from_single_file(path):
    """단일 파일을 챕터 단위로 나눈다. 방식은 project_utils.split_single_file_chapters 참고."""
    from project_utils import split_single_file_chapters
    chapters_list, method = split_single_file_chapters(path)
    if method:
        print(f"  [챕터 구분 방식: {method}]")
    chapters = {}
    for ch_num, title, body in chapters_list:
        name = f'제{ch_num}화.txt' if method == 'pattern' else f'{ch_num:02d}_{title}.txt'
        chapters[name] = body
    return chapters


def short_chapter_label(chapter_name):
    """챕터명에서 '제N화' 부분만 뽑아 표시용 짧은 이름으로 만든다."""
    m = re.search(r'제\d+화', chapter_name)
    return m.group(0) if m else chapter_name

def _load_from_folder(folder):
    chapters = {}
    for path in sorted(glob.glob(os.path.join(folder, '*.txt'))):
        with open(path, encoding='utf-8') as f:
            chapters[os.path.basename(path)] = f.read()
    return chapters

def load_chapters(path, mode='auto'):
    """
    mode='auto' (기본): path가 파일이면 단일 파일 모드, 폴더면 폴더 모드.
    mode='file' / 'folder'로 강제 지정도 가능하다.
    반환 형태는 두 모드 모두 동일: {챕터명: 텍스트}
    """
    if mode == 'auto':
        mode = 'file' if os.path.isfile(path) else 'folder'
    if mode == 'file':
        return _load_from_single_file(path)
    return _load_from_folder(path)

def cross_chapter_report(chapters, detector_fn, label):
    """
    detector_fn: find_repeated_endings 같은 함수 (텍스트 -> {표현: 횟수})
    여러 챕터에 detector_fn을 각각 돌리고, 표현별로
    '어느 챕터에 몇 번씩 나왔는지'를 합쳐서 보여준다.
    """
    # pattern -> {chapter_name: count}
    combined = defaultdict(dict)
    for chapter_name, text in chapters.items():
        result = detector_fn(text)
        for pattern, count in result.items():
            combined[pattern][chapter_name] = count

    print(f"\n=== [{label}] 챕터 간 비교 ===")
    # 2개 챕터 이상에 등장한 표현만 "통일감 문제"로 본다. 1개 챕터에만 나오면
    # 그 챕터만의 특징일 수 있어 책 전체 문제라고 단정하기 어렵다.
    multi_chapter = {p: d for p, d in combined.items() if len(d) >= 2}
    single_chapter = {p: d for p, d in combined.items() if len(d) == 1}

    if multi_chapter:
        print(f"  ▶ 2개 이상 챕터에서 발견된 표현 ({len(multi_chapter)}개):")
        # 등장 챕터 수 내림차순, 그 다음 총 횟수 내림차순
        sorted_items = sorted(
            multi_chapter.items(),
            key=lambda x: (-len(x[1]), -sum(x[1].values()))
        )
        for pattern, dist in sorted_items:
            total = sum(dist.values())
            detail = ', '.join(f"{short_chapter_label(ch)}:{c}회" for ch, c in dist.items())
            print(f"    [총 {total}회 / {len(dist)}개 챕터] '{pattern}' → {detail}")
    else:
        print("  (2개 이상 챕터에 걸친 반복 없음)")

    if single_chapter:
        print(f"  - 참고: 1개 챕터에만 나온 표현 {len(single_chapter)}개는 생략")

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="챕터 간 반복 표현 비교")
    parser.add_argument('folder', nargs='?', default=None, help="챕터 폴더 (기본: --project의 sample_chapters)")
    parser.add_argument('--project', default=None, help="projects/<이름> 기준으로 기본 경로를 잡는다")
    args = parser.parse_args()

    if args.folder:
        target_folder = args.folder
    elif args.project:
        from project_utils import default_sample_source
        target_folder = default_sample_source(args.project)
    else:
        target_folder = 'sample_chapters'

    chapters = load_chapters(target_folder)
    print(f"분석 대상 챕터: {list(chapters.keys())}")

    cross_chapter_report(chapters, find_repeated_endings, "B. 의심 단어/종결패턴")
    cross_chapter_report(chapters, find_connective_patterns, "C. 접속/대조 구조")
    cross_chapter_report(chapters, find_descriptive_cliches, "D. 묘사 클리셰")
    cross_chapter_report(chapters, find_narration_verbs, "E. 대화 서술동사")
    cross_chapter_report(chapters, find_action_cliches, "F. 행동 묘사 클리셰(2~3어절)")
