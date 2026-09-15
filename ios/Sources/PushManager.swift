import Foundation
import UIKit
import UserNotifications
import WebKit

extension Notification.Name {
    /// Posted when a push notification is tapped, carrying the payload's
    /// `url` (e.g. `/live/<handle>`) under the "path" key. RootView listens
    /// and routes to the matching tab.
    static let koeDeepLink = Notification.Name("koeDeepLink")

    /// Posted by widget taps (`koe://pending`) and App Intents/Siri Shortcuts
    /// ("要対応を見る") to open the PendingListView sheet.
    static let koeOpenPending = Notification.Name("koeOpenPending")

    /// Posted by the "KOEで録る" App Intent/Siri Shortcut to jump straight to
    /// the 録る tab (recording hub) on launch.
    static let koeOpenRecord = Notification.Name("koeOpenRecord")

    /// Posted right before the voice recorder starts recording, so anything
    /// currently making sound (in-app voice message playback, the ライブ tab's
    /// WebView radio audio) stops instead of bleeding into the mic / competing
    /// with it. AVAudioSession activation alone already interrupts other apps'
    /// background music, but same-process audio (AudioPlayer, WKWebView
    /// <audio>) shares that session and doesn't get silenced by it.
    static let koeStopAllAudio = Notification.Name("koeStopAllAudio")
    static let koeRecordingAutoStop = Notification.Name("koeRecordingAutoStop")
}

/// Registers this device for APNs and uploads the token to the Koe backend,
/// so new voice messages arrive as notifications even when the app is closed.
final class PushManager: NSObject, ObservableObject, UNUserNotificationCenterDelegate {
    static let shared = PushManager()

    /// Where device tokens are registered. Kept in one place so the backend
    /// route can move without touching call sites. Lives on koe-edge, next to
    /// the inbox the notifications fire on.
    static let registerURL = URL(string: "https://koe.live/api/push/register")!

    @Published var authorized = false

    private override init() {
        super.init()
        UNUserNotificationCenter.current().delegate = self
    }

    /// Ask permission and kick off APNs registration. Safe to call every launch:
    /// iOS only prompts once, and re-registration refreshes a stale token.
    func bootstrap() {
        let center = UNUserNotificationCenter.current()
        center.requestAuthorization(options: [.alert, .sound, .badge]) { granted, _ in
            DispatchQueue.main.async {
                self.authorized = granted
                if granted {
                    UIApplication.shared.registerForRemoteNotifications()
                }
            }
        }
    }

    /// Called from the AppDelegate once APNs hands us the device token.
    /// Auth strategy: attach the koe.live login cookie from the in-app WebView
    /// (server resolves the handle itself); the Bearer token is a fallback for
    /// personal builds where the WebView was never logged in.
    func upload(deviceToken: Data) {
        let hex = deviceToken.map { String(format: "%02x", $0) }.joined()
        DispatchQueue.main.async {
            WKWebsiteDataStore.default().httpCookieStore.getAllCookies { cookies in
                let koe = cookies.filter { $0.domain.hasSuffix("koe.live") }
                self.post(tokenHex: hex, cookies: koe)
            }
        }
    }

    private func post(tokenHex: String, cookies: [HTTPCookie]) {
        var req = URLRequest(url: Self.registerURL)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if !cookies.isEmpty {
            let pairs = cookies.map { "\($0.name)=\($0.value)" }.joined(separator: "; ")
            req.setValue(pairs, forHTTPHeaderField: "Cookie")
        }
        if let bearer = TokenStore.shared.token, !bearer.isEmpty {
            req.setValue("Bearer \(bearer)", forHTTPHeaderField: "Authorization")
        }
        let handle = AppState.normalizeHandle(
            UserDefaults.standard.string(forKey: "koeHandle") ?? "")
        let body: [String: Any] = [
            "device_token": tokenHex,
            "platform": "ios",
            "bundle_id": Bundle.main.bundleIdentifier ?? "tokyo.hamada.koe",
            "handle": handle
        ]
        req.httpBody = try? JSONSerialization.data(withJSONObject: body)
        URLSession.shared.dataTask(with: req) { data, resp, _ in
            let code = (resp as? HTTPURLResponse)?.statusCode ?? -1
            let text = data.flatMap { String(data: $0, encoding: .utf8) } ?? ""
            print("push register → \(code) \(text)")
        }.resume()
    }

    // Show notifications as banners even while the app is in the foreground,
    // matching messenger expectations.
    func userNotificationCenter(_ center: UNUserNotificationCenter,
                                willPresent notification: UNNotification,
                                withCompletionHandler completionHandler:
                                @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .sound, .badge])
    }

    // Notification tap → deep link. Forwards the payload's `url` so RootView
    // can switch tabs and load the right koe.live page.
    func userNotificationCenter(_ center: UNUserNotificationCenter,
                                didReceive response: UNNotificationResponse,
                                withCompletionHandler completionHandler: @escaping () -> Void) {
        if let path = response.notification.request.content.userInfo["url"] as? String, !path.isEmpty {
            NotificationCenter.default.post(name: .koeDeepLink, object: nil, userInfo: ["path": path])
        }
        completionHandler()
    }
}

/// Minimal UIKit delegate: SwiftUI apps still need this for the APNs callbacks.
final class AppDelegate: NSObject, UIApplicationDelegate {
    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        // Touch the singleton so its UNUserNotificationCenter delegate is set
        // before a cold-launch notification tap needs to be delivered.
        _ = PushManager.shared
        return true
    }

    func application(_ application: UIApplication,
                     didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        PushManager.shared.upload(deviceToken: deviceToken)
    }

    func application(_ application: UIApplication,
                     didFailToRegisterForRemoteNotificationsWithError error: Error) {
        print("push register failed: \(error.localizedDescription)")
    }
}
