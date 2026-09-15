import SwiftUI
import WebKit

/// koe.live のページ(ライブ/トーク/友だち)をアプリ内に埋め込む WKWebView ラッパ。
/// Cookie セッションで `/api/social/*` 等がそのまま動くので、認証ブリッジ不要でWeb側を流用できる。
/// 録音(getUserMedia)はマイク権限を grant して動かす。
struct WebAppView: UIViewRepresentable {
    let url: URL
    /// 選択中タブかどうか。非選択時は Web 側の visibilitychange/pagehide を発火させて
    /// presence beat・ポーリングを止めさせる(edge側は document.hidden を見る)。
    var active: Bool = true
    /// 非nilの間、このパスへ読み込み直す(通知タップの deep link 用)。読み込み後は自動でnilに戻す。
    var pendingPath: Binding<String?> = .constant(nil)
    /// 初回ロード中はtrue。タブ初回タップ時の白画面フラッシュにスピナーを出すための通知(harsh-review指摘)。
    var isLoading: Binding<Bool> = .constant(false)
    /// ページが1枚も出せずに失敗(オフライン等)でtrue。画面側が「もう一度」UIを出す
    /// (harsh-review指摘: 圏外で開くと白画面のまま復帰手段がなかった)。
    var loadFailed: Binding<Bool> = .constant(false)

    /// 起動時にライブタブだけロードし、他タブは初回表示までWKWebView自体が作られない
    /// (UIViewRepresentableのmakeUIViewはそのタブが実際に描画されるまで呼ばれない)。
    /// ここではプロセスプールだけ3枚のWebViewで共有してメモリ/起動を軽くする。
    static let sharedProcessPool = WKProcessPool()

    func makeCoordinator() -> Coordinator { Coordinator(isLoading: isLoading, loadFailed: loadFailed) }

    func makeUIView(context: Context) -> WKWebView {
        let cfg = WKWebViewConfiguration()
        cfg.processPool = Self.sharedProcessPool
        cfg.allowsInlineMediaPlayback = true
        cfg.mediaTypesRequiringUserActionForPlayback = []
        // koe-edge側がこのマーカーを見て、ネイティブの「録る」タブ等と丸かぶりする
        // フローティング要素(声を送るFAB/声ライブのミニプレイヤー/下部固定プレイヤー)を
        // 隠す(本人指摘2026-08-27「ごちゃごちゃ」・NATIVE_APP_HIDE_SNIPPET参照)。
        // applicationNameForUserAgentはデフォルトUAの末尾に安全に追記されるAPI(UA全体を
        // 手で組み立てるより壊れにくい)。
        cfg.applicationNameForUserAgent = "KoeNativeApp/1"
        let wv = WKWebView(frame: .zero, configuration: cfg)
        wv.uiDelegate = context.coordinator
        wv.navigationDelegate = context.coordinator
        wv.allowsBackForwardNavigationGestures = true
        wv.scrollView.contentInsetAdjustmentBehavior = .always
        wv.load(URLRequest(url: url))
        context.coordinator.wasActive = active
        context.coordinator.webView = wv
        return wv
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {
        context.coordinator.isLoading = isLoading
        context.coordinator.loadFailed = loadFailed
        if let path = pendingPath.wrappedValue, let target = Self.resolve(path) {
            uiView.load(URLRequest(url: target))
            DispatchQueue.main.async { pendingPath.wrappedValue = nil }
        }
        if context.coordinator.wasActive != active {
            context.coordinator.wasActive = active
            let evt = active ? "pageshow" : "pagehide"
            uiView.evaluateJavaScript(
                "document.dispatchEvent(new Event('\(evt)'));document.dispatchEvent(new Event('visibilitychange'));")
        }
    }

    /// 相対パス(例: "/live/yuki")を koe.live の絶対URLへ。絶対URLはそのまま通す。
    static func resolve(_ path: String) -> URL? {
        if path.hasPrefix("http") { return URL(string: path) }
        return URL(string: "https://koe.live" + path)
    }

    final class Coordinator: NSObject, WKUIDelegate, WKNavigationDelegate {
        var wasActive = true
        var isLoading: Binding<Bool>
        var loadFailed: Binding<Bool>
        weak var webView: WKWebView?

        init(isLoading: Binding<Bool>, loadFailed: Binding<Bool>) {
            self.isLoading = isLoading
            self.loadFailed = loadFailed
            super.init()
            NotificationCenter.default.addObserver(self, selector: #selector(handleStopAllAudio),
                                                    name: .koeStopAllAudio, object: nil)
        }

        deinit {
            NotificationCenter.default.removeObserver(self)
        }

        /// ボイスレコーダー録音開始時などに、ライブ/トークタブが再生中のHTML5
        /// audio/videoを止める(録音への被り防止・harsh-review的には無音でも
        /// 呼んで害はないfail-safe)。
        @objc private func handleStopAllAudio() {
            webView?.evaluateJavaScript(
                "document.querySelectorAll('audio,video').forEach(function(m){try{m.pause();}catch(e){}});")
        }

        func webView(_ webView: WKWebView, didStartProvisionalNavigation navigation: WKNavigation!) {
            isLoading.wrappedValue = true
        }
        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            isLoading.wrappedValue = false
            loadFailed.wrappedValue = false
        }
        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            isLoading.wrappedValue = false
        }
        // ページが1枚も描画できなかった失敗だけ「つながりませんでした」扱いにする。
        // NSURLErrorCancelled(-999)は連続ナビゲーションで正常に起きるので無視。
        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
            isLoading.wrappedValue = false
            let ns = error as NSError
            guard !(ns.domain == NSURLErrorDomain && ns.code == NSURLErrorCancelled) else { return }
            loadFailed.wrappedValue = true
        }

        // /app 等の録音はブラウザの getUserMedia を使うため、アプリ内 WebView でも
        // マイク取得を明示的に許可する(Info.plist の NSMicrophoneUsageDescription と対)。
        @available(iOS 15.0, *)
        func webView(_ webView: WKWebView,
                     requestMediaCapturePermissionFor origin: WKSecurityOrigin,
                     initiatedByFrame frame: WKFrameInfo,
                     type: WKMediaCaptureType,
                     decisionHandler: @escaping (WKPermissionDecision) -> Void) {
            decisionHandler(.grant)
        }
    }
}

