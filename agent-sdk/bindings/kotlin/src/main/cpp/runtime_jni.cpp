#include <jni.h>
#include <cstdint>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>
#include "notemeld_agent.h"
#include "utf_codec.h"

namespace {
JavaVM *vm = nullptr;
struct Bridge { AgentRuntimeHandle *handle; jobject runtime; };
std::mutex bridge_mutex;
std::unordered_map<AgentRuntimeHandle *, Bridge *> bridges;

JNIEnv *CurrentEnv(bool *attached) {
    JNIEnv *env = nullptr;
    *attached = vm->GetEnv(reinterpret_cast<void **>(&env), JNI_VERSION_1_6) == JNI_EDETACHED;
    if (*attached && vm->AttachCurrentThread(&env, nullptr) != JNI_OK) return nullptr;
    return env;
}

bool JavaString(JNIEnv *env, jstring value, std::string *out) {
    if (!value) return false;
    const jchar *chars = env->GetStringChars(value, nullptr);
    if (!chars) return false;
    const auto size = static_cast<size_t>(env->GetStringLength(value));
    const bool ok = notemeld_utf::Utf16ToUtf8(reinterpret_cast<const uint16_t *>(chars), size, out);
    env->ReleaseStringChars(value, chars);
    return ok;
}

jstring NewJavaString(JNIEnv *env, const std::string &value) {
    std::vector<uint16_t> utf16;
    if (!notemeld_utf::Utf8ToUtf16(value, &utf16)) return nullptr;
    return env->NewString(reinterpret_cast<const jchar *>(utf16.data()), static_cast<jsize>(utf16.size()));
}

uint64_t CallId(const std::string &wire) {
    const std::string marker = "\"call_id\":";
    auto start = wire.find(marker);
    if (start == std::string::npos) return 0;
    try { return std::stoull(wire.substr(start + marker.size())); } catch (...) { return 0; }
}

int32_t EventCallback(void *context, const char *wire) {
    auto *bridge = static_cast<Bridge *>(context); bool attached = false;
    JNIEnv *env = CurrentEnv(&attached);
    if (!env || !bridge || !wire) return -2;
    auto cls = env->GetObjectClass(bridge->runtime);
    auto method = cls ? env->GetMethodID(cls, "receiveEvent", "(Ljava/lang/String;)I") : nullptr;
    auto value = NewJavaString(env, wire);
    int32_t code = (method && value) ? env->CallIntMethod(bridge->runtime, method, value) : -2;
    if (env->ExceptionCheck()) { env->ExceptionClear(); code = -9; }
    if (value) env->DeleteLocalRef(value); if (cls) env->DeleteLocalRef(cls);
    if (attached) vm->DetachCurrentThread(); return code;
}

int32_t DriverCallback(void *context, const char *wire) {
    auto *bridge = static_cast<Bridge *>(context); bool attached = false;
    JNIEnv *env = CurrentEnv(&attached);
    if (!env || !bridge || !wire) return -2;
    const std::string request_wire(wire); const auto call_id = CallId(request_wire);
    auto cls = env->GetObjectClass(bridge->runtime);
    auto method = cls ? env->GetMethodID(cls, "receiveDriver", "(Ljava/lang/String;)Ljava/lang/String;") : nullptr;
    auto request = NewJavaString(env, request_wire);
    auto result = (method && request) ? static_cast<jstring>(env->CallObjectMethod(bridge->runtime, method, request)) : nullptr;
    std::string result_wire;
    if (env->ExceptionCheck()) { env->ExceptionClear(); result = nullptr; }
    if (!result || !JavaString(env, result, &result_wire)) result_wire = R"({"schema_version":"1","ok":false,"error":{"code":"sdk_internal_error","message":"host driver failed"}})";
    const int32_t code = call_id ? notemeld_agent_complete_driver_call(bridge->handle, call_id, result_wire.c_str()) : -2;
    if (request) env->DeleteLocalRef(request); if (result) env->DeleteLocalRef(result); if (cls) env->DeleteLocalRef(cls);
    if (attached) vm->DetachCurrentThread(); return code;
}

void ReleaseBridge(void *context) {
    auto *bridge = static_cast<Bridge *>(context); if (!bridge) return;
    { std::lock_guard<std::mutex> guard(bridge_mutex); bridges.erase(bridge->handle); }
    bool attached = false; JNIEnv *env = CurrentEnv(&attached);
    if (env) env->DeleteGlobalRef(bridge->runtime);
    delete bridge;
    if (attached) vm->DetachCurrentThread();
}
}  // namespace

extern "C" jint JNI_OnLoad(JavaVM *java_vm, void *) { vm = java_vm; return JNI_VERSION_1_6; }
#define JNI(name) Java_wiki_notemeld_agent_Runtime_##name
extern "C" JNIEXPORT jstring JNICALL JNI(nativeSdkVersion)(JNIEnv *e,jclass){return NewJavaString(e,notemeld_agent_sdk_version());}
extern "C" JNIEXPORT jstring JNICALL JNI(nativeSchemaVersion)(JNIEnv *e,jclass){return NewJavaString(e,notemeld_agent_schema_version());}
extern "C" JNIEXPORT jlong JNICALL JNI(nativeNew)(JNIEnv *e,jclass,jstring v){std::string s;if(!JavaString(e,v,&s))return 0;return reinterpret_cast<jlong>(notemeld_agent_runtime_new(s.c_str()));}
extern "C" JNIEXPORT jint JNICALL JNI(nativeSetCallbacks)(JNIEnv *e,jclass,jlong raw,jobject runtime){auto *h=reinterpret_cast<AgentRuntimeHandle *>(raw);if(!h||!runtime)return -2;auto global=e->NewGlobalRef(runtime);if(!global)return -9;auto *b=new Bridge{h,global};auto code=notemeld_agent_runtime_set_callbacks(h,EventCallback,b,DriverCallback,b,ReleaseBridge,b);if(code==0){std::lock_guard<std::mutex> g(bridge_mutex);bridges[h]=b;}else{e->DeleteGlobalRef(global);delete b;}return code;}
extern "C" JNIEXPORT jlong JNICALL JNI(nativeSubmit)(JNIEnv *e,jclass,jlong raw,jstring v){std::string s;if(!JavaString(e,v,&s))return 0;return notemeld_agent_submit_turn(reinterpret_cast<AgentRuntimeHandle *>(raw),s.c_str());}
extern "C" JNIEXPORT jint JNICALL JNI(nativeCancel)(JNIEnv*,jclass,jlong raw,jlong token){return notemeld_agent_cancel_turn(reinterpret_cast<AgentRuntimeHandle *>(raw),token);}
extern "C" JNIEXPORT jint JNICALL JNI(nativeWait)(JNIEnv*,jclass,jlong raw,jlong token,jlong timeout){return notemeld_agent_wait_turn(reinterpret_cast<AgentRuntimeHandle *>(raw),token,timeout);}
extern "C" JNIEXPORT jint JNICALL JNI(nativeSteer)(JNIEnv *e,jclass,jlong raw,jlong token,jstring v){std::string s;if(!JavaString(e,v,&s))return -2;return notemeld_agent_steer_turn(reinterpret_cast<AgentRuntimeHandle *>(raw),token,s.c_str());}
extern "C" JNIEXPORT void JNICALL JNI(nativeFree)(JNIEnv*,jclass,jlong raw){notemeld_agent_runtime_free(reinterpret_cast<AgentRuntimeHandle *>(raw));}
