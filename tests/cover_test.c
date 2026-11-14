#include "../src/cover.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static uint32_t draw_hash(Cover *cover, SDL_Renderer *r) {
    SDL_SetRenderDrawColor(r, 0, 0, 0, 255);
    SDL_RenderClear(r);
    SDL_Rect area = {24, 24, 412, 164};
    cover_draw(cover, r, &area);
    uint32_t pixels[480 * 192], hash = 2166136261u;
    assert(SDL_RenderReadPixels(r, NULL, SDL_PIXELFORMAT_ARGB8888, pixels, 480 * 4) == 0);
    for (unsigned i = 0; i < 480 * 192; i++)
        hash = (hash ^ pixels[i]) * 16777619u;
    return hash;
}
int main(int argc, char **argv) {
    assert(argc == 2);
    assert(SDL_Init(SDL_INIT_VIDEO) == 0);
    SDL_Surface *s = SDL_CreateRGBSurfaceWithFormat(0, 480, 192, 32, SDL_PIXELFORMAT_ARGB8888);
    assert(s);
    for (int pass = 0; pass < 3; pass++) {
        SDL_Renderer *r = SDL_CreateSoftwareRenderer(s);
        assert(r);
        const char *cases[] = {"good",     "huge",     "truncated", "missing",
                               "negative", "bad-bits", "offset",    "top-down"};
        for (unsigned i = 0; i < sizeof cases / sizeof cases[0]; i++) {
            char path[4096];
            snprintf(path, sizeof path, "%s/%s", argv[1], cases[i]);
            Cover c = {0};
            cover_load(&c, r, path, "test-app", "Test app");
            assert(c.checked && c.texture);
            assert(c.from_file == (i == 0 || i == 7));
            uint32_t hash = draw_hash(&c, r);
            SDL_Texture *original = c.texture;
            cover_load(&c, r, path, "test-app", "Test app");
            assert(c.texture == original && draw_hash(&c, r) == hash);
            cover_free(&c);
            assert(!c.checked && !c.texture && !c.from_file);
        }
        Cover a = {0}, b = {0};
        cover_load(&a, r, "/nonexistent", "first-project", "First project");
        cover_load(&b, r, "/nonexistent", "second-project", "Second project");
        assert(draw_hash(&a, r) != draw_hash(&b, r));
        cover_free(&a);
        cover_free(&b);
        SDL_DestroyRenderer(r);
    }
    SDL_FreeSurface(s);
    SDL_Quit();
    puts("Cover decoding, bounds, fallback identity, caching and renderer lifecycle passed.");
    return 0;
}
