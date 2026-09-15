import Foundation
#if canImport(WidgetKit)
import WidgetKit
#endif

/// App Group container shared between the main app and the widget/App Intents extensions.
/// The main app is the only writer (it holds the network token); extensions only read.
/// This is the standard WidgetKit "producer/consumer" pattern — it avoids needing to
/// share the admin bearer token with extension processes at all.
enum SharedStore {
    static let appGroupID = "group.tokyo.hamada.koe"
    private static let key = "widgetSnapshot.v1"

    private static var defaults: UserDefaults? { UserDefaults(suiteName: appGroupID) }

    static var snapshot: WidgetSnapshot {
        get {
            guard let data = defaults?.data(forKey: key),
                  let decoded = try? JSONDecoder().decode(WidgetSnapshot.self, from: data) else {
                return .empty
            }
            return decoded
        }
        set {
            guard let data = try? JSONEncoder().encode(newValue) else { return }
            defaults?.set(data, forKey: key)
            #if canImport(WidgetKit)
            WidgetCenter.shared.reloadAllTimelines()
            #endif
        }
    }
}
