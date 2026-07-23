#import <Cocoa/Cocoa.h>

#ifndef PROJECT_DIR
#define PROJECT_DIR "."
#endif

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

static NSView *Card(NSString *title, NSString *value, NSColor *accent) {
    NSView *card = [[NSView alloc] initWithFrame:NSZeroRect];
    card.wantsLayer = YES;
    card.layer.backgroundColor = NSColor.whiteColor.CGColor;
    card.layer.cornerRadius = 12;
    card.layer.borderColor = [NSColor colorWithWhite:0.88 alpha:1].CGColor;
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

@class WorkspaceController;

@interface AttachmentDropField : NSTextField
@property(nonatomic, weak) WorkspaceController *workspaceController;
@end

@interface WorkspaceController : NSObject <NSApplicationDelegate, NSTableViewDataSource, NSTableViewDelegate, NSSearchFieldDelegate>
@property NSDictionary *snapshot;
@property NSArray<NSDictionary *> *allLeads;
@property NSArray<NSDictionary *> *visibleLeads;
@property NSWindow *window;
@property NSTableView *table;
@property NSSearchField *search;
@property NSPopUpButton *bandFilter;
@property NSTextField *detailTitle;
@property NSTextField *detailMeta;
@property NSTextView *detailText;
@property NSTextView *draftText;
@property NSTextField *statusLabel;
@property NSTextField *batchStatusLabel;
@property NSMutableArray<NSString *> *attachmentPaths;
@property NSString *currentBatchID;
@property NSString *snapshotPath;
@property NSString *startupError;
- (void)setAttachmentURLs:(NSArray<NSURL *> *)urls;
@end

@implementation AttachmentDropField
- (instancetype)initWithFrame:(NSRect)frameRect {
    self = [super initWithFrame:frameRect];
    if (self) {
        [self registerForDraggedTypes:@[NSPasteboardTypeFileURL]];
        self.editable = NO;
        self.selectable = NO;
        self.bordered = NO;
        self.drawsBackground = YES;
        self.backgroundColor = [NSColor colorWithRed:1.0 green:0.98 blue:0.90 alpha:1];
        self.textColor = [NSColor colorWithWhite:0.35 alpha:1];
        self.font = [NSFont systemFontOfSize:11];
        self.alignment = NSTextAlignmentCenter;
        self.wantsLayer = YES;
        self.layer.cornerRadius = 6;
        self.layer.borderWidth = 1;
        self.layer.borderColor = NSColor.systemOrangeColor.CGColor;
    }
    return self;
}
- (NSDragOperation)draggingEntered:(id<NSDraggingInfo>)sender {
    return NSDragOperationCopy;
}
- (BOOL)performDragOperation:(id<NSDraggingInfo>)sender {
    NSArray<NSURL *> *urls = [sender.draggingPasteboard readObjectsForClasses:@[NSURL.class] options:@{NSPasteboardURLReadingFileURLsOnlyKey: @YES}];
    if (!urls.count) return NO;
    [self.workspaceController setAttachmentURLs:urls];
    return YES;
}
@end

@implementation WorkspaceController

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
    NSString *pythonRoot = [[NSBundle mainBundle].resourcePath stringByAppendingPathComponent:@"Python"];
    NSTask *task = [[NSTask alloc] init];
    task.executableURL = [NSURL fileURLWithPath:@"/usr/bin/python3"];
    task.arguments = @[@"-m", @"agent_core.workspace_cli", @"--db", db, @"snapshot"];
    NSMutableDictionary *environment = [NSProcessInfo.processInfo.environment mutableCopy];
    environment[@"PYTHONPATH"] = pythonRoot;
    task.environment = environment;
    NSPipe *pipe = [NSPipe pipe];
    task.standardOutput = pipe;
    task.standardError = pipe;
    if (![task launchAndReturnError:error]) return nil;
    [task waitUntilExit];
    NSData *data = [pipe.fileHandleForReading readDataToEndOfFile];
    if (task.terminationStatus != 0) {
        NSString *message = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] ?: @"无法读取分析快照";
        if (error) *error = [NSError errorWithDomain:@"WeChatSalesAgent" code:task.terminationStatus userInfo:@{NSLocalizedDescriptionKey: message}];
        return nil;
    }
    return [NSJSONSerialization JSONObjectWithData:data options:0 error:error];
}

- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    NSError *error = nil;
    self.snapshot = self.snapshotPath.length ? [self loadSnapshotAtPath:self.snapshotPath error:&error] : [self loadCurrentSnapshot:&error];
    if (!self.snapshot) {
        self.startupError = error.localizedDescription ?: @"尚无已发布的客户分析，请先配置 DeepSeek 并完成分析。";
        self.snapshot = @{ @"metrics": @{ @"customer_total": @0, @"high_intent": @0, @"activation_needed": @0, @"recent_leads": @0, @"distribution": @{} }, @"leads": @[], @"run": @{}, @"account_id": @"未连接" };
    }
    self.allLeads = self.snapshot[@"leads"] ?: @[];
    self.visibleLeads = self.allLeads;
    self.attachmentPaths = [NSMutableArray array];
    [self buildWindow];
    [self.window makeKeyAndOrderFront:nil];
    [NSApp activateIgnoringOtherApps:YES];
}

