import Foundation
import Security

/// Persists the backend access token in the iOS Keychain (never hardcoded).
/// Falls back transparently so callers just read/write `.token`.
final class TokenStore {
    static let shared = TokenStore()

    private let service = "tokyo.hamada.koe"
    private let account = "accessToken"
    private let solunaAccount = "solunaToken"
    private let laughAdminAccount = "laughAdminToken"

    private init() {}

    /// The current access token, or nil if not set.
    var token: String? {
        get { read(account: account) }
        set { write(newValue, account: account) }
    }

    /// SOLUNA (どこでもマイク) access key, stored under its own keychain
    /// account. nil means "fall back to the main Koe token".
    var solunaToken: String? {
        get { read(account: solunaAccount) }
        set { write(newValue, account: solunaAccount) }
    }

    /// Admin token for personality-only endpoints (笑い声・リアクション録音 /api/laugh/*).
    /// Separate from the main access token: /api/laugh/* checks VOICES_ADMIN_TOKEN,
    /// not the per-user Bearer token used against voice.koe.live.
    var laughAdminToken: String? {
        get { read(account: laughAdminAccount) }
        set { write(newValue, account: laughAdminAccount) }
    }

    private func write(_ value: String?, account: String) {
        if let v = value, !v.isEmpty {
            save(v, account: account)
        } else {
            delete(account: account)
        }
    }

    private func save(_ value: String, account: String) {
        delete(account: account)
        guard let data = value.data(using: .utf8) else { return }
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlock
        ]
        SecItemAdd(query as CFDictionary, nil)
    }

    private func read(account: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]
        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        guard status == errSecSuccess, let data = item as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    private func delete(account: String) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]
        SecItemDelete(query as CFDictionary)
    }
}
