#!/usr/bin/env python3
"""Стресс-тест списка торрентов в qBittorrent.

    ./bench-ui.py APP COUNT SECONDS [RUNS]

Генерирует COUNT синтетических .torrent (валидный bencode, без пиров),
первым запуском добавляет их в профиль, затем измеряет:
  * время старта до строки «запущен» в логе;
  * RSS и CPU в простое на списке из COUNT торрентов.
"""
import os
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
import time


def bencode(value) -> bytes:
    if isinstance(value, int):
        return b"i" + str(value).encode() + b"e"
    if isinstance(value, bytes):
        return str(len(value)).encode() + b":" + value
    if isinstance(value, str):
        return bencode(value.encode())
    if isinstance(value, list):
        return b"l" + b"".join(bencode(v) for v in value) + b"e"
    if isinstance(value, dict):
        out = b"d"
        for k in sorted(value):
            out += bencode(k) + bencode(value[k])
        return out + b"e"
    raise TypeError(type(value))


def make_torrents(count: int, directory: str) -> list[str]:
    os.makedirs(directory, exist_ok=True)
    paths = []
    for i in range(count):
        name = f"seed{i:05d}.bin"
        info = {
            "length": 1024 * 1024,
            "name": name,
            "piece length": 16384,
            "pieces": b"\x00" * 20,
        }
        data = {
            "announce": "http://127.0.0.1:1/announce",
            "info": info,
        }
        path = os.path.join(directory, f"{i:05d}.torrent")
        with open(path, "wb") as fh:
            fh.write(bencode(data))
        paths.append(path)
    return paths


def read_start_time(log_path: str, start_wall: float) -> float | None:
    if not os.path.exists(log_path):
        return None
    with open(log_path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    if "запущен" not in text and "started" not in text:
        return None
    return time.time() - start_wall


def launch(binary: str, profile: str, save: str, torrents: list[str], wait_log: bool,
           timeout: float = 120) -> tuple[subprocess.Popen, float | None]:
    log = os.path.join(profile, "qBittorrent", "data", "logs", "qbittorrent.log")
    start = time.time()
    args = [binary, f"--profile={profile}", "--confirm-legal-notice",
            f"--save-path={save}", "--skip-dialog=true"] + torrents
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not wait_log:
        return proc, None
    deadline = time.time() + timeout
    while time.time() < deadline:
        t = read_start_time(log, start)
        if t is not None:
            return proc, t
        if proc.poll() is not None:
            return proc, None
        time.sleep(0.05)
    return proc, None


def stop(proc: subprocess.Popen) -> None:
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()


def sample(pid: int, seconds: int) -> tuple[list[float], list[float]]:
    cpu, rss = [], []
    for _ in range(seconds):
        time.sleep(1)
        out = subprocess.run(["ps", "-o", "rss=,%cpu=", "-p", str(pid)],
                             capture_output=True, text=True).stdout.split()
        if len(out) == 2:
            rss.append(int(out[0]) / 1024)
            cpu.append(float(out[1]))
    return cpu, rss


def run(app: str, count: int, seconds: int) -> dict | None:
    binary = os.path.join(app, "Contents", "MacOS", "qbittorrent")
    profile = tempfile.mkdtemp(prefix="qbtui.")
    save = os.path.join(profile, "dl")
    os.makedirs(save, exist_ok=True)
    torrents = make_torrents(count, os.path.join(profile, "torrents")) if count else []

    try:
        # 1) наполняем профиль
        if torrents:
            proc, _ = launch(binary, profile, save, torrents, wait_log=False)
            time.sleep(25)          # дать добавить и записать resume-данные
            stop(proc)
            time.sleep(2)

        # 2) замер старта с уже загруженным списком
        extra = [os.environ["QBT_EXTRA_TORRENT"]] if os.environ.get("QBT_EXTRA_TORRENT") else []
        proc, startup = launch(binary, profile, save, extra, wait_log=True)
        if proc.poll() is not None:
            return None
        time.sleep(3)
        cpu, rss = sample(proc.pid, seconds)
        stop(proc)
        return {"startup": startup, "cpu": cpu, "rss": rss}
    finally:
        shutil.rmtree(profile, ignore_errors=True)


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        return 1
    app = sys.argv[1]
    counts = [int(x) for x in sys.argv[2].split(",")]
    seconds = int(sys.argv[3])
    label = "официальная" if app.startswith("/Applications") else "наша M1"

    for count in counts:
        r = run(app, count, seconds)
        if not r:
            print(f"{label} {count} торрентов: не стартовало")
            continue
        print(f"{label} {count:5d} торрентов: старт {r['startup']:.2f} с | "
              f"CPU idle {statistics.median(r['cpu']):.1f}% (max {max(r['cpu']):.1f}) | "
              f"RSS {statistics.median(r['rss']):.0f} МБ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
