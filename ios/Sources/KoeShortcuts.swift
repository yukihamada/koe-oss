import AppIntents
import Foundation

/// Siri/ショートカットアプリ/Spotlightに自動掲載される2つのApp Intent。
/// 別Extensionは不要(iOS16+はメインアプリターゲット内のApp Intentsだけで動く)。
/// どちらも「アプリを開いて特定画面に飛ばす」だけに徹する — マイク操作を要する処理は
/// フォアグラウンドUIなしでは信頼できない(録音の許可ダイアログ/権限がバックグラウンド
/// 実行のIntentからは扱えないため)。

struct OpenPendingIntent: AppIntent {
    static var title: LocalizedStringResource = "要対応を見る"
    static var description = IntentDescription("焚き火LINEなどから拾った「要対応」の件数と内容を開く。")
    static var openAppWhenRun: Bool = true

    @MainActor
    func perform() async throws -> some IntentResult {
        NotificationCenter.default.post(name: .koeOpenPending, object: nil)
        return .result()
    }
}

struct OpenRecordIntent: AppIntent {
    static var title: LocalizedStringResource = "KOEで録る"
    static var description = IntentDescription("KOEを声メッセージの録音画面で開く。")
    static var openAppWhenRun: Bool = true

    @MainActor
    func perform() async throws -> some IntentResult {
        NotificationCenter.default.post(name: .koeOpenRecord, object: nil)
        return .result()
    }
}

struct KoeShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: OpenPendingIntent(),
            phrases: ["\(.applicationName)の要対応を見る", "\(.applicationName)で要対応を確認"],
            shortTitle: "要対応を見る",
            systemImageName: "waveform.badge.exclamationmark"
        )
        AppShortcut(
            intent: OpenRecordIntent(),
            phrases: ["\(.applicationName)で録る", "\(.applicationName)で声を送る"],
            shortTitle: "KOEで録る",
            systemImageName: "waveform.badge.mic"
        )
    }
}
