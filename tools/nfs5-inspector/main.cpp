#include <algorithm>
#include <cstdint>
#include <cstring>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <iterator>
#include <map>
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
    std::map<std::string, std::size_t> partTags;
    std::size_t partRecords = 0;
    std::size_t vertexShown = 0, vertexCandidates = 0, vertexValid = 0, stride16 = 0;
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
        // Each article block appears to consist of 16-byte part descriptors.
        // Classify their two-byte tag field at offsets +2/+3, without
        // interpreting payload offsets or assuming the geometry is valid.
        for (std::size_t record = begin; record < end; record += 16) {
            const std::string tag{
                static_cast<char>(b[record + 2]),
                static_cast<char>(b[record + 3])
            };
            ++partTags[tag];
            ++partRecords;
            if (tag == "tv") {
                ++vertexCandidates;
                // Legacy VERTEX_PART descriptor uses lengthInfo >> 8 as bytes,
                // an element count at +8, and a record-relative byte offset at +12.
                const std::uint32_t rawLength = read32le(b, record + 4);
                const std::size_t payloadLength = rawLength >> 8;
                const std::size_t count = read32le(b, record + 8);
                const std::size_t offset = read32le(b, record + 12);
                const bool inRange = offset <= b.size() - record &&
                    payloadLength <= b.size() - (record + offset);
                if (inRange) ++vertexValid;
                if (count > 0 && count <= SIZE_MAX / 16 && payloadLength == count * 16) ++stride16;
                if (vertexShown++ < 8) {
                    std::cout << "Vertex candidate[" << (vertexShown - 1)
                              << "] article=" << i << " descriptor=" << record
                              << " payloadOffset=" << (inRange ? record + offset : 0)
                              << " payloadBytes=" << payloadLength
                              << " elementCount=" << count
                              << " inRange=" << (inRange ? "yes" : "no") << "\n";
                    if (inRange && count && payloadLength >= 16) {
                        const auto start = record + offset;
                        auto asFloat = [&](std::size_t at) {
                            const std::uint32_t bits = read32le(b, at);
                            float result;
                            std::memcpy(&result, &bits, sizeof(result));
                            return result;
                        };
                        const float x = asFloat(start), y = asFloat(start+4);
                        const float z = asFloat(start+8), w = asFloat(start+12);
                        std::cout << "  candidate float32 xyzw: " << x << ", " << y
                                  << ", " << z << ", " << w
                                  << " finite=" << ((std::isfinite(x) && std::isfinite(y) &&
                                      std::isfinite(z) && std::isfinite(w)) ? "yes" : "no") << "\n";
                    }
                }
            }
        }
        previousEnd = end;
    }
    std::cout << "Vertex payload candidates in range: " << vertexValid << "/" << vertexCandidates << "\n";
    std::cout << "Vertex descriptors with 16-byte stride: " << stride16 << "/" << vertexCandidates << "\n";
    std::cout << "Article part descriptors: " << partRecords << "\n";
    std::cout << "Part tag frequencies (raw byte order):\n";
    for (const auto& [tag, count] : partTags) {
        std::cout << "  ";
        for (unsigned char c : tag)
            if (c >= 32 && c <= 126) std::cout << static_cast<char>(c);
            else std::cout << "?";
        std::cout << ": " << count << "\n";
    }
    std::cout << "Block transitions: contiguous=" << contiguous
              << " gaps=" << gaps << " overlaps=" << overlaps << "\n";

}


