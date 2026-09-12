#import <CoreGraphics/CoreGraphics.h>
#import <Foundation/Foundation.h>
#import <ImageIO/ImageIO.h>

static BOOL IsOuterBackground(const uint8_t *pixels, size_t index) {
    const uint8_t *pixel = pixels + index * 4;
    int brightest = MAX(pixel[0], MAX(pixel[1], pixel[2]));
    int darkest = MIN(pixel[0], MIN(pixel[1], pixel[2]));
    return brightest >= 185 && brightest - darkest <= 24;
}

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc != 3) {
            fprintf(stderr, "usage: prepare_app_icon INPUT OUTPUT\n");
            return 64;
        }
        NSURL *inputURL = [NSURL fileURLWithPath:[NSString stringWithUTF8String:argv[1]]];
        NSURL *outputURL = [NSURL fileURLWithPath:[NSString stringWithUTF8String:argv[2]]];
        CGImageSourceRef source = CGImageSourceCreateWithURL((__bridge CFURLRef)inputURL, NULL);
        CGImageRef image = source ? CGImageSourceCreateImageAtIndex(source, 0, NULL) : NULL;
        if (!image) {
            fprintf(stderr, "APP_ICON_INPUT_INVALID\n");
            if (source) CFRelease(source);
            return 1;
        }

        size_t width = CGImageGetWidth(image);
        size_t height = CGImageGetHeight(image);
        size_t pixelCount = width * height;
        size_t bytesPerRow = width * 4;
        uint8_t *pixels = calloc(pixelCount, 4);
        CGColorSpaceRef colorSpace = CGColorSpaceCreateDeviceRGB();
        CGContextRef sourceContext = CGBitmapContextCreate(
            pixels, width, height, 8, bytesPerRow, colorSpace,
            kCGImageAlphaPremultipliedLast | kCGBitmapByteOrder32Big
        );
        CGContextDrawImage(sourceContext, CGRectMake(0, 0, width, height), image);

        uint8_t *visited = calloc(pixelCount, 1);
        size_t *queue = malloc(pixelCount * sizeof(size_t));
        size_t head = 0;
        size_t tail = 0;
#define ENQUEUE(X, Y) do { \
    size_t enqueueIndex = (size_t)(Y) * width + (size_t)(X); \
    if (!visited[enqueueIndex] && IsOuterBackground(pixels, enqueueIndex)) { \
        visited[enqueueIndex] = 1; \
        queue[tail++] = enqueueIndex; \
    } \
} while (0)

        for (size_t x = 0; x < width; x++) {
            ENQUEUE(x, 0);
            ENQUEUE(x, height - 1);
        }
        for (size_t y = 0; y < height; y++) {
            ENQUEUE(0, y);
            ENQUEUE(width - 1, y);
        }
        while (head < tail) {
            size_t index = queue[head++];
            size_t x = index % width;
            size_t y = index / width;
            if (x > 0) ENQUEUE(x - 1, y);
            if (x + 1 < width) ENQUEUE(x + 1, y);
            if (y > 0) ENQUEUE(x, y - 1);
            if (y + 1 < height) ENQUEUE(x, y + 1);
        }
#undef ENQUEUE

        for (size_t index = 0; index < tail; index++) {
            uint8_t *pixel = pixels + queue[index] * 4;
            pixel[0] = 0;
            pixel[1] = 0;
            pixel[2] = 0;
            pixel[3] = 0;
        }
        for (size_t index = 0; index < pixelCount; index++) {
            uint8_t *pixel = pixels + index * 4;
            if (pixel[0] > pixel[1] + 32 && pixel[0] > pixel[2] + 32) {
                pixel[0] = 0;
                pixel[1] = 0;
                pixel[2] = 0;
                pixel[3] = 0;
            }
        }

        CGImageRef cutout = CGBitmapContextCreateImage(sourceContext);
        const size_t canvasSize = 1024;
        const size_t artworkSize = 870;
        const size_t inset = (canvasSize - artworkSize) / 2;
        uint8_t *outputPixels = calloc(canvasSize * canvasSize, 4);
        CGContextRef outputContext = CGBitmapContextCreate(
            outputPixels, canvasSize, canvasSize, 8, canvasSize * 4, colorSpace,
            kCGImageAlphaPremultipliedLast | kCGBitmapByteOrder32Big
        );
        CGContextSetInterpolationQuality(outputContext, kCGInterpolationHigh);
        CGContextDrawImage(outputContext, CGRectMake(inset, inset, artworkSize, artworkSize), cutout);
        for (size_t index = 0; index < canvasSize * canvasSize; index++) {
            uint8_t *pixel = outputPixels + index * 4;
            if (pixel[3] < 32 || (pixel[0] > pixel[1] + 32 && pixel[0] > pixel[2] + 32)) {
                pixel[0] = 0;
                pixel[1] = 0;
                pixel[2] = 0;
                pixel[3] = 0;
            }
        }
        CGImageRef output = CGBitmapContextCreateImage(outputContext);
        CGImageDestinationRef destination = CGImageDestinationCreateWithURL(
            (__bridge CFURLRef)outputURL, CFSTR("public.png"), 1, NULL
        );
        BOOL written = destination != NULL;
        if (destination) {
            CGImageDestinationAddImage(destination, output, NULL);
            written = CGImageDestinationFinalize(destination);
        }

        if (destination) CFRelease(destination);
        CGImageRelease(output);
        CGContextRelease(outputContext);
        free(outputPixels);
        CGImageRelease(cutout);
        CGContextRelease(sourceContext);
        CGColorSpaceRelease(colorSpace);
        free(queue);
        free(visited);
        free(pixels);
        CGImageRelease(image);
        CFRelease(source);
        return written ? 0 : 1;
    }
}
