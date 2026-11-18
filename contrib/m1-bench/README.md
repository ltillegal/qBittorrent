# M1 benchmarks

Scripts used to produce the numbers in `M1-BUILD.md`.

- `bench-startup.sh APP [RUNS]` — time from exec to the "started" log line, plus idle RSS.
- `bench-tp.py SECONDS RUNS APP...` — download throughput from `nettop` per-process
  byte counters (immune to preallocation and disk cache), alternating builds
  inside each round. Torrent path via `QBT_TORRENT`.
- `bench-ui.py APP COUNTS SECONDS` — generates synthetic torrents, pre-fills a
  profile, then measures startup/CPU/RSS with a large list. Set
  `QBT_EXTRA_TORRENT` to add a real download on top.

They need macOS (uses `nettop`, `ps`, `du`), a built `qbittorrent.app`, and
`--confirm-legal-notice` support in the binary.
