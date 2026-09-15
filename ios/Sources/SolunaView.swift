import SwiftUI

/// 🌊 どこでもマイク onboarding + live status screen.
///
/// First launch (no ID saved): asks for a name/ID — and an access key only if
/// the app has no Koe token yet — then starts streaming right away (the mic
/// permission prompt appears in this flow, mirroring mic.html on the web).
/// Once set up, the app auto-connects on launch and this screen just shows
/// status with a stop/start control.
struct SolunaView: View {
    @EnvironmentObject var state: AppState
    @ObservedObject private var soluna = SolunaSession.shared
    @Environment(\.dismiss) private var dismiss

    @State private var idField = ""
    @State private var keyField = ""
    @State private var hint: String?

    var body: some View {
        NavigationView {
            ScrollView {
                VStack(spacing: 24) {
                    statusOrb
                        .padding(.top, 32)

                    Text(statusLine)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)

                    if state.solunaId.isEmpty {
                        setupCard
                    } else {
                        controlCard
                    }

                    if let hint {
                        Text(hint)
                            .font(.footnote)
                            .foregroundColor(.red)
                            .multilineTextAlignment(.center)
                    }
                    if let err = soluna.lastError {
                        Text(err)
                            .font(.footnote)
                            .foregroundColor(.red)
                            .multilineTextAlignment(.center)
                    }

                    Text("このiPhoneが、開きっぱなしのマイクとスピーカーになります。画面ロック中も動きます。")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 8)
                }
                .padding(20)
            }
            .navigationTitle("🌊 どこでもマイク")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("閉じる") { dismiss() }
                }
            }
            .onAppear { idField = state.solunaId }
        }
    }

    // MARK: - Pieces

    private var isOn: Bool { soluna.status != .off }

    private var statusOrb: some View {
        ZStack {
            Circle()
                .fill(isOn ? AnyShapeStyle(Theme.accent) : AnyShapeStyle(Color(.tertiarySystemFill)))
                .frame(width: 120, height: 120)
                .shadow(color: isOn ? Theme.accentColor.opacity(0.5) : .clear, radius: 24)
            Image(systemName: isOn ? "waveform" : "mic.slash")
                .font(.system(size: 44))
                .foregroundStyle(isOn ? .white : .secondary)
        }
    }

    private var statusLine: String {
        if soluna.status == .live, !state.solunaId.isEmpty {
            return String(format: NSLocalizedString("%@ でつないでいます", comment: ""), state.solunaId)
        }
        return soluna.status.label
    }

    /// First run: name/ID (+ access key when the app has no Koe token yet).
    private var setupCard: some View {
        Card {
            FieldLabel(text: "なまえ / ID", systemImage: "person.fill")
            TextField("なまえ / ID (例: kenny)", text: $idField)
                .textInputAutocapitalization(.never)
                .disableAutocorrection(true)
                .koeField()

            if state.solunaNeedsKey {
                FieldLabel(text: "アクセスキー", systemImage: "key.fill")
                SecureField("アクセスキーを入力", text: $keyField)
                    .textInputAutocapitalization(.never)
                    .koeField()
            } else {
                Text("Koeのトークンをアクセスキーとして使います。")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }

            Button("はじめる") { begin() }
                .buttonStyle(PrimaryButton())
        }
    }

    /// Returning user: one-tap start/stop.
    private var controlCard: some View {
        Card {
            // ternaryはStringになり非ローカライズinitを踏むため、キーを明示する。
            Button(isOn ? LocalizedStringKey("とめる") : LocalizedStringKey("はじめる")) {
                if isOn {
                    SolunaSession.shared.stop()
                    state.solunaAutoStart = false
                } else {
                    state.solunaAutoStart = true
                    state.startSoluna()
                }
            }
            .buttonStyle(PrimaryButton())

            Button("ログアウト（ID・キーを消す）") {
                state.logoutSoluna()
                idField = ""
                keyField = ""
            }
            .font(.footnote)
            .foregroundColor(.red)
            .frame(maxWidth: .infinity)
        }
    }

    private func begin() {
        hint = nil
        let id = idField.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !id.isEmpty else {
            hint = NSLocalizedString("なまえ / ID を入れてください。", comment: "")
            return
        }
        let key = keyField.trimmingCharacters(in: .whitespacesAndNewlines)
        if !key.isEmpty {
            TokenStore.shared.solunaToken = key
        }
        guard !state.solunaToken.isEmpty else {
            hint = NSLocalizedString("アクセスキーを入れてください。", comment: "")
            return
        }
        state.solunaId = id
        state.solunaAutoStart = true
        state.startSoluna()   // tap-initiated, so the mic prompt appears here
        keyField = ""
    }
}
