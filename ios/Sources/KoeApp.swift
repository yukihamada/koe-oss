import SwiftUI

@main
struct KoeApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var state = AppState()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(state)
                .onAppear {
                    PushManager.shared.bootstrap()
                    Task { await WidgetSync.refresh() }
                }
        }
    }
}

/// 3タブ: トーク(既定・主役)・録る・わたし。2026-08-27本人指摘「ごちゃごちゃしすぎ」で
/// 4本目の「ログ」(架空データのみのプロトタイプ・VoiceLogFeedView参照)をタブから撤去。
/// ライブはタブから外し「わたし」内のサブ画面+通知deep link時のシートへ格下げ
/// (2026-08-17 本人指示「もっとシンプルにして。liveは目立たないとこでいい。メインはトーク」)。
/// 2026-07-20 本人指示「シンプルにして。機能は増やす一方でボタンは減らして」でIA刷新
/// (設計=Fable・実装=Sonnet)。旧「友だち」タブは独立タブをやめ「トーク」上部の
/// セグメントへ格下げ(会話の行き先は常にトーク、友だちは前提リストのため)。
/// 旧「設定」に雑多に積まれていた機能は「録る」(録音起点4機能)と「わたし」(頻度で階層化)へ分割。
enum KoeTab: Hashable {
    case talk, record, me
}

struct RootView: View {
    @EnvironmentObject var state: AppState
    @State private var showSolunaOnboarding = false
    @State private var showOnboarding = OnboardingView.shouldShow
    @State private var tab: KoeTab = .talk

    // 通知タップで該当タブのWebViewへ読み込み直すdeep link先。
    @State private var livePath: String?
    @State private var talkPath: String?
    @State private var friendsPath: String?
    @State private var talkSegment: TalkSegment = .talk
    @State private var showLive = false
    @State private var showPending = false

    var body: some View {
        TabView(selection: $tab) {
            TalkHubScreen(active: tab == .talk, segment: $talkSegment,
                          talkPendingPath: $talkPath, friendsPendingPath: $friendsPath)
                .tabItem { Label("トーク", systemImage: "message.fill") }
                .tag(KoeTab.talk)
            // 🔴2026-08-27 harsh-review指摘で発覚・タブから撤去: VoiceLogFeedView("うちのルーム")は
            // entries/reactionsが全部ハードコードされた架空の5人(あおい/けんと/わたし/みさき等)の
            // フェイクデータで、togglePlay()も実際は音声を再生せず進捗バーを演出するだけ。
            // 対応するはずのバックエンド/api/voice_logsもkoe-edge側でモック止まり・未接続だった
            // (別セッションの未完成プロトタイプがそのままタブに配線されていた)。
            // 実データで作り直すまでファイルは残し、タブからは外す。
            RecordHubView()
                .tabItem { Label("録る", systemImage: "waveform.badge.mic") }
                .tag(KoeTab.record)
            MeView()
                .tabItem { Label("わたし", systemImage: "person.circle.fill") }
                .tag(KoeTab.me)
        }
        .tint(Theme.accentColor)
        .sheet(isPresented: $showLive) {
            NavigationStack {
                LiveScreen(active: true, pendingPath: $livePath)
                    .toolbar {
                        ToolbarItem(placement: .topBarLeading) {
                            Button("閉じる") { showLive = false }
                        }
                    }
            }
        }
        .fullScreenCover(isPresented: $showSolunaOnboarding) {
            SolunaView()
                .environmentObject(state)
        }
        .fullScreenCover(isPresented: $showOnboarding) { OnboardingView() }
        .sheet(isPresented: $showPending) { PendingListView() }
        .onAppear {
            bootstrapSoluna()
        }
        .onReceive(NotificationCenter.default.publisher(for: .koeDeepLink)) { note in
            guard let path = note.userInfo?["path"] as? String, !path.isEmpty else { return }
            route(path)
        }
        .onReceive(NotificationCenter.default.publisher(for: .koeOpenPending)) { _ in
            showPending = true
        }
        .onReceive(NotificationCenter.default.publisher(for: .koeOpenRecord)) { _ in
            tab = .record
        }
        .onOpenURL { url in
            // ウィジェット/ロック画面ウィジェット/Siriショートカットからの koe://pending
            if url.scheme == "koe", url.host == "pending" {
                showPending = true
            }
        }
    }

    /// 通知payloadのurl(例: "/live/<handle>" "/talk1" "/box")を該当タブへ振り分ける。
    /// /friendsは「トーク」タブの「友だち」セグメントへ(独立タブ廃止・2026-07-20)。
    private func route(_ path: String) {
        if path.hasPrefix("/live") {
            livePath = path; showLive = true
        } else if path.hasPrefix("/friends") {
            tab = .talk; talkSegment = .friends; friendsPath = path
        } else {
            tab = .talk; talkSegment = .talk; talkPath = path
        }
    }

    /// 🌊 どこでもマイク: reconnect with the saved ID the moment the app opens
    /// (no taps needed). 🔴harsh-review指摘(2026-07-20)により、未設定時に初回起動で
    /// 全画面オンボーディングを強制表示するのはやめた — 新規ユーザーの第一画面が
    /// ライブでもトークでもなく謎の上級者向け設定になっていた。以後は「わたし」の
    /// トグルをONにした時だけ(ユーザー起点)案内する。
    private func bootstrapSoluna() {
        if !state.solunaId.isEmpty, state.solunaAutoStart, SolunaSession.shared.status == .off {
            state.startSoluna()
        }
    }
}