/// WebAppViewの初回ロード中、白画面の代わりに出す軽量スピナー(harsh-review指摘の穴埋め)。
private struct LoadingOverlay: View {
    var body: some View {
        ZStack {
            Color.black.opacity(0.3).ignoresSafeArea()
            ProgressView(NSLocalizedString("声をあつめています…", comment: ""))
                .tint(.white)
                .padding()
                .background(Color.black.opacity(0.7), in: RoundedRectangle(cornerRadius: 10))
        }
    }
}

/// 読み込み失敗(圏外・機内モード等)のときの全面カバー。「もう一度」で同じページを読み直す。
private struct LoadErrorOverlay: View {
    var retry: () -> Void

    var body: some View {
        VStack(spacing: 14) {
            Image(systemName: "wifi.slash")
                .font(.system(size: 40))
                .foregroundStyle(.secondary)
            Text("つながりませんでした")
                .font(.headline)
            Text("電波のよいところで、もう一度お試しください。")
                .font(.footnote)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            Button(action: retry) {
                Label("もう一度", systemImage: "arrow.clockwise")
                    .font(.subheadline.weight(.semibold))
                    .padding(.horizontal, 24)
                    .frame(minHeight: 44)
            }
            .buttonStyle(.borderedProminent)
            .tint(Theme.accentColor)
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(uiColor: .systemBackground))
    }
}

/// 3タブ共通のWebView画面: スピナー+失敗時の再試行を持つ。パーソナリティーハブ等
/// タブ以外の画面からも埋め込めるようinternal(既定)にしてある。
struct KoeWebScreen: View {
    let url: URL
    /// 「もう一度」で読み直す先(タブの基準パス)。
    let basePath: String
    var active: Bool
    var pendingPath: Binding<String?>
    @State private var isLoading = true
    @State private var loadFailed = false

    var body: some View {
        ZStack {
            WebAppView(url: url, active: active, pendingPath: pendingPath,
                       isLoading: $isLoading, loadFailed: $loadFailed)
                .ignoresSafeArea(edges: .bottom)
            if isLoading { LoadingOverlay() }
            if loadFailed {
                LoadErrorOverlay {
                    loadFailed = false
                    pendingPath.wrappedValue = basePath
                }
            }
        }
    }
}

/// 「ライブ」タブ: koe.live(トップ=ラジオプレイヤー第一画面)。既定選択の主役タブ。
/// 通知等の deep link で /live/<handle> (声の部屋) へは pendingPath 経由で遷移できる。
struct LiveScreen: View {
    var active: Bool = true
    var pendingPath: Binding<String?> = .constant(nil)

    var body: some View {
        KoeWebScreen(url: URL(string: "https://koe.live/")!, basePath: "/",
                     active: active, pendingPath: pendingPath)
    }
}

/// 「トーク」タブ内のセグメント: トーク(会話そのもの) / 友だち(一覧・前提リスト)。
/// 2026-07-20 IA刷新: 旧「友だち」独立タブを廃止しここへ格下げ(設計=Fable)。
/// 会話の行き先は常にトークで、友だちは目的地でなく前提リストのため。
enum TalkSegment: Hashable {
    case talk, friends
}

/// 「トーク」タブ: koe.live/talk1(声のトランシーバー・留守番箱+1:1送受信)を主に、
/// 上部セグメントで koe.live/friends(つながり一覧)にも切り替えられる。
/// 🔴2026-07-20修正: 元は koe.live/app を指していたが、/app は声の登録専用ページに
/// 変わっており送信UIが無い(本人報告「メッセージの画面送れない」で発覚)。プッシュ通知の
/// deep link は元々 /talk1 をこのタブへ振る設計だった(route()参照)ので、既定URLも揃えた。
struct TalkHubScreen: View {
    var active: Bool = true
    @Binding var segment: TalkSegment
    var talkPendingPath: Binding<String?> = .constant(nil)
    var friendsPendingPath: Binding<String?> = .constant(nil)

    var body: some View {
        VStack(spacing: 0) {
            Picker("", selection: $segment) {
                Text("トーク").tag(TalkSegment.talk)
                Text("友だち").tag(TalkSegment.friends)
            }
            .pickerStyle(.segmented)
            .padding(.horizontal, 16)
            .padding(.top, 8)
            .padding(.bottom, 6)

            switch segment {
            case .talk:
                KoeWebScreen(url: URL(string: "https://koe.live/talk1")!, basePath: "/talk1",
                             active: active, pendingPath: talkPendingPath)
            case .friends:
                KoeWebScreen(url: URL(string: "https://koe.live/friends")!, basePath: "/friends",
                             active: active, pendingPath: friendsPendingPath)
            }
        }
        .background(Color(uiColor: .systemBackground))
    }
}
