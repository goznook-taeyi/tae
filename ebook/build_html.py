#!/usr/bin/env python3
"""원고 md → 조판된 리딩용 HTML 빌드."""
import re
from pathlib import Path

import markdown
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent
FILES = ["00-front.md", "01-part1.md", "02-part2.md", "02b-anatomy.md",
         "03-part3.md", "04-part4.md"]

md_src = "\n\n".join((ROOT / f).read_text(encoding="utf-8") for f in FILES)
# 체크박스 표기 → 마커 (스타일은 CSS에서)
md_src = md_src.replace("- [ ] ", "- CHKBOX ")

html_body = markdown.markdown(md_src, extensions=["tables", "toc", "fenced_code"])

FIGURES = {
    "<!-- FIGURE:videostructure -->": """
<figure class="fig">
  <div class="timeline-bar">
    <div class="seg seg-hook"><b>훅 0–3초</b><small>클라이맥스 예고편</small></div>
    <div class="seg seg-main"><b>메인</b><small>통념 교정 → 원리 → 방식·이유 → 한계·개인차</small></div>
    <div class="seg seg-cta"><b>CTA</b><small>행동 1개</small></div>
  </div>
  <figcaption>기획안 한 줄이 펼쳐지는 35~40초의 구조 — 길이는 상한이지 목표가 아니다</figcaption>
</figure>""",
    "<!-- FIGURE:phone -->": """
<figure class="fig">
  <div class="phone">
    <div class="ph-point">(3시간째 상담 중)</div>
    <div class="ph-big">양이 아니라 <em>위치</em>가 정합니다</div>
    <div class="ph-say">입술은 0.1cc 차이로 인상이 바뀌는 부위예요</div>
    <div class="ph-safe">하단 20% · 플랫폼 UI 세이프존 — 비워 둔다</div>
  </div>
  <figcaption>자막 3종의 화면 배치 — 위부터 포인트 「소」 · 강조 「대」(중앙) · 말 「중」.<br>음소거로 재생해도 셋이 눈으로 구분되면 통과다</figcaption>
</figure>""",
    "<!-- FIGURE:anatomy-timeline -->": """
<figure class="fig">
  <div class="flow">
    <div class="flow-step"><b>D-14</b><span>기획 회의</span></div><div class="flow-arrow">→</div>
    <div class="flow-step"><b>D-13</b><span>병원 컨펌</span></div><div class="flow-arrow">→</div>
    <div class="flow-step"><b>D-7</b><span>촬영 12분</span></div><div class="flow-arrow">→</div>
    <div class="flow-step"><b>D-5</b><span>편집 배정</span></div><div class="flow-arrow">→</div>
    <div class="flow-step"><b>D-3</b><span>검수 3건 적발</span></div><div class="flow-arrow">→</div>
    <div class="flow-step"><b>D-2</b><span>피드백 번역</span></div><div class="flow-arrow">→</div>
    <div class="flow-step"><b>D-Day</b><span>업로드</span></div>
  </div>
  <figcaption>한 편의 여정 — 이 장은 이 타임라인을 그대로 따라간다</figcaption>
</figure>""",
}
for marker, fig in FIGURES.items():
    html_body = html_body.replace(marker, fig)

soup = BeautifulSoup(html_body, "html.parser")

# 파이프라인 ASCII 블록 → 흐름도
for pre in soup.find_all("pre"):
    if "① 소싱" in pre.get_text():
        fig = BeautifulSoup("""
<figure class="fig">
  <div class="flow">
    <div class="flow-step"><b>① 소싱</b><span>레퍼런스 수집</span></div><div class="flow-arrow">→</div>
    <div class="flow-step"><b>② 솔팅</b><span>쓸 것 선별</span></div><div class="flow-arrow">→</div>
    <div class="flow-step"><b>③ 제작</b><span>캡컷 편집</span></div><div class="flow-arrow">→</div>
    <div class="flow-step"><b>④ 검수</b><span>규격·톤 확인</span></div><div class="flow-arrow">→</div>
    <div class="flow-step"><b>⑤ 납품</b><span>완성본 업로드</span></div>
  </div>
</figure>""", "html.parser")
        pre.replace_with(fig)

# 1) 체크리스트 항목
for li in soup.find_all("li"):
    txt = li.decode_contents()
    if txt.startswith("CHKBOX "):
        li["class"] = li.get("class", []) + ["check"]
        li.clear()
        li.append(BeautifulSoup(txt[len("CHKBOX "):], "html.parser"))
        li.parent["class"] = li.parent.get("class", []) + ["checklist"]

