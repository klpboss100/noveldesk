# step6_foreshadowing_check.py
#
# 목적: 장편소설 전반부(기본 1~18화)를 한 번에 Claude API에 보내서,
#       "나중에 회수될 것 같은 설정/암시/약속(떡밥)"을 찾아 목록으로 만든다.
#
# 이 단계는 "떡밥이 던져졌는지"만 찾는다. 후반부와 대조해서 실제로
# 회수됐는지 확인하는 건 별도 단계(다음에 만들 step)에서 한다.
#
# 비용 안내 설계:
#   - 18개 챕터 본문 전체를 한 번에 보내는, 토큰을 많이 쓰는 호출이다.
#   - 실행 전에 예상 입력/출력 토큰 수와 대략적인 비용을 먼저 보여주고
#     y/n 확인을 받은 뒤에만 API를 호출한다 (step8과 동일한 설계).
#
# 실행:
#   python step6_foreshadowing_check.py all_chapters
#   python step6_foreshadowing_check.py 36화TOTAL.docx
#   python step6_foreshadowing_check.py all_chapters --start 1 --end 18
#   python step6_foreshadowing_check.py all_chapters --yes

import os
import sys
import argparse

from step5_consistency_check import load_chapters

try:
    import anthropic
except ImportError:
    anthropic = None

try:
    from dotenv import load_dotenv
    load_dotenv(encoding='utf-8-sig')
except ImportError:
    pass

MODEL = "claude-sonnet-4-6"
MAX_OUTPUT_TOKENS = 4000

# Claude Sonnet 4.x 공식 가격 (2026-06 기준, 백만 토큰당 USD)
PRICE_PER_MTOK_INPUT = 3.0
PRICE_PER_MTOK_OUTPUT = 15.0

# 한글 텍스트는 영어보다 토큰을 더 많이 쓴다. 정확한 토큰화기 없이도
# 대략적인 사전 견적을 내기 위한 경험적 비율 (글자수 / 1.7 ≈ 토큰수).
# 실제 호출 결과(usage)로 더 정확한 값을 다시 출력한다.
CHARS_PER_TOKEN_KO = 1.7


def get_api_key():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY 환경변수가 설정되어 있지 않습니다.\n"
            ".env 파일에 ANTHROPIC_API_KEY=본인키 형식으로 등록하세요."
        )
    api_key = api_key.strip().strip('"').strip("'").lstrip('﻿')
    try:
        api_key.encode('ascii')
    except UnicodeEncodeError:
        bad_chars = [c for c in api_key if ord(c) > 127]
        raise RuntimeError(
            f".env 파일의 API 키에 영문/숫자가 아닌 문자가 섞여 있습니다: {bad_chars}"
        )
    return api_key


def select_chapter_range(chapters, start, end):
    """{화수: (이름, 텍스트)} 중 start~end 화만 골라 화수 순으로 정렬해 반환."""
    selected = [
        (n, name, text) for n, (name, text) in chapters.items()
        if start <= n <= end
    ]
    selected.sort(key=lambda x: x[0])
    return selected


def build_combined_text(selected):
    """선택된 챕터들을 '제N화' 표시를 살려서 하나의 텍스트로 합친다."""
    parts = []
    for n, name, text in selected:
        parts.append(text.strip())
    return '\n\n'.join(parts)


def estimate_tokens(text):
    return int(len(text) / CHARS_PER_TOKEN_KO)


def estimate_cost(input_tokens, output_tokens):
    cost_in = input_tokens / 1_000_000 * PRICE_PER_MTOK_INPUT
    cost_out = output_tokens / 1_000_000 * PRICE_PER_MTOK_OUTPUT
    return cost_in + cost_out


def build_prompt(combined_text, start, end):
    prompt = f"""당신은 한국 장편소설 전문 편집자입니다. 아래는 장편소설의 {start}화부터 {end}화까지(전반부) 전체 본문입니다.

이 구간에서 "나중에 회수될 것 같은 설정/암시/약속(떡밥)"을 찾아주세요.
떡밥이란: 작가가 의도적이든 무의식적이든 나중에 다시 다뤄질 것처럼 던져놓은
인물의 비밀, 의미심장한 물건이나 대사, 풀리지 않은 의문, 예고된 사건,
복선이 되는 묘사 등을 말합니다.

각 떡밥마다 다음을 표시해 주세요:
1. 떡밥 요약 (한 줄)
2. 몇 화에서 처음/주로 나왔는지
3. 근거가 된 실제 문장 (원문 인용)
4. 왜 이것을 떡밥으로 판단했는지 1줄 근거
5. (선택) 나중에 어떤 방식으로 회수될 수 있을지 추측 1줄

중요:
- 실제로 본문에 있는 문장만 인용하세요. 본문에 없는 내용을 지어내지 마세요.
- 너무 사소하거나 일반적인 묘사는 제외하고, 정말 "다시 나올 것 같은" 것만 추리세요.
- 떡밥은 중요도 순으로 정렬해 주세요.

반드시 다음 마크다운 형식을 지켜서, 떡밥 개수만큼 반복하세요:

## 떡밥 N: (한 줄 요약)
- **등장**: {start}~{end}화 중 N화
- **근거 문장**: "원문 인용"
- **판단 근거**: (1줄)
- **회수 예상**: (1줄, 추측이면 "추측:"으로 시작)

[본문]
{combined_text}
"""
    return prompt


