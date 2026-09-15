import SwiftUI

// 2026-07-20 本人指示「(声が形になった瞬間の共有導線を)スマホからもアプリからも強くして」。
// koe.live側の /became/<id>(声が実際にJiuFlow技/bim.house建築/MU商品になった瞬間を見せる
// 公開ページ)を、アプリ内でも見つけられてShareLink(OSネイティブ共有シート)で共有できるように。
// 個人識別はこのパイプラインに元々無いため「みんなの最近の分」を表示する(通知は出さない —
// アプリを開いた人が自分で見つける形。招待ノルマ・バッジ煽り等は入れない)。

/// 「わたし」タブから辿れる、声が実際に形になった最近の瞬間の一覧。
struct BecameFeedView: View {
    @State private var items: [BecameItem] = []
    @State private var isLoading = true
    @State private var errorText: String?

    var body: some View {
        Group {
            if isLoading {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let err = errorText, items.isEmpty {
                EmptyStateView(icon: "wifi.slash", title: "読み込めませんでした", message: err)
            } else if items.isEmpty {
                EmptyStateView(icon: "sparkles", title: "まだありません",
                    message: "声で話しかけると、内容によっては実際に形になることがあります。")
            } else {
                List(items) { item in
                    BecameRow(item: item)
                }
                .listStyle(.plain)
            }
        }
        .navigationTitle("声が、形になった瞬間")
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
        .refreshable { await load() }
    }

    private func load() async {
        do {
            items = try await APIClient().becameRecent(limit: 20)
            errorText = nil
        } catch {
            errorText = error.localizedDescription
        }
        isLoading = false
    }
}

/// iOS16対応の簡易EmptyState(ContentUnavailableViewはiOS17〜のため自前実装)。
private struct EmptyStateView: View {
    let icon: String
    let title: String
    let message: String

    var body: some View {
        VStack(spacing: 10) {
            Image(systemName: icon).font(.system(size: 34)).foregroundStyle(.secondary)
            Text(title).font(.headline)
            Text(message).font(.footnote).foregroundStyle(.secondary).multilineTextAlignment(.center)
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

private struct BecameRow: View {
    let item: BecameItem

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .top, spacing: 8) {
                Text(item.icon)
                VStack(alignment: .leading, spacing: 4) {
                    Text(item.heard)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                    Text(item.title)
                        .font(.subheadline).fontWeight(.semibold)
                        .lineLimit(2)
                }
                Spacer()
            }
            HStack {
                Spacer()
                if let url = URL(string: item.url) {
                    ShareLink(item: url, subject: Text(item.title),
                              message: Text("\(item.title) — 声で話しかけたら、こんな形になっていました。")) {
                        Label("共有", systemImage: "square.and.arrow.up")
                            .font(.footnote)
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                }
            }
        }
        .padding(.vertical, 4)
    }
}
