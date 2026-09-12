#import <Cocoa/Cocoa.h>
#import <CoreText/CoreText.h>
#include <signal.h>

static void PolishWorkspace(NSView *view) {
    if ([view isKindOfClass:NSTableView.class]) {
        NSTableView *table = (NSTableView *)view;
        table.rowHeight = MAX(36, table.rowHeight);
        table.usesAlternatingRowBackgroundColors = NO;
        table.intercellSpacing = NSMakeSize(12, 8);
        table.selectionHighlightStyle = NSTableViewSelectionHighlightStyleRegular;
        table.gridStyleMask = NSTableViewSolidHorizontalGridLineMask;
        table.gridColor = [NSColor colorWithWhite:0.94 alpha:1];
        for (NSTableColumn *column in table.tableColumns) {
            column.headerCell.font = [NSFont systemFontOfSize:12 weight:NSFontWeightSemibold];
            column.headerCell.textColor = NSColor.secondaryLabelColor;
        }
    }
    if ([view isKindOfClass:NSScrollView.class]) {
        NSScrollView *scroll = (NSScrollView *)view;
        scroll.scrollerStyle = NSScrollerStyleOverlay;
        scroll.autohidesScrollers = YES;
        if ([scroll.documentView isKindOfClass:NSTableView.class]) scroll.hasHorizontalScroller = YES;
        scroll.wantsLayer = YES;
        scroll.layer.cornerRadius = 12;
    }
    if ([view isKindOfClass:NSButton.class]) {
        NSButton *button = (NSButton *)view;
        NSDictionary *symbols = @{@"▦  仪表盘": @"chart.bar.xaxis", @"☷  智能分析": @"person.2", @"≡  消息检索": @"text.magnifyingglass"};
        NSString *symbol = symbols[button.title];
        if (symbol) {
            button.image = [NSImage imageWithSystemSymbolName:symbol accessibilityDescription:nil];
            button.imagePosition = NSImageLeft;
            button.title = [button.title substringFromIndex:3];
        }
        if (button.bordered && ![button isKindOfClass:NSPopUpButton.class]) {
            button.bezelStyle = NSBezelStyleRounded;
            button.font = [NSFont systemFontOfSize:13 weight:NSFontWeightMedium];
        }
    }
    if ([view isKindOfClass:NSTextView.class]) {
        NSTextView *text = (NSTextView *)view;
        text.textContainerInset = NSMakeSize(18, 16);
        text.font = [NSFont systemFontOfSize:13];
        text.horizontallyResizable = NO;
        text.textContainer.widthTracksTextView = YES;
    }
    for (NSView *child in view.subviews) PolishWorkspace(child);
}

static void PrintDiagnostic(NSString *step, NSString *status, NSString *code, NSString *message) {
    NSDictionary *event = @{ @"step": step, @"status": status, @"code": code, @"message": message, @"evidence": @{} };
    NSData *data = [NSJSONSerialization dataWithJSONObject:event options:NSJSONWritingSortedKeys error:nil];
    printf("%s\n", [[[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] UTF8String]);
}

static NSTextField *Label(NSString *text, CGFloat size, NSColor *color, BOOL bold) {
    NSTextField *field = [NSTextField labelWithString:text ?: @""];
    field.font = bold ? [NSFont boldSystemFontOfSize:size] : [NSFont systemFontOfSize:size];
    field.textColor = color;
    field.lineBreakMode = NSLineBreakByTruncatingTail;
    return field;
}

static void AppendAgentText(NSMutableAttributedString *target, NSString *text, NSFont *font, NSColor *color, CGFloat spacing) {
    NSMutableParagraphStyle *paragraph = [[NSMutableParagraphStyle alloc] init];
    paragraph.lineSpacing = 3;
    paragraph.paragraphSpacing = spacing;
    [target appendAttributedString:[[NSAttributedString alloc] initWithString:text attributes:@{
        NSFontAttributeName: font,
        NSForegroundColorAttributeName: color,
        NSParagraphStyleAttributeName: paragraph,
    }]];
}

static void AppendEvidenceLink(NSMutableAttributedString *target, NSString *label, NSString *evidenceID) {
    if (!evidenceID.length) return;
    NSString *text = [NSString stringWithFormat:@"%@  ", label];
    NSURL *URL = [NSURL URLWithString:[NSString stringWithFormat:@"evidence://%@", evidenceID]];
    [target appendAttributedString:[[NSAttributedString alloc] initWithString:text attributes:@{
        NSFontAttributeName: [NSFont systemFontOfSize:12 weight:NSFontWeightMedium],
        NSForegroundColorAttributeName: NSColor.systemBlueColor,
        NSLinkAttributeName: URL,
        NSUnderlineStyleAttributeName: @(NSUnderlineStyleNone),
    }]];
}

static BOOL WriteAnalysisPDF(NSDictionary *snapshot, NSString *path, NSDictionary *options) {
    NSMutableAttributedString *document = [[NSMutableAttributedString alloc] init];
    void (^append)(NSString *, CGFloat, NSFontWeight, NSColor *, CGFloat) = ^(NSString *text, CGFloat size, NSFontWeight weight, NSColor *color, CGFloat spacing) {
        NSMutableParagraphStyle *paragraph = [[NSMutableParagraphStyle alloc] init];
        paragraph.lineSpacing = 3; paragraph.paragraphSpacing = spacing * 0.65;
        [document appendAttributedString:[[NSAttributedString alloc] initWithString:text ?: @"" attributes:@{
            NSFontAttributeName: [NSFont systemFontOfSize:size weight:weight],
            NSForegroundColorAttributeName: color ?: NSColor.blackColor,
            NSParagraphStyleAttributeName: paragraph,
        }]];
    };
    append([NSString stringWithFormat:@"%@\n", snapshot[@"result_title"] ?: @"智能分析报告"], 24, NSFontWeightBold, [NSColor colorWithRed:0.09 green:0.15 blue:0.33 alpha:1], 8);
    NSString *generatedAt = [NSDateFormatter localizedStringFromDate:NSDate.date dateStyle:NSDateFormatterMediumStyle timeStyle:NSDateFormatterShortStyle];
    append([NSString stringWithFormat:@"分析任务：%@\n生成时间：%@\n\n", snapshot[@"query"] ?: @"", generatedAt], 10, NSFontWeightRegular, NSColor.secondaryLabelColor, 8);
    append(@"核心回答\n", 15, NSFontWeightSemibold, NSColor.blackColor, 4);
    append([NSString stringWithFormat:@"%@\n\n", snapshot[@"answer"] ?: @""], 12, NSFontWeightRegular, [NSColor colorWithWhite:0.18 alpha:1], 10);
    for (NSDictionary *section in [snapshot[@"sections"] isKindOfClass:NSArray.class] ? snapshot[@"sections"] : @[]) {
        append([NSString stringWithFormat:@"%@ · 置信度 %@%%\n", section[@"title"] ?: @"分析", section[@"confidence"] ?: @0], 14, NSFontWeightSemibold, NSColor.blackColor, 3);
        append([NSString stringWithFormat:@"%@\n", section[@"content"] ?: @""], 11, NSFontWeightRegular, [NSColor colorWithWhite:0.2 alpha:1], 4);
        if ([options[@"include_evidence"] boolValue]) append([NSString stringWithFormat:@"支持证据：%@\n反例证据：%@\n\n", [section[@"evidence_ids"] componentsJoinedByString:@"、"] ?: @"", [section[@"counter_evidence_ids"] componentsJoinedByString:@"、"] ?: @""], 9, NSFontWeightRegular, NSColor.secondaryLabelColor, 6);
        else append(@"\n", 8, NSFontWeightRegular, NSColor.blackColor, 2);
    }
    NSArray *items = [snapshot[@"structured_items"] isKindOfClass:NSArray.class] ? snapshot[@"structured_items"] : @[];
    if (items.count) {
        append(@"时间线与待办\n", 15, NSFontWeightSemibold, NSColor.blackColor, 5);
        for (NSDictionary *item in items) append([NSString stringWithFormat:@"• %@  %@  %@  %@\n", item[@"date"] ?: @"", item[@"status"] ?: @"", item[@"subject"] ?: @"", item[@"content"] ?: @""], 11, NSFontWeightRegular, [NSColor colorWithWhite:0.2 alpha:1], 3);
        append(@"\n", 8, NSFontWeightRegular, NSColor.blackColor, 4);
    }
    if ([options[@"include_statistics"] boolValue]) {
        append(@"互动统计\n", 15, NSFontWeightSemibold, NSColor.blackColor, 5);
        for (NSDictionary *lead in [snapshot[@"leads"] isKindOfClass:NSArray.class] ? snapshot[@"leads"] : @[]) {
            NSDictionary *stats = [lead[@"conversation_stats"] isKindOfClass:NSDictionary.class] ? lead[@"conversation_stats"] : @{};
            append([NSString stringWithFormat:@"%@：共 %@ 条（对方 %@ / 我方 %@），%@ 个活跃日，对方中位回复 %@ 分钟，我方中位回复 %@ 分钟\n", lead[@"display_name"] ?: @"联系人", stats[@"message_count"] ?: @0, stats[@"incoming_count"] ?: @0, stats[@"outgoing_count"] ?: @0, stats[@"active_days"] ?: @0, stats[@"their_median_response_minutes"] ?: @"—", stats[@"my_median_response_minutes"] ?: @"—"], 10, NSFontWeightRegular, [NSColor colorWithWhite:0.2 alpha:1], 3);
        }
        append(@"\n", 8, NSFontWeightRegular, NSColor.blackColor, 4);
    }
    if ([options[@"include_evidence"] boolValue]) {
        append(@"证据明细\n", 15, NSFontWeightSemibold, NSColor.blackColor, 5);
        NSMutableSet *seen = [NSMutableSet set];
        for (NSDictionary *lead in [snapshot[@"leads"] isKindOfClass:NSArray.class] ? snapshot[@"leads"] : @[]) {
            for (NSDictionary *evidence in [lead[@"evidence"] isKindOfClass:NSArray.class] ? lead[@"evidence"] : @[]) {
                if ([seen containsObject:evidence[@"evidence_id"] ?: @""]) continue;
                [seen addObject:evidence[@"evidence_id"] ?: @""];
                append([NSString stringWithFormat:@"%@  %@  [%@] %@\n%@\n\n", evidence[@"evidence_id"] ?: @"", evidence[@"time"] ?: @"", evidence[@"direction"] ?: @"", evidence[@"sender"] ?: @"", evidence[@"content"] ?: @""], 9, NSFontWeightRegular, [NSColor colorWithWhite:0.25 alpha:1], 4);
            }
        }
    }
    NSArray *limitations = [snapshot[@"limitations"] isKindOfClass:NSArray.class] ? snapshot[@"limitations"] : @[];
    if (limitations.count) {
        append(@"边界说明\n", 13, NSFontWeightSemibold, NSColor.blackColor, 4);
        for (NSString *item in limitations) append([NSString stringWithFormat:@"• %@\n", item], 10, NSFontWeightRegular, NSColor.secondaryLabelColor, 2);
    }
    if ([options[@"include_followups"] boolValue]) {
        NSArray *followups = [snapshot[@"suggested_followups"] isKindOfClass:NSArray.class] ? snapshot[@"suggested_followups"] : @[];
        if (followups.count) {
            append(@"\n可继续分析\n", 13, NSFontWeightSemibold, NSColor.blackColor, 4);
            for (NSUInteger index = 0; index < followups.count; index += 1) append([NSString stringWithFormat:@"%lu. %@\n", (unsigned long)index + 1, followups[index]], 10, NSFontWeightRegular, [NSColor colorWithWhite:0.25 alpha:1], 2);
        }
    }
    NSURL *URL = [NSURL fileURLWithPath:path];
    CGRect mediaBox = CGRectMake(0, 0, 595, 842);
    CGDataConsumerRef consumer = CGDataConsumerCreateWithURL((__bridge CFURLRef)URL);
    if (!consumer) return NO;
    CGContextRef context = CGPDFContextCreate(consumer, &mediaBox, NULL);
    CGDataConsumerRelease(consumer);
    if (!context) return NO;
    CTFramesetterRef framesetter = CTFramesetterCreateWithAttributedString((__bridge CFAttributedStringRef)document);
    CFIndex location = 0;
    NSInteger page = 1;
    while (location < document.length) {
        CGPDFContextBeginPage(context, NULL);
        CGMutablePathRef pathRef = CGPathCreateMutable();
        CGPathAddRect(pathRef, NULL, CGRectMake(48, 28, 499, 790));
        CTFrameRef frame = CTFramesetterCreateFrame(framesetter, CFRangeMake(location, 0), pathRef, NULL);
        CFRange visible = CTFrameGetVisibleStringRange(frame);
        if (location + visible.length < document.length && visible.length > 0) {
            NSRange visibleRange = NSMakeRange((NSUInteger)location, (NSUInteger)visible.length);
            NSRange boundary = [document.string rangeOfString:@"\n\n" options:NSBackwardsSearch range:visibleRange];
            CFIndex boundaryEnd = boundary.location == NSNotFound ? 0 : (CFIndex)NSMaxRange(boundary);
            if (boundaryEnd > location + visible.length / 4) {
                CFRelease(frame);
                frame = CTFramesetterCreateFrame(framesetter, CFRangeMake(location, boundaryEnd - location), pathRef, NULL);
                visible = CTFrameGetVisibleStringRange(frame);
            }
        }
        CTFrameDraw(frame, context);
        NSString *footer = [NSString stringWithFormat:@"微信客户分析 Agent · %ld", (long)page++];
        [NSGraphicsContext saveGraphicsState];
        [NSGraphicsContext setCurrentContext:[NSGraphicsContext graphicsContextWithCGContext:context flipped:NO]];
        [footer drawAtPoint:NSMakePoint(48, 10) withAttributes:@{NSFontAttributeName:[NSFont systemFontOfSize:8], NSForegroundColorAttributeName:NSColor.secondaryLabelColor}];
        [NSGraphicsContext restoreGraphicsState];
        CFRelease(frame); CGPathRelease(pathRef);
        CGPDFContextEndPage(context);
        if (visible.length <= 0) break;
        location += visible.length;
    }
    CFRelease(framesetter); CGPDFContextClose(context); CGContextRelease(context);
    NSDictionary *attributes = [[NSFileManager defaultManager] attributesOfItemAtPath:path error:nil];
    return [attributes fileSize] > 0;
}

static NSView *Card(NSString *title, NSString *value, NSColor *accent) {
    NSView *card = [[NSView alloc] initWithFrame:NSZeroRect];
    card.wantsLayer = YES;
    card.layer.backgroundColor = NSColor.whiteColor.CGColor;
    card.layer.cornerRadius = 16;
    card.layer.borderColor = [NSColor colorWithWhite:0.92 alpha:1].CGColor;
    card.layer.borderWidth = 1;
    NSTextField *titleField = Label(title, 12, [NSColor colorWithWhite:0.42 alpha:1], NO);
    NSTextField *valueField = Label(value, 28, accent, YES);
    [card addSubview:titleField];
    [card addSubview:valueField];
    titleField.translatesAutoresizingMaskIntoConstraints = NO;
    valueField.translatesAutoresizingMaskIntoConstraints = NO;
    [NSLayoutConstraint activateConstraints:@[
        [titleField.leadingAnchor constraintEqualToAnchor:card.leadingAnchor constant:16],
        [titleField.topAnchor constraintEqualToAnchor:card.topAnchor constant:13],
        [valueField.leadingAnchor constraintEqualToAnchor:card.leadingAnchor constant:16],
        [valueField.bottomAnchor constraintEqualToAnchor:card.bottomAnchor constant:-12]
    ]];
    return card;
}

static NSView *MetricCard(NSString *title, NSTextField *valueField, NSColor *accent) {
    NSView *card = [[NSView alloc] initWithFrame:NSZeroRect];
    card.wantsLayer = YES;
    card.layer.backgroundColor = NSColor.whiteColor.CGColor;
    card.layer.cornerRadius = 14;
    card.layer.borderColor = [NSColor colorWithWhite:0.92 alpha:1].CGColor;
    card.layer.borderWidth = 1;
    NSTextField *titleField = Label(title, 11, [NSColor colorWithWhite:0.42 alpha:1], NO);
    valueField.font = [NSFont monospacedDigitSystemFontOfSize:28 weight:NSFontWeightSemibold];
    valueField.textColor = accent;
    [card addSubview:titleField]; [card addSubview:valueField];
    titleField.translatesAutoresizingMaskIntoConstraints = valueField.translatesAutoresizingMaskIntoConstraints = NO;
    [NSLayoutConstraint activateConstraints:@[
        [titleField.leadingAnchor constraintEqualToAnchor:card.leadingAnchor constant:14], [titleField.topAnchor constraintEqualToAnchor:card.topAnchor constant:11],
        [valueField.leadingAnchor constraintEqualToAnchor:titleField.leadingAnchor], [valueField.bottomAnchor constraintEqualToAnchor:card.bottomAnchor constant:-9]
    ]];
    return card;
}

@interface NativeBarChartView : NSView
@property NSArray<NSDictionary *> *points;
@property NSString *labelKey;
@property NSString *valueKey;
@property NSColor *barColor;
@end

@implementation NativeBarChartView
- (BOOL)isFlipped { return YES; }
- (void)drawRect:(NSRect)dirtyRect {
    [super drawRect:dirtyRect];
    [[NSColor whiteColor] setFill];
    NSRectFill(self.bounds);
    if (!self.points.count) {
        [@"所选时间内暂无数据" drawAtPoint:NSMakePoint(24, 72) withAttributes:@{NSFontAttributeName:[NSFont systemFontOfSize:13], NSForegroundColorAttributeName:NSColor.secondaryLabelColor}];
        return;
    }
    CGFloat left = 48, right = 18, top = 42, bottom = 32;
    CGFloat width = MAX(1, self.bounds.size.width - left - right);
    CGFloat height = MAX(1, self.bounds.size.height - top - bottom);
    double maximum = 1;
    for (NSDictionary *point in self.points) maximum = MAX(maximum, [point[self.valueKey] doubleValue]);
    NSColor *grid = [NSColor colorWithWhite:0.88 alpha:1];
    [grid setStroke];
    NSBezierPath *axis = [NSBezierPath bezierPath];
    [axis moveToPoint:NSMakePoint(left, top)]; [axis lineToPoint:NSMakePoint(left, top + height)]; [axis lineToPoint:NSMakePoint(left + width, top + height)]; [axis stroke];
    for (NSInteger step = 1; step <= 4; step++) {
        CGFloat y = top + height - height * step / 4;
        NSBezierPath *line = [NSBezierPath bezierPath];
        [[NSColor colorWithWhite:0.94 alpha:1] setStroke];
        [line moveToPoint:NSMakePoint(left, y)]; [line lineToPoint:NSMakePoint(left + width, y)]; [line stroke];
        [[NSString stringWithFormat:@"%.0f", maximum * step / 4] drawAtPoint:NSMakePoint(6, y - 5) withAttributes:@{NSFontAttributeName:[NSFont monospacedDigitSystemFontOfSize:9 weight:NSFontWeightRegular], NSForegroundColorAttributeName:NSColor.secondaryLabelColor}];
    }
    CGFloat slot = width / self.points.count;
    CGFloat barWidth = MAX(2, MIN(24, slot * 0.62));
    NSDictionary *labelAttributes = @{NSFontAttributeName: [NSFont systemFontOfSize:9], NSForegroundColorAttributeName: [NSColor colorWithWhite:0.42 alpha:1]};
    NSUInteger stride = MAX((NSUInteger)1, self.points.count / 8);
    [self.points enumerateObjectsUsingBlock:^(NSDictionary *point, NSUInteger index, BOOL *stop) {
        (void)stop;
        CGFloat value = [point[self.valueKey] doubleValue];
        CGFloat barHeight = height * value / maximum;
        CGFloat x = left + slot * index + (slot - barWidth) / 2;
        NSBezierPath *bar = [NSBezierPath bezierPathWithRoundedRect:NSMakeRect(x, top + height - barHeight, barWidth, barHeight) xRadius:3 yRadius:3];
        [self.barColor ?: NSColor.systemBlueColor setFill];
        [bar fill];
        if (index % stride == 0 || index + 1 == self.points.count) {
            NSString *label = [point[self.labelKey] description] ?: @"";
            if (label.length > 5) label = [label substringFromIndex:label.length - 5];
            [label drawAtPoint:NSMakePoint(MAX(left, x - 8), top + height + 6) withAttributes:labelAttributes];
        }
    }];
}
@end

@interface FlippedDashboardView : NSView
@end
@implementation FlippedDashboardView
- (BOOL)isFlipped { return YES; }
@end

static NSView *DashboardPanel(NSRect frame) {
    NSView *panel = [[FlippedDashboardView alloc] initWithFrame:frame];
    panel.wantsLayer = YES;
    panel.layer.backgroundColor = NSColor.whiteColor.CGColor;
    panel.layer.cornerRadius = 10;
    panel.layer.borderColor = [NSColor colorWithWhite:0.88 alpha:1].CGColor;
    panel.layer.borderWidth = 1;
    return panel;
}

static NSView *DashboardTypeBar(NSRect frame, NSArray *rows) {
    NSView *bar = [[NSView alloc] initWithFrame:frame];
    bar.wantsLayer = YES;
    bar.layer.cornerRadius = 3;
    bar.layer.masksToBounds = YES;
    NSArray<NSColor *> *colors = @[
        [NSColor colorWithRed:0.06 green:0.70 blue:0.48 alpha:1],
        [NSColor colorWithRed:0.96 green:0.35 blue:0.48 alpha:1],
        [NSColor colorWithRed:0.98 green:0.63 blue:0.12 alpha:1],
        [NSColor colorWithRed:0.24 green:0.48 blue:0.92 alpha:1],
        [NSColor colorWithRed:0.62 green:0.42 blue:0.86 alpha:1]
    ];
    NSInteger total = 0;
    for (NSDictionary *row in rows) total += MAX(0, [row[@"count"] integerValue]);
    if (total <= 0) return bar;
    CGFloat x = 0;
    NSUInteger index = 0;
    for (NSDictionary *row in rows) {
        NSInteger count = MAX(0, [row[@"count"] integerValue]);
        if (!count) continue;
        CGFloat width = frame.size.width * count / (CGFloat)total;
        NSView *segment = [[NSView alloc] initWithFrame:NSMakeRect(x, 0, width, frame.size.height)];
        segment.wantsLayer = YES;
        segment.layer.backgroundColor = colors[index % colors.count].CGColor;
        [bar addSubview:segment];
        x += width;
        index += 1;
    }
    return bar;
}

@interface AgentComposerTextView : NSTextView
@end

@implementation AgentComposerTextView
@end

@interface AgentPlaceholderLabel : NSTextField
@end

@implementation AgentPlaceholderLabel
- (NSView *)hitTest:(NSPoint)point { return nil; }
@end

@interface WorkspaceController : NSObject <NSApplicationDelegate, NSTableViewDataSource, NSTableViewDelegate, NSSearchFieldDelegate, NSTextViewDelegate>
@property NSDictionary *snapshot;
@property NSArray<NSDictionary *> *allLeads;
@property NSArray<NSDictionary *> *visibleLeads;
@property NSDictionary *lastAgentResult;
@property NSWindow *window;
@property NSTextView *agentTranscript;
@property AgentComposerTextView *agentInput;
@property NSPopUpButton *agentModelPicker;
@property NSTextField *statusLabel;
@property NSTextField *sipStatusLabel;
@property NSButton *agentSendButton;
@property NSProgressIndicator *agentActivityIndicator;
@property AgentPlaceholderLabel *agentPlaceholderLabel;
@property NSPopUpButton *analysisModePicker;
@property NSPopUpButton *savedAnalysisPicker;
@property NSString *agentSessionID;
@property NSAttributedString *priorAgentTranscript;
@property NSString *lastAgentQuestion;
@property NSString *snapshotPath;
@property NSString *startupError;
@property NSTask *chatlogServiceTask;
@property NSString *chatlogServiceAccountID;
@property BOOL didInitializeWorkspace;
@property BOOL agentCommandRunning;
@property BOOL wechatSyncRunning;
@property BOOL messageSearchOpening;
@property BOOL showingMessageSearch;
@property BOOL dashboardOpening;
@property BOOL dashboardLoading;
@property BOOL showingAnalyticsDashboard;
@property NSTask *activeAgentTask;
@property NSArray<NSDictionary *> *messageSearchSessions;
@property NSArray<NSDictionary *> *messageSearchResults;
@property NSComboBox *messageSessionPicker;
@property NSPopUpButton *messageDirectionPicker;
@property NSPopUpButton *messageTypePicker;
@property NSDatePicker *messageStartDate;
@property NSDatePicker *messageEndDate;
@property NSSearchField *messageKeyword;
@property NSTextField *messageLimit;
@property NSTextField *messageSearchStatus;
@property NSTableView *messageTable;
@property NSTextView *messageDetail;
@property NSArray<NSDictionary *> *dashboardGroups;
@property NSArray<NSDictionary *> *dashboardSpeakers;
@property NSTableView *dashboardGroupTable;
@property NSTableView *dashboardSpeakerTable;
@property NativeBarChartView *dashboardTrendChart;
@property NativeBarChartView *dashboardTypeChart;
@property NativeBarChartView *dashboardHourChart;
@property NSTextView *dashboardTopics;
@property NSTextField *dashboardStatus;
@property NSTextField *dashboardPrivateSummary;
@property NSTextField *dashboardGroupSummary;
@property NSView *dashboardGroupCards;
@property NSScrollView *dashboardGroupCardsScroll;
@property NSArray<NSDictionary *> *dashboardDatabases;
@property NSTableView *dashboardDatabaseTable;
@property NSScrollView *dashboardPageScroll;
@property NSDictionary *dashboardSummaryPayload;
@property NSPopUpButton *dashboardPrivatePicker;
@property NSPopUpButton *dashboardGroupPicker;
@property NSPopUpButton *dashboardRangePicker;
@property NSTextField *dashboardMessageMetric;
@property NSTextField *dashboardGroupMetric;
@property NSTextField *dashboardSenderMetric;
@property NSTextField *dashboardPrivateMetric;
@end

@implementation WorkspaceController

- (NSString *)pythonExecutable {
    return [[NSBundle mainBundle].resourcePath stringByAppendingPathComponent:@"PythonRuntime/bin/python3"];
}

- (NSMutableDictionary *)agentEnvironment {
    NSString *resourcePath = [NSBundle mainBundle].resourcePath;
    NSMutableDictionary *environment = [NSProcessInfo.processInfo.environment mutableCopy];
    NSString *runtimeBin = [resourcePath stringByAppendingPathComponent:@"PythonRuntime/bin"];
    environment[@"PATH"] = [NSString stringWithFormat:@"%@:/usr/bin:/bin:/usr/sbin:/sbin", runtimeBin];
    environment[@"PYTHONHOME"] = [resourcePath stringByAppendingPathComponent:@"PythonRuntime"];
    environment[@"PYTHONPATH"] = [resourcePath stringByAppendingPathComponent:@"Python"];
    return environment;
}

- (NSData *)drainPipe:(NSPipe *)pipe whileTaskRuns:(NSTask *)task {
    __block NSData *output = nil;
    dispatch_semaphore_t finished = dispatch_semaphore_create(0);
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        output = [pipe.fileHandleForReading readDataToEndOfFile];
        dispatch_semaphore_signal(finished);
    });
    while (task.running) {
        [NSRunLoop.currentRunLoop runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.05]];
    }
    [task waitUntilExit];
    dispatch_semaphore_wait(finished, DISPATCH_TIME_FOREVER);
    return output ?: NSData.data;
}

