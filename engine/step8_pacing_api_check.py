# step8_pacing_api_check.py
#
# 목적: step7_pacing_check.py가 숫자로만 골라낸 "이상 신호 챕터"에 대해,
#       Claude API에게 실제로 늘어지는지 / 의도된 장면인지 판단을 한 번 더 받는다.
#
# 비용 절감 설계:
#   - 36챕터 전체를 보내지 않고, step7에서 ⚠️ 표시된 챕터만 추린다.
#   - 호출 전에 "몇 개 챕터, 몇 번 호출 예상"을 먼저 보여주고 사용자 확인을 받은 뒤 실행한다.
#
# 실행:
#   python step8_pacing_api_check.py all_chapters
#
# 전제: step7_pacing_check.py를 먼저 실행해서 pacing_report.md / 지표가 나와 있어야 한다.
#       (이 스크립트는 step7의 분석 함수를 그대로 재사용한다 — 같은 계산을 두 번 만들지 않는다)

import os
import re
import sys
import glob

from step7_pacing_check import (
    analyze_chapter, chapter_sort_key, chapter_label, flag_outliers,
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


def call_claude(prompt, model="claude-sonnet-4-6"):
    if anthropic is None:
        raise RuntimeError("anthropic 패키지가 설치되어 있지 않습니다. pip install anthropic 필요")
    client = anthropic.Anthropic(api_key=get_api_key())
    response = client.messages.create(
        model=model,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def collect_outlier_chapters(folder):
    """
    step7과 동일한 방식으로 36챕터를 분석하고, 4개 지표 중 하나라도
    ⚠️ 표시(평균의 1.5배 이상 또는 0.67배 이하)가 붙은 챕터만 추려서 반환한다.
    반환값: [(row, reasons), ...] — reasons는 "어떤 지표가 왜 벗어났는지" 문자열 리스트
    """
    paths = sorted(glob.glob(os.path.join(folder, '*.txt')), key=chapter_sort_key)
    if not paths:
        raise RuntimeError(f"'{folder}' 폴더에 .txt 파일이 없습니다.")

    rows = [analyze_chapter(p) for p in paths]
    rows_with_path = list(zip(rows, paths))

    chars_vals = [r['chars'] for r in rows]
    sent_vals = [r['sent_mean'] for r in rows]
    dia_vals = [r['dialogue_ratio'] for r in rows]
    break_vals = [r['scene_breaks'] for r in rows]

    chars_flags, chars_avg = flag_outliers(chars_vals)
    sent_flags, sent_avg = flag_outliers(sent_vals)
    dia_flags, dia_avg = flag_outliers(dia_vals)
    break_flags, break_avg = flag_outliers(break_vals)

    outliers = []
    for i, (r, path) in enumerate(rows_with_path):
        reasons = []
        if chars_flags[i]:
            direction = "많음" if r['chars'] >= chars_avg else "적음"
            reasons.append(
                f"글자수가 평균({chars_avg:,.0f}자)보다 크게 {direction} "
                f"({r['chars']:,}자, 평균의 {r['chars']/chars_avg:.2f}배)"
            )
        if sent_flags[i]:
            direction = "길음" if r['sent_mean'] >= sent_avg else "짧음"
            reasons.append(
                f"문장 평균 길이가 평균({sent_avg:.1f}자)보다 크게 {direction} "
                f"({r['sent_mean']:.1f}자, 평균의 {r['sent_mean']/sent_avg:.2f}배)"
            )
        if dia_flags[i]:
            direction = "높음" if r['dialogue_ratio'] >= dia_avg else "낮음"
            reasons.append(
                f"대화 비중이 평균({dia_avg*100:.1f}%)보다 크게 {direction} "
                f"({r['dialogue_ratio']*100:.1f}%, 평균의 {r['dialogue_ratio']/dia_avg:.2f}배)"
            )
        if break_flags[i]:
            direction = "많음" if r['scene_breaks'] >= break_avg else "적음"
            reasons.append(
                f"장면 전환 횟수가 평균({break_avg:.1f}회)보다 크게 {direction} "
                f"({r['scene_breaks']}회, 평균의 {r['scene_breaks']/break_avg:.2f}배)"
                if break_avg > 0 else
                f"장면 전환 횟수가 {r['scene_breaks']}회"
            )
        if reasons:
            outliers.append((r, path, reasons))

    return outliers


def build_prompt(label, reasons, text):
    reasons_text = '\n'.join(f"- {r}" for r in reasons)
    prompt = f"""당신은 한국 소설 전문 편집자입니다. 아래는 장편소설 중 {label}의 전체 본문입니다.

기계적인 글자수/문장길이/대화비중/장면전환 분석 결과, 이 챕터는 다음과 같은 이유로
전체 36챕터 평균에서 크게 벗어난 "이상 신호"로 표시되었습니다:

{reasons_text}

[챕터 본문]
{text}

다음을 한국어로 판단해 주세요:
1. 이 챕터가 실제로 "늘어지는" 느낌을 줄 가능성이 있는지, 아니면 의도적인 장면
   (회상, 차분한 분위기 조성, 정보 전달, 긴박한 전개 등)으로 보이는지 1~2문장으로 진단
2. 만약 늘어진다고 판단되면, 구체적으로 어느 부분(인용하거나 위치를 설명)을 줄이면
   좋을지, 또는 어떤 장면(대화, 사건, 전환)을 추가하면 리듬이 살아날지 구체적으로 제안
3. 늘어지지 않는다고 판단되면 왜 그렇게 보는지 근거를 짧게 설명

반드시 다음 형식을 지키세요:
## 진단
(늘어지는지 / 의도된 장면인지)

## 구체적 제안
(늘어진다면 구체적 제안, 아니라면 "특별한 조치 불필요"와 근거)
"""
    return prompt


def main(folder='all_chapters', out_path='pacing_api_report.md', sample=None, skip_confirm=False):
    print(f"'{folder}' 폴더에서 페이싱 지표를 다시 계산하는 중...")
    outliers = collect_outlier_chapters(folder)

    if not outliers:
        print("이상 신호로 표시된 챕터가 없습니다. API 호출 없이 종료합니다.")
        return

    print(f"\n이상 신호가 있는 챕터: {len(outliers)}개")
    for r, path, reasons in outliers:
        label = chapter_label(r['file'])
        print(f"  - {label}: {', '.join(reasons)}")

    # 샘플 모드: 이유 개수가 많은(이상 신호가 가장 뚜렷한) 챕터부터 N개만 추려서
    # 효과를 먼저 확인해볼 수 있게 한다. 전체로 갈지는 결과를 본 뒤 따로 결정한다.
    if sample is not None:
        outliers = sorted(outliers, key=lambda x: -len(x[2]))[:sample]
        out_path = out_path.replace('.md', f'_sample{sample}.md')
        print(f"\n[샘플 모드] 이상 신호가 가장 뚜렷한 {len(outliers)}개 챕터만 처리합니다:")
        for r, path, reasons in outliers:
            print(f"  - {chapter_label(r['file'])} ({len(reasons)}개 이유)")

    print(f"\nAPI 호출 {len(outliers)}번이 예상됩니다.")
    if skip_confirm:
        print("--yes 플래그로 확인을 건너뜁니다.")
    else:
        answer = input("진행하시겠습니까? (y/n): ").strip().lower()
        if answer != 'y':
            print("취소했습니다. API를 호출하지 않았습니다.")
            return

    report_lines = [f"# 페이싱 이상 챕터 — Claude 판단 리포트 ({folder})\n"]
    report_lines.append(
        "> 기계적 신호는 \"여기를 다시 읽어봐라\"는 힌트이고, Claude의 판단도 참고 의견일 뿐입니다.\n"
        "> 실제로 늘어지는지, 손볼지 말지는 항상 작가가 직접 결정합니다.\n"
    )

    for r, path, reasons in outliers:
        label = chapter_label(r['file'])
        print(f"\n처리 중: {label} ...")
        with open(path, encoding='utf-8') as f:
            text = f.read()

        prompt = build_prompt(label, reasons, text)
        try:
            result = call_claude(prompt)
        except RuntimeError as e:
            result = f"(API 호출 실패: {e})"

        # Claude 응답은 '## 진단' / '## 구체적 제안'을 쓰는데, 리포트의 '## Claude 판단 및
        # 제안' 바로 아래 같은 레벨(##)로 들어가면 헤딩 구조가 평평해진다. 한 단계 낮춘다.
        result = re.sub(r'(?m)^## ', '### ', result)

        reasons_md = '\n'.join(f"- {r2}" for r2 in reasons)
        report_lines.append(
            f"\n---\n\n# {label}\n\n"
            f"## 기계적 신호\n\n{reasons_md}\n\n"
            f"## Claude 판단 및 제안\n\n{result}"
        )

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report_lines))
    print(f"\n완료: {out_path}")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="페이싱 이상 챕터에 대한 Claude 판단")
    parser.add_argument('folder', nargs='?', default=None, help="챕터 폴더 (기본: --project의 all_chapters)")
    parser.add_argument('sample', nargs='?', type=int, default=None, help="이상 신호가 가장 뚜렷한 N개만 처리")
    parser.add_argument('--project', default=None, help="projects/<이름> 기준으로 기본 경로를 잡는다")
    parser.add_argument('--yes', action='store_true', help="진행 확인을 건너뛴다")
    args = parser.parse_args()

    if args.folder:
        folder = args.folder
        out_path = 'pacing_api_report.md'
    elif args.project:
        from project_utils import default_chapters_folder, project_path
        folder = default_chapters_folder(args.project)
        out_path = project_path(args.project, 'pacing_api_report.md')
    else:
        folder = 'all_chapters'
        out_path = 'pacing_api_report.md'

    main(folder=folder, out_path=out_path, sample=args.sample, skip_confirm=args.yes)
