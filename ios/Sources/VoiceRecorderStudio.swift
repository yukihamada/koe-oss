import SwiftUI
import AVFoundation
import Speech

// 2026-07-20 本人指示「Koe.appの声レコーダーをiPhoneアプリにも実装、文字起こしを
// 声の開発にも送れる道を」。Mac版(VoiceMemoModels等・[[koe_mac_voice_recorder]])の
// フル機能(要約TTS/焚き火連携)は移植せず、iPhone向けに録音+文字起こし+履歴+
// 「開発に送る」だけの軽量版として新規実装。既存のVoiceRecorder.swift(声登録用の
// 使い捨て一時ファイル録音)とは保存先・目的が別なので触らず並存させる。

// MARK: - Model

struct RecordingEntry: Identifiable, Codable, Equatable {
    enum TranscriptStatus: String, Codable { case pending, running, done, failed }

    let id: String
    let date: Date
    var duration: TimeInterval
    var transcript: String?
    var transcriptStatus: TranscriptStatus = .pending
    var sentToDev: Bool = false
    var waveform: [Float] = []

    var fileName: String { id + ".m4a" }
}

/// Persists recordings + metadata under Documents/VoiceRecorder/. Separate from
/// VoiceRecorder.swift's temp-file scratch space (voice registration) — mixing
/// them risked the registration flow deleting a saved memo, or vice versa.
@MainActor
final class RecordingLibrary: ObservableObject {
    static let shared = RecordingLibrary()

    @Published private(set) var entries: [RecordingEntry] = []

    private let dir: URL = {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let d = docs.appendingPathComponent("VoiceRecorder", isDirectory: true)
        try? FileManager.default.createDirectory(at: d, withIntermediateDirectories: true)
        return d
    }()
    private var indexURL: URL { dir.appendingPathComponent("index.json") }

    private init() { load() }

    func fileURL(for entry: RecordingEntry) -> URL { dir.appendingPathComponent(entry.fileName) }
    func newRecordingURL(id: String) -> URL { dir.appendingPathComponent(id + ".m4a") }

    func add(_ entry: RecordingEntry) {
        entries.insert(entry, at: 0)
        save()
    }

    func update(_ entry: RecordingEntry) {
        guard let i = entries.firstIndex(where: { $0.id == entry.id }) else { return }
        entries[i] = entry
        save()
    }

    func delete(_ entry: RecordingEntry) {
        try? FileManager.default.removeItem(at: fileURL(for: entry))
        entries.removeAll { $0.id == entry.id }
        save()
    }

    private func load() {
        guard let data = try? Data(contentsOf: indexURL),
              let decoded = try? JSONDecoder().decode([RecordingEntry].self, from: data) else { return }
        entries = decoded
    }

    private func save() {
        guard let data = try? JSONEncoder().encode(entries) else { return }
        try? data.write(to: indexURL, options: .atomic)
    }
}

// MARK: - Recording engine

/// Records to a permanent .m4a (unlike VoiceRecorder.swift's overwritten temp
/// file) and samples mic level periodically for a lightweight waveform. This
/// is a coarse level trace, not a full-file downsample like the Mac app's
/// real-time metering pipeline — good enough for a phone list/detail view.
@MainActor
final class RecorderStudioEngine: NSObject, ObservableObject {
    @Published var isRecording = false
    @Published var elapsed: TimeInterval = 0
    @Published var liveLevels: [Float] = []
    @Published var errorText: String?

    private var recorder: AVAudioRecorder?
    private var meterTimer: Timer?
    private var startedAt: Date?
    private var currentID: String?

    func start() {
        // 録音前に、アプリ内で鳴っている音(ライブタブのラジオ・声メッセージ再生)を
        // 明示的に止める。.playAndRecordの有効化だけでは他アプリの音楽は割り込むが、
        // 同じAudioSessionを共有する自アプリ内音声(WKWebViewのHTML5 audio等)は
        // 黙ってくれない(本人指摘・2026-07-20)。
        NotificationCenter.default.post(name: .koeStopAllAudio, object: nil)

        let session = AVAudioSession.sharedInstance()
        try? session.setCategory(.playAndRecord, mode: .default)
        try? session.setActive(true)
        session.requestRecordPermission { [weak self] granted in
            guard let self else { return }
            Task { @MainActor in
                guard granted else {
                    self.errorText = NSLocalizedString("マイクの許可が必要です。設定アプリでKoeにマイクを許可してください。", comment: "")
                    return
                }
                self.errorText = nil
                self.beginRecording()
            }
        }
    }

