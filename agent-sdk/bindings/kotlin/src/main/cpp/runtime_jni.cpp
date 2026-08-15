#include <jni.h>
#include <cstdint>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>
#include "notemeld_agent.h"

namespace {
JavaVM *vm = nullptr;
struct Bridge { AgentRuntimeHandle *handle; jobject runtime; };
std::mutex bridge_mutex;
std::unordered_map<AgentRuntimeHandle *, Bridge *> bridges;
std::vector<Bridge *> retired;

JNIEnv *CurrentEnv(bool *attached) {
    JNIEnv *env = nullptr;
    *attached = vm->GetEnv(reinterpret_cast<void **>(&env), JNI_VERSION_1_6) == JNI_EDETACHED;
    if (*attached && vm->AttachCurrentThread(&env, nullptr) != JNI_OK) return nullptr;
    return env;
}

int32_t EventCallback(void *context, const char *wire) {
    auto *bridge = static_cast<Bridge *>(context);
    bool attached = false;
    JNIEnv *env = CurrentEnv(&attached);
    if (!env || !bridge || !wire) return -2;
    auto cls = env->GetObjectClass(bridge->runtime);
    auto method = env->GetMethodID(cls, "receiveEvent", "(Ljava/lang/String;)I");
    auto value = env->NewStringUTF(wire);
    auto code = env->CallIntMethod(bridge->runtime, method, value);
    env->DeleteLocalRef(value);
    env->DeleteLocalRef(cls);
    if (env->ExceptionCheck()) { env->ExceptionClear(); code = -9; }
    if (attached) vm->DetachCurrentThread();
    return code;
}

uint64_t CallId(const std::string &wire) {
    const std::string marker = "\"call_id\":";
    auto start = wire.find(marker);
    if (start == std::string::npos) return 0;
    try { return std::stoull(wire.substr(start + marker.size())); } catch (...) { return 0; }
}

int32_t DriverCallback(void *context, const char *wire) {
    auto *bridge = static_cast<Bridge *>(context);
    bool attached = false;
    JNIEnv *env = CurrentEnv(&attached);
    if (!env || !bridge || !wire) return -2;
    auto cls = env->GetObjectClass(bridge->runtime);
    auto method = env->GetMethodID(cls, "receiveDriver", "(Ljava/lang/String;)Ljava/lang/String;");
    auto request = env->NewStringUTF(wire);
    auto result = static_cast<jstring>(env->CallObjectMethod(bridge->runtime, method, request));
    int32_t code = -9;
    if (!env->ExceptionCheck() && result != nullptr) {
        const char *text = env->GetStringUTFChars(result, nullptr);
        code = notemeld_agent_complete_driver_call(bridge->handle, CallId(wire), text);
        env->ReleaseStringUTFChars(result, text);
    } else if (env->ExceptionCheck()) {
        env->ExceptionClear();
    }
    env->DeleteLocalRef(request);
    if (result != nullptr) env->DeleteLocalRef(result);
    env->DeleteLocalRef(cls);
    if (attached) vm->DetachCurrentThread();
    return code;
}

std::string JavaString(JNIEnv *env, jstring value) {
    const char *text = env->GetStringUTFChars(value, nullptr);
    std::string result(text);
    env->ReleaseStringUTFChars(value, text);
    return result;
}
}  // namespace

extern "C" jint JNI_OnLoad(JavaVM *java_vm, void *) { vm = java_vm; return JNI_VERSION_1_6; }
extern "C" void JNI_OnUnload(JavaVM *java_vm, void *) {
    JNIEnv *env = nullptr;
    if (java_vm->GetEnv(reinterpret_cast<void **>(&env), JNI_VERSION_1_6) != JNI_OK) return;
    for (auto *bridge : retired) { env->DeleteGlobalRef(bridge->runtime); delete bridge; }
    retired.clear();
}
#define JNI(name) Java_wiki_notemeld_agent_Runtime_##name
extern "C" JNIEXPORT jstring JNICALL JNI(nativeSdkVersion)(JNIEnv *e,jclass){return e->NewStringUTF(notemeld_agent_sdk_version());}
extern "C" JNIEXPORT jstring JNICALL JNI(nativeSchemaVersion)(JNIEnv *e,jclass){return e->NewStringUTF(notemeld_agent_schema_version());}
extern "C" JNIEXPORT jlong JNICALL JNI(nativeNew)(JNIEnv *e,jclass,jstring v){auto s=JavaString(e,v);return reinterpret_cast<jlong>(notemeld_agent_runtime_new(s.c_str()));}
extern "C" JNIEXPORT jint JNICALL JNI(nativeSetCallbacks)(JNIEnv *e,jclass,jlong raw,jobject runtime){auto *h=reinterpret_cast<AgentRuntimeHandle *>(raw);auto *b=new Bridge{h,e->NewGlobalRef(runtime)};auto code=notemeld_agent_runtime_set_callbacks(h,EventCallback,b,DriverCallback,b);if(code==0){std::lock_guard<std::mutex> g(bridge_mutex);bridges[h]=b;}else{e->DeleteGlobalRef(b->runtime);delete b;}return code;}
extern "C" JNIEXPORT jlong JNICALL JNI(nativeSubmit)(JNIEnv *e,jclass,jlong raw,jstring v){auto s=JavaString(e,v);return notemeld_agent_submit_turn(reinterpret_cast<AgentRuntimeHandle *>(raw),s.c_str());}
extern "C" JNIEXPORT jint JNICALL JNI(nativeCancel)(JNIEnv*,jclass,jlong raw,jlong token){return notemeld_agent_cancel_turn(reinterpret_cast<AgentRuntimeHandle *>(raw),token);}
extern "C" JNIEXPORT jint JNICALL JNI(nativeWait)(JNIEnv*,jclass,jlong raw,jlong token,jlong timeout){return notemeld_agent_wait_turn(reinterpret_cast<AgentRuntimeHandle *>(raw),token,timeout);}
extern "C" JNIEXPORT jint JNICALL JNI(nativeSteer)(JNIEnv *e,jclass,jlong raw,jlong token,jstring v){auto s=JavaString(e,v);return notemeld_agent_steer_turn(reinterpret_cast<AgentRuntimeHandle *>(raw),token,s.c_str());}
extern "C" JNIEXPORT void JNICALL JNI(nativeFree)(JNIEnv*,jclass,jlong raw){auto *h=reinterpret_cast<AgentRuntimeHandle *>(raw);notemeld_agent_runtime_free(h);std::lock_guard<std::mutex> g(bridge_mutex);auto it=bridges.find(h);if(it!=bridges.end()){retired.push_back(it->second);bridges.erase(it);}}