- (BOOL)process:(pid_t)pid listensOnTCPPort:(NSInteger)port {
    if (pid <= 0 || port <= 0) return NO;
    NSTask *task = [[NSTask alloc] init];
    task.executableURL = [NSURL fileURLWithPath:@"/usr/sbin/lsof"];
    task.arguments = @[@"-nP", @"-a", @"-p", [NSString stringWithFormat:@"%d", pid],
        [NSString stringWithFormat:@"-iTCP:%ld", (long)port], @"-sTCP:LISTEN", @"-t"];
    NSPipe *pipe = [NSPipe pipe]; task.standardOutput = pipe; task.standardError = pipe;
    if (![task launchAndReturnError:nil]) return NO;
    NSString *output = [[NSString alloc] initWithData:[self drainPipe:pipe whileTaskRuns:task] encoding:NSUTF8StringEncoding] ?: @"";
    return task.terminationStatus == 0 && [[output componentsSeparatedByCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet] containsObject:[NSString stringWithFormat:@"%d", pid]];
}

- (BOOL)chatlogHealthIsOK {
    NSURLSessionConfiguration *configuration = NSURLSessionConfiguration.ephemeralSessionConfiguration;
    configuration.timeoutIntervalForRequest = 1;
    configuration.timeoutIntervalForResource = 1;
    NSURLSession *session = [NSURLSession sessionWithConfiguration:configuration];
    dispatch_semaphore_t completed = dispatch_semaphore_create(0);
    __block BOOL healthy = NO;
    NSURLSessionDataTask *task = [session dataTaskWithURL:[NSURL URLWithString:@"http://127.0.0.1:5030/health"] completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
        NSHTTPURLResponse *http = [response isKindOfClass:NSHTTPURLResponse.class] ? (NSHTTPURLResponse *)response : nil;
        NSDictionary *object = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
        healthy = !error && http.statusCode == 200 && [object[@"status"] isEqualToString:@"ok"];
        dispatch_semaphore_signal(completed);
    }];
    [task resume];
    dispatch_semaphore_wait(completed, dispatch_time(DISPATCH_TIME_NOW, 2 * NSEC_PER_SEC));
    [session invalidateAndCancel];
    return healthy;
}

- (BOOL)chatlogReadAPIIsReadyForAccount:(NSString *)accountID {
    NSURLSessionConfiguration *configuration = NSURLSessionConfiguration.ephemeralSessionConfiguration;
    configuration.timeoutIntervalForRequest = 1;
    configuration.timeoutIntervalForResource = 1;
    NSURLSession *session = [NSURLSession sessionWithConfiguration:configuration];
    dispatch_semaphore_t completed = dispatch_semaphore_create(0);
    __block BOOL ready = NO;
    NSURL *url = [NSURL URLWithString:@"http://127.0.0.1:5030/api/v1/sessions?format=json&limit=1"];
    NSURLSessionDataTask *task = [session dataTaskWithURL:url completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
        NSHTTPURLResponse *http = [response isKindOfClass:NSHTTPURLResponse.class] ? (NSHTTPURLResponse *)response : nil;
        NSDictionary *object = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
        NSArray *sessions = object[@"sessions"];
        if (error || http.statusCode != 200 || ![sessions isKindOfClass:NSArray.class] || !sessions.count) {
            dispatch_semaphore_signal(completed);
            return;
        }
        NSURLSessionDataTask *databaseTask = [session dataTaskWithURL:[NSURL URLWithString:@"http://127.0.0.1:5030/api/v1/db"] completionHandler:^(NSData *databaseData, NSURLResponse *databaseResponse, NSError *databaseError) {
            NSHTTPURLResponse *databaseHTTP = [databaseResponse isKindOfClass:NSHTTPURLResponse.class] ? (NSHTTPURLResponse *)databaseResponse : nil;
            NSDictionary *databases = databaseData ? [NSJSONSerialization JSONObjectWithData:databaseData options:0 error:nil] : nil;
            NSArray *messageDatabases = databases[@"message"];
            NSString *marker = [NSString stringWithFormat:@"/xwechat_files/%@/db_storage/", accountID];
            __block BOOL accountMatches = accountID.length > 0;
            for (NSString *group in @[@"session", @"contact", @"message"]) {
                NSArray *paths = [databases[group] isKindOfClass:NSArray.class] ? databases[group] : @[];
                for (id value in paths) {
                    if (![value isKindOfClass:NSString.class] || ![(NSString *)value containsString:marker]) accountMatches = NO;
                }
            }
            ready = !databaseError && databaseHTTP.statusCode == 200 && [messageDatabases isKindOfClass:NSArray.class] && messageDatabases.count > 0 && accountMatches;
            dispatch_semaphore_signal(completed);
        }];
        [databaseTask resume];
    }];
    [task resume];
    dispatch_semaphore_wait(completed, dispatch_time(DISPATCH_TIME_NOW, 3 * NSEC_PER_SEC));
    [session invalidateAndCancel];
    return ready;
}

- (BOOL)prepareOwnedChatlogPortForBinary:(NSString *)binary {
    NSTask *listenerTask = [[NSTask alloc] init]; listenerTask.executableURL = [NSURL fileURLWithPath:@"/usr/sbin/lsof"]; listenerTask.arguments = @[@"-nP", @"-iTCP:5030", @"-sTCP:LISTEN", @"-t"];
    NSPipe *listenerPipe = [NSPipe pipe]; listenerTask.standardOutput = listenerPipe; listenerTask.standardError = NSFileHandle.fileHandleWithNullDevice;
    if (![listenerTask launchAndReturnError:nil]) return NO;
    NSString *output = [[NSString alloc] initWithData:[self drainPipe:listenerPipe whileTaskRuns:listenerTask] encoding:NSUTF8StringEncoding] ?: @"";
    for (NSString *line in [output componentsSeparatedByCharactersInSet:NSCharacterSet.newlineCharacterSet]) {
        pid_t pid = (pid_t)line.intValue; if (pid <= 0) continue;
        if (self.chatlogServiceTask.running && pid == self.chatlogServiceTask.processIdentifier) continue;
        NSTask *ps = [[NSTask alloc] init]; ps.executableURL = [NSURL fileURLWithPath:@"/bin/ps"]; ps.arguments = @[@"-p", [NSString stringWithFormat:@"%d", pid], @"-o", @"command="]; NSPipe *pipe = [NSPipe pipe]; ps.standardOutput = pipe; ps.standardError = NSFileHandle.fileHandleWithNullDevice;
        if (![ps launchAndReturnError:nil]) return NO;
        NSString *command = [[NSString alloc] initWithData:[self drainPipe:pipe whileTaskRuns:ps] encoding:NSUTF8StringEncoding] ?: @"";
        if (![command containsString:binary] || ![command containsString:@"action start-http"]) return NO;
        kill(pid, SIGKILL);
        while (kill(pid, 0) == 0) [NSThread sleepForTimeInterval:0.05];
    }
    return YES;
}

- (void)stopChatlogService {
    if (self.chatlogServiceTask.running) {
        [self.chatlogServiceTask terminate];
        [self.chatlogServiceTask waitUntilExit];
    }
    self.chatlogServiceTask = nil;
    self.chatlogServiceAccountID = nil;
}

- (BOOL)startChatlogServiceForAccount:(NSString *)accountID binary:(NSString *)binary error:(NSError **)error {
    if (!accountID.length || [accountID isEqualToString:@"未连接"]) {
        if (error) *error = [NSError errorWithDomain:@"WeChatSalesAgent" code:1 userInfo:@{NSLocalizedDescriptionKey: @"请先连接并同步微信账号"}];
        return NO;
    }
    if (self.chatlogServiceTask.running && [self.chatlogServiceAccountID isEqualToString:accountID]) return YES;
    [self stopChatlogService];
    if (![self prepareOwnedChatlogPortForBinary:binary]) {
        if (error) *error = [NSError errorWithDomain:@"WeChatSalesAgent" code:2 userInfo:@{NSLocalizedDescriptionKey: @"5030 端口被其他程序占用"}];
        return NO;
    }
    NSTask *task = [[NSTask alloc] init];
    task.executableURL = [NSURL fileURLWithPath:binary];
    task.arguments = @[@"action", @"start-http", @"--history", accountID];
    task.environment = self.agentEnvironment;
    task.standardOutput = NSFileHandle.fileHandleWithNullDevice;
    task.standardError = NSFileHandle.fileHandleWithNullDevice;
    if (![task launchAndReturnError:error]) return NO;
    self.chatlogServiceTask = task;
    self.chatlogServiceAccountID = accountID;
    return YES;
}

- (BOOL)isSIPDisabled {
    NSTask *task = [[NSTask alloc] init];
    task.executableURL = [NSURL fileURLWithPath:@"/usr/bin/csrutil"];
    task.arguments = @[@"status"];
    NSPipe *pipe = [NSPipe pipe];
    task.standardOutput = pipe;
    task.standardError = pipe;
    if (![task launchAndReturnError:nil]) return NO;
    NSData *data = [self drainPipe:pipe whileTaskRuns:task];
    NSString *output = [[[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] lowercaseString] ?: @"";
    return task.terminationStatus == 0 && [output containsString:@"status: disabled"];
}

- (void)updateSIPStatusLabel:(BOOL)disabled {
    self.sipStatusLabel.stringValue = disabled ? @"● SIP 已关闭" : @"● SIP 未关闭";
    self.sipStatusLabel.textColor = disabled ? NSColor.systemGreenColor : NSColor.systemOrangeColor;
}

- (void)showSIPSetup:(id)sender {
    (void)sender;
    if ([self isSIPDisabled]) {
        [self updateSIPStatusLabel:YES];
        self.statusLabel.stringValue = @"SIP 已关闭，可以连接微信";
        self.statusLabel.textColor = NSColor.systemGreenColor;
        return;
    }
    [self updateSIPStatusLabel:NO];
    NSAlert *alert = [[NSAlert alloc] init];
    alert.alertStyle = NSAlertStyleWarning;
    alert.messageText = @"内测前需要关闭 SIP";
    alert.informativeText = @"关闭 SIP 会降低 macOS 系统保护，仅用于授权的内测 Mac。\n\n1. 关机\n2. 长按电源键，直到出现“正在载入启动选项”\n3. 选择“选项”→“继续”\n4. 顶部菜单选择“实用工具”→“终端”\n5. 输入 csrutil disable 并按提示确认\n6. 重启 Mac，再打开本应用\n\n应用无法代替 macOS 恢复模式执行这项操作。";
    [alert addButtonWithTitle:@"我已完成，重新检测"];
    [alert addButtonWithTitle:@"取消"];
    if ([alert runModal] != NSAlertFirstButtonReturn) return;
    BOOL disabled = [self isSIPDisabled];
    [self updateSIPStatusLabel:disabled];
    self.statusLabel.stringValue = disabled ? @"SIP 已关闭，可以连接微信" : @"SIP 仍未关闭，请完成恢复模式操作并重启 Mac";
    self.statusLabel.textColor = disabled ? NSColor.systemGreenColor : NSColor.systemRedColor;
}

- (void)showCustomerWorkspace:(id)sender {
    (void)sender;
    if (!self.showingMessageSearch && !self.showingAnalyticsDashboard) {
        self.statusLabel.stringValue = @"已在智能分析";
        self.statusLabel.textColor = NSColor.systemGreenColor;
        return;
    }
    self.showingMessageSearch = NO;
    self.showingAnalyticsDashboard = NO;
    [self rebuildWorkspaceWithMessage:@"已返回智能分析" color:NSColor.systemGreenColor];
}

- (void)renderDashboardGroupCards {
    for (NSView *view in self.dashboardGroupCards.subviews.copy) [view removeFromSuperview];
    CGFloat gap = 10; CGFloat width = (self.dashboardGroupCards.bounds.size.width - gap * 2) / 3.0;
    NSUInteger rows = (self.dashboardGroups.count + 2) / 3;
    [self.dashboardGroupCards setFrameSize:NSMakeSize(self.dashboardGroupCards.bounds.size.width, MAX(self.dashboardGroupCardsScroll.contentSize.height, rows * 122))];
    [self.dashboardGroups enumerateObjectsUsingBlock:^(NSDictionary *group, NSUInteger index, BOOL *stop) {
        (void)stop; NSUInteger column = index % 3; NSUInteger row = index / 3;
        NSView *card = DashboardPanel(NSMakeRect(column * (width + gap), row * 122, width, 114));
        NSTextField *name = Label(group[@"chat"] ?: @"未命名群聊", 12, [NSColor colorWithWhite:0.16 alpha:1], YES);
        NSTextField *metrics = Label([NSString stringWithFormat:@"消息 %@   成员 %@   活跃 %@ 天", group[@"total"] ?: @0, group[@"active_senders"] ?: @0, group[@"active_days"] ?: @0], 11, [NSColor colorWithWhite:0.38 alpha:1], NO);
        NSTextField *detail = Label([NSString stringWithFormat:@"高峰 %@ 时   最活跃：%@ (%@)", group[@"peak_hour"] ?: @0, group[@"top_sender"] ?: @"暂无", group[@"top_sender_count"] ?: @0], 11, [NSColor colorWithWhite:0.38 alpha:1], NO);
        NSTextField *typeSummary = Label(group[@"type_summary"] ?: @"暂无消息类型", 10, [NSColor colorWithWhite:0.42 alpha:1], NO);
        typeSummary.lineBreakMode = NSLineBreakByTruncatingTail;
        NSView *typeBar = DashboardTypeBar(NSMakeRect(14, 106, width - 28, 6), group[@"by_type"] ?: @[]);
        [card addSubview:name]; [card addSubview:metrics]; [card addSubview:detail]; [card addSubview:typeSummary]; [card addSubview:typeBar];
        name.frame = NSMakeRect(14, 12, width - 28, 20); metrics.frame = NSMakeRect(14, 40, width - 28, 18); detail.frame = NSMakeRect(14, 64, width - 28, 18); typeSummary.frame = NSMakeRect(14, 88, width - 28, 18);
        [self.dashboardGroupCards addSubview:card];
    }];
}

- (void)populateDashboardPicker:(NSPopUpButton *)picker sessions:(NSArray<NSDictionary *> *)sessions selected:(NSString *)selected {
    [picker removeAllItems];
    for (NSDictionary *session in sessions) {
        NSString *username = session[@"username"] ?: @""; if (!username.length) continue;
        [picker addItemWithTitle:session[@"chat"] ?: username]; picker.lastItem.representedObject = username;
    }
    for (NSMenuItem *item in picker.itemArray) if ([item.representedObject isEqual:selected]) { [picker selectItem:item]; break; }
}

- (void)applyAnalyticsDashboardObject:(NSDictionary *)object status:(int)status error:(NSError *)error privateChat:(NSString *)privateChat groupChat:(NSString *)groupChat {
    if (status != 0 || ![object[@"overview"] isKindOfClass:NSDictionary.class]) {
        self.dashboardStatus.stringValue = [self messageFromEvent:object defaultMessage:(error.localizedDescription ?: @"无法读取聊天统计")];
        self.dashboardStatus.textColor = NSColor.systemRedColor;
        return;
    }
    NSDictionary *overview = object[@"overview"];
    self.dashboardSummaryPayload = @{ @"overview": overview ?: @{}, @"topics": object[@"topics"] ?: @[], @"mentions": object[@"mentions"] ?: @[], @"daily": object[@"daily"] ?: @[], @"groups": object[@"groups"] ?: @[] };
    [self populateDashboardPicker:self.dashboardPrivatePicker sessions:object[@"private_sessions"] ?: @[] selected:privateChat];
    [self populateDashboardPicker:self.dashboardGroupPicker sessions:object[@"group_sessions"] ?: @[] selected:groupChat];
    NSDictionary *privateStats = [object[@"private"] isKindOfClass:NSDictionary.class] ? object[@"private"] : @{};
    self.dashboardGroups = object[@"groups"] ?: @[];
    self.dashboardSpeakers = object[@"leaderboard"] ?: @[];
    self.dashboardMessageMetric.stringValue = [overview[@"messages"] description] ?: @"0";
    self.dashboardGroupMetric.stringValue = [overview[@"groups"] description] ?: @"0";
    self.dashboardSenderMetric.stringValue = [overview[@"active_sender_slots"] description] ?: @"0";
    self.dashboardPrivateMetric.stringValue = [privateStats[@"total"] description] ?: @"0";
    self.dashboardTrendChart.points = object[@"daily"] ?: @[];
    self.dashboardTypeChart.points = object[@"message_types"] ?: @[];
    self.dashboardHourChart.points = object[@"by_hour"] ?: @[];
    self.dashboardDatabases = object[@"databases"] ?: @[];
    self.dashboardPrivateSummary.stringValue = [NSString stringWithFormat:@"%@\n消息 %@  ·  我发送 %@  ·  对方发送 %@  ·  活跃 %@ 天", privateStats[@"chat"] ?: @"暂无私聊", privateStats[@"total"] ?: @0, privateStats[@"sent_count"] ?: @0, privateStats[@"received_count"] ?: @0, privateStats[@"active_days"] ?: @0];
    NSDictionary *firstGroup = [object[@"selected_group"] isKindOfClass:NSDictionary.class] ? object[@"selected_group"] : @{};
    self.dashboardGroupSummary.stringValue = [NSString stringWithFormat:@"%@\n消息 %@  ·  活跃成员 %@  ·  活跃 %@ 天  ·  高峰 %@ 时\n类型：%@", firstGroup[@"chat"] ?: @"暂无群聊", firstGroup[@"total"] ?: @0, firstGroup[@"active_senders"] ?: @0, firstGroup[@"active_days"] ?: @0, firstGroup[@"peak_hour"] ?: @0, firstGroup[@"type_summary"] ?: @"暂无消息类型"];
    for (NativeBarChartView *chart in @[self.dashboardTrendChart, self.dashboardTypeChart, self.dashboardHourChart]) [chart setNeedsDisplay:YES];
    [self renderDashboardGroupCards];
    [self.dashboardGroupTable reloadData]; [self.dashboardSpeakerTable reloadData]; [self.dashboardDatabaseTable reloadData];
    NSInteger recentMessages = 0;
    for (NSDictionary *day in object[@"daily"]) recentMessages += [day[@"count"] integerValue];
    NSMutableString *summary = [NSMutableString stringWithFormat:@"近 30 天 · 全部聊天\n\n共 %ld 条消息。\n\n当前时间范围内有 %lu 个活跃群聊。\n\n点击“生成 DeepSeek 摘要”，进一步解读交流趋势与跟进机会。", (long)recentMessages, (unsigned long)self.dashboardGroups.count];
    self.dashboardTopics.string = summary;
    self.dashboardStatus.stringValue = [NSString stringWithFormat:@"已更新 · %lu 个活跃群聊 · %lu 位发言人", (unsigned long)self.dashboardGroups.count, (unsigned long)self.dashboardSpeakers.count];
    self.dashboardStatus.textColor = NSColor.systemGreenColor;
}

- (void)loadAnalyticsDashboard:(id)sender {
    (void)sender;
    if (self.dashboardLoading) return;
    self.dashboardLoading = YES;
    self.dashboardStatus.stringValue = @"正在读取本机聊天统计…";
    self.dashboardStatus.textColor = NSColor.systemOrangeColor;
    NSString *range = self.dashboardRangePicker.selectedItem.representedObject ?: @"today";
    NSString *privateChat = self.dashboardPrivatePicker.selectedItem.representedObject ?: @"";
    NSString *groupChat = self.dashboardGroupPicker.selectedItem.representedObject ?: @"";
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        int status = 0; NSError *error = nil;
        NSArray<NSString *> *lines = [self runAgentCommand:@[@"-m", @"agent_core.dashboard_cli", @"--time-range", range, @"--private-chat", privateChat, @"--group-chat", groupChat] terminationStatus:&status error:&error];
        NSDictionary *object = [self lastJSONObjectFromLines:lines];
        dispatch_async(dispatch_get_main_queue(), ^{
            self.dashboardLoading = NO;
            if (!self.showingAnalyticsDashboard) return;
            [self applyAnalyticsDashboardObject:object status:status error:error privateChat:privateChat groupChat:groupChat];
        });
    });
}

- (void)generateDashboardSummary:(id)sender {
    (void)sender;
    if (!self.dashboardSummaryPayload) { self.dashboardTopics.string = @"请先刷新仪表盘统计。"; return; }
    NSData *data = [NSJSONSerialization dataWithJSONObject:self.dashboardSummaryPayload options:0 error:nil];
    if (!data) { self.dashboardTopics.string = @"无法准备热点摘要数据。"; return; }
    NSString *path = [NSTemporaryDirectory() stringByAppendingPathComponent:[NSString stringWithFormat:@"wechat-dashboard-summary-%@.json", NSUUID.UUID.UUIDString]];
    if (![data writeToFile:path atomically:YES]) { self.dashboardTopics.string = @"无法准备热点摘要数据。"; return; }
    self.dashboardTopics.string = @"正在使用同一 DeepSeek 配置生成热点摘要…";
    int status = 0; NSError *error = nil;
    NSArray<NSString *> *lines = [self runAgentCommand:@[@"-m", @"agent_core.dashboard_summary_cli", @"--db", self.currentDBPath, @"--input", path] terminationStatus:&status error:&error];
    [[NSFileManager defaultManager] removeItemAtPath:path error:nil];
    NSDictionary *object = [self lastJSONObjectFromLines:lines]; NSString *summary = object[@"summary"];
    if (status == 0 && [summary isKindOfClass:NSString.class] && summary.length) self.dashboardTopics.string = summary;
    else self.dashboardTopics.string = [self messageFromEvent:object defaultMessage:(error.localizedDescription ?: @"DeepSeek 热点摘要生成失败")];
}

