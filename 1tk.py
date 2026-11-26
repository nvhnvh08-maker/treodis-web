import asyncio
from curl_cffi.requests import AsyncSession
import random
import os
import sys
import time as _time
import base64 as b64
import json as js
from pystyle import Colors, Colorate
from typing import List

BANNER = r"""
  _                                     
 | |_ ___ _ __    _   _  ___  __ _ _ __ 
 | __/ _ \ '_ \  | | | |/ _ \/ _` | '__|
 | ||  __/ | | | | |_| |  __/ (_| | |   
  \__\___|_| |_|  \__, |\___|\__,_|_|   
                  |___/                 
         [ AUTO ANTI-COMPRESS & PACING ]
"""

USER_AGENTS = [
    {
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
        "browser": "Chrome",
        "version": "139.0.0.0",
        "sec_ch_ua": '"Not;A=Brand";v="99", "Google Chrome";v="139", "Chromium";v="139"'
    },
    {
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
        "browser": "Chrome",
        "version": "138.0.0.0",
        "sec_ch_ua": '"Not;A=Brand";v="99", "Google Chrome";v="138", "Chromium";v="138"'
    },
    {
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0",
        "browser": "Edge",
        "version": "139.0.0.0",
        "sec_ch_ua": '"Not;A=Brand";v="99", "Microsoft Edge";v="139", "Chromium";v="139"'
    }
]

# Ký tự tàng hình (Zero-Width Characters)
ZERO_WIDTH_CHARS = ["\u200b", "\u200c", "\u200d", "\ufeff"]

def generate_snowflake_nonce() -> str:
    """Tạo Nonce chuẩn Snowflake ID của Discord Web (Discord Epoch: 2015-01-01)"""
    discord_epoch = 1420070400000
    current_ms = int(_time.time() * 1000)
    time_part = (current_ms - discord_epoch) << 22
    random_part = random.randint(0, 0x3FFFFF)
    return str(time_part | random_part)

