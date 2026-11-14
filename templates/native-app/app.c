/* Independent mini app. Uses the optional PocketLAB drawing and USB libraries.
 * Replace this UI freely; the shell imposes no design on mini apps. */
#include "app.h"
#include "ui.h"
#include "usb.h"
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define APP_TITLE "My app"

static volatile sig_atomic_t exiting;
static void stop(int sig) {
    (void)sig;
    exiting = 1;
}
static void save_count(const char *path, int count) {
    char tmp[4096];
    snprintf(tmp, sizeof tmp, "%s.tmp", path);
    FILE *f = fopen(tmp, "w");
    if (!f)
        return;
    bool ok = fprintf(f, "%d\n", count) > 0 && fflush(f) == 0;
    if (ok)
        ok = fsync(fileno(f)) == 0;
    if (fclose(f))
        ok = false;
    if (ok)
        rename(tmp, path);
    else
        unlink(tmp);
}
int main(void) {
    signal(SIGTERM, stop);
    signal(SIGINT, stop);
    const char *root = getenv("POCKETLAB_ROOT");
    const char *data = getenv("POCKETLAB_APP_DATA");
    if (!root || !data) {
        fprintf(stderr, "Launch this example through PocketLAB.\n");
        return 1;
    }
    char assets[4096], path[4096];
    snprintf(assets, sizeof assets, "%s/assets", root);
    snprintf(path, sizeof path, "%s/count.txt", data);
    int count = 0;
    FILE *f = fopen(path, "r");
    if (f) {
        if (fscanf(f, "%d", &count) != 1)
            count = 0;
        fclose(f);
    }
    fprintf(stderr, "%s: restored counter %d\n", APP_TITLE, count);
    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_JOYSTICK))
        return 1;
    Uint32 flags = SDL_WINDOW_SHOWN;
#ifdef __linux__
    flags |= SDL_WINDOW_FULLSCREEN_DESKTOP;
#endif
    SDL_Window *window = SDL_CreateWindow(APP_TITLE, SDL_WINDOWPOS_CENTERED,
                                          SDL_WINDOWPOS_CENTERED, 1024, 768, flags);
    if (!window) {
        SDL_Quit();
        return 1;
    }
    renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC);
    if (!renderer)
        renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_SOFTWARE);
    if (!renderer || !ui_init(assets)) {
        SDL_DestroyWindow(window);
        SDL_Quit();
        return 1;
    }
    SDL_RenderSetLogicalSize(renderer, 1024, 768);
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    SDL_Joystick *pad = SDL_NumJoysticks() ? SDL_JoystickOpen(0) : NULL;
    bool run = true;
    UsbSnapshot devices = {0};
    Uint32 next_scan = 0;
    bool announced = false;
    while (run && !exiting) {
        int previous_count = count;
        SDL_Event e;
        while (SDL_PollEvent(&e)) {
            if (e.type == SDL_QUIT)
                run = false;
            if (e.type == SDL_KEYDOWN) {
                if (e.key.keysym.sym == SDLK_ESCAPE || e.key.keysym.sym == SDLK_TAB)
                    run = false;
                if (e.key.keysym.sym == SDLK_RETURN || e.key.keysym.sym == SDLK_SPACE)
                    count++;
            }
            if (e.type == SDL_JOYBUTTONDOWN) {
                if (e.jbutton.button == 0 || e.jbutton.button == 8 || e.jbutton.button == 15)
                    run = false;
                if (e.jbutton.button == 1)
                    count++;
            }
        }
        if (count != previous_count)
            save_count(path, count);
        if (SDL_GetTicks() >= next_scan) {
            usb_scan(NULL, &devices);
            next_scan = SDL_GetTicks() + 500;
        }
        fill(0, 0, 1024, 768, RGB(40, 17, 50));
        mono(60, 55, 18, RGB(255, 160, 215), "YOUR MINI APP");
        text(56, 159, 84, true, RGB(255, 222, 246), "your canvas.");
        text(60, 273, 28, false, RGB(213, 169, 205), "Build on your computer. Run here over USB.");
        textf(60, 381, 84, true, RGB(255, 160, 215), "%03d", count);
        text(60, 490, 28, false, RGB(255, 222, 246),
             "A adds one. Your count is saved automatically.");
        textf(60, 558, 24, false, RGB(213, 169, 205),
              "USB: %d supported boards / %d devices visible", devices.count, devices.total);
        keycap(60, 686, "B", "return to PocketLAB", true);
        SDL_RenderPresent(renderer);
        if (!announced) {
            pocketlab_ready();
            announced = true;
        }
        SDL_Delay(16);
    }
    save_count(path, count);
    if (pad)
        SDL_JoystickClose(pad);
    ui_destroy();
    SDL_DestroyRenderer(renderer);
    SDL_DestroyWindow(window);
    SDL_Quit();
    return 0;
}