- (void)showAnalyticsDashboardView {
    self.showingMessageSearch = NO; self.showingAnalyticsDashboard = YES;
    self.window.title = @"聊天数据仪表盘";
    NSView *root = [[NSView alloc] initWithFrame:self.window.contentView.bounds]; root.wantsLayer = YES; root.layer.backgroundColor = NSColor.whiteColor.CGColor;
    NSView *sidebar = [[NSView alloc] initWithFrame:NSZeroRect]; sidebar.wantsLayer = YES; sidebar.layer.backgroundColor = [NSColor colorWithWhite:0.965 alpha:1].CGColor;
    NSTextField *brand = Label(@"客户研究", 19, [NSColor colorWithWhite:0.12 alpha:1], YES); NSTextField *tagline = Label(@"DeepSeek Agent", 11, [NSColor colorWithWhite:0.45 alpha:1], NO);
    NSButton *dashboardButton = [NSButton buttonWithTitle:@"▦  仪表盘" target:nil action:nil]; dashboardButton.bordered = NO; dashboardButton.alignment = NSTextAlignmentLeft; dashboardButton.font = [NSFont boldSystemFontOfSize:14]; dashboardButton.contentTintColor = [NSColor colorWithWhite:0.12 alpha:1]; dashboardButton.wantsLayer = YES; dashboardButton.layer.backgroundColor = [NSColor colorWithWhite:0.89 alpha:1].CGColor; dashboardButton.layer.cornerRadius = 8;
    NSButton *customerButton = [NSButton buttonWithTitle:@"☷  智能分析" target:self action:@selector(showCustomerWorkspace:)]; customerButton.bordered = NO; customerButton.alignment = NSTextAlignmentLeft; customerButton.font = [NSFont systemFontOfSize:14]; customerButton.contentTintColor = [NSColor colorWithWhite:0.30 alpha:1];
    NSButton *messageButton = [NSButton buttonWithTitle:@"≡  消息检索" target:self action:@selector(openMessageSearch:)]; messageButton.bordered = NO; messageButton.alignment = NSTextAlignmentLeft; messageButton.font = [NSFont systemFontOfSize:14]; messageButton.contentTintColor = [NSColor colorWithWhite:0.30 alpha:1];
    NSTextField *privacy = Label(@"原始聊天仅在本机统计", 11, [NSColor colorWithWhite:0.55 alpha:1], NO);
    for (NSView *view in @[brand, tagline, dashboardButton, customerButton, messageButton, privacy]) { [sidebar addSubview:view]; view.translatesAutoresizingMaskIntoConstraints = NO; } [root addSubview:sidebar]; sidebar.translatesAutoresizingMaskIntoConstraints = NO;
    [NSLayoutConstraint activateConstraints:@[[sidebar.leadingAnchor constraintEqualToAnchor:root.leadingAnchor], [sidebar.topAnchor constraintEqualToAnchor:root.topAnchor], [sidebar.bottomAnchor constraintEqualToAnchor:root.bottomAnchor], [sidebar.widthAnchor constraintEqualToConstant:210], [brand.leadingAnchor constraintEqualToAnchor:sidebar.leadingAnchor constant:22], [brand.topAnchor constraintEqualToAnchor:sidebar.topAnchor constant:28], [tagline.leadingAnchor constraintEqualToAnchor:brand.leadingAnchor], [tagline.topAnchor constraintEqualToAnchor:brand.bottomAnchor constant:5], [dashboardButton.leadingAnchor constraintEqualToAnchor:sidebar.leadingAnchor constant:14], [dashboardButton.trailingAnchor constraintEqualToAnchor:sidebar.trailingAnchor constant:-14], [dashboardButton.topAnchor constraintEqualToAnchor:tagline.bottomAnchor constant:34], [dashboardButton.heightAnchor constraintEqualToConstant:42], [messageButton.leadingAnchor constraintEqualToAnchor:sidebar.leadingAnchor constant:18], [messageButton.trailingAnchor constraintEqualToAnchor:sidebar.trailingAnchor constant:-18], [messageButton.topAnchor constraintEqualToAnchor:dashboardButton.bottomAnchor constant:6], [messageButton.heightAnchor constraintEqualToConstant:38], [customerButton.leadingAnchor constraintEqualToAnchor:messageButton.leadingAnchor], [customerButton.trailingAnchor constraintEqualToAnchor:messageButton.trailingAnchor], [customerButton.topAnchor constraintEqualToAnchor:messageButton.bottomAnchor constant:4], [customerButton.heightAnchor constraintEqualToConstant:38], [privacy.leadingAnchor constraintEqualToAnchor:sidebar.leadingAnchor constant:22], [privacy.bottomAnchor constraintEqualToAnchor:sidebar.bottomAnchor constant:-24]]];
    CGFloat contentWidth = MAX(940, root.bounds.size.width - 250); CGFloat half = (contentWidth - 10) / 2.0;
    NSScrollView *pageScroll = [[NSScrollView alloc] initWithFrame:NSMakeRect(210, 0, root.bounds.size.width - 210, root.bounds.size.height)]; self.dashboardPageScroll = pageScroll; pageScroll.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable; pageScroll.hasVerticalScroller = YES; pageScroll.drawsBackground = NO;
    FlippedDashboardView *content = [[FlippedDashboardView alloc] initWithFrame:NSMakeRect(0, 0, contentWidth + 40, 1850)]; content.wantsLayer = YES; content.layer.backgroundColor = [NSColor colorWithRed:0.96 green:0.97 blue:0.99 alpha:1].CGColor; pageScroll.documentView = content; [root addSubview:pageScroll];
    CGFloat x = 20;
    NSTextField *title = Label(@"聊天数据仪表盘", 26, [NSColor colorWithRed:0.06 green:0.10 blue:0.20 alpha:1], YES); title.frame = NSMakeRect(x, 18, 320, 34);
    NSTextField *subtitle = Label(@"看清交流趋势，发现值得跟进的关系 · 全部会话，本机统计", 12, [NSColor colorWithWhite:0.42 alpha:1], NO); subtitle.frame = NSMakeRect(x, 52, 600, 20);
    NSButton *refresh = [NSButton buttonWithTitle:@"刷新统计" target:self action:@selector(loadAnalyticsDashboard:)]; refresh.frame = NSMakeRect(contentWidth - 92, 22, 92, 28);
    self.dashboardStatus = Label(@"准备读取…", 12, NSColor.systemOrangeColor, YES); self.dashboardStatus.alignment = NSTextAlignmentRight; self.dashboardStatus.frame = NSMakeRect(contentWidth - 350, 28, 245, 20);
    for (NSView *view in @[title, subtitle, refresh, self.dashboardStatus]) [content addSubview:view];

    NSTextField *analysisTitle = Label(@"聊天分析", 18, [NSColor colorWithWhite:0.14 alpha:1], YES); analysisTitle.frame = NSMakeRect(x, 88, 200, 26); [content addSubview:analysisTitle];
    NSView *privatePanel = DashboardPanel(NSMakeRect(x, 120, half, 120)); NSView *groupPanel = DashboardPanel(NSMakeRect(x + half + 10, 120, half, 120));
    NSTextField *privateTitle = Label(@"私聊分析", 14, [NSColor colorWithWhite:0.16 alpha:1], YES); privateTitle.frame = NSMakeRect(16, 12, 120, 22); self.dashboardPrivatePicker = [[NSPopUpButton alloc] initWithFrame:NSMakeRect(145, 9, half - 161, 28) pullsDown:NO]; self.dashboardPrivatePicker.target = self; self.dashboardPrivatePicker.action = @selector(loadAnalyticsDashboard:); self.dashboardPrivateSummary = Label(@"正在读取私聊统计…", 12, [NSColor colorWithWhite:0.38 alpha:1], NO); self.dashboardPrivateSummary.frame = NSMakeRect(16, 50, half - 32, 52); self.dashboardPrivateSummary.maximumNumberOfLines = 2; self.dashboardPrivateSummary.lineBreakMode = NSLineBreakByWordWrapping;
    NSTextField *groupAnalysisTitle = Label(@"群聊分析", 14, [NSColor colorWithWhite:0.16 alpha:1], YES); groupAnalysisTitle.frame = NSMakeRect(16, 12, 120, 22); self.dashboardGroupPicker = [[NSPopUpButton alloc] initWithFrame:NSMakeRect(145, 9, half - 161, 28) pullsDown:NO]; self.dashboardGroupPicker.target = self; self.dashboardGroupPicker.action = @selector(loadAnalyticsDashboard:); self.dashboardGroupSummary = Label(@"正在读取群聊统计…", 12, [NSColor colorWithWhite:0.38 alpha:1], NO); self.dashboardGroupSummary.frame = NSMakeRect(16, 50, half - 32, 52); self.dashboardGroupSummary.maximumNumberOfLines = 3; self.dashboardGroupSummary.lineBreakMode = NSLineBreakByWordWrapping;
    [privatePanel addSubview:privateTitle]; [privatePanel addSubview:self.dashboardPrivatePicker]; [privatePanel addSubview:self.dashboardPrivateSummary]; [groupPanel addSubview:groupAnalysisTitle]; [groupPanel addSubview:self.dashboardGroupPicker]; [groupPanel addSubview:self.dashboardGroupSummary]; [content addSubview:privatePanel]; [content addSubview:groupPanel];

    NSTextField *overviewTitle = Label(@"群聊数据概览", 18, [NSColor colorWithWhite:0.14 alpha:1], YES); overviewTitle.frame = NSMakeRect(x, 258, 220, 26); self.dashboardRangePicker = [[NSPopUpButton alloc] initWithFrame:NSMakeRect(x + contentWidth - 150, 255, 150, 28) pullsDown:NO]; NSArray *rangeSpecs = @[@[@"今天", @"today"], @[@"近 24 小时", @"last-1d"], @[@"近 30 天", @"last-30d"], @[@"全部", @"all"]]; for (NSArray *spec in rangeSpecs) { [self.dashboardRangePicker addItemWithTitle:spec[0]]; self.dashboardRangePicker.lastItem.representedObject = spec[1]; } self.dashboardRangePicker.target = self; self.dashboardRangePicker.action = @selector(loadAnalyticsDashboard:); [content addSubview:overviewTitle]; [content addSubview:self.dashboardRangePicker];
    self.dashboardMessageMetric = Label(@"0", 24, NSColor.systemBlueColor, YES); self.dashboardGroupMetric = Label(@"0", 24, NSColor.systemGreenColor, YES); self.dashboardSenderMetric = Label(@"0", 24, NSColor.systemOrangeColor, YES); self.dashboardPrivateMetric = Label(@"0", 24, [NSColor colorWithRed:0.38 green:0.23 blue:0.72 alpha:1], YES);
    NSStackView *cards = [[NSStackView alloc] initWithFrame:NSMakeRect(x, 290, contentWidth, 76)]; cards.orientation = NSUserInterfaceLayoutOrientationHorizontal; cards.spacing = 10; cards.distribution = NSStackViewDistributionFillEqually; [cards addArrangedSubview:MetricCard(@"群消息总量", self.dashboardMessageMetric, NSColor.systemBlueColor)]; [cards addArrangedSubview:MetricCard(@"活跃群聊", self.dashboardGroupMetric, NSColor.systemGreenColor)]; [cards addArrangedSubview:MetricCard(@"活跃成员人次", self.dashboardSenderMetric, NSColor.systemOrangeColor)]; [cards addArrangedSubview:MetricCard(@"最新私聊消息", self.dashboardPrivateMetric, [NSColor colorWithRed:0.38 green:0.23 blue:0.72 alpha:1])]; [content addSubview:cards];

    NSTextField *comparisonTitle = Label(@"群聊对比", 18, [NSColor colorWithWhite:0.14 alpha:1], YES); comparisonTitle.frame = NSMakeRect(x, 386, 200, 26); [content addSubview:comparisonTitle]; self.dashboardGroupCards = [[FlippedDashboardView alloc] initWithFrame:NSMakeRect(0, 0, contentWidth - 16, 438)]; self.dashboardGroupCardsScroll = [[NSScrollView alloc] initWithFrame:NSMakeRect(x, 418, contentWidth, 438)]; self.dashboardGroupCardsScroll.documentView = self.dashboardGroupCards; self.dashboardGroupCardsScroll.hasVerticalScroller = YES; self.dashboardGroupCardsScroll.drawsBackground = NO; [content addSubview:self.dashboardGroupCardsScroll];

    NSTextField *groupTableTitle = Label(@"群聊对比表", 17, [NSColor colorWithWhite:0.14 alpha:1], YES); groupTableTitle.frame = NSMakeRect(x, 872, 200, 25); NSTextField *speakerTitle = Label(@"发言人排行榜", 17, [NSColor colorWithWhite:0.14 alpha:1], YES); speakerTitle.frame = NSMakeRect(x + half + 10, 872, 200, 25); [content addSubview:groupTableTitle]; [content addSubview:speakerTitle];
    self.dashboardGroupTable = [[NSTableView alloc] initWithFrame:NSZeroRect]; self.dashboardGroupTable.dataSource = self; self.dashboardGroupTable.delegate = self; self.dashboardGroupTable.rowHeight = 28; self.dashboardGroupTable.usesAlternatingRowBackgroundColors = YES;
    for (NSArray *spec in @[@[@"群聊", @"chat", @160], @[@"消息", @"total", @55], @[@"成员", @"active_senders", @50], @[@"天数", @"active_days", @45], @[@"高峰", @"peak_hour", @50], @[@"最活跃", @"top_sender", @100], @[@"类型结构", @"type_summary", @230]]) { NSTableColumn *column = [[NSTableColumn alloc] initWithIdentifier:spec[1]]; column.title = spec[0]; column.width = [spec[2] doubleValue]; [self.dashboardGroupTable addTableColumn:column]; }
    self.dashboardSpeakerTable = [[NSTableView alloc] initWithFrame:NSZeroRect]; self.dashboardSpeakerTable.dataSource = self; self.dashboardSpeakerTable.delegate = self; self.dashboardSpeakerTable.rowHeight = 28; self.dashboardSpeakerTable.usesAlternatingRowBackgroundColors = YES;
    for (NSArray *spec in @[@[@"发言人", @"name", @145], @[@"来源群", @"group", @180], @[@"消息数", @"count", @75], @[@"覆盖群", @"group_count", @65]]) { NSTableColumn *column = [[NSTableColumn alloc] initWithIdentifier:spec[1]]; column.title = spec[0]; column.width = [spec[2] doubleValue]; [self.dashboardSpeakerTable addTableColumn:column]; }
    NSScrollView *groupScroll = [[NSScrollView alloc] initWithFrame:NSMakeRect(x, 902, half, 220)]; groupScroll.documentView = self.dashboardGroupTable; groupScroll.hasVerticalScroller = YES; groupScroll.drawsBackground = YES; NSScrollView *speakerScroll = [[NSScrollView alloc] initWithFrame:NSMakeRect(x + half + 10, 902, half, 220)]; speakerScroll.documentView = self.dashboardSpeakerTable; speakerScroll.hasVerticalScroller = YES; speakerScroll.drawsBackground = YES; [content addSubview:groupScroll]; [content addSubview:speakerScroll];

    NSTextField *chartsTitle = Label(@"群聊对比图表", 18, [NSColor colorWithWhite:0.14 alpha:1], YES); chartsTitle.frame = NSMakeRect(x, 1142, 220, 26); [content addSubview:chartsTitle];
    self.dashboardTypeChart = [[NativeBarChartView alloc] initWithFrame:NSMakeRect(x, 1174, half, 210)]; self.dashboardTypeChart.labelKey = @"type"; self.dashboardTypeChart.valueKey = @"count"; self.dashboardTypeChart.barColor = [NSColor colorWithRed:0.95 green:0.35 blue:0.48 alpha:1]; self.dashboardTypeChart.wantsLayer = YES; self.dashboardTypeChart.layer.cornerRadius = 10;
    self.dashboardHourChart = [[NativeBarChartView alloc] initWithFrame:NSMakeRect(x + half + 10, 1174, half, 210)]; self.dashboardHourChart.labelKey = @"hour"; self.dashboardHourChart.valueKey = @"count"; self.dashboardHourChart.barColor = NSColor.systemBlueColor; self.dashboardHourChart.wantsLayer = YES; self.dashboardHourChart.layer.cornerRadius = 10;
    NSTextField *typeTitle = Label(@"消息类型结构", 14, [NSColor colorWithWhite:0.16 alpha:1], YES); typeTitle.frame = NSMakeRect(x + 12, 1184, 160, 20); NSTextField *hourTitle = Label(@"24 小时活跃度", 14, [NSColor colorWithWhite:0.16 alpha:1], YES); hourTitle.frame = NSMakeRect(x + half + 22, 1184, 160, 20); [content addSubview:self.dashboardTypeChart]; [content addSubview:self.dashboardHourChart]; [content addSubview:typeTitle]; [content addSubview:hourTitle];

    NSTextField *trendTitle = Label(@"消息趋势", 18, [NSColor colorWithWhite:0.14 alpha:1], YES); trendTitle.frame = NSMakeRect(x, 1404, 180, 26); NSTextField *hotTitle = Label(@"热点摘要", 18, [NSColor colorWithWhite:0.14 alpha:1], YES); hotTitle.frame = NSMakeRect(x + half + 10, 1404, 180, 26); NSButton *summaryButton = [NSButton buttonWithTitle:@"生成 DeepSeek 摘要" target:self action:@selector(generateDashboardSummary:)]; summaryButton.frame = NSMakeRect(x + contentWidth - 154, 1402, 154, 28); [content addSubview:trendTitle]; [content addSubview:hotTitle]; [content addSubview:summaryButton];
    self.dashboardTrendChart = [[NativeBarChartView alloc] initWithFrame:NSMakeRect(x, 1436, half, 210)]; self.dashboardTrendChart.labelKey = @"date"; self.dashboardTrendChart.valueKey = @"count"; self.dashboardTrendChart.barColor = [NSColor colorWithRed:0.06 green:0.70 blue:0.48 alpha:1]; self.dashboardTrendChart.wantsLayer = YES; self.dashboardTrendChart.layer.cornerRadius = 10;
    self.dashboardTopics = [[NSTextView alloc] initWithFrame:NSMakeRect(x + half + 10, 1436, half, 210)]; self.dashboardTopics.editable = NO; self.dashboardTopics.font = [NSFont systemFontOfSize:12]; self.dashboardTopics.textContainerInset = NSMakeSize(12, 12); self.dashboardTopics.backgroundColor = NSColor.whiteColor; self.dashboardTopics.string = @"近 30 天本机统计正在读取…"; self.dashboardTopics.wantsLayer = YES; self.dashboardTopics.layer.cornerRadius = 10; [content addSubview:self.dashboardTrendChart]; [content addSubview:self.dashboardTopics];

    NSTextField *databaseTitle = Label(@"当前可查询数据库", 18, [NSColor colorWithWhite:0.14 alpha:1], YES); databaseTitle.frame = NSMakeRect(x, 1666, 260, 26); [content addSubview:databaseTitle];
    self.dashboardDatabaseTable = [[NSTableView alloc] initWithFrame:NSZeroRect]; self.dashboardDatabaseTable.dataSource = self; self.dashboardDatabaseTable.delegate = self; self.dashboardDatabaseTable.rowHeight = 27; self.dashboardDatabaseTable.usesAlternatingRowBackgroundColors = YES; for (NSArray *spec in @[@[@"类型", @"kind", @120], @[@"本机数据库路径", @"path", @820]]) { NSTableColumn *column = [[NSTableColumn alloc] initWithIdentifier:spec[1]]; column.title = spec[0]; column.width = [spec[2] doubleValue]; [self.dashboardDatabaseTable addTableColumn:column]; } NSScrollView *databaseScroll = [[NSScrollView alloc] initWithFrame:NSMakeRect(x, 1698, contentWidth, 125)]; databaseScroll.documentView = self.dashboardDatabaseTable; databaseScroll.hasVerticalScroller = YES; databaseScroll.drawsBackground = YES; [content addSubview:databaseScroll];
    PolishWorkspace(root);
    self.window.contentView = root;
    [self loadAnalyticsDashboard:nil];
}

- (void)openAnalyticsDashboard:(id)sender {
    (void)sender;
    NSString *accountID = self.snapshot[@"account_id"] ?: @"";
    if (self.chatlogServiceTask.running && [self.chatlogServiceAccountID isEqualToString:accountID] && [self process:self.chatlogServiceTask.processIdentifier listensOnTCPPort:5030] && [self chatlogReadAPIIsReadyForAccount:accountID]) { [self showAnalyticsDashboardView]; return; }
    if (self.dashboardOpening) return;
    NSString *binary = [[NSBundle mainBundle].resourcePath stringByAppendingPathComponent:@"Chatlog/chatlog-darwin-arm64"];
    if (![[NSFileManager defaultManager] isExecutableFileAtPath:binary]) { self.statusLabel.stringValue = @"本地微信数据组件缺失"; self.statusLabel.textColor = NSColor.systemRedColor; return; }
    NSError *launchError = nil;
    if (![self startChatlogServiceForAccount:accountID binary:binary error:&launchError]) { self.statusLabel.stringValue = launchError.localizedDescription ?: @"仪表盘服务启动失败"; self.statusLabel.textColor = NSColor.systemRedColor; return; }
    self.dashboardOpening = YES; self.statusLabel.stringValue = @"正在启动聊天数据仪表盘…"; self.statusLabel.textColor = NSColor.systemOrangeColor; NSTask *ownedService = self.chatlogServiceTask;
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{ while (ownedService.running) { if ([self process:ownedService.processIdentifier listensOnTCPPort:5030] && [self chatlogReadAPIIsReadyForAccount:accountID]) { dispatch_async(dispatch_get_main_queue(), ^{ if (self.chatlogServiceTask != ownedService || !self.dashboardOpening) return; self.dashboardOpening = NO; [self showAnalyticsDashboardView]; }); return; } [NSThread sleepForTimeInterval:0.25]; } dispatch_async(dispatch_get_main_queue(), ^{ if (!self.dashboardOpening) return; self.dashboardOpening = NO; self.statusLabel.stringValue = @"仪表盘服务启动失败"; self.statusLabel.textColor = NSColor.systemRedColor; }); });
}

- (void)loadMessageSearchSessions {
    int status = 0;
    NSError *error = nil;
    NSArray<NSString *> *lines = [self runAgentCommand:@[@"-m", @"agent_core.message_search_cli", @"sessions", @"--limit", @"5000"] terminationStatus:&status error:&error];
    NSDictionary *object = [self lastJSONObjectFromLines:lines];
    NSArray *sessions = object[@"sessions"];
    if (status != 0 || ![sessions isKindOfClass:NSArray.class]) {
        self.messageSearchStatus.stringValue = [self messageFromEvent:object defaultMessage:(error.localizedDescription ?: @"无法读取微信会话")];
        self.messageSearchStatus.textColor = NSColor.systemRedColor;
        return;
    }
    self.messageSearchSessions = sessions;
    [self.messageSessionPicker removeAllItems];
    for (NSDictionary *session in sessions) {
        NSString *name = session[@"display_name"] ?: session[@"username"] ?: @"未命名会话";
        NSString *prefix = [session[@"is_group"] boolValue] ? @"群聊 · " : @"私聊 · ";
        [self.messageSessionPicker addItemWithObjectValue:[NSString stringWithFormat:@"%@ · %@%@", name, prefix, session[@"username"]]];
    }
    if (sessions.count) [self.messageSessionPicker selectItemAtIndex:0];
    self.messageSearchStatus.stringValue = [NSString stringWithFormat:@"已加载 %lu 个会话", (unsigned long)sessions.count];
    self.messageSearchStatus.textColor = NSColor.systemGreenColor;
}

