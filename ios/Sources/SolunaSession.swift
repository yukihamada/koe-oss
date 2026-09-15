import Foundation
import AVFoundation
import Combine

/// 🌊 どこでもマイク (SOLUNA mode) — turns the app into an always-open mic +
/// speaker over the SOLUNA SL2 protocol (server: soluna-surround/server.py),
/// replacing the Safari /mic page. The mic streams to `ch=koe` and replies are
/// played back from `ch=koe-reply`. Keeps running while the screen is locked
/// (UIBackgroundModes = audio) and auto-reconnects 3 seconds after any drop.
final class SolunaSession: NSObject, ObservableObject {

    // MARK: - Public state

    enum Status: Equatable {
        case off
        case connecting
        case live
        case reconnecting

        /// Localized, user-facing label.
        var label: String {
            switch self {
            case .off: return NSLocalizedString("オフ", comment: "")
            case .connecting: return NSLocalizedString("接続中…", comment: "")
            case .live: return NSLocalizedString("接続済み", comment: "")
            case .reconnecting: return NSLocalizedString("再接続します…", comment: "")
            }
        }
    }

    static let shared = SolunaSession()

    @Published private(set) var status: Status = .off
    @Published private(set) var lastError: String?

    /// True from start() until stop(); drives the auto-reconnect loop.
    private(set) var isEnabled = false

    // MARK: - SL2 wire format (little-endian, header = 22 bytes)
    // magic "SL2" / ver=2 / nchan / pad / seq u32 / nsamp u32 / playAt f64

    static let sl2HeaderSize = 22

    /// Encodes one mono SL2 frame (playAt = 0; the server fills it in).
    static func sl2Frame(seq: UInt32, samples: [Int16]) -> Data {
        var data = Data(capacity: sl2HeaderSize + samples.count * 2)
        data.append(contentsOf: [0x53, 0x4C, 0x32])                 // "SL2"
        data.append(2)                                              // version
        data.append(1)                                              // nchan
        data.append(0)                                              // pad
        appendLE(&data, seq)
        appendLE(&data, UInt32(samples.count))
        data.append(contentsOf: [UInt8](repeating: 0, count: 8))    // playAt f64 = 0
        samples.withUnsafeBytes { raw in
            data.append(raw.bindMemory(to: UInt8.self))
        }
        return data
    }

    /// Decodes an SL2 frame into mono int16 samples (channel 0 if interleaved).
    /// Returns nil if the frame is malformed.
    static func sl2Samples(from data: Data) -> [Int16]? {
        guard data.count >= sl2HeaderSize else { return nil }
        return data.withUnsafeBytes { (raw: UnsafeRawBufferPointer) -> [Int16]? in
            guard raw[0] == 0x53, raw[1] == 0x4C, raw[2] == 0x32 else { return nil } // "SL2"
            let nchan = Int(raw[4])
            let nsamp = Int(raw.loadUnaligned(fromByteOffset: 10, as: UInt32.self).littleEndian)
            guard nchan >= 1, nsamp >= 1,
                  data.count >= sl2HeaderSize + nchan * nsamp * 2 else { return nil }
            var out = [Int16](repeating: 0, count: nsamp)
            for i in 0..<nsamp {
                let off = sl2HeaderSize + i * nchan * 2
                out[i] = Int16(littleEndian: raw.loadUnaligned(fromByteOffset: off, as: Int16.self))
            }
            return out
        }
    }

    private static func appendLE<T: FixedWidthInteger>(_ data: inout Data, _ value: T) {
        withUnsafeBytes(of: value.littleEndian) { data.append(contentsOf: $0) }
    }

    // MARK: - Audio plumbing

    private let engine = AVAudioEngine()
    private let player = AVAudioPlayerNode()
    /// Reply frames are 48kHz int16 mono per the SL2 contract.
    private let playbackFormat = AVAudioFormat(standardFormatWithSampleRate: 48_000, channels: 1)!
    private var micSampleRate: Double = 48_000
    private var seq: UInt32 = 0

    // MARK: - Sockets

    private lazy var urlSession = URLSession(configuration: .default,
                                             delegate: self,
                                             delegateQueue: nil)
    private var pushTask: URLSessionWebSocketTask?
    private var listenTask: URLSessionWebSocketTask?
    private var baseURL: URL?
    private var token = ""
    /// Who is speaking (`&node=<id>` on the push URL, same as mic.html).
    private var nodeId = ""
    /// Bumped on every socket teardown so stale callbacks become no-ops.
    private var generation = 0

