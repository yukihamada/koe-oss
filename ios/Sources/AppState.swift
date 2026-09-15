import Foundation
import Combine

/// Shared app state: currently selected voice and the persisted "from" name.
final class AppState: ObservableObject {
    @Published var voice: Voice {
        didSet { UserDefaults.standard.set(voice.rawValue, forKey: "selectedVoice") }
    }
    @Published var fromName: String {
        didSet { UserDefaults.standard.set(fromName, forKey: "fromName") }
    }
    @Published var lang: AppLang {
        didSet { UserDefaults.standard.set(lang.rawValue, forKey: "lang") }
    }
    /// How the message is crafted from what you said.
    @Published var craftMode: CraftMode {
        didSet { UserDefaults.standard.set(craftMode.rawValue, forKey: "craftMode") }
    }
    /// Voice prompt: the instruction used when craftMode == .compose.
    @Published var composePrompt: String {
        didSet { UserDefaults.standard.set(composePrompt, forKey: "composePrompt") }
    }
    /// How background music is applied to the voice clip.
    @Published var bgm: BGMMode {
        didSet { UserDefaults.standard.set(bgm.rawValue, forKey: "bgmMode") }
    }
    /// Public profile handle for koe.live/<handle> (声の作品集). Empty = not set.
    @Published var handle: String {
        didSet { UserDefaults.standard.set(handle, forKey: "koeHandle") }
    }
    /// Mirrors the keychain token so SwiftUI views update when it changes.
    @Published var hasToken: Bool
    /// True once /voice/register/verify has succeeded at least once. Drives the
    /// 「まず、じぶんの声をつくりませんか」nudge on the 録る tab(2026-07-20 IA刷新)。
    @Published var hasRegisteredVoice: Bool {
        didSet { UserDefaults.standard.set(hasRegisteredVoice, forKey: "hasRegisteredVoice") }
    }

    // MARK: - 🌊 どこでもマイク (SOLUNA)

    /// Who this device is (`&node=<id>` on the push URL). Empty = not set up.
    @Published var solunaId: String {
        didSet { UserDefaults.standard.set(solunaId, forKey: "solunaId") }
    }
    /// SOLUNA server base URL. Must use the secure WebSocket scheme (SolunaSession rejects the plaintext one — マイク音声を平文で送らない).
    @Published var solunaURL: String {
        didSet { UserDefaults.standard.set(solunaURL, forKey: "solunaURL") }
    }
    /// When true, the session reconnects automatically on the next launch.
    @Published var solunaAutoStart: Bool {
        didSet { UserDefaults.standard.set(solunaAutoStart, forKey: "solunaAutoStart") }
    }

    static let defaultSolunaURL = "wss://koe-soluna.chatweb.ai"

    /// Access key for SOLUNA: the explicit key if one was entered, otherwise
    /// the main Koe token already in the app (so no key entry is needed).
    var solunaToken: String {
        TokenStore.shared.solunaToken ?? TokenStore.shared.token ?? ""
    }

    /// True when onboarding must ask for an access key (no key of any kind).
    var solunaNeedsKey: Bool { solunaToken.isEmpty }

    /// Starts (or restarts) the SOLUNA session with the saved settings.
    func startSoluna() {
        SolunaSession.shared.start(urlString: solunaURL, token: solunaToken, node: solunaId)
    }

    /// Logs out of SOLUNA: stops the session and clears the ID + explicit key
    /// (the main Koe token is left untouched).
    func logoutSoluna() {
        SolunaSession.shared.stop()
        solunaAutoStart = false
        solunaId = ""
        TokenStore.shared.solunaToken = nil
    }

    let api = APIClient()

    init() {
        let raw = UserDefaults.standard.string(forKey: "selectedVoice") ?? Voice.yuki.rawValue
        voice = Voice(rawValue: raw) ?? .yuki
        fromName = UserDefaults.standard.string(forKey: "fromName") ?? ""
        lang = AppLang(rawValue: UserDefaults.standard.string(forKey: "lang") ?? "ja") ?? .ja
        craftMode = CraftMode(rawValue: UserDefaults.standard.string(forKey: "craftMode") ?? "tidy") ?? .tidy
        composePrompt = UserDefaults.standard.string(forKey: "composePrompt")
            ?? NSLocalizedString("丁寧で温かいメッセージにして", comment: "default compose prompt")
        bgm = BGMMode(rawValue: UserDefaults.standard.string(forKey: "bgmMode") ?? "none") ?? .none
        handle = UserDefaults.standard.string(forKey: "koeHandle") ?? ""
        solunaId = UserDefaults.standard.string(forKey: "solunaId") ?? ""
        solunaURL = UserDefaults.standard.string(forKey: "solunaURL") ?? AppState.defaultSolunaURL
        solunaAutoStart = UserDefaults.standard.bool(forKey: "solunaAutoStart")
        hasRegisteredVoice = UserDefaults.standard.bool(forKey: "hasRegisteredVoice")
        hasToken = (TokenStore.shared.token?.isEmpty == false)
        // First-launch convenience: seed the token from the build-time secret
        // so a personal dev build works without manual entry.
        if !hasToken, !Secrets.seedToken.isEmpty {
            TokenStore.shared.token = Secrets.seedToken
            hasToken = true
        }
        // 🔴 移行救済(2026-07-20): hasRegisteredVoiceはこのビルドで新設したフラグなので、
        // 既にハンドルを持っている既存ユーザーは(このフラグが立つ前に登録済みなのに)false
        // のまま→「録る」タブに「まず、じぶんの声をつくりませんか」が誤って出てしまう。
        // 公開ハンドルを持っている=何らかの形でオンボード済みとみなし、一度だけ救済する。
        if !hasRegisteredVoice, !handle.isEmpty {
            hasRegisteredVoice = true
        }
    }

    func setToken(_ value: String) {
        TokenStore.shared.token = value
        hasToken = (TokenStore.shared.token?.isEmpty == false)
    }

    /// Public profile URL koe.live/<handle>, or nil if the handle isn't usable yet.
    var profileURL: URL? {
        let h = AppState.normalizeHandle(handle)
        guard h.count >= 2 else { return nil }
        return URL(string: "https://koe.live/\(h)")
    }

    /// koe.live/to/<handle> — lets anyone (even without Koe) send a voice reply
    /// back that lands in this user's inbox. nil if the handle isn't usable yet.
    var replyURL: URL? {
        let h = AppState.normalizeHandle(handle)
        guard h.count >= 2 else { return nil }
        return URL(string: "https://koe.live/to/\(h)")
    }

    /// Server rule: lowercased, leading @ stripped, only [a-z0-9_], max 20.
    static func normalizeHandle(_ raw: String) -> String {
        var s = raw.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
        if s.hasPrefix("@") { s.removeFirst() }
        let filtered = s.filter { c in
            (c.isASCII && c.isLetter) || (c.isASCII && c.isNumber) || c == "_"
        }
        return String(filtered.prefix(20))
    }
}
