/*
 * ocean_gltest: does Mesa draw on the Moto's Adreno 506?
 *
 * Opens an OSMesa context (the GPU through the kernel's OceanGPU service when
 * there is one, else softpipe; OSMESA_SOFTWARE=1 forces softpipe), clears
 * the picture blue, draws a red/green/yellow triangle with the fixed
 * function pipeline (Mesa turns it into shaders for ir3), reads the pixels
 * back and prints the renderer, a few pixels, a checksum and how long 100
 * frames took. Writes the picture to /tmp/ocean_gltest.ppm.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include <GL/gl.h>
#include <GL/osmesa.h>

#define W 256
#define H 256

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
	uint8_t *pixels = calloc(W * H, 4);
	OSMesaContext ctx = OSMesaCreateContextExt(OSMESA_RGBA, 24, 8, 0, NULL);

	if (pixels == NULL || ctx == NULL) {
		printf("ocean_gltest: no OSMesa context\n");
		return 1;
	}
	if (!OSMesaMakeCurrent(ctx, pixels, GL_UNSIGNED_BYTE, W, H)) {
		printf("ocean_gltest: OSMesaMakeCurrent failed\n");
		return 1;
	}
	printf("ocean_gltest: GL_RENDERER %s\n", (const char *)glGetString(GL_RENDERER));
	printf("ocean_gltest: GL_VERSION %s\n", (const char *)glGetString(GL_VERSION));

	frame();
	uint32_t sum = 0;
	for (int i = 0; i < W * H * 4; i++) {
		sum = sum * 31 + pixels[i];
	}
	/* OSMesa's rows are bottom-up: (x, y) from the bottom-left corner */
	const int at[4][2] = { { 2, 2 }, { 128, 40 }, { 60, 30 }, { 128, 200 } };
	for (int i = 0; i < 4; i++) {
		const uint8_t *p = pixels + 4 * (at[i][1] * W + at[i][0]);
		printf("ocean_gltest: pixel (%d,%d) = %02x %02x %02x %02x\n", at[i][0], at[i][1], p[0], p[1], p[2], p[3]);
	}
	printf("ocean_gltest: checksum %08x, GL error %#x\n", sum, glGetError());

	double began = now();
	for (int i = 0; i < 100; i++) {
		frame();
	}
	printf("ocean_gltest: 100 frames of %dx%d in %.1f ms\n", W, H, (now() - began) * 1000);

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
	return 0;
}
