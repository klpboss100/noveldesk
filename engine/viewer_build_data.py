# viewer_build_data.py
#
# 분석 파이프라인(step1~8)의 다음 단계가 아니라, step4 결과물을 보기 편하게
# 만들어주는 별도 뷰어 도구다 (그래서 step 번호를 붙이지 않는다).
#
# 목적: api_suggestions_report.md (76개 항목, 7만자)를 그냥 markdown으로
#       읽으면 Ctrl+F 검색과 복사/붙여넣기가 불편하다.
#       이 스크립트는 그 파일을 파싱해서, 검색·필터·복사 버튼이 있는
#       단일 HTML 파일(report_viewer.html)로 만들어준다.
#       단일 파일이라 인터넷 연결 없이 그냥 더블클릭으로 브라우저에서 열린다.

import re
import json

def parse_report(path):
    with open(path, encoding='utf-8') as f:
        text = f.read()

    # 각 항목은 "# '표현' (총 N회, M개 챕터)" 로 시작한다.
    # 이 패턴으로 텍스트를 항목 단위로 쪼갠다.
    pattern = r"^# '(.+?)' \(총 (\d+)회, (\d+)개 챕터\)\s*$"
    matches = list(re.finditer(pattern, text, re.MULTILINE))

    items = []
    for i, m in enumerate(matches):
        phrase, count, n_chapters = m.group(1), int(m.group(2)), int(m.group(3))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end]

        diagnosis = extract_section(body, '진단', '대안 제안')
        strategy = extract_section(body, '전체 전략', None)
        pairs = extract_pairs(body)

        items.append({
            'phrase': phrase,
            'count': count,
            'n_chapters': n_chapters,
            'diagnosis': diagnosis.strip(),
            'pairs': pairs,
            'strategy': strategy.strip(),
        })
    return items


def extract_section(body, start_marker, end_marker):
    """'## 진단' 부터 다음 '## ...' 전까지 텍스트를 뽑는다."""
    start_pat = rf'##\s*{start_marker}\s*\n'
    m = re.search(start_pat, body)
    if not m:
        return ''
    rest = body[m.end():]
    # 다음 '## ' 헤딩이 나오면 거기서 자른다
    next_heading = re.search(r'\n##\s', rest)
    section = rest[:next_heading.start()] if next_heading else rest
    # 구분선(---)도 제거
    section = re.sub(r'^-{3,}\s*$', '', section, flags=re.MULTILINE)
    return section


def extract_pairs(body):
    """'- 원문: ...' / '  대안: ...' 쌍을 전부 추출한다.
    일부 항목은 '- **원문:**' 처럼 굵게 표시되어 있어 그 형식도 함께 처리한다."""
    pairs = []
    pattern = r'-\s*\*{0,2}원문\*{0,2}\s*[:：]\s*(.+?)\n\s*\*{0,2}대안\*{0,2}\s*[:：]\s*(.+?)(?=\n-\s*\*{0,2}원문|\n##|\n---|\Z)'
    for m in re.finditer(pattern, body, re.DOTALL):
        original = m.group(1).strip().strip('`').strip()
        alt = m.group(2).strip()
        pairs.append({'original': original, 'alt': alt})
    return pairs


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="api_suggestions_report.md를 report_data.json으로 파싱")
    parser.add_argument('--project', default=None, help="projects/<이름> 기준으로 입출력 경로를 잡는다")
    parser.add_argument('--report', default=None, help="입력 리포트 경로")
    parser.add_argument('--out', default=None, help="출력 json 경로")
    args = parser.parse_args()

    if args.project:
        from project_utils import project_path
        report_path = args.report or project_path(args.project, 'api_suggestions_report.md')
        out_path = args.out or project_path(args.project, 'report_data.json')
    else:
        report_path = args.report or 'api_suggestions_report.md'
        out_path = args.out or 'report_data.json'

    items = parse_report(report_path)
    print(f"파싱된 항목 수: {len(items)}개")
    # 검증: 빈 진단/전략이 있으면 파싱이 잘못됐을 가능성
    empty_diag = [it['phrase'] for it in items if not it['diagnosis']]
    empty_pairs = [it['phrase'] for it in items if not it['pairs']]
    if empty_diag:
        print(f"  경고: 진단이 비어있는 항목: {empty_diag}")
    if empty_pairs:
        print(f"  경고: 대안 쌍이 비어있는 항목: {empty_pairs}")

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(f"{out_path} 생성 완료")
