import Foundation
import CryptoKit
import Security

public enum DeviceIdentityStore {
    private static let service = "com.notemeld.mobile.device-identity"
    public static func loadOrCreate() throws -> Curve25519.Signing.PrivateKey {
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecReturnData as String: true]
        var result: CFTypeRef?
        if SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess, let data = result as? Data { return try Curve25519.Signing.PrivateKey(rawRepresentation: data) }
        let key = Curve25519.Signing.PrivateKey()
        let add: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecValueData as String: key.rawRepresentation, kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly]
        guard SecItemAdd(add as CFDictionary, nil) == errSecSuccess else { throw RemoteError.identityStoreUnavailable }
        return key
    }
}

/// Native implementation of the versioned remote-frame protocol used by the
/// desktop Host. The Cloud service only routes these frames; it never sees
/// the session key or command plaintext.
public final class RemoteRelayTransport: NSObject, URLSessionWebSocketDelegate {
    public struct Device {
        public let id: String
        public let publicKey: Data
        public init(id: String, publicKey: Data) { self.id = id; self.publicKey = publicKey }
    }

    private let sessionID: String
    private let controllerID: String
    private let host: Device
    private let lanEndpoints: [String]
    private let token: String
    private let cloudURL: URL
    private let identity: Curve25519.Signing.PrivateKey
    private var socket: URLSessionWebSocketTask!
    private var session: URLSession!
    private var key: SymmetricKey?
    private var sequence = 0
    private var authorityEpoch = 1
    private var receiveTask: Task<Void, Never>?
    private var pending: [String: CheckedContinuation<[String: Any], Error>] = [:]
    private let onEvent: (([String: Any]) -> Void)?

    public init(sessionID: String, controllerID: String, host: Device, lanEndpoints: [String] = [], cloudURL: URL, token: String, identity: Curve25519.Signing.PrivateKey, onEvent: (([String: Any]) -> Void)? = nil) {
        self.sessionID = sessionID; self.controllerID = controllerID; self.host = host; self.lanEndpoints = lanEndpoints; self.token = token; self.cloudURL = cloudURL; self.identity = identity
        self.onEvent = onEvent
        super.init()
    }

    public func connect() async throws {
        var lastError: Error?
        for endpoint in lanEndpoints {
            do {
                prepareSocket(URL(string: "ws://\(endpoint)/v1/lan/connect/\(Self.escape(sessionID))")!, bearer: nil)
                socket.resume()
                try await performLanAuthorization()
                try await performHandshake(relay: false)
                receiveTask = Task { [weak self] in await self?.receiveLoop() }
                return
            } catch { lastError = error; closeSocket() }
        }
        var relay = cloudURL.appendingPathComponent("v1/relay/connect/\(Self.escape(sessionID))")
        relay.append(queryItems: [URLQueryItem(name: "device_id", value: controllerID)])
        guard var relayComponents = URLComponents(url: relay, resolvingAgainstBaseURL: false) else { throw RemoteError.invalidHandshake }
        relayComponents.scheme = cloudURL.scheme == "https" ? "wss" : "ws"
        guard let websocketRelay = relayComponents.url else { throw RemoteError.invalidHandshake }
        prepareSocket(websocketRelay, bearer: token)
        socket.resume()
        do {
            try await performHandshake(relay: true)
            receiveTask = Task { [weak self] in await self?.receiveLoop() }
        } catch { lastError = error; closeSocket(); throw lastError ?? error }
    }

    public func send(input: String, requestID: String = UUID().uuidString) async throws -> [String: Any] {
        guard !input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { throw RemoteError.invalidInput }
        guard let key else { throw RemoteError.notConnected }
        let frameID = UUID().uuidString
        sequence += 1
        let nonce = Data((0..<12).map { _ in UInt8.random(in: 0...255) })
        let nonceText = Self.base64url(nonce)
        let metadata: [String: Any] = ["authority_epoch": authorityEpoch, "frame_id": frameID, "frame_type": "command", "nonce": nonceText, "protocol_version": "notemeld.sync.v1", "recipient_device_id": host.id, "sender_device_id": controllerID, "sequence": sequence, "session_id": sessionID]
        let encrypted = try Self.encrypt(JSONSerialization.data(withJSONObject: ["request_id": requestID, "input": input]), key: key, nonce: nonce, metadata: metadata)
        var frame = metadata; frame["ciphertext"] = encrypted
        try await socket.send(.string(Self.json(frame)))
        return try await withCheckedThrowingContinuation { pending[frameID] = $0 }
    }

    public func close() {
        receiveTask?.cancel(); receiveTask = nil; closeSocket()
        pending.values.forEach { $0.resume(throwing: RemoteError.closed) }; pending.removeAll()
    }