    private func beginRecording() {
        let id = UUID().uuidString
        currentID = id
        let url = RecordingLibrary.shared.newRecordingURL(id: id)
        let settings: [String: Any] = [
            AVFormatIDKey: Int(kAudioFormatMPEG4AAC),
            AVSampleRateKey: 44100,
            AVNumberOfChannelsKey: 1,
            AVEncoderAudioQualityKey: AVAudioQuality.high.rawValue
        ]
        do {
            let r = try AVAudioRecorder(url: url, settings: settings)
            r.isMeteringEnabled = true
            r.record()
            recorder = r
            isRecording = true
            elapsed = 0
            liveLevels = []
            startedAt = Date()
            meterTimer = Timer.scheduledTimer(withTimeInterval: 0.12, repeats: true) { [weak self] _ in
                Task { @MainActor in self?.tick() }
            }
        } catch {
            isRecording = false
            errorText = NSLocalizedString("録音を開始できませんでした。", comment: "")
        }
    }

    private func tick() {
        guard let r = recorder, let started = startedAt else { return }
        r.updateMeters()
        let db = r.averagePower(forChannel: 0)
        // -50dB(ほぼ無音)〜0dB(最大)を 0..1 に正規化。
        let level = max(0, min(1, (db + 50) / 50))
        liveLevels.append(level)
        elapsed = Date().timeIntervalSince(started)
        // ログタブの制約「15秒まで」と揃える。超えたら自動停止(ペルソナFB#4)。
        if elapsed >= Self.maxDuration {
            NotificationCenter.default.post(name: .koeRecordingAutoStop, object: nil)
        }
    }

    static let maxDuration: TimeInterval = 15

    /// Stops recording and returns the finished entry (waveform downsampled to
    /// ~60 bars for storage/display). Transcription is kicked off by the caller.
    func stop() -> RecordingEntry? {
        meterTimer?.invalidate(); meterTimer = nil
        recorder?.stop()
        recorder = nil
        let duration = elapsed
        isRecording = false
        guard let id = currentID else { return nil }
        currentID = nil
        let entry = RecordingEntry(
            id: id, date: Date(), duration: duration,
            transcript: nil, transcriptStatus: .pending, sentToDev: false,
            waveform: Self.downsample(liveLevels, to: 60)
        )
        liveLevels = []
        return entry
    }

    private static func downsample(_ values: [Float], to count: Int) -> [Float] {
        guard values.count > count, count > 0 else { return values }
        let bucket = Double(values.count) / Double(count)
        return (0..<count).map { i -> Float in
            let start = Int(Double(i) * bucket)
            let end = min(values.count, Int(Double(i + 1) * bucket) + 1)
            let slice = values[start..<max(start + 1, end)]
            return slice.reduce(0, +) / Float(slice.count)
        }
    }
}

// MARK: - Transcription

/// Transcribes a finished recording file. Uses a URL-based request (runs on
/// the committed audio) rather than live buffer transcription, so quality
/// isn't affected by a concurrent mic tap. Locale follows the app's UI
/// language, same convention as SpeechManager.
///
/// 🔴harsh-review指摘への対応: 元はstatic funcの中だけでrecognizer/taskを作っており、
/// (a) 呼び出し元がインスタンスを保持しないと理論上deallocでコールバックが来なくなり得る、
/// (b) resultもerrorも来ないまま.runningで永久に固まっても検知手段が無かった。
/// 自分自身を保持するjobオブジェクトにし、30秒タイムアウトを追加した。
final class RecorderTranscriber {
    private static var activeJobs: [RecorderTranscriber] = []

    private var task: SFSpeechRecognitionTask?
    private var timeoutTimer: Timer?
    private var completion: ((Result<String, Error>) -> Void)?

