import Foundation
import AVFoundation
import Combine

/// Plays mp3 data (from /speak) using AVAudioPlayer, and exposes simple state.
final class AudioPlayer: NSObject, ObservableObject, AVAudioPlayerDelegate {
    @Published var isPlaying = false
    private var player: AVAudioPlayer?

    override init() {
        super.init()
        NotificationCenter.default.addObserver(self, selector: #selector(handleStopAll),
                                                name: .koeStopAllAudio, object: nil)
    }

    deinit {
        NotificationCenter.default.removeObserver(self)
    }

    @objc private func handleStopAll() {
        DispatchQueue.main.async { [weak self] in self?.stop() }
    }

    /// Plays raw mp3 bytes returned by /speak.
    func play(data: Data) {
        configureSession()
        do {
            let p = try AVAudioPlayer(data: data)
            p.delegate = self
            player = p
            p.prepareToPlay()
            isPlaying = p.play()   // play()失敗時にUIが「再生中」のまま固まらないように
        } catch {
            isPlaying = false
        }
    }

    func stop() {
        player?.stop()
        isPlaying = false
    }

    private func configureSession() {
        let session = AVAudioSession.sharedInstance()
        try? session.setCategory(.playback, mode: .default)
        try? session.setActive(true)
    }

    func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        DispatchQueue.main.async { self.isPlaying = false }
    }
}
