#include "ui.h"
#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define STB_TRUETYPE_IMPLEMENTATION
#include "../vendor/stb_truetype.h"
SDL_Renderer *renderer;
const Color PAPER = {241, 240, 233, 255}, INK = {28, 39, 43, 255}, MUTED = {105, 118, 118, 255};
const Color BLUE = {50, 77, 221, 255}, MINT = {173, 242, 207, 255}, NIGHT = {13, 20, 33, 255},
            LINE = {211, 217, 207, 255};
typedef struct {
    SDL_Texture *texture;
    stbtt_bakedchar chars[96];
    float ascent;
    int size;
} Font;
static Font fonts[3][8];
static bool mono_mode;
static const int sizes[] = {15, 18, 22, 28, 36, 48, 64, 84};
float clampf(float x, float a, float b) {
    return x < a ? a : x > b ? b : x;
}
static void color(Color c) {
    SDL_SetRenderDrawColor(renderer, c.r, c.g, c.b, c.a);
}
bool ui_init(const char *dir) {
    for (int b = 0; b < 3; b++) {
        char path[1024];
        snprintf(path, sizeof path, "%s/%s", dir,
                 b == 2 ? "IBMPlexMono-Regular.ttf"
                 : b    ? "Barlow-SemiBold.ttf"
                        : "Barlow-Regular.ttf");
        FILE *f = fopen(path, "rb");
        if (!f)
            return false;
        fseek(f, 0, SEEK_END);
        long len = ftell(f);
        rewind(f);
        unsigned char *buf = malloc((size_t)len);
        if (!buf) {
            fclose(f);
            return false;
        }
        if (fread(buf, 1, (size_t)len, f) != (size_t)len) {
            free(buf);
            fclose(f);
            return false;
        }
        fclose(f);
        stbtt_fontinfo info;
        if (!stbtt_InitFont(&info, buf, 0)) {
            free(buf);
            return false;
        }
        int ascent;
        stbtt_GetFontVMetrics(&info, &ascent, NULL, NULL);
        for (int k = 0; k < 8; k++) {
            Font *font = &fonts[b][k];
            font->size = sizes[k];
            font->ascent = ascent * stbtt_ScaleForPixelHeight(&info, (float)sizes[k]);
            unsigned char *bitmap = calloc(1024 * 512, 1);
            if (!bitmap) {
                free(buf);
                return false;
            }
            int ok = stbtt_BakeFontBitmap(buf, 0, (float)sizes[k], bitmap, 1024, 512, 32, 96,
                                          font->chars);
            if (ok <= 0) {
                free(bitmap);
                free(buf);
                return false;
            }
            SDL_Surface *s =
                SDL_CreateRGBSurfaceWithFormat(0, 1024, 512, 32, SDL_PIXELFORMAT_RGBA32);
            if (!s) {
                free(bitmap);
                free(buf);
                return false;
            }
            unsigned char *p = s->pixels;
            for (int i = 0; i < 1024 * 512; i++) {
                p[4 * i] = p[4 * i + 1] = p[4 * i + 2] = 255;
                p[4 * i + 3] = bitmap[i];
            }
            font->texture = SDL_CreateTextureFromSurface(renderer, s);
            SDL_SetTextureBlendMode(font->texture, SDL_BLENDMODE_BLEND);
            SDL_FreeSurface(s);
            free(bitmap);
            if (!font->texture) {
                free(buf);
                return false;
            }
        }
        free(buf);
    }
    return true;
}
void ui_destroy(void) {
    for (int b = 0; b < 3; b++)
        for (int k = 0; k < 8; k++) {
            SDL_DestroyTexture(fonts[b][k].texture);
            fonts[b][k].texture = NULL;
        }
}
static Font *getfont(int size, bool bold) {
    int i = 0;
    while (i < 7 && sizes[i] < size)
        i++;
    return &fonts[mono_mode ? 2 : bold ? 1 : 0][i];
}
void fill(float x, float y, float w, float h, Color c) {
    color(c);
    SDL_FRect r = {x, y, w, h};
    SDL_RenderFillRectF(renderer, &r);
}
void line(float x, float y, float x2, float y2, Color c) {
    color(c);
    SDL_RenderDrawLineF(renderer, x, y, x2, y2);
}
void circle(float x, float y, float r, Color c) {
    color(c);
    for (int yy = -(int)r; yy <= (int)r; yy++) {
        float a = sqrtf(fmaxf(0, r * r - yy * yy));
        SDL_RenderDrawLineF(renderer, x - a, y + yy, x + a, y + yy);
    }
}
void roundrect(float x, float y, float w, float h, float r, Color c) {
    r = fminf(r, fminf(w, h) / 2);
    color(c);
    for (int yy = 0; yy < (int)h; yy++) {
        float dy = yy < r ? r - yy : yy >= h - r ? yy - (h - r - 1) : 0;
        float inset = dy > 0 ? r - sqrtf(fmaxf(0, r * r - dy * dy)) : 0;
        SDL_RenderDrawLineF(renderer, x + inset, y + yy, x + w - 1 - inset, y + yy);
    }
}
void outline(float x, float y, float w, float h, float r, Color c, int thickness) {
    for (int i = 0; i < thickness; i++) {
        line(x + r, y + i, x + w - r, y + i, c);
        line(x + r, y + h - 1 - i, x + w - r, y + h - 1 - i, c);
        line(x + i, y + r, x + i, y + h - r, c);
        line(x + w - 1 - i, y + r, x + w - 1 - i, y + h - r, c);
        for (int j = 0; j <= 90; j++) {
            float a = j * 0.0174532925f, rr = r - i;
            float dx = cosf(a) * rr, dy = sinf(a) * rr;
            color(c);
            SDL_RenderDrawPointF(renderer, x + r - dx, y + r - dy);
            SDL_RenderDrawPointF(renderer, x + w - r + dx - 1, y + r - dy);
            SDL_RenderDrawPointF(renderer, x + r - dx, y + h - r + dy - 1);
            SDL_RenderDrawPointF(renderer, x + w - r + dx - 1, y + h - r + dy - 1);
        }
    }
}
void triangle(float x1, float y1, float x2, float y2, float x3, float y3, Color c) {
    float miny = fminf(y1, fminf(y2, y3)), maxy = fmaxf(y1, fmaxf(y2, y3));
    for (int yy = (int)miny; yy <= maxy; yy++) {
        float xs[3];
        int n = 0;
        float vx[] = {x1, x2, x3}, vy[] = {y1, y2, y3};
        for (int j = 0; j < 3; j++) {
            int k = (j + 1) % 3;
            if ((vy[j] <= yy && vy[k] > yy) || (vy[k] <= yy && vy[j] > yy))
                xs[n++] = vx[j] + (yy - vy[j]) / (vy[k] - vy[j]) * (vx[k] - vx[j]);
        }
        if (n >= 2)
            line(fminf(xs[0], xs[1]), yy, fmaxf(xs[0], xs[1]), yy, c);
    }
}
float text_width(const char *s, int size, bool bold) {
    Font *f = getfont(size, bold);
    float w = 0;
    for (const unsigned char *p = (const unsigned char *)s; *p; p++) {
        if (*p >= 32 && *p < 128)
            w += f->chars[*p - 32].xadvance;
    }
    return w * (float)size / f->size;
}
void text(float x, float y, int size, bool bold, Color c, const char *s) {
    Font *f = getfont(size, bold);
    float sc = (float)size / f->size, pen = x;
    SDL_SetTextureColorMod(f->texture, c.r, c.g, c.b);
    SDL_SetTextureAlphaMod(f->texture, c.a);
    for (const unsigned char *p = (const unsigned char *)s; *p; p++) {
        unsigned int v = *p;
        if (v < 32 || v >= 128)
            v = '?';
        stbtt_bakedchar *g = &f->chars[v - 32];
        SDL_Rect src = {g->x0, g->y0, g->x1 - g->x0, g->y1 - g->y0};
        SDL_FRect dst = {pen + g->xoff * sc, y + (f->ascent + g->yoff) * sc, src.w * sc,
                         src.h * sc};
        SDL_RenderCopyF(renderer, f->texture, &src, &dst);
        pen += g->xadvance * sc;
    }
}
void text_fit(float x, float y, float maxw, int size, bool bold, Color c, const char *s) {
    char b[512];
    snprintf(b, sizeof b, "%s", s);
    if (text_width(b, size, bold) > maxw) {
        size_t n = strlen(b);
        while (n && text_width(b, size, bold) + text_width("...", size, bold) > maxw)
            b[--n] = 0;
        strncat(b, "...", sizeof b - strlen(b) - 1);
    }
    text(x, y, size, bold, c, b);
}
void textf(float x, float y, int size, bool bold, Color c, const char *fmt, ...) {
    char b[512];
    va_list a;
    va_start(a, fmt);
    vsnprintf(b, sizeof b, fmt, a);
    va_end(a);
    text(x, y, size, bold, c, b);
}
void mono(float x, float y, int size, Color c, const char *s) {
    mono_mode = true;
    text(x, y, size, false, c, s);
    mono_mode = false;
}
void wrapped(float x, float y, float maxw, int size, Color c, const char *s) {
    char copy[1024];
    snprintf(copy, sizeof copy, "%s", s);
    char row[512] = "";
    char *save = NULL;
    for (char *word = strtok_r(copy, " ", &save); word; word = strtok_r(NULL, " ", &save)) {
        char next[512];
        snprintf(next, sizeof next, "%s%s%s", row, row[0] ? " " : "", word);
        if (text_width(next, size, false) > maxw && row[0]) {
            text(x, y, size, false, c, row);
            y += size * 1.35f;
            snprintf(row, sizeof row, "%s", word);
        } else
            snprintf(row, sizeof row, "%s", next);
    }
    if (row[0])
        text(x, y, size, false, c, row);
}
void keycap(float x, float y, const char *key, const char *label, bool dark) {
    Color fg = dark ? PAPER : INK, bg = dark ? RGB(41, 51, 66) : RGB(222, 226, 215);
    float w = fmaxf(28, text_width(key, 15, true) + 14);
    roundrect(x, y, w, 27, 7, bg);
    text(x + (w - text_width(key, 15, true)) / 2, y + 5, 15, true, fg, key);
    text(x + w + 9, y + 4, 18, false, fg, label);
}
void chip_art(float x, float y, float s, Color body, Color accent, float t, bool connected) {
    roundrect(x - 72 * s, y - 102 * s, 144 * s, 204 * s, 14 * s, body);
    for (int j = 0; j < 12; j++) {
        float yy = y - 78 * s + j * 14 * s;
        fill(x - 80 * s, yy, 14 * s, 5 * s, accent);
        fill(x + 66 * s, yy, 14 * s, 5 * s, accent);
    }
    roundrect(x - 49 * s, y - 70 * s, 98 * s, 99 * s, 7 * s, RGB(184, 195, 182));
    roundrect(x - 38 * s, y - 58 * s, 76 * s, 51 * s, 3 * s, RGB(26, 43, 42));
    for (int j = 0; j < 4; j++)
        line(x - 29 * s, y - 46 * s + j * 9 * s, x + (j % 2 ? 15 : 29) * s, y - 46 * s + j * 9 * s,
             RGB(106, 134, 121));
    fill(x - 24 * s, y + 45 * s, 48 * s, 30 * s, RGB(21, 37, 37));
    roundrect(x - 18 * s, y + 86 * s, 36 * s, 27 * s, 5 * s, RGB(179, 190, 179));
    roundrect(x - 12 * s, y + 92 * s, 24 * s, 12 * s, 4 * s, RGB(32, 43, 42));
    circle(x + 45 * s, y + 53 * s, 4 * s, connected ? MINT : RGB(107, 134, 120));
    if (connected)
        circle(x + 45 * s, y + 53 * s, (7 + 2 * sinf(t * 3)) * s, RGBA(173, 242, 207, 60));
    for (int j = 0; j < 2; j++) {
        circle(x + (-53 + j * 106) * s, y + 86 * s, 4 * s, accent);
        circle(x + (-53 + j * 106) * s, y - 86 * s, 4 * s, accent);
    }
}
static const char *sprites[4][12] = {
    {".....11.....", ".....11.....", "....1221....", "....1221....", "..11122111..", "..12222221..",
     ".1122222211.", "112222222211", "112111111211", "11..1331..11", "....1331....",
     ".....33....."},
    {"..1......1..", "...1....1...", "..11111111..", ".1122112211.", "111221122111", "112222222211",
     "111111111111", "11..1111..11", "1...1..1...1", "....1..1....", "............",
     "............"},
    {".....11.....", "...111111...", "..11222211..", "111221122111", "112222222211", ".1111111111.",
     "..11222211..", "...111111...", "..11....11..", ".11......11.", "............",
     "............"},
    {"..11....11..", ".1111..1111.", "112211112211", "112222222211", "111222222111", ".1112222111.",
     "..11111111..", "...112211...", "....1111....", ".....11.....", "............",
     "............"}};
void ship_art(float x, float y, float s, int type, Color c) {
    for (int j = 0; j < 12; j++)
        for (int i = 0; i < 12; i++) {
            char k = sprites[type % 4][j][i];
            if (k == '.')
                continue;
            Color d = c;
            if (k == '2')
                d = type == 0 ? RGB(235, 245, 240)
                              : RGB((c.r + 255) / 2, (c.g + 255) / 2, (c.b + 255) / 2);
            if (k == '3')
                d = RGB(255, 150, 76);
            fill(x + (i - 6) * s, y + (j - 6) * s, s, s, d);
        }
}
void stars(float t, float x, float y, float w, float h, int count, float alpha) {
    uint32_t seed = 73429;
    for (int i = 0; i < count; i++) {
        seed = seed * 1664525u + 1013904223u;
        float xx = (seed % 10000) / 10000.0f * w;
        seed = seed * 1664525u + 1013904223u;
        float yy = fmodf((seed % 10000) / 10000.0f * h + t * (5 + i % 4 * 8), h);
        int sz = i % 13 == 0 ? 3 : 1;
        fill(x + xx, y + yy, sz, sz, RGBA(196, 217, 229, (int)(alpha * (80 + (i % 5) * 30))));
    }
}
