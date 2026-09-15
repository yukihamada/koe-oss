import SwiftUI

/// 「要対応」一覧。ウィジェット/ロック画面ウィジェット/Siriショートカット(koe://pending)からの入口。
/// 表示は SharedStore のキャッシュ即描画→onAppearでバックグラウンド再取得、を基本にする(体感速度優先)。
struct PendingListView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var snapshot: WidgetSnapshot = SharedStore.snapshot
    @State private var refreshing = false

    var body: some View {
        NavigationStack {
            List {
                if snapshot.pending.isEmpty {
                    ContentUnavailableFallback()
                } else {
                    ForEach(snapshot.pending) { item in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(item.from).font(.subheadline.weight(.semibold))
                            Text(item.summary).font(.body)
                            if let date = item.date {
                                Text(date, style: .relative)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        .padding(.vertical, 4)
                    }
                }
                if snapshot.fetchedAt > .distantPast {
                    Section {
                        Text(String(format: NSLocalizedString("更新: %@前", comment: ""), RelativeDateTimeFormatter().localizedString(for: snapshot.fetchedAt, relativeTo: Date())))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .navigationTitle(String(format: NSLocalizedString("要対応 %d件", comment: ""), snapshot.pendingCount))
            .refreshable { await refresh() }
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button(NSLocalizedString("閉じる", comment: "")) { dismiss() }
                }
            }
            .task { await refresh() }
        }
    }

    private func refresh() async {
        refreshing = true
        await WidgetSync.refresh()
        snapshot = SharedStore.snapshot
        refreshing = false
    }
}

private struct ContentUnavailableFallback: View {
    var body: some View {
        VStack(spacing: 8) {
            Image(systemName: "checkmark.circle")
                .font(.largeTitle)
                .foregroundStyle(.secondary)
            Text(NSLocalizedString("いまは特にありません", comment: ""))
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 40)
        .listRowSeparator(.hidden)
    }
}
