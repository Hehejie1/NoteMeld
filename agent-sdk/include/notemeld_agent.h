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
typedef int32_t (*NotemeldAgentEventCallback)(void * context, const char * event_json);
typedef int32_t (*NotemeldAgentDriverCallback)(void * context, const char * request_json);
typedef void (*NotemeldAgentContextReleaseCallback)(void * context);

/* ownership: static borrowed string | threading: any thread | errors: none */
const char * notemeld_agent_sdk_version(void);
/* ownership: static borrowed string | threading: any thread | errors: none */
const char * notemeld_agent_schema_version(void);
/* ownership: opaque monotonic token; runtime_free is idempotent | threading: any thread | errors: null on invalid config, unavailable runtime, or exhausted handle space */
AgentRuntimeHandle * notemeld_agent_runtime_new(const char * config_json);
/* ownership: JSON borrowed for callback; contexts remain valid until exactly-one release_callback ack | threading: callbacks may run concurrently; free closes gate and never waits | errors: typed FFI result */
int32_t notemeld_agent_runtime_set_callbacks(AgentRuntimeHandle * handle, NotemeldAgentEventCallback event_callback, void * event_context, NotemeldAgentDriverCallback driver_callback, void * driver_context, NotemeldAgentContextReleaseCallback release_callback, void * release_context);
/* ownership: input borrowed; returned observation token has bounded tombstone lifetime | threading: any thread | errors: zero; inspect last_error_json */
uint64_t notemeld_agent_submit_turn(AgentRuntimeHandle * handle, const char * request_json);
/* ownership: input borrowed | threading: atomic Pending to Completed transition | errors: duplicate/late/unknown distinct; 256 bounded tombstones then unknown */
int32_t notemeld_agent_complete_driver_call(AgentRuntimeHandle * handle, uint64_t call_id, const char * result_json);
/* ownership: none | threading: any thread; idempotent while tombstone retained | errors: typed FFI result */
int32_t notemeld_agent_cancel_turn(AgentRuntimeHandle * handle, uint64_t turn_token);
/* ownership: input borrowed | threading: any thread | errors: queued at next model safe point; terminal turns return FFI_TURN_TERMINAL */
int32_t notemeld_agent_steer_turn(AgentRuntimeHandle * handle, uint64_t turn_token, const char * steer_json);
/* ownership: none | threading: blocks caller; never UI event loop | errors: FFI_TIMEOUT distinct from internal error */
int32_t notemeld_agent_wait_turn(AgentRuntimeHandle * handle, uint64_t turn_token, uint64_t timeout_ms);
/* ownership: owned; release once with string_free | threading: any thread | errors: null if unavailable */
char * notemeld_agent_last_error_json(AgentRuntimeHandle * handle);
/* ownership: null-safe; non-null must be outstanding ABI allocation; foreign/double free undefined | threading: any thread | errors: none */
void notemeld_agent_string_free(char * value);
/* ownership: invalidates token; context valid through release ack | threading: non-blocking cancellation | errors: none */
void notemeld_agent_runtime_free(AgentRuntimeHandle * handle);

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
    NOTEMELD_AGENT_FFI_INTERNAL_ERROR = -9,
    NOTEMELD_AGENT_FFI_TIMEOUT = -10
};

#ifdef __cplusplus
}
#endif
#endif
