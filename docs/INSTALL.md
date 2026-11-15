# Install and start creating

Target: TrimUI Brick Pro **TG4040** running **TrimUI's stock OS**, 1024×768, Linux ARM64. Check the model before installation. PocketLAB is an app inside the stock OS and requires it; it does not run on custom firmware or other operating systems. These instructions do not flash firmware. See [compatibility](COMPATIBILITY.md) and [validation status](VALIDATION.md) for tested versus pending behavior.

For agent-assisted setup, use the [copyable prompt in the README](../README.md#set-up-with-your-coding-agent). These tools run on your computer, with the card reader or USB cable connected to that computer.

The SD card is needed only to set up PocketLAB: installing, updating or recovering it, or preparing a new card. Making mini apps never uses the card reader. Leave the card in the Brick and connect the computer to the Brick's **bottom USB-C port** with a data cable; see [First app](#first-app).

## Choose a setup path

| Your card | What to do |
| --- | --- |
| Working stock card, first PocketLAB install | [Copy the device ZIP contents](#manual-installation-from-the-device-zip) or use guided setup |
| Working stock card, install or update from the source bundle | [Install or verify](#existing-working-card--preserves-contents) |
| Blank FAT32 card | [Prepare the card](#new-card) |
| Interrupted stock copy | [Resume preparation](#resume-an-interrupted-copy) |
| New card that needs formatting | [Format an explicitly selected card](#format-and-then-prepare-a-new-card) |
| Working stock card inside a powered-on Brick | [Install over USB](#first-installation-over-usb) |

Run `./pocketlab cards` to list mounted external cards. It shows each card's state and the one command that sets it up:

```sh
./pocketlab cards
# POCKETLAB (7.7 GB) at /Volumes/POCKETLAB
#   state: stock
#   next:  ./pocketlab setup --sd /Volumes/POCKETLAB --eject
```

For an interactive menu, open `Setup.command` on macOS or run `./pocketlab setup` in a terminal. It lists the same cards and suggests an action for each. Press Enter to select the only listed card, or use **m** to enter the mounted card path. After verification, you can choose to eject the card. Scripts and agents use `cards` and the explicit commands below.

On macOS, a terminal or agent app needs permission to read removable volumes. If a command reports "Operation not permitted", allow that app in System Settings → Privacy & Security → Files & Folders (Removable Volumes), or in Full Disk Access.

## Firmware and SD-card requirements

PocketLAB requires a TrimUI Brick Pro TG4040 running TrimUI's stock OS. It installs as an app inside that OS and opens from **Apps**. It does not replace the OS and does not run on custom firmware or alternative operating systems. PocketLAB has been tested on **stock firmware 1.1.1** (Settings → About). No minimum supported version has been established, so other releases may behave differently.

The official SD-base package `v1.0.0-20260626` supplies card contents for new-card preparation. Its version identifies that SD download; it is **not a verified minimum device-firmware version**. PocketLAB setup prepares card files and installs the app without updating or flashing device firmware. Do not upgrade or downgrade firmware solely to match the SD-base tag.

A blank card prepared with `prepare-card --new-card` has booted on a TG4040 and started PocketLAB. Startup rollback after a failed update has been tested on a computer but not on the Brick. Computer-side diagnostics and successful file verification do not establish firmware compatibility. See the [compatibility record](COMPATIBILITY.md#firmware-and-sd-base-versions) for the evidence available and the [known limitations](VALIDATION.md#known-limitations).

## Get the project

Clone the repository with `git clone https://github.com/saivishnu2299/pocketlab`, or extract its complete source ZIP. Keep all supplied files, including `runtime/`: that folder holds the prebuilt ARM64 PocketLAB app, so installation does not require compiling it. Run every `./pocketlab` command below from a terminal **inside the repository folder**. Paths in examples are placeholders; use your actual mounted card path and put it in quotes if it contains spaces.

If you only want the two included apps, the device ZIP is also suitable for a [first manual installation](#manual-installation-from-the-device-zip). It does not contain the computer-side setup tools or PocketLAB SDK. Use the complete source checkout when you want to create apps with an agent.

## Computer prerequisites

> **Note:** PocketLAB has only been tested on an Apple Silicon Mac. Intel macOS and Linux are configured but have not been tested on real machines, and Windows has no native setup tools. See [compatibility](COMPATIBILITY.md).

- **Python 3.9+** for card setup and **3.12+** for building mini apps. macOS includes Python 3.9; if `python3` is missing, run `xcode-select --install`. For app development on macOS, `brew install python` or the [Python installer](https://www.python.org/downloads/) provides 3.12+. On Linux, use your distribution's package. Check with `python3 --version`; installing a new Python does not help if your terminal still selects an older one.
- **ADB, for USB operations only:** install [Android SDK Platform Tools](https://developer.android.com/tools/releases/platform-tools) and make `adb` available in your terminal. On macOS with Homebrew: `brew install --cask android-platform-tools`. On Debian/Ubuntu: `sudo apt install adb`. Check with `adb version`.
- **A card reader and bsdtar, for new-card preparation:** bsdtar is included in macOS. Debian/Ubuntu: `sudo apt install libarchive-tools`. Check with `bsdtar --version`.
- **For desktop previews and repository tests only:** Clang, make, and SDL2 development files. macOS: install Xcode command-line tools with `xcode-select --install` if needed, plus `brew install sdl2`. Debian/Ubuntu: `sudo apt install clang make libsdl2-dev`. These are not prerequisites for installing PocketLAB or building ordinary ARM64 mini apps.

The PocketLAB SDK downloads its pinned compiler and SDL sources itself. You do not need a connected Brick, system cross compiler, Docker, or a device-library dump to build. First SDK setup needs Internet; cached builds work offline. The stock SD base is a separate approximately 400 MiB download for new cards only.

After installing Python, check the local tools and bundled runtime:

```sh
./pocketlab doctor
```

No card or device connection is needed for that check. It does not install prerequisites. To check a USB installation later, open PocketLAB on the Brick and use `./pocketlab doctor --usb`; before the first installation, an "Install PocketLAB first" result is expected.

## Existing working card — preserves contents

```sh
./pocketlab setup --sd /Volumes/TRIMUI
./pocketlab doctor --sd /Volumes/TRIMUI
```

Replace the mount path with yours. A working stock card has `Apps` and `Roms` directories. Setup verifies an identical PocketLAB installation without rewriting its files. If it finds a different runtime, it stages the changed files and retains a rollback copy of the previous runtime. Installed apps, saves, settings, and scores stay in place. This path skips the stock download.

Use `--eject` on the setup command to eject the card on macOS or unmount the selected volume on Linux. Safely remove the card, insert it into the powered-off Brick, and open **Apps → PocketLAB** after boot. After an update, this first launch completes the startup check. If setup reports a pending recovery, follow [the recovery steps](TROUBLESHOOTING.md).

### Manual installation from the device ZIP

For a first install on an already working stock card, download `PocketLAB-<version>-device.zip` from [Releases](https://github.com/saivishnu2299/pocketlab/releases), extract it, and copy its `Apps/PocketLab` folder into the card's existing `Apps` folder. The result must be `CARD/Apps/PocketLab/launch.sh`, with no extra archive-name folder in between. Safely eject, insert the card into the powered-off Brick, boot, and open **Apps → PocketLAB**. This copying route needs no Python or SDK.

If `Apps/PocketLab` is already present, use the preserving installer above for an update. Replacing the whole folder manually can discard saved data and your own apps.

## New card

A blank card needs the stock SD base as well as PocketLAB. Choose **Prepare new FAT32 card** in guided setup, or connect a blank FAT32 card through a reader and run the command below.

```sh
./pocketlab prepare-card --sd /Volumes/POCKETLAB --new-card
./pocketlab doctor --sd /Volumes/POCKETLAB
```

Setup obtains the pinned official TrimUI `v1.0.0-20260626` SD base from TrimUI, verifies it, and uses the local cache on later runs. The download is about 400 MiB. The extracted base takes about 1.6 GiB across 16,000 files. Setup shows separate copy and verification phases with file counts, bytes, throughput, and an estimate once it measures the rate. The total time depends on the card and reader. Keep the card connected until setup reports completion.

After setup, eject the card, insert it into the powered-off Brick, and open **Apps → PocketLAB**. You can also pass `--eject` to `prepare-card`.

### Resume an interrupted copy

Reconnect the same card and select **Resume card preparation** in guided setup, or rerun the original `prepare-card` command. You can also resume a saved setup with:

```sh
./pocketlab setup --sd /Volumes/POCKETLAB
```

Keep the hidden `.pocketlab-preparing` folder on the card. Setup checks the saved record, reuses completed files, and copies missing or incomplete files. Pressing Ctrl-C during preparation exits with status 130 and leaves the saved progress available.

For a partial stock copy made by an older installer or manually, explicitly select that card with:

```sh
./pocketlab prepare-card --sd /Volumes/POCKETLAB --resume
```

Use `--resume` explicitly for an older copy, even if the card already has `Apps` and `Roms`. Setup checks existing stock files before adding missing ones. If a file differs from the pinned base, it reports the path and preserves the existing file. Use the regular install path for a working stock card.

### Format and then prepare a new card

On macOS, the interactive `./pocketlab setup` menu's **f. Format a new card** option guides you through disk selection, erasure confirmation, and preparation. For an agent or an explicit command sequence, first list external physical disks:

```sh
diskutil list external physical
```

Identify the SD card by its size and device identity, then request a plan:

```sh
./pocketlab format-card --disk /dev/diskN
```

Substitute the actual whole **external SD disk**, such as `/dev/disk4`, for `/dev/diskN`. A disk identifier is not the same as a mounted volume path such as `/Volumes/POCKETLAB`. This command is a **plan only**: it reports the device identity, size, FAT32/MBR layout, and a disk-specific confirmation token.

Formatting erases all contents of that disk. Only after checking the plan and explicitly choosing erasure, repeat the command with `--confirm-erasure THE_DISPLAYED_TOKEN`, using the exact token from your plan. The tool resolves downloads and rechecks disk identity before running `diskutil`. No general install or repair command formats the card.

**Formatting alone does not install the stock SD base or PocketLAB.** After formatting succeeds, find the newly mounted volume (normally `/Volumes/POCKETLAB`) and run the `prepare-card` and `doctor --sd` commands above. The interactive menu combines these steps; the explicit `format-card` command does not.

On Linux, use your disk utility to format the selected new card as FAT32 with an MBR partition table, mount it, then use the same `prepare-card` command with its Linux mount path. Automatic raw-disk formatting on Linux is not implemented; native Windows setup is not supported. New cards are not considered hardware-validated merely because file verification passed.

## First installation over USB

With a prepared stock card in the powered-on Brick, connect a data cable to the **bottom USB-C port**, wake it, and keep the stock **USB Storage** app closed. After installing ADB, `adb devices` should show the Brick with state `device`. Run:

```sh
./pocketlab install --usb --confirm-model TG4040
```

Use `--confirm-model TG4040` only after checking the device model. The first installation checks stock TrimUI paths and ARM64 architecture; it does not infer TG4040 from ARM64 alone. Open **Apps → PocketLAB** on the Brick, then run `./pocketlab doctor --usb`. Subsequent installs verify the package identity and request a restart if PocketLAB is running. With multiple ADB devices, add `--serial DEVICE_ID` to each USB command. No custom ADB service is enabled.

## Check the installation on the Brick

1. Open **Apps → PocketLAB** and check the library. A fresh install has exactly **ESP32 detector** and **Starfall**. An update preserves any mini apps already installed.
2. Open each included app and use the physical controls. Follow the [device guide](DEVICE.md); a successful computer-side checksum check cannot establish that display, audio, input, or a connected board works on your hardware.
3. For development, keep PocketLAB open and USB Storage closed, with the computer connected to the bottom port. `./pocketlab doctor --usb` should report the connection and running controller as OK before you create your first app.

If something fails, use [troubleshooting](TROUBLESHOOTING.md). Reformatting is not an installation-repair step.

## First app

App development happens over USB, not through the SD card. Keep the card in the Brick, connect the computer to the Brick's **bottom USB-C port** with a data cable, open PocketLAB, and keep USB Storage closed.

```sh
./pocketlab doctor --usb
./pocketlab new miniapps/my-app --name "My app"
./pocketlab run miniapps/my-app --usb
```

This builds, transfers, and opens the generated starter. Edit `miniapps/my-app/app.c`, `app.json`, and artwork directly or ask your local agent. Then watch for source changes:

```sh
./pocketlab watch miniapps/my-app --usb
```

The first usable frame acknowledges readiness. **Ctrl-C** stops watching but leaves the app installed and running. Use `./pocketlab library --usb` to return. Unplug the computer and reopen the app from the library to test standalone operation and saved state. Use a different project folder for each additional app; `new` refuses to overwrite one that already exists. The [PocketLAB SDK guide](../SDK.md) explains app structure and lifecycle requirements.

The default library contains only ESP32 detector and Starfall until you install your own apps. Your coding agent runs on the computer; PocketLAB runs the resulting native mini app on the Brick. Remote AI services are optional features of individual apps, not required by PocketLAB.
