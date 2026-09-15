import SwiftUI

// 2026-07-20 IA刷新(本人指示「シンプルにして。機能は増やす一方でボタンは減らして」・
// 設計=Fable・実装=Sonnet)。旧「設定」タブ(1画面に約17個の操作要素)を、頻度で
// 階層化した「わたし」タブへ再構成。機能はゼロ削減、各機能はサブ画面に切り出しただけ。

/// 「わたし」タブ本体。可視要素はプロフィールカード/じぶんの声/どこでもマイク/
/// アカウントの4〜5行のみ(パーソナリティー機能は管理者トークン保有時だけ追加で1行)。
struct MeView: View {
    @EnvironmentObject var state: AppState
    @ObservedObject private var soluna = SolunaSession.shared
    @State private var showSolunaSetup = false

    var body: some View {
        NavigationStack {
            List {
                Section {
                    NavigationLink(destination: ProfileView()) {
                        HStack(spacing: 12) {
                            Circle()
                                .fill(Theme.accent)
                                .frame(width: 44, height: 44)
                                .overlay(Image(systemName: "person.fill").foregroundStyle(.white))
                            VStack(alignment: .leading, spacing: 2) {
                                Text(state.fromName.isEmpty ? NSLocalizedString("名前を設定", comment: "") : state.fromName)
                                    .font(.headline)
                                if let url = state.profileURL {
                                    Text(url.absoluteString.replacingOccurrences(of: "https://", with: ""))
                                        .font(.caption).foregroundStyle(.secondary)
                                } else {
                                    Text(NSLocalizedString("公開ページ未設定", comment: ""))
                                        .font(.caption).foregroundStyle(.secondary)
                                }
                            }
                        }
                        .padding(.vertical, 4)
                    }
                }

                Section {
                    NavigationLink(destination: VoiceRegisterView()) {
                        Label("じぶんの声", systemImage: "waveform.circle")
                    }
                } header: {
                    Text("🎙 声")
                }

                Section {
                    Toggle("どこでもマイクを使う", isOn: solunaToggle)
                    NavigationLink(destination: SolunaDetailView()) {
                        HStack {
                            Circle()
                                .fill(soluna.status == .live ? Color.green :
                                      soluna.status == .off ? Color.secondary : Color.orange)
                                .frame(width: 8, height: 8)
                            Text(soluna.status.label).font(.footnote).foregroundStyle(.secondary)
                        }
                    }
                } header: {
                    Text("🌊 どこでもマイク")
                }

                Section {
                    NavigationLink(destination: BecameFeedView()) {
                        Label("声が、形になった瞬間", systemImage: "sparkles")
                    }
                } footer: {
                    Text("声で話しかけると、内容によっては本当にJiuFlowの技になったり、家になったり、グッズになったりします。")
                }

                Section {
                    NavigationLink(destination: LiveScreen(active: true, pendingPath: .constant(nil))) {
                        Label("ライブ", systemImage: "dot.radiowaves.left.and.right")
                    }
                } header: {
                    Text("📡 ライブ")
                }

                Section {
                    NavigationLink(destination: AccountView()) {
                        Label("アカウント", systemImage: "person.badge.key")
                    }
                } header: {
                    Text("🔑 アカウント")
                }

                // 🔴harsh-review指摘: 管理者トークン保有時だけ表示すると、トークンを
                // 入力する画面(LaughRecorderView)自体がこの行の先にしか無いため、新人
                // パーソナリティーが永遠に辿り着けない鶏卵ロックになっていた。常時表示にし、
                // 未認証ならPersonalityHubView側でトークン入力を出す。
                Section {
                    NavigationLink(destination: PersonalityHubView()) {
                        Label("パーソナリティー", systemImage: "theatermasks")
                    }
                } header: {
                    Text("🎭 パーソナリティー")
                }
            }
            .navigationTitle("わたし")
            .fullScreenCover(isPresented: $showSolunaSetup) {
                SolunaView().environmentObject(state)
            }
        }
    }

    /// Toggle binding: on → connect (or open setup if no ID yet), off → stop.
    private var solunaToggle: Binding<Bool> {
        Binding(
            get: { soluna.status != .off },
            set: { on in
                if on {
                    if state.solunaId.isEmpty || state.solunaToken.isEmpty {
                        showSolunaSetup = true
                        return
                    }
                    state.solunaAutoStart = true
                    state.startSoluna()
                } else {
                    state.solunaAutoStart = false
                    SolunaSession.shared.stop()
                }
            }
        )
    }
}

/// プロフィール編集: 送り主の名前+公開ハンドル。旧「送り主の名前」「公開プロフィール」の統合
/// (どちらも"わたしは誰か"という同じ関心事だったため)。
struct ProfileView: View {
    @EnvironmentObject var state: AppState

