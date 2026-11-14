# PocketLAB on the Brick Pro

Open Apps → PocketLAB in the stock launcher. D-pad/left stick selects, A opens, B returns, X opens library settings, and Y opens the guide. B from the library asks before exiting. Menu/Home returns to the library or pauses gameplay.

## Install or update

For a first install on a working stock card, extract the device ZIP and copy its `Apps/PocketLab` folder into the card's existing `Apps` folder. Safely eject the card, insert it into the powered-off Brick, then boot and open **Apps → PocketLAB**.

To update an existing installation, prepare a blank card, or resume an interrupted copy, use the setup tools from https://github.com/saivishnu2299/pocketlab (`./pocketlab cards`, then the command it prints). The updater keeps installed mini apps and saves in place. After an update, open PocketLAB on the Brick to complete the startup check. See `docs/INSTALL.md` and `docs/TROUBLESHOOTING.md` in the source bundle for the commands and recovery steps.

## ESP32 detector

Connect a board with a data cable to the rear HOST USB-C port. Inventory refreshes automatically. L/R or D-pad switches boards. The bottom USB-C port connects the computer.

An ESP32 product descriptor, Espressif vendor, generic serial bridge, and ROM-verified identity are displayed distinctly. A bridge alone does not identify its attached microcontroller. A visible USB device may have no serial port if the stock driver is absent. Unrecognized devices may appear only in the other-device count.

A starts the optional chip-verification confirmation; A again consents. ROM synchronization/identity reads may reset the board or require BOOT/RESET. They do not write or erase flash. Actual ROM verification and compatibility with additional boards require hardware testing. Passive discovery never opens the board serial port.

## Starfall

| Control | Action |
| --- | --- |
| D-pad / left stick | Move |
| Hold A | Fire |
| X | Shield (2 seconds, 9-second recharge) |
| Start / B / Menu | Pause |
| A / Start while paused | Resume |
| B while paused | End flight and return |
| A after game over | Restart |
| L/R on title | Relaxed / Arcade / Expert |

Three lives, diving enemies, aimed shots, later armored enemies, hit streaks, synthesized sound, and separate high scores. Settings control sound and background motion. Scores save at game over, ending a flight, and normal exit; abrupt power loss can lose unsaved progress. Focus loss and long suspend pause gameplay.

## Data and removal

Settings, scores, logs, and app data live under Apps/PocketLab/data. Independent app packages live under Apps/PocketLab/apps. For updates, use the source-bundle installer to keep these directories in place. To uninstall, back up the apps and data you want to keep, then remove `Apps/PocketLab`. The OS, firmware, ROMs, and other applications remain separate.

If launch returns to the stock menu, inspect data/pocketlab.log and data/pocketlab.previous.log. The source release includes diagnostics and recovery instructions. No microphone, lighting, vibration, or additional sensor API is promised by this SDK.
