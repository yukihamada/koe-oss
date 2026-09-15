import SwiftUI
import AVFoundation

struct VoiceLogEntry: Identifiable {
    let id = UUID()
    let memberName: String
    let memberEmoji: String
    let recordedAt: Date
    let duration: TimeInterval
    let waveform: [Float] // Assuming waveform data comes from API
    let reactions: [String]
    let isMine: Bool
}

struct VoiceLogFeedView: View {
    @State private var entries: [VoiceLogEntry] = [] // モックデータを削除し、空の配列で初期化
    @State private var playingID: UUID?
    @State private var showInvite = false
    @State private var reacted: [UUID: String] = [:]
    @State private var playProgress: Double = 0
    @State private var playTimer: Timer?
    @State private var showRecord = false

    private let columns = [GridItem(.flexible(), spacing: 12), GridItem(.flexible(), spacing: 12)]

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    todayMixCard
                    if entries.isEmpty {
                        emptyState
                    } else {
                        LazyVGrid(columns: columns, spacing: 12) {
                            ForEach(entries) { entry in
                                VoiceLogCard(entry: entry,
                                             isPlaying: playingID == entry.id,
                                             isDimmed: playingID != nil && playingID != entry.id,
                                             progress: playingID == entry.id ? playProgress : 0,
                                             reaction: reacted[entry.id]) {
                                    togglePlay(entry)
                                } onReact: { emoji in
                                    withAnimation(.spring(duration: 0.25)) {
                                        reacted[entry.id] = emoji
                                    }
                                }
                            }
                            recordPromptCard
                        }
                        .padding(.horizontal, 16)
                    }
                    Text("声だけ・15秒まで・編集なし。聞き逃しても、返さなくてもだいじょうぶ。")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                }
            }
            .navigationTitle(Text("うちのルーム 🏠"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showInvite = true } label: {
                        Image(systemName: "person.badge.plus")
                    }
                    .accessibilityLabel(Text("ルームに招待する", comment: ""))
                }
            }
            .sheet(isPresented: $showInvite) { InviteSheet() }
            .sheet(isPresented: $showRecord) {
                NavigationStack {
                    RecordHubView()
                        .toolbar {
                            ToolbarItem(placement: .topBarLeading) {
                                Button("閉じる") { showRecord = false }
                            }
                        }
                }
            }
        }
        .onAppear(perform: loadVoiceLogs) // Add onAppear to load data
    }

    private func loadVoiceLogs() {
        // Simulate API call to fetch voice logs
        // In a real app, this would be an actual network request
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) { // Simulate network delay
            self.entries = [
                VoiceLogEntry(memberName: "あおい", memberEmoji: "🌿",
                              recordedAt: Date().addingTimeInterval(-600),
                              duration: 8, waveform: [], // Waveform will come from API
                              reactions: ["😂", "🥺"], isMine: false),
                VoiceLogEntry(memberName: "けんと", memberEmoji: "⚽️",
                              recordedAt: Date().addingTimeInterval(-3600 * 2),
                              duration: 12, waveform: [], // Waveform will come from API
                              reactions: ["👏"], isMine: false),
                VoiceLogEntry(memberName: "わたし", memberEmoji: "🔥",
                              recordedAt: Date().addingTimeInterval(-3600 * 3),
                              duration: 6, waveform: [], // Waveform will come from API
                              reactions: [], isMine: true),
                VoiceLogEntry(memberName: "みさき", memberEmoji: "🌸",
                              recordedAt: Date().addingTimeInterval(-3600 * 5),
                              duration: 10, waveform: [], // Waveform will come from API
                              reactions: ["❤️", "😂", "🙌"], isMine: false),
                VoiceLogEntry(memberName: "あおい", memberEmoji: "🌿",
                              recordedAt: Date().addingTimeInterval(-3600 * 8),
                              duration: 5, waveform: [], // Waveform will come from API
                              reactions: [], isMine: false),
            ] // Replace with actual API data parsing
        }
    }

    private var todayMixCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("今日の声ログ")
                    .font(.headline)
                Spacer()
                Text(todayString)
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(.secondary)
            }
            HStack(spacing: 4) {
                ForEach(Array(entries.prefix(5).enumerated()), id: \.element.id) { _, entry in
                    Text(entry.memberEmoji)
                        .font(.title3)
                        .frame(width: 40, height: 40)
                        .background(Theme.field, in: Circle())
                }
                Spacer()
                Button {
                    playMix()
                } label: {
                    Label("みんなの今日、きいてみる", systemImage: "play.fill")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 10)
                        .background(Theme.accent, in: Capsule())
                }
                .accessibilityLabel(Text("みんなの声ログを順番に再生", comment: ""))
            }
            Text(entries.isEmpty
                 ? "まだ誰もいないよ。最初の声をおいてみない？"
                 : String(format: NSLocalizedString("%lldこ集まったよ。順番に流れます", comment: ""), entries.count))
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(16)
        .background(Theme.card, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        .padding(.horizontal, 16)
        .padding(.top, 8)
    }

    private var emptyState: some View {
        VStack(spacing: 20) {
            Text("🌙")
                .font(.system(size: 48))
            Text("まだ誰もいないよ")
                .font(.headline)
            Text("ルームをつく���て、友だちを招待しよう。\nPINを教えた人だけが入れます。")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            Button { showInvite = true } label: {
                Label("ルームをつくる", systemImage: "plus.circle.fill")
            }
            .buttonStyle(PrimaryButton())
            .padding(.horizontal, 40)
            Button { showRecord = true } label: {
                Label("最初の声をおく", systemImage: "mic.fill")
                    .font(.subheadline)
            }
        }
        .padding(.vertical, 40)
    }

    private var recordPromptCard: some View {
        Button { showRecord = true } label: {
            VStack(spacing: 10) {
                Image(systemName: "mic.fill")
                    .font(.system(size: 32))
                    .foregroundStyle(Theme.accentColor)
                Text("いまの声を\nおいておく")
                    .font(.headline)
                    .multilineTextAlignment(.center)
                Text("15秒だけでいい")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, minHeight: 180)
            .padding(12)
            .background(Theme.field, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .strokeBorder(Theme.accentColor.opacity(0.5), style: StrokeStyle(lineWidth: 2, dash: [8]))
            }
        }
        .buttonStyle(.plain)
        .accessibilityLabel(Text("声を録音してルームに置く", comment: ""))
    }

    private var todayString: String {
        let f = DateFormatter()
        f.locale = Locale(identifier: "ja_JP")
        f.dateFormat = "M月d日(E)"
        return f.string(from: Date())
    }

    private func togglePlay(_ entry: VoiceLogEntry) {
        playTimer?.invalidate()
        if playingID == entry.id {
            playingID = nil
            playProgress = 0
            return
        }
        playingID = entry.id
        playProgress = 0
        let step = 0.05
        playTimer = Timer.scheduledTimer(withTimeInterval: step, repeats: true) { _ in
            playProgress += step / (entry.duration * 0.3)
            if playProgress >= 1.0 {
                playTimer?.invalidate()
                playingID = nil
                playProgress = 0
            }
        }
    }

    private func playMix() {
        guard let first = entries.first else { return }
        togglePlay(first)
    }
}