    var body: some View {
        Form {
            Section("送り主の名前") {
                TextField("from_name (例: 優貴)", text: $state.fromName)
            }
            Section("公開プロフィール") {
                TextField("@ハンドル (例: yuki)", text: $state.handle)
                    .textInputAutocapitalization(.never)
                    .disableAutocorrection(true)
                if let url = state.profileURL {
                    Link(destination: url) {
                        Label(url.absoluteString.replacingOccurrences(of: "https://", with: ""),
                              systemImage: "rectangle.stack.fill")
                    }
                    .font(.footnote)
                } else {
                    Text("ハンドルを入れると、あなたの公開ページへのリンクがここに出ます。")
                        .font(.footnote).foregroundColor(.secondary)
                }
            }
        }
        .navigationTitle("プロフィール")
        .navigationBarTitleDisplayMode(.inline)
    }
}

/// アクセストークン管理。旧「アクセストークン」セクションをそのまま切り出し。
struct AccountView: View {
    @EnvironmentObject var state: AppState
    @State private var tokenField = ""
    @State private var savedFlash = false

    var body: some View {
        Form {
            Section("アクセストークン") {
                SecureField("Bearer トークンを入力", text: $tokenField)
                    .textInputAutocapitalization(.never)
                    .disableAutocorrection(true)
                Button("保存") {
                    state.setToken(tokenField.trimmingCharacters(in: .whitespacesAndNewlines))
                    tokenField = ""
                    savedFlash = true
                    DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { savedFlash = false }
                }
                // 空のまま押せると保存済みトークンを黙って消してしまうため無効化。
                .disabled(tokenField.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                if savedFlash {
                    Label("保存しました", systemImage: "checkmark.circle.fill")
                        .foregroundColor(.green).font(.footnote)
                }
                Label(NSLocalizedString(state.hasToken ? "設定済み" : "未設定", comment: ""),
                      systemImage: state.hasToken ? "lock.fill" : "lock.open")
                    .font(.footnote)
                    .foregroundColor(state.hasToken ? .green : .secondary)
            }
        }
        .navigationTitle("アカウント")
        .navigationBarTitleDisplayMode(.inline)
    }
}

/// どこでもマイク(SOLUNA)の詳細: ID/サーバーURL/アクセスキー/ログアウト。
/// トップの「わたし」にはトグルと状態だけを出し、細かい接続設定はここへ。
struct SolunaDetailView: View {
    @EnvironmentObject var state: AppState
    @ObservedObject private var soluna = SolunaSession.shared
    @State private var solunaKeyField = ""
    @State private var solunaKeySaved = false

    var body: some View {
        Form {
            Section {
                HStack {
                    Circle()
                        .fill(soluna.status == .live ? Color.green :
                              soluna.status == .off ? Color.secondary : Color.orange)
                        .frame(width: 10, height: 10)
                    Text(soluna.status.label).font(.footnote)
                    Spacer()
                    if !state.solunaId.isEmpty {
                        Text(state.solunaId).font(.footnote).foregroundColor(.secondary)
                    }
                }
                if let err = soluna.lastError {
                    Text(err).font(.footnote).foregroundColor(.red)
                }
                TextField("なまえ / ID (例: kenny)", text: $state.solunaId)
                    .textInputAutocapitalization(.never)
                    .disableAutocorrection(true)
                TextField("サーバーURL", text: $state.solunaURL)
                    .textInputAutocapitalization(.never)
                    .disableAutocorrection(true)
                    .keyboardType(.URL)
                SecureField("アクセスキーを入力", text: $solunaKeyField)
                    .textInputAutocapitalization(.never)
                Button("保存") {
                    TokenStore.shared.solunaToken = solunaKeyField
                    solunaKeyField = ""
                    solunaKeySaved = true
                    DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { solunaKeySaved = false }
                    if soluna.status != .off { state.startSoluna() }
                }
                .disabled(solunaKeyField.isEmpty)
                if solunaKeySaved {
                    Label("保存しました", systemImage: "checkmark.circle.fill")
                        .foregroundColor(.green).font(.footnote)
                }
                Button("ログアウト（ID・キーを消す）", role: .destructive) {
                    state.logoutSoluna()
                }
                .disabled(state.solunaId.isEmpty && TokenStore.shared.solunaToken == nil)
            } footer: {
                Text("このiPhoneが、開きっぱなしのマイクとスピーカーになります。画面ロック中も動きます。")
            }
        }
        .navigationTitle("どこでもマイク")
        .navigationBarTitleDisplayMode(.inline)
    }
}

/// 声のクローン登録。旧「声を登録」セクションをそのまま切り出し(ロジック変更なし)。
struct VoiceRegisterView: View {
    @EnvironmentObject var state: AppState
    @StateObject private var recorder = VoiceRecorder()

