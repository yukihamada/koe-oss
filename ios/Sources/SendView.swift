import SwiftUI

// 🔻 2026-07-14: タブからは撤去(/live・/appのWeb送信パネルに機能重複)。ただし
// Koe外の相手にもiOS共有シートでそのまま送れる唯一の経路なので、設定内
// 「声を録ってシェア」から到達可能なまま維持(harsh-review指摘: 削るとKoeを
// 使っていない相手への声の拡散導線=growth loopが消える)。
// ⚠ 設定のNavigationStackからpushされる前提: この画面自身はスタックを持たない。

/// The fast path is one big "tap to talk" button: tap, speak, tap again → the
/// voice clip is generated, auto-played, and ready to share in a single tap.
/// Recipient / voice / typing live in the cards below.
struct SendView: View {
    @EnvironmentObject var state: AppState
    @StateObject private var speech = SpeechManager()

    @State private var recipient = ""
    @State private var message: String
    @State private var result: ShareResponse?

    /// 「録る」タブから文字起こし済みのテキストを持ち込んで開く場合に使う
    /// (例: 録音後「とどける」を選ぶと、その文字起こしがここに入った状態で開く)。
    init(prefillMessage: String = "") {
        _message = State(initialValue: prefillMessage)
    }
    @State private var isSending = false
    @State private var errorText: String?
    @State private var showShare = false
    @State private var pulse = false       // ripple animation while generating
    @State private var craftStep = 0       // cycles the playful waiting captions
    @State private var copiedLink = false  // brief "コピーしました" feedback

    /// Playful captions cycled while the clip is being generated (so the wait
    /// isn't boring).
    private let craftSteps = [
        NSLocalizedString("🎙 声をこねています…", comment: ""),
        NSLocalizedString("✨ ことばを整えています…", comment: ""),
        NSLocalizedString("🔥 あなたの声にしています…", comment: ""),
        NSLocalizedString("🎧 もうすぐ、できます…", comment: "")
    ]
    private let tick = Timer.publish(every: 1.4, on: .main, in: .common).autoconnect()

    private var trimmed: String { message.trimmingCharacters(in: .whitespacesAndNewlines) }
    private var canSend: Bool { !trimmed.isEmpty && !isSending }

    var body: some View {
        ScrollView {
            VStack(spacing: 18) {
                talkHero

                if let r = result { resultCard(r) }
                if let e = errorText {
                    Text(e)
                        .font(.footnote)
                        .foregroundStyle(.red)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }

                advancedSection
            }
            .padding(16)
        }
        .background(Color(.systemGroupedBackground))
        .navigationTitle("声を録ってシェア")
        .navigationBarTitleDisplayMode(.inline)
        .scrollDismissesKeyboard(.interactively)
        .sheet(isPresented: $showShare) {
            if let r = result, let link = URL(string: r.url) {
                // ハンドル設定済みなら返信リンクも一緒に共有(相手がそのまま声で返信できるように)。
                let items: [Any] = state.replyURL.map { [link, $0] } ?? [link]
                ShareSheet(items: items)
            }
        }
        .onAppear { speech.onFinal = handleDictation }
        .onChange(of: speech.partial) { new in
            if speech.isListening && !new.isEmpty { message = new }
        }
        .onDisappear { speech.stop() }
    }

    // MARK: - Fast path: hold to talk

