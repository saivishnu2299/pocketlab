# Prepare a release locally

The project is **PocketLAB**, published at https://github.com/saivishnu2299/pocketlab. Keep the README title **PocketLAB for TrimUI Brick Pro**, the development-tool name **PocketLAB SDK**, and the tagline **Create mini apps for your Brick Pro with your coding agent.** Versioned release archives retain the `PocketLAB` prefix.

Publication is a separate human decision. No tool/workflow in this repository publishes, tags, pushes, or creates a remote repository.

1. Use a clean checkout on a supported host; install native test dependencies from [INSTALL.md](INSTALL.md).
2. Run `make test`, `make brick`, `make sdk-test`, and `make renders`. These operate locally and never deploy or format a card.
3. Run `python3 tools/release.py runtime` to regenerate the bundled runtime from build/pocketlab, packaging files, notices, and DEVICE.md. Verify VERSION matches the unchanged shell/controller version. Keep runtime in the public repository so a clone can install without compiling.
4. Update release-files.txt deliberately for public source additions/removals. It is an exact allowlist; build, dist, user apps under miniapps/, data, device dumps, and caches are excluded. Only miniapps/README.md is included to provide the app workspace in a fresh checkout. Runtime files are separately verified against their own complete manifest.
5. Run `make check`, then `python3 tools/release.py bundle`. Inspect both ZIP inventories and SHA256SUMS in dist/. Archive entry order, timestamps, and permissions are normalized.
6. Extract the source ZIP into a new folder. Run doctor, tests, and an ARM build without a device or private cache. Exercise install, verify, interrupt, resume, update, and recovery on a disposable FAT32 volume. Check that existing app and data hashes match after the update and recovery.
7. Verify the physical-device checklist in VALIDATION.md with an explicitly selected disposable card and supported Brick. Record firmware, host OS, device behavior, and limitations without serials, personal paths, or app data.
8. Review the [README](../README.md) and [installation guide](INSTALL.md) from a new user's perspective. Verify the documented commands against `./pocketlab --help` and each subcommand's `--help`; check relative links in the final source ZIP. Confirm that both ZIPs contain the device guide and that the source ZIP also contains the setup and recovery instructions. After publishing, try the README agent prompt (it names https://github.com/saivishnu2299/pocketlab) in a separate clean folder with a disposable card.
9. Only after all release gates pass, decide whether to publish. Update the README release-status notice, compatibility table, and validation record to match checks actually completed; add the chosen repository URL to issue/contact docs. Nothing about generating artifacts authorizes publication.

CI builds/test/renders on macOS and Linux and uploads workflow artifacts for review only. CI execution is not equivalent to a real Brick test. Do not describe a configured but unexecuted matrix entry as passing.

The frozen UI baseline is tests/baseline/ui-source.json. Changes to src, assets, or vendor require an explicit design/functionality change request; do not refresh it merely to make checks pass. The default apps must remain exactly esp32 and starfall. SDK scaffolding is not a third default app.

When `docs/DEVICE.md` changes, regenerate the bundled runtime even if the executable is unchanged. The bundler copies that guide to `Apps/PocketLab/README.md` and records its checksum. Compare both release archives against `SHA256SUMS`. Record filesystem checks and physical boot or recovery results separately.
