# Contributing

Everyone taking part follows the [code of conduct](CODE_OF_CONDUCT.md). Report security problems privately as described in [SECURITY.md](SECURITY.md).

Read AGENTS.md and SDK.md. Ordinary mini apps belong in ignored miniapps/ or a separate directory. The default library contains only ESP32 detector and Starfall; templates/native-app is scaffolding, not an installed app.

For shell/tooling changes run make test, make brick, make renders, regenerate the runtime with tools/release.py runtime, and run make check. Keep UI changes separate and explicitly reviewed. The frozen source/artwork baseline catches accidental UI drift.

Test installer and deployment failures with isolated directories and mocked raw-disk or ADB commands. For setup changes, cover interruption and resume, a verify-only repeat install, and preservation of installed apps and saves. Use a disposable FAT32 volume for checks that depend on the filesystem. Do not run tests against a real card/device without choosing that hardware action. Report real hardware checks separately from native previews.

The agent skills in skills/ follow AGENTS.md, SDK.md and the CLI. Update them in the same change when you rename or remove a command, flag, referenced file or AGENTS.md section; tests/test_skills.py checks this.

Update release-files.txt deliberately when adding public files. Release archives use this exact inclusion list. Never commit user app files under miniapps/, data, local logs, caches, credentials, or personal validation artifacts. Include third-party provenance and licenses for new dependencies.

See docs/RELEASING.md for local artifact preparation. Publishing requires a separate maintainer action; no current workflow pushes a release.
