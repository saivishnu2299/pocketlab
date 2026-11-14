#include "cover.h"
#include <limits.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static uint32_t le32(const unsigned char *p) {
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}
static unsigned le16(const unsigned char *p) {
    return p[0] | (unsigned)p[1] << 8;
}

/* Validate dimensions and pixel extent before SDL allocates any image memory. */
static SDL_Surface *read_bmp(const char *path) {
    SDL_RWops *file = SDL_RWFromFile(path, "rb");
    if (!file)
        return NULL;
    unsigned char h[54];
    Sint64 bytes = SDL_RWsize(file);
    if (bytes < 54 || bytes > 4 * 1024 * 1024 || SDL_RWread(file, h, 1, sizeof h) != sizeof h)
        goto invalid;
    uint32_t offset = le32(h + 10), dib = le32(h + 14), width = le32(h + 18);
    int32_t signed_height = (int32_t)le32(h + 22);
    unsigned bits = le16(h + 28), compression = le32(h + 30);
    if (h[0] != 'B' || h[1] != 'M' || dib < 40 || dib > 124 || width < 1 || width > 1024 ||
        signed_height == 0 || signed_height < -768 || signed_height > 768 || le16(h + 26) != 1 ||
        (bits != 24 && bits != 32) || (compression != 0 && !(bits == 32 && compression == 3)) ||
        offset < 14 + dib || offset > (uint32_t)bytes)
        goto invalid;
    uint32_t height = (uint32_t)(signed_height < 0 ? -signed_height : signed_height);
    uint32_t stride = ((width * bits + 31) / 32) * 4;
    if ((uint64_t)offset + (uint64_t)stride * height > (uint64_t)bytes)
        goto invalid;
    SDL_RWseek(file, 0, RW_SEEK_SET);
    return SDL_LoadBMP_RW(file, 1);
invalid:
    SDL_RWclose(file);
    return NULL;
}

/* Old or hand-installed apps still receive a stable, colorful visual identity.
   This is local procedural artwork, with no model, runtime, or network service. */
static SDL_Surface *fallback(const char *id, const char *name) {
    uint32_t hash = 2166136261u;
    for (const char *s = id; *s; s++)
        hash = (hash ^ (unsigned char)*s) * 16777619u;
    for (const char *s = name; *s; s++)
        hash = (hash ^ (unsigned char)*s) * 16777619u;
    SDL_Surface *s = SDL_CreateRGBSurfaceWithFormat(0, 480, 192, 32, SDL_PIXELFORMAT_ARGB8888);
    if (!s)
        return NULL;
    Uint32 bg = SDL_MapRGB(s->format, 24 + (hash & 15), 24 + ((hash >> 4) & 15), 43);
    SDL_FillRect(s, NULL, bg);
    Uint8 colors[3][3] = {{127 + (hash % 100), 203, 193}, {245, 176, 124}, {167, 160, 230}};
    bool blocks = strstr(id, "block") != NULL;
    for (int x = 26; x < 454; x++) {
        for (int band = 0; band < 5; band++) {
            float y = 96 + sinf(x * .016f + band * .55f + (hash % 100) * .1f) * (32 + band * 9);
            if (blocks)
                y = 40 + band * 25 + ((x / 25 + band) % 3) * 6;
            SDL_Rect mark = {x, (int)y, blocks ? 2 : 1, blocks ? 18 : 3};
            Uint8 *c = colors[band % 3];
            SDL_FillRect(s, &mark, SDL_MapRGB(s->format, c[0], c[1], c[2]));
        }
    }
    return s;
}

void cover_load(Cover *cover, SDL_Renderer *renderer, const char *directory, const char *id,
                const char *name) {
    if (cover->checked)
        return;
    cover->checked = true;
    char path[PATH_MAX];
    SDL_Surface *surface = NULL;
    int n = snprintf(path, sizeof path, "%s/cover.bmp", directory);
    if (n > 0 && n < (int)sizeof path)
        surface = read_bmp(path);
    cover->from_file = surface != NULL;
    if (!surface)
        surface = fallback(id, name);
    if (surface) {
        cover->texture = SDL_CreateTextureFromSurface(renderer, surface);
        static unsigned logged;
        if (cover->texture && logged < 24) {
            fprintf(stderr, "Library artwork: %s source=%s size=%dx%d\n", id,
                    cover->from_file ? "cover.bmp" : "generated", surface->w, surface->h);
            logged++;
        }
        SDL_FreeSurface(surface);
    }
}

void cover_draw(const Cover *cover, SDL_Renderer *renderer, const SDL_Rect *area) {
    if (!cover->texture)
        return;
    int w, h;
    if (SDL_QueryTexture(cover->texture, NULL, NULL, &w, &h))
        return;
    SDL_Rect crop = {0, 0, w, h};
    if ((int64_t)w * area->h > (int64_t)h * area->w) {
        crop.w = h * area->w / area->h;
        if (crop.w < 1)
            crop.w = 1;
        crop.x = (w - crop.w) / 2;
    } else {
        crop.h = w * area->h / area->w;
        if (crop.h < 1)
            crop.h = 1;
        crop.y = (h - crop.h) / 2;
    }
    if (crop.w > 0 && crop.h > 0)
        SDL_RenderCopy(renderer, cover->texture, &crop, area);
}

void cover_free(Cover *cover) {
    if (cover->texture)
        SDL_DestroyTexture(cover->texture);
    memset(cover, 0, sizeof *cover);
}
