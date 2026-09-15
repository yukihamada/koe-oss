import Foundation

/// Fetches GET /api/widget/summary (koe-edge) and writes the result into the App Group
/// shared container so the widget/App Intents extensions can read it without needing
/// their own network access or copy of the admin token.
///
/// Auth: reuses `TokenStore.shared.laughAdminToken` — the same VOICES_ADMIN_TOKEN-class
/// bearer already used for other personal/admin-only endpoints (`/api/laugh/*`). This
/// widget is exclusively for 優貴さん's own use, so no separate token flow is introduced.
enum WidgetSync {
    private struct SummaryResponse: Decodable {
        let ok: Bool
        let pending_count: Int
        let pending: [PendingItem]
    }

    /// Best-effort refresh. Silently no-ops if the admin token hasn't been set yet
    /// (Settings › 詳細 › 管理トークン) — never surfaces an error to the user for what
    /// is a background convenience feature.
    static func refresh() async {
        guard let token = TokenStore.shared.laughAdminToken, !token.isEmpty else { return }
        guard let url = URL(string: "https://koe.live/api/widget/summary") else { return }
        var req = URLRequest(url: url)
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        do {
            let (data, resp) = try await URLSession.shared.data(for: req)
            guard let http = resp as? HTTPURLResponse, http.statusCode == 200 else { return }
            let decoded = try JSONDecoder().decode(SummaryResponse.self, from: data)
            SharedStore.snapshot = WidgetSnapshot(
                pendingCount: decoded.pending_count,
                pending: decoded.pending,
                fetchedAt: Date()
            )
        } catch {
            // ネットワーク不調時は前回のキャッシュをそのまま残す(ウィジェットは古いが表示は死なない)。
        }
    }
}
