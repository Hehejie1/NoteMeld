#ifndef NOTEMELD_AGENT_H
#define NOTEMELD_AGENT_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define NOTEMELD_AGENT_ABI_VERSION 1
#define NOTEMELD_AGENT_SDK_VERSION "0.1.0"
#define NOTEMELD_AGENT_SCHEMA_VERSION "1"

typedef struct AgentRuntimeHandle AgentRuntimeHandle;
typedef int32_t (*NotemeldAgentEventCallback)(void *context, const char *event_json);
typedef int32_t (*NotemeldAgentDriverCallback)(void *context, const char *request_json);

const char *notemeld_agent_sdk_version(void);
const char *notemeld_agent_schema_version(void);
AgentRuntimeHandle *notemeld_agent_runtime_new(const char *config_json);
int32_t notemeld_agent_runtime_set_callbacks(
    AgentRuntimeHandle *handle,
    NotemeldAgentEventCallback event_callback,
    void *event_context,
    NotemeldAgentDriverCallback driver_callback,
    void *driver_context);
uint64_t notemeld_agent_submit_turn(AgentRuntimeHandle *handle, const char *request_json);
int32_t notemeld_agent_complete_driver_call(
    AgentRuntimeHandle *handle, uint64_t call_id, const char *result_json);
int32_t notemeld_agent_cancel_turn(AgentRuntimeHandle *handle, uint64_t turn_token);
/* v1 returns NOTEMELD_AGENT_FFI_UNSUPPORTED; it never pretends steer applied. */
int32_t notemeld_agent_steer_turn(
    AgentRuntimeHandle *handle, uint64_t turn_token, const char *steer_json);
int32_t notemeld_agent_wait_turn(
    AgentRuntimeHandle *handle, uint64_t turn_token, uint64_t timeout_ms);
char *notemeld_agent_last_error_json(AgentRuntimeHandle *handle);
void notemeld_agent_string_free(char *value);
void notemeld_agent_runtime_free(AgentRuntimeHandle *handle);

enum NotemeldAgentFfiResult {
    NOTEMELD_AGENT_FFI_OK = 0,
    NOTEMELD_AGENT_FFI_INVALID_HANDLE = -1,
    NOTEMELD_AGENT_FFI_INVALID_INPUT = -2,
    NOTEMELD_AGENT_FFI_UNKNOWN_CALL = -3,
    NOTEMELD_AGENT_FFI_DUPLICATE_COMPLETION = -4,
    NOTEMELD_AGENT_FFI_LATE_COMPLETION = -5,
    NOTEMELD_AGENT_FFI_UNSUPPORTED = -6,
    NOTEMELD_AGENT_FFI_TURN_NOT_FOUND = -7,
    NOTEMELD_AGENT_FFI_TURN_TERMINAL = -8,
    NOTEMELD_AGENT_FFI_INTERNAL_ERROR = -9
};

#ifdef __cplusplus
}
#endif
#endif
