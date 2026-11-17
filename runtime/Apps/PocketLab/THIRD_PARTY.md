# Third-party materials

- **stb_truetype.h** by Sean Barrett and contributors, from https://github.com/nothings/stb/blob/master/stb_truetype.h. MIT/public-domain dual licensing text is embedded in the source header and `assets/LICENSE-stb.txt`; used under MIT. Font rasterization is compiled into PocketLAB.
- **Barlow Regular and SemiBold**, Jeremy Tribby and contributors; SIL Open Font License 1.1, included at `assets/OFL.txt`. Source: https://github.com/google/fonts/tree/main/ofl/barlow.
- **IBM Plex Mono Regular**, IBM Corp. and contributors; SIL Open Font License 1.1, included at `assets/OFL-IBM-Plex.txt`. Source: https://github.com/google/fonts/tree/main/ofl/ibmplexmono.
- **SDL2** is dynamically linked from the host/device, not redistributed in the installation. zlib license; https://www.libsdl.org/license.php.
- **Zig 0.14.1** is downloaded from https://ziglang.org/download/ and SHA-256-pinned in `tools/native_build.py`. It supplies the native cross compiler, linker, compiler support libraries and glibc link interfaces. The compiler/cache is not in the source ZIP or device installation. Its distribution retains its own MIT and component license notices. No Docker toolchain is used.
- **SDL 2.26.1 source/headers** are downloaded from https://www.libsdl.org/release/SDL2-2.26.1.tar.gz with a pinned SHA-256. The source retains its zlib license. A generated, explicitly marked import-only shared library derives exported names from src/dynapi/SDL_dynapi_procs.h and retains its notice. It is solely a local link input; it must never be deployed. The application dynamically uses the stock device SDL implementation. No device library is copied or redistributed.
- **TrimUI stock SD base** v1.0.0-20260626 is optionally downloaded directly from https://github.com/trimui/assets_brickpro/releases/tag/v1.0.0-20260626 with a pinned SHA-256 for empty-card preparation. It is distributed separately from PocketLAB. Upstream components retain their own notices and distribution terms. Firmware images are not fetched or flashed.


All PocketLAB/Starfall illustrations, icon geometry, pixel sprites and synthesized sound patterns were created for this project. No Teenage Engineering or Galaga artwork, audio, ROM or trademarks are bundled as app assets.
