# viewer_render_html.py
#
# viewer_build_data.py가 만든 report_data.json을 읽어서 HTML로 렌더링한다.
# (분석 파이프라인의 step이 아니라 viewer_build_data.py와 짝을 이루는 도구)
#
# 목적: report_data.json(파싱된 76개 항목)을 가지고, 인터넷 연결 없이
#       더블클릭으로 바로 열리는 단일 HTML 파일을 만든다.
#       기능: 표현 검색, 펼치기/접기, 원문→대안 한 쌍씩 클립보드 복사.

import argparse
import json

parser = argparse.ArgumentParser(description="report_data.json을 검색 가능한 HTML로 렌더링")
parser.add_argument('--project', default=None, help="projects/<이름> 기준으로 입출력 경로와 제목을 잡는다")
parser.add_argument('--data', default=None, help="입력 json 경로")
parser.add_argument('--out', default=None, help="출력 html 경로")
parser.add_argument('--title', default=None, help="리포트 제목 (기본: <project> - 반복 표현 분석 리포트)")
args = parser.parse_args()

if args.project:
    from project_utils import project_path
    data_path = args.data or project_path(args.project, 'report_data.json')
    out_path = args.out or project_path(args.project, 'report_viewer.html')
    title = args.title or f'{args.project} - 반복 표현 분석 리포트'
else:
    data_path = args.data or 'report_data.json'
    out_path = args.out or 'report_viewer.html'
    title = args.title or '반복 표현 분석 리포트'

with open(data_path, encoding='utf-8') as f:
    items = json.load(f)

# 빈도 높은 순으로 이미 정렬되어 있다고 가정 (step4가 그렇게 만들었음)
data_json = json.dumps(items, ensure_ascii=False)

html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
  body {{ font-family: -apple-system, "Malgun Gothic", sans-serif; max-width: 900px;
         margin: 0 auto; padding: 20px; background: #faf9f7; color: #2b2b2b; }}
  h1 {{ font-size: 22px; }}
  .meta {{ color: #777; font-size: 14px; margin-bottom: 20px; }}
  #search {{ width: 100%; padding: 12px; font-size: 16px; border: 1px solid #ccc;
             border-radius: 8px; margin-bottom: 16px; box-sizing: border-box; }}
  .item {{ background: white; border: 1px solid #e0ddd8; border-radius: 10px;
           margin-bottom: 10px; overflow: hidden; }}
  .item-header {{ padding: 14px 18px; cursor: pointer; display: flex;
                  justify-content: space-between; align-items: center; }}
  .item-header:hover {{ background: #f5f3ef; }}
  .phrase {{ font-weight: 600; font-size: 16px; }}
  .stats {{ color: #888; font-size: 13px; }}
  .item-body {{ display: none; padding: 0 18px 18px 18px; border-top: 1px solid #eee; }}
  .item.open .item-body {{ display: block; }}
  .section-title {{ font-weight: 600; margin-top: 14px; color: #555; font-size: 14px; }}
  .diagnosis {{ font-size: 14px; line-height: 1.6; color: #333; }}
  .pair {{ background: #f7f6f3; border-radius: 8px; padding: 10px 12px; margin: 8px 0;
           display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }}
  .pair-text {{ font-size: 14px; line-height: 1.5; flex: 1; }}
  .orig {{ color: #888; text-decoration: line-through; }}
  .alt {{ color: #1a6b3c; font-weight: 500; }}
  .copy-btn {{ background: #2b6cb0; color: white; border: none; border-radius: 6px;
               padding: 6px 10px; font-size: 12px; cursor: pointer; white-space: nowrap; }}
  .copy-btn:hover {{ background: #234e8c; }}
  .copy-btn.copied {{ background: #1a6b3c; }}
  .strategy {{ font-size: 14px; line-height: 1.6; color: #444; background: #fdf6e8;
               border-radius: 8px; padding: 10px 12px; margin-top: 10px; }}
  .count-badge {{ display: inline-block; background: #eee; border-radius: 6px;
                  padding: 2px 8px; font-size: 12px; color: #555; }}
  #no-results {{ display: none; text-align: center; color: #999; padding: 30px; }}
</style>
</head>
<body>

<h1>{title}</h1>
<div class="meta">총 {len(items)}개 표현 · 빈도 높은 순 정렬 · 표현이나 문장 내용으로 검색 가능</div>

<input type="text" id="search" placeholder="표현 검색 (예: 지만, 가만히, 말했다...)">

<div id="list"></div>
<div id="no-results">검색 결과가 없습니다.</div>

<script>
const DATA = {data_json};

function escapeHtml(s) {{
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}}

function render(filterText) {{
  const list = document.getElementById('list');
  const noResults = document.getElementById('no-results');
  const q = (filterText || '').toLowerCase();
  list.innerHTML = '';
  let shown = 0;

  DATA.forEach((item, idx) => {{
    const haystack = (item.phrase + ' ' + item.diagnosis + ' ' +
      item.pairs.map(p => p.original + ' ' + p.alt).join(' ')).toLowerCase();
    if (q && !haystack.includes(q)) return;
    shown++;

    const div = document.createElement('div');
    div.className = 'item';
    div.innerHTML = `
      <div class="item-header" onclick="this.parentElement.classList.toggle('open')">
        <span class="phrase">'${{escapeHtml(item.phrase)}}'</span>
        <span class="stats"><span class="count-badge">${{item.count}}회 · ${{item.n_chapters}}개 챕터</span></span>
      </div>
      <div class="item-body">
        <div class="section-title">진단</div>
        <div class="diagnosis">${{escapeHtml(item.diagnosis)}}</div>
        <div class="section-title">대안 제안 (클릭하면 복사됩니다)</div>
        ${{item.pairs.map((p, pi) => `
          <div class="pair">
            <div class="pair-text">
              <div class="orig">원문: ${{escapeHtml(p.original)}}</div>
              <div class="alt">대안: ${{escapeHtml(p.alt)}}</div>
            </div>
            <button class="copy-btn" onclick="copyPair(event, ${{idx}}, ${{pi}})">복사</button>
          </div>
        `).join('')}}
        <div class="section-title">전체 전략</div>
        <div class="strategy">${{escapeHtml(item.strategy)}}</div>
      </div>
    `;
    list.appendChild(div);
  }});

  noResults.style.display = shown === 0 ? 'block' : 'none';
}}

function copyPair(event, idx, pi) {{
  event.stopPropagation();
  const p = DATA[idx].pairs[pi];
  const text = p.alt;  // 대안 문장만 복사 (바로 원고에 붙여넣기 좋게)
  navigator.clipboard.writeText(text).then(() => {{
    const btn = event.target;
    const original = btn.textContent;
    btn.textContent = '복사됨!';
    btn.classList.add('copied');
    setTimeout(() => {{ btn.textContent = original; btn.classList.remove('copied'); }}, 1200);
  }});
}}

document.getElementById('search').addEventListener('input', (e) => render(e.target.value));
render('');
</script>

</body>
</html>
"""

with open(out_path, 'w', encoding='utf-8') as f:
    f.write(html)

print(f"{out_path} 생성 완료 ({len(items)}개 항목)")