def call_claude(prompt):
    if anthropic is None:
        raise RuntimeError("anthropic 패키지가 설치되어 있지 않습니다. pip install anthropic 필요")
    client = anthropic.Anthropic(api_key=get_api_key())
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_OUTPUT_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text, response.usage


def main(source='all_chapters', start=1, end=18, out_path=None, skip_confirm=False, project=None):
    if out_path is None:
        filename = f'foreshadowing_part1_{start}-{end}.md'
        if project:
            from project_utils import project_path
            out_path = project_path(project, filename)
        else:
            out_path = filename

    print(f"'{source}'에서 챕터를 읽는 중...")
    chapters = load_chapters(source)
    selected = select_chapter_range(chapters, start, end)

    if not selected:
        print(f"{start}~{end}화 범위에 해당하는 챕터를 찾지 못했습니다.")
        return

    found_nums = [n for n, _, _ in selected]
    missing = sorted(set(range(start, end + 1)) - set(found_nums))
    print(f"선택된 챕터: {len(selected)}개 ({found_nums[0]}화~{found_nums[-1]}화)")
    if missing:
        print(f"경고: 범위 안인데 누락된 화수: {missing}")

    combined_text = build_combined_text(selected)
    prompt = build_prompt(combined_text, start, end)

    est_input = estimate_tokens(prompt)
    est_output = MAX_OUTPUT_TOKENS
    est_cost = estimate_cost(est_input, est_output)

    print(f"\n--- 예상 토큰/비용 (사전 견적, 실제 사용량은 호출 후 다시 출력) ---")
    print(f"  입력 토큰(추정): 약 {est_input:,} 토큰")
    print(f"  출력 토큰(최대 한도): 최대 {est_output:,} 토큰")
    print(f"  예상 비용(최악의 경우, 출력 최대치 기준): 약 ${est_cost:.3f}")
    print(f"  모델: {MODEL}")
    print(f"  API 호출 1번")

    if skip_confirm:
        print("\n--yes 플래그로 확인을 건너뜁니다.")
    else:
        answer = input("\n진행하시겠습니까? (y/n): ").strip().lower()
        if answer != 'y':
            print("취소했습니다. API를 호출하지 않았습니다.")
            return

    print("\nClaude API 호출 중... (18화 분량이라 시간이 걸릴 수 있습니다)")
    try:
        result, usage = call_claude(prompt)
        actual_cost = estimate_cost(usage.input_tokens, usage.output_tokens)
        print(f"실제 사용량: 입력 {usage.input_tokens:,} 토큰, 출력 {usage.output_tokens:,} 토큰")
        print(f"실제 비용(추정): 약 ${actual_cost:.3f}")
    except RuntimeError as e:
        result = f"(API 호출 실패: {e})"
        actual_cost = None

    report_lines = [
        f"# 떡밥/회수 체크 — 전반부 ({start}~{end}화)\n",
        "> 이 리포트는 전반부에서 \"던져진 떡밥\"만 찾은 1단계 결과입니다.\n"
        "> 후반부와 대조해서 실제로 회수됐는지는 다음 단계에서 별도로 확인합니다.\n"
        "> Claude의 판단은 참고 의견이며, 실제로 떡밥인지/중요한지는 작가가 직접 판단합니다.\n",
        f"\n분석 대상: {found_nums[0]}화~{found_nums[-1]}화 ({len(selected)}개 챕터)\n",
        "\n---\n",
        result,
    ]

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report_lines))
    print(f"\n완료: {out_path}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="전반부 떡밥 탐지 (Claude API)")
    parser.add_argument('source', nargs='?', default=None,
                         help="챕터 폴더, .txt 단일 파일, 또는 .docx 파일 (기본: --project의 all_chapters)")
    parser.add_argument('--project', default=None, help="projects/<이름> 기준으로 기본 경로를 잡는다")
    parser.add_argument('--start', type=int, default=1)
    parser.add_argument('--end', type=int, default=18)
    parser.add_argument('--out', default=None)
    parser.add_argument('--yes', action='store_true', help="진행 확인을 건너뛴다")
    args = parser.parse_args()

    if args.source:
        source = args.source
    elif args.project:
        from project_utils import default_chapters_folder
        source = default_chapters_folder(args.project)
    else:
        source = 'all_chapters'

    main(source=source, start=args.start, end=args.end,
         out_path=args.out, skip_confirm=args.yes, project=args.project)
