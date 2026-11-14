#ifndef POCKET_UI_H
#define POCKET_UI_H
#include <SDL.h>
#include <stdbool.h>
#include <stdint.h>
typedef struct {
    Uint8 r, g, b, a;
} Color;
#define RGB(r, g, b) ((Color){r, g, b, 255})
#define RGBA(r, g, b, a) ((Color){r, g, b, a})
extern SDL_Renderer *renderer;
extern const Color PAPER, INK, MUTED, BLUE, MINT, NIGHT, LINE;
bool ui_init(const char *asset_dir);
void ui_destroy(void);
void fill(float x, float y, float w, float h, Color c);
void line(float x, float y, float x2, float y2, Color c);
void circle(float x, float y, float radius, Color c);
void roundrect(float x, float y, float w, float h, float radius, Color c);
void outline(float x, float y, float w, float h, float r, Color c, int thickness);
void triangle(float x1, float y1, float x2, float y2, float x3, float y3, Color c);
float text_width(const char *s, int size, bool bold);
void text(float x, float y, int size, bool bold, Color c, const char *s);
void text_fit(float x, float y, float maxw, int size, bool bold, Color c, const char *s);
void textf(float x, float y, int size, bool bold, Color c, const char *fmt, ...);
void mono(float x, float y, int size, Color c, const char *s);
void wrapped(float x, float y, float maxw, int size, Color c, const char *s);
void keycap(float x, float y, const char *key, const char *label, bool dark);
void chip_art(float x, float y, float scale, Color body, Color accent, float time, bool connected);
void ship_art(float x, float y, float scale, int type, Color color);
void stars(float time, float x, float y, float w, float h, int count, float alpha);
float clampf(float x, float low, float high);
#endif
