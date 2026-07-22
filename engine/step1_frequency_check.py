# step1_frequency_check.py
# 목적: 챕터 텍스트에서 "반복되는 표현"을 자동으로 찾아내는 가장 기초적인 버전
# 형태소 분석기 없이도 동작하는 단순한 방식으로 먼저 감을 잡는 단계입니다.

import re
import os
import glob
from collections import Counter
import sys

def load_text(path):
    with open(path, encoding='utf-8') as f:
        return f.read()

def find_repeated_phrases(text, min_len=4, max_len=10, min_count=2):
    """
    문장을 어절(공백 기준) 단위로 쪼갠 뒤, 연속된 N개 어절 묶음(n-gram)이
    몇 번이나 등장하는지 센다. 한국어는 형태소 분석 없이도
    '어절 n-gram' 방식으로 꽤 많은 반복 표현을 잡아낼 수 있다.
    """
    # 문장 단위로 먼저 분리 (대화문, 줄바꿈 등은 일단 단순 처리)
    words = text.replace('\n', ' ').split()
    results = Counter()

    for n in range(min_len, max_len + 1):
        for i in range(len(words) - n + 1):
            phrase = ' '.join(words[i:i+n])
            results[phrase] += 1

    # min_count 이상 반복되고, 너무 짧은 조사/어미만으로 된 것 제외
    filtered = {p: c for p, c in results.items() if c >= min_count}
    return filtered

def find_repeated_endings(text):
    """
    문장 종결 패턴(~듯했다, ~것 같았다, ~라고 생각했다 등)의 빈도를 본다.
    AI 글쓰기 패턴 탐지에서 가장 흔히 문제되는 부분.
    """
    patterns = [
        r'듯했다', r'듯이', r'것 같았다', r'것이었다', r'라고 생각했다',
        r'멍하니', r'가만히', r'그저', r'문득', r'어느새',
        r'절박', r'절실', r'간절', r'다급', r'공허',
    ]
    counts = {}
    for p in patterns:
        counts[p] = len(re.findall(p, text))
    return {k: v for k, v in counts.items() if v > 0}

def find_connective_patterns(text):
    """
    [후보1] 문장 구조 패턴: 대조/접속 구조가 매 문단마다 비슷하게 반복되는지.
    '~지만', '그러나', '하지만' 등은 문장을 너무 일정한 리듬으로 만들어
    AI 특유의 단조로움을 만드는 주범 중 하나다.
    """
    patterns = [r'지만', r'그러나', r'하지만', r'한편', r'그런데', r'그리고']
    counts = {}
    for p in patterns:
        counts[p] = len(re.findall(p, text))
    return {k: v for k, v in counts.items() if v > 0}

def find_descriptive_cliches(text):
    """
    [후보2] 묘사 클리셰: '형용사+명사' 짝이 거의 그대로 반복되는 패턴.
    단어 하나(예: '공허')가 아니라 '공허한 메아리' 같은 조합 단위로 본다.
    여기서는 자주 쓰이는 수식 조합을 직접 등록해서 빈도를 잡는다.
    (다음 단계에서는 이 목록을 직접 만들지 않고 자동 추출하도록 발전시킬 것)
    """
    patterns = [
        r'텅 빈', r'낯설고 이국적', r'공허한', r'삭막하고',
        r'무겁고 답답', r'깊고 무거운', r'어둡고 적막', r'짙은 어둠',
    ]
    counts = {}
    for p in patterns:
        counts[p] = len(re.findall(p, text))
    return {k: v for k, v in counts.items() if v > 0}

