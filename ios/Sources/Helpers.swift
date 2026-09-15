import SwiftUI

/// UIActivityViewController wrapper for sharing a URL.
struct ShareSheet: UIViewControllerRepresentable {
    let items: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }
    func updateUIViewController(_ vc: UIActivityViewController, context: Context) {}
}

/// Audio-only player for a generated voice clip. Downloads the mp3, auto-plays
/// it once, and offers a clear tap-to-replay control. Forces the playback
/// audio session so it is always audible (even right after recording / mute).
struct VoiceResultPlayer: View {
    let mp3URL: URL
    @StateObject private var audio = AudioPlayer()
    @State private var data: Data?
    @State private var loading = true
    @State private var failed = false

    var body: some View {
        Button {
            guard let d = data else { return }
            if audio.isPlaying { audio.stop() } else { audio.play(data: d) }
        } label: {
            HStack(spacing: 12) {
                ZStack {
                    Circle().fill(Theme.accent).frame(width: 50, height: 50)
                    if loading {
                        ProgressView().tint(.white)
                    } else {
                        Image(systemName: audio.isPlaying ? "pause.fill" : "play.fill")
                            .font(.title3).foregroundStyle(.white)
                    }
                }
                Text(label)
                    .font(.subheadline.weight(.semibold))
                Spacer()
                Image(systemName: "speaker.wave.2.fill")
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .buttonStyle(.plain)
        .disabled(loading || failed)
        .task(id: mp3URL) { await load() }
        .onDisappear { audio.stop() }
    }

    private var label: String {
        if loading { return NSLocalizedString("声を読み込み中…", comment: "") }
        if failed { return NSLocalizedString("再生できませんでした", comment: "") }
        return NSLocalizedString(audio.isPlaying ? "再生中…" : "タップしてきく", comment: "")
    }

    private func load() async {
        loading = true; failed = false
        do {
            let (d, resp) = try await URLSession.shared.data(from: mp3URL)
            let ok = (resp as? HTTPURLResponse).map { (200..<300).contains($0.statusCode) } ?? false
            guard ok, !d.isEmpty else { throw URLError(.badServerResponse) }
            data = d
            loading = false
            audio.play(data: d)   // auto-play the moment it's ready
        } catch {
            loading = false; failed = true
        }
    }
}