    static func transcribe(fileURL: URL, completion: @escaping (Result<String, Error>) -> Void) {
        let job = RecorderTranscriber()
        activeJobs.append(job)
        job.start(fileURL: fileURL) { result in
            completion(result)
            activeJobs.removeAll { $0 === job }
        }
    }

    private func start(fileURL: URL, completion: @escaping (Result<String, Error>) -> Void) {
        self.completion = completion
        SFSpeechRecognizer.requestAuthorization { [weak self] status in
            guard let self else { return }
            guard status == .authorized else {
                self.finish(.failure(NSError(domain: "koe.transcribe", code: 1, userInfo: [
                    NSLocalizedDescriptionKey: NSLocalizedString("音声認識が許可されていません。", comment: "")
                ])))
                return
            }
            let lang = Bundle.main.preferredLocalizations.first ?? "ja"
            let locale = Locale(identifier: lang.hasPrefix("en") ? "en-US" : "ja-JP")
            guard let recognizer = SFSpeechRecognizer(locale: locale), recognizer.isAvailable else {
                self.finish(.failure(NSError(domain: "koe.transcribe", code: 2, userInfo: [
                    NSLocalizedDescriptionKey: NSLocalizedString("音声認識が利用できません。", comment: "")
                ])))
                return
            }
            let req = SFSpeechURLRecognitionRequest(url: fileURL)
            req.shouldReportPartialResults = false
            self.task = recognizer.recognitionTask(with: req) { [weak self] result, error in
                guard let self else { return }
                if let error {
                    self.finish(.failure(error))
                    return
                }
                guard let result, result.isFinal else { return }
                self.finish(.success(result.bestTranscription.formattedString))
            }
            DispatchQueue.main.async { [weak self] in
                guard let self else { return }
                self.timeoutTimer = Timer.scheduledTimer(withTimeInterval: 30, repeats: false) { [weak self] _ in
                    guard let self else { return }
                    self.task?.cancel()
                    self.finish(.failure(NSError(domain: "koe.transcribe", code: 3, userInfo: [
                        NSLocalizedDescriptionKey: NSLocalizedString("文字起こしがタイムアウトしました。", comment: "")
                    ])))
                }
            }
        }
    }

    private func finish(_ result: Result<String, Error>) {
        timeoutTimer?.invalidate(); timeoutTimer = nil
        guard let completion else { return }
        self.completion = nil
        DispatchQueue.main.async { completion(result) }
    }
}

// MARK: - Views

/// どうするか(録音後の行き先)。とどける=SendViewで共有、開発に送る=文字起こしを
/// koe.live/api/agentへ。transcriptStatusがdoneになった瞬間に一度だけ自動発火する。
enum RecordAutoAction {
    case deliver, sendToDev
}

/// 「録る」タブ本体。2026-07-20 IA刷新(本人指示「機能は増やす一方でボタンは減らして」・
/// 設計=Fable)で新設。録音起点だった旧設定内4機能(声を録ってシェア/ボイスレコーダー/
/// 一斉送信β/笑い声録音)の合流点。マイクボタン1つ+「…」メニューがトップの可視要素の全て。
/// 停止のたびに「この声を、どうする?」を聞き、行き先(とどける/開発に送る)を選ばせてから
/// 詳細画面へ自動遷移する — 選ばなければ履歴に残るだけ(のこす、は既定動作)。
struct RecordHubView: View {
    @EnvironmentObject var state: AppState
    @StateObject private var library = RecordingLibrary.shared
    @StateObject private var engine = RecorderStudioEngine()
    @State private var showDoneChoice = false
    @State private var lastEntryID: String?
    @State private var routeEntryID: String?
    @State private var routeAutoAction: RecordAutoAction?
    @State private var showSendView = false
    @State private var showBroadcastView = false

