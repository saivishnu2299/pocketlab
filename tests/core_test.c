#include "../src/game.h"
#include "../src/usb.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static void game_tests(void) {
    Game g;
    game_start(&g, 1, 42);
    assert(g.lives == 3 && g.player_x == 512 && g.wave == 0);
    for (int i = 0; i < 100; i++)
        game_update(&g, 1.0f / 60, -1, false, false);
    assert(g.player_x == 116 && g.wave == 1 && game_alive(&g) == 24);
    for (int i = 0; i < 150; i++)
        game_update(&g, 1.0f / 60, 1, false, false);
    assert(g.player_x == 908);
    g.paused = true;
    float before = g.time;
    int shots = g.shots;
    game_update(&g, .04f, -1, true, true);
    assert(g.time == before && g.player_x == 908 && g.shots == shots);
    g.paused = false;
    game_update(&g, 0, 0, false, true);
    assert(g.shield == 2 && g.shield_recharge == 9);
    game_update(&g, .04f, 0, false, true);
    assert(g.shield < 2 && g.shield_recharge < 9);

    game_start(&g, 0, 42);
    g.wave = 1;
    g.enemies[0] = (Enemy){.active = 1, .type = 1, .hp = 1, .age = 2, .home_x = 512, .home_y = 200};
    g.bullets[0] = (Bullet){.x = 512, .y = 200, .active = 1};
    game_update(&g, 0, 0, false, false);
    assert(g.kills == 1 && g.score == 75 && g.combo == 1 && g.hits == 1);
    for (int i = 0; i < 120; i++)
        game_update(&g, 1.0f / 60, 0, false, false);
    assert(g.wave == 2 && game_alive(&g) == 24);
    memset(g.enemies, 0, sizeof g.enemies);
    g.wave_wait = .01f;
    game_update(&g, .02f, 0, false, false);
    assert(g.wave == 3 && game_alive(&g) == 32);

    game_start(&g, 1, 42);
    g.invulnerable = 0;
    g.bullets[0] = (Bullet){.x = 512, .y = 641, .active = 1, .enemy = 1};
    game_update(&g, 0, 0, false, true);
    assert(g.lives == 3 && !g.bullets[0].active);
    g.shield = 0;
    for (int i = 0; i < 3; i++) {
        g.invulnerable = 0;
        g.bullets[0] = (Bullet){.x = 512, .y = 641, .active = 1, .enemy = 1};
        game_update(&g, 0, 0, false, false);
        assert(g.lives == 2 - i);
    }
    assert(g.over);
    before = g.time;
    game_update(&g, .04f, 1, true, true);
    assert(g.time == before && g.lives == 0);

    for (int level = 0; level < 3; level++) {
        game_start(&g, level, 12345);
        for (int i = 0; i < 60000; i++) {
            if (g.over)
                game_start(&g, level, (unsigned)i + 1);
            game_update(&g, 1.0f / 60, sinf(i * .005f), true, i % 600 == 0);
            assert(isfinite(g.player_x) && g.player_x >= 116 && g.player_x <= 908);
            assert(g.lives >= 0 && g.lives <= 3 && g.score >= 0);
            for (int j = 0; j < ENEMIES; j++)
                assert(isfinite(g.enemies[j].x) && isfinite(g.enemies[j].y));
        }
    }
}
static void usb_tests(void) {
    assert(usb_classify(0x303a, 0x1001, "USB JTAG/serial debug unit", "Espressif") ==
           USB_ESPRESSIF);
    assert(usb_classify(0x303a, 0x1001, "ESP32-S3", "Espressif") == USB_ESP32);
    assert(usb_classify(0x10c4, 0xea60, "CP2102 USB to UART Bridge", "Silicon Labs") == USB_SERIAL);
    assert(usb_classify(0x1a86, 0x7523, "USB2.0-Serial", "WCH") == USB_SERIAL);
    assert(usb_classify(0x0403, 0x6001, "FT232R USB UART", "FTDI") == USB_SERIAL);
    assert(usb_classify(0x046d, 0x1234, "USB Keyboard", "Logitech") == USB_OTHER);
    assert(usb_classify(0x1234, 0x0001, NULL, NULL) == USB_OTHER);
    UsbDevice a = {.vid = 0x10c4, .pid = 0xea60, .instance = 7};
    strcpy(a.id, "1-1");
    strcpy(a.serial, "ABCD");
    char first[512], next[512];
    usb_identity(&a, first, sizeof first);
    a.instance++;
    usb_identity(&a, next, sizeof next);
    assert(strcmp(first, next));
    a.instance--;
    strcpy(a.serial, "OTHER");
    usb_identity(&a, next, sizeof next);
    assert(strcmp(first, next));
}
int main(void) {
    game_tests();
    usb_tests();
    puts("Core: gameplay, 180,000 simulation frames, USB classification and connection identity "
         "passed.");
}
