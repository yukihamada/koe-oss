import Foundation

enum BGMMode: String, CaseIterable, Identifiable {
    case none = "なし"
    case peaceful = "穏やか"
    case energetic = "元気"
    case ambient = "アンビエント"

    var id: String { self.rawValue }
    var label: String { self.rawValue }
}