# 2) 넓은 표(6열 이상) → 카드 스택
CHIP_COLS = {"촬영장소", "유형", "#"}
for table in soup.find_all("table"):
    headers = [th.get_text(strip=True) for th in table.find_all("th")]
    if len(headers) < 6:
        continue
    deck = soup.new_tag("div", attrs={"class": "cards"})
    for tr in table.find_all("tr")[1:]:
        cells = tr.find_all("td")
        if not cells or all(not c.get_text(strip=True) for c in cells):
            continue
        card = soup.new_tag("article", attrs={"class": "card"})
        head = soup.new_tag("div", attrs={"class": "card-head"})
        body = soup.new_tag("div", attrs={"class": "card-body"})
        for h, c in zip(headers, cells):
            val = c.get_text(strip=True)
            if not val:
                continue
            if h in CHIP_COLS:
                chip = soup.new_tag("span", attrs={"class": "chip"})
                chip.string = val
                head.append(chip)
            else:
                field = soup.new_tag("div", attrs={"class": "field"})
                lab = soup.new_tag("span", attrs={"class": "field-label"})
                lab.string = h
                fv = soup.new_tag("span", attrs={"class": "field-value"})
                fv.append(BeautifulSoup(c.decode_contents(), "html.parser"))
                field.append(lab)
                field.append(fv)
                body.append(field)
        card.append(head)
        card.append(body)
        deck.append(card)
    table.replace_with(deck)

# 3) 남은 표 래핑
for table in soup.find_all("table"):
    wrap = soup.new_tag("div", attrs={"class": "table-wrap"})
    table.replace_with(wrap)
    wrap.append(table)

# 4) 요약/면책 인용구 구분
for bq in soup.find_all("blockquote"):
    text = bq.get_text()
    if "요약" in text[:30]:
        bq["class"] = bq.get("class", []) + ["summary"]
    elif "⚠️" in text or "면책" in text[:20]:
        bq["class"] = bq.get("class", []) + ["notice"]