- (void)buildWindow {
    self.window = [[NSWindow alloc] initWithContentRect:NSMakeRect(0, 0, 1360, 820)
        styleMask:(NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable)
        backing:NSBackingStoreBuffered defer:NO];
    self.window.title = @"微信客户激活 Agent";
    self.window.minSize = NSMakeSize(1180, 720);
    [self.window center];
    NSView *root = self.window.contentView;
    root.wantsLayer = YES;
    root.layer.backgroundColor = [NSColor colorWithRed:0.96 green:0.97 blue:0.99 alpha:1].CGColor;

    NSView *sidebar = [[NSView alloc] initWithFrame:NSZeroRect];
    sidebar.wantsLayer = YES;
    sidebar.layer.backgroundColor = [NSColor colorWithRed:0.055 green:0.09 blue:0.18 alpha:1].CGColor;
    [root addSubview:sidebar];
    sidebar.translatesAutoresizingMaskIntoConstraints = NO;
    [NSLayoutConstraint activateConstraints:@[
        [sidebar.leadingAnchor constraintEqualToAnchor:root.leadingAnchor], [sidebar.topAnchor constraintEqualToAnchor:root.topAnchor],
        [sidebar.bottomAnchor constraintEqualToAnchor:root.bottomAnchor], [sidebar.widthAnchor constraintEqualToConstant:210]
    ]];
    NSTextField *brand = Label(@"客户激活 Agent", 19, NSColor.whiteColor, YES);
    NSTextField *tagline = Label(@"微信销售线索工作台", 11, [NSColor colorWithWhite:0.65 alpha:1], NO);
    [sidebar addSubview:brand]; [sidebar addSubview:tagline];
    brand.translatesAutoresizingMaskIntoConstraints = tagline.translatesAutoresizingMaskIntoConstraints = NO;
    [NSLayoutConstraint activateConstraints:@[
        [brand.leadingAnchor constraintEqualToAnchor:sidebar.leadingAnchor constant:22], [brand.topAnchor constraintEqualToAnchor:sidebar.topAnchor constant:28],
        [tagline.leadingAnchor constraintEqualToAnchor:brand.leadingAnchor], [tagline.topAnchor constraintEqualToAnchor:brand.bottomAnchor constant:5]
    ]];
    NSButton *dashboardButton = [NSButton buttonWithTitle:@"▦  仪表盘与客户表" target:nil action:nil];
    dashboardButton.bordered = NO; dashboardButton.alignment = NSTextAlignmentLeft; dashboardButton.font = [NSFont boldSystemFontOfSize:14];
    dashboardButton.contentTintColor = NSColor.whiteColor; dashboardButton.wantsLayer = YES; dashboardButton.layer.backgroundColor = [NSColor colorWithRed:0.12 green:0.32 blue:0.82 alpha:1].CGColor; dashboardButton.layer.cornerRadius = 8;
    [sidebar addSubview:dashboardButton]; dashboardButton.translatesAutoresizingMaskIntoConstraints = NO;
    [NSLayoutConstraint activateConstraints:@[
        [dashboardButton.leadingAnchor constraintEqualToAnchor:sidebar.leadingAnchor constant:14], [dashboardButton.trailingAnchor constraintEqualToAnchor:sidebar.trailingAnchor constant:-14],
        [dashboardButton.topAnchor constraintEqualToAnchor:tagline.bottomAnchor constant:34], [dashboardButton.heightAnchor constraintEqualToConstant:42]
    ]];
    NSTextField *privacy = Label(@"原始聊天默认仅在本机处理", 11, [NSColor colorWithWhite:0.55 alpha:1], NO);
    [sidebar addSubview:privacy]; privacy.translatesAutoresizingMaskIntoConstraints = NO;
    [NSLayoutConstraint activateConstraints:@[[privacy.leadingAnchor constraintEqualToAnchor:sidebar.leadingAnchor constant:22], [privacy.bottomAnchor constraintEqualToAnchor:sidebar.bottomAnchor constant:-24]]];

    NSView *content = [[NSView alloc] initWithFrame:NSZeroRect];
    [root addSubview:content]; content.translatesAutoresizingMaskIntoConstraints = NO;
    [NSLayoutConstraint activateConstraints:@[
        [content.leadingAnchor constraintEqualToAnchor:sidebar.trailingAnchor], [content.trailingAnchor constraintEqualToAnchor:root.trailingAnchor],
        [content.topAnchor constraintEqualToAnchor:root.topAnchor], [content.bottomAnchor constraintEqualToAnchor:root.bottomAnchor]
    ]];

    NSTextField *title = Label(@"线索客户工作台", 26, [NSColor colorWithRed:0.06 green:0.10 blue:0.20 alpha:1], YES);
    NSString *account = self.snapshot[@"account_id"] ?: @"";
    NSTextField *subtitle = Label([NSString stringWithFormat:@"账号 %@ · 所有判断均可回溯到真实聊天证据", account], 12, [NSColor colorWithWhite:0.42 alpha:1], NO);
    self.statusLabel = Label(self.startupError.length ? @"分析未就绪" : @"分析已发布", 12, self.startupError.length ? NSColor.systemRedColor : NSColor.systemGreenColor, YES);
    NSButton *exportButton = [NSButton buttonWithTitle:@"导出 Excel" target:self action:@selector(exportWorkbook:)];
    exportButton.bezelStyle = NSBezelStyleTexturedRounded;
    exportButton.contentTintColor = NSColor.systemBlueColor;
    NSButton *attachButton = [NSButton buttonWithTitle:@"选择附件" target:self action:@selector(chooseAttachments:)];
    attachButton.bezelStyle = NSBezelStyleTexturedRounded;
    NSButton *batchButton = [NSButton buttonWithTitle:@"创建发送批次" target:self action:@selector(createSendBatch:)];
    batchButton.bezelStyle = NSBezelStyleTexturedRounded;
    batchButton.contentTintColor = NSColor.systemOrangeColor;
    NSButton *dispatchButton = [NSButton buttonWithTitle:@"执行发送" target:self action:@selector(dispatchSendBatch:)];
    dispatchButton.bezelStyle = NSBezelStyleTexturedRounded;
    dispatchButton.contentTintColor = NSColor.systemRedColor;
    [content addSubview:title]; [content addSubview:subtitle]; [content addSubview:self.statusLabel]; [content addSubview:exportButton]; [content addSubview:attachButton]; [content addSubview:batchButton]; [content addSubview:dispatchButton];
    for (NSView *view in @[title, subtitle, self.statusLabel, exportButton, attachButton, batchButton, dispatchButton]) view.translatesAutoresizingMaskIntoConstraints = NO;
    [NSLayoutConstraint activateConstraints:@[
        [title.leadingAnchor constraintEqualToAnchor:content.leadingAnchor constant:28], [title.topAnchor constraintEqualToAnchor:content.topAnchor constant:24],
        [subtitle.leadingAnchor constraintEqualToAnchor:title.leadingAnchor], [subtitle.topAnchor constraintEqualToAnchor:title.bottomAnchor constant:4],
        [exportButton.trailingAnchor constraintEqualToAnchor:content.trailingAnchor constant:-28], [exportButton.centerYAnchor constraintEqualToAnchor:title.centerYAnchor],
        [dispatchButton.trailingAnchor constraintEqualToAnchor:exportButton.leadingAnchor constant:-8], [dispatchButton.centerYAnchor constraintEqualToAnchor:title.centerYAnchor],
        [batchButton.trailingAnchor constraintEqualToAnchor:dispatchButton.leadingAnchor constant:-8], [batchButton.centerYAnchor constraintEqualToAnchor:title.centerYAnchor],
        [attachButton.trailingAnchor constraintEqualToAnchor:batchButton.leadingAnchor constant:-8], [attachButton.centerYAnchor constraintEqualToAnchor:title.centerYAnchor],
        [self.statusLabel.trailingAnchor constraintEqualToAnchor:attachButton.leadingAnchor constant:-18], [self.statusLabel.centerYAnchor constraintEqualToAnchor:title.centerYAnchor]
    ]];

    NSDictionary *metrics = self.snapshot[@"metrics"];
    NSStackView *cards = [[NSStackView alloc] initWithFrame:NSZeroRect];
    cards.orientation = NSUserInterfaceLayoutOrientationHorizontal; cards.spacing = 12; cards.distribution = NSStackViewDistributionFillEqually;
    [cards addArrangedSubview:Card(@"线索客户", [metrics[@"customer_total"] stringValue], [NSColor colorWithRed:0.08 green:0.19 blue:0.45 alpha:1])];
    [cards addArrangedSubview:Card(@"高意向", [metrics[@"high_intent"] stringValue], NSColor.systemGreenColor)];
    [cards addArrangedSubview:Card(@"待激活", [metrics[@"activation_needed"] stringValue], NSColor.systemOrangeColor)];
    [cards addArrangedSubview:Card(@"近 30 天联系", [metrics[@"recent_leads"] stringValue], NSColor.systemBlueColor)];
    [content addSubview:cards]; cards.translatesAutoresizingMaskIntoConstraints = NO;
    [NSLayoutConstraint activateConstraints:@[
        [cards.leadingAnchor constraintEqualToAnchor:title.leadingAnchor], [cards.trailingAnchor constraintEqualToAnchor:content.trailingAnchor constant:-28],
        [cards.topAnchor constraintEqualToAnchor:subtitle.bottomAnchor constant:22], [cards.heightAnchor constraintEqualToConstant:92]
    ]];

    NSView *workspace = [[NSView alloc] initWithFrame:NSZeroRect];
    workspace.wantsLayer = YES; workspace.layer.backgroundColor = NSColor.whiteColor.CGColor; workspace.layer.cornerRadius = 12;
    workspace.layer.borderColor = [NSColor colorWithWhite:0.88 alpha:1].CGColor; workspace.layer.borderWidth = 1;
    [content addSubview:workspace]; workspace.translatesAutoresizingMaskIntoConstraints = NO;
    [NSLayoutConstraint activateConstraints:@[
        [workspace.leadingAnchor constraintEqualToAnchor:title.leadingAnchor], [workspace.trailingAnchor constraintEqualToAnchor:content.trailingAnchor constant:-28],
        [workspace.topAnchor constraintEqualToAnchor:cards.bottomAnchor constant:16], [workspace.bottomAnchor constraintEqualToAnchor:content.bottomAnchor constant:-24]
    ]];

    self.search = [[NSSearchField alloc] initWithFrame:NSZeroRect]; self.search.placeholderString = @"搜索客户、需求、阻碍、联系方式"; self.search.delegate = self; self.search.target = self; self.search.action = @selector(applyFilters:);
    self.bandFilter = [[NSPopUpButton alloc] initWithFrame:NSZeroRect pullsDown:NO];
    [self.bandFilter addItemsWithTitles:@[@"全部意向", @"高意向", @"待激活", @"长期培育", @"排除"]]; self.bandFilter.target = self; self.bandFilter.action = @selector(applyFilters:);
    [workspace addSubview:self.search]; [workspace addSubview:self.bandFilter]; self.search.translatesAutoresizingMaskIntoConstraints = self.bandFilter.translatesAutoresizingMaskIntoConstraints = NO;
    [NSLayoutConstraint activateConstraints:@[
        [self.search.leadingAnchor constraintEqualToAnchor:workspace.leadingAnchor constant:16], [self.search.topAnchor constraintEqualToAnchor:workspace.topAnchor constant:14], [self.search.widthAnchor constraintEqualToConstant:310],
        [self.bandFilter.leadingAnchor constraintEqualToAnchor:self.search.trailingAnchor constant:10], [self.bandFilter.centerYAnchor constraintEqualToAnchor:self.search.centerYAnchor], [self.bandFilter.widthAnchor constraintEqualToConstant:120]
    ]];

    self.table = [[NSTableView alloc] initWithFrame:NSZeroRect]; self.table.dataSource = self; self.table.delegate = self; self.table.headerView = [[NSTableHeaderView alloc] init]; self.table.rowHeight = 38; self.table.usesAlternatingRowBackgroundColors = YES; self.table.backgroundColor = NSColor.whiteColor; self.table.gridColor = [NSColor colorWithWhite:0.9 alpha:1];
    NSArray *columns = @[@[@"客户", @"display_name", @150], @[@"意向分", @"intent_score", @72], @[@"等级", @"intent_band", @88], @[@"最近联系", @"recent_contact", @150], @[@"需求 / 联系方式", @"need_contact", @240]];
    for (NSArray *spec in columns) { NSTableColumn *column = [[NSTableColumn alloc] initWithIdentifier:spec[1]]; column.title = spec[0]; column.width = [spec[2] doubleValue]; [self.table addTableColumn:column]; }
    NSScrollView *tableScroll = [[NSScrollView alloc] initWithFrame:NSZeroRect]; tableScroll.documentView = self.table; tableScroll.hasVerticalScroller = YES; tableScroll.borderType = NSNoBorder; tableScroll.backgroundColor = NSColor.whiteColor; tableScroll.drawsBackground = YES;
    [workspace addSubview:tableScroll]; tableScroll.translatesAutoresizingMaskIntoConstraints = NO;

    NSView *detail = [[NSView alloc] initWithFrame:NSZeroRect]; detail.wantsLayer = YES; detail.layer.backgroundColor = [NSColor colorWithRed:0.97 green:0.98 blue:1 alpha:1].CGColor; detail.layer.cornerRadius = 10;
    self.detailTitle = Label(@"选择客户查看详情", 18, [NSColor colorWithRed:0.06 green:0.10 blue:0.20 alpha:1], YES);
    self.detailMeta = Label(@"", 12, [NSColor colorWithWhite:0.42 alpha:1], NO);
    self.detailText = [[NSTextView alloc] initWithFrame:NSMakeRect(0, 0, 360, 210)]; self.detailText.editable = NO; self.detailText.verticallyResizable = YES; self.detailText.autoresizingMask = NSViewWidthSizable; self.detailText.textContainer.widthTracksTextView = YES; self.detailText.drawsBackground = YES; self.detailText.backgroundColor = [NSColor colorWithRed:0.97 green:0.98 blue:1 alpha:1]; self.detailText.textColor = [NSColor colorWithWhite:0.18 alpha:1]; self.detailText.font = [NSFont systemFontOfSize:12]; self.detailText.textContainerInset = NSMakeSize(2, 8);
    NSScrollView *detailScroll = [[NSScrollView alloc] initWithFrame:NSZeroRect]; detailScroll.documentView = self.detailText; detailScroll.hasVerticalScroller = YES; detailScroll.drawsBackground = YES; detailScroll.backgroundColor = [NSColor colorWithRed:0.97 green:0.98 blue:1 alpha:1];
    self.draftText = [[NSTextView alloc] initWithFrame:NSMakeRect(0, 0, 360, 150)]; self.draftText.verticallyResizable = YES; self.draftText.autoresizingMask = NSViewWidthSizable; self.draftText.textContainer.widthTracksTextView = YES; self.draftText.font = [NSFont systemFontOfSize:12]; self.draftText.textColor = [NSColor colorWithWhite:0.18 alpha:1]; self.draftText.drawsBackground = YES; self.draftText.backgroundColor = NSColor.whiteColor; self.draftText.textContainerInset = NSMakeSize(8, 8); self.draftText.wantsLayer = YES; self.draftText.layer.cornerRadius = 6;
    NSScrollView *draftScroll = [[NSScrollView alloc] initWithFrame:NSZeroRect]; draftScroll.documentView = self.draftText; draftScroll.hasVerticalScroller = YES; draftScroll.drawsBackground = YES; draftScroll.backgroundColor = NSColor.whiteColor;
    NSTextField *draftLabel = Label(@"可编辑激活文案", 12, [NSColor colorWithWhite:0.35 alpha:1], YES);
    AttachmentDropField *dropField = [[AttachmentDropField alloc] initWithFrame:NSZeroRect];
    dropField.workspaceController = self;
    dropField.stringValue = @"拖入图片/视频/文件，或点上方选择附件";
    self.batchStatusLabel = dropField;
    for (NSView *view in @[self.detailTitle, self.detailMeta, detailScroll, draftLabel, draftScroll, self.batchStatusLabel]) { [detail addSubview:view]; view.translatesAutoresizingMaskIntoConstraints = NO; }
    [workspace addSubview:detail]; detail.translatesAutoresizingMaskIntoConstraints = NO;
    [NSLayoutConstraint activateConstraints:@[
        [tableScroll.leadingAnchor constraintEqualToAnchor:workspace.leadingAnchor constant:12], [tableScroll.topAnchor constraintEqualToAnchor:self.search.bottomAnchor constant:12],
        [tableScroll.bottomAnchor constraintEqualToAnchor:workspace.bottomAnchor constant:-12], [tableScroll.widthAnchor constraintEqualToAnchor:workspace.widthAnchor multiplier:0.60 constant:-18],
        [detail.leadingAnchor constraintEqualToAnchor:tableScroll.trailingAnchor constant:12], [detail.trailingAnchor constraintEqualToAnchor:workspace.trailingAnchor constant:-12],
        [detail.topAnchor constraintEqualToAnchor:tableScroll.topAnchor], [detail.bottomAnchor constraintEqualToAnchor:tableScroll.bottomAnchor],
        [self.detailTitle.leadingAnchor constraintEqualToAnchor:detail.leadingAnchor constant:16], [self.detailTitle.trailingAnchor constraintEqualToAnchor:detail.trailingAnchor constant:-16], [self.detailTitle.topAnchor constraintEqualToAnchor:detail.topAnchor constant:16],
        [self.detailMeta.leadingAnchor constraintEqualToAnchor:self.detailTitle.leadingAnchor], [self.detailMeta.trailingAnchor constraintEqualToAnchor:self.detailTitle.trailingAnchor], [self.detailMeta.topAnchor constraintEqualToAnchor:self.detailTitle.bottomAnchor constant:5],
        [detailScroll.leadingAnchor constraintEqualToAnchor:self.detailTitle.leadingAnchor], [detailScroll.trailingAnchor constraintEqualToAnchor:self.detailTitle.trailingAnchor], [detailScroll.topAnchor constraintEqualToAnchor:self.detailMeta.bottomAnchor constant:8], [detailScroll.heightAnchor constraintEqualToConstant:210],
        [draftLabel.leadingAnchor constraintEqualToAnchor:self.detailTitle.leadingAnchor], [draftLabel.topAnchor constraintEqualToAnchor:detailScroll.bottomAnchor constant:10],
        [draftScroll.leadingAnchor constraintEqualToAnchor:self.detailTitle.leadingAnchor], [draftScroll.trailingAnchor constraintEqualToAnchor:self.detailTitle.trailingAnchor], [draftScroll.topAnchor constraintEqualToAnchor:draftLabel.bottomAnchor constant:6],
        [self.batchStatusLabel.leadingAnchor constraintEqualToAnchor:self.detailTitle.leadingAnchor], [self.batchStatusLabel.trailingAnchor constraintEqualToAnchor:self.detailTitle.trailingAnchor], [self.batchStatusLabel.bottomAnchor constraintEqualToAnchor:detail.bottomAnchor constant:-12],
        [draftScroll.bottomAnchor constraintEqualToAnchor:self.batchStatusLabel.topAnchor constant:-8]
    ]];
    if (self.startupError.length) { self.detailTitle.stringValue = @"分析尚未就绪"; self.detailText.string = self.startupError; }
    else if (self.visibleLeads.count) { [self.table selectRowIndexes:[NSIndexSet indexSetWithIndex:0] byExtendingSelection:NO]; [self showLead:self.visibleLeads[0]]; }
}