    var body: some View {
        NavigationStack {
            List {
                // まだ声を作っていない人への一度きりの案内(Fable設計「初回は登録に合流させる」)。
                // hasTokenを「じぶんの声」設定済みの代理指標として使う(専用フラグが無いため)。
                if !state.hasRegisteredVoice {
                    Section {
                        NavigationLink(destination: VoiceRegisterView()) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("まず、じぶんの声をつくりませんか").font(.subheadline.weight(.semibold))
                                Text("3分で終わります。声を登録すると、話した言葉がその声で届けられます。")
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                            .padding(.vertical, 4)
                        }
                    }
                }

                Section {
                    recordControl
                }
                if !library.entries.isEmpty {
                    Section(NSLocalizedString("録音履歴", comment: "")) {
                        ForEach(library.entries) { entry in
                            NavigationLink(destination: RecordingDetailView(entryID: entry.id)) {
                                RecordingRow(entry: entry)
                            }
                        }
                        .onDelete { idx in
                            idx.map { library.entries[$0] }.forEach { library.delete($0) }
                        }
                    }
                }

                // 隠しナビゲーション: 「どうする?」選択後にそのまま詳細画面へ進む。
                NavigationLink(isActive: routeBinding) {
                    if let id = routeEntryID {
                        RecordingDetailView(entryID: id, autoAction: routeAutoAction)
                    }
                } label: { EmptyView() }
                .hidden()
            }
            .navigationTitle(NSLocalizedString("録る", comment: ""))
            .onReceive(NotificationCenter.default.publisher(for: .koeRecordingAutoStop)) { _ in
                if engine.isRecording, let entry = engine.stop() {
                    library.add(entry)
                    startTranscription(entry)
                    lastEntryID = entry.id
                    showDoneChoice = true
                }
            }
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    // 🔴harsh-review指摘: Menu内のNavigationLinkはSwiftUIの既知の不具合で
                    // タップしても遷移しないことがある→Button+隠しNavigationLinkに置き換え。
                    Menu {
                        Button {
                            showSendView = true
                        } label: {
                            Label("文字で書いて送る", systemImage: "keyboard")
                        }
                        Button {
                            showBroadcastView = true
                        } label: {
                            Label("一斉送信（β）", systemImage: "person.3.fill")
                        }
                    } label: {
                        Image(systemName: "ellipsis.circle")
                    }
                    .accessibilityLabel(Text("その他の送り方", comment: ""))
                }
            }
            .navigationDestination(isPresented: $showSendView) { SendView() }
            .navigationDestination(isPresented: $showBroadcastView) { BroadcastView() }
            .confirmationDialog(
                NSLocalizedString("この言葉を、どうする？", comment: ""),
                isPresented: $showDoneChoice, presenting: lastEntryID
            ) { id in
                Button(NSLocalizedString("とどける", comment: "")) {
                    routeEntryID = id; routeAutoAction = .deliver
                }
                Button(NSLocalizedString("開発に送る", comment: "")) {
                    routeEntryID = id; routeAutoAction = .sendToDev
                }
                Button(NSLocalizedString("あとで", comment: ""), role: .cancel) {}
            }
        }
    }

    private var routeBinding: Binding<Bool> {
        Binding(get: { routeEntryID != nil }, set: { if !$0 { routeEntryID = nil; routeAutoAction = nil } })
    }

    private var recordControl: some View {
        VStack(spacing: 12) {
            HStack(spacing: 3) {
                ForEach(Array(engine.liveLevels.suffix(50).enumerated()), id: \.offset) { _, v in
                    Capsule()
                        .fill(engine.isRecording ? Color.red : Theme.accentColor)
                        .frame(width: 3, height: max(3, CGFloat(v) * 40))
                }
            }
            .frame(height: 44)
            .frame(maxWidth: .infinity)
            .opacity(engine.isRecording ? 1 : 0.25)
            .animation(.easeOut(duration: 0.1), value: engine.liveLevels)
            // 波形は装飾でVoiceOverには何も伝えない→隠す(harsh-review指摘)。状態は
            // 録音ボタンのラベルと経過時間で伝える。
            .accessibilityHidden(true)

            if engine.isRecording {
                Text(formatted(engine.elapsed))
                    .font(.title3.monospacedDigit())
                    .foregroundStyle(.secondary)
                    .accessibilityLabel(String(format: NSLocalizedString("録音中、%@経過", comment: ""), formatted(engine.elapsed)))
            }

            Button {
                if engine.isRecording {
                    if let entry = engine.stop() {
                        library.add(entry)
                        startTranscription(entry)
                        // 🔴2026-07-20 harsh-review指摘で発覚: ここでlastEntryID/showDoneChoiceを
                        // 立てるコードが丸ごと抜けていて、「この声を、どうする?」が一度も出ない
                        // デッドコードになっていた(ダイアログ・autoAction配線は宣言のみで未接続)。
                        lastEntryID = entry.id
                        showDoneChoice = true
                    }
                } else {
                    engine.start()
                }
            } label: {
                Image(systemName: engine.isRecording ? "stop.circle.fill" : "mic.circle.fill")
                    .font(.system(size: 64))
                    .foregroundStyle(engine.isRecording ? .red : Theme.accentColor)
            }
            .buttonStyle(.plain)
            .accessibilityLabel(engine.isRecording ? NSLocalizedString("録音を止める", comment: "") : NSLocalizedString("録音する", comment: ""))

            if let e = engine.errorText {
                Text(e).font(.footnote).foregroundStyle(.red)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 8)
    }

    private func startTranscription(_ entry: RecordingEntry) {
        var running = entry
        running.transcriptStatus = .running
        library.update(running)
        RecorderTranscriber.transcribe(fileURL: library.fileURL(for: entry)) { result in
            var updated = running
            switch result {
            case .success(let text):
                updated.transcript = text
                updated.transcriptStatus = .done
            case .failure:
                updated.transcriptStatus = .failed
            }
            library.update(updated)
        }
    }

    private func formatted(_ t: TimeInterval) -> String {
        String(format: "%d:%02d", Int(t) / 60, Int(t) % 60)
    }
}

