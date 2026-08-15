import CNotemeldAgent
import Foundation

public let noteMeldAgentSdkVersion = "0.1.0"
public let noteMeldAgentSchemaVersion = "1"

public enum NoteMeldAgentError: Error {
    case native(Int32)
    case invalidJSON
    case versionMismatch
}

private func eventBridge(_ context: UnsafeMutableRawPointer?, _ json: UnsafePointer<CChar>?) -> Int32 {
    guard let context, let json else { return -2 }
    return Unmanaged<CallbackBox>.fromOpaque(context)
        .takeUnretainedValue().receiveEvent(String(cString: json))
}

private func driverBridge(_ context: UnsafeMutableRawPointer?, _ json: UnsafePointer<CChar>?) -> Int32 {
    guard let context, let json else { return -2 }
    return Unmanaged<CallbackBox>.fromOpaque(context)
        .takeUnretainedValue().receiveDriverRequest(String(cString: json))
}

private func releaseBridge(_ context: UnsafeMutableRawPointer?) {
    guard let context else { return }
    _ = Unmanaged<CallbackBox>.fromOpaque(context).takeRetainedValue()
}

private final class CallbackBox {
    typealias Driver = ([String: Any]) throws -> [String: Any]
    private var handle: OpaquePointer?
    private let driver: Driver
    private let eventHandler: ([String: Any]) -> Void
    private let lock = NSLock()
    private(set) var events: [[String: Any]] = []

    init(handle: OpaquePointer, driver: @escaping Driver, eventHandler: @escaping ([String: Any]) -> Void) {
        self.handle = handle; self.driver = driver; self.eventHandler = eventHandler
    }

    func receiveEvent(_ wire: String) -> Int32 {
        guard let data = wire.data(using: .utf8),
              let event = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              event["schema_version"] as? String == noteMeldAgentSchemaVersion else { return -2 }
        lock.lock(); events.append(event); lock.unlock()
        eventHandler(event)
        return 0
    }

    func receiveDriverRequest(_ wire: String) -> Int32 {
        guard let handle, let data = wire.data(using: .utf8),
              let request = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let callId = request["call_id"] as? UInt64 else { return -2 }
        let result: [String: Any]
        do { result = try driver(request) }
        catch { result = ["schema_version": noteMeldAgentSchemaVersion, "ok": false,
                          "error": ["code": "sdk_internal_error", "message": "host driver failed"]] }
        guard let resultData = try? JSONSerialization.data(withJSONObject: result) else { return -2 }
        return String(decoding: resultData, as: UTF8.self).withCString {
            notemeld_agent_complete_driver_call(handle, callId, $0)
        }
    }
}

public final class NoteMeldAgentRuntime {
    public typealias Driver = ([String: Any]) throws -> [String: Any]
    public typealias EventHandler = ([String: Any]) -> Void

    private var handle: OpaquePointer?
    private var callbackBox: CallbackBox?
    public var events: [[String: Any]] { callbackBox?.events ?? [] }

    public init(maxTurns: Int = 16, driver: @escaping Driver, onEvent: @escaping EventHandler = { _ in }) throws {
        guard String(cString: notemeld_agent_sdk_version()) == noteMeldAgentSdkVersion,
              String(cString: notemeld_agent_schema_version()) == noteMeldAgentSchemaVersion else {
            throw NoteMeldAgentError.versionMismatch
        }
        let config = try JSONSerialization.data(withJSONObject: [
            "schema_version": noteMeldAgentSchemaVersion, "max_turns": maxTurns
        ])
        let created = config.withUnsafeBytes { bytes -> OpaquePointer? in
            let text = String(decoding: bytes, as: UTF8.self)
            return text.withCString { notemeld_agent_runtime_new($0) }
        }
        guard let created else { throw NoteMeldAgentError.native(-9) }
        handle = created
        let box = CallbackBox(handle: created, driver: driver, eventHandler: onEvent)
        callbackBox = box
        let context = Unmanaged.passRetained(box).toOpaque()
        let code = notemeld_agent_runtime_set_callbacks(
            created, eventBridge, context, driverBridge, context, releaseBridge, context)
        guard code == 0 else {
            Unmanaged<CallbackBox>.fromOpaque(context).release()
            callbackBox = nil; close(); throw NoteMeldAgentError.native(code)
        }
    }

    public func submit(_ request: [String: Any]) throws -> UInt64 {
        guard let handle else { throw NoteMeldAgentError.native(-1) }
        let data = try JSONSerialization.data(withJSONObject: request)
        let token = String(decoding: data, as: UTF8.self).withCString {
            notemeld_agent_submit_turn(handle, $0)
        }
        guard token != 0 else { throw NoteMeldAgentError.native(-9) }
        return token
    }

    public func wait(_ token: UInt64, timeoutMs: UInt64 = 30_000) throws {
        guard let handle else { throw NoteMeldAgentError.native(-1) }
        let code = notemeld_agent_wait_turn(handle, token, timeoutMs)
        guard code == 0 else { throw NoteMeldAgentError.native(code) }
    }

    public func cancel(_ token: UInt64) throws {
        guard let handle else { throw NoteMeldAgentError.native(-1) }
        let code = notemeld_agent_cancel_turn(handle, token)
        guard code == 0 else { throw NoteMeldAgentError.native(code) }
    }

    public func steer(_ token: UInt64, payload: [String: Any]) throws {
        guard let handle else { throw NoteMeldAgentError.native(-1) }
        let data = try JSONSerialization.data(withJSONObject: payload)
        let code = String(decoding: data, as: UTF8.self).withCString {
            notemeld_agent_steer_turn(handle, token, $0)
        }
        guard code == 0 else { throw NoteMeldAgentError.native(code) }
    }

    public func close() {
        if let handle { notemeld_agent_runtime_free(handle); self.handle = nil; callbackBox = nil }
    }

    deinit { close() }
}
