# step4_api_suggestions.py
#
# 목적: 3단계에서 사람이 손으로 만들었던 "대안 제안"을 Claude API가 자동으로 만들게 한다.
#
# 실행 전 준비물 (켄니의 컴퓨터/Claude Code 환경에서):
#   1. pip install anthropic
#   2. 터미널에 API 키 등록:
#      Mac/Linux: export ANTHROPIC_API_KEY="여기에 본인 키"
#      Windows(PowerShell): $env:ANTHROPIC_API_KEY="여기에 본인 키"
#   3. python step4_api_suggestions.py
#
# 왜 이렇게 짰는지:
#   - 1~3단계 코드(반복 표현 찾기)는 그대로 재사용한다. 이미 검증된 부분을
#     다시 만들지 않는 것이 원칙이다.
#   - 표현 하나하나를 API에 따로따로 보내지 않고, "한 표현 + 그 표현이 들어간
#     모든 문장"을 한 번에 묶어서 보낸다. 이렇게 해야 API가 "이 표현이 책
#     전체에서 이렇게 반복된다"는 맥락을 보고 판단할 수 있다. (문장 하나씩
#     따로 보내면 반복 문제를 알 수 없다)
#   - API 호출은 비용이 들기 때문에, 표현이 너무 적게(1~2번) 나온 것은
#     보내지 않고 일정 횟수 이상만 추려서 보낸다 (비용 절감).

import os
import glob
from collections import defaultdict
from step1_frequency_check import (
    find_repeated_endings, find_connective_patterns,
    find_narration_verbs, find_action_cliches
)
from step3_context_report import load_chapters, split_sentences, find_phrase_contexts

try:
    import anthropic
except ImportError:
    anthropic = None

# .env 파일이 있으면 거기서 환경변수를 읽어온다.
# (코드 안에 키를 직접 쓰지 않고, 별도 파일로 분리하는 이유:
#  이 .py 파일이 나중에 GitHub에 올라가거나 공유돼도 키는 노출되지 않는다.
#  .env 파일은 .gitignore에 등록해서 항상 제외시킨다.)
try:
    from dotenv import load_dotenv
    # encoding='utf-8-sig' : 윈도우 메모장이 파일을 'UTF-8 BOM' 형식으로
    # 저장하는 경우가 많은데, 이때 파일 맨 앞에 보이지 않는 특수문자(BOM)가
    # 끼어들어가 키 값이 깨지는 원인이 된다. 이 옵션으로 그 문제를 막는다.
    load_dotenv(encoding='utf-8-sig')
except ImportError:
    pass


def get_multi_chapter_phrases(chapters, detector_fn, min_chapters=2, min_total=3):
    """
    min_chapters: 몇 개 이상의 챕터에 걸쳐 나와야 '책 전체의 습관'으로 볼지 기준.
    챕터가 3개뿐이던 샘플 테스트 때는 2로 충분했지만, 36챕터 전체에서는
    이 기준을 그대로 쓰면 노이즈(흔한 기능어)가 너무 많이 섞인다.
    그래서 전체 챕터 수에 비례해서 자동으로 기준을 높인다.
    """
    combined = defaultdict(dict)
    for chapter_name, text in chapters.items():
        for pattern, count in detector_fn(text).items():
            combined[pattern][chapter_name] = count
    return {
        p: d for p, d in combined.items()
        if len(d) >= min_chapters and sum(d.values()) >= min_total
    }


def dedupe_overlapping_phrases(phrases):
    """
    '그 어느'와 '그 어느 때보다'처럼 짧은 구문이 긴 구문에 포함되고
    등장 챕터가 거의 동일하면, 짧은 쪽은 중복이므로 제거한다.
    (긴 구문이 더 구체적인 정보이므로 남긴다)
    """
    items = sorted(phrases.items(), key=lambda x: -len(x[0]))  # 긴 구문부터
    kept = []
    for phrase, dist in items:
        is_subset = False
        for kept_phrase, kept_dist in kept:
            if phrase in kept_phrase and phrase != kept_phrase:
                # 등장 챕터가 70% 이상 겹치면 중복으로 판단
                overlap = len(set(dist) & set(kept_dist))
                if overlap >= len(dist) * 0.7:
                    is_subset = True
                    break
        if not is_subset:
            kept.append((phrase, dist))
    return dict(kept)


