#ifndef POCKET_COVER_H
#define POCKET_COVER_H
#include <SDL.h>
#include <stdbool.h>

typedef struct {
    SDL_Texture *texture;
    bool checked, from_file;
} Cover;

/* Loading is lazy; callers release covers before destroying their renderer. */
void cover_load(Cover *cover, SDL_Renderer *renderer, const char *directory, const char *id,
                const char *name);
void cover_draw(const Cover *cover, SDL_Renderer *renderer, const SDL_Rect *area);
void cover_free(Cover *cover);
#endif
