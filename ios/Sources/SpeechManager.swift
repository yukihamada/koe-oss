import Foundation
import Speech
import AVFoundation

/// Wraps SFSpeechRecognizer + AVAudioEngine for live partial transcription.
final class SpeechManager: NSObject, ObservableObject {
    @Published var isListening = false
    @Published var partial = ""
    @Published var authorized = false
    @Published var errorText: String?

    /// Recognition locale follows the app's active UI language (ja/en), not a
    /// hardcoded ja-JP — an English-UI user speaking English was previously
    /// forced through Japanese recognition and got garbage transcripts.
    private static var recognitionLocale: Locale {
        let lang = Bundle.main.preferredLocalizations.first ?? "ja"
        return Locale(identifier: lang.hasPrefix("en") ? "en-US" : "ja-JP")
    }
    private let recognizer = SFSpeechRecognizer(locale: SpeechManager.recognitionLocale)
    private let engine = AVAudioEngine()
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?

    /// Called with the final recognized string when a result is finalized.
    var onFinal: ((String) -> Void)?

    /// Requests speech + mic permission, then calls `completion` once BOTH
    /// prompts have resolved (so callers can safely start listening).
    func requestAuth(completion: (() -> Void)? = nil) {
        SFSpeechRecognizer.requestAuthorization { [weak self] status in
            DispatchQueue.main.async { self?.authorized = (status == .authorized) }
            AVAudioSession.sharedInstance().requestRecordPermission { _ in
                DispatchQueue.main.async { completion?() }
            }
        }
    }

    func toggle() {
        if isListening { stop() } else { start() }
    }

    func start() {
        guard !isListening else { return }
        guard authorized else {
            errorText = NSLocalizedString("マイクと音声認識を許可してください（設定 > Koe）。", comment: "")
            return
        }
        guard let recognizer, recognizer.isAvailable else {
            errorText = NSLocalizedString("音声認識が利用できません。", comment: "")
            return
        }
        errorText = nil
        partial = ""

        let session = AVAudioSession.sharedInstance()
        do {
            try session.setCategory(.record, mode: .measurement, options: .duckOthers)
            try session.setActive(true, options: .notifyOthersOnDeactivation)
        } catch {
            errorText = NSLocalizedString("オーディオの初期化に失敗しました。", comment: "")
            return
        }

        let req = SFSpeechAudioBufferRecognitionRequest()
        req.shouldReportPartialResults = true
        request = req

        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        input.removeTap(onBus: 0)
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak self] buffer, _ in
            self?.request?.append(buffer)
        }

        engine.prepare()
        do {
            try engine.start()
        } catch {
            errorText = NSLocalizedString("マイクの開始に失敗しました。", comment: "")
            return
        }
        isListening = true

        task = recognizer.recognitionTask(with: req) { [weak self] result, error in
            guard let self else { return }
            if let result {
                DispatchQueue.main.async { self.partial = result.bestTranscription.formattedString }
                if result.isFinal {
                    let text = result.bestTranscription.formattedString
                    DispatchQueue.main.async {
                        self.stop()
                        self.onFinal?(text)
                    }
                }
            }
            if error != nil {
                DispatchQueue.main.async { self.stop() }
            }
        }
    }

    func stop() {
        guard isListening || engine.isRunning else {
            isListening = false
            return
        }
        engine.stop()
        engine.inputNode.removeTap(onBus: 0)
        request?.endAudio()
        task?.cancel()
        request = nil
        task = nil
        isListening = false
    }
}