- (void)showMessageSearchView {
    self.showingMessageSearch = YES;
    self.messageSearchResults = @[];
    self.window.title = @"微信消息检索";
    NSView *root = [[NSView alloc] initWithFrame:self.window.contentView.bounds];
    root.wantsLayer = YES;
    root.layer.backgroundColor = NSColor.whiteColor.CGColor;

    NSView *sidebar = [[NSView alloc] initWithFrame:NSZeroRect];
    sidebar.wantsLayer = YES;
    sidebar.layer.backgroundColor = [NSColor colorWithWhite:0.965 alpha:1].CGColor;
    NSTextField *brand = Label(@"微信客户分析 Agent", 19, [NSColor colorWithWhite:0.12 alpha:1], YES);
    NSTextField *tagline = Label(@"DeepSeek", 11, [NSColor colorWithWhite:0.45 alpha:1], NO);
    NSButton *dashboardButton = [NSButton buttonWithTitle:@"▦  仪表盘" target:self action:@selector(openAnalyticsDashboard:)];
    dashboardButton.bordered = NO; dashboardButton.alignment = NSTextAlignmentLeft; dashboardButton.font = [NSFont systemFontOfSize:14]; dashboardButton.contentTintColor = [NSColor colorWithWhite:0.30 alpha:1];
    NSButton *customerButton = [NSButton buttonWithTitle:@"☷  智能分析" target:self action:@selector(showCustomerWorkspace:)];
    customerButton.bordered = NO; customerButton.alignment = NSTextAlignmentLeft; customerButton.font = [NSFont systemFontOfSize:14]; customerButton.contentTintColor = [NSColor colorWithWhite:0.30 alpha:1];
    NSButton *messageButton = [NSButton buttonWithTitle:@"≡  消息检索" target:nil action:nil];
    messageButton.bordered = NO; messageButton.alignment = NSTextAlignmentLeft; messageButton.font = [NSFont boldSystemFontOfSize:14]; messageButton.contentTintColor = [NSColor colorWithWhite:0.12 alpha:1]; messageButton.wantsLayer = YES; messageButton.layer.backgroundColor = [NSColor colorWithWhite:0.89 alpha:1].CGColor; messageButton.layer.cornerRadius = 8;
    NSTextField *privacy = Label(@"原始聊天仅在本机查询", 11, [NSColor colorWithWhite:0.55 alpha:1], NO);
    for (NSView *view in @[brand, tagline, dashboardButton, customerButton, messageButton, privacy]) { [sidebar addSubview:view]; view.translatesAutoresizingMaskIntoConstraints = NO; }
    [root addSubview:sidebar]; sidebar.translatesAutoresizingMaskIntoConstraints = NO;
    [NSLayoutConstraint activateConstraints:@[
        [sidebar.leadingAnchor constraintEqualToAnchor:root.leadingAnchor], [sidebar.topAnchor constraintEqualToAnchor:root.topAnchor], [sidebar.bottomAnchor constraintEqualToAnchor:root.bottomAnchor], [sidebar.widthAnchor constraintEqualToConstant:210],
        [brand.leadingAnchor constraintEqualToAnchor:sidebar.leadingAnchor constant:22], [brand.topAnchor constraintEqualToAnchor:sidebar.topAnchor constant:28],
        [tagline.leadingAnchor constraintEqualToAnchor:brand.leadingAnchor], [tagline.topAnchor constraintEqualToAnchor:brand.bottomAnchor constant:5],
        [dashboardButton.leadingAnchor constraintEqualToAnchor:sidebar.leadingAnchor constant:18], [dashboardButton.trailingAnchor constraintEqualToAnchor:sidebar.trailingAnchor constant:-18], [dashboardButton.topAnchor constraintEqualToAnchor:tagline.bottomAnchor constant:34], [dashboardButton.heightAnchor constraintEqualToConstant:38],
        [messageButton.leadingAnchor constraintEqualToAnchor:sidebar.leadingAnchor constant:14], [messageButton.trailingAnchor constraintEqualToAnchor:sidebar.trailingAnchor constant:-14], [messageButton.topAnchor constraintEqualToAnchor:dashboardButton.bottomAnchor constant:4], [messageButton.heightAnchor constraintEqualToConstant:42],
        [customerButton.leadingAnchor constraintEqualToAnchor:dashboardButton.leadingAnchor], [customerButton.trailingAnchor constraintEqualToAnchor:dashboardButton.trailingAnchor], [customerButton.topAnchor constraintEqualToAnchor:messageButton.bottomAnchor constant:4], [customerButton.heightAnchor constraintEqualToConstant:38],
        [privacy.leadingAnchor constraintEqualToAnchor:sidebar.leadingAnchor constant:22], [privacy.bottomAnchor constraintEqualToAnchor:sidebar.bottomAnchor constant:-24]
    ]];

    NSView *content = [[NSView alloc] initWithFrame:NSZeroRect];
    [root addSubview:content]; content.translatesAutoresizingMaskIntoConstraints = NO;
    [NSLayoutConstraint activateConstraints:@[[content.leadingAnchor constraintEqualToAnchor:sidebar.trailingAnchor], [content.trailingAnchor constraintEqualToAnchor:root.trailingAnchor], [content.topAnchor constraintEqualToAnchor:root.topAnchor], [content.bottomAnchor constraintEqualToAnchor:root.bottomAnchor]]];
    NSTextField *title = Label(@"消息检索", 26, [NSColor colorWithRed:0.06 green:0.10 blue:0.20 alpha:1], YES);
    NSTextField *subtitle = Label(@"按会话、时间、关键词、方向和类型查询本机微信原始消息", 12, [NSColor colorWithWhite:0.42 alpha:1], NO);
    [content addSubview:title]; [content addSubview:subtitle]; title.translatesAutoresizingMaskIntoConstraints = subtitle.translatesAutoresizingMaskIntoConstraints = NO;

    NSView *filters = [[NSView alloc] initWithFrame:NSZeroRect]; filters.wantsLayer = YES; filters.layer.backgroundColor = NSColor.whiteColor.CGColor; filters.layer.cornerRadius = 10; filters.layer.borderWidth = 1; filters.layer.borderColor = [NSColor colorWithWhite:0.88 alpha:1].CGColor;
    self.messageSessionPicker = [[NSComboBox alloc] initWithFrame:NSZeroRect];
    self.messageSessionPicker.completes = YES;
    self.messageSessionPicker.numberOfVisibleItems = 16;
    self.messageSessionPicker.placeholderString = @"输入会话名称，或展开全部会话";
    self.messageSessionPicker.toolTip = @"全部微信会话；输入名称可自动补全，选择后查询消息。";
    self.messageStartDate = [[NSDatePicker alloc] initWithFrame:NSZeroRect]; self.messageStartDate.datePickerElements = NSDatePickerElementFlagYearMonthDay; self.messageStartDate.datePickerStyle = NSDatePickerStyleTextFieldAndStepper; self.messageStartDate.dateValue = [NSDate dateWithTimeIntervalSinceNow:-30 * 86400];
    self.messageEndDate = [[NSDatePicker alloc] initWithFrame:NSZeroRect]; self.messageEndDate.datePickerElements = NSDatePickerElementFlagYearMonthDay; self.messageEndDate.datePickerStyle = NSDatePickerStyleTextFieldAndStepper; self.messageEndDate.dateValue = [NSDate dateWithTimeIntervalSinceNow:86400];
    self.messageKeyword = [[NSSearchField alloc] initWithFrame:NSZeroRect]; self.messageKeyword.placeholderString = @"内容关键词（可选）";
    self.messageDirectionPicker = [[NSPopUpButton alloc] initWithFrame:NSZeroRect pullsDown:NO]; [self.messageDirectionPicker addItemsWithTitles:@[@"全部方向", @"仅我发送", @"仅对方发送"]];
    self.messageTypePicker = [[NSPopUpButton alloc] initWithFrame:NSZeroRect pullsDown:NO]; [self.messageTypePicker addItemsWithTitles:@[@"全部类型", @"文字", @"图片", @"语音", @"视频", @"文件", @"链接", @"引用", @"系统"]];
    self.messageLimit = [[NSTextField alloc] initWithFrame:NSZeroRect]; self.messageLimit.stringValue = @"200"; self.messageLimit.placeholderString = @"最多 1000 条";
    NSButton *searchButton = [NSButton buttonWithTitle:@"查询消息" target:self action:@selector(runMessageSearch:)]; searchButton.bezelStyle = NSBezelStyleTexturedRounded; searchButton.contentTintColor = NSColor.systemBlueColor;
    self.messageSearchStatus = Label(@"正在读取会话…", 12, NSColor.systemOrangeColor, YES);
    for (NSView *view in @[self.messageSessionPicker, self.messageStartDate, self.messageEndDate, self.messageKeyword, self.messageDirectionPicker, self.messageTypePicker, self.messageLimit, searchButton, self.messageSearchStatus]) { [filters addSubview:view]; view.translatesAutoresizingMaskIntoConstraints = NO; }
    [content addSubview:filters]; filters.translatesAutoresizingMaskIntoConstraints = NO;

    self.messageTable = [[NSTableView alloc] initWithFrame:NSZeroRect]; self.messageTable.dataSource = self; self.messageTable.delegate = self; self.messageTable.headerView = [[NSTableHeaderView alloc] init]; self.messageTable.rowHeight = 34; self.messageTable.usesAlternatingRowBackgroundColors = YES; self.messageTable.backgroundColor = NSColor.whiteColor;
    NSArray *columns = @[@[@"时间", @"time", @130], @[@"方向", @"direction", @65], @[@"发送者", @"sender", @110], @[@"类型", @"type", @65], @[@"内容", @"content", @300]];
    for (NSArray *spec in columns) { NSTableColumn *column = [[NSTableColumn alloc] initWithIdentifier:spec[1]]; column.title = spec[0]; column.width = [spec[2] doubleValue]; [self.messageTable addTableColumn:column]; }
    NSScrollView *tableScroll = [[NSScrollView alloc] initWithFrame:NSZeroRect]; tableScroll.documentView = self.messageTable; tableScroll.hasVerticalScroller = YES; tableScroll.drawsBackground = YES; tableScroll.backgroundColor = NSColor.whiteColor;
    self.messageDetail = [[NSTextView alloc] initWithFrame:NSMakeRect(0, 0, 320, 300)]; self.messageDetail.editable = NO; self.messageDetail.verticallyResizable = YES; self.messageDetail.textContainer.widthTracksTextView = YES; self.messageDetail.autoresizingMask = NSViewWidthSizable; self.messageDetail.font = [NSFont systemFontOfSize:13]; self.messageDetail.textContainerInset = NSMakeSize(12, 12); self.messageDetail.string = @"选择一条消息查看完整内容";
    NSScrollView *detailScroll = [[NSScrollView alloc] initWithFrame:NSZeroRect]; detailScroll.documentView = self.messageDetail; detailScroll.hasVerticalScroller = YES; detailScroll.drawsBackground = YES; detailScroll.backgroundColor = [NSColor colorWithRed:0.97 green:0.98 blue:1 alpha:1];
    [content addSubview:tableScroll]; [content addSubview:detailScroll]; tableScroll.translatesAutoresizingMaskIntoConstraints = detailScroll.translatesAutoresizingMaskIntoConstraints = NO;
    [NSLayoutConstraint activateConstraints:@[
        [title.leadingAnchor constraintEqualToAnchor:content.leadingAnchor constant:28], [title.topAnchor constraintEqualToAnchor:content.topAnchor constant:24],
        [subtitle.leadingAnchor constraintEqualToAnchor:title.leadingAnchor], [subtitle.topAnchor constraintEqualToAnchor:title.bottomAnchor constant:4],
        [filters.leadingAnchor constraintEqualToAnchor:title.leadingAnchor], [filters.trailingAnchor constraintEqualToAnchor:content.trailingAnchor constant:-28], [filters.topAnchor constraintEqualToAnchor:subtitle.bottomAnchor constant:18], [filters.heightAnchor constraintEqualToConstant:112],
        [self.messageSessionPicker.leadingAnchor constraintEqualToAnchor:filters.leadingAnchor constant:14], [self.messageSessionPicker.topAnchor constraintEqualToAnchor:filters.topAnchor constant:14], [self.messageSessionPicker.widthAnchor constraintEqualToConstant:260],
        [self.messageStartDate.leadingAnchor constraintEqualToAnchor:self.messageSessionPicker.trailingAnchor constant:10], [self.messageStartDate.centerYAnchor constraintEqualToAnchor:self.messageSessionPicker.centerYAnchor], [self.messageStartDate.widthAnchor constraintEqualToConstant:135],
        [self.messageEndDate.leadingAnchor constraintEqualToAnchor:self.messageStartDate.trailingAnchor constant:8], [self.messageEndDate.centerYAnchor constraintEqualToAnchor:self.messageSessionPicker.centerYAnchor], [self.messageEndDate.widthAnchor constraintEqualToConstant:135],
        [self.messageKeyword.leadingAnchor constraintEqualToAnchor:self.messageEndDate.trailingAnchor constant:10], [self.messageKeyword.centerYAnchor constraintEqualToAnchor:self.messageSessionPicker.centerYAnchor], [self.messageKeyword.trailingAnchor constraintEqualToAnchor:filters.trailingAnchor constant:-14],
        [self.messageDirectionPicker.leadingAnchor constraintEqualToAnchor:self.messageSessionPicker.leadingAnchor], [self.messageDirectionPicker.topAnchor constraintEqualToAnchor:self.messageSessionPicker.bottomAnchor constant:12], [self.messageDirectionPicker.widthAnchor constraintEqualToConstant:140],
        [self.messageTypePicker.leadingAnchor constraintEqualToAnchor:self.messageDirectionPicker.trailingAnchor constant:8], [self.messageTypePicker.centerYAnchor constraintEqualToAnchor:self.messageDirectionPicker.centerYAnchor], [self.messageTypePicker.widthAnchor constraintEqualToConstant:120],
        [self.messageLimit.leadingAnchor constraintEqualToAnchor:self.messageTypePicker.trailingAnchor constant:8], [self.messageLimit.centerYAnchor constraintEqualToAnchor:self.messageDirectionPicker.centerYAnchor], [self.messageLimit.widthAnchor constraintEqualToConstant:100],
        [searchButton.leadingAnchor constraintEqualToAnchor:self.messageLimit.trailingAnchor constant:10], [searchButton.centerYAnchor constraintEqualToAnchor:self.messageDirectionPicker.centerYAnchor],
        [self.messageSearchStatus.leadingAnchor constraintEqualToAnchor:searchButton.trailingAnchor constant:14], [self.messageSearchStatus.centerYAnchor constraintEqualToAnchor:self.messageDirectionPicker.centerYAnchor], [self.messageSearchStatus.trailingAnchor constraintLessThanOrEqualToAnchor:filters.trailingAnchor constant:-14],
        [tableScroll.leadingAnchor constraintEqualToAnchor:title.leadingAnchor], [tableScroll.topAnchor constraintEqualToAnchor:filters.bottomAnchor constant:14], [tableScroll.bottomAnchor constraintEqualToAnchor:content.bottomAnchor constant:-24], [tableScroll.widthAnchor constraintEqualToAnchor:content.widthAnchor multiplier:0.66 constant:-34],
        [detailScroll.leadingAnchor constraintEqualToAnchor:tableScroll.trailingAnchor constant:12], [detailScroll.trailingAnchor constraintEqualToAnchor:content.trailingAnchor constant:-28], [detailScroll.topAnchor constraintEqualToAnchor:tableScroll.topAnchor], [detailScroll.bottomAnchor constraintEqualToAnchor:tableScroll.bottomAnchor]
    ]];
    PolishWorkspace(root);
    self.window.contentView = root;
    [self loadMessageSearchSessions];
}

- (void)runMessageSearch:(id)sender {
    (void)sender;
    NSInteger index = self.messageSessionPicker.indexOfSelectedItem;
    if (index < 0) {
        NSUInteger matched = [self.messageSessionPicker.objectValues indexOfObject:self.messageSessionPicker.stringValue];
        if (matched != NSNotFound) index = (NSInteger)matched;
    }
    if (index < 0 || index >= (NSInteger)self.messageSearchSessions.count) { NSBeep(); return; }
    NSInteger limit = self.messageLimit.integerValue;
    if (limit <= 0 || limit > 1000) { self.messageSearchStatus.stringValue = @"查询数量必须为 1-1000"; self.messageSearchStatus.textColor = NSColor.systemRedColor; return; }
    NSArray *directions = @[@"all", @"self", @"other"];
    NSArray *types = @[@"", @"1", @"3", @"34", @"43", @"49", @"49", @"49", @"10000"];
    NSArray *subTypes = @[@"", @"", @"", @"", @"", @"6", @"5", @"57", @""];
    NSDictionary *session = self.messageSearchSessions[index];
    NSInteger typeIndex = self.messageTypePicker.indexOfSelectedItem;
    NSArray<NSString *> *arguments = @[@"-m", @"agent_core.message_search_cli", @"search", @"--chat", session[@"username"] ?: @"", @"--since", [NSString stringWithFormat:@"%lld", (long long)self.messageStartDate.dateValue.timeIntervalSince1970], @"--until", [NSString stringWithFormat:@"%lld", (long long)self.messageEndDate.dateValue.timeIntervalSince1970], @"--keyword", self.messageKeyword.stringValue ?: @"", @"--msg-type", types[typeIndex], @"--sub-type", subTypes[typeIndex], @"--direction", directions[self.messageDirectionPicker.indexOfSelectedItem], @"--limit", [NSString stringWithFormat:@"%ld", (long)limit]];
    self.messageSearchStatus.stringValue = @"正在查询本机消息…";
    self.messageSearchStatus.textColor = NSColor.systemOrangeColor;
    int status = 0;
    NSError *error = nil;
    NSArray<NSString *> *lines = [self runAgentCommand:arguments terminationStatus:&status error:&error];
    NSDictionary *object = [self lastJSONObjectFromLines:lines];
    NSArray *messages = object[@"messages"];
    if (status != 0 || ![messages isKindOfClass:NSArray.class]) {
        self.messageSearchStatus.stringValue = [self messageFromEvent:object defaultMessage:(error.localizedDescription ?: @"消息查询失败")];
        self.messageSearchStatus.textColor = NSColor.systemRedColor;
        return;
    }
    self.messageSearchResults = messages;
    [self.messageTable reloadData];
    self.messageSearchStatus.stringValue = [NSString stringWithFormat:@"匹配 %@ 条 · 显示 %lu 条", object[@"matched_total"] ?: @0, (unsigned long)messages.count];
    self.messageSearchStatus.textColor = NSColor.systemGreenColor;
    if (messages.count) { [self.messageTable selectRowIndexes:[NSIndexSet indexSetWithIndex:0] byExtendingSelection:NO]; [self showMessageResult:messages[0]]; }
}

- (void)showMessageResult:(NSDictionary *)message {
    self.messageDetail.string = [NSString stringWithFormat:@"时间：%@\n方向：%@\n发送者：%@\n类型：%@\n\n%@", message[@"time"] ?: @"", message[@"direction"] ?: @"", message[@"sender"] ?: @"", message[@"type"] ?: @"", message[@"content"] ?: @""];
}

- (void)openMessageSearch:(id)sender {
    (void)sender;
    NSString *accountID = self.snapshot[@"account_id"] ?: @"";
    if (self.chatlogServiceTask.running && [self.chatlogServiceAccountID isEqualToString:accountID] && [self process:self.chatlogServiceTask.processIdentifier listensOnTCPPort:5030] && [self chatlogReadAPIIsReadyForAccount:accountID]) { [self showMessageSearchView]; return; }
    if (self.messageSearchOpening) { self.statusLabel.stringValue = @"正在启动消息检索…"; self.statusLabel.textColor = NSColor.systemOrangeColor; return; }
    NSString *chatlogBinary = [[NSBundle mainBundle].resourcePath stringByAppendingPathComponent:@"Chatlog/chatlog-darwin-arm64"];
    if (![[NSFileManager defaultManager] isExecutableFileAtPath:chatlogBinary]) { self.statusLabel.stringValue = @"本地微信数据组件缺失"; self.statusLabel.textColor = NSColor.systemRedColor; return; }
    NSError *launchError = nil;
    if (![self startChatlogServiceForAccount:accountID binary:chatlogBinary error:&launchError]) { self.statusLabel.stringValue = launchError.localizedDescription ?: @"消息检索服务启动失败"; self.statusLabel.textColor = NSColor.systemRedColor; return; }
    self.messageSearchOpening = YES;
    self.statusLabel.stringValue = @"正在启动消息检索…";
    self.statusLabel.textColor = NSColor.systemOrangeColor;
    NSTask *ownedService = self.chatlogServiceTask;
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        while (ownedService.running) {
            if ([self process:ownedService.processIdentifier listensOnTCPPort:5030] && [self chatlogReadAPIIsReadyForAccount:accountID]) {
                dispatch_async(dispatch_get_main_queue(), ^{ if (self.chatlogServiceTask != ownedService || !self.messageSearchOpening) return; self.messageSearchOpening = NO; [self showMessageSearchView]; });
                return;
            }
            [NSThread sleepForTimeInterval:0.25];
        }
        dispatch_async(dispatch_get_main_queue(), ^{ if (self.chatlogServiceTask != ownedService || !self.messageSearchOpening) return; self.messageSearchOpening = NO; self.statusLabel.stringValue = @"消息检索服务启动失败"; self.statusLabel.textColor = NSColor.systemRedColor; });
    });
}

- (NSDictionary *)loadSnapshotAtPath:(NSString *)path error:(NSError **)error {
    NSData *data = [NSData dataWithContentsOfFile:path options:0 error:error];
    if (!data) return nil;
    id value = [NSJSONSerialization JSONObjectWithData:data options:0 error:error];
    if (![value isKindOfClass:NSDictionary.class]) return nil;
    return value;
}

- (NSDictionary *)loadCurrentSnapshot:(NSError **)error {
    NSString *db = NSProcessInfo.processInfo.environment[@"WECHAT_SALES_AGENT_DB"];
    if (!db.length) {
        db = [NSHomeDirectory() stringByAppendingPathComponent:@"Library/Application Support/WeChatSalesAgent/agent_state.sqlite3"];
    }
    NSTask *task = [[NSTask alloc] init];
    task.executableURL = [NSURL fileURLWithPath:self.pythonExecutable];
    task.arguments = @[@"-m", @"agent_core.workspace_cli", @"--db", db, @"snapshot"];
    task.environment = self.agentEnvironment;
    NSPipe *pipe = [NSPipe pipe];
    task.standardOutput = pipe;
    task.standardError = pipe;
    if (![task launchAndReturnError:error]) return nil;
    NSData *data = [self drainPipe:pipe whileTaskRuns:task];
    if (task.terminationStatus != 0) {
        NSString *message = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] ?: @"无法读取分析快照";
        if (error) *error = [NSError errorWithDomain:@"WeChatSalesAgent" code:task.terminationStatus userInfo:@{NSLocalizedDescriptionKey: message}];
        return nil;
    }
    return [NSJSONSerialization JSONObjectWithData:data options:0 error:error];
}

- (NSDictionary *)loadReadiness:(NSError **)error {
    NSTask *task = [[NSTask alloc] init];
    task.executableURL = [NSURL fileURLWithPath:self.pythonExecutable];
    task.arguments = @[@"-m", @"agent_core.workspace_cli", @"--db", self.currentDBPath, @"readiness"];
    task.environment = self.agentEnvironment;
    NSPipe *pipe = [NSPipe pipe];
    task.standardOutput = pipe;
    task.standardError = pipe;
    if (![task launchAndReturnError:error]) return nil;
    NSData *data = [self drainPipe:pipe whileTaskRuns:task];
    if (task.terminationStatus != 0) return nil;
    id value = [NSJSONSerialization JSONObjectWithData:data options:0 error:error];
    return [value isKindOfClass:NSDictionary.class] ? value : nil;
}

- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    if (self.didInitializeWorkspace) return;
    self.didInitializeWorkspace = YES;
    NSError *error = nil;
    self.snapshot = self.snapshotPath.length ? [self loadSnapshotAtPath:self.snapshotPath error:&error] : [self loadCurrentSnapshot:&error];
    if (!self.snapshot) {
        self.startupError = error.localizedDescription ?: @"已同步聊天，等待 Agent 指令。";
        NSDictionary *readiness = self.snapshotPath.length ? nil : [self loadReadiness:nil];
        NSString *accountID = readiness[@"account_id"] ?: @"未连接";
        self.snapshot = @{ @"metrics": @{ @"customer_total": @0, @"high_intent": @0, @"activation_needed": @0, @"recent_leads": @0, @"distribution": @{} }, @"leads": @[], @"run": @{}, @"account_id": accountID };
    }
    self.allLeads = self.snapshot[@"leads"] ?: @[];
    self.visibleLeads = self.allLeads;
    [self buildWindow];
    [self.window makeKeyAndOrderFront:nil];
    [NSApp activateIgnoringOtherApps:YES];
}

- (NSString *)storedAgentModel {
    int status = 0;
    NSError *error = nil;
    NSArray<NSString *> *lines = [self runAgentCommand:@[@"-m", @"agent_core.customer_agent_cli", @"--db", self.currentDBPath, @"--get-model"] terminationStatus:&status error:&error];
    NSString *model = status == 0 ? [self lastJSONObjectFromLines:lines][@"model"] : nil;
    return [model isKindOfClass:NSString.class] && model.length ? model : @"deepseek-v4-flash";
}

- (void)setAgentModelOptions:(NSArray<NSString *> *)models selected:(NSString *)selected {
    [self.agentModelPicker removeAllItems];
    for (NSString *model in models) [self.agentModelPicker addItemWithTitle:model];
    if ([models containsObject:selected]) [self.agentModelPicker selectItemWithTitle:selected];
    else [self.agentModelPicker selectItemWithTitle:@"deepseek-v4-flash"];
}

- (void)selectAgentModel:(id)sender {
    (void)sender;
    NSString *model = self.agentModelPicker.titleOfSelectedItem;
    int status = 0;
    NSError *error = nil;
    NSArray<NSString *> *lines = [self runAgentCommand:@[@"-m", @"agent_core.customer_agent_cli", @"--db", self.currentDBPath, @"--set-model", model] terminationStatus:&status error:&error];
    NSDictionary *object = [self lastJSONObjectFromLines:lines];
    self.statusLabel.stringValue = status == 0 ? [NSString stringWithFormat:@"已选择 %@", model] : [self messageFromEvent:object defaultMessage:(error.localizedDescription ?: @"模型切换失败")];
    self.statusLabel.textColor = status == 0 ? NSColor.systemGreenColor : NSColor.systemRedColor;
}

- (BOOL)refreshAgentModels {
    int status = 0;
    NSError *error = nil;
    NSArray<NSString *> *lines = [self runAgentCommand:@[@"-m", @"agent_core.customer_agent_cli", @"--db", self.currentDBPath, @"--list-models"] terminationStatus:&status error:&error];
    NSDictionary *object = [self lastJSONObjectFromLines:lines];
    NSArray *models = object[@"models"];
    if (status != 0 || ![models isKindOfClass:NSArray.class] || !models.count) return NO;
    NSMutableArray<NSString *> *valid = [NSMutableArray array];
    for (id model in models) if ([model isKindOfClass:NSString.class] && [model length]) [valid addObject:model];
    if (!valid.count) return NO;
    [self setAgentModelOptions:valid selected:[self storedAgentModel]];
    return YES;
}

