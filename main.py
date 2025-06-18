# Updated Flask proxy server to support intuitive 69gag.xyz URL format for Discord embedding

import os
import requests
from flask import Flask, send_file, Response, redirect, request, abort
from collections import OrderedDict
from urllib.parse import urlparse
import sys
import subprocess


app = Flask(__name__)

# Config
VIDEO_CACHE_DIR = "/data/cache"
os.makedirs(VIDEO_CACHE_DIR, exist_ok=True)
MAX_CACHE_SIZE = 100

cache_order = OrderedDict()

if not os.path.exists(VIDEO_CACHE_DIR):
    os.makedirs(VIDEO_CACHE_DIR)


def convert_to_webm(mp4_path, webm_path):
    if os.path.exists(webm_path):
        return  # already converted

    try:
        subprocess.run([
            "ffmpeg", "-i", mp4_path,
            "-c:v", "libvpx-vp9",
            "-b:v", "1M",
            "-c:a", "libopus",
            "-y",  # overwrite if exists
            webm_path
        ], check=True)
        print(f"Converted to webm: {webm_path}")
    except subprocess.CalledProcessError as e:
        print(f"ffmpeg conversion failed: {e}")

# Clean cache if too large
def maintain_cache_limit():
    while len(cache_order) > MAX_CACHE_SIZE:
        oldest_file = next(iter(cache_order))
        try:
            os.remove(os.path.join(VIDEO_CACHE_DIR, oldest_file))
        except FileNotFoundError:
            pass
        cache_order.pop(oldest_file)

# Route to stream video
@app.route('/video/<video_id>')
def stream_video(video_id):
    filename = f"{video_id}.mp4"
    filepath = os.path.join(VIDEO_CACHE_DIR, filename)

    if not os.path.exists(filepath):
        return "Video not found. Submit it via the homepage first.", 404

    try:
        def generate():
            with open(filepath, "rb") as f:
                while chunk := f.read(8192):
                    yield chunk

        file_size = os.path.getsize(filepath)

        headers = {
            "Content-Type": "video/mp4",
            "Content-Length": str(file_size),
            "Accept-Ranges": "bytes",
            "Content-Disposition": "inline"
        }

        if filename in cache_order:
            cache_order.move_to_end(filename)

        return Response(generate(), headers=headers, status=200)
    except Exception as e:
        return f"Error streaming video: {str(e)}", 500

# Intuitive route: /photo/<filename>.mp4
@app.route('/photo/<path:filename>')
def proxy_from_clean_url(filename):
    video_id = filename.replace('.mp4', '')
    return redirect(f'/video/{video_id}')

# Intuitive short route: /<video_id>
@app.route('/<video_id>')
def shortcut(video_id):
    return redirect(f'/video/{video_id}')

# Optional form input for manual conversion
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

    # If not cached, download it
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

    proxy_url = request.host_url + f"video/{video_id}"
    return f"Direct proxy link: <a href='{proxy_url}'>{proxy_url}</a><br><br>Copy this into Discord."

# Main download logic from command-line input
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

    input_url = sys.argv[1]
    parsed = urlparse(input_url)

    if not parsed.path.endswith('.mp4'):
        print("Provided URL does not point to an .mp4 file.")
        sys.exit(1)

    video_id = os.path.basename(parsed.path).replace('.mp4', '')
    filename = f"{video_id}.mp4"
    filepath = os.path.join(VIDEO_CACHE_DIR, filename)

    if os.path.exists(filepath):
        print(f"Video already cached: http://localhost:5000/video/{video_id}")
    else:
        try:
            r = requests.get(input_url, stream=True)
            if r.status_code != 200:
                print(f"Failed to download video. Status code: {r.status_code}")
                sys.exit(1)

            with open(filepath, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

            cache_order[filename] = True
            maintain_cache_limit()
            print(f"Cached and available at: http://localhost:5000/video/{video_id}")
        except Exception as e:
            print(f"Error downloading video: {e}")
            sys.exit(1)

    app.run(host='0.0.0.0', port=5000, debug=True)
