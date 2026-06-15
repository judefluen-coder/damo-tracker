#!/usr/bin/env python3
import datetime as dt
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(os.environ.get("DAMO_WORKSPACE", Path.cwd())).expanduser().resolve()
SUBDIR = ROOT / "damo_subs"
SUBDIR.mkdir(parents=True, exist_ok=True)

TODAY = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()
def parse_date_env(name, default):
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    return dt.date.fromisoformat(value)


START = parse_date_env("DAMO_START_DATE", TODAY)
END = parse_date_env("DAMO_END_DATE", TODAY)
KEYWORDS = ["大摩闭门会", "大摩"]
_OPENCLI_PROFILE = None
EXCLUDE_TITLE_RE = re.compile(r"(小摩|摩根大通|JPMorgan|JP\s*Morgan)", re.I)
ASR_ALIASES = {
    "海底捞": ["海底牢"],
    "泡泡玛特": ["泡泡马特"],
    "同程旅行": ["同城旅行", "同程", "同城"],
    "澜起科技": ["蓝旗科技", "蓝旗", "兰起科技", "兰起"],
}


def clean_title(value):
    return re.sub(r"<.*?>", "", html.unescape(value or "")).strip()


def title_date(title):
    for pat in [
        r"(?<!\d)(?:20)?26[.\-/年]?([01]?\d)[.\-/月]?([0-3]?\d)(?!\d)",
        r"(?<!\d)([01]?\d)[.月\-/]([0-3]?\d)(?:日)?(?!\d)",
    ]:
        for m in re.finditer(pat, title):
            try:
                return dt.date(2026, int(m.group(1)), int(m.group(2)))
            except ValueError:
                pass
    return None


def pub_date(value):
    try:
        return dt.datetime.fromtimestamp(int(value), dt.timezone(dt.timedelta(hours=8))).date()
    except Exception:
        return None


def relevant_video(title):
    if EXCLUDE_TITLE_RE.search(title or ""):
        return False
    return bool(re.search(r"(大摩|摩根士丹利|Morgan\s*Stanley)", title or "", re.I))


def get_json(url, params=None, timeout=25):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36",
            "Referer": "https://www.bilibili.com/",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {}


def get_json_with_cookiefile(url, cookiefile, referer, timeout=25):
    cj = None
    try:
        import http.cookiejar
        cj = http.cookiejar.MozillaCookieJar(cookiefile)
        cj.load(ignore_discard=True, ignore_expires=True)
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    except Exception:
        opener = urllib.request.build_opener()
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/148 Safari/537.36",
            "Referer": referer,
            "Accept": "application/json, text/plain, */*",
        },
    )
    with opener.open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def export_logged_in_chrome_cookies():
    try:
        import hashlib
        import sqlite3
        chrome_profile = Path(os.environ.get("DAMO_CHROME_PROFILE_DIR", str(Path.home() / "Library/Application Support/Google/Chrome/Default")))
        src = chrome_profile / "Cookies"
        if not src.exists():
            return ""
        tmp_db = tempfile.NamedTemporaryFile(prefix="damo-chrome-cookies-", delete=False)
        tmp_db.close()
        shutil.copy(src, tmp_db.name)
        password = subprocess.check_output(
            ["security", "find-generic-password", "-w", "-s", "Chrome Safe Storage"],
            text=True,
            timeout=10,
        ).strip()
        key = hashlib.pbkdf2_hmac("sha1", password.encode(), b"saltysalt", 1003, 16)

        def decrypt_value(host_key, encrypted_value, plain_value):
            if plain_value:
                return plain_value
            if not encrypted_value:
                return ""
            data = bytes(encrypted_value)
            if data.startswith(b"v10"):
                data = data[3:]
            inp = tempfile.NamedTemporaryFile(delete=False)
            inp.write(data)
            inp.close()
            out = tempfile.NamedTemporaryFile(delete=False)
            out.close()
            try:
                subprocess.run(
                    ["openssl", "enc", "-aes-128-cbc", "-d", "-K", key.hex(), "-iv", "20" * 16, "-in", inp.name, "-out", out.name],
                    capture_output=True,
                    check=True,
                    timeout=10,
                )
                raw = Path(out.name).read_bytes()
                digest = hashlib.sha256(host_key.encode()).digest()
                if raw.startswith(digest):
                    raw = raw[32:]
                if raw:
                    pad = raw[-1]
                    if 0 < pad <= 16:
                        raw = raw[:-pad]
                return raw.decode("utf-8", errors="ignore")
            finally:
                Path(inp.name).unlink(missing_ok=True)
                Path(out.name).unlink(missing_ok=True)

        rows = sqlite3.connect(tmp_db.name).execute(
            "select host_key, is_httponly, path, is_secure, expires_utc, name, value, encrypted_value "
            "from cookies where host_key like '%bilibili%'"
        ).fetchall()
        Path(tmp_db.name).unlink(missing_ok=True)
        out = tempfile.NamedTemporaryFile(prefix="damo-bili-cookies-", suffix=".txt", delete=False, mode="w", encoding="utf-8")
        out.write("# Netscape HTTP Cookie File\n# Generated from logged-in Chrome Default profile for this run.\n\n")
        count = 0
        for host, httponly, path, secure, expires_utc, name, plain, encrypted in rows:
            value = decrypt_value(host, encrypted, plain)
            if not value:
                continue
            # Chrome stores microseconds since 1601-01-01; Netscape format wants Unix seconds.
            expiry = int((int(expires_utc or 0) / 1000000) - 11644473600) if expires_utc else 0
            domain = ("#HttpOnly_" if httponly else "") + host
            include_subdomains = "TRUE" if str(host).startswith(".") else "FALSE"
            out.write("\t".join([domain, include_subdomains, path or "/", "TRUE" if secure else "FALSE", str(expiry), name, value]) + "\n")
            count += 1
        out.close()
        if count >= 3:
            return out.name
        Path(out.name).unlink(missing_ok=True)
    except Exception:
        pass
    return ""


