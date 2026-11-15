# Security policy

## Reporting a vulnerability

Please report security problems privately through GitHub: open the repository's **Security** tab and choose **Report a vulnerability**. Do not open a public issue for them.

Include the PocketLAB version, the Brick's firmware version (Settings → About), your computer's OS, and the steps that show the problem. Leave out personal paths, serial numbers, saved data and anything else you would not want to share.

PocketLAB is maintained by volunteers, so there is no guaranteed response time. Reports are acknowledged as soon as possible, and fixes go into a new release with credit, if you want it.

## Supported versions

Only the latest release receives fixes.

## Scope

In scope:

- The setup tools that write to SD cards (`setup`, `prepare-card`, `format-card`, `recover`). For example, writing outside `Apps/PocketLab` or the preparation folder, or formatting without the disk-specific confirmation.
- Download and checksum verification of the pinned compiler, SDL headers and TrimUI SD base.
- USB deployment over ADB (`install --usb`, `run`, `watch`) and the shell's control interface on the Brick.
- The PocketLAB shell and the included apps.

Out of scope:

- The stock TrimUI firmware and its built-in ADB access. PocketLAB uses the stock ADB connection and does not enable new services.
- Mini apps written by other people. Each app is the responsibility of its author.
