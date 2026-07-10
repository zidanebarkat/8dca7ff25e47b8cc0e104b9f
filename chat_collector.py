#!/usr/bin/env python3
import os, time, json
from curl_cffi import requests

KICK_CHANNEL = os.environ.get('KICK_CHANNEL', 'zed-bx')
HEADERS = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'}

def get_chatroom_id(channel):
    r = requests.get(f'https://kick.com/api/v2/channels/{channel}',
                     impersonate='chrome120', headers=HEADERS, timeout=15)
    return r.json().get('chatroom', {}).get('id')

def main():
    chatroom_id = get_chatroom_id(KICK_CHANNEL)
    if not chatroom_id:
        return

    seen = set()
    messages = []
    max_messages = 15

    while True:
        try:
            r = requests.get(f'https://kick.com/api/v2/messages/chat/{chatroom_id}?page=1',
                             impersonate='chrome120', headers=HEADERS, timeout=15)
            data = r.json()
            for msg in data.get('messages', []):
                mid = msg.get('id')
                if mid and mid not in seen:
                    seen.add(mid)
                    username = msg.get('sender', {}).get('username', '?')
                    content = msg.get('content', '')
                    if len(content) > 80:
                        content = content[:77] + '...'
                    messages.append(f"{username}: {content}")
                    if len(messages) > max_messages:
                        messages = messages[-max_messages:]
            if messages:
                with open('chat.txt', 'w', encoding='utf-8') as f:
                    f.write('\n'.join(messages))
        except Exception:
            pass
        time.sleep(5)

if __name__ == '__main__':
    main()