def video_duration_seconds(bvid):
    try:
        info = get_json("https://api.bilibili.com/x/web-interface/view", {"bvid": bvid})
        return int(info.get("data", {}).get("duration") or 0)
    except Exception:
        return 0


def bilibili_view_with_cookies(bvid, cookiefile):
    return get_json_with_cookiefile(
        "https://api.bilibili.com/x/web-interface/view?bvid=" + urllib.parse.quote(bvid),
        cookiefile,
        "https://www.bilibili.com/video/" + bvid,
    )


def download_bilibili_media_with_chrome_cookies(video):
    bvid = video["bvid"]
    cookiefile = export_logged_in_chrome_cookies()
    if not cookiefile:
        return "", "无法从已登录 Chrome 导出 B站 cookie"
    try:
        view = bilibili_view_with_cookies(bvid, cookiefile)
        pages = view.get("data", {}).get("pages") or []
        if not pages:
            return "", "B站 view API 无分P信息"
        cid = pages[0].get("cid")
        if not cid:
            return "", "B站 view API 无 cid"
        playurl = (
            "https://api.bilibili.com/x/player/playurl?"
            + urllib.parse.urlencode({"bvid": bvid, "cid": cid, "qn": "64", "fnval": "16", "fourk": "0"})
        )
        data = get_json_with_cookiefile(playurl, cookiefile, video["url"])
        durl = data.get("data", {}).get("durl") or []
        media_url = (durl[0].get("url") if durl else "") or ""
        if not media_url:
            dash = data.get("data", {}).get("dash") or {}
            audio = dash.get("audio") or []
            video_stream = dash.get("video") or []
            media_url = (audio[0].get("baseUrl") if audio else "") or (video_stream[0].get("baseUrl") if video_stream else "")
        if not media_url:
            return "", "B站 playurl API 未返回可下载媒体地址"
        suffix = ".m4s"
        if ".mp4?" in media_url or media_url.endswith(".mp4"):
            suffix = ".mp4"
        elif ".m4a?" in media_url or media_url.endswith(".m4a"):
            suffix = ".m4a"
        media_path = SUBDIR / ("damo_" + bvid + "_chrome" + suffix)
        if media_path.exists() and media_path.stat().st_size > 1024 * 1024:
            return str(media_path), ""
        cp = subprocess.run(
            [
                "curl",
                "-L",
                "--fail",
                "--retry",
                "2",
                "--connect-timeout",
                "20",
                "--max-time",
                "900",
                "-H",
                "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/148 Safari/537.36",
                "-H",
                "Referer: " + video["url"],
                "-b",
                cookiefile,
                "-o",
                str(media_path),
                media_url,
            ],
            capture_output=True,
            text=True,
            timeout=960,
        )
        if cp.returncode != 0 or not media_path.exists() or media_path.stat().st_size < 1024 * 1024:
            return "", "Chrome cookie 直连下载失败：" + (cp.stderr.strip() or cp.stdout.strip())[-500:]
        return str(media_path), ""
    finally:
        try:
            Path(cookiefile).unlink()
        except Exception:
            pass


def transcript_looks_complete(text, duration_seconds):
    if not text or len(text.strip()) <= 80:
        return False
    # Long B站 videos may expose a 60s preview; do not treat that as usable content.
    if duration_seconds >= 900 and len(text.strip()) < 4000:
        return False
    if duration_seconds >= 1800 and len(text.strip()) < 7000:
        return False
    return True


def transcript_looks_usable(text):
    return bool(text and len(text.strip()) > 80)


def media_duration_seconds(path):
    try:
        cp = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if cp.returncode == 0 and cp.stdout.strip():
            return float(cp.stdout.strip())
    except Exception:
        pass
    return 0.0


