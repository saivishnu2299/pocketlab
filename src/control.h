#ifndef POCKET_CONTROL_H
#define POCKET_CONTROL_H
#include <stdbool.h>
#include <stddef.h>
#include <sys/types.h>
typedef struct {
    char token[33], op[16], app[49];
} ControlRequest;
bool control_init(const char *root);
void control_close(void);
bool control_read(ControlRequest *request);
void control_reply(const ControlRequest *request, bool ok, const char *message);
void control_status(const char *state, const char *app, pid_t child, const char *session,
                    bool ready);
bool control_app_id(const char *id);
bool control_stage_valid(const ControlRequest *request);
bool control_install(const ControlRequest *request, bool *had_previous);
bool control_rollback(const ControlRequest *request);
void control_ready_path(char *out, size_t size);
bool control_is_ready(const char *session);
#endif
