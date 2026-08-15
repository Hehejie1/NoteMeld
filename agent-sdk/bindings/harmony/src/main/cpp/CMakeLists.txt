cmake_minimum_required(VERSION 3.5)
project(notemeld_agent_napi)

add_library(notemeld_agent_napi SHARED napi_init.cpp)
target_include_directories(notemeld_agent_napi PRIVATE ../../../../../include)
target_link_libraries(notemeld_agent_napi PUBLIC libace_napi.z.so notemeld_agent)
