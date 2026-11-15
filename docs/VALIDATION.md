# Validation record

This file records what has been checked on real hardware, what has only been checked on a computer, and what is still untested. A passing desktop preview, CI run or file verification is not proof that something works on the Brick, so hardware results are listed separately.

## Current status

| Area | Status |
| --- | --- |
| SD-card setup on macOS (Apple Silicon) | Verified on a real 7.7 GB card from a clean copy of the source ZIP, with only macOS's bundled Python 3.9: first install, update, rollback, blank-card preparation, interrupt and resume, and eject. Hashing every file on the card showed that only PocketLAB's own files changed. |
| Boot on the Brick | Verified on a TG4040 running stock firmware **1.1.1** (Linux 4.9.191, SDL 2.30.8). A blank card prepared by `prepare-card --new-card` booted, and PocketLAB 1.1.0 started at 1024×768 and exited cleanly. |
| Apps-screen icon | Verified on the Brick: one icon, after the double-icon fix of 14 November 2026. |
| ESP32 detector and Starfall | Both worked on the Brick from an earlier card on 11 November 2026. Earlier development testing covered the controls, display, Starfall gameplay and audio, and passive ESP32 detection. The app code is frozen and has not changed since. |
| Mini apps over USB (`run`, `watch`) | Verified with the original development build. Not yet repeated from the public repository. |
| Linux and Intel macOS hosts | Configured, with pinned toolchains and a CI workflow for macOS and Ubuntu. Not yet run on real machines. |
| Windows | No setup tools. Install by copying the device ZIP by hand. |

## Known limitations

