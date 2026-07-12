#!/usr/bin/env python3
"""Live chat renderer - polls YouTube/Facebook chat and writes to chat.txt for ffmpeg overlay."""
import sys, os, time, json, urllib.request, urllib.parse, urllib.error, threading, collections

def yt_get_live_chat_id(video_id, api_key):
    url = f"https://www.googleapis.com/youtube/v3/videos?part=liveStreamingDetails&id={video_id}&key={api_key}"
    try:
        resp = urllib.request.urlopen(url, timeout=10)
        data = json.loads(resp.read())
        items = data.get('items', [])
        if items:
            lsd = items[0].get('liveStreamingDetails', {})
            return lsd.get('activeLiveChatId') or lsd.get('liveChatId')
    except Exception as e:
        print(f"YT chat ID error: {e}", file=sys.stderr)
    return None

def yt_poll_chat(live_chat_id, api_key, messages, max_messages=12):
    page_token = ''
    poll_ms = 2000
    url = f"https://www.googleapis.com/youtube/v3/liveChat/messages?liveChatId={live_chat_id}&part=snippet&key={api_key}&maxResults=100"
    if page_token:
        url += f"&pageToken={page_token}"
    try:
        resp = urllib.request.urlopen(url, timeout=10)
        data = json.loads(resp.read())
        for item in data.get('items', []):
            snippet = item.get('snippet', {})
            author = snippet.get('authorDetails', {}).get('displayName', '') if 'authorDetails' in snippet else ''
            text = snippet.get('displayMessage', '') or snippet.get('textMessageDetails', {}).get('messageText', '')
            if text:
                entry = f"{author}: {text}" if author else text
                messages.append(entry)
        while len(messages) > max_messages:
            messages.popleft()
        poll_ms = data.get('pollingIntervalMillis', 2000)
    except urllib.error.HTTPError as e:
        code = e.code
        if code == 403:
            print("YT chat API quota exceeded or access denied", file=sys.stderr)
        elif code == 404:
            print("YT live chat not found (stream may have ended)", file=sys.stderr)
        else:
            print(f"YT chat poll error: HTTP {code}", file=sys.stderr)
    except Exception as e:
        print(f"YT chat poll error: {e}", file=sys.stderr)
    return poll_ms

def fb_poll_comments(video_id, access_token, messages, max_messages=12):
    url = f"https://graph.facebook.com/v19.0/{video_id}/comments?fields=message,from,created_time&access_token={access_token}&limit=25&order=reverse_chronological"
    try:
        resp = urllib.request.urlopen(url, timeout=10)
        data = json.loads(resp.read())
        for item in reversed(data.get('data', [])):
            text = item.get('message', '')
            author = item.get('from', {}).get('name', '')
            if text:
                entry = f"{author}: {text}" if author else text
                messages.append(entry)
        while len(messages) > max_messages:
            messages.popleft()
    except Exception as e:
        print(f"FB chat poll error: {e}", file=sys.stderr)

def write_chat_file(messages, filepath):
    text = '\n'.join(messages) if messages else ' '
    tmp = filepath + '.tmp'
    with open(tmp, 'w') as f:
        f.write(text)
    os.replace(tmp, filepath)

def extract_video_id(url_or_id):
    import re
    if re.match(r'^[a-zA-Z0-9_-]{11}$', url_or_id):
        return url_or_id
    patterns = [
        r'youtube\.com/watch\?.*v=([a-zA-Z0-9_-]{11})',
        r'youtu\.be/([a-zA-Z0-9_-]{11})',
        r'youtube\.com/embed/([a-zA-Z0-9_-]{11})',
        r'youtube\.com/v/([a-zA-Z0-9_-]{11})',
    ]
    for p in patterns:
        m = re.search(p, url_or_id)
        if m:
            return m.group(1)
    return url_or_id

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--platform', required=True, choices=['youtube', 'facebook'])
    parser.add_argument('--video-id', required=True)
    parser.add_argument('--api-key', default='')
    parser.add_argument('--access-token', default='')
    parser.add_argument('--output', default='chat.txt')
    parser.add_argument('--max-messages', type=int, default=12)
    parser.add_argument('--poll-interval', type=float, default=3.0)
    args = parser.parse_args()

    messages = collections.deque()
    print(f"Chat renderer started: {args.platform} (max {args.max_messages} messages)")

    if args.platform == 'youtube':
        if not args.api_key:
            print("ERROR: YouTube requires --api-key", file=sys.stderr)
            sys.exit(1)
        video_id = extract_video_id(args.video_id)
        live_chat_id = None
        retries = 0
        while not live_chat_id and retries < 30:
            live_chat_id = yt_get_live_chat_id(args.video_id, args.api_key)
            if not live_chat_id:
                retries += 1
                print(f"Waiting for live chat ID (attempt {retries}/30)...", file=sys.stderr)
                time.sleep(5)
        if not live_chat_id:
            print("ERROR: Could not get live chat ID after 30 attempts", file=sys.stderr)
            sys.exit(1)
        print(f"Live chat ID: {live_chat_id}")
        while True:
            try:
                yt_poll_chat(live_chat_id, args.api_key, messages, args.max_messages)
                write_chat_file(messages, args.output)
            except Exception as e:
                print(f"Error: {e}", file=sys.stderr)
            time.sleep(args.poll_interval)

    elif args.platform == 'facebook':
        if not args.access_token:
            print("ERROR: Facebook requires --access-token", file=sys.stderr)
            sys.exit(1)
        while True:
            try:
                fb_poll_comments(args.video_id, args.access_token, messages, args.max_messages)
                write_chat_file(messages, args.output)
            except Exception as e:
                print(f"Error: {e}", file=sys.stderr)
            time.sleep(args.poll_interval)

if __name__ == '__main__':
    main()