    private var talkHero: some View {
        VStack(spacing: 14) {
            Text(heroTitle)
                .font(.headline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .animation(.default, value: heroTitle)

            Button(action: toggleTalk) {
                ZStack {
                    if isSending {
                        ForEach(0..<3, id: \.self) { i in
                            Circle()
                                .stroke(Theme.accentColor.opacity(0.55), lineWidth: 3)
                                .frame(width: 180, height: 180)
                                .scaleEffect(pulse ? 1.55 : 0.9)
                                .opacity(pulse ? 0 : 0.6)
                                .animation(.easeOut(duration: 1.8).repeatForever(autoreverses: false)
                                    .delay(Double(i) * 0.6), value: pulse)
                        }
                    }
                    Circle()
                        .fill(speech.isListening ? AnyShapeStyle(Color.red) : AnyShapeStyle(Theme.accent))
                        .frame(width: 180, height: 180)
                        .shadow(color: Theme.accentColor.opacity(0.4),
                                radius: speech.isListening ? 24 : 12)
                        .scaleEffect(speech.isListening ? 1.06 : 1)
                        .animation(.spring(response: 0.3, dampingFraction: 0.6), value: speech.isListening)
                    if isSending {
                        Image(systemName: "waveform")
                            .font(.system(size: 60))
                            .foregroundStyle(.white)
                            .scaleEffect(pulse ? 1.12 : 0.9)
                            .opacity(pulse ? 1 : 0.7)
                            .animation(.easeInOut(duration: 0.7).repeatForever(autoreverses: true), value: pulse)
                    } else {
                        Image(systemName: speech.isListening ? "stop.fill" : "mic.fill")
                            .font(.system(size: 64))
                            .foregroundStyle(.white)
                    }
                }
            }
            .buttonStyle(.plain)
            .disabled(isSending)
            .accessibilityLabel(Text(heroTitle))
            .accessibilityAddTraits(.isButton)
            // pulseを毎回リセットしないと、2回目以降のリップルが再生されない
            // (repeatForeverはpulseの変化でしか始まらないため)。
            .onChange(of: isSending) { sending in pulse = sending }
            .onReceive(tick) { _ in if isSending { craftStep += 1 } }

            // マイク/音声認識が拒否されていると以前は「押しても無反応」だった。
            // 理由をその場に出す(harsh-review指摘)。
            if let se = speech.errorText, !speech.isListening, !isSending {
                Text(se)
                    .font(.footnote)
                    .foregroundStyle(.red)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal)
            }

            if !trimmed.isEmpty && !speech.isListening {
                Text("「\(trimmed)」")
                    .font(.subheadline)
                    .foregroundStyle(.primary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 12)
    }

    private var heroTitle: String {
        if isSending { return craftSteps[craftStep % craftSteps.count] }
        if speech.isListening { return NSLocalizedString("聞いています（もう一度タップで送る）", comment: "") }
        return NSLocalizedString("タップして話す", comment: "")
    }

    /// Tap once to start listening; tap again to stop and auto-generate the clip.
    private func toggleTalk() {
        guard !isSending else { return }
        if speech.isListening {
            speech.stop()
            // Let the final partial settle, then send. The server LLM splits
            // "AにBって送って" into recipient + message (parseCommand).
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) {
                if canSend { Task { await send(parseCommand: true) } }
            }
        } else {
            result = nil
            errorText = nil
            if speech.authorized {
                speech.start()
            } else {
                speech.requestAuth { speech.start() }
            }
        }
    }

    // MARK: - Result

    private func resultCard(_ r: ShareResponse) -> some View {
        Card {
            FieldLabel(text: "できた声", systemImage: "checkmark.seal.fill")
            if let mp3 = URL(string: r.mp3_url) {
                VoiceResultPlayer(mp3URL: mp3)
            }
            Button {
                showShare = true
            } label: {
                Label("共有して送る", systemImage: "square.and.arrow.up")
            }
            .buttonStyle(PrimaryButton())

            Button {
                UIPasteboard.general.string = copyText(for: r)
                UIImpactFeedbackGenerator(style: .light).impactOccurred()
                copiedLink = true
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { copiedLink = false }
            } label: {
                // ternaryはStringになりLabel(String)は非ローカライズ initを踏むので、キーを明示する。
                Label(copiedLink ? LocalizedStringKey("コピーしました") : LocalizedStringKey("リンクをコピー"),
                      systemImage: copiedLink ? "checkmark" : "doc.on.doc")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(copiedLink ? AnyShapeStyle(Color.green) : AnyShapeStyle(.primary))
                    .frame(maxWidth: .infinity, minHeight: 44)
                    .background(Theme.field, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    .animation(.default, value: copiedLink)
            }
            .buttonStyle(.plain)

            // ハンドル設定済みなら、相手が声で返信できるリンクを一緒に案内する。
            // 返信は koe.live/to/<handle> 経由でこちらの受信箱(/box)に届く(既存の声のポスト機能を流用)。
            if let reply = state.replyURL {
                Text("送った相手は、このリンクから声で返信できます。届いた返信は受信箱に入ります。")
                    .font(.caption).foregroundStyle(.secondary)
                Link(destination: reply) {
                    Text(reply.absoluteString.replacingOccurrences(of: "https://", with: ""))
                }
                .font(.caption.weight(.semibold))
            } else {
                Text("「わたし」＞「プロフィール」でハンドルを登録すると、相手が声で返信できるリンクも一緒に送れるようになります。")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    /// Share/copy text: the voice clip link, plus (if the sender has a handle) a
    /// second link the recipient can use to talk back — landing in /box.
    private func copyText(for r: ShareResponse) -> String {
        guard let reply = state.replyURL else { return r.url }
        return r.url + "\n\n" + String(format: NSLocalizedString("🎙 返信はこちらから: %@", comment: ""), reply.absoluteString)
    }


    // MARK: - Open controls (always visible: typing / voice / recipient)

    private var advancedSection: some View {
        VStack(spacing: 16) {
            Card {
                FieldLabel(text: "メッセージの作り方", systemImage: "wand.and.stars")
                Picker("作り方", selection: $state.craftMode) {
                    ForEach(CraftMode.allCases) { Text($0.label).tag($0) }
                }
                .pickerStyle(.segmented)
                if state.craftMode == .compose {
                    Text("声のプロンプト（どう作るか）")
                        .font(.caption).foregroundStyle(.secondary)
                    TextField("例: 丁寧に / 短く / 感謝を込めて", text: $state.composePrompt)
                        .koeField()
                    Text("言った内容をこの指示で“送る文”に作りかえます。")
                        .font(.caption2).foregroundStyle(.secondary)
                } else if state.craftMode == .tidy {
                    Text("言いよどみを消して聴きやすく整えます（意味はそのまま）。")
                        .font(.caption2).foregroundStyle(.secondary)
                }
            }

            Card {
                FieldLabel(text: "文字で書いて送る", systemImage: "text.bubble.fill")
                TextEditor(text: $message)
                    .frame(minHeight: 90)
                    .scrollContentBackground(.hidden)
                    .koeField()
                    .overlay(alignment: .topLeading) {
                        if message.isEmpty {
                            Text("ここに入力してもOK")
                                .foregroundStyle(.secondary)
                                .padding(.horizontal, 18).padding(.vertical, 20)
                                .allowsHitTesting(false)
                        }
                    }
                Button(action: { Task { await send() } }) {
                    HStack(spacing: 8) {
                        if isSending { ProgressView().tint(.white) }
                        else { Image(systemName: "paperplane.fill") }
                        if isSending { Text("生成中…") } else { Text("声にする") }
                    }
                }
                .buttonStyle(PrimaryButton())
                .disabled(!canSend)
                .opacity(canSend ? 1 : 0.5)
            }

            Card {
                FieldLabel(text: "どの声で", systemImage: "waveform")
                HStack(spacing: 10) {
                    ForEach(Voice.allCases) { v in
                        let selected = state.voice == v
                        Button { state.voice = v } label: {
                            Text(v.label)
                                .font(.subheadline.weight(.semibold))
                                .frame(maxWidth: .infinity, minHeight: 44)
                                .foregroundStyle(selected ? .white : .primary)
                                .background {
                                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                                        .fill(selected ? AnyShapeStyle(Theme.accent) : AnyShapeStyle(Theme.field))
                                }
                        }
                        .buttonStyle(.plain)
                    }
                }

                FieldLabel(text: "言語（あなたの声のまま）", systemImage: "globe")
                Picker("言語", selection: $state.lang) {
                    ForEach(AppLang.allCases) { Text($0.label).tag($0) }
                }
                .pickerStyle(.segmented)
                if state.lang != .ja {
                    Text("日本語で話す/書くと、\(state.lang.label) に翻訳してあなたの声で話します。")
                        .font(.caption).foregroundStyle(.secondary)
                }

                FieldLabel(text: "BGM（任意）", systemImage: "music.note")
                Picker("BGM", selection: $state.bgm) {
                    ForEach(BGMMode.allCases) { Text($0.label).tag($0) }
                }
                .pickerStyle(.segmented)
                if state.bgm != .none {
                    Text("あなたの声のバックグラウンドにBGMが流れます。")
                        .font(.caption).foregroundStyle(.secondary)
                }

                FieldLabel(text: "だれに（任意）", systemImage: "person.fill")
                TextField("あつめ / @account", text: $recipient)
                    .textInputAutocapitalization(.never)
                    .disableAutocorrection(true)
                    .koeField()
            }
        }
    }

    // MARK: - Actions

    /// Spoken text just becomes the message. Interpreting "AにBって送って" into
    /// recipient + message is done by the LLM on the server (parseCommand), not
    /// by rules here.
    private func handleDictation(_ text: String) {
        message = text
    }

    /// parseCommand=true asks the server to understand "AにBって送って" and split
    /// recipient + message via the LLM (used for the voice/talk path).
    private func send(parseCommand: Bool = false) async {
        speech.stop()
        errorText = nil
        result = nil
        isSending = true
        defer { isSending = false }
        do {
            let r = try await state.api.share(
                text: message,
                voice: state.voice,
                to: recipient,
                fromName: state.fromName,
                language: state.lang,
                cleanup: state.craftMode == .tidy,
                composePrompt: state.craftMode == .compose ? state.composePrompt : nil,
                parseCommand: parseCommand
            )
            // Reflect a recipient the server understood from speech.
            if let t = r.to, !t.isEmpty { recipient = t }
            result = r
            UINotificationFeedbackGenerator().notificationOccurred(.success)
        } catch {
            UINotificationFeedbackGenerator().notificationOccurred(.error)
            errorText = error.localizedDescription
        }
    }
}
