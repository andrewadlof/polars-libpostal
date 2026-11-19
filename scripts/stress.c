// Stress test for concurrent libpostal_parse_address.
//
//   cc -O2 stress.c -o stress -I<prefix>/include -L<prefix>/lib -lpostal -lpthread
//   LIBPOSTAL_DATA_DIR=/path/to/libpostal ./stress addresses.txt 8
//
// Parses every address once on the main thread to get reference output, then
// has N threads each parse all addresses (in different orders) and compares
// every result with the reference. Stock libpostal shares one parse context
// between callers, so it corrupts memory or returns mixed-up output here; the
// thread-safe-parser build must report 0 mismatches.
#include <libpostal/libpostal.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static char **addresses;
static char **reference;
static size_t n_addresses;

static char *serialize(libpostal_address_parser_response_t *r) {
    size_t cap = 64;
    for (size_t i = 0; i < r->num_components; i++) cap += strlen(r->labels[i]) + strlen(r->components[i]) + 4;
    char *out = malloc(cap);
    out[0] = 0;
    for (size_t i = 0; i < r->num_components; i++) {
        strcat(out, r->labels[i]);
        strcat(out, "=");
        strcat(out, r->components[i]);
        strcat(out, "|");
    }
    return out;
}

static char *parse(char *address) {
    libpostal_address_parser_options_t options = libpostal_get_address_parser_default_options();
    libpostal_address_parser_response_t *r = libpostal_parse_address(address, options);
    if (r == NULL) return strdup("<null>");
    char *s = serialize(r);
    libpostal_address_parser_response_destroy(r);
    return s;
}

typedef struct { int id; size_t mismatches; } worker_t;

static void *work(void *arg) {
    worker_t *w = arg;
    size_t stride = 7919 + 2 * w->id;  // coprime-ish with n: a different order per thread
    size_t idx = (size_t)w->id * 101 % n_addresses;
    for (size_t k = 0; k < n_addresses; k++) {
        char *got = parse(addresses[idx]);
        if (strcmp(got, reference[idx]) != 0) w->mismatches++;
        free(got);
        idx = (idx + stride) % n_addresses;
    }
    return NULL;
}

static double now(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec * 1e-9;
}

int main(int argc, char **argv) {
    if (argc < 3) { fprintf(stderr, "usage: %s addresses.txt threads\n", argv[0]); return 2; }
    int n_threads = atoi(argv[2]);

    FILE *f = fopen(argv[1], "r");
    if (!f) { perror("open"); return 2; }
    size_t cap = 1024;
    addresses = malloc(cap * sizeof(char *));
    char *line = NULL; size_t len = 0; ssize_t got;
    while ((got = getline(&line, &len, f)) > 0) {
        if (line[got - 1] == '\n') line[got - 1] = 0;
        if (!line[0]) continue;
        if (n_addresses == cap) { cap *= 2; addresses = realloc(addresses, cap * sizeof(char *)); }
        addresses[n_addresses++] = strdup(line);
    }
    fclose(f);

    // Models come from $LIBPOSTAL_DATA_DIR when set, else libpostal's compiled-in path
    char *data_dir = getenv("LIBPOSTAL_DATA_DIR");
    bool loaded = data_dir ? (libpostal_setup_datadir(data_dir) && libpostal_setup_parser_datadir(data_dir))
                           : (libpostal_setup() && libpostal_setup_parser());
    if (!loaded) { fprintf(stderr, "setup failed\n"); return 2; }

    reference = malloc(n_addresses * sizeof(char *));
    double t0 = now();
    for (size_t i = 0; i < n_addresses; i++) reference[i] = parse(addresses[i]);
    double serial = now() - t0;
    printf("serial:  %zu addresses in %.2fs (%.0f/s)\n", n_addresses, serial, n_addresses / serial);

    pthread_t *threads = malloc(n_threads * sizeof(pthread_t));
    worker_t *workers = calloc(n_threads, sizeof(worker_t));
    t0 = now();
    for (int i = 0; i < n_threads; i++) { workers[i].id = i; pthread_create(&threads[i], NULL, work, &workers[i]); }
    size_t bad = 0;
    for (int i = 0; i < n_threads; i++) { pthread_join(threads[i], NULL); bad += workers[i].mismatches; }
    double par = now() - t0;
    size_t total = (size_t)n_threads * n_addresses;
    printf("threads: %d x %zu addresses in %.2fs (%.0f/s, %.2fx serial)\n", n_threads, n_addresses, par, total / par, (total / par) / (n_addresses / serial));
    printf("mismatches: %zu of %zu\n", bad, total);
    return bad ? 1 : 0;
}
