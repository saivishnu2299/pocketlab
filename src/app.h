#ifndef POCKET_APP_SDK_H
#define POCKET_APP_SDK_H
/* Call after presenting the first usable frame. Tell the deploy tool this app
 * supports readiness with "ready": "file" in app.json. */
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
static inline int pocketlab_ready(void) {
    const char *path = getenv("POCKETLAB_READY_FILE"), *session = getenv("POCKETLAB_SESSION");
    if (!path || !session)
        return 0;
    char tmp[4096];
    snprintf(tmp, sizeof tmp, "%s.tmp", path);
    FILE *f = fopen(tmp, "w");
    if (!f)
        return -1;
    int ok = fprintf(f, "%s\n", session) > 0 && fflush(f) == 0;
    if (ok)
        ok = fsync(fileno(f)) == 0;
    if (fclose(f))
        ok = 0;
    return ok ? rename(tmp, path) : -1;
}
#endif
