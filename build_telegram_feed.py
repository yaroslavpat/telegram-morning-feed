import base64
import concurrent.futures
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

ROOT = Path(__file__).resolve().parent
OPML = ROOT / 'TelegramChannels.opml'
HOURS = int(sys.argv[1]) if len(sys.argv) > 1 else 48
OUT_JSON = ROOT / 'work' / 'telegram_posts.json'
now = datetime.now(timezone.utc)
cutoff = now - timedelta(hours=HOURS)
root = ET.parse(OPML).getroot()
channels = [(x.attrib.get('text') or x.attrib.get('title') or '', x.attrib.get('xmlUrl') or '') for x in root.findall('.//outline')]
HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/128 Safari/537.36'}
ALLOWED_INLINE_TAGS = {'b', 'strong', 'i', 'em', 'u', 's', 'del', 'code', 'pre', 'blockquote'}

def clean_message_html(node):
    parts = []
    for child in node.children:
        if isinstance(child, NavigableString):
            value = re.sub(r'\s+', ' ', str(child))
            parts.append(html.escape(value, quote=False))
            continue
        if not isinstance(child, Tag):
            continue
        if child.name == 'br':
            parts.append('<br>')
            continue
        content = clean_message_html(child)
        if child.name == 'a':
            href = child.get('href', '')
            if urlparse(href).scheme in ('https', 'http', 'tg'):
                parts.append(f'<a href="{html.escape(href, quote=True)}" target="_blank" rel="noopener">{content}</a>')
            else:
                parts.append(content)
        elif child.name in ALLOWED_INLINE_TAGS:
            tag = 'strong' if child.name == 'b' else ('em' if child.name == 'i' else child.name)
            parts.append(f'<{tag}>{content}</{tag}>')
        else:
            parts.append(content)
    return re.sub(r'\s+([,.;:!?])', r'\1', ''.join(parts))

def inline_image(url, max_bytes=5_000_000):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200 or not r.headers.get('content-type', '').startswith('image/') or len(r.content) > max_bytes:
            return ''
        mime = r.headers.get('content-type', 'image/jpeg').split(';')[0]
        return 'data:' + mime + ';base64,' + base64.b64encode(r.content).decode('ascii')
    except Exception:
        return ''

def background_url(element):
    match = re.search(r"url\(['\"]?(.*?)['\"]?\)", element.get('style', ''))
    return match.group(1) if match else ''

def get_channel(item):
    name, url = item
    username = urlparse(url).path.strip('/').split('/')[-1]
    page = 'https://t.me/s/' + username
    try:
        response = requests.get(page, headers=HEADERS, timeout=18)
        if response.status_code != 200:
            return {'name': name, 'username': username, 'status': response.status_code, 'posts': []}
        soup = BeautifulSoup(response.text, 'html.parser')
        title = soup.select_one('.tgme_channel_info_header_title')
        avatar_tag = soup.select_one('.tgme_page_photo_image img')
        if not avatar_tag:
            avatar_tag = soup.select_one('.tgme_widget_message_user_photo img')
        avatar_url = avatar_tag.get('src', '') if avatar_tag else ''
        avatar = inline_image(avatar_url) if avatar_url else ''
        posts, seen = [], set()
        cursor, page_count = None, 0
        while page_count < 8:
            response = requests.get(page, params={'before': cursor} if cursor else None, headers=HEADERS, timeout=18)
            if response.status_code != 200:
                break
            page_soup = BeautifulSoup(response.text, 'html.parser')
            wraps = page_soup.select('.tgme_widget_message_wrap')
            if not wraps:
                break
            oldest_time, oldest_id = None, None
            for wrap in wraps:
                msg = wrap.select_one('.tgme_widget_message')
                if not msg:
                    continue
                ident = msg.get('data-post', '')
                if not ident or ident in seen:
                    continue
                seen.add(ident)
                try:
                    msg_id = int(ident.rsplit('/', 1)[-1])
                    oldest_id = msg_id if oldest_id is None else min(oldest_id, msg_id)
                except ValueError:
                    pass
                date_tag = wrap.select_one('time[datetime]')
                if not date_tag:
                    continue
                try:
                    ts = datetime.fromisoformat(date_tag.get('datetime').replace('Z', '+00:00'))
                except Exception:
                    continue
                oldest_time = ts if oldest_time is None or ts < oldest_time else oldest_time
                if ts < cutoff:
                    continue
                text_tag = wrap.select_one('.tgme_widget_message_text')
                rich = clean_message_html(text_tag) if text_tag else ''
                plain = re.sub(r'\s+([,.;:!?])', r'\1', text_tag.get_text(' ', strip=True)) if text_tag else ''
                post_link = wrap.select_one('a.tgme_widget_message_date')
                post_url = post_link.get('href') if post_link else 'https://t.me/' + ident
                image_urls = [background_url(el) for el in wrap.select('.tgme_widget_message_photo_wrap')]
                if not image_urls:
                    image_urls = [background_url(el) for el in wrap.select('.tgme_widget_message_video_thumb')]
                image_urls = [u for u in image_urls if u]
                posts.append({'channel': name, 'username': username, 'avatar': avatar, 'date': ts.isoformat(), 'date_text': date_tag.get_text(strip=True), 'text': plain, 'html': rich, 'url': post_url, 'images': image_urls})
            page_count += 1
            if oldest_time is None or oldest_time < cutoff or not oldest_id:
                break
            if cursor is not None and oldest_id >= cursor:
                break
            cursor = oldest_id
        return {'name': title.get_text(' ', strip=True) if title else name, 'username': username, 'status': 200, 'posts': posts}
    except Exception as error:
        return {'name': name, 'username': username, 'status': str(error), 'posts': []}

with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
    results = list(pool.map(get_channel, channels))
posts = [post for channel in results for post in channel['posts']]
posts.sort(key=lambda post: post['date'], reverse=True)
OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
OUT_JSON.write_text(json.dumps({'generated': now.isoformat(), 'hours': HOURS, 'channels': results, 'posts': posts}, ensure_ascii=False), encoding='utf8')
loaded = sum(channel['status'] == 200 for channel in results)
failed = sum(channel['status'] != 200 for channel in results)
quiet = sum(channel['status'] == 200 and not channel['posts'] for channel in results)
images = sum(len(post['images']) for post in posts)
print(f'channels={len(channels)} posts={len(posts)} quiet={quiet} failed={failed} images={images}')