void exportVertices(const Bytes& b, const std::filesystem::path& destination, bool levelZeroOnly = false) {
    if (std::filesystem::exists(destination))
        throw std::runtime_error("OBJ output already exists; refusing to overwrite");
    if (b.size() < 16) throw std::runtime_error("CRP header too short");
    const std::size_t articleCount = read32le(b, 4) >> 5;
    const std::size_t directory = std::size_t(read32le(b, 12)) * 16;
    if (directory > b.size() || articleCount > (b.size() - directory) / 16)
        throw std::runtime_error("invalid article directory");
    std::ofstream out(destination);
    if (!out) throw std::runtime_error("cannot open OBJ output");
    out << "# NFS5 vertex-only diagnostic; no polygon faces or transforms yet\n";
    out << "# Local personal game data; do not redistribute this generated file\n";
    out << std::setprecision(9);
    std::size_t total = 0, skipped = 0;
    for (std::size_t article = 0; article < articleCount; ++article) {
        const std::size_t at = directory + article * 16;
        const std::size_t offsetUnits = read32le(b, at + 12);
        const std::size_t lengthUnits = read32le(b, at + 8);
        if (offsetUnits > (b.size() - at) / 16) throw std::runtime_error("invalid article offset");
        const std::size_t begin = at + offsetUnits * 16;
        if (lengthUnits > (b.size() - begin) / 16) throw std::runtime_error("invalid article size");
        const std::size_t end = begin + lengthUnits * 16;
        for (std::size_t record = begin; record < end; record += 16) {
            if (b[record + 2] != 't' || b[record + 3] != 'v') continue;
            // CrpLib LEVELINDEX_LEVEL extracts the high nibble of the part index.
            const unsigned partInfo = unsigned(b[record]) | (unsigned(b[record + 1]) << 8);
            if (levelZeroOnly && ((partInfo & 0xF0u) >> 4) != 0) continue;
            const std::size_t bytes = read32le(b, record + 4) >> 8;
            const std::size_t count = read32le(b, record + 8);
            const std::size_t relative = read32le(b, record + 12);
            if (count == 0 || count > SIZE_MAX / 16 || bytes != count * 16 ||
                relative > b.size() - record || bytes > b.size() - record - relative) {
                ++skipped;
                continue;
            }
            const std::size_t start = record + relative;
            out << "g article_" << article << "_descriptor_" << record << "\n";
            const std::size_t first = total + 1;
            for (std::size_t j = 0; j < count; ++j) {
                auto asFloat = [&](std::size_t loc) {
                    const std::uint32_t bits = read32le(b, loc);
                    float value;
                    std::memcpy(&value, &bits, sizeof value);
                    return value;
                };
                const std::size_t atVertex = start + j * 16;
                const float x = asFloat(atVertex), y = asFloat(atVertex + 4);
                const float z = asFloat(atVertex + 8);
                if (!(std::isfinite(x) && std::isfinite(y) && std::isfinite(z)))
                    throw std::runtime_error("non-finite vertex coordinate");
                out << "v " << x << ' ' << y << ' ' << z << "\n";
                ++total;
            }
            // OBJ point elements ensure vertex-only groups are visible in viewers
            // that support point geometry (Blender imports them as vertices).
            for (std::size_t idx = first; idx <= total; ++idx) out << "p " << idx << "\n";
        }
    }
    out.close();
    if (!out) throw std::runtime_error("failed writing OBJ file");
    std::cout << "Vertex-only OBJ: " << destination << "\n"
              << "Vertices: " << total << " skipped descriptors: " << skipped << "\n";
}


