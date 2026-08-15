#include <cassert>
#include "../src/main/cpp/utf_codec.h"
int main() {
    const uint16_t emoji[] = {'{', '"', 'x', '"', ':', '"', 0xD83D, 0xDE00, '"', '}'};
    std::string utf8;
    assert(notemeld_utf::Utf16ToUtf8(emoji, sizeof(emoji) / sizeof(emoji[0]), &utf8));
    std::vector<uint16_t> roundtrip;
    assert(notemeld_utf::Utf8ToUtf16(utf8, &roundtrip));
    assert(roundtrip == std::vector<uint16_t>(emoji, emoji + sizeof(emoji) / sizeof(emoji[0])));
    const uint16_t invalid[] = {0xD83D, 'x'};
    assert(!notemeld_utf::Utf16ToUtf8(invalid, 2, &utf8));
    const uint16_t nul[] = {'x', 0, 'y'};
    assert(!notemeld_utf::Utf16ToUtf8(nul, 3, &utf8));
}
