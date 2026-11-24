import json
import html
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup, NavigableString, Tag

ROOT = Path(__file__).resolve().parent
x = json.load(open(ROOT / 'work' / 'telegram_posts.json', encoding='utf8'))
posts = x['posts']
def esc(v):
    return html.escape(v or '', quote=True)

def wrap_rich_tag(node, content):
    if not content:
        return ''
    if node.name == 'a':
        href = node.get('href', '')
        if urlparse(href).scheme in ('http', 'https', 'tg'):
            return f'<a href="{esc(href)}" target="_blank" rel="noopener">{content}</a>'
        return content
    tag_map = {'b': 'strong', 'i': 'em', 'strong': 'strong', 'em': 'em', 'u': 'u', 's': 's', 'del': 'del', 'code': 'code', 'pre': 'pre', 'blockquote': 'blockquote'}
    tag = tag_map.get(node.name)
    return f'<{tag}>{content}</{tag}>' if tag else content

def split_rich_node(node, budget):
    if isinstance(node, NavigableString):
        raw = str(node)
        if len(raw) <= budget:
            return esc(raw), '', budget - len(raw), False
        cut = max(0, budget)
        boundary = max(raw.rfind(' ', 0, cut + 1), raw.rfind('\n', 0, cut + 1))
        if cut and boundary >= cut - 40:
            cut = boundary
        return esc(raw[:cut]), esc(raw[cut:]), budget - cut, True
    if not isinstance(node, Tag):
        return '', '', budget, False
    if node.name == 'br':
        return ('<br>', '', budget, False) if budget > 0 else ('', '<br>', budget, True)
    left_parts, right_parts = [], []
    remaining, divided = budget, False
    for child in node.children:
        if not divided:
            left, right, remaining, child_divided = split_rich_node(child, remaining)
            left_parts.append(left)
            if child_divided:
                right_parts.append(right)
                divided = True
        else:
            _, right, _, _ = split_rich_node(child, 0)
            right_parts.append(right)
    return wrap_rich_tag(node, ''.join(left_parts)), wrap_rich_tag(node, ''.join(right_parts)), remaining, divided

def split_rich_html(fragment, limit=255):
    soup = BeautifulSoup(fragment or '', 'html.parser')
    left, right, _, divided = split_rich_node(soup, limit)
    return (left, right) if divided else (left, '')

def card(p):
    text = p.get('text', '').strip()
    rich = p.get('html') or esc(text).replace('\n', '<br>')
    if len(text) > 255:
        preview_html, continuation_html = split_rich_html(rich, 255)
        content = (
            f'<div class="body"><span>{preview_html}</span>'
            f'<span class="continuation" hidden>{continuation_html}</span>'
            f'<button class="read-more" type="button">Читать полностью</button></div>'
        )
    else:
        content = f'<div class="body">{rich or "(пост без текста)"}</div>'
    imgs = ''.join(
        f'<img loading="lazy" src="{esc(src)}" alt="Изображение из поста канала {esc(p["channel"])}">'
        for src in p.get('images', [])
    )
    date = datetime.fromisoformat(p['date']).astimezone(ZoneInfo('Europe/Samara')).strftime('%d.%m · %H:%M')
    avatar = f'<img class="avatar" loading="lazy" src="{esc(p.get("avatar"))}" alt="" onerror="this.hidden=true">' if p.get('avatar') else '<div class="avatar fallback">◉</div>'
    return (
        f'<article class="post" data-username="{esc(p.get("username", "").lower())}">'
        f'<header class="post-header">{avatar}<div class="meta"><b>{esc(p["channel"])}</b><time>{esc(date)}</time></div></header>'
        f'<div class="content">{content}{imgs}<a class="open" href="{esc(p["url"])}" target="_blank" rel="noopener" aria-label="Открыть пост в Telegram">↗</a></div></article>'
    )

