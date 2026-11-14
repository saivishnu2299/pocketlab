#include "game.h"
#include <math.h>
#include <string.h>
static float randomf(Game *g) {
    g->rng = g->rng * 1664525u + 1013904223u;
    return (g->rng >> 8) / 16777216.0f;
}
static float bound(float x, float a, float b) {
    return x < a ? a : x > b ? b : x;
}
static void burst(Game *g, float x, float y, int count, int color) {
    for (int i = 0; i < PARTICLES && count; i++) {
        Particle *p = &g->particles[i];
        if (p->life > 0)
            continue;
        float a = randomf(g) * 6.2831853f, v = 40 + randomf(g) * 200;
        p->x = x;
        p->y = y;
        p->vx = cosf(a) * v;
        p->vy = sinf(a) * v;
        p->life = p->maxlife = .25f + randomf(g) * .65f;
        p->color = color;
        count--;
    }
}
static void bullet(Game *g, float x, float y, float vx, float vy, bool enemy) {
    for (int i = 0; i < BULLETS; i++)
        if (!g->bullets[i].active) {
            g->bullets[i] = (Bullet){x, y, vx, vy, 1, enemy};
            return;
        }
}
static void wave(Game *g) {
    g->wave++;
    int cols = 8, rows = 3 + (g->wave > 2);
    memset(g->enemies, 0, sizeof g->enemies);
    for (int i = 0; i < cols * rows; i++) {
        Enemy *e = &g->enemies[i];
        e->active = 1;
        e->type = i / cols % 3 + 1;
        e->hp = (e->type == 3 && g->wave > 3) ? 2 : 1;
        e->home_x = 190 + (i % cols) * 91;
        e->home_y = 155 + (i / cols) * 65;
        e->x = e->home_x;
        e->y = -80 - i * 16;
        e->age = -.045f * i;
    }
    g->shot_clock = 1.4f;
    g->wave_wait = 0;
    g->sounds |= S_WAVE;
    g->combo = 0;
}
void game_start(Game *g, int difficulty, unsigned seed) {
    memset(g, 0, sizeof *g);
    g->difficulty = difficulty;
    g->rng = seed ? seed : 1347;
    g->player_x = 512;
    g->lives = 3;
    g->invulnerable = 2;
    g->wave_wait = 1;
}
int game_alive(const Game *g) {
    int n = 0;
    for (int i = 0; i < ENEMIES; i++)
        n += g->enemies[i].active != 0;
    return n;
}
static void hurt(Game *g) {
    if (g->invulnerable > 0 || g->shield > 0)
        return;
    g->lives--;
    g->invulnerable = 2.3f;
    g->combo = 0;
    g->shake = 1;
    g->sounds |= S_HURT;
    burst(g, g->player_x, 641, 32, 2);
    if (g->lives <= 0) {
        g->over = true;
        g->lives = 0;
    }
}
void game_update(Game *g, float dt, float move, bool fire, bool shield) {
    g->sounds = 0;
    if (g->paused || g->over)
        return;
    dt = bound(dt, 0, .04f);
    g->time += dt;
    g->cooldown = fmaxf(0, g->cooldown - dt);
    g->invulnerable = fmaxf(0, g->invulnerable - dt);
    g->shield = fmaxf(0, g->shield - dt);
    g->shield_recharge = fmaxf(0, g->shield_recharge - dt);
    g->shake = fmaxf(0, g->shake - dt * 4);
    g->player_x = bound(g->player_x + move * 450 * dt, 116, 908);
    if (shield && g->shield_recharge <= 0) {
        g->shield = 2;
        g->shield_recharge = 9;
        g->sounds |= S_SHIELD;
    }
    if (fire && g->cooldown <= 0) {
        bullet(g, g->player_x, 614, 0, -730, false);
        g->cooldown = .15f;
        g->shots++;
        g->sounds |= S_SHOOT;
    }
    if (!game_alive(g)) {
        if (g->wave_wait <= 0)
            g->wave_wait = 1.8f;
        g->wave_wait -= dt;
        if (g->wave_wait <= 0)
            wave(g);
    }
    for (int i = 0; i < ENEMIES; i++) {
        Enemy *e = &g->enemies[i];
        if (!e->active)
            continue;
        e->age += dt;
        if (e->age < 0)
            continue;
        if (e->age < 1.2f) {
            float u = 1 - powf(1 - e->age / 1.2f, 3);
            e->y = -60 + (e->home_y + 60) * u;
            e->x = e->home_x + sinf(e->age * 4 + i) * 60 * (1 - u);
        } else if (e->dive > 0) {
            e->dive += dt;
            float speed = 180 + g->wave * 10 + g->difficulty * 28;
            e->y += speed * dt;
            e->x += sinf(e->dive * 4 + i) * 155 * dt;
            if (e->y > 780) {
                e->dive = 0;
                e->y = -40;
                e->age = 0;
            }
        } else {
            e->x = e->home_x + sinf(g->time * .9f) * 43;
            e->y = e->home_y + sinf(g->time * 1.2f + i * .6f) * 8;
            if (randomf(g) <
                    dt * (.009f + fminf(g->wave, 12) * .003f) * (1 + g->difficulty * .4f) &&
                g->time > 4)
                e->dive = .01f;
        }
        if (fabsf(e->x - g->player_x) < 30 && fabsf(e->y - 641) < 27) {
            if (g->shield > 0) {
                e->active = 0;
                g->score += 100;
                g->kills++;
                burst(g, e->x, e->y, 18, 0);
            } else
                hurt(g);
        }
    }
    g->shot_clock -= dt;
    if (g->shot_clock <= 0) {
        int active[ENEMIES], n = 0;
        for (int i = 0; i < ENEMIES; i++)
            if (g->enemies[i].active && g->enemies[i].age > 1.3f && g->enemies[i].y < 570)
                active[n++] = i;
        if (n) {
            Enemy *e = &g->enemies[active[(int)(randomf(g) * n) % n]];
            float vy = 190 + g->difficulty * 45 + fminf(g->wave * 12, 150);
            float vx = bound((g->player_x - e->x) * .22f, -100, 100);
            bullet(g, e->x, e->y + 18, vx, vy, true);
        }
        g->shot_clock = fmaxf(.18f, 1.1f - g->wave * .045f - g->difficulty * .17f);
    }
    for (int i = 0; i < BULLETS; i++) {
        Bullet *b = &g->bullets[i];
        if (!b->active)
            continue;
        b->x += b->vx * dt;
        b->y += b->vy * dt;
        if (b->y < -30 || b->y > 780 || b->x < 0 || b->x > 1024) {
            b->active = 0;
            if (!b->enemy)
                g->combo = 0;
            continue;
        }
        if (b->enemy) {
            float radius = g->shield > 0 ? 54 : 21;
            if (fabsf(b->x - g->player_x) < radius && fabsf(b->y - 641) < radius) {
                b->active = 0;
                if (g->shield > 0)
                    burst(g, b->x, b->y, 8, 0);
                else
                    hurt(g);
            }
            continue;
        }
        for (int j = 0; j < ENEMIES; j++) {
            Enemy *e = &g->enemies[j];
            if (e->active && e->age > 0 && fabsf(b->x - e->x) < 25 && fabsf(b->y - e->y) < 23) {
                b->active = 0;
                e->hp--;
                g->hits++;
                if (e->hp <= 0) {
                    e->active = 0;
                    g->combo++;
                    if (g->combo > g->best_combo)
                        g->best_combo = g->combo;
                    g->score += (50 + e->type * 25) * (1 + g->combo / 8);
                    g->kills++;
                    g->sounds |= S_EXPLODE;
                    burst(g, e->x, e->y, 20, e->type % 3);
                }
                break;
            }
        }
    }
    for (int i = 0; i < PARTICLES; i++) {
        Particle *p = &g->particles[i];
        if (p->life <= 0)
            continue;
        p->life -= dt;
        p->x += p->vx * dt;
        p->y += p->vy * dt;
        p->vx *= 1 - dt * 2;
        p->vy *= 1 - dt * 2;
    }
}