    private override init() {
        super.init()
        NotificationCenter.default.addObserver(self,
                                               selector: #selector(handleInterruption(_:)),
                                               name: AVAudioSession.interruptionNotification,
                                               object: nil)
    }

    // MARK: - Start / stop (call from the main thread)

    func start(urlString: String, token: String, node: String) {
        stop()
        guard let base = URL(string: urlString.trimmingCharacters(in: .whitespacesAndNewlines)),
              base.scheme == "wss" else {
            lastError = NSLocalizedString("サーバーURLはwss://で始まる必要があります(常時マイク音声を暗号化なしで送らないため)。", comment: "")
            return
        }
        baseURL = base
        self.token = token
        self.nodeId = node.trimmingCharacters(in: .whitespacesAndNewlines)
        lastError = nil
        isEnabled = true
        status = .connecting

        AVAudioSession.sharedInstance().requestRecordPermission { [weak self] granted in
            DispatchQueue.main.async {
                guard let self, self.isEnabled else { return }
                guard granted else {
                    self.lastError = NSLocalizedString("マイクの許可が必要です。", comment: "")
                    self.stop()
                    return
                }
                do {
                    try self.startAudioEngine()
                } catch {
                    self.lastError = error.localizedDescription
                    self.stop()
                    return
                }
                self.connectSockets()
            }
        }
    }

    func stop() {
        isEnabled = false
        closeSockets()
        engine.inputNode.removeTap(onBus: 0)
        player.stop()
        if engine.isRunning { engine.stop() }
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        status = .off
    }

    // MARK: - Engine

    private func startAudioEngine() throws {
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.playAndRecord, mode: .voiceChat,
                                options: [.allowBluetooth, .defaultToSpeaker])
        try session.setActive(true)

        // Hardware echo cancellation: without this the always-open mic would
        // re-capture whatever the speaker plays.
        if !engine.inputNode.isVoiceProcessingEnabled {
            try engine.inputNode.setVoiceProcessingEnabled(true)
        }

        if player.engine == nil { engine.attach(player) }
        engine.connect(player, to: engine.mainMixerNode, format: playbackFormat)

