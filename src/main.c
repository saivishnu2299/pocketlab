#include "audio.h"
#include "control.h"
#include "cover.h"
#include "game.h"
#include "ui.h"
#include "usb.h"
#include <dirent.h>
#include <errno.h>
#include <limits.h>
#include <math.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
#define VERSION "1.1.0"
static const Color ORANGE = {243, 83, 37, 255}, PANEL = {225, 226, 216, 255},
                   GRAY = {164, 171, 161, 255};
typedef enum { LIBRARY, DETECTOR, INTRO, PLAY, SETTINGS, HELP, VERIFY, QUIT } Scene;
typedef struct {
    char id[64], name[96], description[256], path[PATH_MAX];
    int builtin;
    bool ready_signal;
    Cover cover;
} MiniApp;
#define MAX_APPS 128
static MiniApp apps[MAX_APPS];
static int app_count = 2, selected = 0, device_selected = 0, setting = 0;
static Scene scene = LIBRARY;
static ControlRequest pending_request;
static bool request_pending, restart_requested;
static unsigned launch_number;
static Game game;
static SDL_Window *window;
static char root[PATH_MAX] = ".", asset_dir[PATH_MAX], data_dir[PATH_MAX], message[256] = "";
static volatile sig_atomic_t stop_requested;
static void stop_signal(int sig) {
    (void)sig;
    stop_requested = 1;
}
static float now, notice_until;
static bool running = true, quiet = false, reduced = false, fixture = false;
static int difficulty = 1, highscores[3], battery = -1;
static const char *levels[] = {"RELAXED", "ARCADE", "EXPERT"};
static bool sound_on = true, saved_score = false;
static const char *sysroot = NULL;
static SDL_Joystick *pad = NULL;
static SDL_JoystickID pad_id = -1;
static bool held[10], pressed[10];
enum { LEFT, RIGHT, UP, DOWN, ACCEPT, BACK, EXTRA, ALT, START, HOME_KEY };
static float stick_x, nav_repeat;
static int last_axis_dir;
static SDL_Thread *scan_thread, *probe_thread;
static SDL_mutex *usb_lock;
static SDL_atomic_t scan_stop, probe_done;
static UsbSnapshot snapshot;
static bool probing = false;
static char probe_port[256], probe_chip[80], probe_error[192], probe_identity[512],
    verified_identity[512], verified_chip[80];
