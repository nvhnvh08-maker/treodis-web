import asyncio
import base64
import hashlib
import hmac
import json
import os
import random
import secrets
import sqlite3
import time
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional

from aiohttp import web
from curl_cffi.requests import AsyncSession

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DB_PATH = BASE_DIR / "data.db"

USER_AGENTS = [
    {
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
        "browser": "Chrome",
        "version": "139.0.0.0",
        "sec_ch_ua": '"Not;A=Brand";v="99", "Google Chrome";v="139", "Chromium";v="139"',
    },
    {
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
        "browser": "Chrome",
        "version": "138.0.0.0",
        "sec_ch_ua": '"Not;A=Brand";v="99", "Google Chrome";v="138", "Chromium";v="138"',
    },
    {
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0",
        "browser": "Edge",
        "version": "139.0.0.0",
        "sec_ch_ua": '"Not;A=Brand";v="99", "Microsoft Edge";v="139", "Chromium";v="139"',
    },
]

ZERO_WIDTH_CHARS = ["\u200b", "\u200c", "\u200d", "\ufeff"]
ANTI_COMPRESS_PACING = 0.38


def generate_snowflake_nonce() -> str:
    """Tạo Nonce chuẩn Snowflake ID của Discord Web (Discord Epoch: 2015-01-01)."""
    discord_epoch = 1420070400000
    current_ms = int(time.time() * 1000)
    time_part = (current_ms - discord_epoch) << 22
    random_part = random.randint(0, 0x3FFFFF)
    return str(time_part | random_part)


def anti_compress_content(text: str) -> str:
    """Chèn ký tự tàng hình ngẫu nhiên để chống nén và tránh bộ lọc trùng lặp."""
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


