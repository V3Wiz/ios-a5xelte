/*
 * ocean_gltest: does Mesa draw on the Moto's Adreno 506?
 *
 * Opens an OSMesa context (the GPU through the kernel's OceanGPU service when
 * there is one, else softpipe; OSMESA_SOFTWARE=1 forces softpipe), clears
 * the picture blue, draws a red/green/yellow triangle with the fixed
 * function pipeline (Mesa turns it into shaders for ir3), reads the pixels
 * back and prints the renderer, a few pixels, a checksum and how long 100
 * frames took. Writes the picture to /tmp/ocean_gltest.ppm.
 *
 * Every line also goes to the kernel log through the OceanGPU service's
 * request 0x7d, so it reaches the persistent log: on the phone this runs
 * as /usr/sbin/bluetoothd (user mobile, no console) for the first test.
 * It exits 0, so launchd does not start it again.
 */
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include <GL/gl.h>
#include <GL/osmesa.h>
#include <IOKit/IOKitLib.h>

#define W 256
#define H 256

static io_connect_t logger;

static void
say(const char *format, ...)
{
	char line[240] = "ocean_gltest: ";
	va_list ap;

	va_start(ap, format);
	vsnprintf(line + strlen(line), sizeof(line) - strlen(line), format, ap);
	va_end(ap);
	puts(line);
	if (logger != 0) {
		IOConnectCallStructMethod(logger, 0x7d, line, sizeof(line), NULL, NULL);
	}
}

static void
logger_open(void)
{
	io_service_t service = IOServiceGetMatchingService(kIOMainPortDefault, IOServiceMatching("OceanGPU"));

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
frame(void)
{
	glViewport(0, 0, W, H);
	glClearColor(0.0f, 0.0f, 1.0f, 1.0f);
	glClear(GL_COLOR_BUFFER_BIT);
	glBegin(GL_TRIANGLES);
	glColor3f(1.0f, 0.0f, 0.0f);
	glVertex2f(-0.8f, -0.8f);
	glColor3f(0.0f, 1.0f, 0.0f);
	glVertex2f(0.8f, -0.8f);
	glColor3f(1.0f, 1.0f, 0.0f);
	glVertex2f(0.0f, 0.8f);
	glEnd();
	glFinish();
}

int
main(void)
{
	logger_open();
	say("starting (pid %d)", getpid());
	uint8_t *pixels = calloc(W * H, 4);
	OSMesaContext ctx = OSMesaCreateContextExt(OSMESA_RGBA, 24, 8, 0, NULL);

	if (pixels == NULL || ctx == NULL) {
		say("no OSMesa context");
		return 1;
	}
	if (!OSMesaMakeCurrent(ctx, pixels, GL_UNSIGNED_BYTE, W, H)) {
		say("OSMesaMakeCurrent failed");
		return 1;
	}
	say("GL_RENDERER %s", (const char *)glGetString(GL_RENDERER));
	say("GL_VERSION %s", (const char *)glGetString(GL_VERSION));

	frame();
	uint32_t sum = 0;
	for (int i = 0; i < W * H * 4; i++) {
		sum = sum * 31 + pixels[i];
	}
	/* OSMesa's rows are bottom-up: (x, y) from the bottom-left corner */
	const int at[4][2] = { { 2, 2 }, { 128, 40 }, { 60, 30 }, { 128, 200 } };
	for (int i = 0; i < 4; i++) {
		const uint8_t *p = pixels + 4 * (at[i][1] * W + at[i][0]);
		say("pixel (%d,%d) = %02x %02x %02x %02x", at[i][0], at[i][1], p[0], p[1], p[2], p[3]);
	}
	say("checksum %08x, GL error %#x", sum, glGetError());

	double began = now();
	for (int i = 0; i < 100; i++) {
		frame();
	}
	say("100 frames of %dx%d in %.1f ms", W, H, (now() - began) * 1000);

	FILE *f = fopen("/tmp/ocean_gltest.ppm", "wb");
	if (f != NULL) {
		fprintf(f, "P6\n%d %d\n255\n", W, H);
		for (int y = H - 1; y >= 0; y--) {
			for (int x = 0; x < W; x++) {
				fwrite(pixels + 4 * (y * W + x), 1, 3, f);
			}
		}
		fclose(f);
	}
	OSMesaDestroyContext(ctx);
	say("done");
	return 0;
}
