#import <Cocoa/Cocoa.h>

static void PrintDiagnostic(NSString *step, NSString *status, NSString *code, NSString *message) {
    NSDictionary *event = @{
        @"step": step,
        @"status": status,
        @"code": code,
        @"message": message,
        @"evidence": @{}
    };
    NSData *data = [NSJSONSerialization dataWithJSONObject:event options:NSJSONWritingSortedKeys error:nil];
    NSString *line = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding];
    printf("%s\n", [line UTF8String]);
}

int main(int argc, const char * argv[]) {
    @autoreleasepool {
        PrintDiagnostic(@"app_launch", @"passed", @"PHASE0_APP_LAUNCHED", @"WeChat Sales Agent Phase 0 AppKit shell launched.");

        NSApplication *application = [NSApplication sharedApplication];
        [application setActivationPolicy:NSApplicationActivationPolicyRegular];

        NSWindow *window = [[NSWindow alloc]
            initWithContentRect:NSMakeRect(0, 0, 640, 360)
            styleMask:(NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskMiniaturizable)
            backing:NSBackingStoreBuffered
            defer:NO];
        [window setTitle:@"WeChat Sales Agent - Phase 0"];
        [window center];

        NSTextField *label = [[NSTextField alloc] initWithFrame:NSMakeRect(32, 170, 576, 32)];
        [label setStringValue:@"Phase 0: Commercial delivery and exact profile gate"];
        [label setEditable:NO];
        [label setBordered:NO];
        [label setDrawsBackground:NO];
        [label setAlignment:NSTextAlignmentCenter];
        [[window contentView] addSubview:label];

        [window makeKeyAndOrderFront:nil];

        if (argc > 1 && strcmp(argv[1], "--smoke") == 0) {
            return 0;
        }
        [application run];
    }
    return 0;
}
