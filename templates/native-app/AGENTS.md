# Building this PocketLAB mini app

This is an independent native C/SDL2 app for stock TrimUI Brick Pro Linux ARM64.
Its visual design is yours to change. Keep its folder ID stable to preserve data.

- Read SDK.md in the PocketLAB SDK checkout (ask for its location if unavailable). Build from that checkout with its
  `python3 tools/pocketlab.py run /absolute/path/to/this-app --usb` command.
- Use `watch` in place of `run` for automatic build/upload/relaunch on edits.
  The SDK manages its native compiler. Do not introduce Docker, containers,
  firmware changes, web frameworks, or extra runtimes for ordinary mini apps.
- Edit app.c, add more .c/.h files or assets, and update app.json. All .c files
  outside hidden/build/data folders compile automatically with the SDK helpers.
- Keep the generated cover.bmp or replace it with representative artwork for the
  library card (480×192 standard BMP recommended). Existing artwork is preserved
  by build/deploy; missing artwork is generated offline from the app ID and name.
- Keep `"ready": "file"` and call pocketlab_ready() after the first usable frame.
- Handle SIGTERM by setting a flag, then save/clean up in the main loop. Keep
  persistent state in POCKETLAB_APP_DATA; checkpoint it during use.
- Support D-pad/stick and A/B/X/Y as appropriate. B/Menu/Home should return to
  the library. Handle USB insertion/removal and never assume a fixed serial path.
- Use a defined board protocol for peripherals. Passive USB detection does not
  prove board firmware or protocol compatibility. No automatic reset or flashing.
- No on-device AI inference. A cloud-backed app must handle unavailable networks.
- A successful build is not device proof: check the USB readiness reply, logs,
  and actual controls/display when changing hardware-facing behavior.