- (NSInteger)numberOfRowsInTableView:(NSTableView *)tableView { return self.visibleLeads.count; }

- (NSView *)tableView:(NSTableView *)tableView viewForTableColumn:(NSTableColumn *)column row:(NSInteger)row {
    NSDictionary *lead = self.visibleLeads[row];
    NSString *identifier = column.identifier;
    NSString *value = @"";
    if ([identifier isEqualToString:@"need_contact"]) value = [NSString stringWithFormat:@"%@%@%@", lead[@"need"] ?: @"", [lead[@"need"] length] && [lead[@"contact"] length] ? @" · " : @"", lead[@"contact"] ?: @""];
    else value = [lead[identifier] description] ?: @"";
    NSTextField *field = Label(value, 12, [NSColor colorWithWhite:0.18 alpha:1], [identifier isEqualToString:@"intent_score"]);
    if ([identifier isEqualToString:@"intent_band"]) {
        if ([value isEqualToString:@"高意向"]) field.textColor = NSColor.systemGreenColor;
        else if ([value isEqualToString:@"待激活"]) field.textColor = NSColor.systemOrangeColor;
    }
    return field;
}

- (void)tableViewSelectionDidChange:(NSNotification *)notification {
    NSInteger row = self.table.selectedRow;
    if (row >= 0 && row < (NSInteger)self.visibleLeads.count) [self showLead:self.visibleLeads[row]];
}

