import SwiftUI

// 2026-07-20 本人指示「スマホにもその機能つけてね」— koe-edge Web版 /record-laugh
// (パーソナリティーが笑い声・リアクションを録音し live/laughs/ バンクに積む機能)の
// iOS移植。既存の VoiceRecorder.swift(声登録用の使い捨て一時ファイル録音)をそのまま
// 再利用し、新しい録音エンジンは作らない。API契約は APIClient.laughList/laughRecord
// (koe.live, VOICES_ADMIN_TOKEN 必須 — TokenStore.laughAdminToken に別途保存)。

private let laughVoices: [(id: String, label: String)] = [
    ("yuki", "優貴"), ("kentaro", "健太郎"), ("ryozo", "良蔵"), ("bb", "ばばちゃん")
]

struct LaughRecorderView: View {
    @State private var adminTokenField = ""
    @State private var savedAdminToken = TokenStore.shared.laughAdminToken ?? ""
    @State private var voiceID = laughVoices[0].id
    @State private var items: [LaughItem] = []
    @State private var isLoading = false
    @State private var errorText: String?
    @State private var recordingKey: String?   // which item's row is mid-record
    @StateObject private var recorder = VoiceRecorder()
    @State private var uploadingKey: String?
    @State private var flashKey: String?        // brief "保存しました" per row

    private var hasAdminToken: Bool { !savedAdminToken.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }

    var body: some View {
        Form {
            if !hasAdminToken {
                Section {
                    SecureField(NSLocalizedString("管理者トークン", comment: ""), text: $adminTokenField)
                        .textInputAutocapitalization(.never)
                        .disableAutocorrection(true)
                    Button(NSLocalizedString("保存", comment: "")) {
                        let t = adminTokenField.trimmingCharacters(in: .whitespacesAndNewlines)
                        TokenStore.shared.laughAdminToken = t
                        savedAdminToken = t
                        adminTokenField = ""
                    }
                    .disabled(adminTokenField.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                } footer: {
                    Text(NSLocalizedString("この機能はパーソナリティー限定です。管理者トークンが必要です(優貴に聞いてください)。", comment: ""))
                }
            } else {
                Section(NSLocalizedString("声の人", comment: "")) {
                    Picker(NSLocalizedString("声の人", comment: ""), selection: $voiceID) {
                        ForEach(laughVoices, id: \.id) { v in
                            Text(v.label).tag(v.id)
                        }
                    }
                    .pickerStyle(.segmented)
                    .onChange(of: voiceID) { _ in Task { await load() } }
                }

                Section {
                    if isLoading {
                        HStack { Spacer(); ProgressView(); Spacer() }
                    }
                    ForEach(items) { item in
                        laughRow(item)
                    }
                } header: {
                    Text(NSLocalizedString("笑い声・リアクション", comment: ""))
                } footer: {
                    Text(NSLocalizedString("録音は自分の声だけ。そのまま番組のSFX素材として使われます。", comment: ""))
                }

                if let errorText {
                    Section {
                        Text(errorText).foregroundColor(.red).font(.footnote)
                    }
                }
            }
        }
        .navigationTitle(NSLocalizedString("笑い声・リアクション録音", comment: ""))
        .task { if hasAdminToken { await load() } }
        .onAppear {
            NotificationCenter.default.post(name: .koeStopAllAudio, object: nil)
        }
    }

    @ViewBuilder
    private func laughRow(_ item: LaughItem) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(item.label).font(.body)
                Spacer()
                if item.recorded {
                    Image(systemName: "checkmark.circle.fill").foregroundColor(.green)
                }
            }
            Text(item.prompt).font(.caption).foregroundColor(.secondary)

            HStack {
                if recordingKey == item.key {
                    Button(role: .destructive) {
                        stopAndUpload(item)
                    } label: {
                        Label(NSLocalizedString("停止して保存", comment: ""), systemImage: "stop.circle.fill")
                    }
                } else {
                    Button {
                        startRecording(item)
                    } label: {
                        Label(NSLocalizedString("録音する", comment: ""), systemImage: "mic.circle")
                    }
                    .disabled(recordingKey != nil || uploadingKey != nil)
                }
                if uploadingKey == item.key {
                    ProgressView().padding(.leading, 6)
                }
                if flashKey == item.key {
                    Label(NSLocalizedString("保存しました", comment: ""), systemImage: "checkmark")
                        .font(.caption).foregroundColor(.green)
                }
            }
            if let err = recorder.errorText, recordingKey == item.key {
                Text(err).font(.caption).foregroundColor(.red)
            }
        }
        .padding(.vertical, 4)
    }

    private func startRecording(_ item: LaughItem) {
        NotificationCenter.default.post(name: .koeStopAllAudio, object: nil)
        recordingKey = item.key
        recorder.start()
    }

    private func stopAndUpload(_ item: LaughItem) {
        recorder.stop()
        recordingKey = nil
        guard let b64 = recorder.base64(), !b64.isEmpty else {
            errorText = NSLocalizedString("録音できていませんでした。もう一度どうぞ。", comment: "")
            return
        }
        uploadingKey = item.key
        errorText = nil
        Task {
            do {
                _ = try await APIClient().laughRecord(
                    voice: voiceID, type: item.key,
                    adminToken: savedAdminToken,
                    audioBase64Full: "data:audio/mp4;base64," + b64
                )
                await MainActor.run {
                    uploadingKey = nil
                    flashKey = item.key
                    DispatchQueue.main.asyncAfter(deadline: .now() + 1.6) { flashKey = nil }
                }
                await load()
            } catch {
                await MainActor.run {
                    uploadingKey = nil
                    errorText = error.localizedDescription
                }
            }
        }
    }

    private func load() async {
        isLoading = true
        errorText = nil
        do {
            let list = try await APIClient().laughList(voice: voiceID, adminToken: savedAdminToken)
            await MainActor.run { items = list; isLoading = false }
        } catch {
            await MainActor.run { isLoading = false; errorText = error.localizedDescription }
        }
    }
}