        let inFormat = engine.inputNode.inputFormat(forBus: 0)
        micSampleRate = inFormat.sampleRate
        engine.inputNode.removeTap(onBus: 0)
        engine.inputNode.installTap(onBus: 0, bufferSize: 1024, format: inFormat) { [weak self] buffer, _ in
            self?.sendMicBuffer(buffer)
        }
        engine.prepare()
        try engine.start()
    }

    @objc private func handleInterruption(_ note: Notification) {
        guard isEnabled,
              let raw = note.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt,
              let type = AVAudioSession.InterruptionType(rawValue: raw) else { return }
        if type == .ended {
            DispatchQueue.main.async { [weak self] in
                guard let self, self.isEnabled else { return }
                try? AVAudioSession.sharedInstance().setActive(true)
                try? self.engine.start()
            }
        }
    }

    // MARK: - Mic → push socket

    private func sendMicBuffer(_ buffer: AVAudioPCMBuffer) {
        guard let task = pushTask, status == .live || status == .connecting else { return }
        let n = Int(buffer.frameLength)
        guard n > 0 else { return }

        var samples = [Int16](repeating: 0, count: n)
        if let floats = buffer.floatChannelData {
            let ch = floats[0]
            for i in 0..<n {
                let v = max(-1.0, min(1.0, ch[i]))
                samples[i] = Int16(v * 32767)
            }
        } else if let ints = buffer.int16ChannelData {
            let ch = ints[0]
            for i in 0..<n { samples[i] = ch[i] }
        } else {
            return
        }

        // Taps often deliver ~100ms buffers; split into ~20ms SL2 frames.
        let chunk = max(1, Int(micSampleRate * 0.02))
        var start = 0
        while start < n {
            let end = min(start + chunk, n)
            seq &+= 1
            let frame = Self.sl2Frame(seq: seq, samples: Array(samples[start..<end]))
            task.send(.data(frame)) { [weak self] error in
                if error != nil { self?.scheduleReconnect() }
            }
            start = end
        }
    }

    // MARK: - Listen socket → speaker

    private func schedulePlayback(_ samples: [Int16]) {
        guard engine.isRunning,
              let buf = AVAudioPCMBuffer(pcmFormat: playbackFormat,
                                         frameCapacity: AVAudioFrameCount(samples.count)) else { return }
        buf.frameLength = AVAudioFrameCount(samples.count)
        let ch = buf.floatChannelData![0]
        for i in 0..<samples.count { ch[i] = Float(samples[i]) / 32768.0 }
        player.scheduleBuffer(buf)
        if !player.isPlaying { player.play() }
    }

    // MARK: - Socket lifecycle

    private func wsURL(role: String, channel: String, pos: String?, node: String? = nil) -> URL? {
        guard let base = baseURL,
              var comps = URLComponents(url: base, resolvingAgainstBaseURL: false) else { return nil }
        comps.path = "/audio"
        var items = [URLQueryItem(name: "role", value: role),
                     URLQueryItem(name: "ch", value: channel)]
        if let pos { items.append(URLQueryItem(name: "pos", value: pos)) }
        if !token.isEmpty { items.append(URLQueryItem(name: "token", value: token)) }
        if let node, !node.isEmpty { items.append(URLQueryItem(name: "node", value: node)) }
        comps.queryItems = items
        return comps.url
    }

    private func connectSockets() {
        guard let pushURL = wsURL(role: "push", channel: "koe", pos: nil, node: nodeId),
              let listenURL = wsURL(role: "listen", channel: "koe-reply", pos: "C") else {
            lastError = NSLocalizedString("サーバーURLが正しくありません。", comment: "")
            stop()
            return
        }
        let gen = generation

        let push = urlSession.webSocketTask(with: pushURL)
        pushTask = push
        push.resume()
        // Announce our real mic sample rate so the server's clock math is right.
        let hello = "{\"t\":\"hello\",\"map\":[\"L\"],\"sr\":\(Int(micSampleRate))}"
        push.send(.string(hello)) { [weak self] error in
            if error != nil { self?.scheduleReconnect() }
        }
        receiveLoop(push, generation: gen)

        let listen = urlSession.webSocketTask(with: listenURL)
        listenTask = listen
        listen.resume()
        receiveLoop(listen, generation: gen)
    }

    private func receiveLoop(_ task: URLSessionWebSocketTask, generation gen: Int) {
        task.receive { [weak self] result in
            guard let self else { return }
            DispatchQueue.main.async {
                guard gen == self.generation else { return }
                switch result {
                case .failure:
                    self.scheduleReconnect()
                case .success(let message):
                    if case .data(let data) = message,
                       task === self.listenTask,
                       let samples = Self.sl2Samples(from: data) {
                        self.schedulePlayback(samples)
                    }
                    self.receiveLoop(task, generation: gen)
                }
            }
        }
    }

    /// Closes both sockets. Bumping `generation` orphans in-flight callbacks.
    private func closeSockets() {
        generation += 1
        pushTask?.cancel(with: .goingAway, reason: nil)
        listenTask?.cancel(with: .goingAway, reason: nil)
        pushTask = nil
        listenTask = nil
    }

    /// Tears down the sockets and retries 3 seconds later (while enabled).
    private func scheduleReconnect() {
        DispatchQueue.main.async { [weak self] in
            guard let self, self.isEnabled, self.status != .reconnecting else { return }
            self.status = .reconnecting
            self.closeSockets()
            let gen = self.generation
            DispatchQueue.main.asyncAfter(deadline: .now() + 3) { [weak self] in
                guard let self, self.isEnabled, gen == self.generation else { return }
                self.status = .connecting
                if !self.engine.isRunning { try? self.engine.start() }
                self.connectSockets()
            }
        }
    }
}

// MARK: - URLSessionWebSocketDelegate

extension SolunaSession: URLSessionWebSocketDelegate {
    func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask,
                    didOpenWithProtocol protocol: String?) {
        DispatchQueue.main.async { [weak self] in
            guard let self, self.isEnabled, webSocketTask === self.pushTask else { return }
            self.status = .live
            self.lastError = nil
        }
    }

    func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask,
                    didCloseWith closeCode: URLSessionWebSocketTask.CloseCode,
                    reason: Data?) {
        DispatchQueue.main.async { [weak self] in
            guard let self,
                  webSocketTask === self.pushTask || webSocketTask === self.listenTask else { return }
            self.scheduleReconnect()
        }
    }
}
