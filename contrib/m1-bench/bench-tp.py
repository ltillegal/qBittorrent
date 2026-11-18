#!/usr/bin/env python3
"""Скорость qBittorrent по счётчикам ядра (nettop), честный A/B.

    ./bench-tp.py SECONDS RUNS APP1 [APP2 ...]

Замеряет реальные принятые байты процесса (не диск, не внутренние счётчики),
поэтому на результат не влияют преаллокация, кэш и запись на SSD.
"""
import os
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
import time

TORRENT = os.environ.get("QBT_TORRENT", "/tmp/ubuntu.torrent")


def nettop_bytes(pid: int) -> int:
    out = subprocess.run(["nettop", "-P", "-x", "-J", "bytes_in", "-l", "1", "-p", str(pid)],
                         capture_output=True, text=True, timeout=15).stdout
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[1].startswith("qbittorrent."):
            try:
                return int(parts[-1])
            except ValueError:
                return 0
    return 0


def sample_series(pid: int, seconds: int) -> list[int]:
    out = subprocess.run(["nettop", "-P", "-x", "-J", "bytes_in", "-l", str(seconds), "-p", str(pid)],
                         capture_output=True, text=True, timeout=seconds + 30).stdout
    values = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[1].startswith("qbittorrent."):
            try:
                values.append(int(parts[-1]))
            except ValueError:
                pass
    return values


def one_run(app: str, seconds: int) -> dict | None:
    binary = os.path.join(app, "Contents", "MacOS", "qbittorrent")
    profile = tempfile.mkdtemp(prefix="qbttp.")
    save = os.path.join(profile, "dl")
    os.makedirs(save, exist_ok=True)

    proc = subprocess.Popen(
        [binary, f"--profile={profile}", "--confirm-legal-notice",
         f"--save-path={save}", "--skip-dialog=true", TORRENT],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    try:
        started = False
        for _ in range(60):
            time.sleep(1)
            if nettop_bytes(proc.pid) > 0:
                started = True
                break
        if not started:
            return None

        time.sleep(3)  # выйти на скорость
        series = sample_series(proc.pid, seconds + 1)
        if len(series) < 2:
            return None
        deltas = [(b - a) / 1024 / 1024 for a, b in zip(series, series[1:]) if b >= a]

        rss_out = subprocess.run(["ps", "-o", "rss=,%cpu=", "-p", str(proc.pid)],
                                 capture_output=True, text=True).stdout.split()
        rss = int(rss_out[0]) / 1024 if len(rss_out) == 2 else 0
        cpu = int(float(rss_out[1])) if len(rss_out) == 2 else 0
        return {"deltas": deltas, "rss": rss, "cpu": cpu}
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(profile, ignore_errors=True)


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        return 1
    seconds, runs = int(sys.argv[1]), int(sys.argv[2])
    apps = sys.argv[3:]

    results = {app: [] for app in apps}
    for i in range(1, runs + 1):
        for app in apps:                      # чередуем сборки внутри круга
            if app.startswith("/Applications"):
                label = "официальная"
            elif "/src-base/" in app:
                label = "базовая 5.3.0"
            else:
                label = "наша M1"
            r = one_run(app, seconds)
            if r is None:
                print(f"  круг {i} {label}: не начал качать")
                continue
            med = statistics.median(r["deltas"])
            results[app].append(med)
            print(f"  круг {i} {label}: median {med:.2f} МБ/с "
                  f"(min {min(r['deltas']):.2f}, max {max(r['deltas']):.2f}) | "
                  f"RSS {r['rss']:.0f} МБ | CPU {r['cpu']}%")

    print()
    for app in apps:
        vals = results[app]
        if app.startswith("/Applications"):
            label = "официальная 5.2.3"
        elif "/src-base/" in app:
            label = "базовая 5.3.0"
        else:
            label = "наша M1 5.3.0"
        if vals:
            print(f"{label}: median {statistics.median(vals):.2f} МБ/с "
                  f"(min {min(vals):.2f}, max {max(vals):.2f}, n={len(vals)})")
        else:
            print(f"{label}: нет данных")
    return 0


if __name__ == "__main__":
    sys.exit(main())