- (void)showLead:(NSDictionary *)lead {
    self.detailTitle.stringValue = [NSString stringWithFormat:@"%@ · %@ 分", lead[@"display_name"] ?: @"客户", lead[@"intent_score"] ?: @0];
    self.detailMeta.stringValue = [NSString stringWithFormat:@"%@ · 最近联系 %@", lead[@"intent_band"] ?: @"", lead[@"recent_contact"] ?: @""];
    NSMutableString *body = [NSMutableString string];
    [body appendFormat:@"明确需求\n%@\n\n阻碍因素\n%@\n\n建议动作\n%@\n\n关键联系方式\n%@\n\n真实聊天证据\n", lead[@"need"] ?: @"未提取", lead[@"obstacles"] ?: @"未发现", lead[@"suggested_action"] ?: @"", lead[@"contact"] ?: @"未提取"];
    for (NSDictionary *evidence in lead[@"evidence"] ?: @[]) [body appendFormat:@"\n%@  [%@]\n%@\n", evidence[@"time"] ?: @"", evidence[@"direction"] ?: @"", evidence[@"content"] ?: @""];
    self.detailText.string = body;
    self.draftText.string = lead[@"draft_text"] ?: @"";
}

- (void)applyFilters:(id)sender {
    NSString *query = self.search.stringValue.lowercaseString;
    NSString *band = self.bandFilter.titleOfSelectedItem;
    NSPredicate *predicate = [NSPredicate predicateWithBlock:^BOOL(NSDictionary *lead, NSDictionary *bindings) {
        BOOL bandOK = [band isEqualToString:@"全部意向"] || [lead[@"intent_band"] isEqualToString:band];
        if (!bandOK) return NO;
        if (!query.length) return YES;
        NSString *haystack = [NSString stringWithFormat:@"%@ %@ %@ %@ %@", lead[@"display_name"] ?: @"", lead[@"customer_id"] ?: @"", lead[@"need"] ?: @"", lead[@"obstacles"] ?: @"", lead[@"contact"] ?: @""];
        return [haystack.lowercaseString containsString:query];
    }];
    self.visibleLeads = [self.allLeads filteredArrayUsingPredicate:predicate];
    [self.table reloadData];
    if (self.visibleLeads.count) { [self.table selectRowIndexes:[NSIndexSet indexSetWithIndex:0] byExtendingSelection:NO]; [self showLead:self.visibleLeads[0]]; }
}

