import Foundation

/// Identifies a clonable voice exposed by the backend.
enum Voice: String, CaseIterable, Identifiable {
    case yuki
    case kentaro

    var id: String { rawValue }

    /// Display label shown in the picker.
    var label: String {
        switch self {
        case .yuki: return NSLocalizedString("優貴 (yuki)", comment: "")
        case .kentaro: return NSLocalizedString("健太郎 (kentaro)", comment: "")
        }
    }

    /// The `user_id` the backend expects for this voice.
    var userId: String { rawValue }
}

/// Output language. Non-Japanese options translate the text first, then speak it
/// in the same cloned voice.
enum AppLang: String, CaseIterable, Identifiable {
    case ja, en, pt

    var id: String { rawValue }

    var label: String {
        switch self {
        case .ja: return "🇯🇵 日本語"
        case .en: return "🇺🇸 English"
        case .pt: return "🇧🇷 Português"
        }
    }

    /// `translate_to` value for the API; nil when no translation is needed.
    var translateTo: String? { self == .ja ? nil : rawValue }
}

/// How the spoken/typed text becomes the outgoing message.
enum CraftMode: String, CaseIterable, Identifiable {
    case raw      // send as-is
    case tidy     // faithful cleanup (fillers/punctuation)
    case compose  // AI rewrites per the voice prompt

    var id: String { rawValue }
    var label: String {
        switch self {
        case .raw: return NSLocalizedString("そのまま", comment: "")
        case .tidy: return NSLocalizedString("整える", comment: "")
        case .compose: return NSLocalizedString("まかせる", comment: "")
        }
    }
}

/// Errors surfaced from the API layer.
enum APIError: LocalizedError {
    case missingToken
    case badStatus(Int, String)
    case decoding
    case badURL
    case empty

    var errorDescription: String? {
        switch self {
        case .missingToken:
            return NSLocalizedString("アクセストークンが未設定です。「わたし」＞「アカウント」で入力してください。", comment: "")
        case .badStatus(let code, _):
            switch code {
            case 401, 403:
                return NSLocalizedString("声を作る権限がありません。「わたし」＞「アカウント」でトークンをご確認ください。", comment: "")
            case 429:
                return NSLocalizedString("少し混み合っています。数秒おいてもう一度お試しください。", comment: "")
            case 500...599:
                return NSLocalizedString("サーバーが混み合っています。少し待ってからお試しください。", comment: "")
            default:
                return String(format: NSLocalizedString("うまく送れませんでした (%d)。もう一度お試しください。", comment: ""), code)
            }
        case .decoding:
            return NSLocalizedString("応答の解析に失敗しました。", comment: "")
        case .badURL:
            return NSLocalizedString("URL が不正です。", comment: "")
        case .empty:
            return NSLocalizedString("応答が空です。", comment: "")
        }
    }
}

// MARK: - Response models

struct ShareResponse: Decodable {
    let url: String
    let mp3_url: String
    let id: String
    let to: String?
}

struct RegisterStartResponse: Decodable {
    let token: String
    let phrase: String
}

struct RegisterVerifyResponse: Decodable {
    let ok: Bool
}

/// One reaction type from GET /api/laugh/list (koe.live, admin-gated).
struct LaughItem: Decodable, Identifiable {
    let key: String
    let label: String
    let prompt: String
    let recorded: Bool
    var id: String { key }
}

struct LaughListResponse: Decodable {
    let ok: Bool
    let items: [LaughItem]
}

struct LaughRecordResponse: Decodable {
    let ok: Bool
    let key: String?
}

/// Response from POST /api/agent — the same dev-request pipeline LINE「依頼」uses.
struct AgentRequestResponse: Decodable {
    let kind: String?
    let reply: String?
    let req_id: String?
}

/// One row from GET /api/became/recent — a voice that turned into a real JiuFlow
/// technique / bim.house building / MU product. Public, no auth (mirrors the
/// already-public /became/<id> page).
struct BecameItem: Decodable, Identifiable {
    let id: String
    let kind: String       // "mu" | "jiuflow" | "bimhouse"
    let title: String
    let heard: String
    let ts: Double
    let url: String

    var icon: String {
        switch kind {
        case "mu": return "🛍"
        case "jiuflow": return "🥋"
        default: return "🏠"
        }
    }
}

struct BecameRecentResponse: Decodable {
    let ok: Bool
    let items: [BecameItem]
}

/// Thin async URLSession client. No external dependencies.
struct APIClient {
    static let baseURL = URL(string: "https://voice.koe.live")!

    /// Resolves the bearer token from persisted settings.
    private func token() throws -> String {
        guard let t = TokenStore.shared.token, !t.isEmpty else {
            throw APIError.missingToken
        }
        return t
    }

    private func request(path: String, method: String = "POST", authed: Bool = true) throws -> URLRequest {
        guard let url = URL(string: path, relativeTo: Self.baseURL) else {
            throw APIError.badURL
        }
        var req = URLRequest(url: url)
        req.httpMethod = method
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if authed {
            req.setValue("Bearer \(try token())", forHTTPHeaderField: "Authorization")
        }
        return req
    }

    private func send(_ req: URLRequest) async throws -> Data {
        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let http = resp as? HTTPURLResponse else {
            throw APIError.empty
        }
        guard (200..<300).contains(http.statusCode) else {
            let body = String(data: data, encoding: .utf8) ?? ""
            throw APIError.badStatus(http.statusCode, body)
        }
        return data
    }

    // MARK: - Endpoints