struct VoiceLogCard: View {
    let entry: VoiceLogEntry
    let isPlaying: Bool
    let isDimmed: Bool
    let progress: Double
    let reaction: String?
    let onTap: () -> Void
    let onReact: (String) -> Void

    private let reactionChoices = ["❤️", "😂", "🥺", "👏"]

    var body: some View {
        Button(action: onTap) {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text(entry.memberEmoji)
                        .font(.title3)
                        .frame(width: 36, height: 36)
                        .background(Theme.field, in: Circle())
                    VStack(alignment: .leading, spacing: 1) {
                        HStack(spacing: 4) {
                            Text(entry.memberName)
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(.primary)
                            if entry.isMine {
                                Text("わたし")
                                    .font(.system(size: 9, weight: .bold))
                                    .foregroundStyle(.white)
                                    .padding(.horizontal, 5)
                                    .padding(.vertical, 2)
                                    .background(Theme.accentColor, in: Capsule())
                            }
                        }
                        Text(relativeTime(entry.recordedAt))
                            .font(.system(.caption2, design: .monospaced))
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    ZStack {
                        Circle()
                            .fill(isPlaying ? AnyShapeStyle(Theme.accent) : AnyShapeStyle(Theme.field))
                            .frame(width: 28, height: 28)
                        if isPlaying {
                            Circle()
                                .trim(from: 0, to: progress)
                                .stroke(Color.white, lineWidth: 2)
                                .frame(width: 28, height: 28)
                                .rotationEffect(.degrees(-90))
                        }
                        Image(systemName: isPlaying ? "stop.fill" : "play.fill")
                            .font(.system(size: 10))
                            .foregroundStyle(isPlaying ? .white : Theme.accentColor)
                    }
                }
                WaveformView(levels: entry.waveform, active: isPlaying)
                    .frame(height: 40)
                HStack(spacing: 8) {
                    ForEach(reactionChoices, id: \.self) { emoji in
                        let isActive = reaction == emoji || entry.reactions.contains(emoji)
                        Text(emoji)
                            .font(.system(size: 18))
                            .padding(6)
                            .background(isActive ? Theme.accentColor.opacity(0.15) : Color.clear, in: Circle())
                            .scaleEffect(reaction == emoji ? 1.3 : 1.0)
                            .onTapGesture { onReact(emoji) }
                    }
                    Spacer()
                }
            }
            .padding(12)
            .frame(maxWidth: .infinity, minHeight: 130, alignment: .topLeading)
            .background(Theme.card, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay {
                if entry.isMine {
                    RoundedRectangle(cornerRadius: 20, style: .continuous)
                        .strokeBorder(Theme.accentColor.opacity(0.35), lineWidth: 1.5)
                }
            }
        }
        .buttonStyle(.plain)
        .opacity(isDimmed ? 0.4 : 1.0)
        .animation(.easeInOut(duration: 0.2), value: isDimmed)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(accessibilityDescription)
        .accessibilityHint(isPlaying ? Text("タップで停止", comment: "") : Text("タップで再生", comment: ""))
    }

