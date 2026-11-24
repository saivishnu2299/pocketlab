# PocketLAB for TrimUI Brick Pro

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/pocketlab-logo-white.svg">
  <img src="docs/images/pocketlab-logo-graphite.svg" alt="PocketLAB" width="420">
</picture>

**Create mini apps for your Brick Pro with your coding agent.**

An open source project by [OpusLABS](https://www.sainathkrishnamurthy.com/opuslabs/) · [PocketLAB project page](https://www.sainathkrishnamurthy.com/work/pocketlab/) · [Announcement on Substack](https://opuslabs.substack.com/p/i-built-pocketlab-to-vibe-code-my)

PocketLAB is an app library for the **TrimUI Brick Pro (TG4040)** running **TrimUI’s stock operating system**. Open it from **Apps → PocketLAB** to play **Starfall**, an offline space shooter, or use **ESP32 detector** to identify compatible USB boards. You can also describe a game or tool in plain language and have a coding agent build it on your computer and send it to the Brick.

![PocketLAB library showing ESP32 detector and Starfall](docs/images/library.png)

| I want to… | Start here |
| --- | --- |
| Install PocketLAB on the card I already use with my Brick Pro | [Copy one folder by hand](#set-up-yourself) or [ask a coding agent to install it](#set-up-with-your-coding-agent) |
| Start with a blank card, or keep the card in the Brick for setup | [Use the setup menu or install over USB](#setup-menu-and-other-install-options) |
| Make my own game or tool | [Make your own app](#make-your-own-app) after installing PocketLAB |
| Update an existing installation | [Update PocketLAB](#update-pocketlab) so your apps and saves stay in place |

## What you need

- **A TrimUI Brick Pro (TG4040) with its original TrimUI operating system.** Check the model before starting. PocketLAB has been tested on stock firmware **1.1.1**; other firmware versions are unverified. Other Brick models and custom firmware are outside the supported setup.
- **A microSD card.** Use the card your Brick already boots from for the quickest setup. To install from a computer, use a card reader or adapter, or follow the USB option below. PocketLAB installs under `Apps/PocketLab` and leaves your games, saves, other apps and firmware alone.
- **For making apps:** a Mac or Linux computer and a **USB-C cable that carries data**. A charging-only cable won’t work. The SDK has been tested on Apple Silicon Macs; Intel Macs and Linux are configured but unverified on real machines. On Windows, you can copy the app to a working card and use the included apps; there’s no native PocketLAB SDK for Windows. See [compatibility](docs/COMPATIBILITY.md).

## Set up yourself

**First install on a working card (Mac, Windows or Linux).** You can do this in Finder, File Explorer or your Linux file manager. You don’t need a coding agent or a terminal.

1. On the [GitHub Releases page](https://github.com/saivishnu2299/pocketlab/releases), open the latest release and download **`PocketLAB-…-device.zip`** from **Assets**. Unzip it. If you have the full project instead, the same app folder is inside `runtime/Apps/`.
2. Turn the Brick **completely off**, remove its microSD card and insert it into the computer. Open the card in your file manager. A working stock card has `Apps` and `Roms` folders. If yours is blank, go to [blank-card setup](#setup-menu-and-other-install-options).
3. Inside the unzipped download, open `Apps` and copy the **`PocketLab` folder** into the card’s existing **`Apps` folder**. To check the result, open `Apps → PocketLab` on the card and look for `launch.sh` directly inside. If the card already contains `Apps/PocketLab`, stop and use [the update instructions](#update-pocketlab). Replacing that folder by hand can remove installed mini apps and saves.

### Open PocketLAB on the Brick

If the card is still mounted on the computer, use **Eject** or **Safely Remove** before taking it out. Put the card back in the powered-off Brick, turn it on and open **Apps → PocketLAB**. A fresh install shows **ESP32 detector** and **Starfall**.

Use the **D-pad or left stick** to select an app, **A** to open it, and **B** to go back. In the library, **X** opens settings and **Y** opens the guide. Try Starfall first; you don’t need to connect anything. To use ESP32 detector, connect your board to the Brick’s rear **HOST** port. See the [device guide](docs/DEVICE.md) for app controls and USB board support.

## Set up with your coding agent

Use a coding agent that can run commands **on the computer with your card reader**. A web chat or a cloud-only agent can explain the steps but can’t reach the card. With the Brick off, put its card in your computer, then paste this:

```text
Set up PocketLAB on my TrimUI Brick Pro (TG4040). Get the project from
https://github.com/saivishnu2299/pocketlab and follow the setup steps in
AGENTS.md and skills/pocketlab-device/SKILL.md. Explain any steps I need
to do myself. Check which card is the Brick's before writing to it.
On a working card, install or update only Apps/PocketLab and preserve my
apps and saves. Ask before preparing a blank card. Do not format or
erase anything. Verify the install and let me know when I can put the
card back in the Brick and open Apps > PocketLAB.
```

The installer checks the copied files and can safely update an existing installation. If setup verifies the files but can’t eject the card, eject it in your file manager before removing it.

## Setup menu and other install options

The setup tools need **Python 3.9 or newer** on macOS or Linux. Download and unzip **`PocketLAB-…-source.zip`** from [Releases](https://github.com/saivishnu2299/pocketlab/releases), or clone the [PocketLAB project](https://github.com/saivishnu2299/pocketlab). If Python is missing, follow the [prerequisite instructions](docs/INSTALL.md#computer-prerequisites).

Run `./pocketlab` commands from the project folder that contains `AGENTS.md` and `pocketlab`. On a Mac, open Terminal, type `cd` followed by a space, drag that folder into the Terminal window and press **Enter**. On Linux, use **Open in Terminal** from the folder’s file manager menu if available.

- **Working card:** turn the Brick off and insert its card into the computer. On macOS, open `Setup.command` from the project folder. You can also run `./pocketlab setup` in a terminal on macOS or Linux. In the menu, select the card by name and size; it should say **Install or verify PocketLAB**. For setup without the menu, run `./pocketlab doctor` and `./pocketlab cards`, then copy the `next:` command printed for your card. Once the files are verified, [open PocketLAB on the Brick](#open-pocketlab-on-the-brick).
- **Blank card:** use [new-card setup](docs/INSTALL.md#new-card) on an empty FAT32 card. This downloads about 400 MiB of official TrimUI card files and copies about 1.6 GiB. A slow card can take about an hour; leave it connected until verification finishes. If interrupted, reconnect the same card and [resume the copy](docs/INSTALL.md#resume-an-interrupted-copy). Use the separate [formatting steps](docs/INSTALL.md#format-and-then-prepare-a-new-card) only for a card you mean to erase.
- **Card still in the Brick:** [install over USB](docs/INSTALL.md#first-installation-over-usb) if you already have a working stock card in a powered-on TG4040 and the USB tools on your computer. After the first install, open **Apps → PocketLAB** on the Brick.

## Make your own app

Start with something you can test in a minute: a tally counter, a study timer, a dice roller or a one-screen game. You can ask a local coding agent to write the code. It runs on your computer; the finished mini app runs on the Brick and can work unplugged. An app that uses an online service still needs a network for that feature.

### Get ready to build

1. **Open the full PocketLAB project on your computer.** Use the [source ZIP or a Git clone](#setup-menu-and-other-install-options). If you used the device ZIP to install PocketLAB, leave the Brick as it is and get the source separately. The device ZIP contains the ready-to-run library; the full project contains the PocketLAB SDK, which builds new apps.
2. **Install Python 3.12 or newer and ADB.** ADB is the tool your computer uses to send builds over USB. Ask your agent to check `python3 --version` and `adb version` in its terminal, or follow the [computer setup steps](docs/INSTALL.md#computer-prerequisites). The first build needs internet to download the compiler and its files. Later builds can reuse the download and work offline.
3. **Connect the Brick.** Leave the SD card inside. Plug the data cable into the **bottom USB-C port**, wake the Brick, and open **Apps → PocketLAB**. Keep the stock **USB Storage** app closed. The rear **HOST** port is for accessories.

### Describe your idea to an agent

Open the full PocketLAB project folder in your local coding agent and paste this example. Change the name, what the app does, and the controls to match your idea:

```text
Make me a PocketLAB mini app called Study Timer. Show a large countdown
that starts at 25 minutes. Before starting, let me change the duration
with the D-pad. A starts or pauses, and B returns to the library. Remember
my last chosen duration. Put the controls on screen and give it a cover.

Read AGENTS.md, SDK.md and skills/pocketlab-miniapp/SKILL.md. Use a new,
unused folder under miniapps/ and leave the PocketLAB library alone.
Check my USB connection, then build, install and open the app on my Brick.
Tell me how to try it, and explain any steps I need to do myself.
```

To revise it, ask the agent to open the **same** project and run it again. For example: “Change Study Timer so X resets the countdown, put that on the screen, and send the update to my Brick.” Keeping the same project folder keeps the app’s identity and saved data. For a different app, use a new folder name that isn’t already used on the Brick.

### Try the starter or build by hand

From the full PocketLAB project folder on your computer, run these commands one at a time. If you already have an app with the `first-counter` ID on your Brick, substitute a new folder name in the commands so you don’t replace it.

```sh
./pocketlab doctor --usb
./pocketlab new miniapps/first-counter --name "First Counter"
./pocketlab run miniapps/first-counter --usb
```

`doctor` checks the USB connection and whether PocketLAB is running. Check for **OK** next to `usb` and `controller`, and make sure the reported Python version is **3.12 or newer**. `new` creates a working counter and its library cover; `run` builds, transfers and opens it. On the Brick, press **A** a few times, then **B** to return to the library. Unplug the computer, reopen **First Counter**, and check that the number you counted is still there.

Edit `app.c` for what the app does, `app.json` for its library name and description, or `cover.bmp` for its picture. Run the same `run` command after each edit, or use `./pocketlab watch miniapps/first-counter --usb` to rebuild and reopen it automatically when you save. Press **Ctrl+C** in the terminal to stop watching; the app stays installed. The [PocketLAB SDK guide](SDK.md) explains controller buttons, artwork, saving, and how to build without the Brick connected.

**Before calling your own app finished:** try its buttons, check that text is readable, listen if it plays sound, and test any accessory it needs. Return to the library, unplug the cable, reopen the app and check that what you saved is still there. Seeing the first screen confirms it opened; these checks tell you whether it works the way you intended.

**Back up your work.** The `miniapps/` folder on your computer holds the editable projects. Git ignores your projects there, so keep a separate backup of anything you want to keep. The Brick’s card holds the installed copies and their saves under `Apps/PocketLab`; those are separate from the editable projects.

## Update PocketLAB

- **Downloaded a ZIP?** On macOS or Linux, download and extract the **new source ZIP**, then use its [setup menu](#setup-menu-and-other-install-options) with your working card, or use its [USB installer](docs/INSTALL.md#first-installation-over-usb). Copy any projects you want to keep working on from the old `miniapps/` folder into the new one, or keep them in a separate folder.
- **Cloned the project with Git?** Run one of the commands below from your clone. The updater pulls the latest project files first and stops if you’ve edited PocketLAB’s own files. Projects in `miniapps/` are kept.

```sh
./pocketlab update --sd "/Volumes/YOUR_CARD" --eject
./pocketlab update --usb --confirm-model TG4040
```

For the first command, replace `/Volumes/YOUR_CARD` with the actual card path printed by `./pocketlab cards`. For the second, leave the card in the powered-on Brick, use the bottom USB-C port and confirm the model is TG4040 before running it.

The installer keeps your installed apps, saves and scores and retains a backup of the previous PocketLAB version. **Open PocketLAB on the Brick once after updating** to finish the startup check. If an update was interrupted or PocketLAB won’t open, follow the [recovery steps](docs/TROUBLESHOOTING.md) to check or restore the installation.

If you decide to remove PocketLAB, see [how to back up your data and uninstall](docs/DEVICE.md#data-and-removal).

## If you get stuck

| What you see | What to try |
| --- | --- |
| PocketLAB doesn’t show up under **Apps** | Check that `launch.sh` is directly inside `Apps/PocketLab` on the card, then safely eject it and start the Brick with the card inserted. |
| The card is missing from setup, or macOS says **Operation not permitted** | Check whether it appears in your file manager. On macOS, allow your Terminal or agent app to read **Removable Volumes** in **System Settings → Privacy & Security → Files & Folders**. See [card troubleshooting](docs/TROUBLESHOOTING.md). |
| The Brick isn’t found over USB | Try a cable you know can transfer files, use the **bottom port**, wake the Brick, close USB Storage and open PocketLAB. Run `./pocketlab doctor --usb` again. |
| Your app won’t build or open | Copy the error into your coding agent, or see [build and launch troubleshooting](docs/TROUBLESHOOTING.md). If the USB reply was lost, check `./pocketlab status --usb` before retrying. |

See the [validation record](docs/VALIDATION.md) for what has been tested. If you still need help, [report an issue](https://github.com/saivishnu2299/pocketlab/issues) with your Brick model, firmware, computer OS and the error you saw. Remove personal paths, device serial numbers and saved app data from any logs you share. Report security problems privately as described in [SECURITY.md](SECURITY.md).

## Agent skills (optional)

The prompts above work without installing skills. The project includes two guides an agent can read: [pocketlab-device](skills/pocketlab-device/SKILL.md) for setup, updates and recovery, and [pocketlab-miniapp](skills/pocketlab-miniapp/SKILL.md) for creating and running apps. Install them if you want your agent to find them even when you start in a different folder.

<details>
<summary>Link the skills for Claude Code or Codex</summary>

Run the two lines for your agent from the full PocketLAB project folder. Linking keeps the skills tied to this folder so future project updates also refresh the skills.

```sh
# Claude Code
mkdir -p ~/.claude/skills
ln -s "$PWD/skills/pocketlab-device" "$PWD/skills/pocketlab-miniapp" ~/.claude/skills/

# Codex
mkdir -p ~/.agents/skills
ln -s "$PWD/skills/pocketlab-device" "$PWD/skills/pocketlab-miniapp" ~/.agents/skills/
```

Start a new agent session after linking. If you move the project, recreate the links. For other agents, use the personal skills folder named in their documentation.

</details>

## Develop PocketLAB itself

See [CONTRIBUTING](CONTRIBUTING.md) for building and testing the library and [RELEASING](docs/RELEASING.md) for making release bundles.

Copyright (c) 2026 PocketLAB contributors. PocketLAB is licensed under the [GNU Affero General Public License, version 3 only](LICENSE) (`AGPL-3.0-only`). Fonts and third-party components keep their own notices in [THIRD_PARTY.md](THIRD_PARTY.md). The artwork and sound are original. PocketLAB is an independent project and is not affiliated with TrimUI, which provides the stock OS and SD base.