- (void)buildWindow {
    self.showingMessageSearch = NO;
    self.showingAnalyticsDashboard = NO;
    self.window = [[NSWindow alloc] initWithContentRect:NSMakeRect(0, 0, 1360, 820)
        styleMask:(NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable)
        backing:NSBackingStoreBuffered defer:NO];
    self.window.title = @"微信客户分析 Agent";
    self.window.minSize = NSMakeSize(1180, 720);
    [self.window center];
    NSView *root = self.window.contentView;
    root.wantsLayer = YES;
    root.layer.backgroundColor = NSColor.whiteColor.CGColor;

    NSView *sidebar = [[NSView alloc] initWithFrame:NSZeroRect];
    sidebar.wantsLayer = YES;
    sidebar.layer.backgroundColor = [NSColor colorWithWhite:0.965 alpha:1].CGColor;
    [root addSubview:sidebar];
    sidebar.translatesAutoresizingMaskIntoConstraints = NO;
    [NSLayoutConstraint activateConstraints:@[
        [sidebar.leadingAnchor constraintEqualToAnchor:root.leadingAnchor], [sidebar.topAnchor constraintEqualToAnchor:root.topAnchor],
        [sidebar.bottomAnchor constraintEqualToAnchor:root.bottomAnchor], [sidebar.widthAnchor constraintEqualToConstant:210]
    ]];
    NSTextField *brand = Label(@"微信客户分析 Agent", 19, [NSColor colorWithWhite:0.12 alpha:1], YES);
    NSTextField *tagline = Label(@"DeepSeek", 11, [NSColor colorWithWhite:0.45 alpha:1], NO);
    [sidebar addSubview:brand]; [sidebar addSubview:tagline];
    brand.translatesAutoresizingMaskIntoConstraints = tagline.translatesAutoresizingMaskIntoConstraints = NO;
    [NSLayoutConstraint activateConstraints:@[
        [brand.leadingAnchor constraintEqualToAnchor:sidebar.leadingAnchor constant:22], [brand.topAnchor constraintEqualToAnchor:sidebar.topAnchor constant:28],
        [tagline.leadingAnchor constraintEqualToAnchor:brand.leadingAnchor], [tagline.topAnchor constraintEqualToAnchor:brand.bottomAnchor constant:5]
    ]];
    NSButton *dashboardButton = [NSButton buttonWithTitle:@"▦  仪表盘" target:self action:@selector(openAnalyticsDashboard:)];
    dashboardButton.bordered = NO; dashboardButton.alignment = NSTextAlignmentLeft; dashboardButton.font = [NSFont systemFontOfSize:14];
    dashboardButton.contentTintColor = [NSColor colorWithWhite:0.30 alpha:1];
    [sidebar addSubview:dashboardButton]; dashboardButton.translatesAutoresizingMaskIntoConstraints = NO;
    [NSLayoutConstraint activateConstraints:@[
        [dashboardButton.leadingAnchor constraintEqualToAnchor:sidebar.leadingAnchor constant:18], [dashboardButton.trailingAnchor constraintEqualToAnchor:sidebar.trailingAnchor constant:-18],
        [dashboardButton.topAnchor constraintEqualToAnchor:tagline.bottomAnchor constant:34], [dashboardButton.heightAnchor constraintEqualToConstant:38]
    ]];
    NSButton *messageSearchButton = [NSButton buttonWithTitle:@"≡  消息检索" target:self action:@selector(openMessageSearch:)];
    messageSearchButton.bordered = NO; messageSearchButton.alignment = NSTextAlignmentLeft; messageSearchButton.font = [NSFont systemFontOfSize:14]; messageSearchButton.contentTintColor = [NSColor colorWithWhite:0.30 alpha:1];
    [sidebar addSubview:messageSearchButton]; messageSearchButton.translatesAutoresizingMaskIntoConstraints = NO;
    [NSLayoutConstraint activateConstraints:@[
        [messageSearchButton.leadingAnchor constraintEqualToAnchor:sidebar.leadingAnchor constant:18], [messageSearchButton.trailingAnchor constraintEqualToAnchor:sidebar.trailingAnchor constant:-18],
        [messageSearchButton.topAnchor constraintEqualToAnchor:dashboardButton.bottomAnchor constant:4], [messageSearchButton.heightAnchor constraintEqualToConstant:38]
    ]];
    NSButton *customerButton = [NSButton buttonWithTitle:@"☷  智能分析" target:nil action:nil];
    customerButton.bordered = NO; customerButton.alignment = NSTextAlignmentLeft; customerButton.font = [NSFont boldSystemFontOfSize:14]; customerButton.contentTintColor = [NSColor colorWithWhite:0.12 alpha:1]; customerButton.wantsLayer = YES; customerButton.layer.backgroundColor = [NSColor colorWithWhite:0.89 alpha:1].CGColor; customerButton.layer.cornerRadius = 8;
    [sidebar addSubview:customerButton]; customerButton.translatesAutoresizingMaskIntoConstraints = NO;
    [NSLayoutConstraint activateConstraints:@[[customerButton.leadingAnchor constraintEqualToAnchor:sidebar.leadingAnchor constant:14], [customerButton.trailingAnchor constraintEqualToAnchor:sidebar.trailingAnchor constant:-14], [customerButton.topAnchor constraintEqualToAnchor:messageSearchButton.bottomAnchor constant:4], [customerButton.heightAnchor constraintEqualToConstant:42]]];
    NSButton *connectButton = [NSButton buttonWithTitle:@"连接并同步微信" target:self action:@selector(connectWeChatData:)];
    connectButton.bordered = NO;
    connectButton.contentTintColor = [NSColor colorWithRed:0.10 green:0.28 blue:0.66 alpha:1];
    connectButton.font = [NSFont boldSystemFontOfSize:13];
    connectButton.wantsLayer = YES;
    connectButton.layer.backgroundColor = [NSColor colorWithRed:0.90 green:0.94 blue:1 alpha:1].CGColor;
    connectButton.layer.cornerRadius = 7;
    NSButton *sipButton = [NSButton buttonWithTitle:@"关闭 SIP 指引" target:self action:@selector(showSIPSetup:)];
    sipButton.bordered = NO;
    sipButton.contentTintColor = [NSColor colorWithWhite:0.26 alpha:1];
    sipButton.font = [NSFont boldSystemFontOfSize:13];
    sipButton.wantsLayer = YES;
    sipButton.layer.backgroundColor = [NSColor colorWithWhite:0.91 alpha:1].CGColor;
    sipButton.layer.cornerRadius = 7;
    self.sipStatusLabel = Label(@"", 11, NSColor.systemOrangeColor, YES);
    [sidebar addSubview:connectButton]; [sidebar addSubview:sipButton]; [sidebar addSubview:self.sipStatusLabel];
    connectButton.translatesAutoresizingMaskIntoConstraints = NO;
    sipButton.translatesAutoresizingMaskIntoConstraints = NO; self.sipStatusLabel.translatesAutoresizingMaskIntoConstraints = NO;
    [NSLayoutConstraint activateConstraints:@[
        [connectButton.leadingAnchor constraintEqualToAnchor:sidebar.leadingAnchor constant:18], [connectButton.trailingAnchor constraintEqualToAnchor:sidebar.trailingAnchor constant:-18],
        [connectButton.heightAnchor constraintEqualToConstant:30],
        [sipButton.leadingAnchor constraintEqualToAnchor:connectButton.leadingAnchor], [sipButton.trailingAnchor constraintEqualToAnchor:connectButton.trailingAnchor],
        [sipButton.bottomAnchor constraintEqualToAnchor:self.sipStatusLabel.topAnchor constant:-9], [sipButton.heightAnchor constraintEqualToConstant:30],
        [connectButton.bottomAnchor constraintEqualToAnchor:sipButton.topAnchor constant:-8],
        [self.sipStatusLabel.leadingAnchor constraintEqualToAnchor:connectButton.leadingAnchor constant:4],
        [self.sipStatusLabel.bottomAnchor constraintEqualToAnchor:sidebar.bottomAnchor constant:-22]
    ]];
    [self updateSIPStatusLabel:[self isSIPDisabled]];
    NSView *content = [[NSView alloc] initWithFrame:NSZeroRect];
    [root addSubview:content]; content.translatesAutoresizingMaskIntoConstraints = NO;
    [NSLayoutConstraint activateConstraints:@[
        [content.leadingAnchor constraintEqualToAnchor:sidebar.trailingAnchor], [content.trailingAnchor constraintEqualToAnchor:root.trailingAnchor],
        [content.topAnchor constraintEqualToAnchor:root.topAnchor], [content.bottomAnchor constraintEqualToAnchor:root.bottomAnchor]
    ]];

    NSString *initialStatus = [self startupDetailText];
    BOOL accountReady = ![initialStatus isEqualToString:@"请先连接微信。"];
    self.statusLabel = Label(initialStatus, 12, accountReady ? NSColor.systemGreenColor : NSColor.systemOrangeColor, YES);
    self.agentActivityIndicator = [[NSProgressIndicator alloc] initWithFrame:NSZeroRect];
    self.agentActivityIndicator.style = NSProgressIndicatorStyleSpinning;
    self.agentActivityIndicator.controlSize = NSControlSizeSmall;
    self.agentActivityIndicator.indeterminate = YES;
    self.agentActivityIndicator.displayedWhenStopped = NO;
    self.agentActivityIndicator.hidden = YES;
    self.agentModelPicker = [[NSPopUpButton alloc] initWithFrame:NSZeroRect pullsDown:NO];
    self.agentModelPicker.target = self;
    self.agentModelPicker.action = @selector(selectAgentModel:);
    self.agentModelPicker.font = [NSFont monospacedSystemFontOfSize:12 weight:NSFontWeightMedium];
    [self setAgentModelOptions:@[@"deepseek-v4-flash", @"deepseek-v4-pro", @"deepseek-v4-flash-vision-exp"] selected:[self storedAgentModel]];
    NSButton *newButton = [NSButton buttonWithTitle:@"新分析" target:self action:@selector(newAgentAnalysis:)];
    NSButton *saveButton = [NSButton buttonWithTitle:@"保存" target:self action:@selector(saveCurrentAnalysis:)];
    self.savedAnalysisPicker = [[NSPopUpButton alloc] initWithFrame:NSZeroRect pullsDown:NO];
    [self.savedAnalysisPicker addItemWithTitle:@"已保存分析"];
    self.savedAnalysisPicker.target = self;
    self.savedAnalysisPicker.action = @selector(loadSelectedAnalysis:);
    NSButton *refreshButton = [NSButton buttonWithTitle:@"检查更新" target:self action:@selector(refreshSelectedAnalysis:)];
    NSButton *deleteButton = [NSButton buttonWithTitle:@"删除" target:self action:@selector(deleteSelectedAnalysis:)];
    NSButton *exportButton = [NSButton buttonWithTitle:@"导出报告" target:self action:@selector(exportWorkbook:)];
    exportButton.bezelStyle = NSBezelStyleTexturedRounded;
    exportButton.contentTintColor = NSColor.systemBlueColor;
    [content addSubview:newButton]; [content addSubview:saveButton]; [content addSubview:self.savedAnalysisPicker]; [content addSubview:refreshButton]; [content addSubview:deleteButton];
    [content addSubview:self.agentActivityIndicator]; [content addSubview:self.statusLabel]; [content addSubview:exportButton];
    for (NSView *view in @[newButton, saveButton, self.savedAnalysisPicker, refreshButton, deleteButton, self.agentActivityIndicator, self.statusLabel, exportButton]) view.translatesAutoresizingMaskIntoConstraints = NO;
    [NSLayoutConstraint activateConstraints:@[
        [newButton.leadingAnchor constraintEqualToAnchor:content.leadingAnchor constant:28], [newButton.centerYAnchor constraintEqualToAnchor:exportButton.centerYAnchor],
        [saveButton.leadingAnchor constraintEqualToAnchor:newButton.trailingAnchor constant:8], [saveButton.centerYAnchor constraintEqualToAnchor:newButton.centerYAnchor],
        [self.savedAnalysisPicker.leadingAnchor constraintEqualToAnchor:saveButton.trailingAnchor constant:8], [self.savedAnalysisPicker.centerYAnchor constraintEqualToAnchor:newButton.centerYAnchor], [self.savedAnalysisPicker.widthAnchor constraintEqualToConstant:150],
        [refreshButton.leadingAnchor constraintEqualToAnchor:self.savedAnalysisPicker.trailingAnchor constant:8], [refreshButton.centerYAnchor constraintEqualToAnchor:newButton.centerYAnchor],
        [deleteButton.leadingAnchor constraintEqualToAnchor:refreshButton.trailingAnchor constant:6], [deleteButton.centerYAnchor constraintEqualToAnchor:newButton.centerYAnchor],
        [exportButton.trailingAnchor constraintEqualToAnchor:content.trailingAnchor constant:-28], [exportButton.topAnchor constraintEqualToAnchor:content.topAnchor constant:22],
        [self.statusLabel.trailingAnchor constraintEqualToAnchor:exportButton.leadingAnchor constant:-18], [self.statusLabel.centerYAnchor constraintEqualToAnchor:exportButton.centerYAnchor],
        [self.statusLabel.leadingAnchor constraintGreaterThanOrEqualToAnchor:deleteButton.trailingAnchor constant:12],
        [self.statusLabel.widthAnchor constraintLessThanOrEqualToConstant:360],
        [self.agentActivityIndicator.trailingAnchor constraintEqualToAnchor:self.statusLabel.leadingAnchor constant:-8], [self.agentActivityIndicator.centerYAnchor constraintEqualToAnchor:self.statusLabel.centerYAnchor],
        [self.agentActivityIndicator.widthAnchor constraintEqualToConstant:14], [self.agentActivityIndicator.heightAnchor constraintEqualToConstant:14]
    ]];

    PolishWorkspace(root);

    NSView *taskSurface = [[NSView alloc] initWithFrame:NSZeroRect];
    taskSurface.wantsLayer = YES;
    taskSurface.layer.backgroundColor = NSColor.whiteColor.CGColor;
    [content addSubview:taskSurface]; taskSurface.translatesAutoresizingMaskIntoConstraints = NO;
    [NSLayoutConstraint activateConstraints:@[
        [taskSurface.leadingAnchor constraintEqualToAnchor:content.leadingAnchor], [taskSurface.trailingAnchor constraintEqualToAnchor:content.trailingAnchor],
        [taskSurface.topAnchor constraintEqualToAnchor:content.topAnchor constant:58], [taskSurface.bottomAnchor constraintEqualToAnchor:content.bottomAnchor]
    ]];

    self.agentTranscript = [[NSTextView alloc] initWithFrame:NSMakeRect(0, 0, 760, 440)];
    self.agentTranscript.editable = NO; self.agentTranscript.selectable = YES; self.agentTranscript.verticallyResizable = YES; self.agentTranscript.delegate = self;
    self.agentTranscript.linkTextAttributes = @{NSForegroundColorAttributeName: NSColor.systemBlueColor, NSUnderlineStyleAttributeName: @(NSUnderlineStyleNone)};
    self.agentTranscript.textContainer.widthTracksTextView = YES; self.agentTranscript.font = [NSFont systemFontOfSize:14];
    self.agentTranscript.drawsBackground = NO; self.agentTranscript.textColor = [NSColor colorWithWhite:0.14 alpha:1];
    self.agentTranscript.textContainerInset = NSMakeSize(24, 22);
    self.agentTranscript.string = @"";
    NSScrollView *agentTranscriptScroll = [[NSScrollView alloc] initWithFrame:NSZeroRect];
    agentTranscriptScroll.documentView = self.agentTranscript; agentTranscriptScroll.hasVerticalScroller = NO; agentTranscriptScroll.hasHorizontalScroller = NO;
    agentTranscriptScroll.autohidesScrollers = YES; agentTranscriptScroll.scrollerStyle = NSScrollerStyleOverlay;
    agentTranscriptScroll.drawsBackground = NO; agentTranscriptScroll.borderType = NSNoBorder;

    NSView *composer = [[NSView alloc] initWithFrame:NSZeroRect];
    composer.wantsLayer = YES; composer.layer.backgroundColor = [NSColor colorWithWhite:0.985 alpha:1].CGColor;
    composer.layer.cornerRadius = 18; composer.layer.borderWidth = 1;
    composer.layer.borderColor = [NSColor colorWithWhite:0.84 alpha:1].CGColor;
    self.agentInput = [[AgentComposerTextView alloc] initWithFrame:NSMakeRect(0, 0, 760, 70)];
    self.agentInput.font = [NSFont systemFontOfSize:15];
    self.agentInput.delegate = self; self.agentInput.drawsBackground = YES; self.agentInput.backgroundColor = [NSColor colorWithWhite:0.985 alpha:1]; self.agentInput.textColor = [NSColor colorWithWhite:0.12 alpha:1];
    self.agentInput.textContainerInset = NSMakeSize(14, 14);
    NSScrollView *agentInputScroll = [[NSScrollView alloc] initWithFrame:NSZeroRect];
    agentInputScroll.documentView = self.agentInput; agentInputScroll.drawsBackground = YES; agentInputScroll.backgroundColor = [NSColor colorWithWhite:0.985 alpha:1];
    agentInputScroll.hasVerticalScroller = NO; agentInputScroll.hasHorizontalScroller = NO; agentInputScroll.autohidesScrollers = YES;
    agentInputScroll.scrollerStyle = NSScrollerStyleOverlay; agentInputScroll.borderType = NSNoBorder;
    self.agentPlaceholderLabel = [[AgentPlaceholderLabel alloc] initWithFrame:NSZeroRect];
    self.agentPlaceholderLabel.stringValue = @"描述要查找的人或对话";
    self.agentPlaceholderLabel.font = [NSFont systemFontOfSize:15]; self.agentPlaceholderLabel.textColor = [NSColor colorWithWhite:0.52 alpha:1];
    self.agentPlaceholderLabel.editable = NO; self.agentPlaceholderLabel.selectable = NO; self.agentPlaceholderLabel.bezeled = NO; self.agentPlaceholderLabel.drawsBackground = NO;
    NSButton *connectionButton = [NSButton buttonWithTitle:@"连接" target:self action:@selector(saveDeepSeekKey:)];
    connectionButton.bordered = NO; connectionButton.font = [NSFont systemFontOfSize:12]; connectionButton.contentTintColor = [NSColor colorWithWhite:0.38 alpha:1];
    self.analysisModePicker = [[NSPopUpButton alloc] initWithFrame:NSZeroRect pullsDown:NO];
    NSArray<NSArray<NSString *> *> *analysisModes = @[
        @[@"自动分析", @""], @[@"客户筛选", @"customer_search"], @[@"成交机会", @"opportunity_analysis"],
        @[@"重新激活", @"reengagement_analysis"], @[@"客户风险", @"customer_risk"], @[@"承诺待办", @"commitment_tracker"],
        @[@"人物画像", @"person_profile"], @[@"关系洞察", @"relationship_insight"], @[@"多人比较", @"comparison"],
        @[@"话题分析", @"topic_analysis"], @[@"事件时间线", @"timeline"]
    ];
    for (NSArray<NSString *> *mode in analysisModes) {
        [self.analysisModePicker addItemWithTitle:mode[0]];
        self.analysisModePicker.lastItem.representedObject = mode[1];
    }
    self.analysisModePicker.font = [NSFont systemFontOfSize:12];
    self.agentSendButton = [NSButton buttonWithTitle:@"↑" target:self action:@selector(askCustomerAgent:)];
    self.agentSendButton.bordered = NO; self.agentSendButton.font = [NSFont boldSystemFontOfSize:18]; self.agentSendButton.contentTintColor = NSColor.whiteColor;
    self.agentSendButton.wantsLayer = YES; self.agentSendButton.layer.backgroundColor = [NSColor colorWithRed:0.15 green:0.43 blue:0.92 alpha:1].CGColor; self.agentSendButton.layer.cornerRadius = 18;
    [taskSurface addSubview:agentTranscriptScroll]; [taskSurface addSubview:composer];
    [composer addSubview:agentInputScroll]; [composer addSubview:self.agentPlaceholderLabel]; [composer addSubview:self.analysisModePicker]; [composer addSubview:self.agentModelPicker]; [composer addSubview:connectionButton]; [composer addSubview:self.agentSendButton];
    for (NSView *view in @[agentTranscriptScroll, composer, agentInputScroll, self.agentPlaceholderLabel, self.analysisModePicker, self.agentModelPicker, connectionButton, self.agentSendButton]) view.translatesAutoresizingMaskIntoConstraints = NO;
    [NSLayoutConstraint activateConstraints:@[
        [agentTranscriptScroll.leadingAnchor constraintEqualToAnchor:taskSurface.leadingAnchor constant:34], [agentTranscriptScroll.trailingAnchor constraintEqualToAnchor:taskSurface.trailingAnchor constant:-34],
        [agentTranscriptScroll.topAnchor constraintEqualToAnchor:taskSurface.topAnchor constant:8], [agentTranscriptScroll.bottomAnchor constraintEqualToAnchor:composer.topAnchor constant:-14],
        [composer.leadingAnchor constraintEqualToAnchor:taskSurface.leadingAnchor constant:34], [composer.trailingAnchor constraintEqualToAnchor:taskSurface.trailingAnchor constant:-34],
        [composer.bottomAnchor constraintEqualToAnchor:taskSurface.bottomAnchor constant:-20], [composer.heightAnchor constraintEqualToConstant:118],
        [agentInputScroll.leadingAnchor constraintEqualToAnchor:composer.leadingAnchor constant:12], [agentInputScroll.trailingAnchor constraintEqualToAnchor:self.agentSendButton.leadingAnchor constant:-10],
        [agentInputScroll.topAnchor constraintEqualToAnchor:composer.topAnchor constant:8], [agentInputScroll.heightAnchor constraintEqualToConstant:70],
        [self.agentPlaceholderLabel.leadingAnchor constraintEqualToAnchor:agentInputScroll.leadingAnchor constant:14], [self.agentPlaceholderLabel.topAnchor constraintEqualToAnchor:agentInputScroll.topAnchor constant:15], [self.agentPlaceholderLabel.trailingAnchor constraintLessThanOrEqualToAnchor:agentInputScroll.trailingAnchor constant:-14],
        [self.agentSendButton.trailingAnchor constraintEqualToAnchor:composer.trailingAnchor constant:-14], [self.agentSendButton.centerYAnchor constraintEqualToAnchor:composer.centerYAnchor], [self.agentSendButton.widthAnchor constraintEqualToConstant:36], [self.agentSendButton.heightAnchor constraintEqualToConstant:36],
        [self.analysisModePicker.leadingAnchor constraintEqualToAnchor:agentInputScroll.leadingAnchor constant:13], [self.analysisModePicker.centerYAnchor constraintEqualToAnchor:connectionButton.centerYAnchor], [self.analysisModePicker.widthAnchor constraintEqualToConstant:120],
        [self.agentModelPicker.leadingAnchor constraintEqualToAnchor:self.analysisModePicker.trailingAnchor constant:8], [self.agentModelPicker.centerYAnchor constraintEqualToAnchor:connectionButton.centerYAnchor], [self.agentModelPicker.widthAnchor constraintEqualToConstant:190],
        [connectionButton.leadingAnchor constraintEqualToAnchor:self.agentModelPicker.trailingAnchor constant:12], [connectionButton.topAnchor constraintEqualToAnchor:agentInputScroll.bottomAnchor constant:10]
    ]];
    [self setAgentTranscriptContent:[[NSAttributedString alloc] initWithString:@""]];
    [self reloadSavedAnalyses];
}

- (NSInteger)numberOfRowsInTableView:(NSTableView *)tableView {
    if (tableView == self.messageTable) return self.messageSearchResults.count;
    if (tableView == self.dashboardGroupTable) return self.dashboardGroups.count;
    if (tableView == self.dashboardSpeakerTable) return self.dashboardSpeakers.count;
    if (tableView == self.dashboardDatabaseTable) return self.dashboardDatabases.count;
    return 0;
}

- (NSView *)tableView:(NSTableView *)tableView viewForTableColumn:(NSTableColumn *)column row:(NSInteger)row {
    if (tableView == self.messageTable) {
        NSDictionary *message = self.messageSearchResults[row];
        NSString *value = [message[column.identifier] description] ?: @"";
        NSTextField *field = Label(value, 12, [NSColor colorWithWhite:0.18 alpha:1], NO);
        if ([column.identifier isEqualToString:@"direction"]) field.textColor = [value isEqualToString:@"我方"] ? NSColor.systemBlueColor : NSColor.systemGreenColor;
        return field;
    }
    if (tableView == self.dashboardGroupTable || tableView == self.dashboardSpeakerTable || tableView == self.dashboardDatabaseTable) {
        NSArray<NSDictionary *> *rows = tableView == self.dashboardGroupTable ? self.dashboardGroups : (tableView == self.dashboardSpeakerTable ? self.dashboardSpeakers : self.dashboardDatabases);
        NSDictionary *item = rows[row];
        NSString *value = [item[column.identifier] description] ?: @"";
        if ([column.identifier isEqualToString:@"peak_hour"]) value = [NSString stringWithFormat:@"%@ 时", value];
        NSTextField *field = Label(value, 11, [NSColor colorWithWhite:0.18 alpha:1], [column.identifier isEqualToString:@"count"] || [column.identifier isEqualToString:@"total"]);
        return field;
    }
    return nil;
}

- (void)tableViewSelectionDidChange:(NSNotification *)notification {
    if (notification.object == self.dashboardGroupTable || notification.object == self.dashboardSpeakerTable || notification.object == self.dashboardDatabaseTable) return;
    if (notification.object == self.messageTable) {
        NSInteger messageRow = self.messageTable.selectedRow;
        if (messageRow >= 0 && messageRow < (NSInteger)self.messageSearchResults.count) [self showMessageResult:self.messageSearchResults[messageRow]];
        return;
    }

}

- (void)textDidChange:(NSNotification *)notification {
    if (notification.object == self.agentInput) self.agentPlaceholderLabel.hidden = self.agentInput.string.length > 0;
}

- (NSDictionary *)evidenceForID:(NSString *)evidenceID {
    for (NSDictionary *lead in self.visibleLeads ?: @[]) {
        for (NSDictionary *evidence in [lead[@"evidence"] isKindOfClass:NSArray.class] ? lead[@"evidence"] : @[]) {
            if ([evidence[@"evidence_id"] isEqualToString:evidenceID]) return evidence;
        }
    }
    return nil;
}