    @State private var phrase: String?
    @State private var regToken: String?
    @State private var regStatus: String?
    @State private var regFailed = false
    @State private var isWorking = false

    var body: some View {
        Form {
            Section("声を登録") {
                Picker("登録する声", selection: $state.voice) {
                    ForEach(Voice.allCases) { v in Text(v.label).tag(v) }
                }

                Button("登録を開始") {
                    Task { await startRegister() }
                }
                .disabled(isWorking || !state.hasToken)

                if let p = phrase {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("このフレーズを読み上げて録音してください:")
                            .font(.footnote).foregroundColor(.secondary)
                        Text(p).font(.headline)
                    }

                    Button(NSLocalizedString(recorder.isRecording ? "■ 録音を止める" : "● 録音する", comment: "")) {
                        if recorder.isRecording {
                            recorder.stop()
                        } else {
                            recorder.start()
                        }
                    }
                    .foregroundColor(recorder.isRecording ? .red : .accentColor)

                    // マイク拒否時に「押しても無反応」にならないよう理由を出す。
                    if let re = recorder.errorText {
                        Text(re).font(.footnote).foregroundColor(.red)
                    }

                    if recorder.hasRecording && !recorder.isRecording {
                        Button("録音を送信して照合") {
                            Task { await verifyRegister() }
                        }
                        .disabled(isWorking)
                    }
                }

                if let s = regStatus {
                    Text(s).font(.footnote)
                        .foregroundColor(regFailed ? .red : .green)
                }
            }
        }
        .navigationTitle("じぶんの声")
        .navigationBarTitleDisplayMode(.inline)
    }

    private func startRegister() async {
        isWorking = true
        regStatus = nil
        defer { isWorking = false }
        do {
            let r = try await state.api.registerStart(voice: state.voice)
            phrase = r.phrase
            regToken = r.token
        } catch {
            regFailed = true
            regStatus = String(format: NSLocalizedString("エラー: %@", comment: ""), error.localizedDescription)
        }
    }

    private func verifyRegister() async {
        guard let token = regToken, let b64 = recorder.base64() else {
            regFailed = true
            regStatus = NSLocalizedString("録音がありません。", comment: "")
            return
        }
        isWorking = true
        defer { isWorking = false }
        do {
            let r = try await state.api.registerVerify(token: token, audioBase64: b64)
            regFailed = !r.ok
            if r.ok { state.hasRegisteredVoice = true }
            regStatus = NSLocalizedString(
                r.ok ? "声の登録に成功しました。" : "照合に失敗しました。もう一度お試しください。", comment: "")
        } catch {
            regFailed = true
            regStatus = String(format: NSLocalizedString("エラー: %@", comment: ""), error.localizedDescription)
        }
    }
}

/// パーソナリティー(配信する側)モードのハブ。2026-07-20 本人指示「聞くほうじゃなくて、
/// 配信するほうのモードに切り替えられると、そっち側で全部できるように」で新設。
/// koe-edge側に既にある番組運営ツール(myroom=声+台本+受信箱の統合ハブ・studio=
/// 収録した声の確認/削除)をWebViewで束ね、ネイティブの笑い声録音と並べて1画面に。
struct PersonalityHubView: View {
    var body: some View {
        List {
            Section {
                NavigationLink(destination: PersonalityWebScreen(
                    url: URL(string: "https://koe.live/myroom")!, title: "番組・台本")
                ) {
                    Label("番組・台本", systemImage: "list.bullet.rectangle")
                }
            } footer: {
                Text("何を話すか・台本・受信箱をまとめて管理します。")
            }

            Section {
                NavigationLink(destination: PersonalityWebScreen(
                    url: URL(string: "https://koe.live/studio")!, title: "スタジオ")
                ) {
                    Label("スタジオ", systemImage: "waveform.circle")
                }
            } footer: {
                Text("収録した声を確認・削除します。")
            }

            Section {
                NavigationLink(destination: LaughRecorderView()) {
                    Label("笑い声・リアクション録音", systemImage: "face.smiling")
                }
            } footer: {
                Text("自分の声で笑い声やリアクションを録音して、番組のSFX素材バンクに積みます。")
            }
        }
        .navigationTitle("パーソナリティー")
        .navigationBarTitleDisplayMode(.inline)
    }
}

/// パーソナリティーハブ内のWeb埋め込み画面共通ラッパー。
private struct PersonalityWebScreen: View {
    let url: URL
    let title: String
    // 🔴harsh-review指摘: .constant(nil)だと「もう一度」がpendingPath.wrappedValueへの
    // 書き込みをno-opで飲み込み、圏外での読み込み失敗から復帰できなかった。実体のある
    // @Stateに差し替える。
    @State private var pendingPath: String?

    var body: some View {
        KoeWebScreen(url: url, basePath: url.path, active: true, pendingPath: $pendingPath)
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
    }
}
