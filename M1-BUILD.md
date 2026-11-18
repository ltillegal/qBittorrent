# Native Apple Silicon build (M1 / macOS Sequoia)

Personal build of qBittorrent 5.3.0, tuned for an Apple Silicon Mac. Not
affiliated with the upstream project; keep it to yourself and review any change
before using it for anything important.

## What is different

| Area | Change |
| --- | --- |
| Build | `-O3 -flto -DNDEBUG -mcpu=apple-m1`, Ninja, arm64 only |
| Background | `NSAppSleepDisabled` + `NSDisableAutomaticTermination` in `dist/mac/Info.plist`, so App Nap stops throttling timers and network callbacks |
| Sleep / network change | `ReannounceWhenAddressChanged` default flipped to `true`; after sleep or a Wi-Fi/ethernet switch the external address changes and libtorrent otherwise keeps announcing the stale one |
| Disk I/O | `AsyncIOThreadsCount` 10 → 16, `CoalesceReadWrite` also on macOS, `PieceExtentAffinity` enabled |

## Building

```bash
brew install qt libtorrent-rasterbar boost ninja openssl@3 cmake

cmake -B build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_PREFIX_PATH="$(brew --prefix qt);$(brew --prefix libtorrent-rasterbar);$(brew --prefix openssl@3)" \
  -DOpenSSL_DIR="$(brew --prefix openssl@3)/lib/cmake/OpenSSL" \
  -DCMAKE_CXX_FLAGS_RELEASE="-O3 -DNDEBUG -mcpu=apple-m1" \
  -DCMAKE_C_FLAGS_RELEASE="-O3 -DNDEBUG -mcpu=apple-m1" \
  -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=ON
cmake --build build --parallel "$(sysctl -n hw.ncpu)"
```

Two traps:

1. If `/usr/local` holds an Intel Homebrew, CMake picks the x86_64 `libcrypto` /
   `libssl` from there and the link fails. Point `OpenSSL_DIR` at the arm64
   `openssl@3` explicitly (as above).
2. Run `macdeployqt` **after every relink**, otherwise the binary keeps rpaths
   to Homebrew Qt while the bundle also contains a copy, and the app aborts with
   two Qt copies loaded:

   ```bash
   "$(brew --prefix qt)/bin/macdeployqt" build/qbittorrent.app -always-overwrite -libpath="$(brew --prefix)/lib"
   ```

## Measurements

Same machine, fresh profile per run, Ubuntu 24.04.3 ISO torrent (legal, well
seeded), 3 samples of the startup and 2 interleaved rounds of the download test
per build.

| Build | Startup (median) | RSS idle | Download (median) | RSS during download |
| --- | --- | --- | --- | --- |
| Official 5.2.3 (universal) | 0.36 s | 57 MB | 32.4 MB/s | 628–745 MB |
| This build, no tuning (first compile) | 0.58 s | 115 MB | — | — |
| This build, M1 tune | 0.46 s | 71 MB | 33.7 MB/s | 159–165 MB |

Notes:

- Download throughput is within noise of the official build: on this line the
  link, not the client, is the limit.
- Memory during a download is ~4× lower (≈160 MB vs ≈700 MB). Part of that is
  likely 5.3.0 itself, not only the tuning.
- Startup is 0.1 s slower than the official 5.2.3 binary, which is built with a
  different Qt release; comparing against the same code compiled without the
  flags (0.58 s → 0.46 s, 115 MB → 71 MB) is the meaningful delta.

## Packaging

```bash
codesign --force --deep --sign - build/qbittorrent.app
mkdir -p dist/staging && cp -R build/qbittorrent.app dist/staging/
ln -s /Applications dist/staging/Applications
hdiutil create -volname "qBittorrent" -srcfolder dist/staging -ov -format UDZO dist/qBittorrent-m1.dmg
```

Ad-hoc signed, not notarized: first launch needs right-click → Open, or
`xattr -dr com.apple.quarantine /Applications/qbittorrent.app`.