- (NSString *)currentDBPath {
    NSString *db = NSProcessInfo.processInfo.environment[@"WECHAT_SALES_AGENT_DB"];
    if (!db.length) db = [NSHomeDirectory() stringByAppendingPathComponent:@"Library/Application Support/WeChatSalesAgent/agent_state.sqlite3"];
    return db;
}

- (NSArray<NSString *> *)runAgentCommand:(NSArray<NSString *> *)arguments terminationStatus:(int *)status error:(NSError **)error {
    NSString *pythonRoot = [[NSBundle mainBundle].resourcePath stringByAppendingPathComponent:@"Python"];
    NSTask *task = [[NSTask alloc] init];
    task.executableURL = [NSURL fileURLWithPath:@"/usr/bin/python3"];
    task.arguments = arguments;
    NSMutableDictionary *environment = [NSProcessInfo.processInfo.environment mutableCopy];
    environment[@"PYTHONPATH"] = pythonRoot;
    task.environment = environment;
    NSPipe *pipe = [NSPipe pipe];
    task.standardOutput = pipe;
    task.standardError = pipe;
    if (![task launchAndReturnError:error]) return @[];
    [task waitUntilExit];
    if (status) *status = task.terminationStatus;
    NSData *data = [pipe.fileHandleForReading readDataToEndOfFile];
    NSString *output = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] ?: @"";
    NSMutableArray<NSString *> *lines = [NSMutableArray array];
    for (NSString *line in [output componentsSeparatedByCharactersInSet:NSCharacterSet.newlineCharacterSet]) if (line.length) [lines addObject:line];
    return lines;
}