private struct RecordingRow: View {
    let entry: RecordingEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(entry.date.formatted(date: .abbreviated, time: .shortened))
                .font(.subheadline)
            if let t = entry.transcript, !t.isEmpty {
                Text(t).font(.footnote).foregroundStyle(.secondary).lineLimit(1)
            } else if entry.transcriptStatus == .running {
                Label(NSLocalizedString("文字起こし中…", comment: ""), systemImage: "waveform")
                    .font(.footnote).foregroundStyle(.secondary)
            } else if entry.transcriptStatus == .failed {
                Text(NSLocalizedString("文字起こし失敗", comment: ""))
                    .font(.footnote).foregroundStyle(.red)
            }
            if entry.sentToDev {
                Label(NSLocalizedString("開発に送信済み", comment: ""), systemImage: "checkmark.seal.fill")
                    .font(.caption2).foregroundStyle(.green)
            }
        }
    }
}

struct RecordingDetailView: View {
    let entryID: String
    /// 「録る」タブの「この声を、どうする?」で選ばれた行き先。文字起こしが終わった
    /// 瞬間に一度だけ自動実行する(ユーザーが改めてボタンを押さなくて済むように)。
    var autoAction: RecordAutoAction? = nil

    @EnvironmentObject var state: AppState
    @ObservedObject private var library = RecordingLibrary.shared
    @StateObject private var player = AudioPlayer()
    @State private var sending = false
    @State private var sendResult: String?
    @State private var sendError: String?
    @State private var pushDeliver = false
    @State private var autoFired = false