body = ''.join(card(p) for p in posts)
page = f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light dark"><title>Утренняя лента Telegram</title><style>
:root{{color-scheme:light dark;--bg:#f5f5f7;--fg:#19191c;--muted:#74747c;--card:#fff;--line:#e5e5e9;--accent:#7368df;--soft:#f0efff;--accent-fg:#fff}}
@media(prefers-color-scheme:dark){{:root{{--bg:#151518;--fg:#f3f3f5;--muted:#a4a4ad;--card:#222226;--line:#3a3a40;--soft:#302d49;--accent:#9b93ff;--accent-fg:#151518}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}main{{max-width:760px;margin:auto;padding:20px 14px 50px}}
.topbar{{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:12px;padding:8px 4px 16px}}.feed-heading{{display:flex;align-items:center;gap:11px;min-width:0}}.feed-icon{{width:64px;height:64px;flex:0 0 64px;object-fit:cover;border-radius:16px}}h1{{font-size:24px;line-height:1.2;margin:0 0 6px}}.sub{{font-size:13px;color:var(--muted)}}.count-line{{margin-top:2px}}
.filter-control{{min-height:48px;min-width:44px;margin-left:auto;padding:4px 0 4px 12px;border:0;background:transparent;color:var(--fg);display:flex;align-items:center;gap:10px;font:inherit;font-size:22px;font-weight:600;cursor:pointer}}.filter-control:focus-visible{{outline:2px solid var(--accent);outline-offset:3px;border-radius:8px}}.ios-switch{{position:relative;width:52px;height:32px;flex:0 0 52px;border-radius:999px;background:#8e8e93;transition:background-color .18s ease}}.ios-switch::after{{content:"";position:absolute;top:2px;left:2px;width:28px;height:28px;border-radius:50%;background:#fff;box-shadow:0 1px 3px #0004;transition:transform .18s ease}}.filter-control[aria-checked="true"] .ios-switch{{background:#34c759}}.filter-control[aria-checked="true"] .ios-switch::after{{transform:translateX(20px)}}@media(prefers-reduced-motion:reduce){{.ios-switch,.ios-switch::after{{transition:none}}}}
h2{{font-size:17px;line-height:1.3;margin:0 0 8px}}a{{color:var(--accent);text-decoration:none}}
.post{{display:grid;grid-template-columns:minmax(0,1fr);row-gap:10px;padding:14px 12px;background:var(--card);border:1px solid var(--line);border-radius:15px;margin:10px 0}}.post[hidden]{{display:none}}.post-header{{display:grid;grid-template-columns:40px minmax(0,1fr);column-gap:11px;align-items:center}}.avatar{{width:40px;height:40px;flex:0 0 40px;border-radius:50%;object-fit:cover;background:var(--soft)}}.fallback{{display:grid;place-items:center;color:var(--muted)}}.content{{min-width:0;position:relative;padding-right:28px}}.meta{{display:flex;justify-content:space-between;gap:8px;align-items:baseline;margin:0}}.meta b{{font-size:14px;line-height:1.3}}time{{font-size:12px;color:var(--muted);white-space:nowrap}}.body,.full{{overflow-wrap:anywhere}}.read-more{{display:block;min-height:44px;margin-top:3px;padding:0;border:0;background:transparent;color:var(--accent);font:inherit;font-weight:600;text-align:left;cursor:pointer}}.read-more[hidden]{{display:none}}.continuation[hidden]{{display:none}}.content img:not(.avatar){{max-width:100%;height:auto;display:block;border-radius:10px;margin-top:10px}}.open{{position:absolute;right:0;bottom:0;width:44px;height:44px;border-radius:50%;background:var(--soft);display:grid;place-items:center;font-size:19px}}@media(max-width:600px){{main{{padding:14px 0 36px}}.topbar{{padding-left:14px;padding-right:14px}}.post{{padding:12px 14px;margin:8px 0;border-radius:0;border-left:0;border-right:0}}.post-header{{column-gap:9px}}.meta{{display:block}}time{{display:block;margin-top:2px}}}}@media(max-width:420px){{.feed-heading{{gap:10px}}.feed-icon{{width:52px;height:52px;flex-basis:52px}}h1{{font-size:21px}}.filter-control{{gap:7px;font-size:20px}}}}
</style></head><body><main><header class="topbar"><div class="feed-heading"><img class="feed-icon" src="assets/lighthouse.png" alt=""><div><h1>Утренняя лента</h1><div class="sub">{len(x['channels'])} каналов · за 48 часов · время Самары</div><div class="sub count-line"><span id="visible-count">{len(posts)} постов</span></div></div></div><button id="lifestyle-toggle" class="filter-control" type="button" role="switch" aria-checked="true" aria-label="Скрывать посты каналов Нож и Пчела" title="Скрывать посты Ножа и Пчелы"><span>🔪🐝</span><span class="ios-switch" aria-hidden="true"></span></button></header>{body}</main><script>
const lifestyleHandles = new Set(['knifemedia', 'pchelamedia']);
const toggle = document.getElementById('lifestyle-toggle');

const count = document.getElementById('visible-count');
const posts = Array.from(document.querySelectorAll('.post'));
for (const button of document.querySelectorAll('.read-more')) {{
  button.addEventListener('click', () => {{
    button.previousElementSibling.hidden = false;
    button.hidden = true;
  }});
}}
function applyLifestyleFilter() {{
  const hidden = toggle.getAttribute('aria-checked') === 'true';
  let visible = 0;
  for (const post of posts) {{
    const omit = hidden && lifestyleHandles.has((post.dataset.username || '').toLowerCase());
    post.hidden = omit;
    if (!omit) visible++;
  }}
  count.textContent = hidden ? `${{visible}} постов (без Ножа и Пчелы)` : `${{visible}} постов`;
}}
toggle.addEventListener('click', () => {{
  toggle.setAttribute('aria-checked', toggle.getAttribute('aria-checked') === 'true' ? 'false' : 'true');
  applyLifestyleFilter();
}});
applyLifestyleFilter();
</script></body></html>'''
out = ROOT / 'index.html'
out.write_text(page, encoding='utf8')
print(out.resolve(), out.stat().st_size)
