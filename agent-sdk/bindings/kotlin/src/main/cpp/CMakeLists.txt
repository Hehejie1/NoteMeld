cmake_minimum_required(VERSION 3.22.1)
project(notemeld_agent_jni)

add_library(notemeld_agent SHARED IMPORTED)
set_target_properties(notemeld_agent PROPERTIES
    IMPORTED_LOCATION "${NOTEMELD_AGENT_LIBRARY_DIR}/${ANDROID_ABI}/libnotemeld_agent.so")
add_library(notemeld_agent_jni SHARED runtime_jni.cpp)
target_include_directories(notemeld_agent_jni PRIVATE ../../../../../include)
target_link_libraries(notemeld_agent_jni notemeld_agent log)
