import SwiftUI

/// 初回起動チュートリアル。本人指摘(2026-08-27)「ごちゃごちゃしすぎ、もっとシンプルに」への
/// 対応で新設。4タブ+主要導線を1枚ずつ、装飾なしで見せるだけ。既存の
/// MigrationNoticeSheet(旧IA刷新の一度きり案内・2026-07-20導入)はここに統合し廃止した
/// (再インストールのたびにトークンだけ残って再表示される不具合があった上、内容も古い)。
struct OnboardingView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var page = 0

    private let pages: [OnboardingPage] = [
        .init(icon: "waveform.circle.fill",
              title: NSLocalizedString("話すと、声になる", comment: ""),
              body: NSLocalizedString("「録る」で話すと、その声のまま届けられます。文字を打つ必要はありません。", comment: "")),
        .init(icon: "paperplane.circle.fill",
              title: NSLocalizedString("とどける", comment: ""),
              body: NSLocalizedString("録り終えたら「とどける」か「開発に送る」を選ぶだけ。迷ったら、あとで履歴から選べます。", comment: "")),
        .init(icon: "person.2.circle.fill",
              title: NSLocalizedString("トークと友だち", comment: ""),
              body: NSLocalizedString("「トーク」で会話、「友だち」でつながる。上のタブで切り替えられます。", comment: "")),
        .init(icon: "person.crop.circle.fill",
              title: NSLocalizedString("わたし", comment: ""),
              body: NSLocalizedString("声の登録やアカウントは「わたし」に。困ったときはここに戻ってください。", comment: ""))
    ]

    var body: some View {
        VStack(spacing: 0) {
            TabView(selection: $page) {
                ForEach(Array(pages.enumerated()), id: \.offset) { i, p in
                    OnboardingPageView(page: p).tag(i)
                }
            }
            .tabViewStyle(.page(indexDisplayMode: .always))
            .indexViewStyle(.page(backgroundDisplayMode: .always))

            Button(page == pages.count - 1 ? NSLocalizedString("はじめる", comment: "") : NSLocalizedString("次へ", comment: "")) {
                if page == pages.count - 1 {
                    finish()
                } else {
                    withAnimation { page += 1 }
                }
            }
            .buttonStyle(PrimaryButton())
            .padding(.horizontal, 28)
            .padding(.bottom, 16)

            if page < pages.count - 1 {
                Button(NSLocalizedString("スキップ", comment: "")) { finish() }
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .padding(.bottom, 20)
            } else {
                Color.clear.frame(height: 20 + 17) // ボタン位置を揃える(フォントの行高み分)
            }
        }
    }

    private func finish() {
        UserDefaults.standard.set(true, forKey: OnboardingView.seenKey)
        dismiss()
    }

    static let seenKey = "onboardingSeenV1"
    static var shouldShow: Bool { !UserDefaults.standard.bool(forKey: seenKey) }
}

private struct OnboardingPage {
    let icon: String
    let title: String
    let body: String
}

private struct OnboardingPageView: View {
    let page: OnboardingPage

    var body: some View {
        VStack(spacing: 20) {
            Spacer()
            Image(systemName: page.icon)
                .font(.system(size: 72))
                .foregroundStyle(Theme.accentColor)
            Text(page.title)
                .font(.title2.weight(.bold))
            Text(page.body)
                .font(.body)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 36)
            Spacer()
            Spacer()
        }
    }
}
