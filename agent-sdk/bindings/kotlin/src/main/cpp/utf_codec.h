#pragma once
#include <cstdint>
#include <string>
#include <vector>

namespace notemeld_utf {
inline bool Utf16ToUtf8(const uint16_t *input, size_t size, std::string *out) {
    out->clear();
    for (size_t i = 0; i < size; ++i) {
        uint32_t cp = input[i];
        if (cp == 0) return false;
        if (cp >= 0xD800 && cp <= 0xDBFF) {
            if (++i >= size || input[i] < 0xDC00 || input[i] > 0xDFFF) return false;
            cp = 0x10000 + ((cp - 0xD800) << 10) + (input[i] - 0xDC00);
        } else if (cp >= 0xDC00 && cp <= 0xDFFF) return false;
        if (cp <= 0x7F) out->push_back(static_cast<char>(cp));
        else if (cp <= 0x7FF) { out->push_back(static_cast<char>(0xC0 | cp >> 6)); out->push_back(static_cast<char>(0x80 | (cp & 0x3F))); }
        else if (cp <= 0xFFFF) { out->push_back(static_cast<char>(0xE0 | cp >> 12)); out->push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3F))); out->push_back(static_cast<char>(0x80 | (cp & 0x3F))); }
        else { out->push_back(static_cast<char>(0xF0 | cp >> 18)); out->push_back(static_cast<char>(0x80 | ((cp >> 12) & 0x3F))); out->push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3F))); out->push_back(static_cast<char>(0x80 | (cp & 0x3F))); }
    }
    return true;
}

inline bool Utf8ToUtf16(const std::string &input, std::vector<uint16_t> *out) {
    out->clear();
    for (size_t i = 0; i < input.size();) {
        uint8_t first = static_cast<uint8_t>(input[i++]);
        uint32_t cp; size_t trailing;
        if (first <= 0x7F) { cp = first; trailing = 0; }
        else if ((first & 0xE0) == 0xC0) { cp = first & 0x1F; trailing = 1; }
        else if ((first & 0xF0) == 0xE0) { cp = first & 0x0F; trailing = 2; }
        else if ((first & 0xF8) == 0xF0) { cp = first & 0x07; trailing = 3; }
        else return false;
        if (i + trailing > input.size()) return false;
        for (size_t j = 0; j < trailing; ++j) { uint8_t next = static_cast<uint8_t>(input[i++]); if ((next & 0xC0) != 0x80) return false; cp = (cp << 6) | (next & 0x3F); }
        if ((trailing == 1 && cp < 0x80) || (trailing == 2 && cp < 0x800) || (trailing == 3 && cp < 0x10000) || cp > 0x10FFFF || (cp >= 0xD800 && cp <= 0xDFFF) || cp == 0) return false;
        if (cp <= 0xFFFF) out->push_back(static_cast<uint16_t>(cp));
        else { cp -= 0x10000; out->push_back(static_cast<uint16_t>(0xD800 | cp >> 10)); out->push_back(static_cast<uint16_t>(0xDC00 | (cp & 0x3FF))); }
    }
    return true;
}
}  // namespace notemeld_utf
