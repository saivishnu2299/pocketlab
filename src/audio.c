#include "audio.h"
#include <SDL.h>
#include <math.h>
#include <string.h>
typedef struct {
    float phase, age, duration, freq, end, volume;
    int noise;
} Voice;
static Voice voices[12];
static SDL_AudioDeviceID device;
static bool enabled = true;
static unsigned rng = 177;
static void callback(void *ctx, Uint8 *stream, int len) {
    (void)ctx;
    Sint16 *out = (Sint16 *)stream;
    for (int i = 0; i < len / 2; i++) {
        float sample = 0;
        for (int k = 0; k < 12; k++) {
            Voice *v = &voices[k];
            if (v->age >= v->duration)
                continue;
            float t = v->age / v->duration;
            v->phase += (v->freq + (v->end - v->freq) * t) / 44100;
            v->phase -= floorf(v->phase);
            rng = rng * 1664525u + 1013904223u;
            float wave = v->noise ? ((rng >> 16) / 32768.0f - 1) : sinf(v->phase * 6.2831853f);
            float env = (1 - t) * (1 - t) * fminf(1, v->age * 500);
            sample += wave * env * v->volume;
            v->age += 1 / 44100.0f;
        }
        out[i] = (Sint16)(fmaxf(-1, fminf(1, sample)) * (enabled ? 12000 : 0));
    }
}
bool audio_init(void) {
    SDL_AudioSpec want = {0}, got;
    want.freq = 44100;
    want.format = AUDIO_S16SYS;
    want.channels = 1;
    want.samples = 1024;
    want.callback = callback;
    device = SDL_OpenAudioDevice(NULL, 0, &want, &got, 0);
    if (device)
        SDL_PauseAudioDevice(device, 0);
    return device != 0;
}
void audio_destroy(void) {
    if (device) {
        SDL_CloseAudioDevice(device);
        device = 0;
    }
}
void audio_enable(bool on) {
    if (device)
        SDL_LockAudioDevice(device);
    enabled = on;
    if (device)
        SDL_UnlockAudioDevice(device);
}
void sound(int type) {
    if (!device)
        return;
    SDL_LockAudioDevice(device);
    int slot = 0;
    for (int k = 0; k < 12; k++)
        if (voices[k].age >= voices[k].duration) {
            slot = k;
            break;
        }
    Voice v = {0};
    v.volume = .2f;
    v.duration = .07f;
    v.freq = 720;
    v.end = 440;
    switch (type) {
    case 1:
        v.freq = 1100;
        v.end = 250;
        v.duration = .12f;
        v.volume = .09f;
        break;
    case 2:
        v.noise = 1;
        v.duration = .28f;
        v.volume = .4f;
        break;
    case 3:
        v.noise = 1;
        v.duration = .55f;
        v.volume = .65f;
        break;
    case 4:
        v.freq = 420;
        v.end = 1000;
        v.duration = .5f;
        v.volume = .25f;
        break;
    case 5:
        v.freq = 180;
        v.end = 700;
        v.duration = .35f;
        break;
    case 6:
        v.freq = 980;
        v.end = 1150;
        v.duration = .08f;
        break;
    }
    voices[slot] = v;
    SDL_UnlockAudioDevice(device);
}
