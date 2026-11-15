---
name: pocketlab-miniapp
description: Create, change, build and run PocketLAB mini apps, the native C/SDL2 apps that run on a TrimUI Brick Pro (TG4040), and send them to the Brick over USB. Use when the user wants to make a new app, game, tool or instrument for their Brick or PocketLAB, change an existing mini app, or build, run, watch, preview or debug one. Not for installing, updating or recovering PocketLAB itself; use pocketlab-device for that.
---

# PocketLAB mini apps

A mini app is a native C/SDL2 program that PocketLAB launches on the Brick. You build it on the user's computer with the PocketLAB SDK and send it to the Brick over USB. The SD card stays in the Brick.

This skill is the workflow. The rules live in the PocketLAB checkout and change between releases, so read them there every time.

## 1. Find the checkout and load the current rules

1. Find the PocketLAB checkout: a folder containing `pocketlab`, `AGENTS.md`, `SDK.md` and `tools/pocketlab.py`. Check the current folder and its parents first. Otherwise ask the user where their clone is. If they have none, clone it with `git clone https://github.com/saivishnu2299/pocketlab`. Run every `./pocketlab` command from the checkout root, even when the app lives elsewhere.
2. If the checkout's `skills/pocketlab-miniapp/SKILL.md` differs from this copy, stop reading this one and follow the checkout's copy. Your copy may come from an older PocketLAB.
3. Read the checkout's `SDK.md` (the app contract) and the "Making mini apps" and "Safety rules" sections of `AGENTS.md`. For an existing app, also read the `AGENTS.md` inside the app folder. Where those files disagree with this skill, they win.

## 2. Agree on the app

- Get a name and a short description of what it does and how it is controlled. Choose sensible defaults instead of asking about small details.
- Choose a stable ID: 1–48 lowercase letters, digits or hyphens, starting with a letter, and not `esp32` or `starfall`. The project folder's name is the ID. The ID keeps the app's saved data across updates, so never rename it later.
- A new app needs an unused ID. Installing replaces any app on the Brick that has the same ID, including its code, and the new app would inherit that app's saved data. Check that no project folder already uses the ID. With the Brick connected, `adb shell ls /mnt/SDCARD/Apps/PocketLab/apps` lists the installed IDs (add `-s SERIAL` when several devices are connected). If the ID is taken, choose another one, or ask the user whether they meant to change that existing app.
- Put the project in `miniapps/ID` inside the checkout (git ignores it) or in a folder outside the checkout. Don't put it anywhere else in the checkout.

## 3. Create or open the project

- New app: `./pocketlab new miniapps/ID --name "NAME"`. It writes a working starter with `app.c`, `app.json`, `launch.sh`, `cover.bmp` and an `AGENTS.md`. It refuses to overwrite an existing folder. For a new app, treat that as a taken ID and go back to section 2. Never delete or replace an existing project to make room.
- Existing app: work in its folder only when the user asked to change that app.
- Edit only the app's own folder. Don't change the shell, `templates/`, `runtime/` or any other tracked PocketLAB file to make an app work. Local edits to tracked files make `./pocketlab update` stop, and they drift from the public release. If an app truly needs an SDK change, tell the user instead.

## 4. Build it to the contract

Keep these points from `SDK.md` while writing the app:

- `app.json` declares `"ready": "file"`. Call `pocketlab_ready()` right after the first successful `SDL_RenderPresent`.
- SIGTERM and SIGINT set a `volatile sig_atomic_t` flag. The main loop notices it, saves, releases audio, input and display, and exits 0. Don't do file or SDL work inside the handler.
- Save state only in `POCKETLAB_APP_DATA`. Write important files to a temporary file, flush and rename, and checkpoint during use.
- B, Menu or Home returns to the library. Use the controller mapping in `SDK.md`, add analog dead zones, and handle controller and USB peripheral disconnects.
- The app owns its look: the shell palette is optional. Keep the generated `cover.bmp` or replace it with representative 480×192 BMP artwork. Metadata is printable ASCII.
- No on-device AI inference. Any network feature must keep working when the network is unavailable.
- For USB peripherals, passive discovery only. Never reset a board automatically and never write flash. Probing needs an explicit, confirmed action on the app screen.

## 5. Build, preview or run it

Match the request. Install the app on the Brick only when the user wants it running there. If they asked only to build, compile-check or preview, use only step 4 below and don't touch the Brick.

1. To run on the Brick, ask the user to connect a data cable to the Brick's **bottom** USB-C port, open PocketLAB on the Brick, and close the stock USB Storage app. Then run `./pocketlab doctor --usb`. Building needs Python 3.12+ and ADB; `doctor` names anything missing.
2. Build, upload and open the app in one step: `./pocketlab run PATH --usb`. For live iteration, `./pocketlab watch PATH --usb` rebuilds and reopens it on every save; Ctrl-C stops watching and leaves the app installed.
3. Useful commands: `./pocketlab status --usb` (running app and readiness), `./pocketlab logs --usb` (launcher log), `./pocketlab open ID --usb`, `./pocketlab library --usb` (back to the library).
4. Build only, with no Brick and no ADB needed: `./pocketlab build-app PATH` checks the ARM64 build. For a desktop preview, `./pocketlab build-app PATH --host` builds a host binary instead; rebuild without `--host` before deploying (`run` does this for you).

When something fails:

- A failed build keeps the previous binary and installed app. Fix the source and run again.
- If the app misses readiness, check that `pocketlab_ready()` is called after the first frame and that `app.json` declares `"ready": "file"`.
- If a USB reply is lost, check `status` and `logs` before retrying, because the operation may have finished.
- See `docs/TROUBLESHOOTING.md` for the other cases.

## 6. Hand off

- Report only what actually happened. After a local build or preview, say that it built (or ran on the computer) and was not installed on the Brick. After `run` or `watch`, say whether the Brick reported the app ready. Don't call it tested beyond that.
- List what the user must check on the Brick, now or once they install it: each control the app uses, the display, sound, saving and reloading after a relaunch, returning to the library, and any peripheral. Builds and readiness checks don't prove physical controls, SDL hardware behavior, USB drivers or peripherals.
- Remind them that their app sources are not in PocketLAB's git history. Suggest a separate repository or backup for apps they want to keep.

## Apps and PocketLAB updates

Updating PocketLAB leaves installed mini apps, their saves and the projects in `miniapps/` in place. After an update, check the app against the current `SDK.md` before you next change it, and rebuild it with `run` when you do. Use pocketlab-device for the update itself.
