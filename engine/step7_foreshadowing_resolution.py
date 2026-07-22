# step7_foreshadowing_resolution.py
#
# 목적: step6_foreshadowing_check.py가 전반부(1~18화)에서 찾아낸 떡밥 목록을
#       후반부(기본 19~36화) 본문과 함께 Claude API에 보내서,
#       각 떡밥이 실제로 회수됐는지 / 안 됐는지 판단받는다.
#
# 입력: foreshadowing_part1_1-18.md (step6의 결과물)
# 출력: foreshadowing_unresolved.md — 회수 안 된 떡밥을 강조해서 정리
#
# 비용 안내 설계: step6과 동일하게, 실행 전 예상 토큰/비용을 보여주고
# y/n 확인을 받은 뒤에만 API를 호출한다.
#
# 실행:
#   python step7_foreshadowing_resolution.py all_chapters
#   python step7_foreshadowing_resolution.py 36화TOTAL.docx
#   python step7_foreshadowing_resolution.py all_chapters --start 19 --end 36
#   python step7_foreshadowing_resolution.py all_chapters --foreshadowing foreshadowing_part1_1-18.md --yes

import os
import argparse

from step5_consistency_check import load_chapters
from step6_foreshadowing_check import (
    select_chapter_range, build_combined_text, estimate_tokens, estimate_cost,
    get_api_key, MODEL, PRICE_PER_MTOK_INPUT, PRICE_PER_MTOK_OUTPUT,
)

try:
    import anthropic
except ImportError:
    anthropic = None

try:
    from dotenv import load_dotenv
    load_dotenv(encoding='utf-8-sig')
except ImportError:
    pass

MAX_OUTPUT_TOKENS = 4000


def load_foreshadowing_list(path):
    if not os.path.exists(path):
        raise RuntimeError(
            f"'{path}' 파일을 찾을 수 없습니다. 먼저 step6_foreshadowing_check.py를 실행해서 만들어야 합니다."
        )
    with open(path, encoding='utf-8') as f:
        return f.read()


