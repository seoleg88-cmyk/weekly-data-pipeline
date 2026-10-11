"""
주간 브리핑 발행 도구 생성 + 발행 전 자동 검사.

사용:
  python scripts/build_tool.py --date 20261012 --dir OUT [--facts facts.json] [--playwright]

OUT 안의 아래 세 파일을 읽는다 (YYYYMMDD = 이번주 월요일):
  weekly-briefing-naver-YYYYMMDD.html
  weekly-briefing-tistory-YYYYMMDD.html
  weekly-briefing-blogger-YYYYMMDD-en.html
결과: OUT/weekly-briefing-tool-YYYYMMDD.html  (검사 실패 시 종료코드 1, 실패 항목 출력)

제목·태그·라벨은 본문에서 자동 추출한다:
  네이버 = 첫 <p> 텍스트 / 마지막 해시태그 문단, 티스토리·Blogger = <h1> / 상단 주석의 태그·라벨 줄
facts.json(선택)의 "must_appear": ["6,625.93", ...] 는 세 파일 모두에 들어 있어야 한다.
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

BANNED = ["자동화", "파이프라인", "automated", "pipeline"]
KO_WD = "월화수목금토일"
EN_WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
EN_MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def strip_tags(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


def leading_comment(html):
    m = re.match(r"\s*<!--(.*?)-->", html, re.S)
    return (m.group(1) if m else ""), (html[m.end():].lstrip() if m else html)


def comment_list(comment, marker):
    lines = comment.splitlines()
    for i, ln in enumerate(lines):
        if marker in ln:
            for nxt in lines[i + 1:]:
                if nxt.strip():
                    return nxt.strip()
    return ""


class Depth(HTMLParser):
    def __init__(self):
        super().__init__()
        self.depth = self.max = 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.depth += 1
            self.max = max(self.max, self.depth)

    def handle_endtag(self, tag):
        if tag == "table":
            self.depth -= 1


def check_weekdays(text, year):
    errs = []
    for m in re.finditer(r"(?<!\d)(\d{1,2})/(\d{1,2})\s*\(([월화수목금토일])\)", text):
        mo, d, wd = int(m.group(1)), int(m.group(2)), m.group(3)
        try:
            real = KO_WD[date(year, mo, d).weekday()]
        except ValueError:
            continue
        if real != wd:
            errs.append(f"{m.group(0)} → 실제 {real}요일")
    pat_en = r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\w*,?\s+(%s)\w*\s+(\d{1,2})\b" % "|".join(EN_MON)
    for m in re.finditer(pat_en, text):
        wd, mo, d = m.group(1), EN_MON.index(m.group(2)) + 1, int(m.group(3))
        try:
            real = EN_WD[date(year, mo, d).weekday()]
        except ValueError:
            continue
        if real != wd:
            errs.append(f"{m.group(0)} → actually {real}")
    pat_en2 = r"\b(%s)\w*\s+(\d{1,2})\s*\((Mon|Tue|Wed|Thu|Fri|Sat|Sun)\)" % "|".join(EN_MON)
    for m in re.finditer(pat_en2, text):
        mo, d, wd = EN_MON.index(m.group(1)) + 1, int(m.group(2)), m.group(3)
        try:
            real = EN_WD[date(year, mo, d).weekday()]
        except ValueError:
            continue
        if real != wd:
            errs.append(f"{m.group(0)} → actually {real}")
    return errs


def check_links(html, allow_sources_block):
    """외부 링크 금지. 티스토리·Blogger는 id="sources" 블록 이후만 허용."""
    cut = len(html)
    if allow_sources_block:
        m = re.search(r'id="sources"', html)
        cut = m.start() if m else len(html)
    bad = [h for h in re.findall(r'<a\s[^>]*href="([^"#][^"]*)"', html[:cut])]
    return [f"본문 외부 링크: {h}" for h in bad]


def run_checks(name, html, body, year, facts):
    errs = []
    text = strip_tags(body)
    for w in BANNED:
        if w.lower() in text.lower():
            errs.append(f"금지어 '{w}' 노출")
    errs += check_links(body, allow_sources_block=(name != "naver"))
    errs += check_weekdays(text, year)
    if name == "naver":
        if re.search(r"<div\b", body, re.I):
            errs.append("<div> 사용")
        if re.search(r"<style\b", body, re.I):
            errs.append("<style> 사용")
        p = Depth()
        p.feed(body)
        if p.max > 1:
            errs.append(f"table 중첩 깊이 {p.max}")
    for s in (facts or {}).get("must_appear", []):
        if s not in body:
            errs.append(f"사실표 값 누락: {s}")
    return errs


TEMPLATE = r"""<!doctype html>
<html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>주간 브리핑 발행 도구 - __LABEL__</title>
<style>
*{box-sizing:border-box}body{font-family:'Noto Sans KR',-apple-system,sans-serif;margin:0;background:#f4f5f7;color:#222}
.wrap{max-width:920px;margin:0 auto;padding:24px 16px 70px}h1{font-size:19px;margin:6px 0 4px}.sub{color:#777;font-size:13px;margin-bottom:20px}
.tabs{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}.tab-btn{padding:10px 20px;border-radius:8px;border:1px solid #ddd;background:#fff;cursor:pointer;font-size:14px;font-weight:700;color:#555}
.tab-btn.active{background:#222;color:#fff;border-color:#222}.panel{display:none;background:#fff;border-radius:10px;padding:20px;border:1px solid #e5e5e5}.panel.active{display:block}
.row{display:flex;align-items:center;gap:8px;margin-bottom:10px;flex-wrap:wrap}.lbl{font-size:13px;font-weight:700;color:#555;min-width:50px}
.val{flex:1;min-width:200px;font-size:13.5px;background:#f7f7f8;padding:9px 10px;border-radius:6px;border:1px solid #eee;overflow-x:auto;white-space:nowrap}
.btn{padding:9px 16px;border-radius:6px;border:none;background:#6c4bd6;color:#fff;font-size:13px;font-weight:700;cursor:pointer;white-space:nowrap}.btn.alt{background:#1a73e8}
iframe{width:100%;height:560px;border:1px solid #ddd;border-radius:6px;background:#fff}textarea{width:100%;height:160px;font-family:Menlo,Consolas,monospace;font-size:11.5px;border:1px solid #ddd;border-radius:6px;padding:8px}
.guide{background:#fffbe6;border:1px solid #ffe58f;border-radius:8px;padding:12px 14px;font-size:13px;color:#664d03;margin-bottom:16px;line-height:1.65}
.st{font-size:13.5px;font-weight:800;margin:18px 0 8px}.toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:#222;color:#fff;padding:11px 20px;border-radius:20px;font-size:13px;opacity:0;transition:opacity .2s;pointer-events:none}.toast.show{opacity:1}
</style></head><body><div class="wrap">
<h1>주간 브리핑 발행 도구 — __LABEL__</h1>
<p class="sub">탭을 고르고 복사 버튼을 누른 뒤 각 블로그 글쓰기 화면에 붙여넣으세요.</p>
<div class="tabs"><button class="tab-btn active" data-tab="naver">네이버 블로그</button><button class="tab-btn" data-tab="tistory">티스토리</button><button class="tab-btn" data-tab="blogger">Blogger</button></div>
<div id="panel-naver" class="panel active">
<div class="guide">네이버 에디터는 HTML 붙여넣기를 지원하지 않습니다. "본문 전체 복사" 후 본문 입력창에 붙여넣으세요.</div>
<div class="row"><span class="lbl">제목</span><span class="val" id="naver-title"></span><button class="btn" data-copy="naver-title">제목 복사</button></div>
<div class="st">본문 미리보기</div><iframe id="naver-frame"></iframe>
<p><button class="btn" data-rich="naver-frame">📋 본문 전체 복사</button></p>
<div class="row"><span class="lbl">태그</span><span class="val" id="naver-tags"></span><button class="btn" data-copy="naver-tags">태그 복사</button></div>
</div>
<div id="panel-tistory" class="panel">
<div class="guide">글쓰기 화면 우측 상단에서 "HTML" 모드로 바꾼 뒤 "HTML 복사" 내용을 붙여넣고, 기본모드로 돌아와 확인하세요.</div>
<div class="row"><span class="lbl">제목</span><span class="val" id="tistory-title"></span><button class="btn" data-copy="tistory-title">제목 복사</button></div>
<div class="st">미리보기</div><iframe id="tistory-frame"></iframe>
<div class="st">HTML 코드</div><textarea id="tistory-src" readonly></textarea>
<p><button class="btn alt" data-area="tistory-src">💻 HTML 복사</button></p>
<div class="row"><span class="lbl">태그</span><span class="val" id="tistory-tags"></span><button class="btn" data-copy="tistory-tags">태그 복사</button></div>
</div>
<div id="panel-blogger" class="panel">
<div class="guide">"HTML 보기"에 "HTML 복사" 내용을 붙여넣는 방식이 가장 안정적입니다. 작성 보기에는 "본문 전체 복사"를 쓰세요.</div>
<div class="row"><span class="lbl">Title</span><span class="val" id="blogger-title"></span><button class="btn" data-copy="blogger-title">제목 복사</button></div>
<div class="st">미리보기</div><iframe id="blogger-frame"></iframe>
<p><button class="btn" data-rich="blogger-frame">📋 본문 전체 복사 (작성 보기용)</button></p>
<div class="st">HTML 코드 (HTML 보기용)</div><textarea id="blogger-src" readonly></textarea>
<p><button class="btn alt" data-area="blogger-src">💻 HTML 복사</button></p>
<div class="row"><span class="lbl">Labels</span><span class="val" id="blogger-tags"></span><button class="btn" data-copy="blogger-tags">라벨 복사</button></div>
</div></div><div class="toast" id="toast"></div>
<script type="application/json" id="data">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const shell = (lang, body) => '<!doctype html><html lang="' + lang + '"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{margin:0;padding:16px;font-family:\'Noto Sans KR\',-apple-system,sans-serif;color:#222;line-height:1.6;background:#fff}img{max-width:100%}</style></head><body>' + body + '</body></html>';
for (const k of ['naver', 'tistory', 'blogger']) {
  document.getElementById(k + '-title').textContent = D[k].title;
  document.getElementById(k + '-tags').textContent = D[k].tags;
  document.getElementById(k + '-frame').srcdoc = shell(k === 'blogger' ? 'en' : 'ko', D[k].body);
  const ta = document.getElementById(k + '-src'); if (ta) ta.value = D[k].body;
}
function toast(m) { const t = document.getElementById('toast'); t.textContent = m; t.classList.add('show'); clearTimeout(window.__t); window.__t = setTimeout(() => t.classList.remove('show'), 1800); }
function copyPlain(text) { const t = document.createElement('textarea'); t.value = text; t.style.position = 'fixed'; t.style.left = '-9999px'; document.body.appendChild(t); t.select(); let ok = false; try { ok = document.execCommand('copy'); } catch (e) {} document.body.removeChild(t); return ok; }
document.addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b) return;
  if (b.dataset.tab) { document.querySelectorAll('.tab-btn').forEach(x => x.classList.toggle('active', x === b)); document.querySelectorAll('.panel').forEach(p => p.classList.toggle('active', p.id === 'panel-' + b.dataset.tab)); }
  if (b.dataset.copy) toast(copyPlain(document.getElementById(b.dataset.copy).textContent) ? '복사 완료!' : '복사 실패 - 직접 선택해 복사하세요');
  if (b.dataset.area) toast(copyPlain(document.getElementById(b.dataset.area).value) ? 'HTML 복사 완료!' : '복사 실패 - 직접 선택해 복사하세요');
  if (b.dataset.rich) { const f = document.getElementById(b.dataset.rich), doc = f.contentDocument, r = doc.createRange(); r.selectNodeContents(doc.body); const s = f.contentWindow.getSelection(); s.removeAllRanges(); s.addRange(r); let ok = false; try { ok = doc.execCommand('copy'); } catch (er) {} s.removeAllRanges(); toast(ok ? '본문 복사 완료! 글쓰기 창에 붙여넣으세요' : '복사 실패 - 미리보기를 직접 드래그해 복사하세요'); }
});
</script></body></html>
"""


def extract(name, html):
    comment, body = leading_comment(html)
    if name == "naver":
        m = re.search(r"<p[^>]*>(.*?)</p>", body, re.S)
        title = strip_tags(m.group(1)) if m else ""
        tags_p = re.findall(r"<p[^>]*>([^<]*#[^<]*)</p>", body, re.S)
        tags = ", ".join(t.lstrip("#") for t in re.findall(r"#\S+", tags_p[-1])) if tags_p else ""
    else:
        m = re.search(r"<h1[^>]*>(.*?)</h1>", body, re.S)
        title = strip_tags(m.group(1)) if m else ""
        tags = comment_list(comment, "[태그" if name == "tistory" else "[Suggested labels")
    return {"title": title, "tags": tags, "body": body}


def playwright_check(tool_path, expect):
    from playwright.sync_api import sync_playwright
    errs = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        js_err = []
        pg.on("pageerror", lambda e: js_err.append(str(e)))
        pg.goto(Path(tool_path).resolve().as_uri())
        pg.wait_for_timeout(800)
        for k in ("naver", "tistory", "blogger"):
            inner = pg.frame_locator(f"#{k}-frame").locator("body").inner_html()
            if expect[k] not in inner:
                errs.append(f"{k} 미리보기 비어 있음/제목 불일치")
        for k in ("tistory", "blogger"):
            if len(pg.eval_on_selector(f"#{k}-src", "e => e.value")) < 500:
                errs.append(f"{k} textarea 비어 있음")
        errs += [f"JS 오류: {e}" for e in js_err]
        b.close()
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="이번주 월요일 YYYYMMDD")
    ap.add_argument("--dir", default=".")
    ap.add_argument("--facts")
    ap.add_argument("--playwright", action="store_true")
    a = ap.parse_args()

    d = Path(a.dir)
    files = {
        "naver": d / f"weekly-briefing-naver-{a.date}.html",
        "tistory": d / f"weekly-briefing-tistory-{a.date}.html",
        "blogger": d / f"weekly-briefing-blogger-{a.date}-en.html",
    }
    facts = json.loads(Path(a.facts).read_text(encoding="utf-8")) if a.facts else None
    year = int(a.date[:4])
    data, report = {}, {}
    for k, f in files.items():
        html = f.read_text(encoding="utf-8")
        data[k] = extract(k, html)
        report[k] = run_checks(k, html, data[k]["body"], year, facts)
        if not data[k]["title"]:
            report[k].append("제목 추출 실패")
        if not data[k]["tags"]:
            report[k].append("태그/라벨 추출 실패")

    label = f"{a.date[:4]}.{a.date[4:6]}.{a.date[6:]} 주간"
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    out = d / f"weekly-briefing-tool-{a.date}.html"
    out.write_text(TEMPLATE.replace("__LABEL__", label).replace("__DATA__", payload), encoding="utf-8")

    script = re.findall(r"<script>(.*?)</script>", out.read_text(encoding="utf-8"), re.S)[-1]
    js = d / ".tool_check.js"
    js.write_text(script, encoding="utf-8")
    r = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
    js.unlink()
    tool_errs = [] if r.returncode == 0 else [f"node --check 실패: {r.stderr.strip()[:300]}"]
    if a.playwright:
        tool_errs += playwright_check(out, {k: v["title"][:20] for k, v in data.items()})
    report["tool"] = tool_errs

    failed = False
    for k, errs in report.items():
        print(f"[{k}] " + ("OK" if not errs else "FAIL"))
        for e in errs:
            print("   -", e)
        failed |= bool(errs)
    print(f"→ {out}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