CSS = """
:root{
  --paper:#F6F8F6; --ink:#1E2422; --muted:#5E6963;
  --accent:#0F7D67; --accent-soft:#E4F0EB; --line:#DBE2DD; --card:#FFFFFF;
}
@media (prefers-color-scheme: dark){:root{
  --paper:#141A17; --ink:#E5EBE7; --muted:#8FA098;
  --accent:#4CC3A0; --accent-soft:#1D2B26; --line:#29342E; --card:#1A211D;
}}
:root[data-theme="dark"]{
  --paper:#141A17; --ink:#E5EBE7; --muted:#8FA098;
  --accent:#4CC3A0; --accent-soft:#1D2B26; --line:#29342E; --card:#1A211D;
}
:root[data-theme="light"]{
  --paper:#F6F8F6; --ink:#1E2422; --muted:#5E6963;
  --accent:#0F7D67; --accent-soft:#E4F0EB; --line:#DBE2DD; --card:#FFFFFF;
}
*{box-sizing:border-box}
body{
  margin:0; background:var(--paper); color:var(--ink);
  font-family:'Pretendard Variable',Pretendard,'Apple SD Gothic Neo','Noto Sans KR','Malgun Gothic',sans-serif;
  font-size:17px; line-height:1.85; word-break:keep-all;
}
.page{max-width:700px; margin:0 auto; padding:64px 24px 120px}
h1,h2,h3{font-family:'Noto Serif KR','Nanum Myeongjo',AppleMyungjo,Batang,serif; line-height:1.4; text-wrap:balance}
h1{font-size:1.9rem; font-weight:700; margin:4.5rem 0 1.2rem; padding-top:2.2rem; border-top:1px solid var(--line)}
h1:first-of-type{border-top:none; padding-top:0; margin-top:0; font-size:2.5rem; letter-spacing:-.01em}
h1:first-of-type + h3{border:none; margin-top:-0.6rem; color:var(--muted); font-weight:500; font-size:1.05rem}
h2{font-size:1.28rem; font-weight:700; margin:2.6rem 0 .9rem; color:var(--ink)}
h3{font-size:1.05rem; margin:2rem 0 .7rem}
p{margin:0 0 1.05em}
strong{color:var(--ink)}
a{color:var(--accent)}
hr{border:none; border-top:1px solid var(--line); margin:3rem 0}
blockquote{
  margin:1.6rem 0; padding:1rem 1.25rem; background:var(--card);
  border-left:3px solid var(--accent); border-radius:0 8px 8px 0;
  color:var(--muted); font-size:.95rem;
}
blockquote p{margin:0 0 .5em} blockquote p:last-child{margin:0}
blockquote.summary{background:var(--accent-soft); color:var(--ink); border-left-color:var(--accent)}
blockquote.notice{border-left-color:#C08A3E}
ul,ol{padding-left:1.3em; margin:0 0 1.1em}
li{margin:.35em 0}
li::marker{color:var(--accent)}
ul.checklist{list-style:none; padding:0; margin:1.2rem 0; display:flex; flex-direction:column; gap:8px}
ul.checklist li.check{
  background:var(--card); border:1px solid var(--line); border-radius:8px;
  padding:.6rem .9rem .6rem 2.5rem; position:relative; margin:0;
}
ul.checklist li.check::before{
  content:""; position:absolute; left:.9rem; top:.95rem; width:15px; height:15px;
  border:1.6px solid var(--accent); border-radius:4px;
}
.table-wrap{overflow-x:auto; margin:1.4rem 0; border:1px solid var(--line); border-radius:10px; background:var(--card)}
table{border-collapse:collapse; width:100%; font-size:.9rem; line-height:1.6}
th{
  text-align:left; font-weight:600; color:var(--accent); background:var(--accent-soft);
  padding:.65rem .85rem; white-space:nowrap; font-size:.82rem; letter-spacing:.02em;
}
td{padding:.6rem .85rem; border-top:1px solid var(--line); vertical-align:top; min-width:5.5em}
td:first-child,th:first-child{padding-left:1.1rem}
tbody tr:nth-child(even) td{background:color-mix(in srgb, var(--accent-soft) 30%, transparent)}
td{font-variant-numeric:tabular-nums}
.cards{display:flex; flex-direction:column; gap:14px; margin:1.6rem 0}
.card{background:var(--card); border:1px solid var(--line); border-radius:12px; padding:1.05rem 1.2rem}
.card-head{display:flex; gap:8px; flex-wrap:wrap; margin-bottom:.7rem}
.card-head:empty{display:none}
.chip{
  display:inline-block; background:var(--accent-soft); color:var(--accent);
  font-size:.78rem; font-weight:600; padding:.18rem .7rem; border-radius:999px; letter-spacing:.03em;
}
.card-body{display:flex; flex-direction:column; gap:.55rem}
.field{display:grid; grid-template-columns:5.2em 1fr; gap:.9em; font-size:.93rem}
.field-label{color:var(--muted); font-size:.78rem; font-weight:600; letter-spacing:.05em; padding-top:.15em}
.field-value{line-height:1.7}
@media (max-width:520px){.field{grid-template-columns:1fr; gap:.15em}}
@media (prefers-reduced-motion:no-preference){
  .card{transition:border-color .15s ease}
  .card:hover{border-color:var(--accent)}
}
.fig{margin:2rem 0}
.fig figcaption{text-align:center; color:var(--muted); font-size:.8rem; margin-top:.75rem; line-height:1.6}
.flow{display:flex; flex-wrap:wrap; gap:6px; align-items:center; justify-content:center}
.flow-step{background:var(--card); border:1px solid var(--line); border-radius:10px; padding:.5rem .75rem; text-align:center; display:flex; flex-direction:column; gap:.1rem; min-width:84px}
.flow-step b{font-size:.86rem; color:var(--ink); font-family:inherit}
.flow-step span{font-size:.72rem; color:var(--muted)}
.flow-arrow{color:var(--accent); font-weight:700}
.timeline-bar{display:flex; border-radius:10px; overflow:hidden; text-align:center}
.seg{padding:.65rem .4rem; color:#fff; display:flex; flex-direction:column; gap:.1rem; justify-content:center}
.seg b{font-size:.85rem} .seg small{font-size:.68rem; opacity:.85}
.seg-hook{background:var(--accent); width:21%}
.seg-main{background:color-mix(in srgb, var(--accent) 55%, var(--ink)); flex:1}
.seg-cta{background:color-mix(in srgb, var(--accent) 30%, var(--ink)); width:16%}
.phone{position:relative; aspect-ratio:9/16; max-width:250px; margin:0 auto; border:2px solid var(--line); border-radius:22px; overflow:hidden; font-size:.8rem;
  background:linear-gradient(165deg, color-mix(in srgb, var(--accent) 14%, var(--card)), var(--card) 70%)}
.ph-point{position:absolute; top:13%; left:9%; color:var(--muted); font-size:.7rem}
.ph-big{position:absolute; top:40%; width:100%; text-align:center; font-weight:900; font-size:1.08rem; padding:0 14px; color:var(--ink); line-height:1.45}
.ph-big em{font-style:normal; color:var(--accent)}
.ph-say{position:absolute; bottom:23%; width:100%; text-align:center; font-size:.76rem; color:var(--ink); padding:0 14px}
.ph-safe{position:absolute; bottom:0; height:20%; width:100%; display:flex; align-items:center; justify-content:center; text-align:center; font-size:.64rem; color:var(--muted); padding:0 10px;
  border-top:1.5px dashed var(--muted);
  background:repeating-linear-gradient(45deg, transparent 0 6px, color-mix(in srgb, var(--muted) 16%, transparent) 6px 12px)}
"""

out = f"""<title>병원 숏폼으로 먹고삽니다 — 초안 v0.3 리딩본</title>
<style>{CSS}</style>
<div class="page">
{soup.decode()}
</div>
"""
(ROOT / "reading.html").write_text(out, encoding="utf-8")
print("built:", (ROOT / "reading.html").stat().st_size, "bytes")