void inspectParts(const Bytes& b) {
    if (b.size() < 16) throw std::runtime_error("CRP header too short");
    const std::size_t articles = read32le(b, 4) >> 5;
    const std::size_t dir = std::size_t(read32le(b, 12)) * 16;
    if (dir > b.size() || articles > (b.size() - dir) / 16)
        throw std::runtime_error("article directory outside file");

    std::size_t foundNames = 0, invalidNames = 0, foundBases = 0;
    std::map<unsigned, std::size_t> vertexPartInfos;
    std::cout << "Article metadata probe (first 24 articles):\n";
    for (std::size_t i = 0; i < articles; ++i) {
        const std::size_t record = dir + 16 * i;
        const std::size_t offsetUnits = read32le(b, record + 12);
        const std::size_t lengthUnits = read32le(b, record + 8);
        if (offsetUnits > (b.size() - record) / 16)
            throw std::runtime_error("article block offset out of bounds");
        const std::size_t begin = record + 16 * offsetUnits;
        if (lengthUnits > (b.size() - begin) / 16)
            throw std::runtime_error("article block length out of bounds");
        const std::size_t end = begin + 16 * lengthUnits;
        std::string name = "(missing)";
        std::uint32_t baseRaw = 0;
        bool hasBase = false;
        for (std::size_t part = begin; part < end; part += 16) {
            const std::string tag(b.begin()+static_cast<std::ptrdiff_t>(part),
                                  b.begin()+static_cast<std::ptrdiff_t>(part+4));
            if (tag == "emaN" || tag == "Name") {
                const std::size_t byteLength = read32le(b, part + 4) >> 8;
                const std::size_t relative = read32le(b, part + 12);
                if (relative > b.size()-part || byteLength > b.size()-part-relative || byteLength == 0 || byteLength > 4096) {
                    ++invalidNames;
                    name = "(invalid name payload)";
                } else {
                    ++foundNames;
                    const std::size_t start = part + relative;
                    name.clear();
                    for (std::size_t j = 0; j < byteLength && b[start+j] != 0; ++j) {
                        const unsigned char c = b[start+j];
                        name.push_back(c >= 32 && c <= 126 ? static_cast<char>(c) : '?');
                    }
                }
            } else if (tag == "esaB" || tag == "Base") {
                ++foundBases;
                hasBase = true;
                baseRaw = read32le(b, part + 4);
            } else if (b[part+2] == 't' && b[part+3] == 'v') {
                const unsigned info = unsigned(b[part]) | (unsigned(b[part+1]) << 8);
                ++vertexPartInfos[info];
            }
        }
        if (i < 24) {
            std::cout << "Article " << i << " name='" << name
                      << "' baseLengthInfo=0x" << std::hex << (hasBase ? baseRaw : 0)
                      << std::dec << " descriptors=" << lengthUnits << "\n";
        }
    }
    std::cout << "Names found: " << foundNames << " invalid: " << invalidNames
              << " base descriptors: " << foundBases << "\n"
              << "Raw vertex part-info values (first 32):\n";
    std::size_t printed=0;
    for (const auto& [info,count] : vertexPartInfos) {
        if (printed++ == 32) break;
        std::cout << "  0x" << std::hex << info << std::dec << ": " << count << "\n";
    }
}


