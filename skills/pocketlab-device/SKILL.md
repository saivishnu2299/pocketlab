---
name: pocketlab-device
description: Install, update, check or recover PocketLAB on a TrimUI Brick Pro (TG4040) running TrimUI's stock OS, using the SD card in a card reader or a USB connection. Use when the user asks to set up, install, update, upgrade, verify, repair or roll back PocketLAB, prepare an SD card for it, or reports a card, USB or startup problem with it. Not for creating or running mini apps; use pocketlab-miniapp for that.
---

# PocketLAB device setup, update and recovery

PocketLAB is an app inside TrimUI's stock OS on the Brick Pro TG4040. It installs only into `Apps/PocketLab` on the SD card. This skill routes the request to the right commands. The rules live in the PocketLAB checkout and change between releases, so read them there every time.

## 1. Find the checkout and load the current rules

1. You need a terminal on the computer that has the card reader or the USB cable. A cloud agent without that access should stop and point the user to a local agent or the README's "Set up yourself" section.
2. Find the PocketLAB checkout: a folder containing `pocketlab`, `AGENTS.md` and `tools/pocketlab.py`. Check the current folder and its parents first, then ask the user. If there is none, run `git clone https://github.com/saivishnu2299/pocketlab`. Run every `./pocketlab` command from the checkout root.
3. If the checkout's `skills/pocketlab-device/SKILL.md` differs from this copy, stop reading this one and follow the checkout's copy. Your copy may come from an older PocketLAB.
4. Read the "Setting up a user's Brick" and "Safety rules" sections of the checkout's `AGENTS.md`. Where they disagree with this skill, they win.

Explain each step to the user in plain language. Keep their games, saves and other apps untouched.

## 2. Pick the task

| The user wants to | Go to |
| --- | --- |
| Install PocketLAB for the first time, or set up a new card | Section 3 |
| Get the latest PocketLAB on their computer and Brick | Section 4 |
| Find out why something doesn't work | Section 5 |
| Finish an interrupted update or go back to an earlier version | Section 6 |

## 3. Set up

Follow the steps in the "Setting up a user's Brick" section of `AGENTS.md` in order. In short:

1. `./pocketlab doctor`
2. `./pocketlab cards` (add `--json` to parse it). If no card or several cards are listed, or the state is `unreadable`, do what `AGENTS.md` says for that case.
3. Run the `next` command that `cards` printed for the chosen card. Two states need the user first:
   - `blank`: explain the download and copy size and the time it can take, and get their go-ahead before running it.
   - `not-a-trimui-card`: stop and ask. Never format or erase a card as part of setup.
4. USB alternative, for a working stock card inside a powered-on Brick connected with ADB: get the user to confirm the model is a Brick Pro TG4040, then run `./pocketlab install --usb --confirm-model TG4040`.

Then report the result (section 7).

## 4. Update

`./pocketlab update` runs `git pull --ff-only` on the checkout and then installs the new PocketLAB on the Brick. It keeps installed mini apps, saves, and app projects in `miniapps/`.

1. Choose the route with the user:
   - Card in this computer's reader: run `./pocketlab cards` first and check the card's state. Run `./pocketlab update --sd CARD --eject` only for `stock-with-pocketlab`. For `stock`, PocketLAB isn't installed yet: tell the user this is a first install and get their go-ahead before running it. For any other state, don't run `update`. `unfinished-preparation` means an earlier new-card setup was interrupted, and continuing it writes stock TrimUI files to the card. Explain that and follow section 3, which has the checks for each state.
   - Brick connected over USB with PocketLAB open: get the user to confirm the model is TG4040, then `./pocketlab update --usb --confirm-model TG4040`.
   - Computer only, Brick later: `./pocketlab update` pulls and prints the commands to run when the Brick is available.
2. If `update` stops because tracked PocketLAB files have local edits, show the user the listed files and ask what to do. Never stash, reset, discard or commit those edits without their permission. App projects in `miniapps/` never cause this.
3. If the folder is not a git clone (for example an extracted source ZIP), `update` can't pull and says so. Ask the user to download the latest source ZIP from the Releases page and extract it into a new folder. From that folder, `./pocketlab setup --sd CARD --eject` or `./pocketlab install --usb --confirm-model TG4040` updates the Brick directly, after the same card-state and model checks. Their app projects stay in the old folder. Copy them into the new `miniapps/` only if the user wants that, and never overwrite or delete their app folders. Mention that a git clone lets future updates use `./pocketlab update`.
4. After a successful pull, `AGENTS.md`, `SDK.md` and these skills may have changed. Read the checkout's copies again before doing anything else.
5. The first launch of PocketLAB on the Brick finishes a startup check. If the new version fails to start, it rolls back on its own.

## 5. Diagnose

- `./pocketlab doctor` checks the computer and the bundled runtime. `./pocketlab doctor --sd CARD` checks a card in the reader. `./pocketlab doctor --usb` checks a connected Brick with PocketLAB open. Add `--json` to parse the output.
- Look up the reported problem in `docs/TROUBLESHOOTING.md` and follow its suggested action.
- Report the error and that action to the user. Don't retry with more destructive variations, and never reformat a card to fix an installation.

## 6. Recover

- Interrupted shell update: `./pocketlab recover --sd CARD` with the card in a reader, or `./pocketlab recover --usb` over USB. Both use the recorded backup.
- Go back to an earlier version: `./pocketlab backups --sd CARD` lists backups. Let the user choose one, then run `./pocketlab recover --sd CARD --backup NAME`. Recovery keeps current apps and saves.
- Free space: `./pocketlab backups --sd CARD --prune --keep 2` removes older backups. Run it only after the user agrees and the current version works on the Brick.

## Always

- Never format or erase a card unless the user explicitly chooses to erase that particular new or disposable card. If they do, follow the formatting rule in `AGENTS.md` exactly, including the disk-specific confirmation.
- Never flash firmware, alter emulators or stock apps, or enable new debug services.
- Only pass `--confirm-model TG4040` after the user confirms the model.
- If macOS reports "Operation not permitted", ask the user to allow removable-volume access for the app running you. Don't work around it.

## 7. Report and hand off

- Quote the verification lines from the output, such as "Installed and SHA-256 verified", "updated and verified" or "already installed and verified". If `--eject` reports the card is still in use, setup still succeeded; ask the user to eject it in their file manager.
- Give the physical steps that match the route used:
  - SD card: with the Brick powered off, insert the card, turn the Brick on and open **Apps → PocketLAB**.
  - USB: open, or close and reopen, **Apps → PocketLAB** on the Brick. Don't mention the card.
  - Computer only: nothing changed on the Brick yet. Give the commands `update` printed, for later.
- A fresh install shows **ESP32 detector** and **Starfall**; an update also keeps the user's mini apps. After an update, the first launch finishes the startup check.
- Offer the next step: making a mini app over USB with pocketlab-miniapp. Otherwise leave the card and device alone.
