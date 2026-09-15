import SwiftUI

/// One template → everyone gets their own clip, in your voice, with their own
/// name and their own link. Impossible to do by hand — this is Koe's wedge.
/// 設定のNavigationStackからpushされる前提: この画面自身はスタックを持たない。
struct BroadcastView: View {
    @EnvironmentObject var state: AppState

    @State private var template = NSLocalizedString("{name}さん、いつもありがとう。", comment: "")
    @State private var namesText = ""
    @State private var results: [BroadcastResult] = []
    @State private var isWorking = false
    @State private var progress = 0
    @State private var total = 0
    @State private var errorText: String?
    @State private var shareItem: IdentifiableURL?
    @State private var copiedAll = false   // brief "コピーしました" feedback

    /// Parsed, trimmed, de-duplicated recipient names.
    private var names: [String] { Self.parseNames(namesText) }

    /// Splits raw input on newlines / commas (JP or ASCII), trims, and de-dupes
    /// preserving order. Static so it is unit-testable.
    static func parseNames(_ raw: String) -> [String] {
        var seen = Set<String>()
        return raw
            .split(whereSeparator: { $0 == "\n" || $0 == "," || $0 == "、" })
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty && seen.insert($0).inserted }
    }

    private var canRun: Bool {
        !template.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !names.isEmpty && !isWorking
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                templateCard
                namesCard
                runButton
                if let e = errorText {
                    Text(e).font(.footnote).foregroundStyle(.red)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                if !results.isEmpty { resultsCard }
            }
            .padding(16)
        }
        .background(Color(.systemGroupedBackground))
        .navigationTitle("一斉送信（β）")
        .navigationBarTitleDisplayMode(.inline)
        .scrollDismissesKeyboard(.interactively)
        .sheet(item: $shareItem) { ShareSheet(items: [$0.url]) }
    }

    // MARK: - Cards

    private var templateCard: some View {
        Card {
            HStack {
                FieldLabel(text: "メッセージ（全員共通）", systemImage: "text.bubble.fill")
                Spacer()
                Button {
                    template += "{name}"
                } label: {
                    Label("名前を入れる", systemImage: "at")
                        .font(.caption.weight(.semibold))
                }
            }
            TextEditor(text: $template)
                .frame(minHeight: 80)
                .scrollContentBackground(.hidden)
                .koeField()
            Text("「{name}」がひとりひとりの名前に置きかわります。声＝\(state.voice.label)")
                .font(.caption).foregroundStyle(.secondary)

            FieldLabel(text: "言語（あなたの声のまま）", systemImage: "globe")
            Picker("言語", selection: $state.lang) {
                ForEach(AppLang.allCases) { Text($0.label).tag($0) }
            }
            .pickerStyle(.segmented)
        }
    }

    private var namesCard: some View {
        Card {
            FieldLabel(text: "だれに（1行に1人 / カンマ区切り）", systemImage: "person.3.fill")
            TextEditor(text: $namesText)
                .frame(minHeight: 100)
                .scrollContentBackground(.hidden)
                .koeField()
                .overlay(alignment: .topLeading) {
                    if namesText.isEmpty {
                        Text("健太郎\n愛\n村田").foregroundStyle(.secondary)
                            .padding(.horizontal, 18).padding(.vertical, 20)
                            .allowsHitTesting(false)
                    }
                }
            if !names.isEmpty {
                Text("\(names.count)人に送ります").font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    private var runButton: some View {
        Button(action: { Task { await run() } }) {
            HStack(spacing: 8) {
                if isWorking {
                    ProgressView().tint(.white)
                    Text("作成中… \(progress)/\(total)")
                } else {
                    Image(systemName: "paperplane.fill")
                    if names.isEmpty { Text("全員ぶん声をつくる") }
                    else { Text("全員ぶん声をつくる（\(names.count)人）") }
                }
            }
        }
        .buttonStyle(PrimaryButton())
        .disabled(!canRun)
        .opacity(canRun ? 1 : 0.5)
    }

    private var resultsCard: some View {
        Card {
            HStack {
                FieldLabel(text: "できた（\(results.count)人）", systemImage: "checkmark.seal.fill")
                Spacer()
                Button {
                    UIPasteboard.general.string = results
                        .map { "\($0.name): \($0.url)" }
                        .joined(separator: "\n")
                    UIImpactFeedbackGenerator(style: .light).impactOccurred()
                    copiedAll = true
                    DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { copiedAll = false }
                } label: {
                    Label(copiedAll ? LocalizedStringKey("コピーしました") : LocalizedStringKey("全部コピー"),
                          systemImage: copiedAll ? "checkmark" : "doc.on.doc")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(copiedAll ? AnyShapeStyle(Color.green) : AnyShapeStyle(Theme.accentColor))
                }
            }
            ForEach(results) { r in
                HStack(spacing: 10) {
                    Text(r.name)
                        .font(.subheadline.weight(.semibold))
                        .lineLimit(1)
                    Spacer()
                    Button {
                        UIPasteboard.general.string = r.url
                        UIImpactFeedbackGenerator(style: .light).impactOccurred()
                    } label: {
                        Image(systemName: "doc.on.doc").foregroundStyle(.secondary)
                    }
                    .accessibilityLabel(Text("リンクをコピー"))
                    Button {
                        if let u = URL(string: r.url) { shareItem = IdentifiableURL(url: u) }
                    } label: {
                        Image(systemName: "square.and.arrow.up").foregroundStyle(Theme.accentColor)
                    }
                    .accessibilityLabel(Text("共有して送る"))
                }
                .padding(.vertical, 6)
                Divider()
            }
        }
    }

    // MARK: - Action

    private func run() async {
        errorText = nil
        results = []
        isWorking = true
        progress = 0
        let targets = names
        total = targets.count
        defer { isWorking = false }

        var fails: [String] = []
        for name in targets {
            let text = template.replacingOccurrences(of: "{name}", with: name)
            do {
                let r = try await state.api.share(
                    text: text, voice: state.voice, to: name,
                    fromName: state.fromName, language: state.lang,
                    cleanup: state.craftMode == .tidy,
                    composePrompt: state.craftMode == .compose ? state.composePrompt : nil
                )
                results.append(BroadcastResult(name: name, url: r.url, mp3: r.mp3_url))
            } catch {
                fails.append(name)
            }
            progress += 1
        }
        if results.isEmpty {
            UINotificationFeedbackGenerator().notificationOccurred(.error)
            errorText = NSLocalizedString("作成できませんでした。トークンや接続をご確認ください。", comment: "")
        } else {
            UINotificationFeedbackGenerator().notificationOccurred(.success)
            if !fails.isEmpty {
                errorText = String(format: NSLocalizedString("%d人ぶん失敗しました：%@", comment: ""),
                                   fails.count, fails.joined(separator: "、"))
            }
        }
    }
}

struct BroadcastResult: Identifiable {
    let name: String
    let url: String
    let mp3: String
    var id: String { name }
}

/// Wraps a URL so it can drive `.sheet(item:)`.
struct IdentifiableURL: Identifiable {
    let url: URL
    var id: String { url.absoluteString }
}
