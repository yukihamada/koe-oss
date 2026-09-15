//
//  LocalVoiceClient.swift
//  Koe
//
//  Talks to KOE OSS running on your Mac over the local network.
//
//  Why this exists: the voice model and the reference recording live on the
//  Mac. Rather than upload a recording of your voice to a server to hear it on
//  your phone, the Mac synthesizes locally and sends back the audio.
//
//  Pairing: the Mac shows a 6-character code. You enter it here, it is
//  exchanged for a token, and the token is kept in the Keychain. Revoke it
//  from the Mac at any time with POST /pair/revoke.
//
//  Security: this is plain HTTP over your LAN. Do not pair over public wifi.
//

import Foundation

// MARK: - Models

struct PairStartResponse: Codable {
    let code: String
    let expiresAt: Double
    let expiresIn: Int

    enum CodingKeys: String, CodingKey {
        case code
        case expiresAt = "expires_at"
        case expiresIn = "expires_in"
    }
}

struct PairRedeemResponse: Codable {
    let token: String
    let expiresAt: Double

    enum CodingKeys: String, CodingKey {
        case token
        case expiresAt = "expires_at"
    }
}

struct RemoteSynthResponse: Codable {
    let ok: Bool
    let audioPath: String
    let durationSec: Double
    let genSec: Double
    let engine: String
    let lang: String
    let spoken: String
    let corrected: Bool

    enum CodingKeys: String, CodingKey {
        case ok
        case audioPath = "audio_path"
        case durationSec = "duration_sec"
        case genSec = "gen_sec"
        case engine, lang, spoken, corrected
    }
}

struct VoiceSummary: Codable, Identifiable {
    var id: String { handle }
    let handle: String
    let lang: String
    let consentState: String

    enum CodingKeys: String, CodingKey {
        case handle, lang
        case consentState = "consent_state"
    }
}

struct VoicesResponse: Codable {
    let voices: [VoiceSummary]
}

enum LocalVoiceError: LocalizedError {
    case badURL
    case notPaired
    case unauthorized
    case server(String)
    case transport(Error)

    var errorDescription: String? {
        switch self {
        case .badURL: return "Invalid Mac address"
        case .notPaired: return "Not paired. Enter the code shown on your Mac."
        case .unauthorized: return "Pairing expired or revoked. Pair again."
        case .server(let m): return m
        case .transport(let e): return e.localizedDescription
        }
    }
}

// MARK: - Client

@MainActor
final class LocalVoiceClient: ObservableObject {

    /// e.g. "http://192.168.0.10:8807"
    @Published var baseURLString: String {
        didSet { UserDefaults.standard.set(baseURLString, forKey: "koe.local.baseURL") }
    }

    @Published private(set) var isPaired: Bool = false

    private let keychainKey = "koe.local.token"
    private let session: URLSession

    init() {
        self.baseURLString = UserDefaults.standard.string(forKey: "koe.local.baseURL") ?? ""
        let cfg = URLSessionConfiguration.default
        cfg.timeoutIntervalForRequest = 120   // synthesis is not instant
        cfg.timeoutIntervalForResource = 300
        self.session = URLSession(configuration: cfg)
        self.isPaired = (try? KeychainStore.read(key: keychainKey)) != nil
    }

    private var baseURL: URL? {
        let s = baseURLString.trimmingCharacters(in: .whitespaces)
        guard !s.isEmpty else { return nil }
        let normalized = s.hasPrefix("http") ? s : "http://\(s)"
        return URL(string: normalized)
    }

    // MARK: Pairing

    /// Redeem the code shown on the Mac. Stores the token in the Keychain.
    func pair(code: String) async throws {
        guard let base = baseURL else { throw LocalVoiceError.badURL }
        var req = URLRequest(url: base.appendingPathComponent("/pair/redeem"))
        req.httpMethod = "POST"
        req.addValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONSerialization.data(withJSONObject: ["code": code])

        let (data, resp) = try await session.data(for: req)
        guard let http = resp as? HTTPURLResponse else { throw LocalVoiceError.notPaired }
        guard http.statusCode == 200 else {
            throw http.statusCode == 401 ? LocalVoiceError.notPaired
                : LocalVoiceError.server("pair failed (\(http.statusCode))")
        }
        let decoded = try JSONDecoder().decode(PairRedeemResponse.self, from: data)
        try KeychainStore.save(key: keychainKey, value: decoded.token)
        isPaired = true
    }

    func unpair() {
        try? KeychainStore.delete(key: keychainKey)
        isPaired = false
    }

    // MARK: Voices

    func voices() async throws -> [VoiceSummary] {
        guard let base = baseURL else { throw LocalVoiceError.badURL }
        let (data, _) = try await session.data(from: base.appendingPathComponent("/voices"))
        return try JSONDecoder().decode(VoicesResponse.self, from: data).voices
    }

    // MARK: Synthesis

    /// Synthesize on the Mac and return the audio data.
    func synth(voice: String, text: String, lang: String? = nil) async throws -> Data {
        guard let base = baseURL else { throw LocalVoiceError.badURL }
        guard let token = try? KeychainStore.read(key: keychainKey) else {
            throw LocalVoiceError.notPaired
        }

        var body: [String: Any] = ["voice_id": voice, "text": text]
        if let lang { body["lang"] = lang }

        var req = URLRequest(url: base.appendingPathComponent("/remote/synth"))
        req.httpMethod = "POST"
        req.addValue("application/json", forHTTPHeaderField: "Content-Type")
        req.addValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        req.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (data, resp) = try await session.data(for: req)
        guard let http = resp as? HTTPURLResponse else { throw LocalVoiceError.notPaired }
        if http.statusCode == 401 {
            isPaired = false
            throw LocalVoiceError.unauthorized
        }
        guard http.statusCode == 200 else {
            let msg = String(data: data, encoding: .utf8) ?? "synth failed (\(http.statusCode))"
            throw LocalVoiceError.server(msg)
        }

        let result = try JSONDecoder().decode(RemoteSynthResponse.self, from: data)

        // /remote/synth returns a path on the Mac; fetch the bytes.
        var comps = URLComponents(url: base.appendingPathComponent("/audio"),
                                  resolvingAgainstBaseURL: false)!
        comps.queryItems = [URLQueryItem(name: "path", value: result.audioPath)]
        let (audio, _) = try await session.data(from: comps.url!)
        return audio
    }
}

// MARK: - Keychain

enum KeychainStore {
    static func save(key: String, value: String) throws {
        let data = Data(value.utf8)
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key,
            kSecValueData as String: data,
        ]
        SecItemDelete(query as CFDictionary)
        let status = SecItemAdd(query as CFDictionary, nil)
        guard status == errSecSuccess else {
            throw NSError(domain: "Keychain", code: Int(status))
        }
    }

    static func read(key: String) throws -> String {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var ref: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &ref)
        guard status == errSecSuccess,
              let data = ref as? Data,
              let s = String(data: data, encoding: .utf8) else {
            throw NSError(domain: "Keychain", code: Int(status))
        }
        return s
    }

    static func delete(key: String) throws {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key,
        ]
        let status = SecItemDelete(query as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else {
            throw NSError(domain: "Keychain", code: Int(status))
        }
    }
}