These are untested or unsupported. Reports from real devices are welcome; see [Reporting results](#reporting-results).

- **Firmware coverage.** Only stock firmware 1.1.1 has been tested. No minimum supported version has been established, and other stock releases may behave differently.
- **Power loss during an update.** Interrupted copies, startup rollback and recovery are covered by automated tests, FAT32 disk images and a card-reader `recover` run on a real card. Losing power on the Brick during the first launch after an update has not been tried.
- **Device edge cases.** Suspend and resume, a full or read-only card, and low-space warnings have not been exercised on the Brick.
- **USB deployment failures.** Cable disconnects and other ADB failures during `run` or `watch` are covered by mocked tests only.
- **ESP32 boards.** Passive detection was checked with the boards available during development. The optional chip check, and boards or USB bridges beyond those, are unverified. A recognised USB bridge does not prove which chip is attached.
- **Cards and formatting.** One 7.7 GB card has been tested. The `format-card` helper is macOS only and has formatted that one card.
- **Other hosts.** Linux and Intel macOS setup has not been run outside CI configuration.

## Reporting results

Open an issue with the PocketLAB version, the Brick's firmware version (Settings → About), your computer's OS, the command you ran and its output. Remove personal paths, serial numbers and app data first. Say what you checked on the Brick itself and what you only checked on the computer.

## Test history

The shell source, assets, fonts, and bundled vendor header are frozen in tests/baseline/ui-source.json. The public-name change to PocketLAB intentionally updates branding strings in main.c and control.c and the corresponding render baselines; app logic, assets, and controls remain unchanged. Only ESP32 detector and Starfall are default apps. No personal projects or their data belong to this release.

Local preparation completed on 10 November 2026. Prior development-device observations apply to the original shell, not automatically to new provisioning/recovery tools.

### Initial preparation checks (before the PocketLAB name change)

- Environment: macOS 27.2.1 arm64, Python 3.15.2, Apple Clang 21.0.0, native SDL 2.32.10. ARM builds use pinned Zig 0.14.1 and SDL 2.26.1 headers.
- At initial preparation, the 21 source/asset/vendor files matched their original SHA-256 baseline byte-for-byte. The shell implementation and default app artwork were not rewritten.
- Native core tests passed under AddressSanitizer/UndefinedBehaviorSanitizer, including 180,000 deterministic game-simulation frames.
- Eight USB/probe integration tests, six deployment tests, four controller lifecycle tests, and 32 release/setup/recovery/backup tests passed. Library artwork decoding, fallback, generated artwork, and custom-cover preservation checks also passed.
- Thirteen UI render comparisons passed. Twelve compare complete images pixel-for-pixel with the original renders; the empty-detector comparison normalizes only the test-inventory annotation added by the existing test mode and uses a fixed inventory matching the reference. Documentation images are native render fixtures, not device photographs.
- The SDK generated an app outside the checkout, compiled its native preview, acknowledged the first frame, exited on SIGTERM, reopened a nonzero saved counter, built multiple C files for ARM64, retained the prior binary after a deliberate compilation error, and preserved its cover artwork.
- A clean extraction of the source archive passed diagnostics, tests, renders, SDK smoke checks, and an ARM build using fresh downloads with no device-library cache. Its ARM executable was byte-identical to the initial bundled executable (superseded by the branding rebuild): `f1837042a2038d7cbfa931a95a00ab405923d40f4b149031bcd4f425c2fa7e29`.
- ARM inspection found only libSDL2-2.0.so.0, libm.so.6, libpthread.so.0, libc.so.6, and GLIBC_2.17 requirements. The generated SDL import library is never installed or included in release archives.
- The official stock-base archive matched its pinned SHA-256. Extraction and a temporary-directory card simulation verified 15,927 stock files, installation, and an update preserving synthetic user app/data files. No physical card was used.
- Shell recovery fixtures covered successful startup, failed startup, interrupted copying, corrupt-backup rejection, first installation without a controller, and concurrent installer refusal. Card-reader recovery and selective backup pruning were tested against temporary trees.
- Source/device archive inventories, checksums, runtime provenance, private-path checks, Git-index export integrity, and executable permissions were checked. User projects, build caches, vendor SD contents, saved data, and local logs are excluded from public artifacts.
- No real-device deployment, card formatting, or firmware operation was performed in this round.

### PocketLAB naming update — 10 November 2026

- Public folder, documentation, launcher label, UI wordmarks, messages, template labels, and release archive names now use PocketLAB. The installed `Apps/PocketLab` path, backup names, package ID, commands, and environment variables are preserved for upgrade/data compatibility.
- Only branding strings changed in the shell source. All 13 before/after render comparisons matched outside the name regions; the game, pause, and game-over images were completely unchanged. The approved baselines and three documentation screenshots were updated for this requested rename.
- The ARM rebuild, full `make test` suite, all 13 approved render comparisons, and SDK lifecycle/build smoke test passed locally. The rebuilt runtime SHA-256 is `95ee93e4ae16357991de97a238b01f4bd8dff11e9a43df691f5ee7633e0cb890`.
- Fresh-cache archive validation above describes the initial build, not a repeat of that procedure for this branding rebuild.

### Physical SD-card setup — 11 November 2026

- The first real format-plan attempt exposed a macOS property mismatch: diskutil reports WholeDisk, while the helper checked Whole. The helper now checks WholeDisk; regression coverage accepts an external whole disk and still rejects a non-whole disk. All 12 setup tests and seven release tests passed.
- Explicitly authorized formatting of one approximately 7.7 GB external USB SD card completed through `format-card`. The resulting card was verified as FAT32 with an MBR partition table and the POCKETLAB volume label.
- The interrupted stock copy was completed while preserving existing files. PocketLAB and the added files passed checksums, and the maintainer confirmed that PocketLAB and both included apps worked on the Brick.

### Faster setup and resume — 12 November 2026

- Guided setup detected the connected FAT32 card. The installed runtime verified in about 0.4 seconds. A before-and-after check confirmed that the installed files, saved settings and neighboring app files examined on the card retained their hashes and modification times.
- With the same cached stock package on disposable macOS FAT32 disk images, complete preparation took about 64 seconds with the revised installer and 98 seconds with the previous installer. These are disk-image timings.
- On a disposable macOS FAT32 disk image, setup resumed after an interrupt and remount. It reused the staged files, verified the rest, and installed PocketLAB. A separate read of the finished volume matched all 15,927 stock file hashes.
- The eject option unmounted a FAT32 image after install, and diagnostics verified the installed files after reattaching it.
- A runtime update on a populated FAT32 image preserved a test mini app and a 16 MiB save. Both the host recovery command and the generated launcher recovery script restored the previous runtime and preserved the same files.
- The rebuilt ARM64 binary matched the bundled runtime byte-for-byte. The host tests, including 24 card-workflow regression tests, the SDK smoke test, and 13 render comparisons passed. The card-workflow tests also passed from a clean extraction of the source ZIP. The revised fresh-card flow has been tested at the filesystem level and still needs a boot test on a physical Brick.

### Public source SD-card test — 14 November 2026

Every step ran from a fresh extraction of the public source ZIP. Only macOS's bundled Python 3.9.6 was available (`PATH=/usr/bin:/bin:/usr/sbin:/sbin`), and there was no download or compiler cache. The hardware was one real 7.7 GB SD card in a USB reader. The commands were the ones in the AGENTS.md setup playbook: `doctor`, `cards`, then the printed `setup` or `prepare-card` command.

- **Update of an existing install:** a user app, a 2 MB save and a settings file were planted beside an older runtime. `setup --sd` staged the three changed runtime files (icon, device guide, manifest) in 19 seconds and kept a rollback backup. A hash comparison of all 32,791 files on the card found only those three files changed, plus their macOS metadata companions. The only additions were the backup and the pending-startup record under `data/`. Repeating `setup` only verified.
- **Recovery:** `backups` listed the update. `recover --sd` restored the previous runtime, confirmed by the old icon hash, and a further `setup` updated it again. The user app, save and settings kept their hashes throughout.
- **First install on a stock card:** with `Apps/PocketLab` removed, `cards` reported `stock`, and `setup --sd` installed and verified the runtime. Copying the device ZIP's `Apps/PocketLab` folder by hand also passed `doctor --sd` and a verify-only `setup`.
- **Blank card:** the `format-card` plan identified the USB card, and the confirmed format produced a FAT32/MBR `POCKETLAB` volume. The official SD base downloaded fresh from TrimUI's GitHub release (399.2 MiB at about 60–80 MiB/s) and matched its pinned SHA-256. `prepare-card --new-card` copied 15,927 files (1,639 MiB) and read them back. On this card, writes ran at 0.6–1.8 MiB/s, so the whole preparation took about 40 minutes; earlier disk-image timings do not represent slow cards.
- **Bug found and fixed:** in that run, the stock files and PocketLAB were already in place and verified when the final cleanup crashed with `No such file or directory: '._stock'`. That left the preparation folder behind and returned exit status 1. On FAT, macOS deletes each AppleDouble companion (`._NAME`) together with its file, and Python 3.9–3.12 `rmtree` treats the vanished entry as an error. Card-side tree removal now tolerates it, and a regression test covers it.
- **Interrupt and resume:** a SIGINT during resume exited with status 130 and kept the saved progress. `cards` then reported `unfinished-preparation`, and `setup --sd` with the fixed code finished in under 2 minutes with exit status 0, removing the preparation folder.
- **Independent check:** after unmounting and remounting to drop caches, all 15,927 stock files matched the official manifest. The only other files on the card were the 15 PocketLAB runtime files.
- **macOS metadata:** macOS adds `._NAME` companions to files written on FAT. PocketLAB now removes them for its own runtime files, backups and preparation folder, which left zero in `Apps/PocketLab` after install, update and recovery. It leaves them beside stock files: removing them ran at about 5 files per second on this card, and the previous card, which had 16,845 of them, worked on the Brick.
- **Final one-shot run:** with the final code, `format-card` followed by `prepare-card --new-card` finished with exit status 0 in 41 minutes. It left no preparation folder and no macOS metadata in `Apps/PocketLab`. After a cold remount, 15,927/15,927 stock files and 14/14 runtime files matched, and there were no unexpected files. `cards` then reported `stock-with-pocketlab 1.1.0`.
- **Eject:** the first `setup --sd … --eject` was blocked by Spotlight (`mds`), which was indexing the freshly mounted card, and setup exited with status 1 even though everything was verified. Eject now retries for about 16 seconds and otherwise prints a non-fatal file-manager instruction. With that change, the playbook's `setup --sd /Volumes/POCKETLAB --eject` verified the card and ejected it on the first attempt (exit status 0).

### Brick boot test and icon fix — 14 November 2026

- The card prepared by the final one-shot run booted on a TG4040 running stock firmware 1.1.1. The device log on the card shows that PocketLAB 1.1.0 started at 1024×768 with the `opengles2` renderer and exited with status 0.
- The Apps screen showed two overlapping PocketLAB icons. Cause: `config.json` set `icon.png` as both `icontop` and `icon`, and the stock launcher draws `icon` as a second, larger layer. Every stock app and emulator config on the card sets `icontop` and leaves `"icon": ""`. The fix uses the same convention, and `release.py` now rejects a runtime that sets both fields.
- The rebuilt ARM64 binary was byte-identical. `make test` (66 tests) and `make check` passed. `setup --sd /Volumes/POCKETLAB` staged two changed files (`config.json` and the manifest) with a rollback backup. A comparison of all 32,767 files before and after showed only those two files changed; the only additions were the backup and the pending-startup record under `data/`.
- On the Brick, the Apps screen then showed a single PocketLAB icon.

## Scope of the automated tests

No real card formatting, device installation, or firmware operation is performed by the automated tests. They use temporary directories and mocked disk and transport commands.