    /// POST /share — creates a shareable voice message page + mp3.
    func share(text: String, voice: Voice, to: String, fromName: String,
               language: AppLang = .ja, cleanup: Bool = false,
               composePrompt: String? = nil, parseCommand: Bool = false) async throws -> ShareResponse {
        var req = try request(path: "/share")
        var body: [String: Any] = [
            "text": text,
            "user_id": voice.userId,
            "to": to,
            "from_name": fromName
        ]
        if let tt = language.translateTo { body["translate_to"] = tt }
        if let cp = composePrompt?.trimmingCharacters(in: .whitespacesAndNewlines), !cp.isEmpty {
            body["compose_prompt"] = cp
        } else if cleanup {
            body["cleanup"] = true
        }
        if parseCommand { body["parse_command"] = true }
        req.httpBody = try JSONSerialization.data(withJSONObject: body)
        let data = try await send(req)
        guard let decoded = try? JSONDecoder().decode(ShareResponse.self, from: data) else {
            throw APIError.decoding
        }
        return decoded
    }

    /// POST /speak — returns raw mp3 bytes synthesized in the chosen voice.
    func speak(text: String, voice: Voice) async throws -> Data {
        var req = try request(path: "/speak")
        let body: [String: Any] = [
            "text": text,
            "user_id": voice.userId,
            "format": "mp3"
        ]
        req.httpBody = try JSONSerialization.data(withJSONObject: body)
        let data = try await send(req)
        guard !data.isEmpty else { throw APIError.empty }
        return data
    }

    /// POST /voice/register/start — begins voice enrollment, returns phrase to read.
    func registerStart(voice: Voice) async throws -> RegisterStartResponse {
        var req = try request(path: "/voice/register/start")
        let body: [String: Any] = ["user_id": voice.userId]
        req.httpBody = try JSONSerialization.data(withJSONObject: body)
        let data = try await send(req)
        guard let decoded = try? JSONDecoder().decode(RegisterStartResponse.self, from: data) else {
            throw APIError.decoding
        }
        return decoded
    }

    /// POST /api/agent — koe.live's dev-request pipeline (same endpoint LINE「依頼 ◯◯」
    /// and koe.live/agent use). No auth required (server rate-limits by IP); the request
    /// lands in the human's inbox/LINE and is picked up by the autonomous dev worker.
    /// Note: this hits koe.live, not `voice.koe.live` (APIClient.baseURL) — /api/agent
    /// lives on the main koe-edge worker, a different backend than voice synthesis.
    func sendDevRequest(text: String, name: String) async throws -> AgentRequestResponse {
        guard let url = URL(string: "https://koe.live/api/agent") else { throw APIError.badURL }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let body: [String: Any] = ["text": text, "name": name]
        req.httpBody = try JSONSerialization.data(withJSONObject: body)
        let data = try await send(req)
        guard let decoded = try? JSONDecoder().decode(AgentRequestResponse.self, from: data) else {
            throw APIError.decoding
        }
        return decoded
    }

    /// POST /voice/register/verify — submits the recorded sample (base64) for verification.
    func registerVerify(token: String, audioBase64: String) async throws -> RegisterVerifyResponse {
        var req = try request(path: "/voice/register/verify")
        let body: [String: Any] = [
            "token": token,
            "audio_b64": audioBase64
        ]
        req.httpBody = try JSONSerialization.data(withJSONObject: body)
        let data = try await send(req)
        guard let decoded = try? JSONDecoder().decode(RegisterVerifyResponse.self, from: data) else {
            throw APIError.decoding
        }
        return decoded
    }

    // MARK: - Became feed (koe.live, public — no auth)

    /// GET /api/became/recent — recent voices that turned into a real thing.
    func becameRecent(limit: Int = 12) async throws -> [BecameItem] {
        guard var comps = URLComponents(string: "https://koe.live/api/became/recent") else { throw APIError.badURL }
        comps.queryItems = [URLQueryItem(name: "limit", value: String(limit))]
        guard let url = comps.url else { throw APIError.badURL }
        var req = URLRequest(url: url)
        req.httpMethod = "GET"
        let data = try await send(req)
        guard let decoded = try? JSONDecoder().decode(BecameRecentResponse.self, from: data) else {
            throw APIError.decoding
        }
        return decoded.items
    }

    // MARK: - Laugh bank (koe.live, not voice.koe.live — admin-only, personality feature)

    /// GET /api/laugh/list — which of the 7 reaction types this voice has already recorded.
    /// Hits koe.live (the main worker), unlike the rest of this client (voice.koe.live).
    func laughList(voice: String, adminToken: String) async throws -> [LaughItem] {
        guard var comps = URLComponents(string: "https://koe.live/api/laugh/list") else { throw APIError.badURL }
        comps.queryItems = [URLQueryItem(name: "voice", value: voice), URLQueryItem(name: "token", value: adminToken)]
        guard let url = comps.url else { throw APIError.badURL }
        var req = URLRequest(url: url)
        req.httpMethod = "GET"
        let data = try await send(req)
        guard let decoded = try? JSONDecoder().decode(LaughListResponse.self, from: data) else {
            throw APIError.decoding
        }
        return decoded.items
    }

    /// POST /api/laugh/record — uploads one reaction recording (base64, self-consent = auto-approved).
    func laughRecord(voice: String, type: String, adminToken: String, audioBase64Full: String) async throws -> String? {
        guard let url = URL(string: "https://koe.live/api/laugh/record") else { throw APIError.badURL }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let body: [String: Any] = ["voice": voice, "type": type, "token": adminToken, "audio_b64": audioBase64Full]
        req.httpBody = try JSONSerialization.data(withJSONObject: body)
        let data = try await send(req)
        guard let decoded = try? JSONDecoder().decode(LaughRecordResponse.self, from: data) else {
            throw APIError.decoding
        }
        return decoded.key
    }
}