void inspectPolygons(const Bytes& b, std::size_t articleIndex) {
    if (b.size() < 16) throw std::runtime_error("CRP header too short");
    const std::size_t count = read32le(b, 4) >> 5;
    const std::size_t directory = std::size_t(read32le(b, 12)) * 16;
    if (directory > b.size() || count > (b.size() - directory) / 16 || articleIndex >= count)
        throw std::runtime_error("article index outside directory");
    const std::size_t at = directory + articleIndex * 16;
    const std::size_t relative = read32le(b, at + 12);
    const std::size_t length = read32le(b, at + 8);
    if (relative > (b.size() - at) / 16) throw std::runtime_error("article offset outside file");
    const std::size_t begin = at + relative * 16;
    if (length > (b.size() - begin) / 16) throw std::runtime_error("article length outside file");
    const std::size_t end = begin + length * 16;
    std::cout << "Polygon descriptor probe article=" << articleIndex
              << " (Body=5 in 993.crp)\n";
    std::size_t found = 0;
    for (std::size_t p = begin; p < end; p += 16) {
        if (b[p+2] != 'r' || b[p+3] != 'p') continue;
        ++found;
        const std::size_t payloadBytes = read32le(b, p+4) >> 8;
        const std::size_t entryCount = read32le(b, p+8);
        const std::size_t payloadRelative = read32le(b, p+12);
        const bool valid = payloadRelative <= b.size()-p &&
                           payloadBytes <= b.size()-p-payloadRelative;
        const unsigned info = unsigned(b[p]) | (unsigned(b[p+1]) << 8);
        std::cout << "rp[" << found-1 << "] descriptor=" << p
                  << " partInfo=0x" << std::hex << info << std::dec
                  << " level=" << ((info & 0xF0u) >> 4)
                  << " subindex=" << (info & 0xFu)
                  << " countField=" << entryCount
                  << " payloadBytes=" << payloadBytes
                  << " payloadOffset=" << (valid ? p+payloadRelative : 0)
                  << " inRange=" << (valid ? "yes" : "no") << "\n";
        if (valid && payloadBytes >= 48) {
            const std::size_t base = p + payloadRelative;
            const std::size_t infoCount = read32le(b, base + 40);
            const std::size_t indexCount = read32le(b, base + 44);
            const std::size_t fixed = 48;
            const bool headerSafe = infoCount <= (payloadBytes - fixed) / 16 &&
                indexCount <= (payloadBytes - fixed - infoCount*16) / 8;
            if (headerSafe) {
                const std::size_t streamStart = fixed + infoCount*16 + indexCount*8;
                const bool streamSafe = indexCount == 0 ||
                    (entryCount <= (payloadBytes - streamStart) / indexCount);
                std::cout << "  CrpLib layout: infoCount=" << infoCount
                          << " indexCount=" << indexCount
                          << " streamStart=" << streamStart
                          << " streamFits=" << (streamSafe ? "yes" : "no") << "\n";
                if (streamSafe && indexCount <= 8) {
                    for (std::size_t stream=0; stream<indexCount; ++stream) {
                        const std::size_t d = base + 48 + infoCount*16 + stream*8;
                        const unsigned streamIndex = unsigned(b[d]) | (unsigned(b[d+1]) << 8);
                        const unsigned streamId = unsigned(b[d+2]) | (unsigned(b[d+3]) << 8);
                        const std::size_t streamOffset = read32le(b,d+4);
                        std::cout << "    stream[" << stream << "] index=" << streamIndex
                                  << " id=" << streamId << " offset=" << streamOffset
                                  << " inRange=" << (streamOffset <= entryCount*indexCount &&
                                      entryCount <= entryCount*indexCount-streamOffset ? "yes" : "no") << "\n";
                    }
                }
            } else {
                std::cout << "  CrpLib layout: invalid header table counts\n";
            }
        }
        if (valid && payloadBytes > 0) {
            std::cout << "  prefix:";
            const auto n = std::min<std::size_t>(payloadBytes, 32);
            for (std::size_t j = 0; j < n; ++j)
                std::cout << ' ' << std::hex << std::setfill('0')
                          << std::setw(2) << unsigned(b[p+payloadRelative+j]);
            std::cout << std::dec << "\n";
        }
    }
    std::cout << "Polygon descriptors in article: " << found << "\n";
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
    if (argc != 2 && !(argc == 3 && std::string(argv[2]) == "--parts") && !(argc == 4 && (std::string(argv[2]) == "--polygons" || std::string(argv[2]) == "--dump" || std::string(argv[2]) == "--vertices" || std::string(argv[2]) == "--vertices-level0")) ) {
        std::cerr << "Usage: nfs5-inspector <path-to-crp> [--dump <new-output-file> | --vertices <new-obj-file> | --vertices-level0 <new-obj-file> | --polygons <article-index>] | --self-test\n";
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
        if (argc == 3 && std::string(argv[2]) == "--parts") inspectParts(output);
        if (argc == 4 && std::string(argv[2]) == "--polygons") {
            const std::string arg(argv[3]);
            std::size_t consumed = 0;
            const auto idx = std::stoull(arg, &consumed, 10);
            if (consumed != arg.size()) throw std::runtime_error("invalid article index");
            inspectPolygons(output, static_cast<std::size_t>(idx));
        }
        if (argc == 4 && (std::string(argv[2]) == "--vertices" || std::string(argv[2]) == "--vertices-level0"))
            exportVertices(output, std::filesystem::path(argv[3]), std::string(argv[2]) == "--vertices-level0");
        if (argc == 4 && std::string(argv[2]) == "--dump") {
            const std::filesystem::path destination(argv[3]);
            if (std::filesystem::exists(destination))
                throw std::runtime_error("output path already exists; refusing to overwrite");
            // Refuse a pre-existing file. This is a convenience guard, not an
            // atomic no-clobber guarantee; use a private local output directory.
            std::ofstream out(destination, std::ios::binary | std::ios::out);
            if (!out) throw std::runtime_error("cannot open output file");
            out.write(reinterpret_cast<const char*>(output.data()),
                      static_cast<std::streamsize>(output.size()));
            out.close();
            if (!out) {
                std::filesystem::remove(destination);
                throw std::runtime_error("failed writing decoded file");
            }
            std::cout << "Wrote decompressed data to " << destination << "\n";
        }
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "Inspector error: " << e.what() << "\n";
        return 1;
    }
}
