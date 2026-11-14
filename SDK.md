# PocketLAB SDK

The development tools and app contract for creating native PocketLAB mini apps on the TrimUI Brick Pro.

Start with the [installation guide](docs/INSTALL.md). Run the commands in this guide from the repository folder on your computer; PocketLAB must be open on the Brick for app deployment over USB. For an agent-assisted first app, use the [README prompt](README.md#make-your-own-app).

Ordinary apps start with `./pocketlab new miniapps/my-app --name "My app"`. Edit the generated project, then use `./pocketlab run miniapps/my-app --usb` to build, transfer, and open it. The sections below describe the contract already demonstrated by that starter.

The public name is **PocketLAB**. The installed directory remains `Apps/PocketLab` for compatibility with existing installations and saved data. Commands (`./pocketlab`), package IDs, and `POCKETLAB_*` environment variables retain their existing names.

## App contract

Put a folder in `Apps/PocketLab/apps/<id>` containing `app.json` and `launch.sh`. The library currently displays up to 126 external apps, plus the two built-ins. IDs should be 1–48 lowercase letters, digits or hyphens, starting with a letter. Keep each ID stable to retain its data. Do not use `esp32` or `starfall`.

```json
{
  "name": "My instrument",
  "description": "What this tool does in one sentence.",
  "ready": "file"
}
```

Metadata in this release uses printable ASCII without quotes or backslashes inside strings. The display truncates long titles/descriptions cleanly. UTF-8 localization is not yet implemented. Other app assets can use any format your renderer supports.

### Library artwork

Every mini app has a visual identity in the main library. `new` creates `cover.bmp` automatically from the app's ID and name, entirely offline. Music, visual-art, block-building and instrument-panel names receive themed artwork; other projects receive a unique abstract cover. `build-app`, `run`, `watch` and `deploy-app` also create a cover when an older source package has none. Existing cover files are always preserved. Rename or replace the file yourself when you want new artwork after changing the app's name.

Replace `cover.bmp` with an original illustration or a representative app image for a more specific identity. The recommended canvas is **480×192** pixels. The shell accepts standard uncompressed 24-bit or 32-bit BMP images up to 1024×768 and 4 MiB; 32-bit bitfield BMP is also supported. The image is centered and cropped to the card's wide picture area. Keep text in the app name below the image. PNG, JPEG and SVG need conversion to BMP on the computer; the device requires no new image decoder or runtime. The fixed filename needs no manifest setting.

Older hand-installed apps and missing, unsupported or damaged images get deterministic artwork drawn by the shell. This fallback never writes to the app package or its data. Only the two visible covers occupy texture memory, and covers reload after app updates, library refreshes or returning from a mini app. The two built-in apps retain their own chip and spacecraft illustrations.

`launch.sh` runs with its working directory set to the app folder. Use quoted relative paths, for example:

```sh
#!/bin/sh
cd "$(dirname "$0")" || exit 1
exec ./app
```

Environment variables supplied by the shell:

| Variable | Meaning |
| --- | --- |
| `POCKETLAB_ROOT` | Absolute PocketLAB installation directory |
| `POCKETLAB_APP_DATA` | Writable persistent directory for this app's stable ID |
| `POCKETLAB_WIDTH` | Logical width, currently 1024 |
| `POCKETLAB_HEIGHT` | Logical height, currently 768 |
| `POCKETLAB_READY_FILE` | Atomic readiness acknowledgement file |
| `POCKETLAB_SESSION` | Unique ID for this process launch |

Save state in `POCKETLAB_APP_DATA`, not your code folder. Use write-temp, flush/fsync and rename for important state. Keep your own logs bounded. The shell releases graphics, audio and input before launching an external app, waits for it, then restores the library. Exit 0 for a normal return; a nonzero exit or signal shows a brief error notice. The library does not sandbox app code: install only code you intend to run.

Mini apps must implement their own B/Menu return behavior and clean up audio/input/display on exit. A crash should also release their process-owned descriptors. A USB library/relaunch command can stop a hung app; the shell first sends SIGTERM to its own child process group, waits up to three seconds, then uses SIGKILL if necessary. Forced termination cannot guarantee unsaved application state. Device sleep/shutdown remains the stock OS's responsibility.

## Install or update PocketLAB

Use `./pocketlab setup --sd CARD` with a mounted working card. An up-to-date runtime is verified in place. An update stages only changed runtime files and keeps a rollback copy, so installed mini apps and their data stay in their original directories. Open PocketLAB on the Brick after updating to complete the startup check. Use the [installation guide](docs/INSTALL.md#choose-a-setup-path) for blank cards and interrupted stock copies, and [troubleshooting](docs/TROUBLESHOOTING.md) for recovery.

## Direct USB development

Use `python3 tools/pocketlab.py run PATH --usb` for build/upload/open in one command, or `watch PATH --usb` for updates on source edits. `deploy-app PATH --usb` uploads an already-built package and automatically opens it. `open APP_ID --usb` opens an installed mini app; `library --usb` closes it and returns to PocketLAB. `status --usb` reports the active app, process ID, launch session and readiness; `logs --usb` reads the launcher log.

The USB installer also uses the bundled runtime. Open PocketLAB from Apps after first installation. Subsequent `install --usb` shell upgrades request a restart when PocketLAB is running and retain a runtime backup. See [troubleshooting](docs/TROUBLESHOOTING.md) for pending updates. Keep the stock USB Storage app closed during ADB use.

Include `app.h` and call `pocketlab_ready()` immediately after the first successful `SDL_RenderPresent`. Declare `"ready": "file"` in app.json. The shell waits up to eight seconds for the matching session before declaring startup failed and rolling back an update. Without this declaration, acknowledgement means only that the process survived 0.8 seconds; it does not claim a displayed frame.

Handle SIGTERM and SIGINT by setting a `volatile sig_atomic_t` flag. Let the render loop notice the flag, save state, close device descriptors, destroy graphics/audio and exit. Do not perform filesystem or SDL work inside a signal handler. The starter demonstrates this. Keep important state checkpointed during use because forced termination, crashes and power loss cannot guarantee an exit save.

Updates arrive in a hidden staging folder and are checksum-verified before the controller accepts an install request. App code is promoted only after the old process exits. Requests and replies use unique tokens; requests from a previous shell instance are rejected on restart. Commands are serialized on the device. The command channel is local files under the app's own data directory, accessed through existing ADB; it exposes no TCP listener and is not a security boundary against a computer that already has root ADB access.

## Optional C helpers

`src/ui.h` provides SDL2 drawing, bundled Barlow/IBM Plex typography, wrapping and single-line truncation. `src/usb.h` provides `usb_scan(NULL, &snapshot)` on Linux sysfs and on Mac IOKit. `UsbDevice` includes VID, PID, product, serial, driver, serial port, classification and an identity tied to the USB connection instance. The scan itself never opens the board serial port.

`esp_probe` is optional, blocking and potentially resets the board. Run it off the render thread, show clear consent and progress, and never call it automatically for arbitrary hardware. Prefer passive protocol discovery or a firmware-defined handshake for custom instruments. Runtime hot-plug support must handle disconnect and reopen, not assume `/dev/ttyUSB0` is always the same board.

The helper scanner is not a UART protocol implementation for arbitrary Arduino projects. To send commands or read measurements, the mini app and board firmware need an agreed baud rate and protocol. HID, MIDI and other USB classes need suitable host drivers and corresponding application support.

## Starter app build

`templates/native-app/app.c` is a working independent fullscreen app with an atomically checkpointed counter and a passive USB inventory count. It is a neutral scaffold, not an installed default app. Apps need not inherit the shell palette.

`python3 tools/pocketlab.py new PATH --name "My instrument"` creates a complete ready-to-edit app with metadata, automatic library artwork, launch script, readiness signalling, graceful shutdown, persistent state, controls, and instructions for a coding agent. It refuses to overwrite an existing folder.

`./pocketlab build-app PATH` cross-compiles the app's .c files (excluding hidden/build/data folders), plus optional drawing/USB helpers, with pinned Zig 0.14.1. Target: `aarch64-linux.4.9-gnu.2.17`. The first build downloads SHA-256-verified Zig and SDL 2.26.1 source/header archives. It generates a link-only SDL import library from the pinned upstream export table. This is not an SDL implementation and never goes onto the device; runtime calls resolve to stock libSDL2-2.0.so.0.

A clean build needs Internet and Python 3.12+, but no connected device or copied device library. Later builds use the local build/toolchain cache and can be offline. macOS and Linux ARM64/x86-64 compiler variants are configured; see docs/COMPATIBILITY.md for actual validation. ADB is needed only for USB operations. No Docker, VM, system cross compiler, or device runtime installation is required.

App folders may live outside the checkout. The ARM builder writes `PATH/app` atomically; compilation failures retain the prior executable. Apart from that executable, keep intermediate build artifacts outside the app folder. `app.c` supplies `main()`; extra .c/.h files may live in subfolders. Runtime dependencies and maximum GLIBC requirements are inspected. Use `run PATH --usb` to build/deploy/open together.

For a native desktop test, `build-app PATH --host` builds a host executable instead. It needs the [desktop preview prerequisites](docs/INSTALL.md#computer-prerequisites) and replaces `PATH/app`; always rebuild without `--host` before deploying to the Brick. `run PATH --usb` performs that ARM build for you. The deploy command rejects an `app` executable that is not ARM64 Linux ELF. To preview a newly generated app without connecting a Brick:

```sh
./pocketlab new miniapps/preview-app --name "Preview app"
./pocketlab build-app miniapps/preview-app --host
mkdir -p build/example-data
POCKETLAB_ROOT="$PWD" POCKETLAB_APP_DATA="$PWD/build/example-data" miniapps/preview-app/app
```

If you already have a project, skip `new` and substitute its path in the build and launch commands. Desktop preview is not proof of the Brick's physical controls or hardware behavior.

To build with Rust, Go, Python or another runtime, supply your own compatible ARM64 output and launch script. This release bundles no Python, Node, Lua, browser or model runtime. A browser-only React app cannot run unchanged. Keep native dependencies compatible with stock SDL2 and glibc; avoid shipping a replacement system libc or changing system library paths globally.

## Controller conventions

The initial profile follows the shared TG5040 TrimUI mapping: raw joystick buttons B=0, A=1, Y=2, X=3, L=4, R=5, Start=7, Menu=8, Home=15; D-pad is the hat and the left stick is axes 0/1. D-pad/stick, A/X and launcher controls were recorded as working during prior shell hardware validation; verify any additional controls used by your app. SDL joystick indices are not Linux evdev key codes. Include analog dead zones and support disconnect/reconnect.

## Practical agent request

> Read AGENTS.md and SDK.md. Use `new` to create a new independent PocketLAB mini app in miniapps/my-instrument. Give it its own visual style. Use the physical D-pad, A/B/X/Y and Menu controls, and handle peripheral disconnects. Persist data in POCKETLAB_APP_DATA. Do not change the shell design or firmware. Build for ARM64 with tools/pocketlab.py, run appropriate tests, and use run --usb or watch --usb to deploy and relaunch on the connected Brick. Handle SIGTERM gracefully and use the readiness handshake. Explain any dependency that needs a real-device check. No on-device AI inference.