- (BOOL)textView:(NSTextView *)textView clickedOnLink:(id)link atIndex:(NSUInteger)charIndex {
    (void)charIndex;
    if (textView != self.agentTranscript || ![link isKindOfClass:NSURL.class]) return NO;
    NSURL *URL = link;
    if (![URL.scheme isEqualToString:@"evidence"]) return NO;
    NSString *evidenceID = URL.host ?: @"";
    NSDictionary *evidence = [self evidenceForID:evidenceID];
    if (!evidence) { NSBeep(); return YES; }
    NSMutableString *detail = [NSMutableString stringWithFormat:@"%@ · %@ · %@\n\n%@\n", evidence[@"time"] ?: @"", evidence[@"direction"] ?: @"", evidence[@"sender"] ?: @"", evidence[@"content"] ?: @""];
    NSArray *context = [evidence[@"context"] isKindOfClass:NSArray.class] ? evidence[@"context"] : @[];
    if (context.count) {
        [detail appendString:@"\n前后消息\n"];
        for (NSDictionary *item in context) {
            NSString *marker = [item[@"is_target"] boolValue] ? @"▶" : @" ";
            [detail appendFormat:@"%@ %@  [%@] %@\n%@\n\n", marker, item[@"time"] ?: @"", item[@"direction"] ?: @"", item[@"sender"] ?: @"", item[@"content"] ?: @""];
        }
    }
    NSAlert *alert = [[NSAlert alloc] init];
    alert.messageText = [NSString stringWithFormat:@"原始证据 · %@", evidenceID];
    alert.informativeText = @"内容来自本机已同步的微信记录，箭头标记当前引用。";
    NSScrollView *scroll = [[NSScrollView alloc] initWithFrame:NSMakeRect(0, 0, 620, 330)];
    scroll.hasVerticalScroller = YES; scroll.autohidesScrollers = YES; scroll.borderType = NSBezelBorder;
    NSTextView *view = [[NSTextView alloc] initWithFrame:NSMakeRect(0, 0, 620, 330)];
    view.editable = NO; view.selectable = YES; view.font = [NSFont systemFontOfSize:13]; view.string = detail;
    view.textContainerInset = NSMakeSize(14, 12); scroll.documentView = view; alert.accessoryView = scroll;
    [alert addButtonWithTitle:@"关闭"];
    [alert runModal];
    return YES;
}

- (BOOL)textView:(NSTextView *)textView doCommandBySelector:(SEL)commandSelector {
    if (textView != self.agentInput || self.agentInput.hasMarkedText) return NO;
    BOOL isReturn = commandSelector == @selector(insertNewline:) || commandSelector == @selector(insertNewlineIgnoringFieldEditor:);
    NSEventModifierFlags flags = NSApp.currentEvent.modifierFlags & NSEventModifierFlagDeviceIndependentFlagsMask;
    if (!isReturn || (flags & NSEventModifierFlagShift)) return NO;
    [self askCustomerAgent:textView];
    return YES;
}

- (NSString *)agentLeadSummary {
    NSMutableArray<NSString *> *lines = [NSMutableArray array];
    NSArray *sections = [self.lastAgentResult[@"sections"] isKindOfClass:NSArray.class] ? self.lastAgentResult[@"sections"] : @[];
    for (NSDictionary *section in sections) {
        NSString *title = [section[@"title"] isKindOfClass:NSString.class] ? section[@"title"] : @"分析";
        NSString *content = [section[@"content"] isKindOfClass:NSString.class] ? section[@"content"] : @"";
        if (content.length) [lines addObject:[NSString stringWithFormat:@"%@\n%@", title, content]];
    }
    NSArray *followups = [self.lastAgentResult[@"suggested_followups"] isKindOfClass:NSArray.class] ? self.lastAgentResult[@"suggested_followups"] : @[];
    if (followups.count) {
        NSMutableArray<NSString *> *items = [NSMutableArray arrayWithObject:@"可以继续问"];
        for (NSUInteger index = 0; index < MIN(followups.count, 4); index += 1) {
            [items addObject:[NSString stringWithFormat:@"%lu. %@", (unsigned long)index + 1, followups[index]]];
        }
        [lines addObject:[items componentsJoinedByString:@"\n"]];
    }
    if (lines.count) return [lines componentsJoinedByString:@"\n\n"];
    if (!self.visibleLeads.count) return @"没有匹配结果。";
    NSUInteger limit = MIN(self.visibleLeads.count, 12);
    for (NSUInteger index = 0; index < limit; index += 1) {
        NSDictionary *lead = self.visibleLeads[index];
        NSString *name = lead[@"display_name"] ?: @"未命名联系人";
        NSString *summary = lead[@"summary"] ?: lead[@"need"] ?: @"";
        [lines addObject:[NSString stringWithFormat:@"%lu. %@ · %@", (unsigned long)index + 1, name, summary]];
    }
    if (self.visibleLeads.count > limit) [lines addObject:[NSString stringWithFormat:@"其余 %lu 位见 Excel。", (unsigned long)(self.visibleLeads.count - limit)]];
    return [lines componentsJoinedByString:@"\n"];
}

- (NSString *)startupDetailText {
    NSString *accountID = self.snapshot[@"account_id"] ?: @"未连接";
    NSNumber *eligible = [self loadReadiness:nil][@"eligible_conversations"] ?: @0;
    if ([accountID isEqualToString:@"未连接"]) return @"请先连接微信。";
    return [NSString stringWithFormat:@"账号 %@ · 已同步 %@ 个对话，可以开始提问。", accountID, eligible];
}

- (void)setAgentTranscriptContent:(NSAttributedString *)content {
    [self.agentTranscript.textStorage setAttributedString:content ?: [[NSAttributedString alloc] initWithString:@""]];
}

- (NSMutableAttributedString *)agentTranscriptWithHistory {
    NSMutableAttributedString *content = [[NSMutableAttributedString alloc] init];
    if (self.priorAgentTranscript.length) {
        [content appendAttributedString:self.priorAgentTranscript];
        AppendAgentText(content, @"\n\n────────────────────────\n\n", [NSFont systemFontOfSize:11], [NSColor colorWithWhite:0.84 alpha:1], 0);
    }
    return content;
}

- (NSArray<NSDictionary<NSString *, NSString *> *> *)agentStages {
    return @[
        @{@"key": @"planning", @"title": @"理解任务"},
        @{@"key": @"retrieval", @"title": @"证据召回"},
        @{@"key": @"analysis", @"title": @"语义复核"},
        @{@"key": @"audit", @"title": @"覆盖审计"},
    ];
}

- (NSAttributedString *)agentProgressTranscriptForQuestion:(NSString *)question progress:(NSDictionary<NSString *, NSString *> *)progress activeStage:(NSString *)activeStage {
    NSMutableAttributedString *content = [self agentTranscriptWithHistory];
    AppendAgentText(content, @"你\n", [NSFont systemFontOfSize:12 weight:NSFontWeightSemibold], NSColor.secondaryLabelColor, 3);
    AppendAgentText(content, [NSString stringWithFormat:@"%@\n", question], [NSFont systemFontOfSize:15], [NSColor colorWithWhite:0.10 alpha:1], 20);
    AppendAgentText(content, @"✦  Agent\n", [NSFont systemFontOfSize:12 weight:NSFontWeightSemibold], [NSColor colorWithRed:0.15 green:0.38 blue:0.82 alpha:1], 3);
    AppendAgentText(content, @"正在处理这项任务\n", [NSFont systemFontOfSize:15 weight:NSFontWeightSemibold], [NSColor colorWithWhite:0.12 alpha:1], 14);

    NSArray<NSDictionary<NSString *, NSString *> *> *stages = [self agentStages];
    NSUInteger activeIndex = [stages indexOfObjectPassingTest:^BOOL(NSDictionary<NSString *,NSString *> *stage, NSUInteger index, BOOL *stop) {
        (void)index; (void)stop;
        return [stage[@"key"] isEqualToString:activeStage];
    }];
    for (NSUInteger index = 0; index < stages.count; index += 1) {
        NSDictionary<NSString *, NSString *> *stage = stages[index];
        BOOL completed = activeIndex != NSNotFound && index < activeIndex;
        BOOL active = index == activeIndex;
        NSString *marker = completed ? @"✓" : (active ? @"●" : @"○");
        NSString *detail = progress[stage[@"key"]] ?: stage[@"title"];
        NSColor *color = completed ? [NSColor colorWithRed:0.12 green:0.52 blue:0.34 alpha:1] : (active ? [NSColor colorWithRed:0.15 green:0.43 blue:0.92 alpha:1] : [NSColor colorWithWhite:0.66 alpha:1]);
        NSFont *font = active ? [NSFont systemFontOfSize:13 weight:NSFontWeightSemibold] : [NSFont systemFontOfSize:13 weight:NSFontWeightRegular];
        AppendAgentText(content, [NSString stringWithFormat:@"%@  %@\n", marker, detail], font, color, index + 1 == stages.count ? 0 : 8);
    }
    return content;
}

- (NSAttributedString *)agentCompletedTranscriptForQuestion:(NSString *)question trace:(NSArray<NSString *> *)trace reply:(NSString *)reply summary:(NSString *)summary resultTitle:(NSString *)resultTitle resultCount:(NSUInteger)resultCount {
    (void)summary;
    NSMutableAttributedString *content = [self agentTranscriptWithHistory];
    AppendAgentText(content, @"你\n", [NSFont systemFontOfSize:12 weight:NSFontWeightSemibold], NSColor.secondaryLabelColor, 3);
    AppendAgentText(content, [NSString stringWithFormat:@"%@\n", question], [NSFont systemFontOfSize:15], [NSColor colorWithWhite:0.10 alpha:1], 20);
    AppendAgentText(content, @"✦  Agent\n", [NSFont systemFontOfSize:12 weight:NSFontWeightSemibold], [NSColor colorWithRed:0.15 green:0.38 blue:0.82 alpha:1], 3);
    AppendAgentText(content, @"执行完成\n", [NSFont systemFontOfSize:15 weight:NSFontWeightSemibold], [NSColor colorWithWhite:0.12 alpha:1], 14);
    for (NSString *item in trace) {
        AppendAgentText(content, [NSString stringWithFormat:@"✓  %@\n", item], [NSFont systemFontOfSize:13], [NSColor colorWithRed:0.12 green:0.52 blue:0.34 alpha:1], 8);
    }
    if (trace.count > 0 && trace.count < 4) {
        NSArray<NSDictionary<NSString *, NSString *> *> *stages = [self agentStages];
        for (NSUInteger index = trace.count; index < stages.count; index += 1) {
            AppendAgentText(content, [NSString stringWithFormat:@"—  %@ · 无候选，无需执行\n", stages[index][@"title"]], [NSFont systemFontOfSize:13], [NSColor colorWithWhite:0.60 alpha:1], 8);
        }
    }
    NSString *heading = resultTitle.length ? resultTitle : [NSString stringWithFormat:@"结果 · %lu 位", (unsigned long)resultCount];
    AppendAgentText(content, [NSString stringWithFormat:@"\n%@\n", heading], [NSFont systemFontOfSize:16 weight:NSFontWeightSemibold], [NSColor colorWithWhite:0.10 alpha:1], 6);
    AppendAgentText(content, [NSString stringWithFormat:@"%@\n", reply], [NSFont systemFontOfSize:13], [NSColor colorWithWhite:0.22 alpha:1], 12);
    if (self.visibleLeads.count) {
        AppendAgentText(content, @"精确互动统计\n", [NSFont systemFontOfSize:12 weight:NSFontWeightSemibold], NSColor.secondaryLabelColor, 4);
        for (NSUInteger index = 0; index < MIN(self.visibleLeads.count, 4); index += 1) {
            NSDictionary *lead = self.visibleLeads[index];
            NSDictionary *stats = [lead[@"conversation_stats"] isKindOfClass:NSDictionary.class] ? lead[@"conversation_stats"] : @{};
            NSString *line = [NSString stringWithFormat:@"%@ · %@ 条 · %@ 个活跃日 · 对方回复中位数 %@ 分钟 · 我方 %@ 分钟\n", lead[@"display_name"] ?: @"联系人", stats[@"message_count"] ?: @0, stats[@"active_days"] ?: @0, stats[@"their_median_response_minutes"] ?: @"—", stats[@"my_median_response_minutes"] ?: @"—"];
            AppendAgentText(content, line, [NSFont monospacedDigitSystemFontOfSize:11 weight:NSFontWeightRegular], NSColor.secondaryLabelColor, 3);
        }
        AppendAgentText(content, @"\n", [NSFont systemFontOfSize:8], NSColor.clearColor, 0);
    }
    NSArray *sections = [self.lastAgentResult[@"sections"] isKindOfClass:NSArray.class] ? self.lastAgentResult[@"sections"] : @[];
    for (NSDictionary *section in sections) {
        NSString *title = [section[@"title"] isKindOfClass:NSString.class] ? section[@"title"] : @"分析";
        NSString *body = [section[@"content"] isKindOfClass:NSString.class] ? section[@"content"] : @"";
        NSNumber *confidence = [section[@"confidence"] isKindOfClass:NSNumber.class] ? section[@"confidence"] : nil;
        NSString *titleLine = confidence ? [NSString stringWithFormat:@"%@  ·  置信度 %@%%\n", title, confidence] : [NSString stringWithFormat:@"%@\n", title];
        AppendAgentText(content, titleLine, [NSFont systemFontOfSize:14 weight:NSFontWeightSemibold], [NSColor colorWithWhite:0.12 alpha:1], 3);
        AppendAgentText(content, [body stringByAppendingString:@"\n"], [NSFont systemFontOfSize:13], [NSColor colorWithWhite:0.25 alpha:1], 5);
        NSArray *evidenceIDs = [section[@"evidence_ids"] isKindOfClass:NSArray.class] ? section[@"evidence_ids"] : @[];
        for (NSUInteger index = 0; index < evidenceIDs.count; index += 1) AppendEvidenceLink(content, [NSString stringWithFormat:@"证据 %lu", (unsigned long)index + 1], evidenceIDs[index]);
        NSArray *counterIDs = [section[@"counter_evidence_ids"] isKindOfClass:NSArray.class] ? section[@"counter_evidence_ids"] : @[];
        for (NSUInteger index = 0; index < counterIDs.count; index += 1) AppendEvidenceLink(content, [NSString stringWithFormat:@"反例 %lu", (unsigned long)index + 1], counterIDs[index]);
        AppendAgentText(content, @"\n\n", [NSFont systemFontOfSize:8], NSColor.clearColor, 0);
    }
    NSArray *items = [self.lastAgentResult[@"structured_items"] isKindOfClass:NSArray.class] ? self.lastAgentResult[@"structured_items"] : @[];
    if (items.count) {
        AppendAgentText(content, @"时间线与待办\n", [NSFont systemFontOfSize:14 weight:NSFontWeightSemibold], [NSColor colorWithWhite:0.12 alpha:1], 5);
        for (NSDictionary *item in items) {
            NSString *line = [NSString stringWithFormat:@"• %@  %@  %@\n", item[@"date"] ?: @"", item[@"status"] ?: @"", item[@"content"] ?: @""];
            AppendAgentText(content, line, [NSFont systemFontOfSize:13], [NSColor colorWithWhite:0.25 alpha:1], 4);
        }
    }
    NSArray *limitations = [self.lastAgentResult[@"limitations"] isKindOfClass:NSArray.class] ? self.lastAgentResult[@"limitations"] : @[];
    if (limitations.count) {
        AppendAgentText(content, @"边界说明\n", [NSFont systemFontOfSize:12 weight:NSFontWeightSemibold], NSColor.secondaryLabelColor, 3);
        for (NSString *item in limitations) AppendAgentText(content, [NSString stringWithFormat:@"• %@\n", item], [NSFont systemFontOfSize:12], NSColor.secondaryLabelColor, 3);
    }
    NSArray *followups = [self.lastAgentResult[@"suggested_followups"] isKindOfClass:NSArray.class] ? self.lastAgentResult[@"suggested_followups"] : @[];
    if (followups.count) {
        AppendAgentText(content, @"\n可以继续问\n", [NSFont systemFontOfSize:12 weight:NSFontWeightSemibold], NSColor.secondaryLabelColor, 4);
        for (NSUInteger index = 0; index < MIN(followups.count, 4); index += 1) AppendAgentText(content, [NSString stringWithFormat:@"%lu. %@\n", (unsigned long)index + 1, followups[index]], [NSFont systemFontOfSize:12], NSColor.secondaryLabelColor, 4);
    }
    return content;
}

- (NSAttributedString *)agentFailureTranscriptForQuestion:(NSString *)question progress:(NSDictionary<NSString *, NSString *> *)progress activeStage:(NSString *)activeStage message:(NSString *)message {
    NSMutableAttributedString *content = [[self agentProgressTranscriptForQuestion:question progress:progress activeStage:activeStage] mutableCopy];
    AppendAgentText(content, @"\n任务失败\n", [NSFont systemFontOfSize:15 weight:NSFontWeightSemibold], NSColor.systemRedColor, 4);
    AppendAgentText(content, message, [NSFont systemFontOfSize:13], NSColor.systemRedColor, 0);
    return content;
}

- (void)askCustomerAgent:(id)sender {
    (void)sender;
    NSString *question = [self.agentInput.string stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    if (!question.length || self.agentCommandRunning) { NSBeep(); return; }
    if (self.lastAgentResult) self.priorAgentTranscript = [self.agentTranscript.textStorage copy];
    self.lastAgentQuestion = question;
    self.lastAgentResult = nil;
    self.visibleLeads = @[];
    NSMutableDictionary<NSString *, NSString *> *progressByStage = [@{@"planning": @"理解任务与时间范围"} mutableCopy];
    __block NSString *activeStage = @"planning";
    [self setAgentTranscriptContent:[self agentProgressTranscriptForQuestion:question progress:progressByStage activeStage:activeStage]];
    self.statusLabel.stringValue = @"理解任务";
    self.statusLabel.textColor = NSColor.systemOrangeColor;
    self.agentActivityIndicator.hidden = NO;
    [self.agentActivityIndicator startAnimation:nil];
    self.agentSendButton.enabled = NO;
    self.agentSendButton.title = @"…";
    [self.agentTranscript scrollRangeToVisible:NSMakeRange(self.agentTranscript.string.length, 0)];
    [self.window.contentView displayIfNeeded];
    NSString *databasePath = self.currentDBPath;
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        int status = 0; NSError *error = nil;
        NSMutableArray<NSString *> *arguments = [@[@"-m", @"agent_core.customer_agent_cli", @"--db", databasePath, @"--question", question] mutableCopy];
        if (self.agentSessionID.length) [arguments addObjectsFromArray:@[@"--session-id", self.agentSessionID]];
        NSString *mode = [self.analysisModePicker.selectedItem.representedObject isKindOfClass:NSString.class] ? self.analysisModePicker.selectedItem.representedObject : @"";
        if (mode.length) [arguments addObjectsFromArray:@[@"--mode", mode]];
        NSArray<NSString *> *lines = [self runCustomerAgentCommand:arguments terminationStatus:&status error:&error progressHandler:^(NSDictionary *eventObject) {
            NSString *progressText = [self agentProgressText:eventObject];
            NSString *stage = [eventObject[@"stage"] isKindOfClass:NSString.class] ? eventObject[@"stage"] : @"planning";
            activeStage = stage;
            progressByStage[stage] = progressText;
            NSDictionary<NSString *, NSString *> *progressSnapshot = [progressByStage copy];
            dispatch_async(dispatch_get_main_queue(), ^{
                self.statusLabel.stringValue = progressText;
                self.statusLabel.textColor = NSColor.systemOrangeColor;
                [self setAgentTranscriptContent:[self agentProgressTranscriptForQuestion:question progress:progressSnapshot activeStage:stage]];
                [self.agentTranscript scrollRangeToVisible:NSMakeRange(self.agentTranscript.string.length, 0)];
            });
        }];
        NSDictionary *object = [self lastJSONObjectFromLines:lines];
        NSDictionary<NSString *, NSString *> *finalProgress = [progressByStage copy];
        NSString *finalStage = activeStage;
        dispatch_async(dispatch_get_main_queue(), ^{
            self.agentSendButton.enabled = YES;
            self.agentSendButton.title = @"↑";
            [self.agentActivityIndicator stopAnimation:nil];
            self.agentActivityIndicator.hidden = YES;
            if (status != 0 || ![object[@"leads"] isKindOfClass:NSArray.class]) {
                NSString *message = [self messageFromEvent:object defaultMessage:(error.localizedDescription ?: @"DeepSeek 微信客户分析 Agent 查询失败")];
                [self setAgentTranscriptContent:[self agentFailureTranscriptForQuestion:question progress:finalProgress activeStage:finalStage message:message]];
                self.statusLabel.stringValue = @"任务失败";
                self.statusLabel.textColor = NSColor.systemRedColor;
                [self.agentTranscript scrollRangeToVisible:NSMakeRange(self.agentTranscript.string.length, 0)];
                return;
            }
            self.visibleLeads = object[@"leads"];
            self.allLeads = self.visibleLeads;
            self.lastAgentResult = object;
            self.agentSessionID = [object[@"session_id"] isKindOfClass:NSString.class] ? object[@"session_id"] : self.agentSessionID;
            self.startupError = nil;
            NSString *reply = object[@"answer"] ?: object[@"reply"] ?: @"已完成查询。";
            NSString *resultTitle = [object[@"result_title"] isKindOfClass:NSString.class] ? object[@"result_title"] : @"智能分析结果";
            NSArray *trace = [object[@"analysis_trace"] isKindOfClass:NSArray.class] ? object[@"analysis_trace"] : @[];
            [self setAgentTranscriptContent:[self agentCompletedTranscriptForQuestion:question trace:trace reply:reply summary:[self agentLeadSummary] resultTitle:resultTitle resultCount:self.visibleLeads.count]];
            self.agentInput.string = @"";
            self.agentPlaceholderLabel.hidden = NO;
            self.statusLabel.stringValue = [NSString stringWithFormat:@"完成 · %@", resultTitle];
            self.statusLabel.textColor = NSColor.systemGreenColor;
            [self.agentTranscript scrollRangeToVisible:NSMakeRange(self.agentTranscript.string.length, 0)];
        });
    });
}

- (void)newAgentAnalysis:(id)sender {
    (void)sender;
    if (self.agentCommandRunning) { NSBeep(); return; }
    self.agentSessionID = nil; self.priorAgentTranscript = nil; self.lastAgentResult = nil; self.lastAgentQuestion = nil;
    self.visibleLeads = @[]; self.allLeads = @[]; self.agentInput.string = @""; self.agentPlaceholderLabel.hidden = NO;
    [self setAgentTranscriptContent:[[NSAttributedString alloc] initWithString:@""]];
    self.statusLabel.stringValue = [self startupDetailText]; self.statusLabel.textColor = NSColor.systemGreenColor;
}

- (void)reloadSavedAnalyses {
    if (self.agentCommandRunning) return;
    NSString *databasePath = self.currentDBPath;
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        int status = 0; NSError *error = nil;
        NSArray<NSString *> *lines = [self runAgentCommand:@[@"-m", @"agent_core.customer_agent_cli", @"--db", databasePath, @"--list-saved"] terminationStatus:&status error:&error];
        NSDictionary *object = [self lastJSONObjectFromLines:lines];
        NSArray *saved = status == 0 && [object[@"saved_analyses"] isKindOfClass:NSArray.class] ? object[@"saved_analyses"] : @[];
        dispatch_async(dispatch_get_main_queue(), ^{
            [self.savedAnalysisPicker removeAllItems]; [self.savedAnalysisPicker addItemWithTitle:@"已保存分析"];
            for (NSDictionary *item in saved) {
                [self.savedAnalysisPicker addItemWithTitle:item[@"title"] ?: @"未命名分析"];
                self.savedAnalysisPicker.lastItem.representedObject = item;
            }
            [self.savedAnalysisPicker selectItemAtIndex:0];
        });
    });
}

- (void)saveCurrentAnalysis:(id)sender {
    (void)sender;
    if (!self.agentSessionID.length || !self.lastAgentResult || self.agentCommandRunning) { NSBeep(); return; }
    NSString *databasePath = self.currentDBPath; NSString *sessionID = self.agentSessionID;
    self.statusLabel.stringValue = @"正在保存分析"; self.statusLabel.textColor = NSColor.systemOrangeColor;
    self.agentActivityIndicator.hidden = NO; [self.agentActivityIndicator startAnimation:nil];
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        int status = 0; NSError *error = nil;
        NSArray<NSString *> *lines = [self runAgentCommand:@[@"-m", @"agent_core.customer_agent_cli", @"--db", databasePath, @"--save-session", sessionID] terminationStatus:&status error:&error];
        dispatch_async(dispatch_get_main_queue(), ^{
            [self.agentActivityIndicator stopAnimation:nil]; self.agentActivityIndicator.hidden = YES;
            if (status == 0) { self.statusLabel.stringValue = @"分析已保存，可随新消息刷新"; self.statusLabel.textColor = NSColor.systemGreenColor; [self reloadSavedAnalyses]; }
            else { self.statusLabel.stringValue = [self messageFromEvent:[self lastJSONObjectFromLines:lines] defaultMessage:(error.localizedDescription ?: @"保存失败")]; self.statusLabel.textColor = NSColor.systemRedColor; }
        });
    });
}

- (void)applySavedAnalysis:(NSDictionary *)object title:(NSString *)title statusText:(NSString *)statusText {
    self.priorAgentTranscript = nil;
    self.lastAgentResult = object; self.visibleLeads = object[@"leads"]; self.allLeads = self.visibleLeads;
    self.lastAgentQuestion = object[@"query"] ?: title; self.agentSessionID = object[@"session_id"] ?: self.agentSessionID;
    NSArray *trace = [object[@"analysis_trace"] isKindOfClass:NSArray.class] ? object[@"analysis_trace"] : @[];
    [self setAgentTranscriptContent:[self agentCompletedTranscriptForQuestion:[NSString stringWithFormat:@"已保存：%@", title] trace:trace reply:object[@"answer"] ?: @"已载入" summary:@"" resultTitle:object[@"result_title"] ?: title resultCount:self.visibleLeads.count]];
    self.statusLabel.stringValue = statusText; self.statusLabel.textColor = NSColor.systemGreenColor;
}

