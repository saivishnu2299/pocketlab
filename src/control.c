#include "control.h"
#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
static char base[PATH_MAX], app_root[PATH_MAX], last_status[1024], instance[80];
static int lock_fd = -1;
static bool token_valid(const char *s) {
    if (strlen(s) != 32)
        return false;
    for (; *s; s++)
        if (!isxdigit((unsigned char)*s))
            return false;
    return true;
}
bool control_app_id(const char *s) {
    size_t n = strlen(s);
    if (!n || n > 48 || s[0] < 'a' || s[0] > 'z')
        return false;
    for (; *s; s++)
        if (!((*s >= 'a' && *s <= 'z') || (*s >= '0' && *s <= '9') || *s == '-'))
            return false;
    return true;
}
static bool write_atomic(const char *path, const char *text) {
    char tmp[PATH_MAX];
    snprintf(tmp, sizeof tmp, "%s.tmp", path);
    FILE *f = fopen(tmp, "w");
    if (!f)
        return false;
    bool ok = fputs(text, f) >= 0 && fflush(f) == 0;
    if (ok)
        ok = fsync(fileno(f)) == 0;
    if (fclose(f))
        ok = false;
    if (ok)
        ok = rename(tmp, path) == 0;
    if (!ok)
        unlink(tmp);
    return ok;
}
static void escaped(char *out, size_t cap, const char *s) {
    size_t n = 0;
    for (; *s && n + 3 < cap; s++) {
        unsigned char c = (unsigned char)*s;
        if (c == '"' || c == '\\')
            out[n++] = '\\';
        out[n++] = c >= 32 && c < 127 ? (char)c : ' ';
    }
    out[n] = 0;
}
void control_reply(const ControlRequest *r, bool ok, const char *message) {
    char path[PATH_MAX], body[1024], safe[512];
    escaped(safe, sizeof safe, message);
    snprintf(path, sizeof path, "%s/replies/%s.json", base, r->token);
    snprintf(body, sizeof body, "{\"token\":\"%s\",\"ok\":%s,\"message\":\"%s\"}\n", r->token,
             ok ? "true" : "false", safe);
    if (!write_atomic(path, body))
        fprintf(stderr, "Cannot write USB command reply: %s\n", strerror(errno));
}
bool control_init(const char *root) {
    snprintf(app_root, sizeof app_root, "%s/apps", root);
    snprintf(base, sizeof base, "%s/data/control", root);
    if (mkdir(base, 0755) && errno != EEXIST)
        return false;
    char path[PATH_MAX];
    snprintf(path, sizeof path, "%s/runtime.lock", base);
    lock_fd = open(path, O_CREAT | O_RDWR | O_CLOEXEC, 0644);
    if (lock_fd < 0 || flock(lock_fd, LOCK_EX | LOCK_NB))
        return false;
    snprintf(path, sizeof path, "%s/requests", base);
    if (mkdir(path, 0755) && errno != EEXIST)
        return false;
    snprintf(path, sizeof path, "%s/replies", base);
    if (mkdir(path, 0755) && errno != EEXIST)
        return false;
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    snprintf(instance, sizeof instance, "%ld-%ld-%ld", (long)getpid(), t.tv_sec, t.tv_nsec);
    last_status[0] = 0;
    /* Requests belong to one running instance, never replay them after a reboot. */
    ControlRequest r;
    while (control_read(&r))
        control_reply(&r, false, "PocketLAB restarted; send the command again.");
    control_ready_path(path, sizeof path);
    unlink(path);
    return true;
}
void control_close(void) {
    control_status("stopped", "", 0, "", false);
    if (lock_fd >= 0) {
        close(lock_fd);
        lock_fd = -1;
    }
}
void control_status(const char *state, const char *app, pid_t child, const char *session,
                    bool ready) {
    char path[PATH_MAX], body[1024];
    snprintf(body, sizeof body,
             "{\"protocol\":1,\"version\":\"1.1.0\",\"instance\":\"%s\",\"shell_pid\":%ld,"
             "\"state\":\"%s\",\"app\":\"%s\",\"child_pid\":%ld,\"session\":\"%s\",\"ready\":%s}\n",
             instance, (long)getpid(), state, app, (long)child, session, ready ? "true" : "false");
    if (!strcmp(body, last_status))
        return;
    snprintf(path, sizeof path, "%s/status.json", base);
    if (write_atomic(path, body))
        snprintf(last_status, sizeof last_status, "%s", body);
}
bool control_read(ControlRequest *r) {
    char path[PATH_MAX], folder[PATH_MAX];
    snprintf(folder, sizeof folder, "%s/requests", base);
    DIR *d = opendir(folder);
    if (!d)
        return false;
    struct dirent *e;
    while ((e = readdir(d))) {
        if (!token_valid(e->d_name))
            continue;
        memset(r, 0, sizeof *r);
        snprintf(r->token, sizeof r->token, "%s", e->d_name);
        snprintf(path, sizeof path, "%s/%s", folder, e->d_name);
        FILE *f = fopen(path, "r");
        if (!f)
            continue;
        char line[160], extra[8];
        bool ok = fgets(line, sizeof line, f) != NULL;
        int tail = fgetc(f);
        fclose(f);
        unlink(path);
        if (!ok || tail != EOF) {
            control_reply(r, false, "Malformed command.");
            continue;
        }
        int n = sscanf(line, "%15s %48s %7s", r->op, r->app, extra);
        bool simple =
            !strcmp(r->op, "library") || !strcmp(r->op, "refresh") || !strcmp(r->op, "restart");
        bool appop = !strcmp(r->op, "launch") || !strcmp(r->op, "install");
        if (!((simple && n == 1) || (appop && n == 2 && control_app_id(r->app)))) {
            control_reply(r, false, "Unsupported command or app ID.");
            continue;
        }
        closedir(d);
        return true;
    }
    closedir(d);
    return false;
}
static bool directory(const char *path) {
    struct stat s;
    return !lstat(path, &s) && S_ISDIR(s.st_mode);
}
static void paths(const ControlRequest *r, char *stage, char *live, char *backup) {
    snprintf(stage, PATH_MAX, "%s/.incoming-%s-%s", app_root, r->app, r->token);
    snprintf(live, PATH_MAX, "%s/%s", app_root, r->app);
    snprintf(backup, PATH_MAX, "%s/.backup-%s-%s", app_root, r->app, r->token);
}
bool control_stage_valid(const ControlRequest *r) {
    if (!strcmp(r->app, "esp32") || !strcmp(r->app, "starfall"))
        return false;
    char stage[PATH_MAX], live[PATH_MAX], backup[PATH_MAX], file[PATH_MAX];
    paths(r, stage, live, backup);
    if (!directory(stage))
        return false;
    snprintf(file, sizeof file, "%s/app.json", stage);
    if (access(file, R_OK))
        return false;
    snprintf(file, sizeof file, "%s/launch.sh", stage);
    if (access(file, R_OK))
        return false;
    /* Host writes this only after remote SHA-256 verification has succeeded. */
    snprintf(file, sizeof file, "%s/.verified", stage);
    FILE *f = fopen(file, "r");
    if (!f)
        return false;
    char token[40] = "";
    if (!fgets(token, sizeof token, f))
        token[0] = 0;
    fclose(f);
    token[strcspn(token, "\r\n")] = 0;
    return !strcmp(token, r->token);
}
bool control_install(const ControlRequest *r, bool *had_previous) {
    if (!control_stage_valid(r))
        return false;
    char stage[PATH_MAX], live[PATH_MAX], backup[PATH_MAX];
    paths(r, stage, live, backup);
    struct stat s;
    *had_previous = lstat(live, &s) == 0;
    if (*had_previous && (!S_ISDIR(s.st_mode) || rename(live, backup)))
        return false;
    if (rename(stage, live)) {
        if (*had_previous && rename(backup, live))
            fprintf(stderr, "Restore failed: %s\n", strerror(errno));
        return false;
    }
    return true;
}
bool control_rollback(const ControlRequest *r) {
    char stage[PATH_MAX], live[PATH_MAX], backup[PATH_MAX], failed[PATH_MAX];
    paths(r, stage, live, backup);
    snprintf(failed, sizeof failed, "%s/.failed-%s-%s", app_root, r->app, r->token);
    if (rename(live, failed))
        return false;
    if (directory(backup) && rename(backup, live)) {
        rename(failed, live);
        return false;
    }
    return true;
}
void control_ready_path(char *out, size_t size) {
    snprintf(out, size, "%s/ready", base);
}
bool control_is_ready(const char *session) {
    char path[PATH_MAX], value[96] = "";
    control_ready_path(path, sizeof path);
    FILE *f = fopen(path, "r");
    if (!f)
        return false;
    if (!fgets(value, sizeof value, f))
        value[0] = 0;
    fclose(f);
    value[strcspn(value, "\r\n")] = 0;
    return !strcmp(value, session);
}