    public func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask, didOpenWithProtocol protocol: String?) {}

    private func prepareSocket(_ url: URL, bearer: String?) {
        var request = URLRequest(url: url)
        if let bearer { request.setValue("Bearer \(bearer)", forHTTPHeaderField: "Authorization") }
        session = URLSession(configuration: .ephemeral, delegate: nil, delegateQueue: nil)
        socket = session.webSocketTask(with: request)
    }

    private func closeSocket() {
        socket?.cancel(with: .normalClosure, reason: nil)
        session?.invalidateAndCancel()
        socket = nil
        session = nil
    }

    private func performLanAuthorization() async throws {
        try await socket.send(.string(Self.json(["type": "hello", "protocol_version": "notemeld.lan.v1", "controller_device_id": controllerID])))
        let challenge = try await receiveUntil { $0["type"] as? String == "challenge" }
        guard let challengeID = challenge["challenge_id"] as? String, let value = challenge["challenge"] as? String else { throw RemoteError.invalidHandshake }
        let message = Data("notemeld-lan-auth-v1\0\(sessionID)\0\(controllerID)\0\(host.id)\0\(challengeID)\0\(value)".utf8)
        let signature = try identity.signature(for: message)
        try await socket.send(.string(Self.json(["type": "proof", "challenge_id": challengeID, "challenge": value, "signature": Self.base64url(signature)])))
        let authorized = try await receiveUntil { $0["type"] as? String == "authorized" }
        guard authorized["session_id"] as? String == sessionID, let epoch = authorized["authority_epoch"] as? Int, epoch > 0 else { throw RemoteError.invalidHandshake }
        authorityEpoch = epoch
    }

    private func performHandshake(relay: Bool) async throws {
        let ephemeral = Curve25519.KeyAgreement.PrivateKey()
        let publicKey = ephemeral.publicKey.rawRepresentation
        let offer = try Self.handshake(sessionID: sessionID, sender: controllerID, recipient: host.id, identity: identity, ephemeral: ephemeral, publicKey: publicKey)
        let nonce = Self.base64url(Data((0..<12).map { _ in UInt8.random(in: 0...255) }))
        var frame: [String: Any] = ["authority_epoch": authorityEpoch, "frame_id": UUID().uuidString, "frame_type": "handshake", "nonce": nonce, "protocol_version": "notemeld.sync.v1", "recipient_device_id": host.id, "sender_device_id": controllerID, "sequence": 1, "session_id": sessionID]
        frame["ciphertext"] = Self.base64url(Data(Self.json(offer).utf8))
        try await socket.send(.string(Self.json(relay ? frame : offer)))
        let response = try await receiveUntil { value in relay ? value["frame_type"] as? String == "handshake" : value["protocol_version"] as? String == "notemeld.e2ee.handshake.v1" }
        let peer: [String: Any]
        if relay {
            guard let encoded = response["ciphertext"] as? String, let payload = Self.decode(encoded), let decoded = try JSONSerialization.jsonObject(with: payload) as? [String: Any] else { throw RemoteError.invalidHandshake }
            peer = decoded
        } else { peer = response }
        guard peer["session_id"] as? String == sessionID, peer["sender_device_id"] as? String == host.id, peer["recipient_device_id"] as? String == controllerID else { throw RemoteError.invalidHandshake }
        let peerPublic = try Self.decodeKey(peer["ephemeral_public"] as? String)
        guard let signature = Self.decode(peer["signature"] as? String ?? "") else { throw RemoteError.invalidHandshake }
        let signed = Self.handshakeMessage(sessionID: sessionID, sender: host.id, recipient: controllerID, ephemeralPublic: peerPublic)
        guard host.publicKey.count == 32,
              let hostSigningKey = try? Curve25519.Signing.PublicKey(rawRepresentation: host.publicKey),
              hostSigningKey.isValidSignature(signature, for: signed) else { throw RemoteError.invalidHandshake }
        let shared = try ephemeral.sharedSecretFromKeyAgreement(with: Curve25519.KeyAgreement.PublicKey(rawRepresentation: peerPublic))
        let first = controllerID < host.id ? (controllerID, publicKey, host.id, peerPublic) : (host.id, peerPublic, controllerID, publicKey)
        let transcript = Self.handshakeTranscript(sessionID: sessionID, first: first.0, firstPublic: first.1, second: first.2, secondPublic: first.3)
        key = shared.hkdfDerivedSymmetricKey(using: SHA256.self, salt: Data(), sharedInfo: transcript, outputByteCount: 32)
        sequence = 1
    }

    private func receiveLoop() async {
        while !Task.isCancelled {
            do { let message = try await socket.receive(); if case .string(let text) = message, let value = Self.object(text) { handle(value) } }
            catch { pending.values.forEach { $0.resume(throwing: error) }; pending.removeAll(); return }
        }
    }

    private func receiveUntil(_ predicate: @escaping ([String: Any]) -> Bool) async throws -> [String: Any] {
        while true {
            let message = try await socket.receive()
            guard case .string(let text) = message, let object = Self.object(text) else { continue }
            if let type = object["type"] as? String, ["rejected", "failed"].contains(type) { throw RemoteError.rejected(type) }
            if predicate(object) { return object }
        }
    }

    private func handle(_ value: [String: Any]) {
        guard let frameType = value["frame_type"] as? String else { return }
        guard frameType == "receipt" || frameType == "event", let key, let nonce = value["nonce"] as? String, let ciphertext = value["ciphertext"] as? String else { return }
        do {
            let metadata = value.filter { $0.key != "ciphertext" }
            let plaintext = try Self.decrypt(nonce: nonce, ciphertext: ciphertext, key: key, metadata: metadata)
            guard let payload = Self.object(Data(plaintext)) else { return }
            if frameType == "event" { onEvent?(payload) }
            if let frameID = payload["frame_id"] as? String, let continuation = pending.removeValue(forKey: frameID) { continuation.resume(returning: payload) }
        } catch { pending.values.forEach { $0.resume(throwing: error) }; pending.removeAll() }
    }

    private static func handshake(sessionID: String, sender: String, recipient: String, identity: Curve25519.Signing.PrivateKey, ephemeral: Curve25519.KeyAgreement.PrivateKey, publicKey: Data) throws -> [String: Any] {
        let message = handshakeMessage(sessionID: sessionID, sender: sender, recipient: recipient, ephemeralPublic: publicKey)
        return ["protocol_version": "notemeld.e2ee.handshake.v1", "session_id": sessionID, "sender_device_id": sender, "recipient_device_id": recipient, "ephemeral_public": base64url(publicKey), "signature": base64url(try identity.signature(for: message))]
    }

    private static func handshakeMessage(sessionID: String, sender: String, recipient: String, ephemeralPublic: Data) -> Data { Data("notemeld-e2ee-v1\0\(sessionID)\0\(sender)\0\(recipient)\0".utf8) + ephemeralPublic }
    private static func handshakeTranscript(sessionID: String, first: String, firstPublic: Data, second: String, secondPublic: Data) -> Data { Data("notemeld-e2ee-transcript-v1\0\(sessionID)\0\(first)\0\(second)\0".utf8) + firstPublic + secondPublic }

    private static func encrypt(_ plaintext: Data, key: SymmetricKey, nonce: Data, metadata: [String: Any]) throws -> String { let sealed = try AES.GCM.seal(plaintext, using: key, nonce: AES.GCM.Nonce(data: nonce), authenticating: Data(Self.json(metadata).utf8)); return base64url(sealed.ciphertext + sealed.tag) }
    private static func decrypt(nonce: String, ciphertext: String, key: SymmetricKey, metadata: [String: Any]) throws -> Data { guard let n = decode(nonce), let c = decode(ciphertext) else { throw RemoteError.invalidFrame }; let sealed = try AES.GCM.SealedBox(nonce: AES.GCM.Nonce(data: n), ciphertext: c.dropLast(16), tag: c.suffix(16)); return try AES.GCM.open(sealed, using: key, authenticating: Data(Self.json(metadata).utf8)) }
    private static func decodeKey(_ value: String?) throws -> Data { guard let value, let data = decode(value), data.count == 32 else { throw RemoteError.invalidHandshake }; return data }
    private static func decode(_ value: String) -> Data? { Data(base64Encoded: value.replacingOccurrences(of: "-", with: "+").replacingOccurrences(of: "_", with: "/") + String(repeating: "=", count: (4 - value.count % 4) % 4)) }
    private static func base64url(_ value: Data) -> String { value.base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "") }
    private static func json(_ value: [String: Any]) -> String { let keys = value.keys.sorted(); let ordered = keys.reduce(into: [String: Any]()) { $0[$1] = value[$1] }; return String(data: (try? JSONSerialization.data(withJSONObject: ordered, options: [.sortedKeys])) ?? Data("{}".utf8), encoding: .utf8) ?? "{}" }
    private static func object(_ text: String) -> [String: Any]? { object(Data(text.utf8)) }
    private static func object(_ data: Data) -> [String: Any]? { (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] }
    private static func escape(_ value: String) -> String { value.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? value }
}

public enum RemoteError: Error { case invalidInput, invalidFrame, invalidHandshake, notConnected, closed, rejected(String), identityStoreUnavailable }
