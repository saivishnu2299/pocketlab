#include "usb.h"
#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/select.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>
#ifdef __APPLE__
#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOKitLib.h>
#endif
static bool has(const char *s, const char *q) {
    if (!s)
        return false;
    size_t n = strlen(q);
    for (; *s; s++) {
        size_t j = 0;
        while (j < n && s[j] && tolower((unsigned char)s[j]) == tolower((unsigned char)q[j]))
            j++;
        if (j == n)
            return true;
    }
    return false;
}
UsbKind usb_classify(unsigned vid, unsigned pid, const char *p, const char *m) {
    (void)pid;
    if (has(p, "esp32") || has(p, "esp-32"))
        return USB_ESP32;
    if (vid == 0x303a || has(m, "espressif"))
        return USB_ESPRESSIF;
    if (vid == 0x10c4 || vid == 0x1a86 || vid == 0x0403 || vid == 0x067b || has(p, "usb serial") ||
        has(p, "usb-serial") || has(p, "cp210") || has(p, "ch340") || has(p, "ch910"))
        return USB_SERIAL;
    return USB_OTHER;
}
static void readstr(const char *p, char *b, size_t n) {
    b[0] = 0;
    FILE *f = fopen(p, "r");
    if (!f)
        return;
    if (fgets(b, (int)n, f)) {
        b[strcspn(b, "\r\n")] = 0;
        for (char *q = b; *q; q++)
            if ((unsigned char)*q < 32 || (unsigned char)*q > 126)
                *q = '?';
    }
    fclose(f);
}
static void field(const char *root, const char *id, const char *name, char *b, size_t n) {
    char p[PATH_MAX];
    snprintf(p, sizeof p, "%s/bus/usb/devices/%s/%s", root, id, name);
    readstr(p, b, n);
}
void usb_identity(const UsbDevice *u, char *out, unsigned cap) {
    snprintf(out, cap, "%s:%04x:%04x:%llu:%s", u->id, u->vid, u->pid, u->instance, u->serial);
}
static void scan_sysfs(const char *root, UsbSnapshot *out) {
    char path[PATH_MAX];
    snprintf(path, sizeof path, "%s/bus/usb/devices", root);
    DIR *d = opendir(path);
    if (!d) {
        snprintf(out->error, sizeof out->error, "USB inventory unavailable: %s", strerror(errno));
        return;
    }
    out->available = true;
    struct dirent *e;
    while ((e = readdir(d))) {
        if (e->d_name[0] == '.' || strchr(e->d_name, ':'))
            continue;
        char v[32], p[32], cls[32];
        field(root, e->d_name, "idVendor", v, sizeof v);
        if (!v[0])
            continue;
        field(root, e->d_name, "idProduct", p, sizeof p);
        field(root, e->d_name, "bDeviceClass", cls, sizeof cls);
        if (strtoul(cls, 0, 16) == 9)
            continue;
        out->total++;
        UsbDevice u = {0};
        u.vid = (unsigned)strtoul(v, 0, 16);
        u.pid = (unsigned)strtoul(p, 0, 16);
        snprintf(u.id, sizeof u.id, "%s", e->d_name);
        field(root, e->d_name, "devnum", v, sizeof v);
        u.instance = strtoull(v, NULL, 10);
        field(root, e->d_name, "product", u.product, sizeof u.product);
        field(root, e->d_name, "manufacturer", u.manufacturer, sizeof u.manufacturer);
        field(root, e->d_name, "serial", u.serial, sizeof u.serial);
        u.kind = usb_classify(u.vid, u.pid, u.product, u.manufacturer);
        if (u.kind == USB_OTHER)
            continue;
        char resolved[PATH_MAX], devpath[PATH_MAX];
        snprintf(devpath, sizeof devpath, "%s/bus/usb/devices/%s", root, e->d_name);
        if (realpath(devpath, resolved)) {
            char ttyroot[PATH_MAX];
            snprintf(ttyroot, sizeof ttyroot, "%s/class/tty", root);
            DIR *td = opendir(ttyroot);
            if (td) {
                struct dirent *te;
                while ((te = readdir(td))) {
                    if (strncmp(te->d_name, "ttyUSB", 6) && strncmp(te->d_name, "ttyACM", 6))
                        continue;
                    char tpath[PATH_MAX], tr[PATH_MAX];
                    snprintf(tpath, sizeof tpath, "%s/%s/device", ttyroot, te->d_name);
                    if (realpath(tpath, tr) && !strncmp(tr, resolved, strlen(resolved)) &&
                        tr[strlen(resolved)] == '/') {
                        snprintf(u.port, sizeof u.port, "/dev/%s", te->d_name);
                        char dp[PATH_MAX], dr[PATH_MAX];
                        snprintf(dp, sizeof dp, "%s/driver", tpath);
                        if (realpath(dp, dr)) {
                            char *name = strrchr(dr, '/');
                            snprintf(u.driver, sizeof u.driver, "%s", name ? name + 1 : dr);
                        }
                        break;
                    }
                }
                closedir(td);
            }
        }
        if (!u.product[0])
            snprintf(u.product, sizeof u.product, "USB device %04X:%04X", u.vid, u.pid);
        if (out->count < MAX_USB)
            out->devices[out->count++] = u;
    }
    closedir(d);
}
#ifdef __APPLE__
static int cfnum(io_service_t s, CFStringRef key) {
    CFTypeRef v = IORegistryEntryCreateCFProperty(s, key, kCFAllocatorDefault, 0);
    int n = 0;
    if (v) {
        if (CFGetTypeID(v) == CFNumberGetTypeID())
            CFNumberGetValue(v, kCFNumberIntType, &n);
        CFRelease(v);
    }
    return n;
}
static void cfstr(io_service_t s, CFStringRef key, char *b, size_t n) {
    CFTypeRef v = IORegistryEntryCreateCFProperty(s, key, kCFAllocatorDefault, 0);
    if (v) {
        if (CFGetTypeID(v) == CFStringGetTypeID())
            CFStringGetCString(v, b, (CFIndex)n, kCFStringEncodingUTF8);
        CFRelease(v);
    }
}
static void mac_port(UsbDevice *u) {
    io_iterator_t it;
    if (IOServiceGetMatchingServices(kIOMainPortDefault, IOServiceMatching("IOSerialBSDClient"),
                                     &it) != KERN_SUCCESS)
        return;
    io_service_t s;
    while ((s = IOIteratorNext(it))) {
        io_registry_entry_t p = s;
        IOObjectRetain(p);
        bool match = false;
        for (int depth = 0; depth < 10; depth++) {
            if (cfnum(p, CFSTR("idVendor")) == (int)u->vid &&
                cfnum(p, CFSTR("idProduct")) == (int)u->pid) {
                char serial[160] = "";
                cfstr(p, CFSTR("USB Serial Number"), serial, sizeof serial);
                if (!u->serial[0] || !strcmp(serial, u->serial))
                    match = true;
                break;
            }
            io_registry_entry_t next;
            if (IORegistryEntryGetParentEntry(p, kIOServicePlane, &next) != KERN_SUCCESS)
                break;
            IOObjectRelease(p);
            p = next;
        }
        IOObjectRelease(p);
        if (match)
            cfstr(s, CFSTR("IOCalloutDevice"), u->port, sizeof u->port);
        IOObjectRelease(s);
        if (match)
            break;
    }
    IOObjectRelease(it);
}
static void scan_mac(UsbSnapshot *out) {
    io_iterator_t it;
    if (IOServiceGetMatchingServices(kIOMainPortDefault, IOServiceMatching("IOUSBHostDevice"),
                                     &it) != KERN_SUCCESS) {
        snprintf(out->error, sizeof out->error, "Unable to read USB inventory");
        return;
    }
    out->available = true;
    io_service_t s;
    while ((s = IOIteratorNext(it))) {
        UsbDevice u = {0};
        u.vid = cfnum(s, CFSTR("idVendor"));
        u.pid = cfnum(s, CFSTR("idProduct"));
        if (cfnum(s, CFSTR("bDeviceClass")) == 9) {
            IOObjectRelease(s);
            continue;
        }
        out->total++;
        cfstr(s, CFSTR("USB Product Name"), u.product, sizeof u.product);
        cfstr(s, CFSTR("USB Vendor Name"), u.manufacturer, sizeof u.manufacturer);
        cfstr(s, CFSTR("USB Serial Number"), u.serial, sizeof u.serial);
        uint64_t entry = 0;
        IORegistryEntryGetRegistryEntryID(s, &entry);
        u.instance = entry;
        snprintf(u.id, sizeof u.id, "usb-%08x", cfnum(s, CFSTR("locationID")));
        u.kind = usb_classify(u.vid, u.pid, u.product, u.manufacturer);
        if (u.kind != USB_OTHER && out->count < MAX_USB) {
            mac_port(&u);
            out->devices[out->count++] = u;
        }
        IOObjectRelease(s);
    }
    IOObjectRelease(it);
}
#endif
static int compare(const void *a, const void *b) {
    return strcmp(((const UsbDevice *)a)->id, ((const UsbDevice *)b)->id);
}
void usb_scan(const char *root, UsbSnapshot *out) {
    memset(out, 0, sizeof *out);
#ifdef __APPLE__
    if (!root)
        scan_mac(out);
    else
        scan_sysfs(root, out);
#else
    scan_sysfs(root ? root : "/sys", out);
#endif
    qsort(out->devices, (size_t)out->count, sizeof(UsbDevice), compare);
}
static uint32_t le32(const unsigned char *p) {
    return p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
static void put32(unsigned char *p, uint32_t v) {
    for (int i = 0; i < 4; i++)
        p[i] = (v >> (i * 8)) & 255;
}
static bool sendcmd(int fd, int cmd, const unsigned char *data, int len) {
    unsigned char raw[128] = {0}, frame[260];
    if (len > 120)
        return false;
    raw[1] = (unsigned char)cmd;
    raw[2] = (unsigned char)len;
    memcpy(raw + 8, data, (size_t)len);
    int n = 0;
    frame[n++] = 0xc0;
    for (int i = 0; i < len + 8; i++) {
        if (raw[i] == 0xc0) {
            frame[n++] = 0xdb;
            frame[n++] = 0xdc;
        } else if (raw[i] == 0xdb) {
            frame[n++] = 0xdb;
            frame[n++] = 0xdd;
        } else
            frame[n++] = raw[i];
    }
    frame[n++] = 0xc0;
    int sent = 0;
    while (sent < n) {
        ssize_t w = write(fd, frame + sent, (size_t)(n - sent));
        if (w < 0) {
            if (errno == EINTR)
                continue;
            return false;
        }
        if (!w)
            return false;
        sent += (int)w;
    }
    return true;
}
static double monotime(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec + t.tv_nsec / 1e9;
}
static int reply(int fd, int cmd, unsigned char *out, int cap, double timeout) {
    int n = 0;
    bool active = false, escape = false;
    double end = monotime() + timeout;
    while (monotime() < end) {
        fd_set fds;
        FD_ZERO(&fds);
        FD_SET(fd, &fds);
        struct timeval tv = {0, 30000};
        if (select(fd + 1, &fds, 0, 0, &tv) <= 0)
            continue;
        unsigned char b;
        if (read(fd, &b, 1) != 1)
            continue;
        if (b == 0xc0) {
            if (active && n >= 10 && out[0] == 1 && out[1] == cmd) {
                int len = out[2] | out[3] << 8;
                if (len + 8 == n)
                    return n;
            }
            active = true;
            escape = false;
            n = 0;
            continue;
        }
        if (!active)
            continue;
        if (b == 0xdb) {
            escape = true;
            continue;
        }
        if (escape) {
            if (b == 0xdc)
                b = 0xc0;
            else if (b == 0xdd)
                b = 0xdb;
            else {
                active = false;
                continue;
            }
            escape = false;
        }
        if (n < cap)
            out[n++] = b;
        else {
            active = false;
            n = 0;
        }
    }
    return 0;
}
static void pins(int fd, bool dtr, bool rts) {
    int v = 0;
    if (ioctl(fd, TIOCMGET, &v) < 0)
        return;
    v = dtr ? v | TIOCM_DTR : v & ~TIOCM_DTR;
    v = rts ? v | TIOCM_RTS : v & ~TIOCM_RTS;
    ioctl(fd, TIOCMSET, &v);
}
bool esp_probe(const char *port, char *chip, unsigned cap, char *error, unsigned ecap) {
    chip[0] = 0;
    error[0] = 0;
    int fd = open(port, O_RDWR | O_NOCTTY | O_NONBLOCK);
    if (fd < 0) {
        snprintf(error, ecap, "Cannot open serial port: %s", strerror(errno));
        return false;
    }
    struct termios old, t;
    if (tcgetattr(fd, &old) < 0) {
        snprintf(error, ecap, "Cannot read serial settings");
        close(fd);
        return false;
    }
    t = old;
    cfmakeraw(&t);
    cfsetispeed(&t, B115200);
    cfsetospeed(&t, B115200);
    t.c_cflag |= CLOCAL | CREAD;
    t.c_cflag &= ~HUPCL;
#ifdef CRTSCTS
    t.c_cflag &= ~CRTSCTS;
#endif
    if (tcsetattr(fd, TCSANOW, &t) < 0) {
        snprintf(error, ecap, "Cannot configure serial port: %s", strerror(errno));
        close(fd);
        return false;
    }
    fcntl(fd, F_SETFL, fcntl(fd, F_GETFL) & ~O_NONBLOCK);
    unsigned char sync[36] = {7, 7, 18, 32}, r[256];
    memset(sync + 4, 0x55, 32);
    bool connected = false;
    for (int attempt = 0; attempt < 3 && !connected; attempt++) {
        if (attempt < 2) {
            pins(fd, false, true);
            usleep(100000);
            pins(fd, true, false);
            usleep(100000);
            pins(fd, false, false);
        }
        tcflush(fd, TCIOFLUSH);
        for (int j = 0; j < 4; j++) {
            if (!sendcmd(fd, 8, sync, 36))
                break;
            int n = reply(fd, 8, r, sizeof r, .3);
            if (n >= 10 && r[8] == 0) {
                connected = true;
                break;
            }
        }
    }
    if (connected) {
        tcflush(fd, TCIFLUSH);
        sendcmd(fd, 0x14, (const unsigned char *)"", 0);
        int n = reply(fd, 0x14, r, sizeof r, .5);
        if (n >= 32 && r[n - 4] == 0) {
            unsigned id = le32(r + 20);
            const char *name = NULL;
            switch (id) {
            case 0:
                name = "ESP32";
                break;
            case 2:
                name = "ESP32-S2";
                break;
            case 5:
                name = "ESP32-C3";
                break;
            case 9:
                name = "ESP32-S3";
                break;
            case 12:
                name = "ESP32-C2";
                break;
            case 13:
                name = "ESP32-C6";
                break;
            case 16:
                name = "ESP32-H2";
                break;
            case 18:
                name = "ESP32-P4";
                break;
            case 20:
                name = "ESP32-C61";
                break;
            case 23:
                name = "ESP32-C5";
                break;
            }
            if (name)
                snprintf(chip, cap, "%s", name);
            else
                snprintf(chip, cap, "Espressif chip (ID %u)", id);
        }
        if (!chip[0]) {
            unsigned char address[4];
            put32(address, 0x40001000);
            tcflush(fd, TCIFLUSH);
            sendcmd(fd, 0x0a, address, 4);
            n = reply(fd, 0x0a, r, sizeof r, .5);
            if (n >= 10 && r[8] == 0) {
                uint32_t m = le32(r + 4);
                if (m == 0x00f01d83)
                    snprintf(chip, cap, "ESP32");
                else if (m == 0x000007c6)
                    snprintf(chip, cap, "ESP32-S2");
                else if (m == 0xfff0c101)
                    snprintf(chip, cap, "ESP8266 (not ESP32)");
            }
        }
    }
    pins(fd, false, true);
    usleep(100000);
    pins(fd, false, false);
    tcsetattr(fd, TCSANOW, &old);
    close(fd);
    if (!chip[0])
        snprintf(error, ecap,
                 "No chip identity returned. Hold BOOT, tap RESET, then retry. Some boards disable "
                 "ROM access.");
    return chip[0] != 0;
}