def build_prompt(phrase, contexts, total_count, num_chapters):
    """
    API에게 보낼 프롬프트를 만든다.
    핵심 설계 포인트:
    - "고쳐 써라"가 아니라 "패턴을 진단하고, 대표 예시 몇 개에 대안을 제안하라"고 요청한다.
      문장 전체를 다 고치게 하면 작가의 원래 의도가 사라질 위험이 크기 때문에,
      최종 결정은 항상 작가(켄니)가 하도록 설계한다.
    - 어떤 챕터에서 몇 번 나왔는지 숫자 정보를 같이 줘서, API가 "전체 맥락에서의
      과다 사용"을 판단 근거로 쓰게 한다.
    """
    lines = []
    for chapter, sentences in contexts.items():
        for s in sentences[:8]:  # 너무 많으면 토큰 낭비라 챕터별 최대 8개만
            lines.append(f"[{chapter}] {s}")
    examples = '\n'.join(lines)

    prompt = f"""당신은 한국 소설 전문 편집자입니다. 작가가 36개 챕터, 34만자 분량의 장편소설을 쓰고 있는데, 아래 표현 '{phrase}'이 정확히 {num_chapters}개 챕터에 걸쳐 총 {total_count}회 사용되고 있습니다.

중요: 진단을 쓸 때 반드시 위에 명시된 정확한 횟수({total_count}회, {num_chapters}개 챕터)만 사용하세요. 임의로 다른 숫자를 만들어내지 마세요.

[반복 표현]: {phrase}
[등장 문장들]:
{examples}

다음을 한국어로 답하세요:
1. 이 반복이 실제로 문제가 되는지 1~2문장으로 진단 (단순히 흔한 단어라 문제 없을 수도 있음을 고려)
2. 문제가 있다면, 위 예시 중 대표적인 3~5개 문장에 대해 "원문 → 대안" 형식으로 제안
3. 전체적으로 이 표현의 의존도를 줄이기 위한 전략 1~2줄

반드시 다음 형식을 지키세요:
## 진단
(내용)

## 대안 제안
- 원문: ...
  대안: ...

## 전체 전략
(내용)
"""
    return prompt