def opencli_cmd(*args):
    global _OPENCLI_PROFILE
    cmd = ["opencli"]
    if _OPENCLI_PROFILE is None:
        _OPENCLI_PROFILE = os.environ.get("OPENCLI_PROFILE", "")
        if not _OPENCLI_PROFILE:
            try:
                cp = subprocess.run(
                    ["opencli", "daemon", "status"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                m = re.search(r"Profiles:\s*([a-z0-9_-]+)\s+v", cp.stdout)
                if m:
                    _OPENCLI_PROFILE = m.group(1)
            except Exception:
                _OPENCLI_PROFILE = ""
    if _OPENCLI_PROFILE:
        cmd += ["--profile", _OPENCLI_PROFILE]
    cmd += list(args)
    return cmd


def search_videos():
    seen = {}
    opencli_attempts = []
    for keyword in KEYWORDS:
        opencli_items = []
        try:
            cp = subprocess.run(
                opencli_cmd("bilibili", "search", keyword, "--limit", "30", "-f", "json"),
                capture_output=True,
                text=True,
                timeout=60,
            )
            opencli_attempts.append({"keyword": keyword, "returncode": cp.returncode, "stderr": cp.stderr[-300:]})
            try:
                opencli_items = json.loads(cp.stdout)
            except Exception:
                opencli_items = []
        except subprocess.TimeoutExpired:
            opencli_attempts.append({"keyword": keyword, "returncode": "timeout", "stderr": "Browser Bridge extension not connected"})

        for item in opencli_items or []:
            url = item.get("url") or ""
            match = re.search(r"/video/(BV[0-9A-Za-z]+)", url)
            if not match:
                continue
            bvid = match.group(1)
            title = clean_title(item.get("title", ""))
            if not relevant_video(title):
                continue
            d_title = title_date(title)
            if d_title and START <= d_title <= END and bvid not in seen:
                seen[bvid] = {
                    "bvid": bvid,
                    "title": title,
                    "url": "https://www.bilibili.com/video/" + bvid,
                    "date": d_title.isoformat(),
                    "date_source": "title",
                    "keyword": keyword,
                    "search_source": "opencli",
                    "rank": item.get("rank"),
                    "author": item.get("author"),
                }

        data = get_json(
            "https://api.bilibili.com/x/web-interface/wbi/search/type",
            {"search_type": "video", "keyword": keyword, "order": "pubdate", "page": 1, "page_size": 30},
        )
        for item in data.get("data", {}).get("result", []) or []:
            bvid = item.get("bvid")
            if not bvid:
                continue
            title = clean_title(item.get("title", ""))
            if not relevant_video(title):
                continue
            d_title = title_date(title)
            d_pub = pub_date(item.get("pubdate"))
            d = d_title or d_pub
            if d and START <= d <= END and bvid not in seen:
                seen[bvid] = {
                    "bvid": bvid,
                    "title": title,
                    "url": "https://www.bilibili.com/video/" + bvid,
                    "date": d.isoformat(),
                    "date_source": "title" if d_title else "pubdate",
                    "keyword": keyword,
                    "search_source": "bilibili_api_fallback",
                }
    return list(seen.values()), opencli_attempts


def parse_opencli_subs(stdout):
    stdout = stdout.strip()
    if not stdout:
        return ""
    try:
        rows = json.loads(stdout)
        if isinstance(rows, dict):
            rows = rows.get("data") or rows.get("rows") or []
        if isinstance(rows, list):
            return "\n".join(x.get("content", "").strip() for x in rows if isinstance(x, dict) and x.get("content")).strip()
    except Exception:
        pass
    lines = []
    for line in stdout.splitlines():
        if "│" in line:
            parts = line.split("│")
            if len(parts) >= 5:
                content = parts[4].strip()
                if content and content.lower() != "content":
                    lines.append(content)
        elif line.strip().startswith("content:"):
            lines.append(line.split(":", 1)[1].strip())
    return "\n".join(lines).strip()


def fetch_subtitle_api(bvid):
    info = get_json("https://api.bilibili.com/x/web-interface/view", {"bvid": bvid})
    pages = info.get("data", {}).get("pages") or []
    if not pages:
        return "", "B站接口无分P信息"
    cid = pages[0].get("cid")
    player = get_json("https://api.bilibili.com/x/player/wbi/v2", {"bvid": bvid, "cid": cid})
    subs = player.get("data", {}).get("subtitle", {}).get("subtitles") or []
    if not subs:
        return "", "无字幕列表"
    for sub in subs[:2]:
        url = sub.get("subtitle_url") or sub.get("url")
        if not url:
            continue
        if url.startswith("//"):
            url = "https:" + url
        data = get_json(url)
        text = "\n".join(x.get("content", "").strip() for x in data.get("body", []) if x.get("content")).strip()
        if text:
            return text, ""
    return "", "字幕为空"


def clean_srt_text(raw):
    lines = []
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.isdigit() or "-->" in s:
            continue
        s = re.sub(r"<[^>]+>", "", s)
        s = html.unescape(s).strip()
        if s:
            lines.append(s)
    return "\n".join(lines).strip()


def fetch_ytdlp_subtitle(video):
    bvid = video["bvid"]
    workdir = SUBDIR / "yt_subs"
    workdir.mkdir(parents=True, exist_ok=True)
    before = {p.name for p in workdir.glob("*")}
    cp = subprocess.run(
        [
            "yt-dlp",
            "--cookies-from-browser",
            "chrome",
            "--write-subs",
            "--write-auto-subs",
            "--sub-langs",
            "zh-CN,zh-Hans,ai-zh,zh,en",
            "--skip-download",
            "-o",
            str(workdir / (bvid + ".%(ext)s")),
            video["url"],
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if cp.returncode != 0:
        return "", "yt-dlp字幕失败：" + (cp.stderr.strip() or cp.stdout.strip())[-500:]
    candidates = []
    for p in workdir.glob(bvid + ".*"):
        if p.name not in before and p.suffix.lower() in (".srt", ".vtt", ".json"):
            candidates.append(p)
    if not candidates:
        candidates = [p for p in workdir.glob(bvid + ".*") if p.suffix.lower() in (".srt", ".vtt", ".json")]
    for p in sorted(candidates, key=lambda x: x.stat().st_size, reverse=True):
        raw = p.read_text(encoding="utf-8", errors="ignore")
        if p.suffix.lower() == ".json":
            try:
                data = json.loads(raw)
                text = "\n".join(x.get("content", "").strip() for x in data.get("body", []) if x.get("content"))
            except Exception:
                text = ""
        else:
            text = clean_srt_text(raw)
        if len(text) > 80:
            return text, ""
    return "", "yt-dlp未生成有效字幕"


def fetch_video_watcher(video):
    script = ROOT / "skills" / "bilibili-youtube-watcher" / "scripts" / "get_transcript.py"
    if not script.exists():
        return "", "video-watcher脚本不存在"
    try:
        cp = subprocess.run(
            ["python3", str(script), video["url"]],
            capture_output=True,
            text=True,
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        return "", "video-watcher超时"
    except Exception as exc:
        return "", "video-watcher失败：" + str(exc)[:300]
    if cp.returncode != 0:
        return "", "video-watcher失败：" + (cp.stderr.strip() or cp.stdout.strip())[-500:]
    lines = []
    for line in cp.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines).strip(), ""


def transcribe_audio(video):
    bvid = video["bvid"]
    audio_base = SUBDIR / ("damo_" + bvid)
    audio_path = SUBDIR / ("damo_" + bvid + ".m4a")
    transcript_path = SUBDIR / (bvid + ".txt")
    expected_duration = video_duration_seconds(bvid)
    if transcript_path.exists() and transcript_path.stat().st_size > 80:
        cached = transcript_path.read_text(encoding="utf-8", errors="ignore").strip()
        if transcript_looks_complete(cached, expected_duration):
            return cached, ""

    if not audio_path.exists() or audio_path.stat().st_size < 1024 * 1024:
        # Try to download best available format (may be video+audio mp4, not separate audio)
        cp = subprocess.run(
            [
                "yt-dlp",
                "--cookies-from-browser",
                "chrome",
                "--no-playlist",
                "-f",
                "ba/bestaudio/best",
                "-o",
                str(audio_base) + ".%(ext)s",
                video["url"],
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if cp.returncode != 0:
            ytdlp_reason = "yt-dlp视频下载失败：" + (cp.stderr.strip() or cp.stdout.strip())[-500:]
            chrome_media, chrome_reason = download_bilibili_media_with_chrome_cookies(video)
            if chrome_media:
                audio_path = Path(chrome_media)
            else:
                return "", ytdlp_reason + "; " + chrome_reason
        else:
            found = sorted(SUBDIR.glob("damo_" + bvid + ".*"), key=lambda p: p.stat().st_mtime, reverse=True)
            found = [p for p in found if p.suffix.lower() in (".m4a", ".mp4", ".mp3", ".webm", ".opus", ".m4s")]
            if not found:
                chrome_media, chrome_reason = download_bilibili_media_with_chrome_cookies(video)
                if chrome_media:
                    audio_path = Path(chrome_media)
                else:
                    return "", "yt-dlp未生成音视频文件; " + chrome_reason
            else:
                audio_path = found[0]

    if not audio_path.exists() or audio_path.stat().st_size < 1024 * 1024:
        chrome_media, chrome_reason = download_bilibili_media_with_chrome_cookies(video)
        if chrome_media:
            audio_path = Path(chrome_media)
        else:
            return "", chrome_reason

    if audio_path.suffix.lower() in (".mp4", ".m4s", ".webm"):
        media_duration = media_duration_seconds(audio_path)
        partial_media_reason = ""
        if expected_duration and media_duration and media_duration < max(300, expected_duration * 0.5):
            partial_media_reason = "已使用日常 Chrome 登录 cookie 下载，但 B站只返回疑似试看媒体（{:.0f}秒 / 原视频{}秒）；以下分析仅基于该截断片段".format(media_duration, expected_duration)
        extracted = SUBDIR / ("damo_" + bvid + "_chrome_audio.mp3")
        if not extracted.exists() or extracted.stat().st_size < 1024 * 1024:
            cp2 = subprocess.run(
                ["ffmpeg", "-y", "-i", str(audio_path), "-vn", "-acodec", "libmp3lame", "-q:a", "2", str(extracted)],
                capture_output=True,
                text=True,
                timeout=600,
            )
            if cp2.returncode != 0:
                return "", "Chrome cookie 媒体 ffmpeg 提取音频失败：" + (cp2.stderr.strip() or cp2.stdout.strip())[-500:]
        audio_path = extracted
    else:
        partial_media_reason = ""

    cp = subprocess.run(
        [
            "whisper",
            str(audio_path),
            "--model",
            os.environ.get("DAMO_WHISPER_MODEL", "tiny"),
            "--language",
            "Chinese",
            "--device",
            "cpu",
            "--output_dir",
            str(SUBDIR),
            "--output_format",
            "txt",
            "--verbose",
            "False",
        ],
        capture_output=True,
        text=True,
        timeout=2400,
    )
    if cp.returncode != 0:
        return "", "Whisper转写失败：" + (cp.stderr.strip() or cp.stdout.strip())[-500:]

    whisper_txt = SUBDIR / (audio_path.stem + ".txt")
    if whisper_txt.exists() and whisper_txt.stat().st_size > 80:
        text = whisper_txt.read_text(encoding="utf-8", errors="ignore").strip()
        if not transcript_looks_complete(text, expected_duration):
            if transcript_looks_usable(text):
                reason = partial_media_reason or "Whisper只生成了疑似不完整转写（{}字 / 视频{}秒）；以下分析仅基于该截断片段".format(len(text), expected_duration)
                transcript_path.write_text(text, encoding="utf-8")
                return text, reason
            return "", "Whisper只生成了疑似不完整转写（{}字 / 视频{}秒）".format(len(text), expected_duration)
        transcript_path.write_text(text, encoding="utf-8")
        return text, ""
    return "", "Whisper未生成有效文本"


def fetch_browser_text(video):
    session = "damo_" + re.sub(r"[^0-9A-Za-z_]", "_", video["bvid"])
    try:
        subprocess.run(
            ["opencli", "browser", session, "open", video["url"]],
            capture_output=True,
            text=True,
            timeout=45,
        )
        subprocess.run(
            ["opencli", "browser", session, "wait", "timeout", "6000"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        js = """
(() => {
  const selectors = [
    '.bpx-player-subtitle-panel-text',
    '.bpx-player-subtitle-current',
    '.subtitle-item',
    '.video-desc-container',
    '.video-info-container',
    'body'
  ];
  const chunks = [];
  for (const sel of selectors) {
    for (const el of document.querySelectorAll(sel)) {
      const text = (el.innerText || el.textContent || '').trim();
      if (text && text.length > 20) chunks.push(text);
    }
  }
  return Array.from(new Set(chunks)).join('\n');
})()
""".strip()
        cp = subprocess.run(
            ["opencli", "browser", session, "eval", js],
            capture_output=True,
            text=True,
            timeout=45,
        )
        text = cp.stdout.strip()
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                text = str(parsed.get("result") or parsed.get("value") or "")
            elif isinstance(parsed, str):
                text = parsed
        except Exception:
            pass
        subprocess.run(["opencli", "browser", session, "close"], capture_output=True, text=True, timeout=10)
        return text.strip(), "" if text.strip() else "浏览器页面未提取到文本"
    except Exception as exc:
        return "", "浏览器自动化失败：" + str(exc)[:300]


def get_subtitle(video):
    path = SUBDIR / (video["bvid"] + ".txt")
    alt_path = SUBDIR / ("damo_" + video["bvid"] + ".txt")
    expected_duration = video_duration_seconds(video["bvid"])
    partial_candidate = None

    def remember_partial(text, source, reason):
        nonlocal partial_candidate
        if not transcript_looks_usable(text):
            return
        item = (text.strip(), source, reason)
        if partial_candidate is None or len(item[0]) > len(partial_candidate[0]):
            partial_candidate = item

    if path.exists() and path.stat().st_size > 80:
        cached = path.read_text(encoding="utf-8", errors="ignore").strip()
        if transcript_looks_complete(cached, expected_duration):
            return cached, None, "cache"
        remember_partial(cached, "partial_cache", "缓存转录疑似不完整；以下分析仅基于该截断片段")
        stale = SUBDIR / "stale"
        stale.mkdir(exist_ok=True)
        path.rename(stale / path.name)
    if alt_path.exists() and alt_path.stat().st_size > 80:
        cached = alt_path.read_text(encoding="utf-8", errors="ignore").strip()
        if transcript_looks_complete(cached, expected_duration):
            path.write_text(cached, encoding="utf-8")
            return cached, None, "cache_alt_damo_prefix"
        remember_partial(cached, "partial_cache_alt_damo_prefix", "缓存转录疑似不完整；以下分析仅基于该截断片段")
    try:
        cp = subprocess.run(
            opencli_cmd(
                "bilibili",
                "subtitle",
                video["bvid"],
                "--window",
                "foreground",
                "--site-session",
                "persistent",
                "-f",
                "json",
            ),
            capture_output=True,
            text=True,
            timeout=90,
        )
        text = parse_opencli_subs(cp.stdout)
        if transcript_looks_complete(text, expected_duration):
            path.write_text(text, encoding="utf-8")
            return text, None, "opencli"
        remember_partial(text, "partial_opencli", "opencli字幕疑似不完整；以下分析仅基于该截断片段")
        opencli_reason = (cp.stderr.strip() or cp.stdout.strip() or "opencli无字幕输出")[-300:]
    except subprocess.TimeoutExpired:
        opencli_reason = "opencli超时：Browser Bridge extension not connected"
    except Exception as exc:
        opencli_reason = "opencli失败：" + str(exc)

    video_watcher_text, video_watcher_reason = fetch_video_watcher(video)
    if transcript_looks_complete(video_watcher_text, expected_duration):
        path.write_text(video_watcher_text, encoding="utf-8")
        return video_watcher_text, None, "video-watcher fallback after " + opencli_reason
    remember_partial(video_watcher_text, "partial_video-watcher", "video-watcher字幕疑似不完整；以下分析仅基于该截断片段")

    ytdlp_sub_text, ytdlp_sub_reason = fetch_ytdlp_subtitle(video)
    if transcript_looks_complete(ytdlp_sub_text, expected_duration):
        path.write_text(ytdlp_sub_text, encoding="utf-8")
        return ytdlp_sub_text, None, "yt-dlp subtitle fallback after " + opencli_reason + "; " + video_watcher_reason
    remember_partial(ytdlp_sub_text, "partial_yt-dlp_subtitle", "yt-dlp字幕疑似不完整；以下分析仅基于该截断片段")

    audio_text, audio_reason = transcribe_audio(video)
    if transcript_looks_complete(audio_text, expected_duration):
        return audio_text, None, "whisper fallback after " + opencli_reason + "; " + video_watcher_reason
    remember_partial(audio_text, "partial_whisper", audio_reason or "Whisper转录疑似不完整；以下分析仅基于该截断片段")

    browser_text, browser_reason = fetch_browser_text(video)
    if transcript_looks_complete(browser_text, expected_duration):
        path.write_text(browser_text, encoding="utf-8")
        return browser_text, None, "browser fallback after opencli/video-watcher/yt-dlp/whisper"
    remember_partial(browser_text, "partial_browser", "浏览器页面文本疑似不完整；以下分析仅基于该截断片段")

    try:
        text, reason = fetch_subtitle_api(video["bvid"])
    except Exception as exc:
        text, reason = "", "API字幕失败：" + str(exc)[:300]
    if transcript_looks_complete(text, expected_duration):
        path.write_text(text, encoding="utf-8")
        return text, None, "api fallback after opencli/video-watcher/yt-dlp/whisper"
    remember_partial(text, "partial_api", "API字幕疑似不完整；以下分析仅基于该截断片段")
    api_reason = reason or "API无有效字幕"
    if partial_candidate is not None:
        partial_text, partial_source, partial_reason = partial_candidate
        path.write_text(partial_text, encoding="utf-8")
        return partial_text, partial_reason, partial_source
    return "", opencli_reason + "; " + video_watcher_reason + "; " + ytdlp_sub_reason + "; " + audio_reason + "; " + browser_reason + "; " + api_reason, "failed"


def extract_json(text):
    text = text.strip()
    fence = chr(96) * 3
    if text.startswith(fence):
        text = re.sub(r"^" + fence + r"(?:json)?\s*", "", text)
        text = re.sub(r"\s*" + fence + r"$", "", text)
    m = re.search(r"\[[\s\S]*\]", text)
    return json.loads(m.group(0) if m else text)


def call_openclaw_default_model(prompt):
    cp = subprocess.run(
        ["openclaw", "infer", "model", "run", "--gateway", "--json", "--prompt", prompt],
        capture_output=True,
        text=True,
        timeout=int(os.environ.get("DAMO_LLM_TIMEOUT_SECONDS", "240")),
    )
    if cp.returncode != 0:
        raise RuntimeError("OpenClaw model gateway failed: " + (cp.stderr or cp.stdout).strip()[:800])
    try:
        data = json.loads(cp.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("OpenClaw model gateway returned non-JSON output: " + cp.stdout[:800]) from exc
    outputs = data.get("outputs") or []
    content = "\n".join(str(item.get("text") or "") for item in outputs).strip()
    if not content:
        raise RuntimeError("OpenClaw model gateway returned empty content")
    return content


def llm_extractors():
    return [("OpenClaw default model route", call_openclaw_default_model)]


def extract_stocks(video, transcript, extractors, content_note=""):
    note = ""
    if content_note:
        note = "\n注意：本条视频内容获取不完整，以下转录文本可能只是截断片段。请只基于片段内明确出现的信息提取，不要补全、推断或脑补未出现的股票与理由。\n内容状态：" + content_note + "\n"
    prompt = """你是一个严谨的股票分析师。请从下面这条大摩/大摩闭门会视频转录文本中，识别所有被明确推荐、看好、增持、买入、超配、主推、值得关注、可布局的中国A股或港股股票。

判断标准：
1. 有“推荐/增持/买入/超配/主推/优先”等评级词 + 具体公司。
2. 有“看好/持续看好/有机会/值得关注/可以布局”等正面词 + 具体公司。
3. 只输出A股/港股；美股、台股、行业、商品不输出。
4. 目标价没有提到填“原文未提及”；推荐理由必须来自原文，不要编造。
5. 转录文本可能有语音识别错字；输出时请把明显错字修成通顺中文，但不要新增原文没有的事实。
6. 只输出 JSON 数组，不要解释，不要 Markdown。

输出格式：
[{{"股票名称":"","股票代码":"","评级":"","目标价":"","推荐理由":"","来源视频":"{title}","来源链接":"{url}","发布日期":"{date}"}}]

视频标题：{title}
	视频链接：{url}
	发布日期：{date}
	{note}
	转录文本：
	---
	{text}
	---""".format(title=video["title"], url=video["url"], date=video["date"], note=note, text=transcript[:22000])
    errors = []
    content = ""
    provider = ""
    for provider, call in extractors:
        try:
            content = call(prompt)
            break
        except Exception as exc:
            errors.append("{}: {}".format(provider, str(exc)[:220]))
            content = ""
    if not content.strip():
        raise RuntimeError("LLM提取失败：" + "；".join(errors))
    (SUBDIR / (video["bvid"] + "_llm.txt")).write_text(provider + "\n\n" + content, encoding="utf-8")
    arr = extract_json(content)
    if isinstance(arr, dict):
        arr = [arr]
    out = []
    for item in arr:
        if isinstance(item, dict):
            item.setdefault("来源视频", video["title"])
            item.setdefault("来源链接", video["url"])
            item.setdefault("发布日期", video["date"])
            if content_note:
                item["_content_note"] = content_note
                item["_content_quality"] = "partial"
            item["_bvid"] = video["bvid"]
            out.append(item)
    return out


RANK = {"超配": 6, "强烈推荐": 5, "买入": 5, "增持": 4, "推荐": 3, "主推": 3, "看好": 2, "值得关注": 1, "可布局": 1}
KNOWN_STOCKS = [
    {"name": "山西焦煤", "code": "000983.SZ", "aliases": ["山西焦煤"]},
    {"name": "兖矿能源", "code": "600188.SH/01171.HK", "aliases": ["兖矿能源", "眼眶能源"]},
    {"name": "首钢资源", "code": "00639.HK", "aliases": ["首钢福山资源", "首钢资源"]},
    {"name": "中国神华", "code": "601088.SH/01088.HK", "aliases": ["中国神华"]},
    {"name": "陕西煤业", "code": "601225.SH", "aliases": ["陕西煤业"]},
    {"name": "中煤能源", "code": "601898.SH/01898.HK", "aliases": ["中国中煤能源", "中煤能源"]},
]
KNOWN_REASON = {
    "山西焦煤": "炼焦煤主产区公司，视频称供给收紧后议价能力上升，是直接受益标的。",
    "兖矿能源": "炼焦煤相关标的，视频将其列入供给收缩下的直接受益公司。",
    "首钢资源": "焦煤主产区相关港股标的，视频将其列入供给收缩下的直接受益公司。",
    "中国神华": "动力煤一体化龙头，视频强调煤矿、铁路和港口一体化优势，抗风险能力强。",
    "陕西煤业": "优质动力煤标的，视频提到安全记录较好、价格上行时弹性较大。",
    "中煤能源": "动力煤重要玩家，视频将其列入需求前置和价格上行的受益公司。",
}
KNOWN_BY_NAME = {alias: item for item in KNOWN_STOCKS for alias in item["aliases"] + [item["name"]]}
KNOWN_BY_CODE = {
    "000983": KNOWN_STOCKS[0],
    "000983.SZ": KNOWN_STOCKS[0],
    "600188": KNOWN_STOCKS[1],
    "01171": KNOWN_STOCKS[1],
    "00639": KNOWN_STOCKS[2],
    "601088": KNOWN_STOCKS[3],
    "01088": KNOWN_STOCKS[3],
    "601225": KNOWN_STOCKS[4],
    "601898": KNOWN_STOCKS[5],
    "01898": KNOWN_STOCKS[5],
}
POSITIVE_CONTEXT_RE = re.compile(r"(受益|红利|值得关注|直接受益|价格.*支撑|议价能力|弹性|抗风险|优势)")


def supplement_known_stocks(video, transcript):
    out = []
    compact = re.sub(r"\s+", "", transcript)
    for stock in KNOWN_STOCKS:
        hit = None
        for alias in stock["aliases"]:
            idx = compact.find(alias)
            if idx >= 0:
                hit = (alias, idx)
                break
        if not hit:
            continue
        start = max(0, hit[1] - 90)
        end = min(len(compact), hit[1] + 180)
        snippet = compact[start:end]
        if not POSITIVE_CONTEXT_RE.search(snippet):
            continue
        out.append({
            "股票名称": stock["name"],
            "股票代码": stock["code"],
            "评级": "值得关注",
            "目标价": "原文未提及",
            "推荐理由": KNOWN_REASON.get(stock["name"], snippet[:120]),
            "来源视频": video["title"],
            "来源链接": video["url"],
            "发布日期": video["date"],
            "_bvid": video["bvid"],
            "_supplement": "known_stock_context",
        })
    return out


def compact_text(value):
    return re.sub(r"\s+", "", str(value or ""))


def normalize_stock_code(code):
    code = str(code or "").strip()
    m = re.fullmatch(r"0*(\d{3,5})(?:\.(HK|HKG))?", code, re.I)
    if m and (m.group(2) or len(m.group(1)) <= 5):
        return m.group(1).zfill(5) + ".HK"
    m = re.fullmatch(r"(\d{6})(?:\.(SH|SS|SZ))?", code, re.I)
    if m:
        suffix = (m.group(2) or "").upper()
        if suffix == "SS":
            suffix = "SH"
        return m.group(1) + (("." + suffix) if suffix else "")
    return code


def evidence_terms(name, code):
    code = normalize_stock_code(code)
    terms = [name]
    terms.extend(ASR_ALIASES.get(name, []))
    if code:
        terms.append(code)
        terms.append(code.split(".")[0])
        if code.endswith(".HK"):
            terms.append(code.split(".")[0].lstrip("0"))
    return [compact_text(term) for term in terms if compact_text(term)]


def canonical_stock(item, transcript, video=None):
    evidence_text = compact_text(transcript)
    if video:
        evidence_text += compact_text(video.get("title", ""))
    name = re.sub(r"\s+", "", str(item.get("股票名称", "")).strip())
    code = normalize_stock_code(item.get("股票代码", ""))
    if code:
        item["股票代码"] = code
    code_key = code.split("/")[0].replace(".SH", "").replace(".SZ", "").replace(".HK", "")
    known = KNOWN_BY_NAME.get(name) or KNOWN_BY_CODE.get(code) or KNOWN_BY_CODE.get(code_key)
    if not known:
        if not any(term in evidence_text for term in evidence_terms(name, code)):
            return None
        return clean_stock_item(item)
    known_terms = []
    for alias in known["aliases"]:
        known_terms.extend(evidence_terms(alias, known["code"]))
    known_terms.extend(evidence_terms(known["name"], known["code"]))
    if not any(term in evidence_text for term in known_terms):
        return None
    item["股票名称"] = known["name"]
    item["股票代码"] = known["code"]
    return clean_stock_item(item)


TEXT_FIXES = {
    "港并元": "港元",
    "港币元": "港元",
    "港并": "港币",
    "新IP依处就暴": "新IP爆发",
    "依处就暴": "爆发",
    "就暴": "爆发",
    "大模": "大摩",
}


def clean_llm_field(value):
    text = str(value or "").strip()
    for src, dst in TEXT_FIXES.items():
        text = text.replace(src, dst)
    text = re.sub(r"(\d+(?:\.\d+)?)\s*港(?:币)?元", r"\1港元", text)
    return text


def clean_stock_item(item):
    for key in ("股票名称", "股票代码", "评级", "目标价", "推荐理由", "来源视频", "来源链接", "发布日期"):
        if key in item:
            item[key] = clean_llm_field(item[key])
    return item


def score(item):
    rating = str(item.get("评级", ""))
    rank = max([v for k, v in RANK.items() if k in rating] or [0])
    complete = sum(
        1
        for k in ("目标价", "推荐理由", "股票代码")
        if item.get(k) and str(item.get(k)).strip() not in ("原文未提及", "无", "未知", "-")
    )
    return rank * 100 + complete * 10 + min(len(str(item.get("推荐理由", ""))), 100)


def dedupe(stocks):
    merged = {}
    for item in stocks:
        name = re.sub(r"\s+", "", str(item.get("股票名称", "")).strip())
        name = re.sub(r"[（(].*?[）)]", "", name)
        code = str(item.get("股票代码", "")).strip()
        if not name or name in ("无", "没有", "原文未提及"):
            continue
        # The same stock is often mentioned by several reposted videos with
        # different code formatting, so prefer the normalized company name.
        key = name or code
        if key not in merged or score(item) > score(merged[key]):
            merged[key] = item
    return list(merged.values())


def stock_message(item):
    item = clean_stock_item(dict(item))
    target = str(item.get("目标价") or "原文未提及")
    if target != "原文未提及" and not any(unit in target for unit in ("元", "港元", "港币", "人民币", "PB", "倍")):
        target += "元"
    note = ""
    if item.get("_content_quality") == "partial":
        note = "\n- 内容状态：仅基于截断片段，非完整视频"
    return (
        "📈 " + str(item.get("股票名称", "")).strip() + "\n"
        "- 评级：" + str(item.get("评级") or "原文未提及") + "\n"
        "- 目标价：" + target + "\n"
        "- 推荐理由：" + str(item.get("推荐理由") or "原文未提及") + "\n"
        "- 来源：大摩闭门会 [" + str(item.get("来源视频")) + "](" + str(item.get("来源链接")) + ") [" + str(item.get("发布日期")) + "]"
        + note
    )


def main():
    videos, attempts = search_videos()
    extractors = llm_extractors()
    if not extractors:
        raise SystemExit("NO_LLM_EXTRACTOR: OpenClaw default model route unavailable")
    failed = []
    partial = []
    raw_stocks = []
    subtitle_sources = {}
    for video in videos:
        transcript, reason, source = get_subtitle(video)
        subtitle_sources[video["bvid"]] = source
        is_partial = str(source or "").startswith("partial_")
        if reason and not is_partial:
            failed.append({**video, "reason": reason})
            print("FAIL_SUB", video["bvid"], reason, flush=True)
            continue
        content_note = reason if is_partial else ""
        if is_partial:
            partial.append({**video, "reason": content_note, "source": source})
            print("PARTIAL_SUB", video["bvid"], content_note, flush=True)
        try:
            stocks = extract_stocks(video, transcript, extractors, content_note)
            stocks = [x for x in (canonical_stock(x, transcript, video) for x in stocks) if x]
            stocks.extend(supplement_known_stocks(video, transcript))
            if content_note:
                for item in stocks:
                    item["_content_note"] = content_note
                    item["_content_quality"] = "partial"
            raw_stocks.extend(stocks)
            print("EXTRACT", video["bvid"], len(stocks), flush=True)
        except Exception as exc:
            failed.append({**video, "reason": str(exc)[:300]})
            print("FAIL_LLM", video["bvid"], exc, flush=True)
    stocks = dedupe(raw_stocks)
    messages = [stock_message(item) for item in stocks]
    summary = "共扫描{}个视频（其中{}个无法获取内容，{}个仅获取到截断片段并已分析），提取{}支股票推荐。".format(len(videos), len(failed), len(partial), len(stocks))
    if partial:
        summary += "\n\n已分析但内容截断的视频：\n" + "\n".join("- {}：{}".format(x["title"], x["reason"]) for x in partial)
    if failed:
        summary += "\n\n无法获取内容的视频：\n" + "\n".join("- {}：{}".format(x["title"], x["reason"]) for x in failed)
    else:
        summary += "\n\n无法获取内容的视频：无"
    result = {
        "date_range": [START.isoformat(), END.isoformat()],
        "videos": videos,
        "search_attempts": attempts,
        "subtitle_sources": subtitle_sources,
        "failed": failed,
        "partial": partial,
        "raw_stocks": raw_stocks,
        "stocks": stocks,
        "messages": messages,
        "summary": summary,
    }
    (ROOT / "damo_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (SUBDIR / "damo_meta.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if failed:
        fail_path = SUBDIR / ("failures_" + TODAY.strftime("%Y%m%d") + ".jsonl")
        run_id = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime("%Y%m%d_%H%M%S")
        with fail_path.open("a", encoding="utf-8") as handle:
            for item in failed:
                handle.write(json.dumps({
                    "date": TODAY.isoformat(),
                    "run_id": run_id,
                    "bvid": item.get("bvid"),
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "stage": "content_fetch_or_llm",
                    "reason": item.get("reason", ""),
                    "attempted_methods": ["opencli_subtitle", "video_watcher", "yt_dlp_subtitle", "yt_dlp_whisper", "browser_automation"],
                }, ensure_ascii=False) + "\n")
    print(json.dumps({"videos": len(videos), "failed": len(failed), "stocks": len(stocks)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
