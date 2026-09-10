import yt_dlp
import os
import shutil
import subprocess

#  Silent logger (suppress yt-dlp console noise)
class _SilentLogger:
    def debug(self, msg):   pass
    def warning(self, msg): pass
    def error(self, msg):   print(f"[ENGINE ERROR] {msg}")

_COMMON_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'nocheckcertificate': True,
    'source_address': '0.0.0.0',
    'simulate': True,
    'format': 'all',
    'js_runtimes': {'node': {}},
    'impersonate': yt_dlp.networking.impersonate.ImpersonateTarget(client='chrome'),
    # ── Network stability ────────────────────────────────────────────────────
    'socket_timeout': 30,      # idle socket timeout (seconds)
    'retries': 10,             # retry on transient network errors
    'fragment_retries': 10,    # retry on fragment errors (HLS/DASH)
    # ── Playlist safety cap ──────────────────────────────────────────────────
    'playlistend': 100,        # max 100 entries per playlist fetch
}

import urllib.request
import json

#  Helper: Dynamic YouTube Extractor Args
def _get_youtube_args() -> dict:
    """
    Build yt-dlp extractor args for YouTube.
    
    Strategy (best → fallback):
      1. tv_embedded client  → no PO token required, bypasses bot detection
      2. bgutil POT server   → auto-generates PO tokens (needs bgutil running)
      3. POT_PROVIDER_URL    → external PO token REST API
      4. YT_PO_TOKEN env var → manual static PO token
    
    tv_embedded is the most reliable for server/datacenter IPs.
    """
    # ── Player clients: let yt-dlp use its own default selection ──────────────
    # DO NOT set player_client here — yt-dlp's default picks the best clients
    # automatically and returns the most formats (including 1080p, 4K, etc.)
    # Forcing a specific client (e.g. tv_embedded) limits available formats.
    yt_args: dict = {}

    # ── PO Token from remote provider URL ──
    provider_url = os.environ.get("POT_PROVIDER_URL")
    if provider_url:
        try:
            req = urllib.request.Request(provider_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
                po_token    = data.get("po_token")    or data.get("poToken")
                visitor_data = data.get("visitor_data") or data.get("visitorData")
                if po_token:
                    yt_args['po_token'] = po_token
                    print(f"[ENGINE POT] Token fetched from provider: {provider_url}")
                if visitor_data:
                    yt_args['visitor_data'] = visitor_data
        except Exception as e:
            print(f"[ENGINE POT ERROR] Failed to fetch from {provider_url}: {e}")

    # ── Fallback: direct env vars ──
    if 'po_token' not in yt_args and os.environ.get("YT_PO_TOKEN"):
        yt_args['po_token'] = os.environ.get("YT_PO_TOKEN")
        print("[ENGINE POT] Using YT_PO_TOKEN from environment")
    if 'visitor_data' not in yt_args and os.environ.get("YT_VISITOR_DATA"):
        yt_args['visitor_data'] = os.environ.get("YT_VISITOR_DATA")

    return yt_args

#  Helper: extract & rank formats (AUDIO ONLY)
def _extract_formats(info: dict) -> list[dict]:
    formats_dict: dict[str, dict] = {}
    
    for f in info.get('formats') or []:
        vcodec    = f.get('vcodec', 'none')
        acodec    = f.get('acodec', 'none')
        ext       = f.get('ext', '')
        url       = f.get('url') or f.get('manifest_url')
        format_id = f.get('format_id')
        
        if not url:
            continue

        # Audio Formats Only
        if vcodec == 'none' and acodec != 'none' and f.get('abr'):
            res = f"{int(f.get('abr'))}kbps"
            score = 0
            if ext == 'm4a': score += 5
            
            if res not in formats_dict or score > formats_dict.get(res, {}).get('score', -1):
                formats_dict[res] = {
                    'id': format_id, 'res': res, 'ext': ext, 'url': url, 'score': score,
                    'cookies': f.get('cookies') or info.get('cookies'),
                    'http_headers': f.get('http_headers') or info.get('http_headers')
                }

    def sort_key(item):
        res_str = item['res']
        if res_str.endswith('kbps'):
            return int(res_str.replace('kbps', ''))
        return 0

    sorted_formats = sorted(formats_dict.values(), key=sort_key, reverse=True)
    
    return [{'id': f['id'], 'res': f['res'], 'ext': f['ext'], 'url': f['url'], 'cookies': f.get('cookies'), 'http_headers': f.get('http_headers')} for f in sorted_formats]

def _get_best_audio(info: dict) -> dict:
    best_audio = None
    for f in info.get('formats') or []:
        vcodec = f.get('vcodec', 'none')
        acodec = f.get('acodec', 'none')
        url = f.get('url') or f.get('manifest_url')
        if vcodec == 'none' and acodec != 'none' and url:
            if not best_audio or (f.get('abr') or 0) > (best_audio.get('abr') or 0):
                best_audio = f
    if best_audio:
        raw = best_audio.get('url') or best_audio.get('manifest_url', '')
        return {
            'url':          raw,
            'direct_url':   raw,   # raw CDN URL — expose to trusted callers
            'cookies':      best_audio.get('cookies') or info.get('cookies'),
            'http_headers': best_audio.get('http_headers') or info.get('http_headers'),
            'ext':          best_audio.get('ext'),
            'abr':          best_audio.get('abr'),
            'acodec':       best_audio.get('acodec'),
            'filesize':     best_audio.get('filesize') or best_audio.get('filesize_approx'),
        }
    return {}

#  Public API functions
def check_ffmpeg() -> bool:
    """Return True if ffmpeg is available on this machine."""
    return shutil.which('ffmpeg') is not None or os.path.exists('ffmpeg.exe')

# ── Helper: build the result dict from an info dict ──────────────────────────
def _build_audio_result(src: dict) -> dict:
    return {
        'type':            'audio',
        'title':           src.get('title'),
        'thumb':           src.get('thumbnail'),
        'duration':        src.get('duration'),
        'duration_string': src.get('duration_string'),
        'uploader':        src.get('uploader') or src.get('channel'),
        'channel_url':     src.get('channel_url') or src.get('uploader_url'),
        'webpage_url':     src.get('webpage_url'),
        'upload_date':     src.get('upload_date'),
        'view_count':      src.get('view_count'),
        'description':     src.get('description'),
        'best_audio':      _get_best_audio(src),
        'formats':         _extract_formats(src),
    }

# ── Helper: run yt-dlp extract_info with given opts ──────────────────────────
def _run_extract(url: str, opts: dict, cookie_path: str | None):
    """Run yt-dlp extract_info and return (info_dict, cookie_path)."""
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
    finally:
        if cookie_path and os.path.exists(cookie_path):
            try:
                os.remove(cookie_path)
            except Exception:
                pass

def get_info(url: str) -> dict:
    """
    Fetch metadata for a single video, search query, or a playlist.
    Restricted to YouTube ONLY. Extracts ONLY Audio.
    """
    url_lower = url.lower()
    if not any(d in url_lower for d in ('youtube.com', 'youtu.be', 'ytsearch')):
        return {'type': 'error', 'message': 'Only YouTube URLs are supported. Please provide a valid YouTube link or search query.'}

    is_search = url.startswith('ytsearch')

    # ── Build opts with given yt extractor args ───────────────────────────────
    def _make_opts(extra_yt_args: dict | None = None) -> tuple[dict, str | None]:
        """Returns (opts_dict, temp_cookie_path_or_None)."""
        yt_args = _get_youtube_args()
        if extra_yt_args:
            yt_args.update(extra_yt_args)

        print(f"[ENGINE YT] player_client={yt_args.get('player_client', 'default')}, "
              f"po_token={'YES' if 'po_token' in yt_args else 'NO'}")

        extractor_args = {
            'youtube': yt_args,
            'youtubepot-bgutilhttp': {
                'base_url': os.environ.get('BGU_BASE_URL', 'http://localhost:4416')
            },
        }

        o = {
            **_COMMON_OPTS,
            'logger': _SilentLogger(),
            'extractor_args': extractor_args,
        }

        # ── Cookies ──────────────────────────────────────────────────────────
        c_path = None
        if os.path.exists("cookies.txt"):
            o['cookiefile'] = "cookies.txt"
        else:
            env_cookies = os.environ.get("YT_COOKIES")
            if env_cookies:
                try:
                    import base64, tempfile
                    try:
                        decoded = base64.b64decode(env_cookies.strip(), validate=True).decode('utf-8')
                        cookie_content = decoded if ("Netscape" in decoded or "# HTTP Cookie File" in decoded) else env_cookies
                    except Exception:
                        cookie_content = env_cookies
                    tmp = tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.txt', encoding='utf-8')
                    tmp.write(cookie_content)
                    tmp.close()
                    c_path = tmp.name
                    o['cookiefile'] = c_path
                except Exception as e:
                    print(f"[ENGINE COOKIE ERROR] {e}")

        if not is_search:
            o['extract_flat'] = 'in_playlist'

        return o, c_path

    # ── Parse yt-dlp info dict → result dict ─────────────────────────────────
    def _parse_info(info: dict) -> dict:
        if 'entries' in info:
            entries = list(info['entries'])
            if is_search and entries:
                return _build_audio_result(entries[0])
            else:
                videos = [
                    {'title': e.get('title'), 'url': e.get('url')}
                    for e in entries if e.get('url')
                ]
                return {
                    'type':   'playlist',
                    'title':  info.get('title'),
                    'count':  len(videos),
                    'videos': videos,
                }
        else:
            return _build_audio_result(info)

    # ════════════════════════════════════════════════════════════════════════
    # RETRY LOOP FOR IP BLOCK / CAPTCHA (Max 2 attempts)
    # ════════════════════════════════════════════════════════════════════════
    max_retries = 2
    for attempt in range(max_retries):
        opts, cookie_path = _make_opts()
        try:
            info   = _run_extract(url, opts, cookie_path)
            result = _parse_info(info)

            # Check if YouTube returned empty formats (IP blocked on datacenter)
            is_youtube    = any(d in url.lower() for d in ('youtube.com', 'youtu.be', 'ytsearch'))
            formats_empty = is_youtube and result.get('type') == 'video' and not result.get('formats')

            if not formats_empty:
                return result  # ✅ Primary succeeded with formats
            
            # If formats_empty, maybe try fallback chain BEFORE doing Playwright (optional), 
            # but usually formats_empty means datacenter IP blocked, so refreshing cookies is better.
            print(f"[ENGINE] Attempt {attempt+1}: 0 formats returned (IP Block likely).")
            if attempt < max_retries - 1:
                print("[ENGINE] Refreshing cookies via Playwright...")
                try:
                    subprocess.run(["python", "fetch_cookies.py"], check=True)
                except Exception as e:
                    print(f"[ENGINE COOKIE FETCH ERROR] {e}")
                continue # Retry primary attempt
                
        except Exception as exc:
            error_msg = str(exc)
            print(f"[ENGINE] Attempt {attempt+1} failed for {url!r}: {error_msg}")
            # If YouTube asks to sign in or detects bot, refresh cookies and retry
            if attempt < max_retries - 1 and any(key in error_msg.lower() for key in ('sign in', 'bot', '403', 'verify')):
                print("[ENGINE] Refreshing cookies via Playwright...")
                try:
                    subprocess.run(["python", "fetch_cookies.py"], check=True)
                except Exception as e:
                    print(f"[ENGINE COOKIE FETCH ERROR] {e}")
                continue
            
            # If we reach here, it's the last attempt or an unrecoverable error
            if attempt == max_retries - 1:
                return {'type': 'error', 'message': error_msg}

        # ════════════════════════════════════════════════════════════════════
        # FALLBACK CHAIN — tries multiple client strategies when primary fails
        # Only runs when primary (with Playwright retries) still returns 0 formats.
        # ════════════════════════════════════════════════════════════════════
        print("[ENGINE FALLBACK] Primary returned 0 formats after all retries — trying fallback client chain")

        FALLBACK_STRATEGIES = [
            {'player_client': ['tv_embedded', 'tv']},
            {'player_client': ['android', 'mweb', 'ios']},
            {'player_client': ['android_vr', 'web_creator']},
        ]

        for i, strategy in enumerate(FALLBACK_STRATEGIES, 1):
            print(f"[ENGINE FALLBACK] Trying strategy {i}/{len(FALLBACK_STRATEGIES)}: {strategy['player_client']}")
            try:
                fb_opts, fb_cookie_path = _make_opts(strategy)
                fb_info   = _run_extract(url, fb_opts, fb_cookie_path)
                fb_result = _parse_info(fb_info)
                if fb_result.get('formats'):
                    print(f"[ENGINE FALLBACK] Strategy {i} got {len(fb_result['formats'])} formats ✅")
                    result['formats']    = fb_result['formats']
                    result['best_video'] = fb_result.get('best_video') or result.get('best_video')
                    result['best_audio'] = fb_result.get('best_audio') or result.get('best_audio')
                    result['_fallback']  = True
                    return result
            except Exception as fb_exc:
                print(f"[ENGINE FALLBACK] Strategy {i} error: {fb_exc}")

        print("[ENGINE FALLBACK] All fallback strategies exhausted ❌")
        return result