- (NSDictionary *)lastJSONObjectFromLines:(NSArray<NSString *> *)lines {
    for (NSString *line in lines.reverseObjectEnumerator) {
        NSData *data = [line dataUsingEncoding:NSUTF8StringEncoding];
        id object = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
        if ([object isKindOfClass:NSDictionary.class] && object[@"batch_id"]) return object;
    }
    return nil;
}

- (void)chooseAttachments:(id)sender {
    NSOpenPanel *panel = [NSOpenPanel openPanel];
    panel.canChooseFiles = YES;
    panel.canChooseDirectories = NO;
    panel.allowsMultipleSelection = YES;
    if ([panel runModal] != NSModalResponseOK) return;
    [self setAttachmentURLs:panel.URLs];
}

- (void)setAttachmentURLs:(NSArray<NSURL *> *)urls {
    [self.attachmentPaths removeAllObjects];
    for (NSURL *url in urls) if (url.path.length) [self.attachmentPaths addObject:url.path];
    self.batchStatusLabel.stringValue = self.attachmentPaths.count ? [NSString stringWithFormat:@"已选择 %lu 个附件 · 可继续创建发送批次", (unsigned long)self.attachmentPaths.count] : @"拖入图片/视频/文件，或点上方选择附件";
    self.batchStatusLabel.textColor = [NSColor colorWithWhite:0.30 alpha:1];
}

