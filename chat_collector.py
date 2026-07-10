#!/usr/bin/env python3
import socket, re, os, sys, time

def get_channel(source_url):
    m = re.search(r'twitch\.tv/(\w+)', source_url)
    return m.group(1).lower() if m else None

def main():
    source_url = os.environ.get('SOURCE_URL', '')
    channel = get_channel(source_url)
    if not channel:
        return

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    try:
        sock.connect(('irc.chat.twitch.tv', 6667))
        sock.sendall(b'NICK justinfan42069\r\n')
        sock.sendall(b'USER justinfan42069 8 * :justinfan42069\r\n')
        sock.sendall(f'JOIN #{channel}\r\n'.encode())
    except Exception:
        return

    messages = []
    max_messages = 15
    sock.settimeout(30)

    while True:
        try:
            data = sock.recv(8192).decode('utf-8', errors='replace')
            for line in data.split('\r\n'):
                line = line.strip()
                if not line:
                    continue
                if line.startswith('PING'):
                    sock.sendall(line.replace('PING', 'PONG').encode() + b'\r\n')
                    continue
                m = re.match(r'^:(\w+)!\w+@\w+\.tmi\.twitch\.tv PRIVMSG #\w+ :(.+)$', line)
                if m:
                    username = m.group(1)
                    msg = m.group(2)
                    if len(msg) > 80:
                        msg = msg[:77] + '...'
                    messages.append(f"{username}: {msg}")
                    if len(messages) > max_messages:
                        messages = messages[-max_messages:]
                    with open('chat.txt', 'w', encoding='utf-8') as f:
                        f.write('\n'.join(messages))
        except socket.timeout:
            try:
                sock.sendall(b'PONG :tmi.twitch.tv\r\n')
            except Exception:
                break
        except Exception:
            time.sleep(1)

if __name__ == '__main__':
    main()
