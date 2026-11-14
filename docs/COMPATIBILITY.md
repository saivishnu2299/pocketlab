# Compatibility

| Component | Scope |
| --- | --- |
| Device | Stock TrimUI Brick Pro TG4040, ARM64 Linux, 1024×768 |
| Original shell | Prior device validation recorded controls/display, Starfall audio/gameplay, passive ESP32 detection, app launch/watch/readiness; app behavior/artwork retained; public branding updated to PocketLAB |
| Working-card setup | Install, verify, update, recovery and preservation of user files tested on a real SD card from a clean public checkout with macOS's bundled Python 3.9 (14 November 2026). An earlier card ran PocketLAB and both included apps on the Brick. |
| Preparation, resume, and rollback | Blank-card format, fresh SD-base download, preparation, interruption and resume tested on a real SD card (about 40 minutes on a slow card), plus disposable FAT32 images. Boot from this card and startup rollback on a physical Brick are pending. |
| macOS Apple Silicon | Host used for builds, tests, and the connected-card setup check |
| macOS Intel | Pinned toolchain configured; fresh-machine execution pending |
| Linux ARM64 / x86-64 | Pinned toolchains and portable build/test commands configured; CI defines Linux tests, execution must be verified |
| Windows | No native SDK/setup support in this release; copy the device ZIP manually. Not advertised as tested through WSL |
| Python | Card setup and diagnostics: 3.9+ (tested with macOS's bundled 3.9.6 and 3.15). Mini-app builds and repository tests: 3.12+ |
| New-card format | Explicit macOS FAT32/MBR helper; completed on one external SD card, with other hosts/cards unverified |
| New-card base | Full pinned official TG4040 SD base for blank cards. The installer skips the stock download on working cards. |
| Runtime | Stock SDL2, libc, libm, pthread; GLIBC requirements no newer than 2.17 |
| Additional hardware | Only interfaces actually implemented/tested by each app; no inference from connector presence |

## Firmware and SD-base versions

**No minimum supported firmware version or complete tested firmware-version matrix has been established.** Stock TG4040 firmware is the target, not a claim that every stock release has been validated.

| Version or requirement | What it establishes |
| --- | --- |
| Stock TrimUI Brick Pro TG4040 firmware | Intended device environment; exact supported release versions remain unverified |
| SD-base package `v1.0.0-20260626` | The pinned official card-content download used by new-card setup; not a verified minimum firmware version |
| Linux 4.9.191 and SDL runtime 2.30.8 | Versions recorded during prior original-shell device validation; they do not identify a complete supported firmware release matrix |
| SDL 2.26.1 headers and GLIBC_2.17 build requirements | Build/dependency constraints; not proof of compatibility with a particular firmware release |

PocketLAB setup does not update or flash device firmware. Do not upgrade or downgrade firmware merely to match the SD-base package tag. A verified download, successful copy, or passing desktop preview cannot establish that a firmware/card combination boots and works on the Brick.

Before publication, record the actual stock firmware release identifier, SD-base version, host platform, and results of the [physical acceptance checklist](VALIDATION.md#required-physical-acceptance-before-publication). Include fresh-card boot, first installation, app deployment, and update/recovery results. Only mark combinations as supported after those checks pass; leave untested versions explicitly unverified.

Do not claim support for other TrimUI models, alternative firmware, every ESP32 board/bridge, or arbitrary web applications.