def mask_token(token: str) -> str:
    if len(token) > 20:
        return token[:16] + "..."
    return token[: max(1, len(token) // 2)] + "..."


def hash_password(password: str, salt: Optional[str] = None) -> str:
    if salt is None:
        salt = secrets.token_hex(16)
    dk = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt.encode("utf-8"),
        n=16384,
        r=8,
        p=1,
    )
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, expected_hex = stored.split("$", 1)
    except ValueError:
        return False
    computed = hash_password(password, salt)
    return hmac.compare_digest(computed, stored)


def init_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at REAL NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS tabs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            tokens_text TEXT NOT NULL DEFAULT '',
            channels_text TEXT NOT NULL DEFAULT '',
            delay REAL NOT NULL DEFAULT 0,
            burst_count INTEGER NOT NULL DEFAULT 1,
            message_text TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """
    )
    conn.commit()
    return conn


class TabRuntime:
    def __init__(self, tab_id: int) -> None:
        self.tab_id = tab_id
        self.running = False
        self.started_at: Optional[float] = None
        self.elapsed_saved: float = 0.0
        self.success_count: int = 0
        self.fail_count: int = 0
        self.send_counter: int = 0
        self.logs: deque = deque(maxlen=40)
        self.task: Optional[asyncio.Task] = None
        self._counter_lock = asyncio.Lock()
        self.client_build = random.randint(382000, 383000)

    def add_log(self, level: str, text: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self.logs.append({"ts": ts, "level": level, "text": text})

    def current_elapsed(self) -> int:
        if self.running and self.started_at is not None:
            return int(self.elapsed_saved + (time.time() - self.started_at))
        return int(self.elapsed_saved)

    def build_headers(self, token: str) -> dict:
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
            "client_event_source": None,
        }
        sp_json = json.dumps(dev, separators=(",", ":"))
        sp_base64 = base64.b64encode(sp_json.encode()).decode()
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

    async def send_one(
        self,
        session: AsyncSession,
        token: str,
        channel_id: str,
        raw_message: str,
    ) -> bool:
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
        payload = {
            "content": anti_compress_content(raw_message),
            "tts": False,
            "nonce": generate_snowflake_nonce(),
            "flags": 0,
        }
        headers = self.build_headers(token)
        token_label = mask_token(token)

        for attempt in range(3):
            if not self.running:
                return False
            try:
                response = await session.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=10,
                    impersonate="chrome",
                )
                if response.status_code == 200:
                    async with self._counter_lock:
                        self.send_counter += 1
                        self.success_count += 1
                        num = self.send_counter
                    self.add_log("ok", f"{token_label} | Kênh {channel_id} | Đã gửi #{num}")
                    return True

                if response.status_code == 429:
                    try:
                        retry_after = float(response.json().get("retry_after", 0.8))
                    except Exception:
                        retry_after = 0.8
                    self.add_log("warn", f"{token_label} | Rate limit 429, đợi {retry_after:.2f}s")
                    await asyncio.sleep(retry_after + 0.05)
                    continue

                if response.status_code in (401, 403):
                    self.fail_count += 1
                    self.add_log("err", f"{token_label} | Mã {response.status_code} (Token lỗi hoặc thiếu quyền)")
                    return False

                await asyncio.sleep(0.3)
            except asyncio.CancelledError:
                raise
            except Exception:
                if attempt < 2:
                    await asyncio.sleep(0.3)
                    continue
                self.fail_count += 1
                self.add_log("err", f"{token_label} | Mất kết nối tới Discord")
                return False

        return False

    async def send_batch(
        self,
        session: AsyncSession,
        token: str,
        channel_id: str,
        message_text: str,
        burst_count: int,
        global_delay: float,
    ) -> None:
        for i in range(burst_count):
            if not self.running:
                return
            await self.send_one(session, token, channel_id, message_text)
            if i < burst_count - 1:
                if global_delay == 0:
                    await asyncio.sleep(ANTI_COMPRESS_PACING)
                else:
                    await asyncio.sleep(random.uniform(0.15, 0.30))

    async def spam_token(
        self,
        session: AsyncSession,
        token: str,
        channels: List[str],
        message_text: str,
        burst_count: int,
        global_delay: float,
    ) -> None:
        while self.running:
            await asyncio.gather(
                *[
                    self.send_batch(session, token, ch, message_text, burst_count, global_delay)
                    for ch in channels
                ]
            )
            if not self.running:
                break
            sleep_time = 0.3 if global_delay <= 0 else global_delay
            await asyncio.sleep(sleep_time)

    async def run_loop(
        self,
        tokens: List[str],
        channels: List[str],
        message_text: str,
        burst_count: int,
        global_delay: float,
    ) -> None:
        self.add_log(
            "info",
            f"Bắt đầu treo ({len(tokens)} token, {len(channels)} kênh, bắn {burst_count}/đợt, delay {global_delay}s)",
        )
        try:
            async with AsyncSession(impersonate="chrome", verify=False) as session:
                await asyncio.gather(
                    *[
                        self.spam_token(session, tk, channels, message_text, burst_count, global_delay)
                        for tk in tokens
                    ],
                    return_exceptions=True,
                )
        except asyncio.CancelledError:
            pass
        finally:
            if self.running and self.started_at is not None:
                self.elapsed_saved += time.time() - self.started_at
            self.running = False
            self.started_at = None
            self.add_log("info", "Đã dừng luồng gửi")


class WorkerManager:
    def __init__(self) -> None:
        self.runtimes: Dict[int, TabRuntime] = {}

    def get(self, tab_id: int) -> TabRuntime:
        if tab_id not in self.runtimes:
            self.runtimes[tab_id] = TabRuntime(tab_id)
        return self.runtimes[tab_id]

    def start(self, tab_row: sqlite3.Row) -> TabRuntime:
        rt = self.get(tab_row["id"])
        if rt.running:
            return rt

        tokens = [x.strip() for x in tab_row["tokens_text"].splitlines() if x.strip()]
        channels = [x.strip() for x in tab_row["channels_text"].splitlines() if x.strip()]
        message_text = tab_row["message_text"].strip()
        burst_count = max(1, int(tab_row["burst_count"] or 1))
        global_delay = max(0.0, float(tab_row["delay"] or 0.0))

        if not tokens:
            raise ValueError("Chưa nhập Token")
        if not channels:
            raise ValueError("Chưa nhập ID Channel")
        if not message_text:
            raise ValueError("Chưa có nội dung ngôn")

        rt.running = True
        rt.started_at = time.time()
        rt.task = asyncio.create_task(
            rt.run_loop(tokens, channels, message_text, burst_count, global_delay)
        )
        return rt

    async def stop(self, tab_id: int) -> TabRuntime:
        rt = self.get(tab_id)
        if rt.running and rt.started_at is not None:
            rt.elapsed_saved += time.time() - rt.started_at
        rt.running = False
        rt.started_at = None
        if rt.task and not rt.task.done():
            rt.task.cancel()
            try:
                await rt.task
            except asyncio.CancelledError:
                pass
        rt.task = None
        return rt

    async def stop_all(self) -> None:
        for tab_id in list(self.runtimes.keys()):
            await self.stop(tab_id)


def serialize_tab(row: sqlite3.Row, runtime: TabRuntime) -> dict:
    tokens_count = len([x for x in row["tokens_text"].splitlines() if x.strip()])
    channels_count = len([x for x in row["channels_text"].splitlines() if x.strip()])
    return {
        "id": row["id"],
        "name": row["name"],
        "tokens_text": row["tokens_text"],
        "channels_text": row["channels_text"],
        "delay": row["delay"],
        "burst_count": row["burst_count"],
        "message_text": row["message_text"],
        "tokens_count": tokens_count,
        "channels_count": channels_count,
        "running": runtime.running,
        "elapsed_seconds": runtime.current_elapsed(),
        "started_at": runtime.started_at,
        "success_count": runtime.success_count,
        "fail_count": runtime.fail_count,
        "logs": list(runtime.logs),
    }


def get_current_user(request: web.Request) -> Optional[sqlite3.Row]:
    token = request.cookies.get("session_token")
    if not token:
        return None
    db: sqlite3.Connection = request.app["db"]
    return db.execute(
        """
        SELECT users.id, users.username
        FROM sessions
        JOIN users ON users.id = sessions.user_id
        WHERE sessions.token = ?
        """,
        (token,),
    ).fetchone()


async def handle_index(request: web.Request) -> web.FileResponse:
    return web.FileResponse(STATIC_DIR / "index.html")


async def handle_health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "ts": int(time.time())})


async def handle_me(request: web.Request) -> web.Response:
    user = get_current_user(request)
    if not user:
        return web.json_response({"user": None})
    return web.json_response({"user": {"id": user["id"], "username": user["username"]}})


async def handle_register(request: web.Request) -> web.Response:
    data = await request.json()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if len(username) < 3 or len(username) > 32:
        return web.json_response({"error": "Tên đăng nhập phải từ 3 đến 32 ký tự"}, status=400)
    if len(password) < 4:
        return web.json_response({"error": "Mật khẩu phải có ít nhất 4 ký tự"}, status=400)

    db: sqlite3.Connection = request.app["db"]
    existing = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if existing:
        return web.json_response({"error": "Tên đăng nhập đã tồn tại"}, status=409)

    pw_hash = hash_password(password)
    cur = db.execute(
        "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
        (username, pw_hash, time.time()),
    )
    user_id = cur.lastrowid
    session_token = secrets.token_urlsafe(32)
    db.execute(
        "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
        (session_token, user_id, time.time()),
    )
    db.commit()

    resp = web.json_response({"user": {"id": user_id, "username": username}}, status=201)
    resp.set_cookie("session_token", session_token, httponly=True, samesite="Lax", path="/", max_age=2592000)
    return resp


async def handle_login(request: web.Request) -> web.Response:
    data = await request.json()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    db: sqlite3.Connection = request.app["db"]
    user = db.execute(
        "SELECT id, username, password_hash FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    if not user or not verify_password(password, user["password_hash"]):
        return web.json_response({"error": "Sai tên đăng nhập hoặc mật khẩu"}, status=401)

    session_token = secrets.token_urlsafe(32)
    db.execute(
        "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
        (session_token, user["id"], time.time()),
    )
    db.commit()

    resp = web.json_response({"user": {"id": user["id"], "username": user["username"]}})
    resp.set_cookie("session_token", session_token, httponly=True, samesite="Lax", path="/", max_age=2592000)
    return resp


async def handle_logout(request: web.Request) -> web.Response:
    token = request.cookies.get("session_token")
    if token:
        db: sqlite3.Connection = request.app["db"]
        db.execute("DELETE FROM sessions WHERE token = ?", (token,))
        db.commit()
    resp = web.json_response({"ok": True})
    resp.del_cookie("session_token", path="/")
    return resp


async def handle_list_tabs(request: web.Request) -> web.Response:
    user = get_current_user(request)
    if not user:
        return web.json_response({"error": "Chưa đăng nhập"}, status=401)

    db: sqlite3.Connection = request.app["db"]
    workers: WorkerManager = request.app["workers"]
    rows = db.execute(
        "SELECT * FROM tabs WHERE user_id = ? ORDER BY id ASC",
        (user["id"],),
    ).fetchall()
    return web.json_response({"tabs": [serialize_tab(r, workers.get(r["id"])) for r in rows]})


async def handle_create_tab(request: web.Request) -> web.Response:
    user = get_current_user(request)
    if not user:
        return web.json_response({"error": "Chưa đăng nhập"}, status=401)

    data = await request.json()
    name = (data.get("name") or "").strip()
    if not name:
        return web.json_response({"error": "Vui lòng nhập tên tab"}, status=400)
    if len(name) > 60:
        return web.json_response({"error": "Tên tab tối đa 60 ký tự"}, status=400)

    db: sqlite3.Connection = request.app["db"]
    workers: WorkerManager = request.app["workers"]
    cur = db.execute(
        "INSERT INTO tabs (user_id, name, created_at) VALUES (?, ?, ?)",
        (user["id"], name, time.time()),
    )
    db.commit()
    row = db.execute("SELECT * FROM tabs WHERE id = ?", (cur.lastrowid,)).fetchone()
    return web.json_response({"tab": serialize_tab(row, workers.get(row["id"]))}, status=201)


async def handle_update_tab(request: web.Request) -> web.Response:
    user = get_current_user(request)
    if not user:
        return web.json_response({"error": "Chưa đăng nhập"}, status=401)

    tab_id = int(request.match_info["id"])
    db: sqlite3.Connection = request.app["db"]
    workers: WorkerManager = request.app["workers"]
    row = db.execute(
        "SELECT * FROM tabs WHERE id = ? AND user_id = ?",
        (tab_id, user["id"]),
    ).fetchone()
    if not row:
        return web.json_response({"error": "Không tìm thấy tab"}, status=404)

    data = await request.json()
    name = (data.get("name") if data.get("name") is not None else row["name"]).strip() or row["name"]
    tokens_text = data.get("tokens_text") if data.get("tokens_text") is not None else row["tokens_text"]
    channels_text = data.get("channels_text") if data.get("channels_text") is not None else row["channels_text"]
    message_text = data.get("message_text") if data.get("message_text") is not None else row["message_text"]

    try:
        delay = max(0.0, float(data.get("delay") if data.get("delay") is not None else row["delay"]))
    except (TypeError, ValueError):
        return web.json_response({"error": "Delay phải là số hợp lệ"}, status=400)

    try:
        burst_count = max(1, int(data.get("burst_count") if data.get("burst_count") is not None else row["burst_count"]))
    except (TypeError, ValueError):
        return web.json_response({"error": "Số lần bắn mỗi đợt phải là số nguyên"}, status=400)

    db.execute(
        """
        UPDATE tabs
        SET name = ?, tokens_text = ?, channels_text = ?, delay = ?, burst_count = ?, message_text = ?
        WHERE id = ? AND user_id = ?
        """,
        (name, tokens_text, channels_text, delay, burst_count, message_text, tab_id, user["id"]),
    )
    db.commit()
    updated = db.execute("SELECT * FROM tabs WHERE id = ?", (tab_id,)).fetchone()
    return web.json_response({"tab": serialize_tab(updated, workers.get(tab_id))})


async def handle_start_tab(request: web.Request) -> web.Response:
    user = get_current_user(request)
    if not user:
        return web.json_response({"error": "Chưa đăng nhập"}, status=401)

    tab_id = int(request.match_info["id"])
    db: sqlite3.Connection = request.app["db"]
    workers: WorkerManager = request.app["workers"]
    row = db.execute(
        "SELECT * FROM tabs WHERE id = ? AND user_id = ?",
        (tab_id, user["id"]),
    ).fetchone()
    if not row:
        return web.json_response({"error": "Không tìm thấy tab"}, status=404)

    try:
        rt = workers.start(row)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)

    return web.json_response({"tab": serialize_tab(row, rt)})


async def handle_test_send(request: web.Request) -> web.Response:
    user = get_current_user(request)
    if not user:
        return web.json_response({"error": "Chưa đăng nhập"}, status=401)

    tab_id = int(request.match_info["id"])
    db: sqlite3.Connection = request.app["db"]
    row = db.execute(
        "SELECT * FROM tabs WHERE id = ? AND user_id = ?",
        (tab_id, user["id"]),
    ).fetchone()
    if not row:
        return web.json_response({"error": "Không tìm thấy tab"}, status=404)

    tokens = [x.strip() for x in row["tokens_text"].splitlines() if x.strip()]
    channels = [x.strip() for x in row["channels_text"].splitlines() if x.strip()]
    if not tokens:
        return web.json_response({"error": "Chưa nhập Token"}, status=400)
    if not channels:
        return web.json_response({"error": "Chưa nhập ID Channel"}, status=400)

    token = tokens[0]
    channel_id = channels[0]

    workers: WorkerManager = request.app["workers"]
    rt = workers.get(tab_id)

    client_info = random.choice(USER_AGENTS)
    headers = {
        "Authorization": token,
        "Content-Type": "application/json",
        "User-Agent": client_info["ua"],
        "Accept": "*/*",
        "Origin": "https://discord.com",
        "X-Discord-Locale": "vi-VN",
    }

    results = {}

    # Fetch channel info
    try:
        async with AsyncSession(impersonate="chrome", verify=False) as session:
            ch_res = await session.get(
                f"https://discord.com/api/v10/channels/{channel_id}",
                headers=headers,
                timeout=8,
            )
            if ch_res.status_code == 200:
                ch_data = ch_res.json()
                ch_name = ch_data.get("name") or ch_data.get("id", channel_id)
                guild_id = ch_data.get("guild_id", "DM")
                results["channel"] = f"#{ch_name} (server: {guild_id})"
                rt.add_log("info", f"[Thử] Kênh xác nhận: #{ch_name} | Server ID: {guild_id}")
            else:
                results["channel"] = f"Không lấy được tên kênh (mã {ch_res.status_code})"
                rt.add_log("warn", f"[Thử] Không lấy được tên kênh: {ch_res.status_code}")

            # Send plain test message
            payload = {
                "content": "✅ [TreoDis Test] Tin thử — nếu thấy dòng này kênh đúng rồi!",
                "tts": False,
                "nonce": generate_snowflake_nonce(),
                "flags": 0,
            }
            send_res = await session.post(
                f"https://discord.com/api/v10/channels/{channel_id}/messages",
                headers=headers,
                json=payload,
                timeout=8,
                impersonate="chrome",
            )
            results["send_status"] = send_res.status_code
            if send_res.status_code == 200:
                rt.add_log("ok", f"[Thử] Gửi tin test thành công vào kênh {channel_id} — kiểm tra Discord ngay")
                results["message"] = "Gửi thành công! Kiểm tra Discord ngay để xem tin có hiện không."
            elif send_res.status_code == 429:
                retry = send_res.json().get("retry_after", "?")
                rt.add_log("warn", f"[Thử] Rate limit 429, thử lại sau {retry}s")
                results["message"] = f"Rate limit 429, thử lại sau {retry}s"
            else:
                try:
                    err = send_res.json()
                except Exception:
                    err = {}
                rt.add_log("err", f"[Thử] Gửi lỗi mã {send_res.status_code}: {err.get('message','')}")
                results["message"] = f"Lỗi {send_res.status_code}: {err.get('message','Không rõ')}"
    except Exception as exc:
        results["message"] = f"Lỗi kết nối: {exc}"
        rt.add_log("err", f"[Thử] Lỗi kết nối: {exc}")

    return web.json_response(results)


async def handle_stop_tab(request: web.Request) -> web.Response:
    user = get_current_user(request)
    if not user:
        return web.json_response({"error": "Chưa đăng nhập"}, status=401)

    tab_id = int(request.match_info["id"])
    db: sqlite3.Connection = request.app["db"]
    workers: WorkerManager = request.app["workers"]
    row = db.execute(
        "SELECT * FROM tabs WHERE id = ? AND user_id = ?",
        (tab_id, user["id"]),
    ).fetchone()
    if not row:
        return web.json_response({"error": "Không tìm thấy tab"}, status=404)

    rt = await workers.stop(tab_id)
    return web.json_response({"tab": serialize_tab(row, rt)})


async def handle_delete_tab(request: web.Request) -> web.Response:
    user = get_current_user(request)
    if not user:
        return web.json_response({"error": "Chưa đăng nhập"}, status=401)

    tab_id = int(request.match_info["id"])
    db: sqlite3.Connection = request.app["db"]
    workers: WorkerManager = request.app["workers"]
    row = db.execute(
        "SELECT id FROM tabs WHERE id = ? AND user_id = ?",
        (tab_id, user["id"]),
    ).fetchone()
    if not row:
        return web.json_response({"error": "Không tìm thấy tab"}, status=404)

    await workers.stop(tab_id)
    workers.runtimes.pop(tab_id, None)
    db.execute("DELETE FROM tabs WHERE id = ? AND user_id = ?", (tab_id, user["id"]))
    db.commit()
    return web.json_response({"ok": True})


async def on_cleanup(app: web.Application) -> None:
    await app["workers"].stop_all()
    app["db"].close()


def create_app() -> web.Application:
    app = web.Application()
    app["db"] = init_db()
    app["workers"] = WorkerManager()
    app.on_cleanup.append(on_cleanup)

    app.router.add_get("/", handle_index)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/api/me", handle_me)
    app.router.add_post("/api/register", handle_register)
    app.router.add_post("/api/login", handle_login)
    app.router.add_post("/api/logout", handle_logout)
    app.router.add_get("/api/tabs", handle_list_tabs)
    app.router.add_post("/api/tabs", handle_create_tab)
    app.router.add_put("/api/tabs/{id:\\d+}", handle_update_tab)
    app.router.add_post("/api/tabs/{id:\\d+}/start", handle_start_tab)
    app.router.add_post("/api/tabs/{id:\\d+}/stop", handle_stop_tab)
    app.router.add_post("/api/tabs/{id:\\d+}/test", handle_test_send)
    app.router.add_delete("/api/tabs/{id:\\d+}", handle_delete_tab)
    app.router.add_static("/static", STATIC_DIR)
    return app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    web.run_app(create_app(), host="0.0.0.0", port=port)
