#ifndef POCKET_AUDIO_H
#define POCKET_AUDIO_H
#include <stdbool.h>
bool audio_init(void);
void audio_destroy(void);
void audio_enable(bool on);
void sound(int type);
#endif