- (void)loadSelectedAnalysis:(id)sender {
    (void)sender;
    NSDictionary *saved = [self.savedAnalysisPicker.selectedItem.representedObject isKindOfClass:NSDictionary.class] ? self.savedAnalysisPicker.selectedItem.representedObject : nil;
    if (!saved || self.agentCommandRunning) return;
    NSString *savedID = saved[@"saved_id"] ?: @""; NSString *title = saved[@"title"] ?: @"已保存分析"; NSString *databasePath = self.currentDBPath;
    self.statusLabel.stringValue = @"正在载入本地分析"; self.statusLabel.textColor = NSColor.systemOrangeColor;
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        int status = 0; NSError *error = nil;
        NSArray<NSString *> *lines = [self runAgentCommand:@[@"-m", @"agent_core.customer_agent_cli", @"--db", databasePath, @"--load-saved", savedID] terminationStatus:&status error:&error];
        NSDictionary *object = [self lastJSONObjectFromLines:lines];
        dispatch_async(dispatch_get_main_queue(), ^{
            if (status != 0 || ![object[@"leads"] isKindOfClass:NSArray.class]) { self.statusLabel.stringValue = [self messageFromEvent:object defaultMessage:(error.localizedDescription ?: @"载入失败")]; self.statusLabel.textColor = NSColor.systemRedColor; return; }
            [self applySavedAnalysis:object title:title statusText:@"已从本机载入"];
        });
    });
}

- (void)deleteSelectedAnalysis:(id)sender {
    (void)sender;
    NSDictionary *saved = [self.savedAnalysisPicker.selectedItem.representedObject isKindOfClass:NSDictionary.class] ? self.savedAnalysisPicker.selectedItem.representedObject : nil;
    if (!saved || self.agentCommandRunning) { NSBeep(); return; }
    NSAlert *alert = [[NSAlert alloc] init]; alert.messageText = @"删除这项保存的分析？"; alert.informativeText = saved[@"title"] ?: @"已保存分析"; [alert addButtonWithTitle:@"删除"]; [alert addButtonWithTitle:@"取消"];
    if ([alert runModal] != NSAlertFirstButtonReturn) return;
    NSString *savedID = saved[@"saved_id"] ?: @""; NSString *databasePath = self.currentDBPath;
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        int status = 0; NSError *error = nil;
        NSArray<NSString *> *lines = [self runAgentCommand:@[@"-m", @"agent_core.customer_agent_cli", @"--db", databasePath, @"--delete-saved", savedID] terminationStatus:&status error:&error];
        dispatch_async(dispatch_get_main_queue(), ^{
            if (status == 0) { [self newAgentAnalysis:nil]; self.statusLabel.stringValue = @"保存的分析已删除"; self.statusLabel.textColor = NSColor.systemGreenColor; [self reloadSavedAnalyses]; }
            else { self.statusLabel.stringValue = [self messageFromEvent:[self lastJSONObjectFromLines:lines] defaultMessage:(error.localizedDescription ?: @"删除失败")]; self.statusLabel.textColor = NSColor.systemRedColor; }
        });
    });
}

- (void)refreshSelectedAnalysis:(id)sender {
    (void)sender;
    NSDictionary *saved = [self.savedAnalysisPicker.selectedItem.representedObject isKindOfClass:NSDictionary.class] ? self.savedAnalysisPicker.selectedItem.representedObject : nil;
    if (!saved || self.agentCommandRunning) return;
    NSString *savedID = saved[@"saved_id"] ?: @"";
    NSString *title = saved[@"title"] ?: @"已保存分析";
    self.statusLabel.stringValue = @"正在检查新增消息"; self.statusLabel.textColor = NSColor.systemOrangeColor;
    self.agentActivityIndicator.hidden = NO; [self.agentActivityIndicator startAnimation:nil];
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        int status = 0; NSError *error = nil;
        NSArray<NSString *> *lines = [self runCustomerAgentCommand:@[@"-m", @"agent_core.customer_agent_cli", @"--db", self.currentDBPath, @"--refresh-saved", savedID] terminationStatus:&status error:&error progressHandler:^(NSDictionary *eventObject) {
            dispatch_async(dispatch_get_main_queue(), ^{ self.statusLabel.stringValue = [self agentProgressText:eventObject]; });
        }];
        NSDictionary *object = [self lastJSONObjectFromLines:lines];
        dispatch_async(dispatch_get_main_queue(), ^{
            [self.agentActivityIndicator stopAnimation:nil]; self.agentActivityIndicator.hidden = YES;
            if (status != 0 || ![object[@"leads"] isKindOfClass:NSArray.class]) {
                self.statusLabel.stringValue = [self messageFromEvent:object defaultMessage:(error.localizedDescription ?: @"刷新失败")]; self.statusLabel.textColor = NSColor.systemRedColor; return;
            }
            BOOL unchanged = [object[@"refresh_status"] isEqualToString:@"unchanged"];
            self.agentSessionID = object[@"session_id"] ?: saved[@"session_id"];
            [self applySavedAnalysis:object title:title statusText:(unchanged ? @"没有相关新消息" : [NSString stringWithFormat:@"已加入 %@ 条新证据", object[@"new_evidence_count"] ?: @0])];
            if (!unchanged) [self reloadSavedAnalyses];
        });
    });
}

- (NSString *)currentDBPath {
    NSString *db = NSProcessInfo.processInfo.environment[@"WECHAT_SALES_AGENT_DB"];
    if (!db.length) db = [NSHomeDirectory() stringByAppendingPathComponent:@"Library/Application Support/WeChatSalesAgent/agent_state.sqlite3"];
    db = [db stringByExpandingTildeInPath];
    if (![db isAbsolutePath]) db = [NSFileManager.defaultManager.currentDirectoryPath stringByAppendingPathComponent:db];
    db = [db stringByStandardizingPath];
    [[NSFileManager defaultManager] createDirectoryAtPath:[db stringByDeletingLastPathComponent] withIntermediateDirectories:YES attributes:nil error:nil];
    return [[db stringByResolvingSymlinksInPath] stringByStandardizingPath];
}

- (NSArray<NSString *> *)runAgentCommand:(NSArray<NSString *> *)arguments terminationStatus:(int *)status error:(NSError **)error {
    return [self runAgentCommand:arguments stdinString:nil terminationStatus:status error:error];
}

- (NSArray<NSString *> *)runAgentCommand:(NSArray<NSString *> *)arguments stdinString:(NSString *)stdinString terminationStatus:(int *)status error:(NSError **)error {
    if (self.agentCommandRunning) {
        if (status) *status = 75;
        if (error) *error = [NSError errorWithDomain:@"WeChatSalesAgent" code:75 userInfo:@{NSLocalizedDescriptionKey: @"另一项操作正在进行，请等待完成"}];
        return @[];
    }
    self.agentCommandRunning = YES;
    NSTask *task = [[NSTask alloc] init];
    self.activeAgentTask = task;
    task.executableURL = [NSURL fileURLWithPath:self.pythonExecutable];
    task.arguments = arguments;
    task.environment = self.agentEnvironment;
    NSPipe *pipe = [NSPipe pipe];
    task.standardOutput = pipe;
    task.standardError = pipe;
    NSPipe *inputPipe = nil;
    if (stdinString) {
        inputPipe = [NSPipe pipe];
        task.standardInput = inputPipe;
    }
    if (![task launchAndReturnError:error]) {
        if (status) *status = -1;
        self.activeAgentTask = nil;
        self.agentCommandRunning = NO;
        return @[];
    }
    if (stdinString) {
        NSData *input = [stdinString dataUsingEncoding:NSUTF8StringEncoding];
        [inputPipe.fileHandleForWriting writeData:input ?: NSData.data];
        [inputPipe.fileHandleForWriting closeFile];
    }
    NSData *data = [self drainPipe:pipe whileTaskRuns:task];
    if (status) *status = task.terminationStatus;
    self.activeAgentTask = nil;
    self.agentCommandRunning = NO;
    NSString *output = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] ?: @"";
    NSMutableArray<NSString *> *lines = [NSMutableArray array];
    for (NSString *line in [output componentsSeparatedByString:@"\n"]) if (line.length) [lines addObject:line];
    return lines;
}

- (NSArray<NSString *> *)runCustomerAgentCommand:(NSArray<NSString *> *)arguments terminationStatus:(int *)status error:(NSError **)error progressHandler:(void (^)(NSDictionary *))progressHandler {
    if (self.agentCommandRunning) {
        if (status) *status = 75;
        if (error) *error = [NSError errorWithDomain:@"WeChatSalesAgent" code:75 userInfo:@{NSLocalizedDescriptionKey: @"另一项操作正在进行，请等待完成"}];
        return @[];
    }
    self.agentCommandRunning = YES;
    NSTask *task = [[NSTask alloc] init];
    self.activeAgentTask = task;
    task.executableURL = [NSURL fileURLWithPath:self.pythonExecutable];
    task.arguments = arguments;
    task.environment = self.agentEnvironment;
    NSPipe *pipe = [NSPipe pipe];
    task.standardOutput = pipe;
    task.standardError = pipe;
    if (![task launchAndReturnError:error]) {
        if (status) *status = -1;
        self.activeAgentTask = nil;
        self.agentCommandRunning = NO;
        return @[];
    }
    NSMutableData *pending = [NSMutableData data];
    NSMutableArray<NSString *> *lines = [NSMutableArray array];
    NSData *newline = [@"\n" dataUsingEncoding:NSUTF8StringEncoding];
    while (YES) {
        NSData *chunk = [pipe.fileHandleForReading availableData];
        if (!chunk.length) break;
        [pending appendData:chunk];
        while (pending.length) {
            NSRange range = [pending rangeOfData:newline options:0 range:NSMakeRange(0, pending.length)];
            if (range.location == NSNotFound) break;
            NSData *lineData = [pending subdataWithRange:NSMakeRange(0, range.location)];
            [pending replaceBytesInRange:NSMakeRange(0, NSMaxRange(range)) withBytes:NULL length:0];
            NSString *line = [[NSString alloc] initWithData:lineData encoding:NSUTF8StringEncoding];
            if (!line.length) continue;
            [lines addObject:line];
            NSDictionary *object = [NSJSONSerialization JSONObjectWithData:lineData options:0 error:nil];
            if ([object[@"event"] isEqualToString:@"agent_progress"] && progressHandler) progressHandler(object);
        }
    }
    [task waitUntilExit];
    if (pending.length) {
        NSString *line = [[NSString alloc] initWithData:pending encoding:NSUTF8StringEncoding];
        if (line.length) [lines addObject:line];
    }
    if (status) *status = task.terminationStatus;
    self.activeAgentTask = nil;
    self.agentCommandRunning = NO;
    return lines;
}

- (NSString *)agentProgressText:(NSDictionary *)eventObject {
    NSString *stage = eventObject[@"stage"] ?: @"";
    NSDictionary *stats = [eventObject[@"stats"] isKindOfClass:NSDictionary.class] ? eventObject[@"stats"] : @{};
    if ([stage isEqualToString:@"retrieval"]) return [NSString stringWithFormat:@"证据召回 · 扫描 %@ 个对话，召回 %@ 个候选（%@ 天）", stats[@"conversations"] ?: @0, stats[@"candidates"] ?: @0, stats[@"time_window_days"] ?: @0];
    if ([stage isEqualToString:@"analysis"]) {
        NSNumber *completed = stats[@"completed"];
        return completed ? [NSString stringWithFormat:@"语义复核 · 已完成 %@/%@ 批，共 %@ 个候选", completed, stats[@"batches"] ?: @0, stats[@"candidates"] ?: @0] : [NSString stringWithFormat:@"语义复核 · 准备 %@ 批，共 %@ 个候选", stats[@"batches"] ?: @0, stats[@"candidates"] ?: @0];
    }
    if ([stage isEqualToString:@"audit"]) {
        NSNumber *completed = stats[@"completed"];
        return completed ? [NSString stringWithFormat:@"覆盖审计 · 已完成 %@/%@ 批，独立复核 %@ 个候选", completed, stats[@"batches"] ?: @0, stats[@"candidates"] ?: @0] : [NSString stringWithFormat:@"覆盖审计 · 准备 %@ 批，独立复核 %@ 个候选", stats[@"batches"] ?: @0, stats[@"candidates"] ?: @0];
    }
    return eventObject[@"message"] ?: @"分析中";
}

- (NSDictionary *)lastJSONObjectFromLines:(NSArray<NSString *> *)lines {
    for (NSString *line in lines.reverseObjectEnumerator) {
        NSData *data = [line dataUsingEncoding:NSUTF8StringEncoding];
        id object = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
        if ([object isKindOfClass:NSDictionary.class]) return object;
    }
    return nil;
}

- (void)rebuildWorkspaceWithMessage:(NSString *)message color:(NSColor *)color {
    NSWindow *previousWindow = self.window;
    NSRect frame = previousWindow.frame;
    [self buildWindow];
    [self.window setFrame:frame display:YES];
    if (message.length) {
        self.statusLabel.stringValue = message;
        self.statusLabel.textColor = color ?: NSColor.systemGreenColor;
    }
    [self.window makeKeyAndOrderFront:nil];
    [previousWindow orderOut:nil];
}

- (NSString *)messageFromEvent:(NSDictionary *)eventObject defaultMessage:(NSString *)defaultMessage {
    NSString *code = eventObject[@"code"] ?: @"";
    NSString *message = eventObject[@"message"] ?: defaultMessage ?: @"";
    return code.length ? [NSString stringWithFormat:@"%@：%@", code, message] : message;
}

- (NSString *)selectedAccountIDFromLines:(NSArray<NSString *> *)lines {
    NSMutableDictionary<NSString *, NSDictionary *> *byAccountID = [NSMutableDictionary dictionary];
    for (NSString *line in lines) {
        NSData *data = [line dataUsingEncoding:NSUTF8StringEncoding];
        NSDictionary *event = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
        if (![event[@"code"] isEqualToString:@"WECHAT_ACCOUNT_AVAILABLE"]) continue;
        NSDictionary *evidence = event[@"evidence"];
        NSString *accountID = evidence[@"account_id"];
        if (!accountID.length) continue;
        NSDictionary *existing = byAccountID[accountID];
        if (!existing || [evidence[@"current"] isEqualToString:@"true"]) byAccountID[accountID] = evidence;
    }
    NSArray<NSDictionary *> *accounts = [byAccountID.allValues sortedArrayUsingComparator:^NSComparisonResult(NSDictionary *left, NSDictionary *right) {
        return [left[@"account_id"] compare:right[@"account_id"]];
    }];
    NSArray *current = [accounts filteredArrayUsingPredicate:[NSPredicate predicateWithBlock:^BOOL(NSDictionary *item, NSDictionary *bindings) {
        (void)bindings;
        return [item[@"current"] isEqualToString:@"true"];
    }]];
    if (accounts.count == 1) return accounts[0][@"account_id"];
    if (!accounts.count) return @"";
    NSAlert *alert = [[NSAlert alloc] init];
    alert.messageText = @"选择要连接的微信账号";
    alert.informativeText = @"当前登录与历史账号已明确标注；选择后本次解密、查询和分析只绑定这一账号。";
    NSPopUpButton *picker = [[NSPopUpButton alloc] initWithFrame:NSMakeRect(0, 0, 420, 26) pullsDown:NO];
    for (NSDictionary *account in accounts) {
        NSString *state = [account[@"current"] isEqualToString:@"true"] ? @"当前登录" : @"历史账号";
        [picker addItemWithTitle:[NSString stringWithFormat:@"%@ · %@", account[@"account_id"], state]];
        picker.lastItem.representedObject = account[@"account_id"];
    }
    if (current.count == 1) {
        NSUInteger index = [accounts indexOfObject:current[0]];
        if (index != NSNotFound) [picker selectItemAtIndex:index];
    }
    alert.accessoryView = picker;
    [alert addButtonWithTitle:@"连接此账号"];
    [alert addButtonWithTitle:@"取消"];
    return [alert runModal] == NSAlertFirstButtonReturn ? picker.selectedItem.representedObject : @"";
}

- (void)finishWeChatSyncWithBinary:(NSString *)chatlogBinary accountID:(NSString *)selectedAccountID {
    NSString *databasePath = self.currentDBPath;
    self.statusLabel.stringValue = @"正在同步微信会话…"; self.statusLabel.textColor = NSColor.systemOrangeColor;
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        int status = 1; NSError *error = nil;
        NSArray<NSString *> *syncLines = [self runAgentCommand:@[@"-m", @"agent_core.sync_cli", @"--db", databasePath, @"--chatlog-bin", chatlogBinary, @"sync", @"--account-id", selectedAccountID, @"--limit", @"5000"] terminationStatus:&status error:&error];
        NSDictionary *eventObject = [self lastJSONObjectFromLines:syncLines];
        if (status != 0) {
            dispatch_async(dispatch_get_main_queue(), ^{ self.wechatSyncRunning = NO; self.statusLabel.stringValue = [self messageFromEvent:eventObject defaultMessage:(error.localizedDescription ?: @"微信数据同步失败")]; self.statusLabel.textColor = NSColor.systemRedColor; });
            return;
        }
        NSString *accountID = eventObject[@"evidence"][@"account_id"] ?: @"";
        if (![accountID isEqualToString:selectedAccountID]) {
            dispatch_async(dispatch_get_main_queue(), ^{ self.wechatSyncRunning = NO; self.statusLabel.stringValue = @"同步结果账号与所选账号不一致"; self.statusLabel.textColor = NSColor.systemRedColor; });
            return;
        }
        dispatch_async(dispatch_get_main_queue(), ^{ self.statusLabel.stringValue = @"正在构建完整历史分析语料…"; });
        NSArray<NSString *> *corpusLines = [self runAgentCommand:@[@"-m", @"agent_core.corpus_cli", @"--db", databasePath, @"--account-id", accountID, @"--all-history"] terminationStatus:&status error:&error];
        eventObject = [self lastJSONObjectFromLines:corpusLines];
        if (status != 0) {
            dispatch_async(dispatch_get_main_queue(), ^{ self.wechatSyncRunning = NO; self.statusLabel.stringValue = [self messageFromEvent:eventObject defaultMessage:(error.localizedDescription ?: @"完整历史语料构建失败")]; self.statusLabel.textColor = NSColor.systemRedColor; });
            return;
        }
        NSDictionary *readiness = [self loadReadiness:nil] ?: @{};
        NSNumber *eligible = readiness[@"eligible_conversations"] ?: @0;
        dispatch_async(dispatch_get_main_queue(), ^{
            self.snapshot = @{ @"metrics": @{ @"customer_total": @0, @"high_intent": @0, @"activation_needed": @0, @"recent_leads": @0, @"distribution": @{} }, @"leads": @[], @"run": @{}, @"account_id": accountID };
            self.allLeads = @[]; self.visibleLeads = @[]; self.startupError = @"微信已同步，等待 Agent 指令"; self.wechatSyncRunning = NO;
            [self rebuildWorkspaceWithMessage:[NSString stringWithFormat:@"微信同步完成 · %@ 个双向私聊可分析", eligible] color:NSColor.systemGreenColor];
        });
    });
}

- (void)connectWeChatData:(id)sender {
    if (self.wechatSyncRunning) {
        self.statusLabel.stringValue = @"正在连接并同步微信…";
        self.statusLabel.textColor = NSColor.systemOrangeColor;
        return;
    }
    if (self.agentCommandRunning) { NSBeep(); self.statusLabel.stringValue = @"另一项操作正在进行"; return; }
    if (![self isSIPDisabled]) {
        self.statusLabel.stringValue = @"SIP 未关闭，无法读取微信密钥";
        self.statusLabel.textColor = NSColor.systemRedColor;
        [self showSIPSetup:nil];
        return;
    }
    [self updateSIPStatusLabel:YES];
    NSString *chatlogBinary = [[NSBundle mainBundle].resourcePath stringByAppendingPathComponent:@"Chatlog/chatlog-darwin-arm64"];
    if (![[NSFileManager defaultManager] isExecutableFileAtPath:chatlogBinary]) {
        self.statusLabel.stringValue = @"本地微信数据组件缺失";
        self.statusLabel.textColor = NSColor.systemRedColor;
        return;
    }
    self.wechatSyncRunning = YES;
    self.statusLabel.stringValue = @"正在读取微信账号…";
    self.statusLabel.textColor = NSColor.systemOrangeColor;
    NSString *databasePath = self.currentDBPath;
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        int status = 1; NSError *error = nil;
        NSArray<NSString *> *accountLines = [self runAgentCommand:@[@"-m", @"agent_core.sync_cli", @"--db", databasePath, @"--chatlog-bin", chatlogBinary, @"accounts"] terminationStatus:&status error:&error];
        dispatch_async(dispatch_get_main_queue(), ^{
            if (status != 0) { self.wechatSyncRunning = NO; self.statusLabel.stringValue = error.localizedDescription ?: @"无法读取可用的微信账号"; self.statusLabel.textColor = NSColor.systemRedColor; return; }
            NSString *selectedAccountID = [self selectedAccountIDFromLines:accountLines];
            if (!selectedAccountID.length) { self.wechatSyncRunning = NO; self.statusLabel.stringValue = @"未选择微信账号"; self.statusLabel.textColor = NSColor.systemOrangeColor; return; }
            if (self.chatlogServiceTask.running && ![self.chatlogServiceAccountID isEqualToString:selectedAccountID]) [self stopChatlogService];
            self.statusLabel.stringValue = @"正在准备所选账号的本地数据…";
            dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
                int prepareStatus = 1; NSError *prepareError = nil;
                NSArray<NSString *> *prepareLines = [self runAgentCommand:@[@"-m", @"agent_core.sync_cli", @"--db", databasePath, @"--chatlog-bin", chatlogBinary, @"prepare-runtime", @"--account-id", selectedAccountID] terminationStatus:&prepareStatus error:&prepareError];
                NSDictionary *eventObject = [self lastJSONObjectFromLines:prepareLines];
                dispatch_async(dispatch_get_main_queue(), ^{
                    if (prepareStatus != 0) { self.wechatSyncRunning = NO; self.statusLabel.stringValue = [self messageFromEvent:eventObject defaultMessage:(prepareError.localizedDescription ?: @"微信本地数据准备失败")]; self.statusLabel.textColor = NSColor.systemRedColor; return; }
                    NSError *launchError = nil;
                    if (![self startChatlogServiceForAccount:selectedAccountID binary:chatlogBinary error:&launchError]) { self.wechatSyncRunning = NO; self.statusLabel.stringValue = launchError.localizedDescription ?: @"本地微信数据服务启动失败"; self.statusLabel.textColor = NSColor.systemRedColor; return; }
                    self.statusLabel.stringValue = @"正在连接微信本地数据服务…";
                    NSTask *ownedService = self.chatlogServiceTask;
                    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
                        while (ownedService.running) {
                            if ([self process:ownedService.processIdentifier listensOnTCPPort:5030] && [self chatlogReadAPIIsReadyForAccount:selectedAccountID]) {
                                dispatch_async(dispatch_get_main_queue(), ^{ if (self.chatlogServiceTask == ownedService && self.wechatSyncRunning) [self finishWeChatSyncWithBinary:chatlogBinary accountID:selectedAccountID]; });
                                return;
                            }
                            [NSThread sleepForTimeInterval:0.25];
                        }
                        dispatch_async(dispatch_get_main_queue(), ^{ if (self.chatlogServiceTask == ownedService && self.wechatSyncRunning) { self.wechatSyncRunning = NO; self.statusLabel.stringValue = @"本地微信数据服务启动失败"; self.statusLabel.textColor = NSColor.systemRedColor; } });
                    });
                });
            });
        });
    });
}

