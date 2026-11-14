#include "../src/usb.h"
#include <stdio.h>
#include <string.h>
int main(int argc, char **argv) {
    if (argc != 3)
        return 64;
    if (!strcmp(argv[1], "scan")) {
        UsbSnapshot s;
        usb_scan(argv[2], &s);
        printf("%d\t%d\t%d\n", s.available, s.count, s.total);
        for (int i = 0; i < s.count; i++) {
            UsbDevice *u = &s.devices[i];
            printf("%s\t%04x\t%04x\t%d\t%s\t%llu\n", u->id, u->vid, u->pid, u->kind, u->port,
                   u->instance);
        }
        return 0;
    }
    char chip[80], error[192];
    bool ok = esp_probe(argv[2], chip, sizeof chip, error, sizeof error);
    puts(ok ? chip : error);
    return ok ? 0 : 2;
}
