#include <napi/native_api.h>
#include <napi/native_node_api.h>

#include <cstdint>
#include <atomic>
#include <mutex>
#include <memory>
#include <string>
#include <unordered_map>

#include "notemeld_agent.h"

namespace {

std::string String(napi_env env, napi_value value);

struct CallbackBridge {
    AgentRuntimeHandle *handle = nullptr;
    napi_threadsafe_function events = nullptr;
    napi_threadsafe_function drivers = nullptr;
    std::atomic<unsigned> finalized{0};
};

std::mutex bridges_mutex;
std::unordered_map<AgentRuntimeHandle *, CallbackBridge *> bridges;

void FinalizeTsfn(napi_env, void *data, void *) {
    auto *bridge = static_cast<CallbackBridge *>(data);
    if (bridge != nullptr && bridge->finalized.fetch_add(1) + 1 == 2) delete bridge;
}

void ReleaseBridge(void *context) {
    auto *bridge = static_cast<CallbackBridge *>(context);
    if (!bridge) return;
    { std::lock_guard<std::mutex> guard(bridges_mutex); bridges.erase(bridge->handle); }
    if (bridge->events) napi_release_threadsafe_function(bridge->events, napi_tsfn_release);
    if (bridge->drivers) napi_release_threadsafe_function(bridge->drivers, napi_tsfn_release);
}

uint64_t CallId(const std::string &wire) {
    const std::string marker = "\"call_id\":";
    const auto start = wire.find(marker);
    if (start == std::string::npos) return 0;
    try { return std::stoull(wire.substr(start + marker.size())); }
    catch (...) { return 0; }
}

void CallEventJs(napi_env env, napi_value callback, void *, void *data) {
    std::unique_ptr<std::string> wire(static_cast<std::string *>(data));
    if (env == nullptr || callback == nullptr) return;
    napi_value global, argument;
    napi_get_global(env, &global);
    napi_create_string_utf8(env, wire->c_str(), wire->size(), &argument);
    napi_call_function(env, global, callback, 1, &argument, nullptr);
}

struct DriverPayload { CallbackBridge *bridge; std::string wire; };

void CallDriverJs(napi_env env, napi_value callback, void *, void *data) {
    std::unique_ptr<DriverPayload> payload(static_cast<DriverPayload *>(data));
    if (env == nullptr || callback == nullptr) return;
    napi_value global, argument, result;
    napi_get_global(env, &global);
    napi_create_string_utf8(env, payload->wire.c_str(), payload->wire.size(), &argument);
    const auto call_id = CallId(payload->wire);
    std::string result_wire = R"({"schema_version":"1","ok":false,"error":{"code":"sdk_internal_error","message":"host driver failed"}})";
    napi_valuetype type = napi_undefined;
    if (napi_call_function(env, global, callback, 1, &argument, &result) == napi_ok &&
        napi_typeof(env, result, &type) == napi_ok && type == napi_string) {
        result_wire = String(env, result);
    } else {
        bool pending = false;
        if (napi_is_exception_pending(env, &pending) == napi_ok && pending) {
            napi_value ignored; napi_get_and_clear_last_exception(env, &ignored);
        }
    }
    if (call_id != 0) {
        notemeld_agent_complete_driver_call(payload->bridge->handle, call_id, result_wire.c_str());
    }
}

int32_t EventCallback(void *context, const char *event_json) {
    auto *bridge = static_cast<CallbackBridge *>(context);
    if (bridge == nullptr || bridge->events == nullptr || event_json == nullptr) return -2;
    auto *wire = new std::string(event_json);
    if (napi_call_threadsafe_function(bridge->events, wire, napi_tsfn_nonblocking) != napi_ok) {
        delete wire;
        return -9;
    }
    return 0;
}

int32_t DriverCallback(void *context, const char *request_json) {
    auto *bridge = static_cast<CallbackBridge *>(context);
    if (bridge == nullptr || bridge->drivers == nullptr || request_json == nullptr) return -2;
    auto *payload = new DriverPayload{bridge, request_json};
    if (napi_call_threadsafe_function(bridge->drivers, payload, napi_tsfn_nonblocking) != napi_ok) {
        delete payload;
        return -9;
    }
    return 0;
}

AgentRuntimeHandle *HandleFromBigInt(napi_env env, napi_value value) {
    uint64_t raw = 0;
    bool lossless = false;
    if (napi_get_value_bigint_uint64(env, value, &raw, &lossless) != napi_ok) return nullptr;
    return lossless ? reinterpret_cast<AgentRuntimeHandle *>(raw) : nullptr;
}

napi_value BigInt(napi_env env, uint64_t value) {
    napi_value result;
    napi_create_bigint_uint64(env, value, &result);
    return result;
}

std::string String(napi_env env, napi_value value) {
    napi_valuetype type = napi_undefined;
    if (napi_typeof(env, value, &type) != napi_ok || type != napi_string) return {};
    size_t size = 0;
    if (napi_get_value_string_utf8(env, value, nullptr, 0, &size) != napi_ok) return {};
    std::string result(size + 1, '\0');
    if (napi_get_value_string_utf8(env, value, result.data(), result.size(), &size) != napi_ok) return {};
    result.resize(size);
    return result;
}

napi_value Int(napi_env env, int32_t value) {
    napi_value result;
    napi_create_int32(env, value, &result);
    return result;
}

napi_value SdkVersion(napi_env env, napi_callback_info info) {
    size_t argc = 0;
    napi_value result;
    if (napi_get_cb_info(env, info, &argc, nullptr, nullptr, nullptr) != napi_ok || argc != 0) {
        napi_create_string_utf8(env, "", 0, &result); return result;
    }
    napi_create_string_utf8(env, notemeld_agent_sdk_version(), NAPI_AUTO_LENGTH, &result);
    return result;
}

napi_value SchemaVersion(napi_env env, napi_callback_info info) {
    size_t argc = 0;
    napi_value result;
    if (napi_get_cb_info(env, info, &argc, nullptr, nullptr, nullptr) != napi_ok || argc != 0) {
        napi_create_string_utf8(env, "", 0, &result); return result;
    }
    napi_create_string_utf8(env, notemeld_agent_schema_version(), NAPI_AUTO_LENGTH, &result);
    return result;
}

napi_value RuntimeNew(napi_env env, napi_callback_info info) {
    size_t argc = 1;
    napi_value argv[1];
    if (napi_get_cb_info(env, info, &argc, argv, nullptr, nullptr) != napi_ok || argc != 1) return BigInt(env, 0);
    auto config = String(env, argv[0]);
    return BigInt(env, reinterpret_cast<uint64_t>(notemeld_agent_runtime_new(config.c_str())));
}

napi_value SubmitTurn(napi_env env, napi_callback_info info) {
    size_t argc = 2;
    napi_value argv[2];
    if (napi_get_cb_info(env, info, &argc, argv, nullptr, nullptr) != napi_ok || argc != 2) return BigInt(env, 0);
    auto *handle = HandleFromBigInt(env, argv[0]);
    if (handle == nullptr) return BigInt(env, 0);
    auto request = String(env, argv[1]);
    return BigInt(env, notemeld_agent_submit_turn(handle, request.c_str()));
}

napi_value CompleteDriverCall(napi_env env, napi_callback_info info) {
    size_t argc = 3;
    napi_value argv[3];
    if (napi_get_cb_info(env, info, &argc, argv, nullptr, nullptr) != napi_ok || argc != 3) return Int(env, -2);
    uint64_t call_id = 0;
    bool lossless = false;
    auto *handle = HandleFromBigInt(env, argv[0]);
    if (handle == nullptr || napi_get_value_bigint_uint64(env, argv[1], &call_id, &lossless) != napi_ok) return Int(env, -2);
    auto result = String(env, argv[2]);
    return Int(env, lossless ? notemeld_agent_complete_driver_call(
        handle, call_id, result.c_str()) : -2);
}

napi_value CancelTurn(napi_env env, napi_callback_info info) {
    size_t argc = 2;
    napi_value argv[2];
    if (napi_get_cb_info(env, info, &argc, argv, nullptr, nullptr) != napi_ok || argc != 2) return Int(env, -2);
    uint64_t token = 0;
    bool lossless = false;
    auto *handle = HandleFromBigInt(env, argv[0]);
    if (handle == nullptr || napi_get_value_bigint_uint64(env, argv[1], &token, &lossless) != napi_ok) return Int(env, -2);
    return Int(env, lossless ? notemeld_agent_cancel_turn(handle, token) : -2);
}

napi_value SteerTurn(napi_env env, napi_callback_info info) {
    size_t argc = 3;
    napi_value argv[3];
    if (napi_get_cb_info(env, info, &argc, argv, nullptr, nullptr) != napi_ok || argc != 3) return Int(env, -2);
    uint64_t token = 0;
    bool lossless = false;
    auto *handle = HandleFromBigInt(env, argv[0]);
    if (handle == nullptr || napi_get_value_bigint_uint64(env, argv[1], &token, &lossless) != napi_ok) return Int(env, -2);
    auto steer = String(env, argv[2]);
    return Int(env, lossless ? notemeld_agent_steer_turn(
        handle, token, steer.c_str()) : -2);
}

napi_value RuntimeFree(napi_env env, napi_callback_info info) {
    size_t argc = 1;
    napi_value argv[1];
    if (napi_get_cb_info(env, info, &argc, argv, nullptr, nullptr) != napi_ok || argc != 1) {
        return Int(env, -2);
    }
    auto *handle = HandleFromBigInt(env, argv[0]);
    if (handle != nullptr) notemeld_agent_runtime_free(handle);
    return Int(env, handle == nullptr ? -2 : 0);
}

napi_value SetCallbacks(napi_env env, napi_callback_info info) {
    size_t argc = 3;
    napi_value argv[3];
    if (napi_get_cb_info(env, info, &argc, argv, nullptr, nullptr) != napi_ok || argc != 3) return Int(env, -2);
    auto *handle = HandleFromBigInt(env, argv[0]);
    if (handle == nullptr || argc != 3) return Int(env, -2);
    for (size_t index = 1; index < 3; ++index) {
        napi_valuetype type = napi_undefined;
        if (napi_typeof(env, argv[index], &type) != napi_ok || type != napi_function) return Int(env, -2);
    }
    auto *bridge = new CallbackBridge();
    bridge->handle = handle;
    napi_value resource_name;
    napi_create_string_utf8(env, "notemeld-agent-events", NAPI_AUTO_LENGTH, &resource_name);
    if (napi_create_threadsafe_function(env, argv[1], nullptr, resource_name, 0, 1,
        bridge, FinalizeTsfn, nullptr, CallEventJs, &bridge->events) != napi_ok) { delete bridge; return Int(env, -9); }
    napi_create_string_utf8(env, "notemeld-agent-drivers", NAPI_AUTO_LENGTH, &resource_name);
    if (napi_create_threadsafe_function(env, argv[2], nullptr, resource_name, 0, 1,
        bridge, FinalizeTsfn, nullptr, CallDriverJs, &bridge->drivers) != napi_ok) {
        bridge->finalized.store(1);
        napi_release_threadsafe_function(bridge->events, napi_tsfn_release);
        return Int(env, -9);
    }
    const auto code = notemeld_agent_runtime_set_callbacks(
        handle, EventCallback, bridge, DriverCallback, bridge, ReleaseBridge, bridge);
    if (code == 0) {
        std::lock_guard<std::mutex> guard(bridges_mutex);
        bridges[handle] = bridge;
    } else {
        napi_release_threadsafe_function(bridge->events, napi_tsfn_release);
        napi_release_threadsafe_function(bridge->drivers, napi_tsfn_release);
    }
    return Int(env, code);
}

napi_value Init(napi_env env, napi_value exports) {
    napi_property_descriptor properties[] = {
        {"sdkVersion", nullptr, SdkVersion, nullptr, nullptr, nullptr, napi_default, nullptr},
        {"schemaVersion", nullptr, SchemaVersion, nullptr, nullptr, nullptr, napi_default, nullptr},
        {"runtimeNew", nullptr, RuntimeNew, nullptr, nullptr, nullptr, napi_default, nullptr},
        {"setCallbacks", nullptr, SetCallbacks, nullptr, nullptr, nullptr, napi_default, nullptr},
        {"submitTurn", nullptr, SubmitTurn, nullptr, nullptr, nullptr, napi_default, nullptr},
        {"completeDriverCall", nullptr, CompleteDriverCall, nullptr, nullptr, nullptr, napi_default, nullptr},
        {"cancelTurn", nullptr, CancelTurn, nullptr, nullptr, nullptr, napi_default, nullptr},
        {"steerTurn", nullptr, SteerTurn, nullptr, nullptr, nullptr, napi_default, nullptr},
        {"runtimeFree", nullptr, RuntimeFree, nullptr, nullptr, nullptr, napi_default, nullptr},
    };
    napi_define_properties(env, exports, sizeof(properties) / sizeof(properties[0]), properties);
    return exports;
}

}  // namespace

EXTERN_C_START
static napi_module module = {1, 0, nullptr, Init, "notemeld_agent_napi", nullptr, {0}};
EXTERN_C_END

static void RegisterModule() __attribute__((constructor));
static void RegisterModule() { napi_module_register(&module); }