- (NSArray<NSString *> *)actionableVisibleCustomerIDs {
    NSMutableArray<NSString *> *ids = [NSMutableArray array];
    for (NSDictionary *lead in self.visibleLeads) {
        NSString *band = lead[@"intent_band"];
        if (![band isEqualToString:@"高意向"] && ![band isEqualToString:@"待激活"]) continue;
        NSString *customerID = lead[@"customer_id"];
        if (customerID.length) [ids addObject:customerID];
    }
    return ids;
}

- (BOOL)createSendBatchInternal {
    NSArray<NSString *> *customerIDs = self.actionableVisibleCustomerIDs;
    if (!customerIDs.count) { NSBeep(); self.batchStatusLabel.stringValue = @"当前筛选没有高意向/待激活客户"; return NO; }
    NSString *text = [self.draftText.string stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    if (!text.length) { NSBeep(); self.batchStatusLabel.stringValue = @"激活文案不能为空"; return NO; }
    NSMutableArray<NSString *> *arguments = [NSMutableArray arrayWithArray:@[@"-m", @"agent_core.send_cli", @"--db", self.currentDBPath, @"create", @"--account-id", self.snapshot[@"account_id"] ?: @"", @"--text", text]];
    for (NSString *customerID in customerIDs) [arguments addObjectsFromArray:@[@"--customer-id", customerID]];
    for (NSString *path in self.attachmentPaths) [arguments addObjectsFromArray:@[@"--attachment", path]];
    int status = 0;
    NSError *error = nil;
    NSArray<NSString *> *lines = [self runAgentCommand:arguments terminationStatus:&status error:&error];
    NSDictionary *batch = [self lastJSONObjectFromLines:lines];
    if (status != 0 || !batch) {
        self.batchStatusLabel.stringValue = error.localizedDescription ?: @"发送批次创建失败";
        self.batchStatusLabel.textColor = NSColor.systemRedColor;
        return NO;
    }
    self.currentBatchID = batch[@"batch_id"];
    self.batchStatusLabel.stringValue = [NSString stringWithFormat:@"批次 %@ 已创建 · %@ 人", [self.currentBatchID substringToIndex:MIN((NSUInteger)8, self.currentBatchID.length)], batch[@"total"] ?: @0];
    self.batchStatusLabel.textColor = NSColor.systemOrangeColor;
    return YES;
}

- (void)createSendBatch:(id)sender {
    [self createSendBatchInternal];
}

- (void)dispatchSendBatch:(id)sender {
    if (!self.currentBatchID.length && ![self createSendBatchInternal]) return;
    int status = 0;
    NSError *error = nil;
    NSArray<NSString *> *lines = [self runAgentCommand:@[@"-m", @"agent_core.send_cli", @"--db", self.currentDBPath, @"dispatch", @"--batch-id", self.currentBatchID] terminationStatus:&status error:&error];
    NSDictionary *batch = [self lastJSONObjectFromLines:lines];
    if (!batch) {
        self.batchStatusLabel.stringValue = error.localizedDescription ?: @"发送执行失败";
        self.batchStatusLabel.textColor = NSColor.systemRedColor;
        return;
    }
    NSString *label = batch[@"status_label"] ?: batch[@"status"] ?: @"未知";
    self.batchStatusLabel.stringValue = [NSString stringWithFormat:@"发送状态：%@ · %@ 人", label, batch[@"total"] ?: @0];
    self.batchStatusLabel.textColor = status == 0 ? NSColor.systemGreenColor : NSColor.systemRedColor;
}

- (void)exportWorkbook:(id)sender {
    if (!self.allLeads.count) { NSBeep(); return; }
    NSSavePanel *panel = [NSSavePanel savePanel]; panel.nameFieldStringValue = @"微信客户激活表.xlsx"; panel.allowedContentTypes = @[];
    if ([panel runModal] != NSModalResponseOK) return;
    NSTask *task = [[NSTask alloc] init]; task.executableURL = [NSURL fileURLWithPath:@"/bin/bash"];
    task.arguments = @[[NSString stringWithFormat:@"%s/scripts/phase4_export.sh", PROJECT_DIR], panel.URL.path, self.snapshot[@"account_id"] ?: @""];
    NSError *error = nil;
    if (![task launchAndReturnError:&error]) { self.statusLabel.stringValue = error.localizedDescription; self.statusLabel.textColor = NSColor.systemRedColor; return; }
    [task waitUntilExit];
    self.statusLabel.stringValue = task.terminationStatus == 0 ? @"Excel 已导出" : @"Excel 导出失败";
    self.statusLabel.textColor = task.terminationStatus == 0 ? NSColor.systemGreenColor : NSColor.systemRedColor;
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
        BOOL launchSmoke = NO;
        BOOL uiSmoke = NO;
        for (int index = 1; index < argc; index++) {
            NSString *argument = [NSString stringWithUTF8String:argv[index]];
            if ([argument isEqualToString:@"--snapshot"] && index + 1 < argc) controller.snapshotPath = [NSString stringWithUTF8String:argv[++index]];
            else if ([argument isEqualToString:@"--render-preview"] && index + 1 < argc) previewPath = [NSString stringWithUTF8String:argv[++index]];
            else if ([argument isEqualToString:@"--smoke"]) launchSmoke = YES;
            else if ([argument isEqualToString:@"--ui-smoke"]) uiSmoke = YES;
        }
        application.delegate = controller;
        [application finishLaunching];
        [controller applicationDidFinishLaunching:[NSNotification notificationWithName:NSApplicationDidFinishLaunchingNotification object:application]];
        if (previewPath.length) {
            [controller.window displayIfNeeded];
            BOOL written = WriteWindowPNG(controller.window, previewPath);
            PrintDiagnostic(@"ui_preview", written ? @"passed" : @"failed", written ? @"NATIVE_UI_PREVIEW_WRITTEN" : @"NATIVE_UI_PREVIEW_FAILED", previewPath);
            return written ? 0 : 1;
        }
        if (launchSmoke || uiSmoke) {
            BOOL valid = controller.window != nil && (!uiSmoke || (controller.allLeads.count > 0 && controller.table.numberOfRows == (NSInteger)controller.allLeads.count));
            PrintDiagnostic(uiSmoke ? @"ui_smoke" : @"app_smoke", valid ? @"passed" : @"failed", valid ? (uiSmoke ? @"NATIVE_WORKSPACE_UI_OK" : @"NATIVE_APP_SHELL_OK") : @"NATIVE_WORKSPACE_UI_INVALID", valid ? (uiSmoke ? @"Dashboard, lead table, and detail view loaded." : @"Native AppKit shell loaded.") : @"Workspace did not load the supplied published snapshot.");
            return valid ? 0 : 1;
        }
        [application run];
    }
    return 0;
}