    private var accessibilityDescription: String {
        let who = entry.isMine ? NSLocalizedString("わたし", comment: "") : entry.memberName
        let when = relativeTime(entry.recordedAt)
        let secs = Int(entry.duration)
        return String(format: NSLocalizedString("%@の声、%@、%d秒", comment: ""), who, when, secs)
    }

    private func relativeTime(_ date: Date) -> String {
        let interval = Date().timeIntervalSince(date)
        if interval < 300 { return NSLocalizedString("さっき", comment: "") }
        if interval < 3600 { return String(format: NSLocalizedString("%lld分前", comment: ""), Int(interval / 60)) }
        if interval < 86400 { return String(format: NSLocalizedString("%lld時間前", comment: ""), Int(interval / 3600)) }
        return String(format: NSLocalizedString("%lld日前", comment: ""), Int(interval / 86400))
    }
}

struct WaveformView: View {
    let levels: [Float]
    var active: Bool = false

    var body: some View {
        HStack(alignment: .center, spacing: 2.5) {
            ForEach(Array(levels.enumerated()), id: \.offset) { index, level in
                Capsule()
                    .fill(active ? AnyShapeStyle(Theme.accent) : AnyShapeStyle(Color.secondary.opacity(0.6)))
                    .frame(width: 3, height: max(4, CGFloat(level) * 36))
                    .opacity(active ? (index % 2 == 0 ? 1.0 : 0.7) : 1.0)
            }
        }
        .frame(maxWidth: .infinity)
        .accessibilityHidden(true)
    }
}

struct InviteSheet: View {
    @Environment(\.dismiss) private var dismiss
    @State private var copied = false
    private let pin = "4821"

    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "person.2.fill")
                .font(.system(size: 40))
                .foregroundStyle(Theme.accentColor)
                .padding(.top, 8)
            Text("ルームに招待する")
                .font(.title3.weight(.bold))
            Text("このPINを教えた人だけが入れます。20人まで。")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            Text(pin)
                .font(.system(size: 44, weight: .bold, design: .monospaced))
                .tracking(8)
                .padding(.vertical, 16)
                .padding(.horizontal, 32)
                .background(Theme.field, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            HStack(spacing: 12) {
                Button {
                    UIPasteboard.general.string = pin
                    withAnimation { copied = true }
                } label: {
                    Label(copied ? "コピーしました" : "PINをコピー", systemImage: copied ? "checkmark" : "doc.on.doc")
                }
                .buttonStyle(PrimaryButton())
                ShareLink(item: String(format: NSLocalizedString("Koeのルームに入って！PIN: %@", comment: ""), pin)) {
                    Label("シェア", systemImage: "square.and.arrow.up")
                }
                .buttonStyle(PrimaryButton())
            }
            Button("閉じる") { dismiss() }
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .padding(28)
        .presentationDetents([.medium])
    }
}

#Preview {
    VoiceLogFeedView()
}
