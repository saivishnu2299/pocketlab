#ifndef POCKET_GAME_H
#define POCKET_GAME_H
#include <stdbool.h>
#define ENEMIES 40
#define BULLETS 128
#define PARTICLES 320
typedef struct {
    float x, y, vx, vy;
    int active, enemy;
} Bullet;
typedef struct {
    float x, y, age, home_x, home_y;
    int active, type, hp;
    float dive;
} Enemy;
typedef struct {
    float x, y, vx, vy, life, maxlife;
    int color;
} Particle;
typedef struct {
    float time, player_x, cooldown, invulnerable, wave_wait, shot_clock, shield, shield_recharge,
        shake;
    int score, wave, lives, kills, shots, hits, combo, best_combo, difficulty;
    bool over, paused;
    unsigned rng;
    Enemy enemies[ENEMIES];
    Bullet bullets[BULLETS];
    Particle particles[PARTICLES];
    int sounds;
} Game;
enum { S_SHOOT = 1, S_EXPLODE = 2, S_HURT = 4, S_WAVE = 8, S_SHIELD = 16 };
void game_start(Game *g, int difficulty, unsigned seed);
void game_update(Game *g, float dt, float move, bool fire, bool shield);
int game_alive(const Game *g);
#endif
