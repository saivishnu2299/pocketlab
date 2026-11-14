# Your mini apps

Save your PocketLAB application projects here, with one folder per app. From the repository root:

```sh
./pocketlab new miniapps/my-app --name "My app"
./pocketlab run miniapps/my-app --usb
./pocketlab watch miniapps/my-app --usb
```

Edit the generated app.c, app.json, and artwork yourself or with your coding agent. Choose a different folder name for each app; existing folders are never overwritten by `new`.

See the [PocketLAB SDK](../SDK.md) for app development and the [installation guide](../docs/INSTALL.md) for device setup. USB deployment requires PocketLAB open on the Brick and the stock USB Storage app closed.

This directory contains your computer-side source projects. PocketLAB installs app packages in `Apps/PocketLab/apps` and keeps their saves under `Apps/PocketLab/data`. The shell updater leaves both directories in place. ESP32 detector and Starfall are built into PocketLAB and do not need source-project folders here.

Only this guide is included in Git and public release archives. Your app folders are ignored by Git and excluded from PocketLAB releases. Keep separate backups or repositories for apps you want to preserve or share.