def build_prompt(foreshadowing_md, combined_text, start, end):
    prompt = f"""당신은 한국 장편소설 전문 편집자입니다.

아래 [떡밥 목록]은 이 소설의 전반부(1~18화)를 분석해서 미리 찾아낸,
"나중에 회수될 것 같은 설정/암시/약속"의 목록입니다.
그리고 [후반부 본문]은 이 소설의 {start}화부터 {end}화까지(후반부) 전체 본문입니다.

당신이 할 일: [떡밥 목록]에 있는 떡밥 하나하나에 대해, [후반부 본문] 안에서
실제로 회수(설명/해소/재등장하여 의미가 완결됨)되는지 확인하세요.

판정 기준:
- "회수됨": 후반부에 그 떡밥과 명확히 연결되는 사건/대사/설명이 나온다.
- "부분 회수": 관련된 내용이 다시 나오지만 완전히 해소되지는 않았다.
- "회수 안 됨": 후반부 전체에서 그 떡밥과 연결되는 내용을 찾을 수 없다.

중요:
- 실제로 본문에 있는 문장만 근거로 인용하세요. 본문에 없는 내용을 지어내지 마세요.
- "회수 안 됨"이라고 판정하기 전에 본문 전체를 충분히 검토하세요.

반드시 다음 마크다운 형식을 정확히 지켜서 두 섹션으로 답하세요.

## 미회수 떡밥 (우선 확인)
(여기에는 "회수 안 됨"으로 판정한 떡밥만, 아래 형식으로 모두 나열하세요. 없으면 "회수 안 된 떡밥 없음"이라고 쓰세요)

### 떡밥: (원래 떡밥 한 줄 요약)
- **원래 등장**: (전반부 화수)
- **판정**: 회수 안 됨
- **검토 의견**: ({start}~{end}화 전체를 봐도 연결되는 내용이 없는 이유)

## 전체 판정 (참고)
(여기에는 떡밥 목록의 모든 항목을 빠짐없이, 아래 형식으로 나열하세요)

### 떡밥: (원래 떡밥 한 줄 요약)
- **원래 등장**: (전반부 화수)
- **판정**: 회수됨 / 부분 회수 / 회수 안 됨
- **회수 위치**: (회수됐다면 몇 화인지, 안 됐다면 "해당 없음")
- **근거 문장**: ("회수됐다면 후반부 원문 인용, 안 됐다면 생략 가능")

[떡밥 목록]
{foreshadowing_md}

[후반부 본문]
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


def split_unresolved_section(result_text):
    """응답에서 '## 미회수 떡밥' 섹션만 따로 떼어낸다 (리포트 맨 위에 강조용으로 쓰기 위함)."""
    marker = '## 미회수 떡밥'
    rest_marker = '## 전체 판정'
    idx = result_text.find(marker)
    idx2 = result_text.find(rest_marker)
    if idx == -1:
        return None, result_text
    unresolved = result_text[idx:idx2].strip() if idx2 != -1 else result_text[idx:].strip()
    rest = result_text[idx2:].strip() if idx2 != -1 else ''
    return unresolved, rest


def main(source='all_chapters', start=19, end=36,
         foreshadowing_path='foreshadowing_part1_1-18.md',
         out_path='foreshadowing_unresolved.md', skip_confirm=False):

    foreshadowing_md = load_foreshadowing_list(foreshadowing_path)
    print(f"떡밥 목록 로드 완료: '{foreshadowing_path}' ({len(foreshadowing_md):,}자)")

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
    prompt = build_prompt(foreshadowing_md, combined_text, start, end)

    est_input = estimate_tokens(prompt)
    est_output = MAX_OUTPUT_TOKENS
    est_cost = estimate_cost(est_input, est_output)

    print(f"\n--- 예상 토큰/비용 (사전 견적, 실제 사용량은 호출 후 다시 출력) ---")
    print(f"  입력 토큰(추정): 약 {est_input:,} 토큰  (떡밥 목록 + {start}~{end}화 본문)")
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

    print(f"\nClaude API 호출 중... ({end - start + 1}화 분량이라 시간이 걸릴 수 있습니다)")
    try:
        result, usage = call_claude(prompt)
        actual_cost = estimate_cost(usage.input_tokens, usage.output_tokens)
        print(f"실제 사용량: 입력 {usage.input_tokens:,} 토큰, 출력 {usage.output_tokens:,} 토큰")
        print(f"실제 비용(추정): 약 ${actual_cost:.3f}")
    except RuntimeError as e:
        result = f"(API 호출 실패: {e})"
        unresolved_section, rest_section = None, ''
    else:
        unresolved_section, rest_section = split_unresolved_section(result)

    report_lines = [
        f"# 떡밥 회수 체크 — 후반부 ({start}~{end}화) 대조 결과\n",
        f"> 전반부 떡밥 목록: `{foreshadowing_path}`\n"
        f"> Claude의 판단은 참고 의견이며, 실제로 회수됐는지/중요한지는 작가가 직접 판단합니다.\n",
        f"\n분석 대상: {found_nums[0]}화~{found_nums[-1]}화 ({len(selected)}개 챕터)\n",
    ]

    if unresolved_section:
        report_lines.append(f"\n---\n\n{unresolved_section}\n")
        if rest_section:
            report_lines.append(f"\n---\n\n{rest_section}\n")
    else:
        report_lines.append(f"\n---\n\n{result}\n")

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report_lines))
    print(f"\n완료: {out_path}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="후반부 떡밥 회수 여부 체크 (Claude API)")
    parser.add_argument('source', nargs='?', default=None,
                         help="챕터 폴더, .txt 단일 파일, 또는 .docx 파일 (기본: --project의 all_chapters)")
    parser.add_argument('--project', default=None, help="projects/<이름> 기준으로 기본 경로를 잡는다")
    parser.add_argument('--start', type=int, default=19)
    parser.add_argument('--end', type=int, default=36)
    parser.add_argument('--foreshadowing', default=None)
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

    if args.project:
        from project_utils import project_path
        foreshadowing_path = args.foreshadowing or project_path(args.project, 'foreshadowing_part1_1-18.md')
        out_path = args.out or project_path(args.project, 'foreshadowing_unresolved.md')
    else:
        foreshadowing_path = args.foreshadowing or 'foreshadowing_part1_1-18.md'
        out_path = args.out or 'foreshadowing_unresolved.md'

    main(source=source, start=args.start, end=args.end,
         foreshadowing_path=foreshadowing_path, out_path=out_path,
         skip_confirm=args.yes)
