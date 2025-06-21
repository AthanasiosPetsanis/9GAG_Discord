# Updated Flask proxy server to support intuitive 69gag.xyz URL format for Discord embedding

import os
import requests
from flask import Flask, send_file, Response, redirect, request, abort
from collections import OrderedDict
from urllib.parse import urlparse
import sys
import mimetypes
import re

app = Flask(__name__)

# Config
VIDEO_CACHE_DIR = 'cache'
MAX_CACHE_SIZE = 100

cache_order = OrderedDict()

if not os.path.exists(VIDEO_CACHE_DIR):
    os.makedirs(VIDEO_CACHE_DIR)

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
        return "Video not found.", 404

    file_size = os.path.getsize(filepath)
    range_header = request.headers.get('Range', None)
    content_type = mimetypes.guess_type(filepath)[0] or 'application/octet-stream'

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
    app.run(host='0.0.0.0', port=5000)

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
