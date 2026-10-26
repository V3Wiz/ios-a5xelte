/*
 * ocean_gltest: does Mesa draw on the Moto's Adreno 506?
 *
 * Runs the same test twice: first in a child process with OSMESA_SOFTWARE=1
 * (Mesa's CPU renderer, softpipe: the reference), then with the GPU through
 * the kernel's OceanGPU service. Each run opens an OSMesa context, clears
 * the picture blue and reads it back, draws a red/green/yellow triangle with
 * the fixed function pipeline (Mesa turns it into shaders for ir3) and reads
 * it back again, then times 100 frames. Pixels are read two ways: from the
 * buffer OSMesa copies the picture into, and with glReadPixels.
 *
 * Every line also goes to the kernel log through the OceanGPU service's
 * request 0x7d, so it reaches the persistent log: on the phone this runs
 * as /usr/sbin/bluetoothd (user mobile, no console) for the GPU tests.
 * When done it waits forever, so launchd does not start it again.
 */
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/wait.h>

#include <GL/gl.h>
#include <GL/osmesa.h>
#include <IOKit/IOKitLib.h>

#define W 256
#define H 256

static io_connect_t logger;
static const char *mode = "gpu";

static void
say(const char *format, ...)
{
	char line[240];
	va_list ap;

	snprintf(line, sizeof(line), "ocean_gltest %s: ", mode);
	va_start(ap, format);
	vsnprintf(line + strlen(line), sizeof(line) - strlen(line), format, ap);
	va_end(ap);
	puts(line);
	if (logger != 0) {
		IOConnectCallStructMethod(logger, 0x7d, line, sizeof(line), NULL, NULL);
	}
}

/* Mach ports do not survive fork(): each process opens its own. */
static void
logger_open(void)
{
	io_service_t service = IOServiceGetMatchingService(kIOMainPortDefault, IOServiceMatching("OceanGPU"));

	logger = 0;
	if (service != 0) {
		if (IOServiceOpen(service, mach_task_self(), 0, &logger) != KERN_SUCCESS) {
			logger = 0;
		}
		IOObjectRelease(service);
	}
}

static double
now(void)
{
	struct timespec ts;

	clock_gettime(CLOCK_MONOTONIC, &ts);
	return ts.tv_sec + ts.tv_nsec / 1e9;
}

static void
triangle(void)
{
	glBegin(GL_TRIANGLES);
	glColor3f(1.0f, 0.0f, 0.0f);
	glVertex2f(-0.8f, -0.8f);
	glColor3f(0.0f, 1.0f, 0.0f);
	glVertex2f(0.8f, -0.8f);
	glColor3f(1.0f, 1.0f, 0.0f);
	glVertex2f(0.0f, 0.8f);
	glEnd();
}

static void
frame(int with_triangle)
{
	glViewport(0, 0, W, H);
	glClearColor(0.0f, 0.0f, 1.0f, 1.0f);
	glClear(GL_COLOR_BUFFER_BIT);
	if (with_triangle) {
		triangle();
	}
	glFinish();
}

static uint32_t
checksum(const uint8_t *p)
{
	uint32_t sum = 0;

	for (int i = 0; i < W * H * 4; i++) {
		sum = sum * 31 + p[i];
	}
	return sum;
}

/* OSMesa's rows and glReadPixels' are both bottom-up: (x, y) from the bottom-left. */
static void
look(const char *what, const uint8_t *osmesa)
{
	static uint8_t read[W * H * 4];
	static const int at[3][2] = { { 2, 2 }, { 128, 40 }, { 128, 200 } };
	char line[160];
	size_t n = 0;

	memset(read, 0x5a, sizeof(read));
	glReadPixels(0, 0, W, H, GL_RGBA, GL_UNSIGNED_BYTE, read);
	for (int i = 0; i < 3; i++) {
		const uint8_t *p = osmesa + 4 * (at[i][1] * W + at[i][0]);
		const uint8_t *q = read + 4 * (at[i][1] * W + at[i][0]);

		n += snprintf(line + n, sizeof(line) - n, " (%d,%d) %02x%02x%02x%02x/%02x%02x%02x%02x", at[i][0], at[i][1],
		    p[0], p[1], p[2], p[3], q[0], q[1], q[2], q[3]);
	}
	say("%s: buffer/readpixels%s; checksums %08x/%08x, GL error %#x", what, line, checksum(osmesa), checksum(read),
	    glGetError());
}

static int
run(void)
{
	uint8_t *pixels = calloc(W * H, 4);
	OSMesaContext ctx = OSMesaCreateContextExt(OSMESA_RGBA, 24, 8, 0, NULL);

	logger_open();
	say("starting (pid %d)", getpid());
	if (pixels == NULL || ctx == NULL) {
		say("no OSMesa context");
		return 1;
	}
	if (!OSMesaMakeCurrent(ctx, pixels, GL_UNSIGNED_BYTE, W, H)) {
		say("OSMesaMakeCurrent failed");
		return 1;
	}
	say("GL_RENDERER %s, GL_VERSION %s", (const char *)glGetString(GL_RENDERER),
	    (const char *)glGetString(GL_VERSION));

	frame(0);
	look("clear", pixels);
	frame(1);
	look("triangle", pixels);

	double began = now();
	for (int i = 0; i < 100; i++) {
		frame(1);
	}
	say("100 frames of %dx%d in %.1f ms", W, H, (now() - began) * 1000);
	look("after 100", pixels);
	OSMesaDestroyContext(ctx);
	say("done");
	return 0;
}

int
main(void)
{
	pid_t child = fork();

	if (child == 0) {
		mode = "cpu";
		setenv("OSMESA_SOFTWARE", "1", 1);
		_exit(run());
	}
	if (child > 0) {
		int status = 0;

		waitpid(child, &status, 0);
	}
	run();
	for (;;) {
		pause();
	}
}