def find_narration_verbs(text):
    """
    [후보3] 대화/내레이션 전환 패턴: 대화문 뒤에 붙는 서술 동사
    ('~라고 말했다', '~하며 외쳤다', '~쏘아붙였다' 등)가
    인물 구분 없이 비슷하게 반복되는지 본다. 대화 장면이 다 똑같은
    리듬으로 느껴지는 원인이 되는 경우가 많다.
    """
    patterns = [
        r'말했다', r'외쳤다', r'쏘아붙였다', r'말씀드렸다', r'물었다',
        r'대답했다', r'중얼거렸다', r'소리쳤다',
    ]
    counts = {}
    for p in patterns:
        counts[p] = len(re.findall(p, text))
    return {k: v for k, v in counts.items() if v > 0}

def find_action_cliches(text, min_len=2, max_len=3, min_count=2):
    """
    [후보4] 인물 행동 묘사 클리셰: '발길을 재촉했다', '고개를 끄덕이며'처럼
    짧은 동작 묘사 구문이 인물과 무관하게 반복되는지 본다.
    find_repeated_phrases와 같은 원리지만 더 짧은 n-gram(2~3어절)을 본다.
    행동 묘사는 보통 짧은 구문이라 짧게 잡아야 걸린다.
    """
    words = text.replace('\n', ' ').split()
    results = Counter()
    for n in range(min_len, max_len + 1):
        for i in range(len(words) - n + 1):
            phrase = ' '.join(words[i:i+n])
            results[phrase] += 1
    return {p: c for p, c in results.items() if c >= min_count}

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="단일 챕터 빈도 분석")
    parser.add_argument('path', nargs='?', default=None, help="분석할 .txt 파일 경로")
    parser.add_argument('--project', default=None,
                         help="projects/<이름>/sample_chapters의 첫 파일을 기본 분석 대상으로 사용")
    args = parser.parse_args()

    if args.path:
        path = args.path
    elif args.project:
        from project_utils import project_path
        sample_dir = project_path(args.project, 'sample_chapters')
        candidates = sorted(glob.glob(os.path.join(sample_dir, '*.txt')))
        if not candidates:
            sys.exit(f"'{sample_dir}'에 .txt 파일이 없습니다.")
        path = candidates[0]
    else:
        sys.exit("사용법: python step1_frequency_check.py <파일경로> 또는 --project <소설이름>")

    text = load_text(path)

    print(f"=== 파일: {path} ===")
    print(f"전체 글자수(공백제외): {len(text.replace(' ', '').replace(chr(10), ''))}\n")

    print("--- [A] 반복되는 4~10어절 구문 (2회 이상) ---")
    phrases = find_repeated_phrases(text)
    # 긴 구문(더 구체적인 반복)을 우선 보여주기 위해 길이 내림차순 정렬
    for phrase, count in sorted(phrases.items(), key=lambda x: (-len(x[0]), -x[1])):
        print(f"  [{count}회] {phrase}")

    print("\n--- [B] 의심 단어/종결패턴 빈도 ---")
    endings = find_repeated_endings(text)
    for pattern, count in sorted(endings.items(), key=lambda x: -x[1]):
        print(f"  [{count}회] '{pattern}'")

    print("\n--- [C] 접속/대조 구조 빈도 (후보1) ---")
    connectives = find_connective_patterns(text)
    for pattern, count in sorted(connectives.items(), key=lambda x: -x[1]):
        print(f"  [{count}회] '{pattern}'")

    print("\n--- [D] 묘사 클리셰 빈도 (후보2) ---")
    cliches = find_descriptive_cliches(text)
    for pattern, count in sorted(cliches.items(), key=lambda x: -x[1]):
        print(f"  [{count}회] '{pattern}'")

    print("\n--- [E] 대화 서술동사 빈도 (후보3) ---")
    verbs = find_narration_verbs(text)
    for pattern, count in sorted(verbs.items(), key=lambda x: -x[1]):
        print(f"  [{count}회] '{pattern}'")

    print("\n--- [F] 행동 묘사 클리셰: 2~3어절 반복구문 (후보4) ---")
    actions = find_action_cliches(text)
    for phrase, count in sorted(actions.items(), key=lambda x: (-x[1], -len(x[0]))):
        print(f"  [{count}회] {phrase}")
