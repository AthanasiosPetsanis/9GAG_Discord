import os
import requests
from flask import Flask, send_file, Response, redirect, request, abort
from collections import OrderedDict
from urllib.parse import urlparse
import subprocess

app = Flask(__name__)

# Config
VIDEO_CACHE_DIR = "/data/cache"
os.makedirs(VIDEO_CACHE_DIR, exist_ok=True)
MAX_CACHE_SIZE = 100

cache_order = OrderedDict()


def convert_to_webm(mp4_path, webm_path):
    if os.path.exists(webm_path):
        return  # already converted

    try:
        subprocess.run([
            "ffmpeg", "-i", mp4_path,
            "-c:v", "libvpx-vp9",
            "-b:v", "1M",
            "-c:a", "libopus",
            "-y",
            webm_path
        ], check=True)
        print(f"Converted to webm: {webm_path}")
    except subprocess.CalledProcessError as e:
        print(f"ffmpeg conversion failed: {e}")


def maintain_cache_limit():
    while len(cache_order) > MAX_CACHE_SIZE:
        oldest_file = next(iter(cache_order))
        try:
            os.remove(os.path.join(VIDEO_CACHE_DIR, oldest_file))
        except FileNotFoundError:
            pass
        cache_order.pop(oldest_file)


@app.route('/video/<video_id>')
def stream_video(video_id):
    webm_path = os.path.join(VIDEO_CACHE_DIR, f"{video_id}.webm")
    mp4_path = os.path.join(VIDEO_CACHE_DIR, f"{video_id}.mp4")

    if os.path.exists(webm_path):
        file_path = webm_path
        content_type = "video/webm"
    elif os.path.exists(mp4_path):
        file_path = mp4_path
        content_type = "video/mp4"
    else:
        return "Video not cached yet. Submit a 9GAG link via the homepage.", 404

    try:
        def generate():
            with open(file_path, "rb") as f:
                while chunk := f.read(8192):
                    yield chunk

        file_size = os.path.getsize(file_path)

        headers = {
            "Content-Type": content_type,
            "Content-Length": str(file_size),
            "Accept-Ranges": "bytes",
            "Content-Disposition": "inline"
        }

        cache_order[os.path.basename(file_path)] = True
        maintain_cache_limit()

        return Response(generate(), headers=headers, status=200)
    except Exception as e:
        return f"Error streaming video: {str(e)}", 500


@app.route('/photo/<path:filename>')
def proxy_from_clean_url(filename):
    video_id = filename.replace('.mp4', '').replace('.webm', '')
    return redirect(f'/video/{video_id}')


@app.route('/<video_id>')
def shortcut(video_id):
    return redirect(f'/video/{video_id}')


@app.route('/')
def home():
    return '''
    <form action="/convert" method="get">
        9GAG URL: <input type="text" name="url">
        <input type="submit" value="Convert">
    </form>
    '''


@app.route('/convert')
def convert():
    url = request.args.get('url', '')

    if not url.endswith('.mp4'):
        return "Invalid 9GAG .mp4 URL"

    video_id = url.split('/')[-1].replace('.mp4', '')
    filename = f"{video_id}.mp4"
    filepath = os.path.join(VIDEO_CACHE_DIR, filename)
    webm_filename = f"{video_id}.webm"
    webm_path = os.path.join(VIDEO_CACHE_DIR, webm_filename)

    if not os.path.exists(filepath):
        try:
            r = requests.get(url, stream=True)
            if r.status_code != 200:
                return f"Failed to download video from 9GAG: {url}", 404

            with open(filepath, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

            cache_order[filename] = True
            maintain_cache_limit()
        except Exception as e:
            return f"Error downloading video: {str(e)}", 500

    # Convert to webm
    convert_to_webm(filepath, webm_path)

    proxy_url = request.host_url + f"video/{video_id}.webm"
    return f"Direct proxy link: <a href='{proxy_url}'>{proxy_url}</a><br><br>Copy this into Discord."


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
