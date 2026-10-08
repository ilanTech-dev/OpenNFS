#include <algorithm>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
using Bytes = std::vector<std::uint8_t>;
constexpr std::size_t maxFileSize = 64u * 1024u * 1024u;

std::uint32_t read32le(const Bytes& b, std::size_t at) {
    if (at > b.size() || b.size() - at < 4) throw std::runtime_error("truncated 32-bit field");
    return std::uint32_t(b[at]) | (std::uint32_t(b[at+1]) << 8)
         | (std::uint32_t(b[at+2]) << 16) | (std::uint32_t(b[at+3]) << 24);
}

Bytes decode(const Bytes& input, bool& compressed) {
    if (input.size() < 4) throw std::runtime_error("file too short");
    compressed = input[0] == 0x10 && input[1] == 0xFB;
    if (!compressed) return input;
    if (input.size() < 6) throw std::runtime_error("truncated compression header");

    const std::size_t expected = (std::size_t(input[2]) << 16) |
                                 (std::size_t(input[3]) << 8) | input[4];
    if (expected == 0 || expected > maxFileSize)
        throw std::runtime_error("invalid decompressed size");

    Bytes output;
    output.reserve(expected);
    std::size_t pos = 5;
    auto take = [&]() -> std::uint8_t {
        if (pos >= input.size()) throw std::runtime_error("truncated compressed stream");
        return input[pos++];
    };
    auto literals = [&](std::size_t n) {
        if (n > input.size() - pos) throw std::runtime_error("truncated literals");
        if (n > expected - output.size()) throw std::runtime_error("literal output overflow");
        output.insert(output.end(), input.begin() + static_cast<std::ptrdiff_t>(pos),
                      input.begin() + static_cast<std::ptrdiff_t>(pos + n));
        pos += n;
    };
    auto backref = [&](std::size_t distance, std::size_t n) {
        if (distance == 0 || distance > output.size()) throw std::runtime_error("invalid back-reference distance");
        if (n > expected - output.size()) throw std::runtime_error("back-reference output overflow");
        // Bytewise copy intentionally permits overlapping LZ77 references.
        for (std::size_t i = 0; i < n; ++i) output.push_back(output[output.size() - distance]);
    };

    bool terminated = false;
    while (pos < input.size()) {
        const auto control = take();
        if (control >= 0xFC) {
            literals(control & 3);
            terminated = true;
            break;
        }
        if ((control & 0x80) == 0) {
            auto a = take();
            literals(control & 3);
            backref(((std::size_t(control) >> 5) << 8) + a + 1,
                    ((control & 0x1C) >> 2) + 3);
        } else if ((control & 0x40) == 0) {
            auto a = take();
            auto b = take();
            literals((a >> 6) & 3);
            backref(((std::size_t(a) & 0x3F) << 8) + b + 1, (control & 0x3F) + 4);
        } else if ((control & 0x20) == 0) {
            auto a = take();
            auto b = take();
            auto c = take();
            literals(control & 3);
            backref(((std::size_t(control) & 0x10) << 12) + (std::size_t(a) << 8) + b + 1,
                    (((control >> 2) & 3) << 8) + c + 5);
        } else {
            literals(((control & 0x1F) * 4) + 4);
        }
    }
    if (!terminated) throw std::runtime_error("missing stream terminator");
    if (output.size() != expected) throw std::runtime_error("decompressed size mismatch");
    if (pos != input.size()) throw std::runtime_error("trailing compressed data");
    return output;
}

