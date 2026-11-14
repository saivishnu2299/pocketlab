#ifndef POCKET_USB_H
#define POCKET_USB_H
#include <stdbool.h>
#define MAX_USB 16
typedef enum { USB_OTHER, USB_SERIAL, USB_ESPRESSIF, USB_ESP32 } UsbKind;
typedef struct {
    char id[128], product[160], manufacturer[160], serial[160], port[256], driver[80];
    unsigned vid, pid;
    unsigned long long instance;
    UsbKind kind;
} UsbDevice;
typedef struct {
    UsbDevice devices[MAX_USB];
    int count, total;
    bool available;
    char error[192];
} UsbSnapshot;
UsbKind usb_classify(unsigned vid, unsigned pid, const char *product, const char *maker);
void usb_scan(const char *sysroot, UsbSnapshot *out);
void usb_identity(const UsbDevice *device, char *out, unsigned capacity);
bool esp_probe(const char *port, char *chip, unsigned capacity, char *error, unsigned errorcap);
#endif