    private var entry: RecordingEntry? { library.entries.first { $0.id == entryID } }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                if let entry {
                    Card {
                        FieldLabel(text: LocalizedStringKey("再生"), systemImage: "waveform")
                        Button {
                            togglePlay(entry)
                        } label: {
                            Label(
                                player.isPlaying ? NSLocalizedString("停止", comment: "") : NSLocalizedString("再生", comment: ""),
                                systemImage: player.isPlaying ? "pause.fill" : "play.fill"
                            )
                        }
                        .buttonStyle(PrimaryButton())
                    }

                    Card {
                        FieldLabel(text: LocalizedStringKey("文字起こし"), systemImage: "text.bubble")
                        switch entry.transcriptStatus {
                        case .running:
                            ProgressView(NSLocalizedString("文字起こし中…", comment: ""))
                        case .failed:
                            Text(NSLocalizedString("文字起こしに失敗しました。", comment: "")).foregroundStyle(.red)
                            // 🔴harsh-review指摘: 失敗しても再試行手段が無く、その録音は
                            // 聴くか消すかしかできない袋小路だった。
                            Button(NSLocalizedString("もう一度文字起こす", comment: "")) {
                                retryTranscription(entry)
                            }
                            .buttonStyle(.bordered)
                        default:
                            let t = entry.transcript ?? ""
                            Text(t.isEmpty ? NSLocalizedString("（文字起こしなし）", comment: "") : t)
                        }
                    }

                    Card {
                        FieldLabel(text: LocalizedStringKey("とどける"), systemImage: "paperplane.circle.fill")
                        Text(NSLocalizedString("この文字起こしを、声のクリップにして誰かに届けます。", comment: ""))
                            .font(.caption).foregroundStyle(.secondary)
                        NavigationLink(isActive: $pushDeliver) {
                            SendView(prefillMessage: entry.transcript ?? "")
                        } label: {
                            Text("とどける")
                        }
                        .buttonStyle(PrimaryButton())
                        .disabled((entry.transcript ?? "").trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    }

                    Card {
                        FieldLabel(text: LocalizedStringKey("開発に送る"), systemImage: "paperplane.fill")
                        Text(NSLocalizedString("この文字起こしを開発依頼として優貴に送ります(LINE/通知が届きます)。", comment: ""))
                            .font(.caption).foregroundStyle(.secondary)
                        Button {
                            Task { await sendToDev(entry) }
                        } label: {
                            if sending {
                                ProgressView().tint(.white)
                            } else {
                                Text(entry.sentToDev ? NSLocalizedString("もう一度送る", comment: "") : NSLocalizedString("開発に送る", comment: ""))
                            }
                        }
                        .buttonStyle(PrimaryButton())
                        .disabled(sending || (entry.transcript ?? "").trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                        if let sendResult {
                            Text(sendResult).font(.footnote).foregroundStyle(.green)
                        }
                        if let sendError {
                            Text(sendError).font(.footnote).foregroundStyle(.red)
                        }
                    }
                }
            }
            .padding(16)
        }
        .navigationTitle(NSLocalizedString("録音", comment: ""))
        .navigationBarTitleDisplayMode(.inline)
        .onDisappear { player.stop() }
        .onAppear { maybeAutoFire() }
        .onChange(of: entry?.transcriptStatus) { _ in maybeAutoFire() }
    }

    /// 「録る」タブの選択(autoAction)が付いていて、文字起こしが既に終わっているなら
    /// 一度だけ自動実行する。まだ実行中ならonChangeで完了を待つ。
    private func maybeAutoFire() {
        guard !autoFired, let action = autoAction, let entry, entry.transcriptStatus == .done,
              !(entry.transcript ?? "").trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        autoFired = true
        switch action {
        case .deliver:
            pushDeliver = true
        case .sendToDev:
            Task { await sendToDev(entry) }
        }
    }

    private func retryTranscription(_ entry: RecordingEntry) {
        var running = entry
        running.transcriptStatus = .running
        library.update(running)
        RecorderTranscriber.transcribe(fileURL: library.fileURL(for: entry)) { result in
            var updated = running
            switch result {
            case .success(let text):
                updated.transcript = text
                updated.transcriptStatus = .done
            case .failure:
                updated.transcriptStatus = .failed
            }
            library.update(updated)
        }
    }

    private func togglePlay(_ entry: RecordingEntry) {
        if player.isPlaying { player.stop(); return }
        guard let data = try? Data(contentsOf: library.fileURL(for: entry)) else { return }
        player.play(data: data)
    }

    private func sendToDev(_ entry: RecordingEntry) async {
        guard let text = entry.transcript, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        sending = true; sendError = nil; sendResult = nil
        defer { sending = false }
        do {
            let name = state.fromName.isEmpty ? "iOSボイスレコーダー" : state.fromName
            let r = try await state.api.sendDevRequest(text: text, name: name)
            sendResult = r.reply ?? NSLocalizedString("送りました。", comment: "")
            var updated = entry
            updated.sentToDev = true
            library.update(updated)
            UINotificationFeedbackGenerator().notificationOccurred(.success)
        } catch {
            sendError = error.localizedDescription
            UINotificationFeedbackGenerator().notificationOccurred(.error)
        }
    }
}
