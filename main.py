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


@app.route('/video/<path:video_id>')
def stream_video(video_id):
    if not video_id.endswith('.mp4') and not video_id.endswith('.webm'):
        return "Invalid video format.", 400

    filename = video_id
    filepath = os.path.join(VIDEO_CACHE_DIR, filename)

    if not os.path.exists(filepath):
        return "Video not cached yet. Submit a 9GAG link via the homepage.", 404

    # Move to the end of cache order for LRU
    cache_order[filename] = True
    maintain_cache_limit()

    return send_file(filepath, mimetype='video/webm' if filename.endswith('.webm') else 'video/mp4')



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
