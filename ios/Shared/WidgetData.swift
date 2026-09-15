import Foundation

/// One "要対応" item surfaced from takibi-line (see koe-edge `/api/widget/summary`).
struct PendingItem: Codable, Identifiable, Hashable {
    let id: String
    let from: String
    let summary: String
    let ts: Double?

    var date: Date? { ts.map { Date(timeIntervalSince1970: $0 / 1000) } }
}

/// Cached snapshot written by the main app, read by the widget/App Intents extensions.
/// Kept tiny and Codable-simple so it survives round-tripping through shared UserDefaults.
struct WidgetSnapshot: Codable {
    var pendingCount: Int
    var pending: [PendingItem]
    var fetchedAt: Date

    static let empty = WidgetSnapshot(pendingCount: 0, pending: [], fetchedAt: .distantPast)
}
