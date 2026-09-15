import Foundation
import AVFoundation

/// Records a short sample with AVAudioRecorder and returns the base64-encoded bytes.
final class VoiceRecorder: NSObject, ObservableObject {
    @Published var isRecording = false
    @Published var hasRecording = false
    /// マイク拒否・開始失敗の理由。以前は黙って何も起きなかった(harsh-review指摘)。
    @Published var errorText: String?

    var onRecordingStarted: (() -> Void)?
    var onRecordingStopped: (() -> Void)?

    private var recorder: AVAudioRecorder?
    private var fileURL: URL {
        FileManager.default.temporaryDirectory.appendingPathComponent("koe_register.m4a")
    }

    /// Requests mic permission and begins recording.
    func start() {
        let session = AVAudioSession.sharedInstance()
        try? session.setCategory(.playAndRecord, mode: .default)
        try? session.setActive(true)

        session.requestRecordPermission { [weak self] granted in
            guard let self else { return }
            DispatchQueue.main.async {
                guard granted else {
                    self.errorText = NSLocalizedString("マイクの許可が必要です。設定アプリでKoeにマイクを許可してください。", comment: "")
                    return
                }
                self.errorText = nil
                self.beginRecording()
            }
        }
    }

    private func beginRecording() {
        let settings: [String: Any] = [
            AVFormatIDKey: Int(kAudioFormatMPEG4AAC),
            AVSampleRateKey: 44100,
            AVNumberOfChannelsKey: 1,
            AVEncoderAudioQualityKey: AVAudioQuality.high.rawValue
        ]
        do {
            let r = try AVAudioRecorder(url: fileURL, settings: settings)
            r.record()
            recorder = r
            isRecording = true
            onRecordingStarted?()
        } catch {
            isRecording = false
            errorText = NSLocalizedString("録音を開始できませんでした。", comment: "")
        }
    }

    func stop() {
        recorder?.stop()
        recorder = nil
        isRecording = false
        hasRecording = FileManager.default.fileExists(atPath: fileURL.path)
        onRecordingStopped?()
    }

    /// Reads the recorded file and returns base64 (or nil if nothing recorded).
    func base64() -> String? {
        guard let data = try? Data(contentsOf: fileURL) else { return nil }
        return data.base64EncodedString()
    }
}
