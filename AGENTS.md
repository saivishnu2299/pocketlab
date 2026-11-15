# Working on PocketLAB

PocketLAB is an app inside TrimUI's stock OS on the TrimUI Brick Pro TG4040 (Linux ARM64, 1024×768). It requires that stock OS and does not run on custom firmware. It installs only into `Apps/PocketLab` on the SD card. Run every `./pocketlab` command from the repository root on the user's computer.

## Setting up a user's Brick

Follow these steps when a user asks you to set up PocketLAB, for example with the README prompt. Tell the user what you are doing in plain language, and keep their games, saves and other apps untouched.

1. **Get the repository.** If you are not already inside it, run `git clone https://github.com/saivishnu2299/pocketlab` and `cd pocketlab`. You need a terminal on the computer that has the card reader. If you are a cloud agent without that access, tell the user to run a local agent or follow the README's "Set up yourself" section.
2. **Check the computer:** run `./pocketlab doctor`. Card setup needs Python 3.9+, which macOS includes. If `python3` is missing, ask the user to install it: on macOS run `xcode-select --install`, on Linux use the distribution's package. Nothing else is needed for card setup.
3. **Find the card:** run `./pocketlab cards`. Add `--json` if you want to parse the output.
   - If no card is listed, ask the user to power off the Brick, take out its SD card and insert it into this computer, then run `cards` again.
   - If more than one card is listed, ask the user which one belongs to the Brick, using the label and size.
   - On macOS, if the state is `unreadable` or a command fails with "Operation not permitted", the app running you lacks permission to use removable volumes. Ask the user to allow it in System Settings → Privacy & Security → Files & Folders (Removable Volumes), or in Full Disk Access, and then retry. Do not work around this permission.
4. **Run the `next` command that `cards` printed for the chosen card:**
   - `stock`, `stock-with-pocketlab` or `unfinished-preparation`: run `./pocketlab setup --sd CARD --eject`. It installs, updates, verifies or resumes. It writes only to `Apps/PocketLab`, or to its own preparation folder. On a working Brick Pro card, keep every existing file as it is.
   - `blank`: confirm with the user first. Explain that setup downloads the official TrimUI SD base (about 400 MiB) and copies about 1.6 GiB in 16,000 files. On a slow card this can take up to an hour, and it resumes if interrupted. Then run `./pocketlab prepare-card --sd CARD --new-card --eject`.
   - `not-a-trimui-card`: stop and ask the user. Never format or erase a card as part of setup. See the formatting rule below.
5. **Report the result.** If `--eject` reports that the computer is still using the card, setup itself has succeeded; ask the user to eject the card in their file manager. Quote the verification lines from the output, such as "Installed and SHA-256 verified", "updated and verified" or "already installed and verified". If the command failed, report the error and its suggested action; `docs/TROUBLESHOOTING.md` covers the common cases. Do not retry destructive variations.
6. **Give the user the physical steps:** with the Brick powered off, insert the card. Turn the Brick on and open **Apps → PocketLAB**. The library shows **ESP32 detector** and **Starfall**. After an update, the first launch finishes a startup check and rolls back on its own if the new version fails to start.
7. **Offer the next step:** creating a first mini app over USB, as described in the next section. Leave the user's card and device alone unless they ask for more.

The Brick does not need to be connected for card setup. With a working stock card inside a powered-on Brick that is connected over USB with ADB, `./pocketlab install --usb --confirm-model TG4040` is an alternative. Use it only after the user confirms the model is a Brick Pro TG4040.

## Making mini apps

- The SD card is only for setting up PocketLAB. App development goes over USB, with the card left in the Brick. App building needs Python 3.12+, ADB and a data cable in the Brick's **bottom** USB-C port, with PocketLAB open and the stock USB Storage app closed. Use the rear HOST port for peripherals. Check with `./pocketlab doctor --usb`.
- Use `./pocketlab new miniapps/ID --name NAME`, then edit that project's sources, assets and `app.json`. Projects may live outside this repository. Keep the stable ID. Never edit the shell to satisfy an ordinary new-app request.
- Use `run PATH --usb` or `watch PATH --usb`. The SDK manages its own pinned compiler; do not add Docker, a VM or an extra device runtime.
- Every app declares `"ready":"file"`, calls `pocketlab_ready()` after its first usable frame, handles SIGTERM gracefully and saves in `POCKETLAB_APP_DATA`. Keep or replace `cover.bmp` with representative artwork.
- Mini apps own their design. No on-device AI inference. Remote services belong to individual apps and must handle unavailable networks.
- Passive USB discovery never resets a board. Bridge identity does not prove chip identity. ROM probing requires an explicit action on the app screen and must never write flash.
- Build and readiness checks do not prove that physical controls, SDL hardware behavior, USB drivers or peripherals work. Tell the user what to check on the actual Brick.

## Safety rules

- Preserve existing card contents, mini apps, app data and scores. Never format a card in response to a general setup request or an installation failure.
- Formatting has one exception: the user explicitly chooses to erase a particular new or disposable SD card. First run `format-card --disk DEVICE` to get a plan and show that exact disk identity. Then get the disk-specific erasure confirmation. Never infer it, and never reuse it after a device change. Formatting alone installs nothing; follow it with `prepare-card --sd PATH --new-card`. Use `--resume` explicitly for an older interrupted stock copy.
- Never flash firmware, alter emulators or stock apps, or enable new debug services.
- For interrupted updates and backups, use `recover` and `backups` (see `docs/TROUBLESHOOTING.md`). Never erase a card to recover the shell.

## Maintaining the release

- Public naming: the project is PocketLAB, at https://github.com/saivishnu2299/pocketlab. The README title is "PocketLAB for TrimUI Brick Pro", the development tools and documentation are the "PocketLAB SDK", and the tagline is "Create mini apps for your Brick Pro with your coding agent." Keep executable names, API identifiers and installed paths (`Apps/PocketLab`, `org.pocketlab.shell`, `POCKETLAB_*`) unchanged.
- Preserve the frozen shell source, assets, fonts and UI (`tests/baseline/ui-source.json`). Intentional baseline changes require an explicit request. Only ESP32 detector and Starfall are installed by default; the template is source-only. The Apps-screen icon is generated by `tools/icon_art.py`.
- Use `make host`, `make test`, `make brick` and `make renders`, then `python3 tools/release.py runtime` and `make check`. See `docs/RELEASING.md`. The builder checks ARM runtime dependencies and GLIBC versions.
- Never include user app files under `miniapps/` (only its README.md is public), `data/`, `build/`, local logs, caches, credentials, device identifiers or workstation paths in public artifacts. `release-files.txt` is an exact source allowlist.
- Do not publish, push, tag or deploy to real hardware unless explicitly requested. CI produces artifacts only.
