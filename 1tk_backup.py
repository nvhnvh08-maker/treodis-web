import asyncio
from curl_cffi.requests import AsyncSession
import random
import os
import sys
from pystyle import Colors, Colorate
from typing import List

BANNER = r"""
  _                                     
 | |_ ___ _ __    _   _  ___  __ _ _ __ 
 | __/ _ \ '_ \  | | | |/ _ \/ _` | '__|
 | ||  __/ | | | | |_| |  __/ (_| | |   
  \__\___|_| |_|  \__, |\___|\__,_|_|   
                  |___/                 
"""

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0"
]

class hdk:
    def __init__(self):
        self.tokens: List[str] = []
        self.channels: List[str] = []
        self.messages: List[str] = []
        self.global_delay: float = 0
        self.global_count: int = 1
        self.success_count = 0
        self.fail_count = 0
        self.send_counter = 0
        self._counter_lock = asyncio.Lock()

    def get_headers(self, token: str) -> dict:
        import base64 as b64, json as js
        ua = random.choice(USER_AGENTS)
        dev = {
            "os": "Windows", "browser": "Chrome", "device": "",
            "system_locale": "vi-VN", "browser_user_agent": ua,
            "browser_version": "139.0.0.0", "os_version": "10",
            "referrer": "https://discord.com/", "referring_domain": "discord.com",
            "release_channel": "stable",
            "client_build_number": random.randint(560000, 570000),
            "client_event_source": None
        }
        return {
            "Authorization": token,
            "Content-Type": "application/json",
            "User-Agent": ua,
            "Accept": "*/*",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8",
            "X-Super-Properties": b64.b64encode(js.dumps(dev, separators=(',', ':')).encode()).decode(),
            "Origin": "https://discord.com",
            "Referer": "https://discord.com/channels/@me",
            "X-Discord-Locale": "vi-VN",
            "X-Discord-Timezone": "Asia/Ho_Chi_Minh",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }

    def get_token_display(self, token: str) -> str:
        return token[:20] + "..." if len(token) > 20 else token[:len(token)//2] + "..."

    def log(self, msg: str, color=Colors.green_to_cyan):
        print(Colorate.Horizontal(color, msg))

    async def send_one(self, session: AsyncSession, token: str, channel_id: str, message: str) -> bool:
        import time as _time
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
        payload = {
            "content": message,
            "tts": False,
            "nonce": str(int(_time.time() * 1000) + random.randint(1000, 9999)),
            "flags": 0
        }

        for attempt in range(2):
            try:
                response = await session.post(
                    url, headers=self.get_headers(token),
                    json=payload, timeout=12, impersonate="chrome"
                )

                if response.status_code == 200:
                    async with self._counter_lock:
                        self.send_counter += 1
                        num = self.send_counter
                    token_display = self.get_token_display(token)
                    self.log(f"[HDK] {token_display} | GỬI {num}", Colors.rainbow)
                    self.success_count += 1
                    return True

                elif response.status_code == 429:
                    retry_after = response.json().get("retry_after", 1.5)
                    await asyncio.sleep(retry_after)
                    continue

                elif response.status_code in [401, 403]:
                    token_display = self.get_token_display(token)
                    self.log(f"[LỖI] {token_display} | {response.status_code} ✗", Colors.red_to_yellow)
                    self.fail_count += 1
                    return False

                else:
                    await asyncio.sleep(random.uniform(0.3, 0.7))
                    continue

            except Exception:
                if attempt < 1:
                    await asyncio.sleep(random.uniform(0.5, 1.0))
                    continue
                token_display = self.get_token_display(token)
                self.log(f"[LỖI] {token_display} | KẾT NỐI THẤT BẠI ", Colors.red_to_yellow)
                self.fail_count += 1
                return False

        return False

    async def send_batch_to_channel(self, session: AsyncSession, token: str, channel_id: str):
        for i in range(self.global_count):
            msg = random.choice(self.messages)
            await self.send_one(session, token, channel_id, msg)
            if i < self.global_count - 1:
                await asyncio.sleep(random.uniform(0.15, 0.35))

    async def spam_token(self, session: AsyncSession, token: str):
        while True:
            await asyncio.gather(*[
                self.send_batch_to_channel(session, token, ch)
                for ch in self.channels
            ])
            await asyncio.sleep(self.global_delay)

    async def start_spam(self):
        async with AsyncSession(impersonate="chrome", verify=False) as session:
            await asyncio.gather(*[
                self.spam_token(session, token) for token in self.tokens
            ], return_exceptions=True)

    def run(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))

        os.system('cls' if os.name == 'nt' else 'clear')
        print(Colorate.Horizontal(Colors.purple_to_blue, BANNER))

        token_path = os.path.join(base_dir, 'tokens.txt')
        try:
            with open(token_path, 'r', encoding='utf-8') as f:
                self.tokens = [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            self.log("✗ Không tìm thấy tokens.txt", Colors.red_to_yellow)
            return
        if not self.tokens:
            self.log("✗ tokens.txt trống!", Colors.red_to_yellow)
            return
        print(Colorate.Horizontal(Colors.green_to_cyan, f" Load Token từ file | {len(self.tokens)} token"))

        channel_path = os.path.join(base_dir, 'channel.txt')
        try:
            with open(channel_path, 'r', encoding='utf-8') as f:
                self.channels = [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            self.log("✗ Không tìm thấy channel.txt", Colors.red_to_yellow)
            return
        if not self.channels:
            self.log("✗ channel.txt trống!", Colors.red_to_yellow)
            return
        print(Colorate.Horizontal(Colors.green_to_cyan, f" Load Channel từ file | {len(self.channels)} kênh"))

 
        msg_path = os.path.join(base_dir, 'ngon.txt')
        try:
            with open(msg_path, 'r', encoding='utf-8') as f:
                message_content = f.read().strip()
            if not message_content:
                self.log("✗ ngon.txt trống!", Colors.red_to_yellow)
                return
            self.messages = [message_content] 
            print(Colorate.Horizontal(Colors.green_to_cyan, f" Load Nội dung từ file | {len(message_content)} ký tự"))
        except FileNotFoundError:
            self.log("✗ Không tìm thấy ngon.txt", Colors.red_to_yellow)
            return

    
        times_path = os.path.join(base_dir, 'tinnhan.txt')
        try:
            with open(times_path, 'r', encoding='utf-8') as f:
                times_content = f.read().strip()
            self.global_count = int(times_content)
            if self.global_count <= 0:
                self.global_count = 1
            print(Colorate.Horizontal(Colors.green_to_cyan, f" Load Số lần bắn từ file | {self.global_count} lần"))
        except FileNotFoundError:
            self.log("✗ Không tìm thấy tinnhan.txt", Colors.red_to_yellow)
            return
        except ValueError:
            self.log("✗ tinnhan.txt phải chứa số hợp lệ", Colors.red_to_yellow)
            return

        delay_path = os.path.join(base_dir, 'delay.txt')
        try:
            with open(delay_path, 'r', encoding='utf-8') as f:
                self.global_delay = float(f.read().strip())
            print(Colorate.Horizontal(Colors.green_to_cyan, f" Load Delay từ file | {self.global_delay}s"))
        except FileNotFoundError:
            self.log("✗ Không tìm thấy delay.txt", Colors.red_to_yellow)
            return
        except ValueError:
            self.log("✗ delay.txt phải chứa số hợp lệ", Colors.red_to_yellow)
            return

        os.system('cls' if os.name == 'nt' else 'clear')
        print(Colorate.Horizontal(Colors.purple_to_blue, BANNER))

        try:
            asyncio.run(self.start_spam())
        except KeyboardInterrupt:
            print(Colorate.Horizontal(Colors.green_to_cyan, f"\n Thành công: {self.success_count}"))
            print(Colorate.Horizontal(Colors.red_to_yellow, f" Thất bại  : {self.fail_count}"))
            print(Colorate.Horizontal(Colors.blue_to_cyan, "Đã dừng tool!"))

def main():
    spammer = hdk()
    spammer.run()

if __name__ == "__main__":
    main()