def anti_compress_content(text: str) -> str:
    """
    Kỹ thuật chống nén ngôn:
    Chèn ký tự tàng hình ngẫu nhiên vào các dòng và cuối nội dung.
    Giúp tạo chuỗi hash riêng biệt, ngăn Discord gộp nhóm và ngăn duplicate filter.
    """
    lines = text.split("\n")
    formatted_lines = []
    for line in lines:
        if line.strip():
            tail_ghost = "".join(random.choices(ZERO_WIDTH_CHARS, k=random.randint(1, 3)))
            formatted_lines.append(line + tail_ghost)
        else:
            formatted_lines.append(line)
    
    global_ghost = "".join(random.choices(ZERO_WIDTH_CHARS, k=random.randint(2, 5)))
    return "\n".join(formatted_lines) + global_ghost

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
        self.client_build = random.randint(382000, 383000)
        
        # Nhịp vàng chống nén ngôn khi gửi nhanh (0.35s - 0.45s giúp Discord Client kịp render đầy đủ khung)
        self.anti_compress_pacing = 0.38

    def get_headers(self, token: str) -> dict:
        client_info = random.choice(USER_AGENTS)
        dev = {
            "os": "Windows",
            "browser": client_info["browser"],
            "device": "",
            "system_locale": "vi-VN",
            "browser_user_agent": client_info["ua"],
            "browser_version": client_info["version"],
            "os_version": "10",
            "referrer": "https://discord.com/",
            "referring_domain": "discord.com",
            "release_channel": "stable",
            "client_build_number": self.client_build,
            "client_event_source": None
        }
        sp_json = js.dumps(dev, separators=(',', ':'))
        sp_base64 = b64.b64encode(sp_json.encode()).decode()

        return {
            "Authorization": token,
            "Content-Type": "application/json",
            "User-Agent": client_info["ua"],
            "Accept": "*/*",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8",
            "X-Super-Properties": sp_base64,
            "Origin": "https://discord.com",
            "Referer": "https://discord.com/channels/@me",
            "X-Discord-Locale": "vi-VN",
            "X-Discord-Timezone": "Asia/Ho_Chi_Minh",
            "Sec-Ch-Ua": client_info["sec_ch_ua"],
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }

    def get_token_display(self, token: str) -> str:
        return token[:20] + "..." if len(token) > 20 else token[:len(token)//2] + "..."

    def log(self, msg: str, color=Colors.green_to_cyan):
        print(Colorate.Horizontal(color, msg))

    async def send_one(self, session: AsyncSession, token: str, channel_id: str, raw_message: str) -> bool:
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
        
        content = anti_compress_content(raw_message)
        nonce = generate_snowflake_nonce()
        
        payload = {
            "content": content,
            "tts": False,
            "nonce": nonce,
            "flags": 0
        }

        headers = self.get_headers(token)

        for attempt in range(3):
            try:
                response = await session.post(
                    url, headers=headers,
                    json=payload, timeout=10, impersonate="chrome"
                )

                if response.status_code == 200:
                    async with self._counter_lock:
                        self.send_counter += 1
                        num = self.send_counter
                    token_display = self.get_token_display(token)
                    self.log(f"[HDK] {token_display} | BUNG NGÔN THÀNH CÔNG #{num}", Colors.rainbow)
                    self.success_count += 1
                    return True

                elif response.status_code == 429:
                    try:
                        res_data = response.json()
                        retry_after = float(res_data.get("retry_after", 0.8))
                    except Exception:
                        retry_after = 0.8
                    
                    token_display = self.get_token_display(token)
                    self.log(f"[CHỜ 429] {token_display} | Đợi hồi Rate Limit {retry_after:.2f}s...", Colors.yellow_to_red)
                    await asyncio.sleep(retry_after + 0.05)
                    continue

                elif response.status_code in [401, 403]:
                    token_display = self.get_token_display(token)
                    self.log(f"[LỖI TOKEN] {token_display} | Mã {response.status_code} (Không có quyền/Token die)", Colors.red_to_yellow)
                    self.fail_count += 1
                    return False

                else:
                    await asyncio.sleep(0.3)
                    continue

            except Exception:
                if attempt < 2:
                    await asyncio.sleep(0.3)
                    continue
                token_display = self.get_token_display(token)
                self.log(f"[LỖI MẠNG] {token_display} | Mất kết nối", Colors.red_to_yellow)
                self.fail_count += 1
                return False

        return False

    async def send_batch_to_channel(self, session: AsyncSession, token: str, channel_id: str):
        for i in range(self.global_count):
            msg = random.choice(self.messages)
            await self.send_one(session, token, channel_id, msg)
            if i < self.global_count - 1:
                # Nếu chỉ có 1 token hoặc gửi nhanh: áp dụng nhịp vàng 0.35s - 0.45s để Discord Client kịp bung khung, không bị nén!
                if self.global_delay == 0:
                    # Nhịp vàng chống nén ngôn
                    await asyncio.sleep(self.anti_compress_pacing)
                else:
                    await asyncio.sleep(random.uniform(0.15, 0.30))

    async def spam_token(self, session: AsyncSession, token: str):
        while True:
            await asyncio.gather(*[
                self.send_batch_to_channel(session, token, ch)
                for ch in self.channels
            ])
            # Nghỉ theo global_delay cấu hình
            if self.global_delay <= 0:
                # Nếu delay 0, nghỉ tối thiểu 0.3s để tránh kẹt rate limit và bung mượt đợt tiếp theo
                await asyncio.sleep(0.3)
            else:
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
        print(Colorate.Horizontal(Colors.green_to_cyan, f"✔ Đã load {len(self.tokens)} Token"))

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
        print(Colorate.Horizontal(Colors.green_to_cyan, f"✔ Đã load {len(self.channels)} Kênh"))

        msg_path = os.path.join(base_dir, 'ngon.txt')
        try:
            with open(msg_path, 'r', encoding='utf-8') as f:
                message_content = f.read().strip()
            if not message_content:
                self.log("✗ ngon.txt trống!", Colors.red_to_yellow)
                return
            self.messages = [message_content]
            print(Colorate.Horizontal(Colors.green_to_cyan, f"✔ Đã load Nội dung ({len(message_content)} ký tự) - Đã kích hoạt Anti-Nén"))
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
            print(Colorate.Horizontal(Colors.green_to_cyan, f"✔ Số lần bắn mỗi đợt: {self.global_count} lần"))
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
            print(Colorate.Horizontal(Colors.green_to_cyan, f"✔ Cấu hình Delay: {self.global_delay}s"))
        except FileNotFoundError:
            self.log("✗ Không tìm thấy delay.txt", Colors.red_to_yellow)
            return
        except ValueError:
            self.log("✗ delay.txt phải chứa số hợp lệ", Colors.red_to_yellow)
            return

        print(Colorate.Horizontal(Colors.yellow_to_green, f"[*] Chế độ: Nhịp vàng chống nén ngôn ({self.anti_compress_pacing}s/tin) - Bung khung cực đẹp"))
        print(Colorate.Horizontal(Colors.cyan_to_blue, "\n[!] Bắt đầu chạy tool, bấm Ctrl+C để dừng...\n"))

        try:
            asyncio.run(self.start_spam())
        except KeyboardInterrupt:
            print(Colorate.Horizontal(Colors.green_to_cyan, f"\n✔ Thành công: {self.success_count}"))
            print(Colorate.Horizontal(Colors.red_to_yellow, f"✗ Thất bại  : {self.fail_count}"))
            print(Colorate.Horizontal(Colors.blue_to_cyan, "Đã dừng tool an toàn!"))

def main():
    spammer = hdk()
    spammer.run()

if __name__ == "__main__":
    main()