def call_claude(prompt, model="claude-sonnet-4-6"):
    if anthropic is None:
        raise RuntimeError("anthropic 패키지가 설치되어 있지 않습니다. pip install anthropic 필요")
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY 환경변수가 설정되어 있지 않습니다.\n"
            "터미널에서 export ANTHROPIC_API_KEY='본인 키' 실행 후 다시 시도하세요."
        )
    # 메모장 등에서 .env 파일을 저장할 때 앞뒤 공백, 따옴표, 보이지 않는
    # BOM 문자(\ufeff)가 섞여 들어가는 경우가 많아 이를 제거한다.
    api_key = api_key.strip().strip('"').strip("'").lstrip('\ufeff')
    try:
        api_key.encode('ascii')
    except UnicodeEncodeError:
        bad_chars = [c for c in api_key if ord(c) > 127]
        raise RuntimeError(
            f".env 파일의 API 키에 영문/숫자가 아닌 문자가 섞여 있습니다: {bad_chars}\n"
            ".env 파일을 다시 열어서 키 값에 한글이나 특수문자가 섞이지 않았는지,\n"
            "줄 끝에 다른 내용이 붙어있지 않은지 확인하세요."
        )
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        # 1000 -> 1600 : '지만'/'말했다'처럼 예시 문장이 많이 들어가는 항목은
        # 답변이 길어져서 1000 토큰 안에 다 못 들어가고 중간에 잘리는 문제가 있었다.
        max_tokens=1600,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def main(chapters_folder='sample_chapters', out_path='api_suggestions_report.md', min_chapters=None, top=None):
    chapters = load_chapters(chapters_folder)
    print(f"분석 대상: {len(chapters)}개 챕터")

    # 챕터가 많을수록(예: 36개) '2개 챕터 이상'이라는 기준은 너무 느슨해서
    # 노이즈(흔한 기능어)가 과도하게 잡힌다. 챕터 수에 비례해 자동으로
    # 기준을 높인다 (대략 전체 챕터의 10% 이상에서 나와야 채택).
    if min_chapters is None:
        min_chapters = max(2, len(chapters) // 9)
    print(f"채택 기준: {min_chapters}개 챕터 이상에서 등장한 표현만 분석")

    all_phrases = {}
    fixed_pattern_keys = set()
    for fn in [find_repeated_endings, find_connective_patterns, find_narration_verbs]:
        result = get_multi_chapter_phrases(chapters, fn, min_chapters=min_chapters)
        all_phrases.update(result)
        fixed_pattern_keys.update(result.keys())

    action_phrases = get_multi_chapter_phrases(chapters, find_action_cliches, min_chapters=min_chapters)
    before = len(action_phrases)
    # 중복 제거는 자동 추출된 짧은 구문(예: '그 어느' vs '그 어느 때보다')에만 적용한다.
    # '지만'처럼 미리 정해둔 어미/접속어는 '하지만'의 부분 문자열이라고 해서
    # 같은 의미가 아니므로, 이 패턴들은 중복 제거 대상에서 제외해야 한다.
    action_phrases = dedupe_overlapping_phrases(action_phrases)
    print(f"행동묘사 구문 중복 제거: {before}개 -> {len(action_phrases)}개")
    all_phrases.update(action_phrases)

    print(f"API로 보낼 표현 {len(all_phrases)}개 (반복 횟수 많은 순)")

    sorted_phrases = sorted(all_phrases.items(), key=lambda x: -sum(x[1].values()))

    if top is not None:
        sorted_phrases = sorted_phrases[:top]
        print(f"--top {top}: 빈도 상위 {len(sorted_phrases)}개만 처리합니다")

    report_lines = [f"# API 자동 분석 리포트 ({chapters_folder})\n"]
    for phrase, dist in sorted_phrases:
        total = sum(dist.values())
        print(f"  처리 중: '{phrase}' (총 {total}회)...")
        contexts = find_phrase_contexts(chapters, phrase)
        prompt = build_prompt(phrase, contexts, total, len(dist))
        try:
            result = call_claude(prompt)
        except RuntimeError as e:
            result = f"(API 호출 실패: {e})"
        report_lines.append(f"\n---\n\n# '{phrase}' (총 {total}회, {len(dist)}개 챕터)\n\n{result}")

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report_lines))
    print(f"\n완료: {out_path}")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="Claude API 자동 제안 생성")
    parser.add_argument('folder', nargs='?', default=None, help="챕터 폴더 (기본: --project의 all_chapters)")
    parser.add_argument('--project', default=None, help="projects/<이름> 기준으로 기본 경로를 잡는다")
    parser.add_argument('--top', type=int, default=None, help="빈도 상위 N개 표현만 처리 (기본: 전체)")
    args = parser.parse_args()

    if args.folder:
        chapters_folder = args.folder
        out_path = 'api_suggestions_report.md'
    elif args.project:
        from project_utils import project_path, default_chapters_folder
        chapters_folder = default_chapters_folder(args.project)
        out_path = project_path(args.project, 'api_suggestions_report.md')
    else:
        chapters_folder = 'sample_chapters'
        out_path = 'api_suggestions_report.md'

    if args.top is not None:
        out_path = out_path.replace('.md', f'_top{args.top}.md')

    main(chapters_folder=chapters_folder, out_path=out_path, top=args.top)