static unsigned scan_generation = 0;
static void notice(const char *s) {
    snprintf(message, sizeof message, "%s", s);
    notice_until = now + 4;
}
static void save_settings(void) {
    char tmp[PATH_MAX], dst[PATH_MAX];
    snprintf(tmp, sizeof tmp, "%s/settings.tmp", data_dir);
    snprintf(dst, sizeof dst, "%s/settings.ini", data_dir);
    FILE *f = fopen(tmp, "w");
    if (!f) {
        notice("Could not save. Check SD card space.");
        return;
    }
    fprintf(f, "sound=%d\nreduced=%d\ndifficulty=%d\nhigh0=%d\nhigh1=%d\nhigh2=%d\n", sound_on,
            reduced, difficulty, highscores[0], highscores[1], highscores[2]);
    bool ok = fflush(f) == 0;
    if (ok)
        ok = fsync(fileno(f)) == 0;
    if (fclose(f))
        ok = false;
    if (!ok || rename(tmp, dst)) {
        notice("Could not save settings to the SD card.");
    }
}
static void load_settings(void) {
    char p[PATH_MAX];
    snprintf(p, sizeof p, "%s/settings.ini", data_dir);
    FILE *f = fopen(p, "r");
    if (!f)
        return;
    char key[64];
    int val;
    while (fscanf(f, "%63[^=]=%d\n", key, &val) == 2) {
        if (!strcmp(key, "sound"))
            sound_on = val != 0;
        if (!strcmp(key, "reduced"))
            reduced = val != 0;
        if (!strcmp(key, "difficulty"))
            difficulty = val >= 0 && val <= 2 ? val : 1;
        for (int i = 0; i < 3; i++) {
            char k[16];
            snprintf(k, sizeof k, "high%d", i);
            if (!strcmp(key, k) && val >= 0)
                highscores[i] = val;
        }
    }
    fclose(f);
}
static void remember_score(void) {
    if (!saved_score) {
        if (game.score > highscores[difficulty]) {
            highscores[difficulty] = game.score;
            save_settings();
        }
        saved_score = true;
    }
}
static bool json_string(const char *json, const char *key, char *out, size_t cap) {
    char needle[96];
    snprintf(needle, sizeof needle, "\"%s\"", key);
    const char *p = strstr(json, needle);
    if (!p)
        return false;
    p = strchr(p + strlen(needle), ':');
    if (!p)
        return false;
    p++;
    while (*p == ' ' || *p == '\n' || *p == '\r' || *p == '\t')
        p++;
    if (*p != '\"')
        return false;
    p++;
    size_t n = 0;
    while (*p && *p != '\"') {
        if (*p == '\\')
            return false;
        if (n + 1 < cap)
            out[n++] = *p;
        p++;
    }
    out[n] = 0;
    return *p == '\"' && n > 0;
}
static void catalog(void) {
    for (int i = 0; i < app_count; i++) cover_free(&apps[i].cover);
    memset(apps, 0, sizeof apps);
    app_count = 2;
    snprintf(apps[0].id, sizeof apps[0].id, "esp32");
    snprintf(apps[0].name, sizeof apps[0].name, "ESP32 detector");
    snprintf(apps[0].description, sizeof apps[0].description,
             "Connect a board. See what is there.");
    apps[0].builtin = 1;
    snprintf(apps[1].id, sizeof apps[1].id, "starfall");
    snprintf(apps[1].name, sizeof apps[1].name, "Starfall");
    snprintf(apps[1].description, sizeof apps[1].description, "A small ship. An endless sky.");
    apps[1].builtin = 2;
    char dir[PATH_MAX];
    snprintf(dir, sizeof dir, "%s/apps", root);
    DIR *d = opendir(dir);
    if (!d) {
        selected = 0;
        return;
    }
    struct dirent *e;
    while ((e = readdir(d)) && app_count < MAX_APPS) {
        if (e->d_name[0] == '.')
            continue;
        char path[PATH_MAX];
        snprintf(path, sizeof path, "%s/%s/app.json", dir, e->d_name);
        FILE *f = fopen(path, "r");
        if (!f)
            continue;
        char json[4096];
        size_t n = fread(json, 1, sizeof json - 1, f);
        json[n] = 0;
        fclose(f);
        MiniApp a = {0};
        if (!json_string(json, "name", a.name, sizeof a.name))
            continue;
        if (!control_app_id(e->d_name))
            continue;
        char ready[32];
        a.ready_signal = json_string(json, "ready", ready, sizeof ready) && !strcmp(ready, "file");
        snprintf(a.id, sizeof a.id, "%s", e->d_name);
        json_string(json, "description", a.description, sizeof a.description);
        snprintf(a.path, sizeof a.path, "%s/%s", dir, e->d_name);
        snprintf(path, sizeof path, "%s/launch.sh", a.path);
        if (access(path, R_OK) == 0)
            apps[app_count++] = a;
    }
    closedir(d);
    if (selected >= app_count)
        selected = 0;
}
static void set_scene(Scene s) {
    scene = s;
    memset(held, 0, sizeof held);
    memset(pressed, 0, sizeof pressed);
    stick_x = 0;
    nav_repeat = 0;
    last_axis_dir = 0;
    if (s == LIBRARY)
        catalog();
}
static void start_game(void) {
    game_start(&game, difficulty, (unsigned)SDL_GetTicks());
    saved_score = false;
    set_scene(PLAY);
    sound(4);
}
static void open_pad(void) {
    if (pad && SDL_JoystickGetAttached(pad))
        return;
    if (pad) {
        SDL_JoystickClose(pad);
        pad = NULL;
        pad_id = -1;
    }
    for (int i = 0; i < SDL_NumJoysticks(); i++) {
        SDL_Joystick *p = SDL_JoystickOpen(i);
        if (!p)
            continue;
        if (!pad) {
            pad = p;
            pad_id = SDL_JoystickInstanceID(p);
        } else
            SDL_JoystickClose(p);
    }
}
static int scan_loop(void *unused) {
    (void)unused;
    while (!SDL_AtomicGet(&scan_stop)) {
        UsbSnapshot s;
        usb_scan(sysroot, &s);
        SDL_LockMutex(usb_lock);
        snapshot = s;
        scan_generation++;
        SDL_UnlockMutex(usb_lock);
        for (int i = 0; i < 5 && !SDL_AtomicGet(&scan_stop); i++)
            SDL_Delay(100);
    }
    return 0;
}
static int probe_loop(void *unused) {
    (void)unused;
    esp_probe(probe_port, probe_chip, sizeof probe_chip, probe_error, sizeof probe_error);
    SDL_AtomicSet(&probe_done, 1);
    return 0;
}
static void begin_probe(UsbSnapshot *s) {
    if (probing || !s->count)
        return;
    UsbDevice *u = &s->devices[device_selected % s->count];
    if (!u->port[0]) {
        notice("USB is visible, but no serial driver exposed a port.");
        return;
    }
    snprintf(probe_port, sizeof probe_port, "%s", u->port);
    usb_identity(u, probe_identity, sizeof probe_identity);
    probe_chip[0] = probe_error[0] = 0;
    SDL_AtomicSet(&probe_done, 0);
    probe_thread = SDL_CreateThread(probe_loop, "esp-probe", NULL);
    if (probe_thread) {
        probing = true;
        set_scene(DETECTOR);
    } else
        notice("Could not start chip verification.");
}
static void header(const char *section, bool dark) {
    Color fg = dark ? PAPER : INK, dim = dark ? RGB(138, 155, 172) : MUTED;
    mono(42, 29, 17, fg, "PocketLAB");
    text(186, 27, 19, false, dim, "/");
    mono(211, 29, 17, dim, section);
    if (battery >= 0) {
        textf(864, 28, 18, false, dim, "%d%%", battery);
        outline(931, 30, 43, 17, 3, dim, 1);
        fill(975, 35, 3, 7, dim);
        fill(935, 34, 35 * clampf(battery / 100.0f, 0, 1), 9, dim);
    } else {
        mono(859, 29, 17, dim, "PL / 01");
    }
    line(42, 69, 982, 69, dark ? RGB(45, 55, 65) : LINE);
}
static void footer(bool dark) {
    line(42, 703, 982, 703, dark ? RGB(45, 55, 65) : LINE);
    if (scene == LIBRARY) {
        keycap(42, 724, "A", "open", false);
        keycap(180, 724, "D-PAD", "select", false);
        keycap(412, 724, "X", "settings", false);
        keycap(625, 724, "Y", "guide", false);
        keycap(812, 724, "B", "exit", false);
    } else if (scene == DETECTOR) {
        keycap(42, 724, "B", "library", true);
        keycap(226, 724, "L / R", "board", true);
        keycap(455, 724, "A", "verify chip", true);
        keycap(718, 724, "Y", "help", true);
    } else if (scene == INTRO) {
        keycap(42, 724, "A", "launch", true);
        keycap(231, 724, "L / R", "difficulty", true);
        keycap(540, 724, "B", "library", true);
    } else if (scene == SETTINGS) {
        keycap(42, 724, "D-PAD", "select", false);
        keycap(287, 724, "A", "change", false);
        keycap(520, 724, "B", "save + return", false);
    } else if (scene == HELP) {
        keycap(42, 724, "B", "return to library", false);
    } else if (scene == PLAY && !game.paused && !game.over) {
        keycap(42, 724, "A", "fire", true);
        keycap(205, 724, "X", "shield", true);
        keycap(417, 724, "START", "pause", true);
        keycap(712, 724, "D-PAD", "move", true);
    }
}
static void library_view(void) {
    fill(0, 0, 1024, 768, PAPER);
    header("library", false);
    text(38, 91, 84, false, INK, "PocketLAB");
    mono(43, 197, 18, MUTED, "A PORTABLE WORKBENCH.");
    circle(939, 143, 40, ORANGE);
    line(919, 143, 959, 143, PAPER);
    line(939, 123, 939, 163, PAPER);
    mono(750, 211, 16, MUTED, "PORTABLE WORK / PLAY");
    int first = (selected / 2) * 2;
    /* Only the visible pair owns textures, even with a full 128-app catalog. */
    for (int i = 0; i < app_count; i++)
        if (i < first || i >= first + 2) cover_free(&apps[i].cover);
    for (int j = 0; j < 2; j++) {
        int index = first + j;
        if (index >= app_count)
            break;
        MiniApp *a = &apps[index];
        float x = 42 + j * 480;
        bool active = index == selected;
        Color bg = active ? INK : PANEL, fg = active ? PAPER : INK,
              dim = active ? RGB(169, 184, 176) : MUTED;
        roundrect(x, 258, 460, 326, 8, bg);
        if (active)
            outline(x - 3, 255, 466, 332, 10, ORANGE, 3);
        char number[16];
        snprintf(number, sizeof number, "%02d", index + 1);
        mono(x + 24, 280, 18, dim, number);
        circle(x + 421, 291, 6, active ? ORANGE : GRAY);
        if (a->builtin == 1) {
            chip_art(x + 233, 397, .62f, active ? RGB(60, 83, 74) : RGB(71, 96, 82),
                     active ? RGB(143, 164, 138) : RGB(135, 153, 121), reduced ? 0 : now, true);
            line(x + 66, 398, x + 145, 398, dim);
            line(x + 320, 398, x + 392, 398, dim);
            circle(x + 65, 398, 4, ORANGE);
            outline(x + 390, 391, 14, 14, 2, dim, 1);
        } else if (a->builtin == 2) {
            SDL_Rect clip = {(int)x + 18, 310, 424, 169};
            SDL_RenderSetClipRect(renderer, &clip);
            stars(reduced ? 0 : now, x + 24, 310, 410, 165, 44, active ? 1 : .45f);
            ship_art(x + 230, 417, 4, 0, active ? MINT : BLUE);
            ship_art(x + 140, 350, 2, 2, ORANGE);
            ship_art(x + 317, 347, 2, 1, ORANGE);
            fill(x + 228, 353, 4, 20, ORANGE);
            SDL_RenderSetClipRect(renderer, NULL);
        } else {
            cover_load(&a->cover, renderer, a->path, a->id, a->name);
            SDL_Rect area = {(int)x + 24, 318, 412, 164};
            cover_draw(&a->cover, renderer, &area);
        }
        line(x + 24, 493, x + 436, 493, active ? RGB(65, 80, 73) : RGB(190, 198, 185));
        text_fit(x + 24, 507, 410, 36, true, fg, a->name);
        mono(x + 24, 554, 15, dim,
             a->builtin == 1   ? "USB / INSTRUMENT"
             : a->builtin == 2 ? "ARCADE / SHOOTER"
                               : "INSTALLED / MINI APP");
    }
    text_fit(42, 618, 940, 28, false, INK, apps[selected].description);
    textf(42, 659, 18, false, MUTED, "%02d apps installed", app_count);
    mono(805, 659, 17, MUTED, "READY TO EXPLORE");
    footer(false);
}
static void detector_view(UsbSnapshot *s) {
    fill(0, 0, 1024, 768, NIGHT);
    header("esp32 detector", true);
    bool connected = s->count > 0;
    if (device_selected >= s->count)
        device_selected = 0;
    UsbDevice *u = connected ? &s->devices[device_selected] : NULL;
    char identity[512] = "";
    if (u)
        usb_identity(u, identity, sizeof identity);
    bool verified = u && !strcmp(verified_identity, identity) && verified_chip[0];
    Color status = connected ? (u->kind == USB_SERIAL && !verified ? RGB(255, 193, 93) : MINT)
                             : RGB(148, 165, 179);
    const char *title = !s->available           ? "USB unavailable"
                        : !connected            ? "Waiting for a board"
                        : verified              ? verified_chip
                        : u->kind == USB_SERIAL ? "Serial board detected"
                        : u->kind == USB_ESP32  ? "ESP32 connected"
                                                : "Espressif connected";
    circle(52, 112, 7, status);
    mono(72, 102, 17, status,
         probing     ? "VERIFYING CHIP"
         : connected ? "CONNECTION DETECTED"
                     : "LIVE USB MONITOR");
    text(42, 140, 48, true, PAPER, title);
    roundrect(42, 225, 350, 383, 7, RGB(22, 34, 47));
    for (int i = 0; i < 9; i++)
        for (int j = 0; j < 10; j++)
            fill(60 + i * 38, 242 + j * 35, 2, 2, RGB(43, 57, 65));
    chip_art(217, 385, 1.1f, RGB(51, 74, 66), RGB(106, 134, 104), reduced ? 0 : now, connected);
    line(217, 510, 217, 550, status);
    roundrect(181, 546, 72, 27, 6, status);
    mono(154, 580, 15, RGB(151, 169, 179), "USB-C / HOST");
    if (connected) {
        mono(428, 228, 16, RGB(140, 158, 174), "DEVICE");
        text_fit(428, 257, 554, 28, true, PAPER, u->product);
        line(428, 304, 982, 304, RGB(45, 57, 70));
        mono(428, 326, 15, RGB(140, 158, 174), "USB ID");
        textf(690, 321, 23, true, PAPER, "%04X : %04X", u->vid, u->pid);
        mono(428, 372, 15, RGB(140, 158, 174), "SERIAL PORT");
        text_fit(690, 367, 292, 21, false, PAPER, u->port[0] ? u->port : "not exposed");
        mono(428, 418, 15, RGB(140, 158, 174), "IDENTITY");
        text(690, 413, 21, false, status,
             verified                ? "ROM verified"
             : u->kind == USB_SERIAL ? "unconfirmed"
             : u->kind == USB_ESP32  ? "USB descriptor"
                                     : "Espressif USB");
        line(428, 460, 982, 460, RGB(45, 57, 70));
        const char *body =
            probing    ? "Reading chip identity. The board may restart. No firmware is written."
            : verified ? "Chip identity read successfully. The board has been restarted into its "
                         "normal firmware."
            : u->kind == USB_SERIAL ? "This USB bridge is also used by other boards. Press A to "
                                      "verify the connected chip."
                                    : "The device is visible over USB. Press A to read its chip "
                                      "identity if a serial port is available.";
        wrapped(428, 483, 530, 23, RGB(183, 199, 208), body);
        if (!u->port[0])
            wrapped(428, 581, 530, 20, RGB(255, 193, 93),
                    "No serial port: the firmware may need a driver, or this USB interface is not "
                    "serial.");
        textf(42, 645, 21, false, RGB(151, 169, 179),
              "Board %d of %d   /   auto-detect every 0.5 s", device_selected + 1, s->count);
    } else {
        text(428, 238, 32, true, PAPER, "Plug in. Get a signal.");
        wrapped(428, 298, 520, 26, RGB(183, 199, 208),
                "Connect the board to the Brick's rear HOST USB-C port using a data cable.");
        line(428, 402, 982, 402, RGB(45, 57, 70));
        mono(428, 431, 16, RGB(140, 158, 174), "SUPPORTED CONNECTIONS");
        text(428, 467, 23, false, PAPER, "Espressif native USB");
        text(428, 506, 23, false, PAPER, "CP210x / CH34x / CH91xx / FTDI");
        wrapped(428, 558, 520, 21, RGB(140, 158, 174),
                "Shared serial bridges appear as candidates until verified. Charge-only cables "
                "cannot carry USB data.");
        if (!s->available)
            wrapped(42, 635, 900, 20, RGB(255, 193, 93), s->error);
        else
            textf(42, 645, 21, false, RGB(151, 169, 179), "%d other USB devices visible", s->total);
    }
    footer(true);
}
static void intro_view(void) {
    fill(0, 0, 1024, 768, NIGHT);
    stars(reduced ? 0 : now, 0, 70, 1024, 630, 130, 1);
    header("starfall", true);
    mono(42, 108, 17, MINT, "THE SKY IS NOT EMPTY.");
    text(38, 153, 84, true, PAPER, "STARFALL");
    text(42, 251, 28, false, RGB(158, 180, 202), "A small ship. An endless sky.");
    ship_art(789, 374, 10, 0, MINT);
    fill(784, 434, 10, 40 + (reduced ? 0 : 20 * sinf(now * 6)), RGBA(255, 133, 74, 180));
    ship_art(644, 191, 3, 2, ORANGE);
    ship_art(887, 166, 3, 1, RGB(177, 157, 255));
    line(42, 328, 493, 328, RGB(45, 57, 70));
    mono(42, 358, 16, RGB(140, 158, 174), "FLIGHT MANUAL");
    text(42, 397, 24, false, PAPER, "Move with the D-pad or left stick.");
    text(42, 440, 24, false, PAPER, "Hold A to fire. X activates your shield.");
    text(42, 483, 24, false, PAPER, "Clear formations. Watch for divers.");
    roundrect(42, 560, 451, 86, 6, RGB(29, 44, 59));
    mono(66, 576, 15, RGB(140, 158, 174), "DIFFICULTY");
    text(66, 601, 28, true, MINT, levels[difficulty]);
    textf(589, 590, 22, false, RGB(140, 158, 174), "BEST  %06d", highscores[difficulty]);
    footer(true);
}
static void game_view(void) {
    fill(0, 0, 1024, 768, NIGHT);
    stars(reduced ? 0 : game.time, 88, 80, 848, 610, 110, 1);
    Color colors[] = {MINT, RGB(186, 155, 255), RGB(255, 166, 99)};
    mono(42, 24, 16, RGB(131, 153, 175), "SCORE");
    textf(42, 45, 32, true, PAPER, "%06d", game.score);
    mono(295, 24, 16, RGB(131, 153, 175), "BEST");
    textf(295, 45, 32, true, RGB(131, 153, 175), "%06d",
          highscores[difficulty] > game.score ? highscores[difficulty] : game.score);
    mono(536, 24, 16, RGB(131, 153, 175), "WAVE");
    textf(536, 45, 32, true, MINT, "%02d", game.wave);
    for (int i = 0; i < game.lives; i++)
        ship_art(859 + i * 38, 49, 2, 0, MINT);
    line(42, 90, 982, 90, RGB(45, 55, 65));
    line(92, 112, 92, 682, RGB(28, 40, 55));
    line(932, 112, 932, 682, RGB(28, 40, 55));
    SDL_Rect playarea = {100, 96, 824, 596};
    SDL_RenderSetClipRect(renderer, &playarea);
    for (int i = 0; i < ENEMIES; i++) {
        Enemy *e = &game.enemies[i];
        if (e->active && e->age >= 0)
            ship_art(e->x, e->y, 3.2f, e->type, colors[e->type % 3]);
    }
    for (int i = 0; i < BULLETS; i++) {
        Bullet *b = &game.bullets[i];
        if (b->active) {
            Color c = b->enemy ? ORANGE : MINT;
            fill(b->x - 5, b->y - 10, 10, 24, RGBA(c.r, c.g, c.b, 35));
            roundrect(b->x - 2, b->y - 8, 4, b->enemy ? 12 : 20, 2, c);
        }
    }
    for (int i = 0; i < PARTICLES; i++) {
        Particle *p = &game.particles[i];
        if (p->life > 0) {
            Color c = colors[p->color];
            c.a = (Uint8)(255 * p->life / p->maxlife);
            float sz = 2 + 3 * p->life / p->maxlife;
            fill(p->x, p->y, sz, sz, c);
        }
    }
    if (!game.over && (game.invulnerable <= 0 || ((int)(game.time * 12) % 2) == 0)) {
        if (game.shield > 0) {
            for (int a = 0; a < 360; a += 4) {
                float r = a * .0174533f;
                circle(game.player_x + cosf(r) * 48, 641 + sinf(r) * 48, 2,
                       RGBA(173, 242, 207, 160));
            }
        }
        ship_art(game.player_x, 641, 4, 0, MINT);
    }
    if (game.wave_wait > 0) {
        const char *s = game.wave == 0 ? "GET READY" : "SECTOR CLEAR";
        text(512 - text_width(s, 36, true) / 2, 360, 36, true, MINT, s);
    }
    SDL_RenderSetClipRect(renderer, NULL);
    if (game.combo >= 3)
        textf(110, 109, 18, true, MINT, "%d HIT STREAK", game.combo);
    fill(749, 674, 170, 4, RGB(45, 55, 65));
    fill(749, 674, 170 * (1 - clampf(game.shield_recharge / 9, 0, 1)), 4, MINT);
    mono(749, 648, 13, RGB(140, 158, 174),
         game.shield_recharge > 0 ? "SHIELD CHARGING" : "SHIELD READY");
    footer(true);
    if (game.paused || game.over) {
        fill(0, 0, 1024, 768, RGBA(7, 12, 22, 215));
        roundrect(214, 203, 596, 353, 9, RGB(26, 39, 54));
        mono(250, 236, 16, MINT, game.over ? "FLIGHT COMPLETE" : "TAKE A BREATHER");
        text(250, 276, 64, true, PAPER, game.over ? "Good flying." : "Paused.");
        if (game.over) {
            textf(250, 365, 32, true, PAPER, "%06d points", game.score);
            textf(250, 413, 22, false, RGB(165, 186, 204),
                  "Wave %d   /   %d enemies   /   best streak %d", game.wave, game.kills,
                  game.best_combo);
            keycap(250, 493, "A", "fly again", true);
            keycap(514, 493, "B", "library", true);
        } else {
            wrapped(250, 369, 500, 26, RGB(165, 186, 204),
                    "Your flight is waiting. Resume when you are ready.");
            keycap(250, 493, "A", "resume", true);
            keycap(514, 493, "B", "end flight", true);
        }
    }
}
static void settings_view(void) {
    fill(0, 0, 1024, 768, PAPER);
    header("settings", false);
    text(42, 105, 64, false, INK, "settings");
    const char *names[] = {"Sound", "Motion", "Starfall difficulty"};
    const char *values[] = {sound_on ? "ON" : "OFF", reduced ? "REDUCED" : "FULL",
                            levels[difficulty]};
    for (int i = 0; i < 3; i++) {
        float y = 227 + i * 108;
        bool active = setting == i;
        roundrect(42, y, 940, 90, 6, active ? INK : PANEL);
        circle(70, y + 45, 5, active ? ORANGE : GRAY);
        text(95, y + 27, 32, true, active ? PAPER : INK, names[i]);
        mono(730, y + 34, 20, active ? PAPER : MUTED, values[i]);
    }
    mono(42, 595, 16, MUTED, "PocketLAB " VERSION " / BRICK PRO");
    wrapped(42, 628, 880, 23, MUTED,
            "Settings and high scores stay on your SD card. Each mini app can have its own visual "
            "style and controls.");
    footer(false);
}
static void help_view(void) {
    fill(0, 0, 1024, 768, PAPER);
    header("quick guide", false);
    text(42, 102, 64, false, INK, "quick guide");
    const char *titles[] = {"01   THE LIBRARY", "02   CONNECT A BOARD", "03   PLAY STARFALL",
                            "04   ADD YOUR OWN APPS"};
    const char *body[] = {
        "D-pad selects. A opens. B goes back. X opens settings. The Menu button returns here, or "
        "pauses an active game.",
        "Use the rear HOST port and a data cable. Native Espressif USB is recognized immediately. "
        "Generic serial bridges need chip verification to confirm an ESP32.",
        "Move with the D-pad or left stick. Hold A to fire. X gives two seconds of shield. Start "
        "pauses. Three lives; a new formation each wave.",
        "Install a mini-app folder with app.json and launch.sh into PocketLab/apps. Return to the "
        "library to refresh it. Apps own their fullscreen design."};
    for (int i = 0; i < 4; i++) {
        float y = 204 + i * 118;
        mono(42, y, 16, ORANGE, titles[i]);
        wrapped(42, y + 31, 912, 24, INK, body[i]);
        if (i < 3)
            line(42, y + 105, 982, y + 105, LINE);
    }
    footer(false);
}
static void dialog_view(bool quit) {
    fill(0, 0, 1024, 768, PAPER);
    header(quit ? "exit" : "verify chip", false);
    text(64, 151, 64, false, INK, quit ? "back to the Brick?" : "identify this chip?");
    wrapped(64, 267, 870, 32, INK,
            quit ? "Your apps and saved scores will be here when you return."
                 : "Verification restarts the selected board and asks its ROM for a chip identity. "
                   "It never writes firmware.");
    if (!quit)
        wrapped(64, 402, 870, 25, MUTED,
                "If automatic reset is not supported, hold BOOT and tap RESET before retrying. A "
                "board's USB bridge alone cannot prove that it is an ESP32.");
    keycap(64, 593, "A", quit ? "exit PocketLAB" : "verify + restart board", false);
    keycap(487, 593, "B", "cancel", false);
}
static bool video_init(bool headless) {
    SDL_SetHint(SDL_HINT_RENDER_SCALE_QUALITY, "1");
    Uint32 flags = headless ? SDL_WINDOW_HIDDEN : SDL_WINDOW_SHOWN;
#ifdef __linux__
    if (!headless)
        flags |= SDL_WINDOW_FULLSCREEN_DESKTOP;
#endif
    window = SDL_CreateWindow("PocketLAB", SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED, 1024,
                              768, flags);
    if (!window)
        return false;
    if (!headless)
        renderer =
            SDL_CreateRenderer(window, -1, SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC);
    if (!renderer)
        renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_SOFTWARE);
    if (!renderer)
        return false;
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    SDL_RenderSetLogicalSize(renderer, 1024, 768);
    SDL_ShowCursor(SDL_DISABLE);
    SDL_RendererInfo info;
    SDL_GetRendererInfo(renderer, &info);
    SDL_version linked;
    SDL_GetVersion(&linked);
    fprintf(stderr, "Renderer: %s; SDL runtime %d.%d.%d; headers %d.%d.%d\n", info.name,
            linked.major, linked.minor, linked.patch, SDL_MAJOR_VERSION, SDL_MINOR_VERSION,
            SDL_PATCHLEVEL);
    return ui_init(asset_dir);
}
static void video_destroy(void) {
    for (int i = 0; i < app_count; i++) cover_free(&apps[i].cover);
    ui_destroy();
    SDL_DestroyRenderer(renderer);
    renderer = NULL;
    SDL_DestroyWindow(window);
    window = NULL;
}
static int find_app(const char *id) {
    for (int i = 0; i < app_count; i++)
        if (!strcmp(apps[i].id, id))
            return i;
    return -1;
}
static bool receive_request(void) {
    if (request_pending)
        return true;
    ControlRequest r;
    if (!control_read(&r))
        return false;
    catalog();
    if (!strcmp(r.op, "launch") && find_app(r.app) < 0) {
        control_reply(&r, false, "App is not installed.");
        return false;
    }
    if (!strcmp(r.op, "install") && !control_stage_valid(&r)) {
        control_reply(&r, false, "Verified upload is missing or invalid.");
        return false;
    }
    if (!strcmp(r.op, "refresh")) {
        control_reply(&r, true, "Library refreshed.");
        return false;
    }
    pending_request = r;
    request_pending = true;
    return true;
}
static bool launch_external(const ControlRequest *command) {
    MiniApp a = apps[selected];
    char launch[PATH_MAX], appdata[PATH_MAX], ready_path[PATH_MAX], session[80];
    snprintf(launch, sizeof launch, "%s/launch.sh", a.path);
    snprintf(appdata, sizeof appdata, "%s/%s", data_dir, a.id);
    snprintf(session, sizeof session, "%ld-%u", (long)getpid(), ++launch_number);
    control_ready_path(ready_path, sizeof ready_path);
    unlink(ready_path);
    mkdir(appdata, 0755);
    setenv("POCKETLAB_APP_DATA", appdata, 1);
    setenv("POCKETLAB_ROOT", root, 1);
    setenv("POCKETLAB_WIDTH", "1024", 1);
    setenv("POCKETLAB_HEIGHT", "768", 1);
    setenv("POCKETLAB_READY_FILE", ready_path, 1);
    setenv("POCKETLAB_SESSION", session, 1);
    if (probe_thread) {
        SDL_WaitThread(probe_thread, NULL);
        probe_thread = NULL;
        probing = false;
    }
    SDL_AtomicSet(&scan_stop, 1);
    if (scan_thread) {
        SDL_WaitThread(scan_thread, NULL);
        scan_thread = NULL;
    }
    audio_destroy();
    if (pad) {
        SDL_JoystickClose(pad);
        pad = NULL;
        pad_id = -1;
    }
    video_destroy();
    SDL_QuitSubSystem(SDL_INIT_VIDEO | SDL_INIT_JOYSTICK);
    char *child_args[] = {"sh", launch, NULL};
    extern char **environ;
    pid_t pid = fork();
    if (pid == 0) {
        setpgid(0, 0);
        if (chdir(a.path))
            _exit(126);
        execve("/bin/sh", child_args, environ);
        _exit(127);
    }
    int status = 127 << 8;
    bool started = false, stopping = false, intentional = false;
    Uint32 began = SDL_GetTicks(), stop_at = 0;
    if (pid > 0) {
        setpgid(pid, pid);
        control_status("starting", a.id, pid, session, false);
        fprintf(stderr, "App starting: %s pid=%ld session=%s\n", a.id, (long)pid, session);
        for (;;) {
            pid_t result = waitpid(pid, &status, WNOHANG);
            if (result == pid || (result < 0 && errno != EINTR))
                break;
            bool ready = control_is_ready(session);
            if (!started && !stopping &&
                (ready || (!a.ready_signal && SDL_GetTicks() - began >= 800))) {
                started = true;
                control_status("app", a.id, pid, session, ready);
                if (command)
                    control_reply(command, true,
                                  ready ? "App presented its first frame."
                                        : "App process started (no readiness signal declared).");
                fprintf(stderr, "App running: %s ready=%d\n", a.id, ready);
            }
            if (!stopping && (stop_requested || receive_request())) {
                intentional = true;
                stopping = true;
                stop_at = SDL_GetTicks();
                control_status("stopping", a.id, pid, session, false);
                kill(-pid, SIGTERM);
            }
            if (!stopping && !started && SDL_GetTicks() - began > 8000) {
                stopping = true;
                stop_at = SDL_GetTicks();
                kill(-pid, SIGTERM);
                fprintf(stderr, "App readiness timed out: %s\n", a.id);
            }
            if (stopping && SDL_GetTicks() - stop_at > 3000)
                kill(-pid, SIGKILL);
            SDL_Delay(50);
        }
        /* Reap/stop any remaining descendants belonging to this app's group. */
        kill(-pid, SIGTERM);
    }
    fprintf(stderr, "App exited: %s status=%d intentional=%d\n", a.id, status, intentional);
    if (SDL_InitSubSystem(SDL_INIT_VIDEO | SDL_INIT_JOYSTICK) || !video_init(false)) {
        fprintf(stderr, "Unable to restore PocketLAB display: %s\n", SDL_GetError());
        running = false;
        return started;
    }
    audio_init();
    audio_enable(sound_on);
    open_pad();
    SDL_AtomicSet(&scan_stop, 0);
    scan_thread = SDL_CreateThread(scan_loop, "usb-monitor", NULL);
    set_scene(LIBRARY);
    control_status("library", "", 0, "", true);
    if ((!WIFEXITED(status) || WEXITSTATUS(status)) && !intentional)
        notice("App closed with an error. See data/pocketlab.log.");
    return started;
}
static bool handle_request(void) {
    if (!receive_request())
        return false;
    ControlRequest r = pending_request;
    request_pending = false;
    if (scene == PLAY)
        remember_score();
    if (!strcmp(r.op, "library")) {
        set_scene(LIBRARY);
        control_status("library", "", 0, "", true);
        control_reply(&r, true, "Returned to the library.");
        return true;
    }
    if (!strcmp(r.op, "restart")) {
        save_settings();
        control_reply(&r, true, "Restarting PocketLAB.");
        restart_requested = true;
        running = false;
        return true;
    }
    bool installing = !strcmp(r.op, "install"), had_previous = false;
    if (installing && !control_install(&r, &had_previous)) {
        control_reply(&r, false, "Could not install upload; previous app retained.");
        return true;
    }
    catalog();
    int index = find_app(r.app);
    if (index < 0) {
        if (installing)
            control_rollback(&r);
        control_reply(&r, false, "App manifest is invalid or the library is full.");
        return true;
    }
    selected = index;
    if (apps[index].builtin) {
        set_scene(apps[index].builtin == 1 ? DETECTOR : INTRO);
        control_status("builtin", r.app, 0, "", true);
        control_reply(&r, true, "Built-in app opened.");
        return true;
    }
    if (!launch_external(&r)) {
        if (installing) {
            bool restored = control_rollback(&r);
            control_reply(
                &r, false,
                restored ? (had_previous
                                ? "New app failed to start; previous version restored."
                                : "App failed to start; failed upload removed from the library.")
                         : "App failed and rollback failed; inspect retained backups.");
            catalog();
            index = find_app(r.app);
            if (restored && had_previous && index >= 0 && !stop_requested && !request_pending) {
                selected = index;
                launch_external(NULL);
            }
        } else
            control_reply(&r, false, "App exited or did not signal readiness during startup.");
    }
    return true;
}
static void button(int code, bool down) {
    if (code < 0 || code > HOME_KEY)
        return;
    if (down && !held[code])
        pressed[code] = true;
    held[code] = down;
}
static int keyboard(SDL_Keycode k) {
    switch (k) {
    case SDLK_LEFT:
    case SDLK_a:
        return LEFT;
    case SDLK_RIGHT:
    case SDLK_d:
        return RIGHT;
    case SDLK_UP:
    case SDLK_w:
        return UP;
    case SDLK_DOWN:
    case SDLK_s:
        return DOWN;
    case SDLK_RETURN:
    case SDLK_SPACE:
    case SDLK_z:
        return ACCEPT;
    case SDLK_ESCAPE:
    case SDLK_BACKSPACE:
        return BACK;
    case SDLK_x:
        return EXTRA;
    case SDLK_y:
    case SDLK_h:
        return ALT;
    case SDLK_p:
        return START;
    case SDLK_TAB:
        return HOME_KEY;
    default:
        return -1;
    }
}
static int joybutton(int b) {
    switch (b) {
    case 0:
        return BACK;
    case 1:
        return ACCEPT;
    case 2:
        return ALT;
    case 3:
        return EXTRA;
    case 4:
        return LEFT;
    case 5:
        return RIGHT;
    case 7:
        return START;
    case 8:
    case 15:
        return HOME_KEY;
    default:
        return -1;
    }
}
static void events(void) {
    memset(pressed, 0, sizeof pressed);
    SDL_Event e;
    while (SDL_PollEvent(&e)) {
        if (e.type == SDL_QUIT)
            running = false;
        else if (e.type == SDL_KEYDOWN || e.type == SDL_KEYUP)
            button(keyboard(e.key.keysym.sym), e.type == SDL_KEYDOWN);
        else if (e.type == SDL_JOYDEVICEADDED)
            open_pad();
        else if (e.type == SDL_JOYDEVICEREMOVED) {
            open_pad();
            memset(held, 0, sizeof held);
            stick_x = 0;
            if (scene == PLAY)
                game.paused = true;
        } else if (e.type == SDL_JOYBUTTONDOWN || e.type == SDL_JOYBUTTONUP) {
            if (e.jbutton.which == pad_id)
                button(joybutton(e.jbutton.button), e.type == SDL_JOYBUTTONDOWN);
        } else if (e.type == SDL_JOYHATMOTION && e.jhat.which == pad_id) {
            button(LEFT, e.jhat.value & SDL_HAT_LEFT);
            button(RIGHT, e.jhat.value & SDL_HAT_RIGHT);
            button(UP, e.jhat.value & SDL_HAT_UP);
            button(DOWN, e.jhat.value & SDL_HAT_DOWN);
        } else if (e.type == SDL_JOYAXISMOTION && e.jaxis.which == pad_id) {
            if (e.jaxis.axis == 0) {
                float v = e.jaxis.value / 32767.0f;
                stick_x = fabsf(v) < .16f ? 0 : (v > 0 ? 1 : -1) * (fabsf(v) - .16f) / .84f;
            } else if (e.jaxis.axis == 1 && scene != PLAY) {
                button(UP, e.jaxis.value < -16000);
                button(DOWN, e.jaxis.value > 16000);
            }
        } else if (e.type == SDL_WINDOWEVENT && (e.window.event == SDL_WINDOWEVENT_FOCUS_LOST ||
                                                 e.window.event == SDL_WINDOWEVENT_MINIMIZED)) {
            memset(held, 0, sizeof held);
            stick_x = 0;
            if (scene == PLAY && !game.over)
                game.paused = true;
        } else if (e.type == SDL_APP_WILLENTERBACKGROUND) {
            if (scene == PLAY)
                game.paused = true;
            save_settings();
        }
    }
}
static void act(float dt, UsbSnapshot *s) {
    int axis_dir = stick_x < -.55f ? -1 : stick_x > .55f ? 1 : 0;
    if (scene != PLAY) {
        if (axis_dir && axis_dir != last_axis_dir)
            pressed[axis_dir < 0 ? LEFT : RIGHT] = true;
        last_axis_dir = axis_dir;
    }
    int dir = (held[RIGHT] || held[DOWN] || axis_dir > 0) ? 1
              : (held[LEFT] || held[UP] || axis_dir < 0)  ? -1
                                                          : 0;
    bool nav = pressed[LEFT] || pressed[RIGHT] || pressed[UP] || pressed[DOWN];
    int step = (pressed[LEFT] || pressed[UP]) ? -1 : (pressed[RIGHT] || pressed[DOWN]) ? 1 : dir;
    if (!dir)
        nav_repeat = 0;
    else if (nav)
        nav_repeat = .33f;
    else if ((nav_repeat -= dt) <= 0) {
        nav = true;
        nav_repeat = .16f;
    }
    if (pressed[HOME_KEY]) {
        if (scene == PLAY && !game.over)
            game.paused = true;
        else
            set_scene(LIBRARY);
        return;
    }
    if (scene == LIBRARY) {
        if (nav) {
            selected = (selected + (step ? step : 1) + app_count) % app_count;
            sound(6);
        }
        if (pressed[ACCEPT]) {
            sound(6);
            if (apps[selected].builtin == 1)
                set_scene(DETECTOR);
            else if (apps[selected].builtin == 2)
                set_scene(INTRO);
            else
                launch_external(NULL);
        } else if (pressed[EXTRA])
            set_scene(SETTINGS);
        else if (pressed[ALT])
            set_scene(HELP);
        else if (pressed[BACK])
            set_scene(QUIT);
    } else if (scene == DETECTOR) {
        if (nav && s->count)
            device_selected = (device_selected + (step ? step : 1) + s->count) % s->count;
        if (pressed[BACK])
            set_scene(LIBRARY);
        else if (pressed[ALT])
            set_scene(HELP);
        else if (pressed[ACCEPT] && !probing && s->count) {
            if (!s->devices[device_selected].port[0])
                notice("USB is visible, but no serial port is exposed.");
            else
                set_scene(VERIFY);
        }
    } else if (scene == VERIFY) {
        if (pressed[BACK])
            set_scene(DETECTOR);
        else if (pressed[ACCEPT])
            begin_probe(s);
    } else if (scene == INTRO) {
        if (nav) {
            difficulty = (difficulty + (step ? step : 1) + 3) % 3;
            save_settings();
            sound(6);
        }
        if (pressed[ACCEPT])
            start_game();
        else if (pressed[BACK])
            set_scene(LIBRARY);
    } else if (scene == PLAY) {
        if (game.over) {
            remember_score();
            if (pressed[ACCEPT])
                start_game();
            else if (pressed[BACK])
                set_scene(LIBRARY);
        } else if (game.paused) {
            if (pressed[ACCEPT] || pressed[START]) {
                game.paused = false;
                memset(held, 0, sizeof held);
            } else if (pressed[BACK]) {
                remember_score();
                set_scene(LIBRARY);
            }
        } else if (pressed[BACK] || pressed[START])
            game.paused = true;
        else {
            float move = held[LEFT] ? -1 : held[RIGHT] ? 1 : stick_x;
            game_update(&game, dt, move, held[ACCEPT], pressed[EXTRA]);
            if (game.sounds & S_SHOOT)
                sound(1);
            if (game.sounds & S_EXPLODE)
                sound(2);
            if (game.sounds & S_HURT)
                sound(3);
            if (game.sounds & S_WAVE)
                sound(4);
            if (game.sounds & S_SHIELD)
                sound(5);
        }
    } else if (scene == SETTINGS) {
        if (pressed[UP] || pressed[DOWN]) {
            setting = (setting + (pressed[DOWN] ? 1 : 2)) % 3;
            sound(6);
        }
        if (pressed[ACCEPT] || pressed[LEFT] || pressed[RIGHT]) {
            if (setting == 0) {
                sound_on = !sound_on;
                audio_enable(sound_on);
            } else if (setting == 1)
                reduced = !reduced;
            else
                difficulty = (difficulty + (pressed[LEFT] ? 2 : 1)) % 3;
            save_settings();
            sound(6);
        }
        if (pressed[BACK]) {
            save_settings();
            set_scene(LIBRARY);
        }
    } else if (scene == HELP) {
        if (pressed[BACK] || pressed[ACCEPT])
            set_scene(LIBRARY);
    } else if (scene == QUIT) {
        if (pressed[ACCEPT])
            running = false;
        else if (pressed[BACK])
            set_scene(LIBRARY);
    }
}
static void render(UsbSnapshot *s) {
    SDL_RenderSetClipRect(renderer, NULL);
    switch (scene) {
    case LIBRARY:
        library_view();
        break;
    case DETECTOR:
        detector_view(s);
        break;
    case INTRO:
        intro_view();
        break;
    case PLAY:
        game_view();
        break;
    case SETTINGS:
        settings_view();
        break;
    case HELP:
        help_view();
        break;
    case VERIFY:
        dialog_view(false);
        break;
    case QUIT:
        dialog_view(true);
        break;
    }
    if (fixture) {
        roundrect(711, 75, 271, 24, 3, ORANGE);
        mono(722, 79, 13, PAPER, "TEST USB INVENTORY");
    }
    if (message[0] && now < notice_until) {
        roundrect(40, 634, 944, 61, 6, ORANGE);
        wrapped(58, 646, 908, 22, PAPER, message);
    }
}
static void fixture_game(void) {
    game_start(&game, 1, 1234);
    for (int i = 0; i < 440; i++)
        game_update(&game, 1 / 60.0f, sinf(i * .013f) * .6f, true, false);
    game.score = 2450;
}
static void read_battery(void) {
    FILE *f = fopen("/sys/class/power_supply/axp2202-battery/capacity", "r");
    if (f) {
        int n;
        if (fscanf(f, "%d", &n) == 1 && n >= 0 && n <= 100)
            battery = n;
        fclose(f);
    }
}
int main(int argc, char **argv) {
    signal(SIGTERM, stop_signal);
    signal(SIGINT, stop_signal);
    const char *render_path = NULL, *scene_name = NULL, *render_app = NULL;
    bool root_set = false;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--root") && i + 1 < argc) {
            snprintf(root, sizeof root, "%s", argv[++i]);
            root_set = true;
        } else if (!strcmp(argv[i], "--render") && i + 1 < argc)
            render_path = argv[++i];
        else if (!strcmp(argv[i], "--scene") && i + 1 < argc)
            scene_name = argv[++i];
        else if (!strcmp(argv[i], "--render-app") && i + 1 < argc)
            render_app = argv[++i];
        else if (!strcmp(argv[i], "--sysroot") && i + 1 < argc) {
            sysroot = argv[++i];
            fixture = true;
        } else if (!strcmp(argv[i], "--quiet"))
            quiet = true;
    }
    if (!root_set) {
        char *b = SDL_GetBasePath();
        if (b) {
            snprintf(root, sizeof root, "%s", b);
            SDL_free(b);
        }
    }
    char real[PATH_MAX];
    if (realpath(root, real))
        snprintf(root, sizeof root, "%s", real);
    snprintf(asset_dir, sizeof asset_dir, "%s/assets", root);
    snprintf(data_dir, sizeof data_dir, "%s/data", root);
    mkdir(data_dir, 0755);
    load_settings();
    catalog();
    fprintf(stderr, "PocketLAB %s\nRoot: %s\n", VERSION, root);
    if (render_path) {
        if (render_app) {
            selected = find_app(render_app);
            if (selected < 0) {
                fprintf(stderr, "Render app is not installed: %s\n", render_app);
                return 1;
            }
        }
        SDL_setenv("SDL_VIDEODRIVER", "dummy", 1);
        SDL_setenv("SDL_AUDIODRIVER", "dummy", 1);
    }
    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_AUDIO | SDL_INIT_JOYSTICK | SDL_INIT_EVENTS |
                 SDL_INIT_TIMER)) {
        fprintf(stderr, "SDL initialization failed: %s\n", SDL_GetError());
        return 1;
    }
    if (!video_init(render_path != NULL)) {
        fprintf(stderr, "Display/font initialization failed: %s\n", SDL_GetError());
        SDL_Quit();
        return 1;
    }
    if (!quiet && !render_path) {
        audio_init();
        audio_enable(sound_on);
    }
    open_pad();
    read_battery();
    usb_lock = SDL_CreateMutex();
    if (!usb_lock) {
        fprintf(stderr, "Cannot create device lock\n");
        return 1;
    }
    usb_scan(sysroot, &snapshot);
    if (scene_name) {
        if (!strcmp(scene_name, "detector"))
            scene = DETECTOR;
        else if (!strcmp(scene_name, "intro"))
            scene = INTRO;
        else if (!strcmp(scene_name, "game") || !strcmp(scene_name, "pause") ||
                 !strcmp(scene_name, "over")) {
            fixture_game();
            scene = PLAY;
            game.paused = !strcmp(scene_name, "pause");
            game.over = !strcmp(scene_name, "over");
            if (game.over)
                game.lives = 0;
        } else if (!strcmp(scene_name, "settings"))
            scene = SETTINGS;
        else if (!strcmp(scene_name, "help"))
            scene = HELP;
        else if (!strcmp(scene_name, "verify"))
            scene = VERIFY;
        else if (!strcmp(scene_name, "quit"))
            scene = QUIT;
    }
    if (render_path) {
        now = 4;
        render(&snapshot);
        SDL_Surface *s = SDL_CreateRGBSurfaceWithFormat(0, 1024, 768, 32, SDL_PIXELFORMAT_RGBA32);
        int result = 1;
        if (s && SDL_RenderReadPixels(renderer, NULL, s->format->format, s->pixels, s->pitch) == 0)
            result = SDL_SaveBMP(s, render_path);
        SDL_FreeSurface(s);
        video_destroy();
        SDL_DestroyMutex(usb_lock);
        SDL_Quit();
        return result ? 1 : 0;
    }
    if (!control_init(root)) {
        fprintf(stderr, "Cannot initialize control channel (already running?): %s\n",
                strerror(errno));
        return 1;
    }
    control_status("library", "", 0, "", true);
    scan_thread = SDL_CreateThread(scan_loop, "usb-monitor", NULL);
    if (!scan_thread)
        notice("USB background monitor could not start.");
    Uint64 previous = SDL_GetPerformanceCounter();
    float battery_clock = 0;
    int last_count = snapshot.count;
    unsigned generation = 0;
    while (running && !stop_requested) {
        Uint64 tick = SDL_GetPerformanceCounter();
        float dt = (float)((double)(tick - previous) / SDL_GetPerformanceFrequency());
        previous = tick;
        if (dt > .4f && scene == PLAY && !game.over)
            game.paused = true;
        dt = clampf(dt, .001f, .05f);
        now += dt;
        battery_clock += dt;
        if (battery_clock > 5) {
            read_battery();
            battery_clock = 0;
        }
        UsbSnapshot s;
        SDL_LockMutex(usb_lock);
        s = snapshot;
        unsigned newgen = scan_generation;
        SDL_UnlockMutex(usb_lock);
        if (generation != newgen) {
            if (s.count > last_count)
                sound(4);
            last_count = s.count;
            generation = newgen;
            bool present = false;
            for (int i = 0; i < s.count; i++) {
                char identity[512];
                usb_identity(&s.devices[i], identity, sizeof identity);
                if (!strcmp(identity, verified_identity))
                    present = true;
            }
            if (!present && !probing)
                verified_identity[0] = verified_chip[0] = 0;
        }
        if (probing && SDL_AtomicGet(&probe_done)) {
            SDL_WaitThread(probe_thread, NULL);
            probe_thread = NULL;
            probing = false;
            bool present = false;
            for (int i = 0; i < s.count; i++) {
                char identity[512];
                usb_identity(&s.devices[i], identity, sizeof identity);
                if (!strcmp(identity, probe_identity))
                    present = true;
            }
            if (probe_chip[0] && present) {
                snprintf(verified_identity, sizeof verified_identity, "%s", probe_identity);
                snprintf(verified_chip, sizeof verified_chip, "%s", probe_chip);
                sound(4);
            } else
                notice(probe_chip[0] ? "Board connection changed during verification. Verify again."
                                     : probe_error);
        }
        if (device_selected >= s.count)
            device_selected = 0;
        events();
        if (!handle_request())
            act(dt, &s);
        const char *active = (scene == DETECTOR || scene == VERIFY) ? "esp32"
                             : (scene == PLAY || scene == INTRO)    ? "starfall"
                                                                    : "";
        control_status(active[0] ? "builtin" : "library", active, 0, "", true);
        if (!running)
            break;
        render(&s);
        SDL_RenderPresent(renderer);
        double elapsed =
            (double)(SDL_GetPerformanceCounter() - tick) / SDL_GetPerformanceFrequency();
        double target = scene == PLAY && !game.paused && !game.over ? 1.0 / 60 : 1.0 / 30;
        if (elapsed < target)
            SDL_Delay((Uint32)((target - elapsed) * 1000));
    }
    if (scene == PLAY)
        remember_score();
    save_settings();
    SDL_AtomicSet(&scan_stop, 1);
    if (scan_thread)
        SDL_WaitThread(scan_thread, NULL);
    if (probe_thread)
        SDL_WaitThread(probe_thread, NULL);
    SDL_DestroyMutex(usb_lock);
    audio_destroy();
    if (pad)
        SDL_JoystickClose(pad);
    video_destroy();
    SDL_Quit();
    control_close();
    return restart_requested ? 75 : 0;
}