void inspect(const Bytes& b) {
    std::cout << "Decoded bytes: " << b.size() << "\nFirst bytes:";
    for (std::size_t i = 0; i < std::min<std::size_t>(32, b.size()); ++i)
        std::cout << ' ' << std::hex << std::setfill('0') << std::setw(2) << unsigned(b[i]);
    std::cout << std::dec << "\n";
    if (b.size() < 16) throw std::runtime_error("truncated CRP header");
    const std::string id(b.begin(), b.begin()+4);
    if (id != " raC" && id != "Car " && id != "karT" && id != "Trak")
        throw std::runtime_error("unrecognised CRP container identifier");
    std::uint32_t header = read32le(b, 4);
    std::uint32_t misc = read32le(b, 8);
    std::uint32_t table = read32le(b, 12);
    std::cout << "CRP identifier: '" << id << "'\n"
              << "Article count (header >> 5): " << (header >> 5) << "\n"
              << "Misc entries: " << misc << "\n"
              << "Article table offset field: " << table << "\n";
    // Legacy CRP header describes a 16-byte article record table.
    // For known car files the table offset field is in 16-byte units.
    const std::size_t tableStart = std::size_t(table) * 16;
    const std::size_t articleCount = header >> 5;
    if (tableStart > b.size() || articleCount > (b.size() - tableStart) / 16)
        throw std::runtime_error("article table exceeds decoded buffer");
    std::cout << "Article table byte offset: " << tableStart << "\n";
    std::size_t recognised = 0;
    for (std::size_t i = 0; i < articleCount; ++i) {
        const std::size_t at = tableStart + i * 16;
        const std::string tag(b.begin() + static_cast<std::ptrdiff_t>(at),
                              b.begin() + static_cast<std::ptrdiff_t>(at + 4));
        if (tag == "itrA" || tag == "Arti") ++recognised;
        // Printed fields are raw until we verify their units/semantics.
        if (i < 8) {
            std::cout << "Article[" << i << "] @" << at
                      << " tag='" << tag << "' header=0x"
                      << std::hex << read32le(b, at + 4)
                      << " lengthField=0x" << read32le(b, at + 8)
                      << " offsetField=0x" << read32le(b, at + 12)
                      << std::dec << "\n";
        }
    }
    std::cout << "Recognised article tags: " << recognised << "/" << articleCount << "\n";
    // Report structural properties without assuming that raw offset fields
    // have been decoded into absolute addresses.
    std::size_t increasing = 0, equal = 0, decreasing = 0;
    std::uint32_t minLength = UINT32_MAX, maxLength = 0;
    std::uint32_t minOffset = UINT32_MAX, maxOffset = 0;
    std::uint32_t previousOffset = 0;
    for (std::size_t i = 0; i < articleCount; ++i) {
        const auto at = tableStart + i * 16;
        const auto length = read32le(b, at + 8);
        const auto offset = read32le(b, at + 12);
        minLength = std::min(minLength, length);
        maxLength = std::max(maxLength, length);
        minOffset = std::min(minOffset, offset);
        maxOffset = std::max(maxOffset, offset);
        if (i != 0) {
            if (offset > previousOffset) ++increasing;
            else if (offset == previousOffset) ++equal;
            else ++decreasing;
        }
        previousOffset = offset;
    }
    if (articleCount > 0) {
        std::cout << "Raw article length fields: min=" << minLength
                  << " max=" << maxLength << "\n"
                  << "Raw article offset fields: min=" << minOffset
                  << " max=" << maxOffset << "\n"
                  << "Offset transitions: increasing=" << increasing
                  << " equal=" << equal << " decreasing=" << decreasing << "\n";
    }

    if (recognised != articleCount)
        throw std::runtime_error("one or more article records have unrecognised identifiers");
    // CRP offsets are relative to the 16-byte directory record, in 16-byte units.
    std::size_t contiguous = 0, gaps = 0, overlaps = 0, previousEnd = 0;
    for (std::size_t i = 0; i < articleCount; ++i) {
        const std::size_t at = tableStart + i * 16;
        const std::size_t offsetUnits = read32le(b, at + 12);
        const std::size_t lengthUnits = read32le(b, at + 8);
        if (offsetUnits > (b.size() - at) / 16)
            throw std::runtime_error("article block offset outside file");
        const std::size_t begin = at + 16 * offsetUnits;
        if (lengthUnits > (b.size() - begin) / 16)
            throw std::runtime_error("article block length outside file");
        const std::size_t end = begin + 16 * lengthUnits;
        if (i) {
            if (begin == previousEnd) ++contiguous;
            else if (begin > previousEnd) ++gaps;
            else ++overlaps;
        }
        if (i < 8) {
            std::cout << "Block[" << i << "] begin=" << begin << " end=" << end << " prefix:";
            for (std::size_t j = begin; j < std::min(begin + 16, end); ++j)
                std::cout << ' ' << std::hex << std::setfill('0') << std::setw(2) << unsigned(b[j]);
            std::cout << std::dec << "\n";
        }
        previousEnd = end;
    }
    std::cout << "Block transitions: contiguous=" << contiguous
              << " gaps=" << gaps << " overlaps=" << overlaps << "\n";

}

