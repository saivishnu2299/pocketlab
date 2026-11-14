SOURCES = src/main.c src/ui.c src/usb.c src/game.c src/audio.c src/control.c src/cover.c
CFLAGS = -std=gnu11 -O2 -Wall -Wextra
HOST_LIBS = -lm -lpthread
ifeq ($(shell uname -s),Darwin)
HOST_LIBS += -framework IOKit -framework CoreFoundation
endif
.PHONY: host brick test renders release check sdk-test
host:
	mkdir -p build
	clang $(CFLAGS) $$(sdl2-config --cflags) $(SOURCES) $$(sdl2-config --libs) $(HOST_LIBS) -o build/pocketlab-host
brick:
	python3 tools/pocketlab.py build-shell
test: host
	clang $(CFLAGS) -fsanitize=address,undefined -g tests/core_test.c src/usb.c src/game.c $(HOST_LIBS) -o build/core-test
	build/core-test
	clang $(CFLAGS) -fsanitize=address,undefined -g tests/usb_cli.c src/usb.c $(HOST_LIBS) -o build/usb-test
	python3 tests/integration.py
	python3 tests/deploy_test.py
	python3 tests/control_test.py
	python3 tests/cover_test.py
	python3 -m unittest discover -s tests -p 'test_*.py' -v
renders: host
	python3 tools/render.py
check:
	python3 tools/release.py check
sdk-test:
	python3 tests/sdk_smoke.py
release: test brick renders
	python3 tests/sdk_smoke.py
	python3 tools/release.py runtime
	python3 tools/release.py bundle