- (void)saveDeepSeekKey:(id)sender {
    NSAlert *alert = [[NSAlert alloc] init];
    alert.messageText = @"保存 DeepSeek API Key";
    alert.informativeText = @"Key 会写入本机 macOS Keychain，不会保存到项目文件。";
    NSSecureTextField *field = [[NSSecureTextField alloc] initWithFrame:NSMakeRect(0, 0, 420, 24)];
    field.placeholderString = @"sk-...";
    alert.accessoryView = field;
    [alert addButtonWithTitle:@"保存"];
    [alert addButtonWithTitle:@"取消"];
    if ([alert runModal] != NSAlertFirstButtonReturn) return;
    NSString *key = [field.stringValue stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    if (!key.length) { NSBeep(); self.statusLabel.stringValue = @"DeepSeek Key 不能为空"; self.statusLabel.textColor = NSColor.systemRedColor; return; }
    int status = 0;
    NSError *error = nil;
    NSArray<NSString *> *lines = [self runAgentCommand:@[@"-m", @"agent_core.ai_cli", @"--db", self.currentDBPath, @"set-key"] stdinString:key terminationStatus:&status error:&error];
    NSDictionary *eventObject = [self lastJSONObjectFromLines:lines];
    if (status == 0) {
        self.statusLabel.stringValue = [self refreshAgentModels] ? @"模型连接完成 · 已同步官网模型列表" : @"DeepSeek Key 已保存，但模型列表读取失败";
        self.statusLabel.textColor = [self.statusLabel.stringValue hasPrefix:@"模型连接完成"] ? NSColor.systemGreenColor : NSColor.systemOrangeColor;
    } else {
        self.statusLabel.stringValue = [self messageFromEvent:eventObject defaultMessage:(error.localizedDescription ?: @"DeepSeek Key 保存失败")];
        self.statusLabel.textColor = NSColor.systemRedColor;
    }
}

- (NSDictionary *)agentExportSnapshot {
    NSInteger highIntent = 0;
    NSInteger activation = 0;
    NSInteger recent = 0;
    NSTimeInterval cutoff = NSDate.date.timeIntervalSince1970 - 30 * 86400;
    NSMutableDictionary<NSString *, NSNumber *> *distribution = [NSMutableDictionary dictionary];
    for (NSDictionary *lead in self.visibleLeads) {
        NSString *statusBand = [lead[@"status_label"] isKindOfClass:NSString.class] ? lead[@"status_label"] : @"";
        NSString *band = statusBand.length ? statusBand : (lead[@"intent_band"] ?: @"未分类");
        distribution[band] = @([distribution[band] integerValue] + 1);
        if ([band isEqualToString:@"高意向"]) highIntent += 1;
        if ([band isEqualToString:@"待激活"]) activation += 1;
        if ([lead[@"recent_contact_ts"] doubleValue] >= cutoff) recent += 1;
    }
    NSMutableDictionary *result = [self.lastAgentResult mutableCopy] ?: [NSMutableDictionary dictionary];
    result[@"schema_version"] = @"agent.query.v2";
    result[@"account_id"] = self.snapshot[@"account_id"] ?: @"";
    result[@"query"] = self.lastAgentQuestion ?: @"智能分析任务";
    result[@"run"] = @{ @"run_id": @"agent_query", @"model": self.agentModelPicker.titleOfSelectedItem ?: @"deepseek-v4-flash", @"prompt_version": @"smart_analysis_v2" };
    result[@"metrics"] = @{ @"customer_total": @(self.visibleLeads.count), @"high_intent": @(highIntent), @"activation_needed": @(activation), @"recent_leads": @(recent), @"distribution": distribution };
    result[@"leads"] = self.visibleLeads ?: @[];
    return result;
}

- (void)exportWorkbook:(id)sender {
    if (self.agentCommandRunning) { NSBeep(); self.statusLabel.stringValue = @"另一项操作正在进行"; return; }
    if (!self.lastAgentResult) { NSBeep(); return; }
    NSAlert *optionsAlert = [[NSAlert alloc] init];
    optionsAlert.messageText = @"导出自适应分析报告";
    optionsAlert.informativeText = [NSString stringWithFormat:@"将按“%@”自动组织结果、统计、待办和证据字段。", self.lastAgentResult[@"result_title"] ?: @"智能分析"];
    NSPopUpButton *formatPicker = [[NSPopUpButton alloc] initWithFrame:NSZeroRect pullsDown:NO];
    [formatPicker addItemsWithTitles:@[@"Excel 工作簿", @"PDF 报告", @"文字摘要"]];
    NSButton *(^check)(NSString *, BOOL) = ^NSButton *(NSString *title, BOOL state) {
        NSButton *button = [NSButton checkboxWithTitle:title target:nil action:nil]; button.state = state ? NSControlStateValueOn : NSControlStateValueOff; return button;
    };
    NSButton *evidenceCheck = check(@"包含原文证据与前后消息", YES);
    NSButton *statisticsCheck = check(@"包含精确互动统计", YES);
    NSButton *followupsCheck = check(@"包含后续分析建议", YES);
    NSButton *chartCheck = check(@"包含可编辑统计图表（Excel）", YES);
    NSStackView *stack = [NSStackView stackViewWithViews:@[formatPicker, evidenceCheck, statisticsCheck, followupsCheck, chartCheck]];
    stack.orientation = NSUserInterfaceLayoutOrientationVertical; stack.alignment = NSLayoutAttributeLeading; stack.spacing = 8; stack.frame = NSMakeRect(0, 0, 420, 142);
    [formatPicker.widthAnchor constraintEqualToConstant:220].active = YES;
    optionsAlert.accessoryView = stack; [optionsAlert addButtonWithTitle:@"继续"]; [optionsAlert addButtonWithTitle:@"取消"];
    if ([optionsAlert runModal] != NSAlertFirstButtonReturn) return;
    NSInteger format = formatPicker.indexOfSelectedItem;
    NSString *extension = format == 0 ? @"xlsx" : (format == 1 ? @"pdf" : @"txt");
    NSSavePanel *panel = [NSSavePanel savePanel]; panel.nameFieldStringValue = [NSString stringWithFormat:@"%@.%@", self.lastAgentResult[@"result_title"] ?: @"智能分析报告", extension]; panel.allowedContentTypes = @[];
    if ([panel runModal] != NSModalResponseOK) return;
    NSMutableDictionary *exportSnapshot = [[self agentExportSnapshot] mutableCopy];
    NSDictionary *reportOptions = @{
        @"include_evidence": @(evidenceCheck.state == NSControlStateValueOn),
        @"include_statistics": @(statisticsCheck.state == NSControlStateValueOn),
        @"include_followups": @(followupsCheck.state == NSControlStateValueOn),
        @"include_chart": @(chartCheck.state == NSControlStateValueOn),
    };
    exportSnapshot[@"report_options"] = reportOptions;
    NSString *outputPath = panel.URL.path;
    if (format == 1) {
        self.agentCommandRunning = YES; self.statusLabel.stringValue = @"正在生成 PDF…"; self.statusLabel.textColor = NSColor.systemOrangeColor;
        self.agentActivityIndicator.hidden = NO; [self.agentActivityIndicator startAnimation:nil];
        dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
            BOOL written = WriteAnalysisPDF(exportSnapshot, outputPath, reportOptions);
            dispatch_async(dispatch_get_main_queue(), ^{ self.agentCommandRunning = NO; [self.agentActivityIndicator stopAnimation:nil]; self.agentActivityIndicator.hidden = YES; self.statusLabel.stringValue = written ? @"PDF 已导出" : @"PDF 导出失败"; self.statusLabel.textColor = written ? NSColor.systemGreenColor : NSColor.systemRedColor; });
        });
        return;
    }
    if (format == 2) {
        self.agentCommandRunning = YES; self.statusLabel.stringValue = @"正在生成文字摘要…"; self.statusLabel.textColor = NSColor.systemOrangeColor;
        dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
            NSMutableString *text = [NSMutableString stringWithFormat:@"%@\n\n任务：%@\n\n%@\n", exportSnapshot[@"result_title"] ?: @"智能分析报告", exportSnapshot[@"query"] ?: @"", exportSnapshot[@"answer"] ?: @""];
            for (NSDictionary *section in exportSnapshot[@"sections"] ?: @[]) { [text appendFormat:@"\n%@（置信度 %@%%）\n%@\n支持证据：%@\n反例证据：%@\n", section[@"title"] ?: @"分析", section[@"confidence"] ?: @0, section[@"content"] ?: @"", [section[@"evidence_ids"] componentsJoinedByString:@"、"] ?: @"", [section[@"counter_evidence_ids"] componentsJoinedByString:@"、"] ?: @""]; }
            NSArray *structuredItems = [exportSnapshot[@"structured_items"] isKindOfClass:NSArray.class] ? exportSnapshot[@"structured_items"] : @[];
            if (structuredItems.count) { [text appendString:@"\n时间线与待办\n"]; for (NSDictionary *item in structuredItems) [text appendFormat:@"• %@  %@  %@  %@\n", item[@"date"] ?: @"", item[@"status"] ?: @"", item[@"subject"] ?: @"", item[@"content"] ?: @""]; }
            if ([reportOptions[@"include_statistics"] boolValue]) { [text appendString:@"\n精确互动统计\n"]; for (NSDictionary *lead in exportSnapshot[@"leads"] ?: @[]) { NSDictionary *stats = [lead[@"conversation_stats"] isKindOfClass:NSDictionary.class] ? lead[@"conversation_stats"] : @{}; [text appendFormat:@"%@：共 %@ 条（对方 %@ / 我方 %@），%@ 个活跃日，对方中位回复 %@ 分钟，我方 %@ 分钟\n", lead[@"display_name"] ?: @"联系人", stats[@"message_count"] ?: @0, stats[@"incoming_count"] ?: @0, stats[@"outgoing_count"] ?: @0, stats[@"active_days"] ?: @0, stats[@"their_median_response_minutes"] ?: @"—", stats[@"my_median_response_minutes"] ?: @"—"]; } }
            if ([reportOptions[@"include_evidence"] boolValue]) { [text appendString:@"\n证据明细\n"]; NSMutableSet *seen = [NSMutableSet set]; for (NSDictionary *lead in exportSnapshot[@"leads"] ?: @[]) { for (NSDictionary *evidence in lead[@"evidence"] ?: @[]) { NSString *evidenceID = evidence[@"evidence_id"] ?: @""; if ([seen containsObject:evidenceID]) continue; [seen addObject:evidenceID]; [text appendFormat:@"\n%@  %@  [%@] %@\n%@\n", evidenceID, evidence[@"time"] ?: @"", evidence[@"direction"] ?: @"", evidence[@"sender"] ?: @"", evidence[@"content"] ?: @""]; NSArray *context = [evidence[@"context"] isKindOfClass:NSArray.class] ? evidence[@"context"] : @[]; for (NSDictionary *item in context) [text appendFormat:@"%@ %@ [%@] %@：%@\n", [item[@"is_target"] boolValue] ? @"▶" : @" ", item[@"time"] ?: @"", item[@"direction"] ?: @"", item[@"sender"] ?: @"", item[@"content"] ?: @""]; } } }
            NSArray *limitations = [exportSnapshot[@"limitations"] isKindOfClass:NSArray.class] ? exportSnapshot[@"limitations"] : @[]; if (limitations.count) { [text appendString:@"\n边界说明\n"]; for (NSString *item in limitations) [text appendFormat:@"• %@\n", item]; }
            if ([reportOptions[@"include_followups"] boolValue]) for (NSString *item in exportSnapshot[@"suggested_followups"] ?: @[]) [text appendFormat:@"\n建议继续：%@", item];
            NSError *writeError = nil; BOOL written = [text writeToFile:outputPath atomically:YES encoding:NSUTF8StringEncoding error:&writeError];
            dispatch_async(dispatch_get_main_queue(), ^{ self.agentCommandRunning = NO; self.statusLabel.stringValue = written ? @"文字摘要已导出" : (writeError.localizedDescription ?: @"文字摘要导出失败"); self.statusLabel.textColor = written ? NSColor.systemGreenColor : NSColor.systemRedColor; });
        });
        return;
    }
    NSError *serializationError = nil;
    NSData *snapshotData = [NSJSONSerialization dataWithJSONObject:exportSnapshot options:0 error:&serializationError];
    if (!snapshotData) { self.statusLabel.stringValue = serializationError.localizedDescription ?: @"无法准备导出数据"; self.statusLabel.textColor = NSColor.systemRedColor; return; }
    NSString *resourcePath = [NSBundle mainBundle].resourcePath;
    self.agentCommandRunning = YES; self.statusLabel.stringValue = @"正在生成 Excel…"; self.statusLabel.textColor = NSColor.systemOrangeColor;
    self.agentActivityIndicator.hidden = NO; [self.agentActivityIndicator startAnimation:nil];
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        NSTask *task = [[NSTask alloc] init]; self.activeAgentTask = task;
        task.executableURL = [NSURL fileURLWithPath:[resourcePath stringByAppendingPathComponent:@"Node/node"]];
        task.arguments = @[[resourcePath stringByAppendingPathComponent:@"Export/build_lead_workbook.mjs"], @"-", outputPath];
        NSPipe *pipe = [NSPipe pipe]; NSPipe *inputPipe = [NSPipe pipe]; task.standardOutput = pipe; task.standardError = pipe; task.standardInput = inputPipe;
        NSError *launchError = nil;
        if (![task launchAndReturnError:&launchError]) { dispatch_async(dispatch_get_main_queue(), ^{ self.activeAgentTask = nil; self.agentCommandRunning = NO; [self.agentActivityIndicator stopAnimation:nil]; self.agentActivityIndicator.hidden = YES; self.statusLabel.stringValue = launchError.localizedDescription ?: @"Excel 导出失败"; self.statusLabel.textColor = NSColor.systemRedColor; }); return; }
        [inputPipe.fileHandleForWriting writeData:snapshotData]; [inputPipe.fileHandleForWriting closeFile];
        NSData *outputData = [self drainPipe:pipe whileTaskRuns:task]; NSString *output = [[NSString alloc] initWithData:outputData encoding:NSUTF8StringEncoding] ?: @""; int exportStatus = task.terminationStatus;
        dispatch_async(dispatch_get_main_queue(), ^{ self.activeAgentTask = nil; self.agentCommandRunning = NO; [self.agentActivityIndicator stopAnimation:nil]; self.agentActivityIndicator.hidden = YES; self.statusLabel.stringValue = exportStatus == 0 ? @"Excel 已导出" : (output.length ? output : @"Excel 导出失败"); self.statusLabel.textColor = exportStatus == 0 ? NSColor.systemGreenColor : NSColor.systemRedColor; });
    });
}

- (void)applicationWillTerminate:(NSNotification *)notification {
    if (self.activeAgentTask.running) [self.activeAgentTask terminate];
    self.activeAgentTask = nil;
    [self stopChatlogService];
}

- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)sender { return YES; }
@end

static BOOL WriteWindowPNG(NSWindow *window, NSString *path) {
    NSView *view = window.contentView;
    NSBitmapImageRep *rep = [view bitmapImageRepForCachingDisplayInRect:view.bounds];
    if (!rep) return NO;
    [view cacheDisplayInRect:view.bounds toBitmapImageRep:rep];
    NSData *png = [rep representationUsingType:NSBitmapImageFileTypePNG properties:@{}];
    return [png writeToFile:path atomically:YES];
}

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        PrintDiagnostic(@"app_launch", @"passed", @"NATIVE_WORKSPACE_APP_LAUNCHED", @"Native customer activation workspace launched.");
        NSApplication *application = NSApplication.sharedApplication;
        application.activationPolicy = NSApplicationActivationPolicyRegular;
        application.appearance = [NSAppearance appearanceNamed:NSAppearanceNameAqua];
        WorkspaceController *controller = [[WorkspaceController alloc] init];
        NSString *previewPath = nil;
        NSString *agentPreviewPath = nil;
        NSString *agentResultPreviewPath = nil;
        NSString *dashboardPreviewPath = nil;
        NSString *searchPreviewPath = nil;
        NSString *reportPDFPath = nil;
        BOOL launchSmoke = NO;
        BOOL uiSmoke = NO;
        for (int index = 1; index < argc; index++) {
            NSString *argument = [NSString stringWithUTF8String:argv[index]];
            if ([argument isEqualToString:@"--snapshot"] && index + 1 < argc) controller.snapshotPath = [NSString stringWithUTF8String:argv[++index]];
            else if ([argument isEqualToString:@"--render-preview"] && index + 1 < argc) previewPath = [NSString stringWithUTF8String:argv[++index]];
            else if ([argument isEqualToString:@"--render-agent-preview"] && index + 1 < argc) agentPreviewPath = [NSString stringWithUTF8String:argv[++index]];
            else if ([argument isEqualToString:@"--render-agent-result-preview"] && index + 1 < argc) agentResultPreviewPath = [NSString stringWithUTF8String:argv[++index]];
            else if ([argument isEqualToString:@"--render-dashboard-preview"] && index + 1 < argc) dashboardPreviewPath = [NSString stringWithUTF8String:argv[++index]];
            else if ([argument isEqualToString:@"--render-search-preview"] && index + 1 < argc) searchPreviewPath = [NSString stringWithUTF8String:argv[++index]];
            else if ([argument isEqualToString:@"--render-report-pdf"] && index + 1 < argc) reportPDFPath = [NSString stringWithUTF8String:argv[++index]];
            else if ([argument isEqualToString:@"--smoke"]) launchSmoke = YES;
            else if ([argument isEqualToString:@"--ui-smoke"]) uiSmoke = YES;
        }
        if (reportPDFPath.length) {
            NSDictionary *sample = @{
                @"result_title": @"杨凯互动画像与跟进建议", @"query": @"杨凯常说什么，他是怎样的人？",
                @"answer": @"从当前聊天样本看，杨凯表达直接、重视执行与交付，也会主动确认关键节点。",
                @"sections": @[
                    @{@"title": @"沟通方式", @"content": @"常用简短确认句，讨论任务时直接给出下一步。", @"confidence": @92, @"evidence_ids": @[@"e_001"]},
                    @{@"title": @"关注重点", @"content": @"更频繁关注进度、结果和时间安排。", @"confidence": @86, @"evidence_ids": @[@"e_002"]},
                ],
                @"leads": @[@{@"display_name": @"杨凯", @"conversation_stats": @{@"message_count": @1524, @"incoming_count": @781, @"outgoing_count": @743, @"active_days": @208, @"their_median_response_minutes": @8.5, @"my_median_response_minutes": @11.0}, @"evidence": @[
                    @{@"evidence_id": @"e_001", @"time": @"2026-08-03 10:20", @"direction": @"对方", @"sender": @"杨凯", @"content": @"先把这件事做完，下午我来确认结果。"},
                    @{@"evidence_id": @"e_002", @"time": @"2026-08-05 16:42", @"direction": @"对方", @"sender": @"杨凯", @"content": @"这个节点什么时候能交付？"},
                ]}],
                @"structured_items": @[@{@"date": @"2026-08-03", @"status": @"已确认", @"subject": @"项目推进", @"content": @"下午确认结果"}],
                @"limitations": @[@"结论仅基于当前同步的双向聊天样本。"],
                @"suggested_followups": @[@"比较最近半年与上一阶段的沟通变化", @"提取尚未完成的承诺事项"],
            };
            NSDictionary *options = @{@"include_evidence": @YES, @"include_statistics": @YES, @"include_followups": @YES, @"include_chart": @YES};
            BOOL written = WriteAnalysisPDF(sample, reportPDFPath, options);
            PrintDiagnostic(@"report_pdf", written ? @"passed" : @"failed", written ? @"ANALYSIS_PDF_WRITTEN" : @"ANALYSIS_PDF_FAILED", reportPDFPath);
            return written ? 0 : 1;
        }
        application.delegate = controller;
        [application finishLaunching];
        [controller applicationDidFinishLaunching:[NSNotification notificationWithName:NSApplicationDidFinishLaunchingNotification object:application]];
        if (agentPreviewPath.length) {
            NSDictionary<NSString *, NSString *> *progress = @{
                @"planning": @"理解任务与时间范围",
                @"retrieval": @"证据召回 · 扫描 276 个对话，召回 231 个候选（183 天）",
                @"analysis": @"语义复核 · 已完成 5/15 批，共 231 个候选",
            };
            [controller setAgentTranscriptContent:[controller agentProgressTranscriptForQuestion:@"找出近半年和我有创业讨论的人" progress:progress activeStage:@"analysis"]];
            controller.statusLabel.stringValue = @"语义复核 · 5/15 批";
            controller.statusLabel.textColor = NSColor.systemOrangeColor;
            controller.agentActivityIndicator.hidden = NO;
            [controller.agentActivityIndicator startAnimation:nil];
            [controller.window.contentView layoutSubtreeIfNeeded];
            [controller.window displayIfNeeded];
            BOOL written = WriteWindowPNG(controller.window, agentPreviewPath);
            PrintDiagnostic(@"agent_preview", written ? @"passed" : @"failed", written ? @"NATIVE_AGENT_PREVIEW_WRITTEN" : @"NATIVE_AGENT_PREVIEW_FAILED", agentPreviewPath);
            return written ? 0 : 1;
        }
        if (agentResultPreviewPath.length) {
            controller.lastAgentResult = @{
                @"sections": @[
                    @{@"title": @"沟通方式", @"content": @"表达直接，会主动确认任务节点和交付结果。", @"confidence": @92, @"evidence_ids": @[@"e_001"], @"counter_evidence_ids": @[]},
                    @{@"title": @"压力下的变化", @"content": @"时间紧张时句子更短，追问频率上升，但仍聚焦事情本身。", @"confidence": @84, @"evidence_ids": @[@"e_002"], @"counter_evidence_ids": @[@"e_003"]},
                ],
                @"structured_items": @[@{@"date": @"2026-08-03", @"status": @"待确认", @"content": @"下午确认交付结果"}],
                @"limitations": @[@"结论仅基于当前已同步的双向聊天记录。"],
                @"suggested_followups": @[@"比较最近半年与上一阶段的沟通变化", @"提取尚未完成的承诺事项"],
            };
            controller.visibleLeads = @[@{
                @"display_name": @"杨凯",
                @"conversation_stats": @{@"message_count": @1524, @"active_days": @208, @"their_median_response_minutes": @8.5, @"my_median_response_minutes": @11.0},
                @"evidence": @[
                    @{@"evidence_id": @"e_001", @"time": @"2026-08-03 10:20", @"direction": @"对方", @"sender": @"杨凯", @"content": @"先把这件事做完，下午我来确认结果。", @"context": @[@{@"time": @"2026-08-03 10:18", @"direction": @"我方", @"sender": @"我", @"content": @"我们先处理当前版本。", @"is_target": @NO}, @{@"time": @"2026-08-03 10:20", @"direction": @"对方", @"sender": @"杨凯", @"content": @"先把这件事做完，下午我来确认结果。", @"is_target": @YES}]},
                    @{@"evidence_id": @"e_002", @"time": @"2026-08-05 16:42", @"direction": @"对方", @"sender": @"杨凯", @"content": @"这个节点什么时候能交付？", @"context": @[]},
                    @{@"evidence_id": @"e_003", @"time": @"2026-08-06 09:12", @"direction": @"对方", @"sender": @"杨凯", @"content": @"不着急，先把问题查清楚。", @"context": @[]},
                ],
            }];
            controller.allLeads = controller.visibleLeads;
            NSArray *trace = @[@"理解任务 · 联系人杨凯，分析沟通方式", @"证据召回 · 扫描 276 个对话，锁定 1 位", @"语义复核 · 6 批，确认 1 位", @"覆盖审计 · 找回 0 位，移除 0 位"];
            [controller setAgentTranscriptContent:[controller agentCompletedTranscriptForQuestion:@"杨凯在压力下的沟通方式有什么变化？" trace:trace reply:@"压力增加时，他会缩短句子并增加进度确认，但没有足够证据支持他会转向情绪化表达。" summary:@"" resultTitle:@"杨凯的压力沟通画像" resultCount:1]];
            controller.statusLabel.stringValue = @"完成 · 杨凯的压力沟通画像";
            controller.statusLabel.textColor = NSColor.systemGreenColor;
            [controller.window.contentView layoutSubtreeIfNeeded];
            [controller.window displayIfNeeded];
            BOOL written = WriteWindowPNG(controller.window, agentResultPreviewPath);
            PrintDiagnostic(@"agent_result_preview", written ? @"passed" : @"failed", written ? @"NATIVE_AGENT_RESULT_PREVIEW_WRITTEN" : @"NATIVE_AGENT_RESULT_PREVIEW_FAILED", agentResultPreviewPath);
            return written ? 0 : 1;
        }
        if (searchPreviewPath.length) {
            [controller showMessageSearchView];
            [controller.window.contentView layoutSubtreeIfNeeded];
            [controller.window displayIfNeeded];
            BOOL valid = controller.messageSearchSessions.count > 0 && WriteWindowPNG(controller.window, searchPreviewPath);
            PrintDiagnostic(@"search_preview", valid ? @"passed" : @"failed", valid ? @"NATIVE_SEARCH_PREVIEW_WRITTEN" : @"NATIVE_SEARCH_PREVIEW_FAILED", searchPreviewPath);
            return valid ? 0 : 1;
        }
        if (dashboardPreviewPath.length) {
            [controller showAnalyticsDashboardView];
            NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:240];
            while (controller.dashboardLoading && deadline.timeIntervalSinceNow > 0) {
                [NSRunLoop.currentRunLoop runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.05]];
            }
            [controller.window displayIfNeeded];
            BOOL written = WriteWindowPNG(controller.window, dashboardPreviewPath);
            [controller.dashboardPageScroll.contentView scrollToPoint:NSMakePoint(0, 1030)]; [controller.dashboardPageScroll reflectScrolledClipView:controller.dashboardPageScroll.contentView]; [controller.window displayIfNeeded];
            NSString *bottomPath = [dashboardPreviewPath stringByAppendingString:@".bottom.png"];
            BOOL bottomWritten = WriteWindowPNG(controller.window, bottomPath);
            BOOL valid = written && bottomWritten && controller.dashboardGroups.count > 0 && controller.dashboardTrendChart.points.count > 0 && controller.dashboardTypeChart.points.count > 0 && controller.dashboardHourChart.points.count == 24 && controller.dashboardSpeakerTable.numberOfRows > 0 && controller.dashboardDatabaseTable.numberOfRows > 0;
            PrintDiagnostic(@"dashboard_preview", valid ? @"passed" : @"failed", valid ? @"NATIVE_DASHBOARD_PREVIEW_WRITTEN" : @"NATIVE_DASHBOARD_PREVIEW_FAILED", dashboardPreviewPath);
            return valid ? 0 : 1;
        }
        if (previewPath.length) {
            [controller.window displayIfNeeded];
            BOOL written = WriteWindowPNG(controller.window, previewPath);
            PrintDiagnostic(@"ui_preview", written ? @"passed" : @"failed", written ? @"NATIVE_UI_PREVIEW_WRITTEN" : @"NATIVE_UI_PREVIEW_FAILED", previewPath);
            return written ? 0 : 1;
        }
        if (launchSmoke || uiSmoke) {
            BOOL valid = controller.window != nil && (!uiSmoke || (controller.allLeads.count > 0 && controller.agentTranscript != nil));
            PrintDiagnostic(uiSmoke ? @"ui_smoke" : @"app_smoke", valid ? @"passed" : @"failed", valid ? (uiSmoke ? @"NATIVE_WORKSPACE_UI_OK" : @"NATIVE_APP_SHELL_OK") : @"NATIVE_WORKSPACE_UI_INVALID", valid ? (uiSmoke ? @"Agent task workspace loaded." : @"Native AppKit shell loaded.") : @"Workspace did not load the supplied published snapshot.");
            return valid ? 0 : 1;
        }
        [application run];
    }
    return 0;
}