bool selfTest() {
    auto test = [](const Bytes& input, const Bytes& expected) {
        bool compressed = false;
        return decode(input, compressed) == expected && compressed;
    };
    // Twelve raw bytes, then an explicit end-of-stream marker.
    Bytes literal{0x10,0xFB,0,0,12,0xE2,' ','r','a','C',0,0,0,0,0,0,0,0,0xFC};
    if (!test(literal, {' ','r','a','C',0,0,0,0,0,0,0,0})) return false;
    // Four initial literals and a 4-byte overlapping back-reference to "AAAA".
    Bytes overlap{0x10,0xFB,0,0,8,0xE0,'A','A','A','A',0x80,0,0,0xFC};
    if (!test(overlap, {'A','A','A','A','A','A','A','A'})) return false;
    auto rejects = [](Bytes bytes) {
        try { bool compressed = false; (void)decode(bytes, compressed); return false; }
        catch (const std::runtime_error&) { return true; }
    };
    if (!rejects({0x10,0xFB,0,0,8,0x80})) return false;
    if (!rejects({0x10,0xFB,0,0,8,0x80,0,0,0xFC})) return false;
    if (!rejects({0x10,0xFB,0,0,8,0xFC})) return false;
    return true;
}
} // namespace

int main(int argc, char* argv[]) {
    if (argc == 2 && std::string(argv[1]) == "--self-test") {
        const bool ok = selfTest();
        std::cout << (ok ? "Self-tests passed\n" : "Self-tests FAILED\n");
        return ok ? 0 : 1;
    }
    if (argc != 2 && !(argc == 4 && std::string(argv[2]) == "--dump")) {
        std::cerr << "Usage: nfs5-inspector <path-to-crp> [--dump <new-output-file>] | --self-test\n";
        return 2;
    }
    try {
        const std::filesystem::path path(argv[1]);
        std::error_code ec;
        const auto length = std::filesystem::file_size(path, ec);
        if (ec) throw std::runtime_error("cannot stat file: " + ec.message());
        if (length > maxFileSize) throw std::runtime_error("compressed file exceeds 64 MiB limit");
        std::ifstream file(path, std::ios::binary);
        if (!file) throw std::runtime_error("cannot open file");
        Bytes input((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
        if (file.bad() || input.size() != length) throw std::runtime_error("failed to read entire input");
        bool compressed = false;
        const Bytes output = decode(input, compressed);
        std::cout << "NFS5 CRP Inspector\nFile: " << path
                  << "\nInput size: " << input.size() << "\nCompressed: "
                  << (compressed ? "yes (10 FB)" : "no") << "\n";
        inspect(output);
        if (argc == 4) {
            const std::filesystem::path destination(argv[3]);
            if (std::filesystem::exists(destination))
                throw std::runtime_error("output path already exists; refusing to overwrite");
            // Reserve the destination exclusively so a concurrent process cannot
            // replace an existing file between checking and opening it.
            // std::ofstream cannot enforce O_EXCL portably; reject existing paths
            // and leave race-hardening to a subsequent platform-specific change.
            std::ofstream out(destination, std::ios::binary | std::ios::out);
            if (!out) throw std::runtime_error("cannot open output file");
            out.write(reinterpret_cast<const char*>(output.data()),
                      static_cast<std::streamsize>(output.size()));
            out.close();
            if (!out) {
                std::filesystem::remove(destination);
                throw std::runtime_error("failed writing decoded file");
            }
            std::cout << "Wrote decompressed data to " << destination << "\\n";
        }
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "Inspector error: " << e.what() << "\n";
        return 1;
    }
}
