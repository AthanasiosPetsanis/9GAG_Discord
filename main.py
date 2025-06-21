import os
import re
import subprocess
import requests
from flask import Flask, send_file, Response, redirect, request, abort
from collections import OrderedDict
from urllib.parse import urlparse
import sys

app = Flask(__name__)

# Config
VIDEO_CACHE_DIR = 'cache'
MAX_CACHE_SIZE = 100
FFMPEG_PATH = os.path.join('bin', 'ffmpeg')

cache_order = OrderedDict()

if not os.path.exists(VIDEO_CACHE_DIR):
    os.makedirs(VIDEO_CACHE_DIR)

def maintain_cache_limit():
    while len(cache_order) > MAX_CACHE_SIZE:
        oldest_file = next(iter(cache_order))
        try:
            os.remove(os.path.join(VIDEO_CACHE_DIR, oldest_file))
        except FileNotFoundError:
            pass
        cache_order.pop(oldest_file)

def transcode_to_h264(input_path, output_path):
    command = [
        FFMPEG_PATH,
        '-i', input_path,
        '-c:v', 'libx264',
        '-c:a', 'aac',
        '-movflags', '+faststart',
        '-y',  # overwrite
        output_path
    ]
    try:
        subprocess.run(command, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print("FFmpeg error:", e)
        return False

@app.route('/video/<video_id>')
def stream_video(video_id):
    filename = f"{video_id}.mp4"
    filepath = os.path.join(VIDEO_CACHE_DIR, filename)

    if not os.path.exists(filepath):
        return "Video not found. Submit it via the homepage first.", 404

    file_size = os.path.getsize(filepath)
    range_header = request.headers.get('Range', None)
    content_type = 'video/mp4'

    if range_header:
        byte1, byte2 = 0, None
        m = re.search(r'bytes=(\d+)-(\d*)', range_header)
        if m:
            g = m.groups()
            byte1 = int(g[0])
            if g[1]:
                byte2 = int(g[1])
        byte2 = byte2 or file_size - 1
        length = byte2 - byte1 + 1
        with open(filepath, 'rb') as f:
            f.seek(byte1)
            data = f.read(length)
        rv = Response(data, 206, mimetype=content_type, direct_passthrough=True)
        rv.headers.add('Content-Range', f'bytes {byte1}-{byte2}/{file_size}')
        rv.headers.add('Accept-Ranges', 'bytes')
        rv.headers.add('Content-Length', str(length))
        rv.headers.add('Content-Disposition', 'inline')
        return rv

    return send_file(filepath, mimetype=content_type, as_attachment=False)

@app.route('/photo/<path:filename>')
def proxy_from_clean_url(filename):
    video_id = filename.replace('.mp4', '')
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
    raw_filename = f"{video_id}_raw.mp4"
    final_filename = f"{video_id}.mp4"
    raw_path = os.path.join(VIDEO_CACHE_DIR, raw_filename)
    final_path = os.path.join(VIDEO_CACHE_DIR, final_filename)

    if not os.path.exists(final_path):
        try:
            r = requests.get(url, stream=True)
            if r.status_code != 200:
                return f"Failed to download video from 9GAG: {url}", 404
            with open(raw_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

            if not transcode_to_h264(raw_path, final_path):
                return "Failed to transcode video.", 500

            os.remove(raw_path)
            cache_order[final_filename] = True
            maintain_cache_limit()

        except Exception as e:
            return f"Error: {str(e)}", 500

    proxy_url = request.host_url + f"video/{video_id}"
    return f"Direct H.264 video link: <a href='{proxy_url}'>{proxy_url}</a><br><br>Copy this into Discord."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)