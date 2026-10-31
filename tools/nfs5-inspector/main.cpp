#include <algorithm>
#include <array>
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



void exportBodyMesh(const Bytes& b, const std::filesystem::path& dest) {
    if (std::filesystem::exists(dest)) throw std::runtime_error("OBJ already exists");
    const std::size_t n = read32le(b,4)>>5, dir = std::size_t(read32le(b,12))*16;
    if (dir > b.size() || n > (b.size()-dir)/16 || n <= 5)
        throw std::runtime_error("Body article missing");
    const std::size_t at=dir+5*16, rel=read32le(b,at+12), len=read32le(b,at+8);
    if(rel>(b.size()-at)/16) throw std::runtime_error("invalid Body offset");
    const std::size_t begin=at+rel*16;
    if(len>(b.size()-begin)/16) throw std::runtime_error("invalid Body size");
    const std::size_t end=begin+len*16;
    struct VBuf {std::size_t start,count,descriptor; unsigned info;};
    std::vector<VBuf> vertices;
    for(std::size_t p=begin;p<end;p+=16) {
        if(b[p+2]!='t'||b[p+3]!='v')continue;
        const std::size_t size=read32le(b,p+4)>>8, count=read32le(b,p+8), off=read32le(b,p+12);
        if(count==0||count>SIZE_MAX/16||size!=count*16||off>b.size()-p||size>b.size()-p-off)continue;
        vertices.push_back({p+off,count,p,unsigned(b[p])|(unsigned(b[p+1])<<8)});
    }
    std::cout<<"Body vertex buffers (descriptor, partInfo, count):\n";
    for(const auto& v:vertices)
        std::cout<<"  "<<v.descriptor<<" 0x"<<std::hex<<v.info<<std::dec<<" "<<v.count<<"\n";
    // The original loader selects its geometry through GetDataEntry(ID_VERTEX, lev).
    // Limit this first experiment to the unique 251-vertex buffer referenced by
    // level-1 Body polygon info rows. Prefer the explicit unflagged 0x0001\n    // descriptor over 0x8001; the high-bit variant's semantics remain unknown.\n    // Never guess if more than one unflagged candidate remains.
    std::vector<VBuf> candidates;
    for(const auto& v:vertices) if(v.count==251 && v.info==0x0001) candidates.push_back(v);
    if(candidates.size()!=1) {
        std::cout<<"251-vertex unflagged 0x0001 candidate count: "<<candidates.size()<<"\n";
        throw std::runtime_error("ambiguous vertex buffer; OBJ not written");
    }
    const auto selected=candidates.front();
    std::vector<std::uint32_t> faces;
    std::size_t used=0, skipped=0;
    for(std::size_t p=begin;p<end;p+=16) {
        if(b[p+2]!='r'||b[p+3]!='p')continue;
        const unsigned partInfo=unsigned(b[p])|(unsigned(b[p+1])<<8);
        if((partInfo>>12)!=1)continue; // first polygon LOD group only
        const std::size_t size=read32le(b,p+4)>>8, count=read32le(b,p+8), off=read32le(b,p+12);
        if(off>b.size()-p||size>b.size()-p-off||size<48||count%3) {++skipped;continue;}
        const std::size_t base=p+off, infos=read32le(b,base+40), streams=read32le(b,base+44);
        if(infos> (size-48)/16 || streams> (size-48-infos*16)/8) {++skipped;continue;}
        const std::size_t data=48+infos*16+streams*8;
        if(streams==0||count>(size-data)/streams){++skipped;continue;}
        std::size_t vertexOff=SIZE_MAX;
        for(std::size_t k=0;k<streams;++k) {
            const auto descriptor=base+48+infos*16+k*8;
            const unsigned id=unsigned(b[descriptor+2])|(unsigned(b[descriptor+3])<<8);
            if(id==0x4976)vertexOff=read32le(b,descriptor+4);
        }
        std::size_t adjust=SIZE_MAX;
        for(std::size_t k=0;k<infos;++k) {
            const auto row=base+48+k*16;
            const unsigned id=unsigned(b[row+10])|(unsigned(b[row+11])<<8);
            const unsigned level=unsigned(b[row+12])|(unsigned(b[row+13])<<8);
            if(id==0&&level==1&&read32le(b,row+4)%16==0)
                adjust=read32le(b,row+4)/16;
        }
        if(vertexOff==SIZE_MAX||adjust==SIZE_MAX||vertexOff>size-data||
           count>size-data-vertexOff){++skipped;continue;}
        bool valid=true;
        for(std::size_t k=0;k<count;++k)
            if(std::size_t(b[base+data+vertexOff+k])+adjust>=selected.count)valid=false;
        if(!valid){++skipped;continue;}
        for(std::size_t k=0;k<count;++k)
            faces.push_back(static_cast<std::uint32_t>(b[base+data+vertexOff+k]+adjust+1));
        ++used;
    }
    if(faces.empty())throw std::runtime_error("no validated triangles; OBJ not written");
    std::ofstream out(dest);
    if(!out)throw std::runtime_error("cannot open OBJ");
    out<<"# Local diagnostic: Porsche 993 Body, first polygon group only\n";
    out<<std::setprecision(9);
    for(std::size_t i=0;i<selected.count;++i) {
        const std::size_t v=selected.start+i*16;
        auto rd=[&](std::size_t off){const auto bits=read32le(b,v+off);float value;std::memcpy(&value,&bits,4);return value;};
        const float x=rd(0),y=rd(4),z=rd(8);
        if(!std::isfinite(x)||!std::isfinite(y)||!std::isfinite(z))
            throw std::runtime_error("non-finite vertex");
        out<<"v "<<x<<" "<<y<<" "<<z<<"\n";
    }
    out<<"g Porsche993_Body_level1\n";
    for(std::size_t i=0;i<faces.size();i+=3)
        out<<"f "<<faces[i]<<" "<<faces[i+1]<<" "<<faces[i+2]<<"\n";
    out.close();
    if(!out)throw std::runtime_error("failed writing OBJ");
    std::cout<<"Body mesh exported: "<<faces.size()/3<<" triangles from "
             <<used<<" polygon descriptors; skipped "<<skipped<<" -> "<<dest<<"\n";
}

void exportArticleMesh(const Bytes& b, std::size_t article, const std::filesystem::path& dest, bool uvMode=false, bool normalMode=false, bool reverseWinding=false, bool strictUv=false) {
    if(uvMode && !strictUv && article!=46 && article!=47)throw std::runtime_error("wheel UV export requires article 46 or 47");
    if(strictUv && article!=36 && article!=32 && article!=17 && article!=18)throw std::runtime_error("article UV preview supports 36, 32, 17, 18 only");
    if (std::filesystem::exists(dest)) throw std::runtime_error("OBJ already exists");
    const std::size_t n = read32le(b,4)>>5, dir = std::size_t(read32le(b,12))*16;
    if (dir > b.size() || n > (b.size()-dir)/16 || article >= n)
        throw std::runtime_error("requested article missing");
    const std::size_t at=dir+article*16, rel=read32le(b,at+12), len=read32le(b,at+8);
    if(rel>(b.size()-at)/16) throw std::runtime_error("invalid Body offset");
    const std::size_t begin=at+rel*16;
    if(len>(b.size()-begin)/16) throw std::runtime_error("invalid Body size");
    const std::size_t end=begin+len*16;
    struct VBuf {std::size_t start,count,descriptor; unsigned info;};
    std::vector<VBuf> vertices;
    for(std::size_t p=begin;p<end;p+=16) {
        if(b[p+2]!='t'||b[p+3]!='v')continue;
        const std::size_t size=read32le(b,p+4)>>8, count=read32le(b,p+8), off=read32le(b,p+12);
        if(count==0||count>SIZE_MAX/16||size!=count*16||off>b.size()-p||size>b.size()-p-off)continue;
        vertices.push_back({p+off,count,p,unsigned(b[p])|(unsigned(b[p+1])<<8)});
    }
    std::cout<<"Article "<<article<<" vertex buffers (descriptor, partInfo, count):\n";
    for(const auto& v:vertices)
        std::cout<<"  "<<v.descriptor<<" 0x"<<std::hex<<v.info<<std::dec<<" "<<v.count<<"\n";
    // tPartInfo::Length is a *referenced span*, not necessarily the size of
    // the entire vertex array. For example, TrunkOut2 references a 101-vertex
    // span within its 202-vertex level-1 buffer. Validate the actual indices
    // against the full buffer below.
    std::vector<VBuf> candidates;
    for(const auto& v:vertices)
        if(v.info==0x0001) candidates.push_back(v);
    if(candidates.size()!=1) {
        std::cout<<"Unflagged level-1 candidate count: "<<candidates.size()<<"\n";
        throw std::runtime_error("no unique matching vertex buffer; OBJ not written");
    }
    const auto selected=candidates.front();
    std::size_t uvStart=SIZE_MAX,uvCount=0,normStart=SIZE_MAX,normCount=0;
    if(uvMode || normalMode){
        for(std::size_t q=begin;q<end;q+=16){
            const std::string tag{char(b[q+2]),char(b[q+3])};
            const unsigned level=unsigned(b[q])|(unsigned(b[q+1])<<8);
            if(level!=1||(tag!="vu"&&tag!="mn"))continue;
            const auto bytes=std::size_t(read32le(b,q+4)>>8),count=std::size_t(read32le(b,q+8)),off=std::size_t(read32le(b,q+12));
            const auto stride=(tag=="vu"?8u:16u);
            if(!count||count>SIZE_MAX/stride||bytes!=count*stride||off>b.size()-q||bytes>b.size()-q-off)continue;
            if(tag=="vu"){uvStart=q+off;uvCount=count;}
            if(tag=="mn"){normStart=q+off;normCount=count;}
        }
        if((uvMode&&uvStart==SIZE_MAX)||normStart==SIZE_MAX||normCount!=selected.count)
            throw std::runtime_error("level-1 UV/normal streams absent or inconsistent");
    }
    std::vector<std::uint32_t> textureFaces;
    std::vector<std::uint32_t> faces;
    std::size_t used=0, skipped=0, expected=0;
    for(std::size_t p=begin;p<end;p+=16) {
        if(b[p+2]!='r'||b[p+3]!='p')continue;
        const unsigned partInfo=unsigned(b[p])|(unsigned(b[p+1])<<8);
        if((partInfo>>12)!=1)continue; // first polygon LOD group only
        ++expected;
        const std::size_t size=read32le(b,p+4)>>8, count=read32le(b,p+8), off=read32le(b,p+12);
        if(off>b.size()-p||size>b.size()-p-off||size<48||count%3) {++skipped;continue;}
        const std::size_t base=p+off, infos=read32le(b,base+40), streams=read32le(b,base+44);
        if(infos> (size-48)/16 || streams> (size-48-infos*16)/8) {++skipped;continue;}
        const std::size_t data=48+infos*16+streams*8;
        if(streams==0||count>(size-data)/streams){++skipped;continue;}
        std::size_t vertexOff=SIZE_MAX,textureOff=SIZE_MAX;
        for(std::size_t k=0;k<streams;++k) {
            const auto descriptor=base+48+infos*16+k*8;
            const unsigned id=unsigned(b[descriptor+2])|(unsigned(b[descriptor+3])<<8);
            if(id==0x4976)vertexOff=read32le(b,descriptor+4);
            if(id==0x4975)textureOff=read32le(b,descriptor+4);
        }
        std::size_t adjust=SIZE_MAX;
        for(std::size_t k=0;k<infos;++k) {
            const auto row=base+48+k*16;
            const unsigned id=unsigned(b[row+10])|(unsigned(b[row+11])<<8);
            const unsigned level=unsigned(b[row+12])|(unsigned(b[row+13])<<8);
            if(id==0&&level==1&&read32le(b,row+4)%16==0)
                adjust=read32le(b,row+4)/16;
        }
        if(vertexOff==SIZE_MAX||adjust==SIZE_MAX||vertexOff>size-data||
           count>size-data-vertexOff){++skipped;continue;}
        std::size_t uvAdjust=0;
        if(uvMode){
            bool found=false;
            for(std::size_t k=0;k<infos;++k){
                const auto row=base+48+k*16;
                const unsigned id=unsigned(b[row+10])|(unsigned(b[row+11])<<8);
                const unsigned level=unsigned(b[row+12])|(unsigned(b[row+13])<<8);
                const auto byteOffset=read32le(b,row+4);
                if(id==2&&level==1&&byteOffset%8==0){uvAdjust=byteOffset/8;found=true;break;}
            }
            if(!found||textureOff==SIZE_MAX||textureOff>size-data||count>size-data-textureOff){++skipped;continue;}
        }
        bool valid=true;
        for(std::size_t k=0;k<count;++k){
            if(std::size_t(b[base+data+vertexOff+k])+adjust>=selected.count)valid=false;
            if(uvMode&&std::size_t(b[base+data+textureOff+k])+uvAdjust>=uvCount)valid=false;
        }
        if(!valid){++skipped;continue;}
        for(std::size_t k=0;k<count;++k){
            faces.push_back(static_cast<std::uint32_t>(b[base+data+vertexOff+k]+adjust+1));
            if(uvMode)textureFaces.push_back(static_cast<std::uint32_t>(b[base+data+textureOff+k]+uvAdjust+1));
        }
        ++used;
    }
    if(strictUv && skipped)throw std::runtime_error("UV preview rejected one or more polygon groups; OBJ not written");
    if(strictUv && used!=expected)throw std::runtime_error("UV preview polygon-group mismatch; OBJ not written");
    if(faces.empty())throw std::runtime_error("no validated triangles; OBJ not written");
    std::ofstream out(dest);
    if(!out)throw std::runtime_error("cannot open OBJ");
    out<<"# Local diagnostic: Porsche 993 article mesh, first polygon group only\n";
    out<<std::setprecision(9);
    for(std::size_t i=0;i<selected.count;++i) {
        const std::size_t v=selected.start+i*16;
        auto rd=[&](std::size_t off){const auto bits=read32le(b,v+off);float value;std::memcpy(&value,&bits,4);return value;};
        const float x=rd(0),y=rd(4),z=rd(8);
        if(!std::isfinite(x)||!std::isfinite(y)||!std::isfinite(z))
            throw std::runtime_error("non-finite vertex");
        out<<"v "<<x<<" "<<y<<" "<<z<<"\n";
    }
    if(uvMode || normalMode){
        if(uvMode)for(std::size_t i=0;i<uvCount;++i){
            const auto at=uvStart+i*8;
            const auto ub=read32le(b,at),vb=read32le(b,at+4);
            float u,v;std::memcpy(&u,&ub,4);std::memcpy(&v,&vb,4);
            if(!std::isfinite(u)||!std::isfinite(v))throw std::runtime_error("invalid UV float");
            out<<"vt "<<u<<" "<<v<<"\n";
        }
        for(std::size_t i=0;i<normCount;++i){
            const auto at=normStart+i*16;
            float value[3];
            for(int k=0;k<3;++k){
                const auto bits=read32le(b,at+k*4);
                std::memcpy(&value[k],&bits,4);
                if(!std::isfinite(value[k]))throw std::runtime_error("invalid normal float");
            }
            out<<"vn "<<value[0]<<" "<<value[1]<<" "<<value[2]<<"\n";
        }
    }
    out<<"g Porsche993_article_"<<article<<"_level1\n";
    for(std::size_t i=0;i<faces.size();i+=3){
        if(uvMode){
            out<<"f";
            for(std::size_t k=0;k<3;++k)out<<" "<<faces[i+k]<<"/"<<textureFaces[i+k]<<"/"<<faces[i+k];
            out<<"\n";
        }else if(normalMode){
            const std::size_t first=i, second=reverseWinding?i+2:i+1, third=reverseWinding?i+1:i+2;
            out<<"f "<<faces[first]<<"//"<<faces[first]<<" "<<faces[second]<<"//"<<faces[second]<<" "<<faces[third]<<"//"<<faces[third]<<"\n";
        }
        else out<<"f "<<faces[i]<<" "<<faces[i+1]<<" "<<faces[i+2]<<"\n";
    }
    out.close();
    if(!out)throw std::runtime_error("failed writing OBJ");
    std::cout<<"Article "<<article<<" mesh exported: "<<faces.size()/3<<" triangles from "
             <<used<<" polygon descriptors; skipped "<<skipped<<" -> "<<dest<<"\n";
}


std::string articleName(const Bytes& b, std::size_t article) {
    const std::size_t dir=std::size_t(read32le(b,12))*16, n=read32le(b,4)>>5;
    if(dir>b.size()||n>(b.size()-dir)/16||article>=n) throw std::runtime_error("bad article");
    const std::size_t at=dir+article*16,off=read32le(b,at+12),len=read32le(b,at+8);
    if(off>(b.size()-at)/16)throw std::runtime_error("bad article offset");
    const std::size_t start=at+off*16;
    if(len>(b.size()-start)/16)throw std::runtime_error("bad article length");
    for(std::size_t p=start;p<start+len*16;p+=16) {
        if(!((b[p]=='e'&&b[p+1]=='m'&&b[p+2]=='a'&&b[p+3]=='N')||
             (b[p]=='N'&&b[p+1]=='a'&&b[p+2]=='m'&&b[p+3]=='e')))continue;
        const std::size_t rel=read32le(b,p+12),bytes=read32le(b,p+4)>>8;
        if(rel>b.size()-p||bytes>b.size()-p-rel||bytes>4096)break;
        std::string name;
        for(std::size_t k=0;k<bytes&&b[p+rel+k];++k) {
            const unsigned char c=b[p+rel+k];
            name+=((c>='A'&&c<='Z')||(c>='a'&&c<='z')||
                   (c>='0'&&c<='9')||c=='_'||c=='-')?char(c):'_';
        }
        return name.empty()?"unnamed":name;
    }
    return "unnamed";
}

void inspectTransforms(const Bytes& b, std::size_t article) {
    const std::size_t dir=std::size_t(read32le(b,12))*16,n=read32le(b,4)>>5;
    if(dir>b.size()||n>(b.size()-dir)/16||article>=n)throw std::runtime_error("invalid article");
    const std::size_t at=dir+article*16,off=read32le(b,at+12),len=read32le(b,at+8);
    if(off>(b.size()-at)/16)throw std::runtime_error("invalid article offset");
    const std::size_t start=at+off*16;
    if(len>(b.size()-start)/16)throw std::runtime_error("invalid article length");
    std::cout<<"Transform diagnostics article "<<article<<" "<<articleName(b,article)<<"\n";
    std::size_t found=0;
    for(std::size_t p=start;p<start+len*16;p+=16) {
        if(b[p+2]!='r'||b[p+3]!='t')continue;
        ++found;
        const std::size_t rel=read32le(b,p+12),bytes=read32le(b,p+4)>>8;
        const unsigned info=unsigned(b[p])|(unsigned(b[p+1])<<8);
        if(rel>b.size()-p||bytes>b.size()-p-rel||bytes<64) {
            std::cout<<"  descriptor="<<p<<" partInfo=0x"<<std::hex<<info<<std::dec<<" invalid matrix payload\n";
            continue;
        }
        const std::size_t pos=p+rel;
        float m[16];
        for(std::size_t k=0;k<16;++k) {
            const auto bits=read32le(b,pos+k*4);
            std::memcpy(&m[k],&bits,4);
        }
        std::cout<<"  descriptor="<<p<<" partInfo=0x"<<std::hex<<info<<std::dec
                 <<" matrixBytes="<<bytes<<" translation=("
                 <<m[12]<<","<<m[13]<<","<<m[14]<<")"
                 <<" finite="<<(std::all_of(m,m+16,[](float x){return std::isfinite(x);})?"yes":"no")<<"\n";
    }
    std::cout<<"  transform descriptors: "<<found<<" (not yet applied to OBJ)\n";
}


void inspectWheelPlacement(const Bytes& b) {
    const std::size_t dir=std::size_t(read32le(b,12))*16,n=read32le(b,4)>>5;
    if(dir>b.size()||n>(b.size()-dir)/16||n<=49)
        throw std::runtime_error("missing wheel articles");
    auto asFloat=[&](std::size_t p) {
        const auto bits=read32le(b,p);
        float x; std::memcpy(&x,&bits,sizeof(x)); return x;
    };
    for(std::size_t article=46;article<=49;++article) {
        const std::size_t at=dir+article*16,rel=read32le(b,at+12),len=read32le(b,at+8);
        if(rel>(b.size()-at)/16)throw std::runtime_error("bad article offset");
        const std::size_t begin=at+rel*16;
        if(len>(b.size()-begin)/16)throw std::runtime_error("bad article length");
        const std::size_t end=begin+len*16;
        std::cout<<"Wheel "<<article<<" "<<articleName(b,article)<<"\n";
        bool haveVertex=false,haveMatrix=false;
        float lo[3]{},hi[3]{},translation[3]{};
        for(std::size_t p=begin;p<end;p+=16) {
            const unsigned info=unsigned(b[p])|(unsigned(b[p+1])<<8);
            const std::size_t off=read32le(b,p+12),bytes=read32le(b,p+4)>>8;
            if(off>b.size()-p||bytes>b.size()-p-off)continue;
            const std::size_t start=p+off;
            if(b[p+2]=='t'&&b[p+3]=='v'&&info==1) {
                const std::size_t count=read32le(b,p+8);
                if(count==0||count>SIZE_MAX/16||count*16!=bytes)continue;
                for(std::size_t j=0;j<count;++j) {
                    const std::size_t v=start+j*16;
                    float xyz[]{asFloat(v),asFloat(v+4),asFloat(v+8)};
                    if(!std::all_of(xyz,xyz+3,[](float x){return std::isfinite(x);}))
                        throw std::runtime_error("nonfinite wheel vertex");
                    for(int k=0;k<3;++k) {
                        if(!haveVertex)lo[k]=hi[k]=xyz[k];
                        else {lo[k]=std::min(lo[k],xyz[k]);hi[k]=std::max(hi[k],xyz[k]);}
                    }
                    haveVertex=true;
                }
                std::cout<<"  vertexCount="<<count<<" raw bounds ["
                    <<lo[0]<<","<<lo[1]<<","<<lo[2]<<"] to ["
                    <<hi[0]<<","<<hi[1]<<","<<hi[2]<<"]\n";
            }
            if(b[p+2]=='r'&&b[p+3]=='t'&&info==1&&bytes>=64) {
                for(int k=0;k<3;++k)translation[k]=asFloat(start+48+k*4);
                haveMatrix=true;
                std::cout<<"  transform translation ["
                    <<translation[0]<<","<<translation[1]<<","<<translation[2]<<"]\n";
            }
        }
        if(haveVertex&&haveMatrix) {
            std::cout<<"  raw centre=(";
            for(int k=0;k<3;++k)std::cout<<(k?",":"")<<(lo[k]+hi[k])/2;
            std::cout<<") translated centre=(";
            for(int k=0;k<3;++k)std::cout<<(k?",":"")<<((lo[k]+hi[k])/2+translation[k]);
            std::cout<<")\n";
        } else std::cout<<"  missing level-1 raw vertex or transform data\n";
    }
}



void inspectSurfaceDescriptors(const Bytes& b) {
    const std::size_t dir=std::size_t(read32le(b,12))*16,n=read32le(b,4)>>5;
    if(dir>b.size()||n>(b.size()-dir)/16)throw std::runtime_error("bad article directory");
    for(const std::size_t article: {std::size_t(5),std::size_t(20),std::size_t(13),
                                    std::size_t(28),std::size_t(46),std::size_t(47),
                                    std::size_t(52),std::size_t(53)}) {
        if(article>=n)continue;
        const auto at=dir+article*16;
        const std::size_t rel=read32le(b,at+12),len=read32le(b,at+8);
        if(rel>(b.size()-at)/16)throw std::runtime_error("bad article offset");
        const auto begin=at+rel*16;
        if(len>(b.size()-begin)/16)throw std::runtime_error("bad article length");
        const auto end=begin+len*16;
        std::map<unsigned,std::size_t> attributes,streams,groups;
        std::size_t invalid=0, polygons=0;
        int textureType=-1,geomIndex=-1;
        for(std::size_t p=begin;p<end;p+=16) {
            const auto tag0=b[p+2],tag1=b[p+3];
            const auto size=std::size_t(read32le(b,p+4)>>8),off=std::size_t(read32le(b,p+12));
            if(off>b.size()-p||size>b.size()-p-off){++invalid;continue;}
            if(tag0=='a'&&tag1=='B'&&size>=100) {
                const auto base=p+off+68;
                geomIndex=b[base];textureType=b[base+6];
            }
            if(tag0!='r'||tag1!='p')continue;
            const unsigned descriptor=unsigned(b[p])|(unsigned(b[p+1])<<8);
            if((descriptor>>12)!=1)continue;
            ++polygons;
            ++groups[descriptor];
            if(size<48){++invalid;continue;}
            const auto base=p+off;
            const auto info=std::size_t(read32le(b,base+40));
            const auto stream=std::size_t(read32le(b,base+44));
            if(info>(size-48)/16||stream>(size-48-info*16)/8){++invalid;continue;}
            for(std::size_t i=0;i<info;++i) {
                const auto q=base+48+i*16;
                const unsigned id=unsigned(b[q+10])|(unsigned(b[q+11])<<8);
                ++attributes[id];
            }
            for(std::size_t i=0;i<stream;++i) {
                const auto q=base+48+info*16+i*8;
                const unsigned id=unsigned(b[q+2])|(unsigned(b[q+3])<<8);
                ++streams[id];
            }
        }
        std::cout<<"Article "<<article<<" "<<articleName(b,article)
                 <<" geomIndex="<<geomIndex<<" textureType="<<textureType
                 <<" level1PolygonGroups="<<polygons<<" invalid="<<invalid<<"\n";
        auto report=[](const char* label,const std::map<unsigned,std::size_t>& vals) {
            std::cout<<"  "<<label<<":";
            for(const auto& entry:vals)
                std::cout<<" 0x"<<std::hex<<entry.first<<std::dec<<"("<<entry.second<<")";
            std::cout<<"\n";
        };
        report("group descriptors",groups);
        report("attribute IDs [raw, unclassified]",attributes);
        report("index stream IDs [raw, unclassified]",streams);
    }
    std::cout<<"NOTE: IDs and textureType are raw CRP fields; UV or material semantics are unverified.\\n";
}


void inspectTriangleAttributeSamples(const Bytes& b) {
    const std::size_t dir=std::size_t(read32le(b,12))*16,n=read32le(b,4)>>5;
    if(dir>b.size()||n>(b.size()-dir)/16)throw std::runtime_error("invalid article directory");
    for(const std::size_t article: {std::size_t(5),std::size_t(46),std::size_t(47)}) {
        if(article>=n)continue;
        const auto at=dir+article*16;
        const std::size_t rel=read32le(b,at+12),len=read32le(b,at+8);
        if(rel>(b.size()-at)/16)throw std::runtime_error("article offset invalid");
        const auto begin=at+rel*16;
        if(len>(b.size()-begin)/16)throw std::runtime_error("article length invalid");
        std::cout<<"Article "<<article<<" "<<articleName(b,article)<<"\n";
        // Select level-1 positions for an independent triangle-normal test.
        std::size_t vertexStart=SIZE_MAX,vertexCount=0;
        for(std::size_t p=begin;p<begin+len*16;p+=16) {
            if(b[p+2]!='t'||b[p+3]!='v')continue;
            const unsigned info=unsigned(b[p])|(unsigned(b[p+1])<<8);
            const auto bytes=std::size_t(read32le(b,p+4)>>8);
            const auto count=std::size_t(read32le(b,p+8));
            const auto relv=std::size_t(read32le(b,p+12));
            if(info==1&&count&&count<=100000&&bytes==count*16&&
               relv<=b.size()-p&&bytes<=b.size()-p-relv) {
                vertexStart=p+relv;vertexCount=count;break;
            }
        }
        auto pos=[&](std::size_t index) {
            std::array<double,3> v{};
            if(index>=vertexCount)throw std::runtime_error("bad vertex index");
            for(int k=0;k<3;++k) {
                const auto bits=read32le(b,vertexStart+index*16+4*k);
                float x;std::memcpy(&x,&bits,4);v[k]=x;
            }
            return v;
        };

        std::size_t sampledGroups=0;
        for(std::size_t p=begin;p<begin+len*16&&sampledGroups<3;p+=16) {
            if(b[p+2]!='r'||b[p+3]!='p')continue;
            const unsigned descriptor=unsigned(b[p])|(unsigned(b[p+1])<<8);
            if((descriptor>>12)!=1)continue;
            const auto bytes=std::size_t(read32le(b,p+4)>>8),off=std::size_t(read32le(b,p+12));
            if(off>b.size()-p||bytes>b.size()-p-off||bytes<48)continue;
            const auto base=p+off, info=std::size_t(read32le(b,base+40));
            if(info>(bytes-48)/16)continue;
            for(std::size_t k=0;k<info;++k) {
                const auto q=base+48+k*16;
                const unsigned id=unsigned(b[q+10])|(unsigned(b[q+11])<<8);
                if(id!=0x246e)continue;
                const auto rm=std::size_t(read32le(b,q));
                const auto offset=std::size_t(read32le(b,q+4));
                const auto length=std::size_t(unsigned(b[q+8])|(unsigned(b[q+9])<<8));
                // rmOffset locates the first n$ part. CRP can split the
                // logical per-triangle stream across successive n$ payloads.
                // Resolve a logical byte offset by walking compatible parts.
                if(rm>=len){std::cout<<"  invalid part reference\\n";break;}
                const auto rp=begin+rm*16;
                const char tag0=char(b[rp+2]),tag1=char(b[rp+3]);
                std::vector<std::uint8_t> logical;
                for(std::size_t part=rm;part<len;++part) {
                    const auto desc=begin+part*16;
                    if(char(b[desc+2])!=tag0||char(b[desc+3])!=tag1) {
                        if(!logical.empty())break;
                        continue;
                    }
                    const auto pb=std::size_t(read32le(b,desc+4)>>8);
                    const auto po=std::size_t(read32le(b,desc+12));
                    if(po>b.size()-desc||pb>b.size()-desc-po)break;
                    const auto start=desc+po;
                    logical.insert(logical.end(),b.begin()+start,b.begin()+start+pb);
                    if(logical.size()>=offset&&length<=logical.size()-offset)break;
                }
                if(offset>logical.size()||length>logical.size()-offset) {
                    std::cout<<"  group 0x"<<std::hex<<descriptor<<std::dec
                             <<" unresolved source range; logicalBytes="<<logical.size()
                             <<" offset="<<offset<<" bytes="<<length<<"\n";
                    break;
                }
                const auto data=logical.data()+offset;
                std::cout<<"  group 0x"<<std::hex<<descriptor<<std::dec
                         <<" sourceTag="<<char(b[rp+2])<<char(b[rp+3])
                         <<" rmOffset="<<rm<<" bytes="<<length
                         <<" records16="<<length/16<<"\n";
                for(std::size_t rec=0;rec<std::min<std::size_t>(4,length/16);++rec) {
                    const auto atData=data+rec*16;
                    std::cout<<"    record "<<rec<<" hex=";
                    for(std::size_t j=0;j<16;++j)
                        std::cout<<std::hex<<std::setfill('0')<<std::setw(2)<<unsigned(atData[j]);
                    std::cout<<std::dec<<std::setfill(' ')<<" uint32=";
                    for(int j=0;j<4;++j)std::cout<<(j?",":"")<<(std::uint32_t(atData[j*4]) | (std::uint32_t(atData[j*4+1])<<8) | (std::uint32_t(atData[j*4+2])<<16) | (std::uint32_t(atData[j*4+3])<<24));
                    std::cout<<" float32=";
                    for(int j=0;j<4;++j){
                        const auto bits=std::uint32_t(atData[j*4]) | (std::uint32_t(atData[j*4+1])<<8) | (std::uint32_t(atData[j*4+2])<<16) | (std::uint32_t(atData[j*4+3])<<24);
                        float v;std::memcpy(&v,&bits,4);
                        if(std::isfinite(v))std::cout<<(j?",":"")<<v;
                        else std::cout<<(j?",":"")<<"nonfinite";
                    }
                    std::cout<<"\n";
                }
                // Index stream 0x4976 identifies triangles. Calculate a
                // geometric normal and compare its signed dot with 0x246e.
                const auto streams=std::size_t(read32le(b,base+44));
                if(vertexStart!=SIZE_MAX && info<=(bytes-48)/16 &&
                   streams<=(bytes-48-info*16)/8 && streams) {
                    const auto streamBase=48+info*16+streams*8;
                    const auto count=std::size_t(read32le(b,p+8));
                    std::size_t indexOffset=SIZE_MAX,adjust=SIZE_MAX;
                    for(std::size_t i=0;i<streams;++i) {
                        const auto d=base+48+info*16+i*8;
                        const unsigned sid=unsigned(b[d+2])|(unsigned(b[d+3])<<8);
                        if(sid==0x4976)indexOffset=read32le(b,d+4);
                    }
                    for(std::size_t i=0;i<info;++i) {
                        const auto d=base+48+i*16;
                        const unsigned aid=unsigned(b[d+10])|(unsigned(b[d+11])<<8);
                        const unsigned level=unsigned(b[d+12])|(unsigned(b[d+13])<<8);
                        const auto byteOffset=read32le(b,d+4);
                        if(aid==0&&level==1&&byteOffset%16==0)
                            adjust=byteOffset/16;
                    }
                    if(indexOffset!=SIZE_MAX&&adjust!=SIZE_MAX&&
                       streamBase<=bytes&&indexOffset<=bytes-streamBase&&
                       count<=bytes-streamBase-indexOffset) {
                        const auto indexData=base+streamBase+indexOffset;
                        for(std::size_t j=0;j<std::min<std::size_t>(4,std::min(count/3,length/16));++j) {
                            const std::size_t i0=adjust+b[indexData+j*3],
                                              i1=adjust+b[indexData+j*3+1],
                                              i2=adjust+b[indexData+j*3+2];
                            if(i0>=vertexCount||i1>=vertexCount||i2>=vertexCount)continue;
                            const auto a=pos(i0),c=pos(i1),d=pos(i2);
                            std::array<double,3> u{},v{},cross{};
                            for(int k=0;k<3;++k){u[k]=c[k]-a[k];v[k]=d[k]-a[k];}
                            cross={u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]};
                            const double mag=std::sqrt(cross[0]*cross[0]+cross[1]*cross[1]+cross[2]*cross[2]);
                            if(mag<1e-12)continue;
                            std::array<float,4> stored{};
                            for(int k=0;k<4;++k) {
                                const auto ptr=data+j*16+4*k;
                                const auto bits=std::uint32_t(ptr[0])|(std::uint32_t(ptr[1])<<8)|
                                                (std::uint32_t(ptr[2])<<16)|(std::uint32_t(ptr[3])<<24);
                                std::memcpy(&stored[k],&bits,4);
                            }
                            const double dot=(cross[0]*stored[0]+cross[1]*stored[1]+cross[2]*stored[2])/mag;
                            const double planePlus=stored[0]*a[0]+stored[1]*a[1]+stored[2]*a[2]+stored[3];
                            const double planeMinus=stored[0]*a[0]+stored[1]*a[1]+stored[2]*a[2]-stored[3];
                            std::cout<<"    triangle "<<j<<" storedNormalLength="
                                     <<std::sqrt(double(stored[0])*stored[0]+double(stored[1])*stored[1]+double(stored[2])*stored[2])
                                     <<" normalDot="<<dot
                                     <<" planeResidual(+w)="<<planePlus
                                     <<" planeResidual(-w)="<<planeMinus<<"\n";
                        }
                    }
                }
                ++sampledGroups;
                break;
            }
        }
    }
    std::cout<<"NOTE: raw 16-byte attributes; float32/uint32 interpretations are hypotheses.\\n";
}


void inspectAttributeLayout(const Bytes& b) {
    const std::size_t dir=std::size_t(read32le(b,12))*16,n=read32le(b,4)>>5;
    if(dir>b.size()||n>(b.size()-dir)/16)throw std::runtime_error("invalid article table");
    for(const std::size_t article: {std::size_t(5),std::size_t(46),std::size_t(47)}) {
        if(article>=n)continue;
        const auto at=dir+article*16;
        const auto rel=std::size_t(read32le(b,at+12)),len=std::size_t(read32le(b,at+8));
        if(rel>(b.size()-at)/16)throw std::runtime_error("invalid article offset");
        const auto begin=at+rel*16;
        if(len>(b.size()-begin)/16)throw std::runtime_error("invalid article length");
        std::cout<<"Article "<<article<<" "<<articleName(b,article)<<"\n";
        std::size_t groups=0;
        for(std::size_t p=begin;p<begin+len*16 && groups<2;p+=16) {
            if(b[p+2]!='r'||b[p+3]!='p')continue;
            const unsigned descriptor=unsigned(b[p])|(unsigned(b[p+1])<<8);
            if((descriptor>>12)!=1)continue;
            const auto bytes=std::size_t(read32le(b,p+4)>>8),off=std::size_t(read32le(b,p+12));
            if(off>b.size()-p||bytes>b.size()-p-off||bytes<48)continue;
            const auto base=p+off,info=std::size_t(read32le(b,base+40));
            if(info>(bytes-48)/16)continue;
            std::cout<<"  polygon 0x"<<std::hex<<descriptor<<std::dec
                     <<" indexEntries="<<read32le(b,p+8)<<"\n";
            for(std::size_t k=0;k<info;++k) {
                const auto q=base+48+k*16;
                const unsigned id=unsigned(b[q+10])|(unsigned(b[q+11])<<8);
                if(id!=1&&id!=2)continue;
                const auto rm=std::size_t(read32le(b,q));
                const auto offset=std::size_t(read32le(b,q+4));
                const auto length=std::size_t(unsigned(b[q+8])|(unsigned(b[q+9])<<8));
                std::cout<<"    attribute "<<id<<" rmOffset="<<rm
                         <<" offset="<<offset<<" length="<<length;
                if(rm>=len){std::cout<<" INVALID reference\\n";continue;}
                const auto part=begin+rm*16;
                const auto pb=std::size_t(read32le(b,part+4)>>8);
                const auto po=std::size_t(read32le(b,part+12));
                std::cout<<" sourceTag="<<char(b[part+2])<<char(b[part+3])
                         <<" payloadBytes="<<pb;
                if(po>b.size()-part||pb>b.size()-part-po||offset>pb||length>pb-offset) {
                    std::cout<<" [indirect/segmented; no sample]\\n";continue;
                }
                const auto data=part+po+offset;
                std::cout<<" sample16=";
                for(std::size_t j=0;j<std::min<std::size_t>(16,length);++j)
                    std::cout<<std::hex<<std::setfill('0')<<std::setw(2)<<unsigned(b[data+j]);
                std::cout<<std::dec<<std::setfill(' ')<<" sampleFloat32=";
                for(std::size_t j=0;j<std::min<std::size_t>(4,length/4);++j) {
                    const auto bits=read32le(b,data+j*4);
                    float value;std::memcpy(&value,&bits,4);
                    if(j)std::cout<<",";
                    if(std::isfinite(value))std::cout<<value;
                    else std::cout<<"nonfinite";
                }
                std::cout<<"\n";
            }
            ++groups;
        }
        std::map<std::string,std::size_t> tags;
        for(std::size_t p=begin;p<begin+len*16;p+=16) {
            const std::string tag{char(b[p+2]),char(b[p+3])};
            if(tag=="vu"||tag=="tv"||tag=="n$")++tags[tag];
        }
        std::cout<<"  buffer descriptors: vu="<<tags["vu"]
                 <<" tv="<<tags["tv"]<<" n$="<<tags["n$"]<<"\n";
    }
    std::cout<<"NOTE: raw attribute samples are not proven UV or material data.\\n";
}


void inspectWheelReferences(const Bytes& b) {
    const std::size_t dir=std::size_t(read32le(b,12))*16,n=read32le(b,4)>>5;
    if(dir>b.size()||n>(b.size()-dir)/16)throw std::runtime_error("invalid directory");
    for(const std::size_t article: {std::size_t(46),std::size_t(47)}) {
        if(article>=n)continue;
        const auto at=dir+article*16;
        const auto rel=std::size_t(read32le(b,at+12)),len=std::size_t(read32le(b,at+8));
        if(rel>(b.size()-at)/16)throw std::runtime_error("invalid article offset");
        const auto begin=at+rel*16;
        if(len>(b.size()-begin)/16)throw std::runtime_error("invalid article length");
        std::cout<<"Article "<<article<<" "<<articleName(b,article)
                 <<" descriptors="<<len<<"\n";
        for(std::size_t i=0;i<len;++i) {
            const auto p=begin+i*16;
            const auto bytes=std::size_t(read32le(b,p+4)>>8),offset=std::size_t(read32le(b,p+12));
            const bool valid=offset<=b.size()-p&&bytes<=b.size()-p-offset;
            std::cout<<"  part["<<i<<"] tag="<<char(b[p+2])<<char(b[p+3])
                     <<" info=0x"<<std::hex<<(unsigned(b[p])|(unsigned(b[p+1])<<8))<<std::dec
                     <<" payload="<<bytes<<" count="<<read32le(b,p+8)
                     <<" valid="<<(valid?"yes":"NO")<<"\n";
        }
        for(std::size_t i=0;i<len;++i) {
            const auto p=begin+i*16;
            if(b[p+2]!='r'||b[p+3]!='p')continue;
            const unsigned descriptor=unsigned(b[p])|(unsigned(b[p+1])<<8);
            if((descriptor>>12)!=1)continue;
            const auto size=std::size_t(read32le(b,p+4)>>8),offset=std::size_t(read32le(b,p+12));
            if(offset>b.size()-p||size>b.size()-p-offset||size<48)continue;
            const auto base=p+offset,info=std::size_t(read32le(b,base+40));
            if(info>(size-48)/16)continue;
            std::cout<<"  polygon 0x"<<std::hex<<descriptor<<std::dec<<" at part["<<i<<"]\\n";
            for(std::size_t k=0;k<info;++k) {
                const auto q=base+48+k*16;
                const unsigned id=unsigned(b[q+10])|(unsigned(b[q+11])<<8);
                if(id!=0&&id!=1&&id!=2&&id!=0x246e)continue;
                const auto rm=std::size_t(read32le(b,q));
                const auto length=std::size_t(unsigned(b[q+8])|(unsigned(b[q+9])<<8));
                std::cout<<"    attr=0x"<<std::hex<<id<<std::dec
                         <<" rm="<<rm<<" length="<<length;
                for(const auto candidate: {rm,i+rm}) {
                    std::cout<<" candidate["<<candidate<<"]=";
                    if(candidate>=len){std::cout<<"outside";continue;}
                    const auto cp=begin+candidate*16;
                    std::cout<<char(b[cp+2])<<char(b[cp+3])
                             <<"/"<<(read32le(b,cp+4)>>8)<<"B";
                }
                std::cout<<"\n";
            }
        }
    }
    std::cout<<"NOTE: candidate indices are hypotheses; no texture assignments inferred.\\n";
}


void inspectWheelStreamSamples(const Bytes& b) {
    const std::size_t dir=std::size_t(read32le(b,12))*16,n=read32le(b,4)>>5;
    if(dir>b.size()||n>(b.size()-dir)/16)throw std::runtime_error("invalid directory");
    for(const std::size_t article: {std::size_t(46),std::size_t(47)}) {
        if(article>=n)continue;
        const auto at=dir+article*16;
        const auto rel=std::size_t(read32le(b,at+12)),len=std::size_t(read32le(b,at+8));
        if(rel>(b.size()-at)/16)throw std::runtime_error("invalid article offset");
        const auto begin=at+rel*16;
        if(len>(b.size()-begin)/16)throw std::runtime_error("invalid article length");
        std::cout<<"Article "<<article<<" "<<articleName(b,article)<<"\n";
        for(const std::string tag: {"vu","tv","mn"}) {
            bool found=false;
            for(std::size_t i=0;i<len;++i) {
                const auto p=begin+i*16;
                if(b[p+2]!=tag[0]||b[p+3]!=tag[1])continue;
                const unsigned level=unsigned(b[p])|(unsigned(b[p+1])<<8);
                if(level!=1)continue;
                const auto bytes=std::size_t(read32le(b,p+4)>>8);
                const auto count=std::size_t(read32le(b,p+8));
                const auto off=std::size_t(read32le(b,p+12));
                if(off>b.size()-p||bytes>b.size()-p-off||!count||bytes%count) {
                    std::cout<<"  "<<tag<<" invalid level1 buffer\\n";break;
                }
                const auto stride=bytes/count,base=p+off;
                std::cout<<"  "<<tag<<" part["<<i<<"] count="<<count
                         <<" stride="<<stride<<" bytes="<<bytes<<"\n";
                const auto limit=std::min<std::size_t>(count,8);
                for(std::size_t j=0;j<limit;++j) {
                    const auto addr=base+j*stride;
                    std::cout<<"    ["<<j<<"] hex=";
                    for(std::size_t k=0;k<stride;++k)
                        std::cout<<std::hex<<std::setfill('0')<<std::setw(2)<<unsigned(b[addr+k]);
                    std::cout<<std::dec<<std::setfill(' ')<<" floats=";
                    for(std::size_t k=0;k<stride/4;++k) {
                        const auto bits=read32le(b,addr+4*k);
                        float value;std::memcpy(&value,&bits,4);
                        if(k)std::cout<<",";
                        if(std::isfinite(value))std::cout<<value;
                        else std::cout<<"nonfinite";
                    }
                    std::cout<<"\n";
                }
                if(tag=="vu"&&stride==8) {
                    std::size_t finite=0,range=0;
                    float low[2]={INFINITY,INFINITY},high[2]={-INFINITY,-INFINITY};
                    for(std::size_t j=0;j<count;++j) {
                        float v[2]{};
                        for(int k=0;k<2;++k) {
                            const auto bits=read32le(b,base+j*8+k*4);
                            std::memcpy(&v[k],&bits,4);
                        }
                        if(!std::isfinite(v[0])||!std::isfinite(v[1]))continue;
                        ++finite;
                        if(v[0]>=0&&v[0]<=1&&v[1]>=0&&v[1]<=1)++range;
                        for(int k=0;k<2;++k) {
                            low[k]=std::min(low[k],v[k]);high[k]=std::max(high[k],v[k]);
                        }
                    }
                    std::cout<<"    vu float2 finite="<<finite<<"/"<<count
                             <<" both_in_0..1="<<range<<"/"<<count
                             <<" min=("<<low[0]<<","<<low[1]<<")"
                             <<" max=("<<high[0]<<","<<high[1]<<")\\n";
                }
                found=true;break;
            }
            if(!found)std::cout<<"  "<<tag<<" level1 not found\\n";
        }
    }
    std::cout<<"NOTE: float2 ranges alone do not establish UV semantics or indexing.\\n";
}


void inspectWheelIndexStreams(const Bytes& b) {
    const auto dir=std::size_t(read32le(b,12))*16,n=std::size_t(read32le(b,4)>>5);
    if(dir>b.size()||n>(b.size()-dir)/16)throw std::runtime_error("invalid article directory");
    for(const std::size_t article: {std::size_t(46),std::size_t(47)}) {
        if(article>=n)continue;
        const auto at=dir+article*16,rel=std::size_t(read32le(b,at+12)),len=std::size_t(read32le(b,at+8));
        if(rel>(b.size()-at)/16)throw std::runtime_error("invalid article offset");
        const auto begin=at+rel*16;
        if(len>(b.size()-begin)/16)throw std::runtime_error("invalid article size");
        std::size_t countPositions=0,countUvs=0;
        for(std::size_t i=0;i<len;++i){
            const auto p=begin+i*16;
            const auto tag=std::string{char(b[p+2]),char(b[p+3])};
            const auto level=unsigned(b[p])|(unsigned(b[p+1])<<8);
            if(level!=1)continue;
            if(tag=="tv")countPositions=read32le(b,p+8);
            if(tag=="vu")countUvs=read32le(b,p+8);
        }
        std::cout<<"Article "<<article<<" "<<articleName(b,article)
                 <<" positions="<<countPositions<<" uvPairs="<<countUvs<<"\n";
        for(std::size_t i=0;i<len;++i){
            const auto p=begin+i*16;
            if(b[p+2]!='r'||b[p+3]!='p')continue;
            const unsigned descriptor=unsigned(b[p])|(unsigned(b[p+1])<<8);
            if((descriptor>>12)!=1)continue;
            const auto bytes=std::size_t(read32le(b,p+4)>>8);
            const auto off=std::size_t(read32le(b,p+12));
            const auto entries=std::size_t(read32le(b,p+8));
            if(off>b.size()-p||bytes>b.size()-p-off||bytes<48)continue;
            const auto base=p+off,infos=std::size_t(read32le(b,base+40)),streams=std::size_t(read32le(b,base+44));
            if(infos>(bytes-48)/16||streams>(bytes-48-infos*16)/8)continue;
            const auto dataStart=48+infos*16+streams*8;
            if(dataStart>bytes)continue;
            std::cout<<"  polygon 0x"<<std::hex<<descriptor<<std::dec<<" entries="<<entries<<"\n";
            for(std::size_t k=0;k<streams;++k){
                const auto q=base+48+infos*16+k*8;
                const auto id=unsigned(b[q+2])|(unsigned(b[q+3])<<8);
                const auto offset=std::size_t(read32le(b,q+4));
                std::cout<<"    stream 0x"<<std::hex<<id<<std::dec<<" offset="<<offset;
                if(offset>bytes-dataStart||entries>bytes-dataStart-offset){
                    std::cout<<" INVALID RANGE\\n";continue;
                }
                unsigned lo=255,hi=0;
                for(std::size_t j=0;j<entries;++j){
                    const auto val=unsigned(b[base+dataStart+offset+j]);
                    lo=std::min(lo,val);hi=std::max(hi,val);
                }
                std::cout<<" indexRange="<<lo<<".."<<hi
                         <<" fitsPositions="<<(hi<countPositions?"yes":"no")
                         <<" fitsUVs="<<(hi<countUvs?"yes":"no")<<"\n";
                for(std::size_t j=0;j<std::min<std::size_t>(entries/3,5);++j) {
                    const auto data=base+dataStart+offset+j*3;
                    std::cout<<"      triangle["<<j<<"]="
                             <<unsigned(b[data])<<","<<unsigned(b[data+1])<<","<<unsigned(b[data+2])<<"\n";
                }
            }
        }
    }
    std::cout<<"NOTE: raw index values may be local to referenced buffers; range fit is not proof of semantics.\\n";
}


void inspectCrpTextures(const Bytes& b) {
    if(b.size()<16)throw std::runtime_error("truncated CRP header");
    const auto count=std::size_t(read32le(b,4)>>5);
    const auto misc=std::size_t(read32le(b,8));
    const auto table=std::size_t(read32le(b,12))*16;
    if(table>b.size()||count>(b.size()-table)/16)throw std::runtime_error("article table outside CRP");
    const auto start=table+count*16;
    if(start>b.size()||misc>(b.size()-start)/16)throw std::runtime_error("misc table outside CRP");
    std::cout<<"CRP miscellaneous resources: "<<misc<<" records at byte "<<start<<"\n";
    std::map<std::string,std::size_t> frequencies;
    for(std::size_t i=0;i<misc;++i){
        const auto p=start+i*16;
        const std::string tag{char(b[p+2]),char(b[p+3])};
        ++frequencies[tag];
        const auto resource=unsigned(b[p])|(unsigned(b[p+1])<<8);
        const auto bytes=std::size_t(read32le(b,p+4)>>8);
        const auto offset=std::size_t(read32le(b,p+12));
        const bool valid=offset<=b.size()-p&&bytes<=b.size()-p-offset;
        std::cout<<"  misc["<<i<<"] tag="<<tag<<" id="<<resource
                 <<" length="<<bytes<<" offset="<<offset
                 <<" valid="<<(valid?"yes":"no");
        if(valid && bytes>=4) {
            const auto base=p+offset;
            std::cout<<" first8=";
            for(std::size_t j=0;j<std::min<std::size_t>(8,bytes);++j)
                std::cout<<std::hex<<std::setfill('0')<<std::setw(2)<<unsigned(b[base+j]);
            std::cout<<std::dec<<std::setfill(' ');
            if(bytes>=16 && b[base]=='S'&&b[base+1]=='H'&&b[base+2]=='P'&&b[base+3]=='I')
                std::cout<<" FSH_SHPI entries="<<read32le(b,base+8);
        }
        std::cout<<"\n";
    }
    std::cout<<"Misc tag counts:";
    for(const auto& item:frequencies)std::cout<<" "<<item.first<<"="<<item.second;
    std::cout<<"\\nNOTE: metadata inspection only; no copyrighted textures extracted.\\n";
}


void exportEmbeddedFsh(const Bytes& b, const std::filesystem::path& destination) {
    if(b.size()<16)throw std::runtime_error("truncated CRP");
    const auto count=std::size_t(read32le(b,4)>>5),misc=std::size_t(read32le(b,8));
    const auto table=std::size_t(read32le(b,12))*16;
    if(table>b.size()||count>(b.size()-table)/16)throw std::runtime_error("invalid article directory");
    const auto begin=table+count*16;
    if(misc>(b.size()-begin)/16)throw std::runtime_error("invalid miscellaneous directory");
    struct Resource {unsigned id;std::size_t start,length,entries;};
    std::vector<Resource> archives;
    for(std::size_t i=0;i<misc;++i){
        const auto p=begin+i*16;
        if(b[p+2]!='f'||b[p+3]!='s')continue;
        const auto bytes=std::size_t(read32le(b,p+4)>>8),offset=std::size_t(read32le(b,p+12));
        if(offset>b.size()-p||bytes>b.size()-p-offset||bytes<16)
            throw std::runtime_error("invalid embedded FSH extent");
        const auto start=p+offset;
        if(b[start]!='S'||b[start+1]!='H'||b[start+2]!='P'||b[start+3]!='I')
            throw std::runtime_error("embedded FSH lacks SHPI header");
        const auto declared=std::size_t(read32le(b,start+4));
        if(declared>bytes||declared<16)throw std::runtime_error("invalid embedded FSH size");
        archives.push_back({unsigned(b[p])|(unsigned(b[p+1])<<8),start,declared,read32le(b,start+8)});
    }
    if(archives.empty())throw std::runtime_error("no FSH archives found");
    if(std::filesystem::exists(destination))throw std::runtime_error("output directory already exists");
    if(!std::filesystem::create_directory(destination))
        throw std::runtime_error("unable to create destination directory (create parent first)");
    for(const auto& archive:archives){
        const auto path=destination/("fs-"+std::to_string(archive.id)+".fsh");
        std::ofstream out(path,std::ios::binary);
        if(!out)throw std::runtime_error("cannot open FSH output file");
        out.write(reinterpret_cast<const char*>(b.data()+archive.start),std::streamsize(archive.length));
        out.close();
        if(!out)throw std::runtime_error("failed writing FSH");
        std::cout<<"Extracted "<<path<<" ("<<archive.length<<" bytes, "
                 <<archive.entries<<" SHPI entries)\\n";
    }
    std::cout<<"Embedded archives extracted locally; source CRP unchanged.\\n";
}


void inspectBodyNormalAlignment(const Bytes& b) {
    const auto n=std::size_t(read32le(b,4)>>5),dir=std::size_t(read32le(b,12))*16;
    if(dir>b.size()||n>(b.size()-dir)/16||n<=5)throw std::runtime_error("invalid body article");
    const auto at=dir+5*16,rel=std::size_t(read32le(b,at+12)),len=std::size_t(read32le(b,at+8));
    if(rel>(b.size()-at)/16)throw std::runtime_error("invalid body offset");
    const auto begin=at+rel*16;
    if(len>(b.size()-begin)/16)throw std::runtime_error("invalid body descriptors");
    std::size_t vp=SIZE_MAX,np=SIZE_MAX,vc=0,nc=0;
    for(std::size_t i=0;i<len;++i){
        const auto p=begin+i*16;
        const auto level=unsigned(b[p])|(unsigned(b[p+1])<<8);
        if(level!=1)continue;
        const auto tag=std::string{char(b[p+2]),char(b[p+3])};
        const auto count=std::size_t(read32le(b,p+8)),bytes=std::size_t(read32le(b,p+4)>>8),off=std::size_t(read32le(b,p+12));
        if(!count||count>SIZE_MAX/16||bytes!=count*16||off>b.size()-p||bytes>b.size()-p-off)continue;
        if(tag=="tv"){vp=p+off;vc=count;}
        if(tag=="mn"){np=p+off;nc=count;}
    }
    if(vp==SIZE_MAX||np==SIZE_MAX||vc!=nc)throw std::runtime_error("body positions and normals do not correspond");
    auto xyz=[&](std::size_t base,std::size_t index){
        std::array<double,3> v{};
        for(int axis=0;axis<3;++axis){auto bits=read32le(b,base+index*16+axis*4);float x;std::memcpy(&x,&bits,4);v[axis]=x;}
        return v;
    };
    std::size_t triangles=0,positive=0,negative=0,nearZero=0;
    double sum=0;
    std::cout<<"Body normal diagnostic: positions="<<vc<<" normals="<<nc<<"\n";
    for(std::size_t i=0;i<len;++i){
        const auto p=begin+i*16;
        if(b[p+2]!='r'||b[p+3]!='p')continue;
        const auto level=(unsigned(b[p])|(unsigned(b[p+1])<<8))>>12;
        if(level!=1)continue;
        const auto bytes=std::size_t(read32le(b,p+4)>>8),off=std::size_t(read32le(b,p+12)),entries=std::size_t(read32le(b,p+8));
        if(off>b.size()-p||bytes>b.size()-p-off||bytes<48||entries%3)continue;
        const auto base=p+off,infos=std::size_t(read32le(b,base+40)),streams=std::size_t(read32le(b,base+44));
        if(infos>(bytes-48)/16||streams>(bytes-48-infos*16)/8)continue;
        const auto data=48+infos*16+streams*8;
        std::size_t streamOff=SIZE_MAX,adjust=SIZE_MAX;
        for(std::size_t k=0;k<streams;++k){auto q=base+48+infos*16+k*8;auto id=unsigned(b[q+2])|(unsigned(b[q+3])<<8);if(id==0x4976)streamOff=read32le(b,q+4);}
        for(std::size_t k=0;k<infos;++k){auto q=base+48+k*16;auto id=unsigned(b[q+10])|(unsigned(b[q+11])<<8);auto l=unsigned(b[q+12])|(unsigned(b[q+13])<<8);auto off2=read32le(b,q+4);if(id==0&&l==1&&off2%16==0)adjust=off2/16;}
        if(streamOff==SIZE_MAX||adjust==SIZE_MAX||streamOff>bytes-data||entries>bytes-data-streamOff)continue;
        for(std::size_t k=0;k<entries;k+=3){
            std::size_t index[3];
            for(int c=0;c<3;++c)index[c]=std::size_t(b[base+data+streamOff+k+c])+adjust;
            if(index[0]>=vc||index[1]>=vc||index[2]>=vc)continue;
            const auto a=xyz(vp,index[0]),bb=xyz(vp,index[1]),c=xyz(vp,index[2]);
            const std::array<double,3> u{bb[0]-a[0],bb[1]-a[1],bb[2]-a[2]},v{c[0]-a[0],c[1]-a[1],c[2]-a[2]};
            const std::array<double,3> cross{u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]};
            const double length=std::sqrt(cross[0]*cross[0]+cross[1]*cross[1]+cross[2]*cross[2]);
            if(length<1e-10)continue;
            const auto normal=xyz(np,index[0]);
            const double nl=std::sqrt(normal[0]*normal[0]+normal[1]*normal[1]+normal[2]*normal[2]);
            if(nl<1e-10)continue;
            const double dot=(cross[0]*normal[0]+cross[1]*normal[1]+cross[2]*normal[2])/(length*nl);
            if(dot>0.2)++positive;else if(dot< -0.2)++negative;else ++nearZero;
            sum+=dot;
            if(triangles<12)std::cout<<"  face["<<triangles<<"] vertices="<<index[0]<<","<<index[1]<<","<<index[2]<<" normalDot="<<dot<<"\n";
            ++triangles;
        }
    }
    std::cout<<"Body normal alignment: tested="<<triangles<<" positive="<<positive<<" negative="<<negative<<" ambiguous="<<nearZero
             <<" meanDot="<<(triangles?sum/triangles:0)<<"\n";
    std::cout<<"NOTE: diagnostic compares the first stored vertex normal per face, not Blender's evaluated loop normals.\\n";
}





void inspectMaterialRecordComparison(const Bytes& b) {
    const std::size_t n=read32le(b,4)>>5,dir=std::size_t(read32le(b,12))*16;
    if(dir>b.size()||n>(b.size()-dir)/16)throw std::runtime_error("invalid article directory");
    const std::array<std::size_t,10> selected{{32,17,18,15,23,12,36,5,46,56}};
    struct Record {std::size_t article;std::string name;std::vector<std::uint8_t> data;};
    std::vector<Record> records;
    for(auto article:selected) {
        if(article>=n)continue;
        const auto at=dir+article*16,rel=std::size_t(read32le(b,at+12)),len=std::size_t(read32le(b,at+8));
        if(rel>(b.size()-at)/16)throw std::runtime_error("bad article offset");
        const auto begin=at+rel*16;
        if(len>(b.size()-begin)/16)throw std::runtime_error("bad article descriptors");
        for(std::size_t i=0;i<len;++i){
            const auto p=begin+i*16;
            if(b[p+2]!='a'||b[p+3]!='B')continue;
            const auto bytes=std::size_t(read32le(b,p+4)>>8),off=std::size_t(read32le(b,p+12));
            if(off>b.size()-p||bytes>b.size()-p-off)throw std::runtime_error("bad aB payload");
            records.push_back({article,articleName(b,article),{b.begin()+std::ptrdiff_t(p+off),b.begin()+std::ptrdiff_t(p+off+bytes)}});
        }
    }
    std::cout<<"AB RECORD COMPARISON: offsets are relative to aB payload, not descriptor\n";
    for(const auto& rec:records){
        std::cout<<"  article="<<rec.article<<" name="<<rec.name<<" bytes="<<rec.data.size()<<"\n";
        for(std::size_t offset=0;offset<rec.data.size();offset+=16){
            std::cout<<"    +0x"<<std::hex<<std::setw(3)<<std::setfill('0')<<offset<<std::dec<<std::setfill(' ')<<" ";
            for(std::size_t j=0;j<16;++j) {
                if(offset+j<rec.data.size())
                    std::cout<<std::hex<<std::setw(2)<<std::setfill('0')<<unsigned(rec.data[offset+j])<<" ";
                else std::cout<<"   ";
            }
            std::cout<<std::dec<<std::setfill(' ')<<"\n";
        }
    }
    std::cout<<"AB BYTE COMPARISON: rows with differing values (missing bytes shown as --)\n";
    std::size_t maxLength=0;
    for(const auto& rec:records)maxLength=std::max(maxLength,rec.data.size());
    for(std::size_t pos=0;pos<maxLength;++pos){
        bool differing=false;
        for(std::size_t i=1;i<records.size();++i){
            if(pos>=records[0].data.size()||pos>=records[i].data.size()||
               records[0].data[pos]!=records[i].data[pos]){differing=true;break;}
        }
        if(!differing)continue;
        std::cout<<"  +0x"<<std::hex<<std::setw(3)<<std::setfill('0')<<pos<<std::dec<<std::setfill(' ')<<":";
        for(const auto& rec:records){
            std::cout<<" "<<rec.article<<"=";
            if(pos<rec.data.size())std::cout<<std::hex<<std::setw(2)<<std::setfill('0')<<unsigned(rec.data[pos])<<std::dec<<std::setfill(' ');
            else std::cout<<"--";
        }
        std::cout<<"\n";
    }
    std::cout<<"NOTE: byte differences are observations; no semantic mapping has been inferred.\n";
}

void inspectMaterialWordCandidates(const Bytes& b) {
    const std::size_t n=read32le(b,4)>>5,dir=std::size_t(read32le(b,12))*16;
    if(dir>b.size()||n>(b.size()-dir)/16)throw std::runtime_error("bad article directory");
    struct Entry {std::size_t index; std::string name; std::vector<std::uint8_t> bytes;};
    std::vector<Entry> entries;
    for(std::size_t article=0;article<n;++article){
        const auto at=dir+article*16,rel=std::size_t(read32le(b,at+12)),count=std::size_t(read32le(b,at+8));
        if(rel>(b.size()-at)/16)throw std::runtime_error("bad article offset");
        const auto start=at+rel*16;
        if(count>(b.size()-start)/16)throw std::runtime_error("bad descriptor span");
        for(std::size_t i=0;i<count;++i){
            const auto p=start+i*16;
            if(b[p+2]!='a'||b[p+3]!='B')continue;
            const auto size=std::size_t(read32le(b,p+4)>>8),off=std::size_t(read32le(b,p+12));
            if(off>b.size()-p||size>b.size()-p-off)throw std::runtime_error("bad aB extent");
            entries.push_back({article,articleName(b,article),
                {b.begin()+std::ptrdiff_t(p+off),b.begin()+std::ptrdiff_t(p+off+size)}});
        }
    }
    std::cout<<"AB WORD CANDIDATES: offset-relative little-endian interpretation, all articles\n";
    std::cout<<"article name size b44 b45 b46 b47 b48 b49 b4a b4b b4e u16_44 u16_46 u16_48 u16_4a u16_4e u32_44 u32_46 u32_48 u32_4a\n";
    for(const auto& e:entries){
        auto byte=[&](std::size_t p)->std::uint32_t {return p<e.bytes.size()?e.bytes[p]:0;};
        auto u16=[&](std::size_t p)->std::uint32_t {return byte(p)|(byte(p+1)<<8);};
        auto u32=[&](std::size_t p)->std::uint32_t {return u16(p)|(u16(p+2)<<16);};
        if(e.bytes.size()<0x50)continue;
        std::cout<<e.index<<" "<<e.name<<" "<<e.bytes.size();
        for(auto p:{0x44,0x45,0x46,0x47,0x48,0x49,0x4a,0x4b,0x4e})std::cout<<" "<<byte(p);
        for(auto p:{0x44,0x46,0x48,0x4a,0x4e})std::cout<<" "<<u16(p);
        for(auto p:{0x44,0x46,0x48,0x4a})std::cout<<" "<<u32(p);
        std::cout<<"\n";
    }
    std::cout<<"NOTE: candidate values are raw numerical views, not confirmed pointers or texture identifiers.\n";
}

void inspectMaterialCandidateDistribution(const Bytes& b) {
    const std::size_t n=read32le(b,4)>>5,dir=std::size_t(read32le(b,12))*16;
    if(dir>b.size()||n>(b.size()-dir)/16)throw std::runtime_error("invalid article directory");
    std::map<unsigned,std::vector<std::size_t>> byCandidate;
    for(std::size_t article=0;article<n;++article){
        const auto at=dir+article*16,rel=std::size_t(read32le(b,at+12)),len=std::size_t(read32le(b,at+8));
        if(rel>(b.size()-at)/16)throw std::runtime_error("bad article offset");
        const auto begin=at+rel*16;
        if(len>(b.size()-begin)/16)throw std::runtime_error("bad article descriptors");
        for(std::size_t i=0;i<len;++i){
            const auto p=begin+i*16;
            if(b[p+2]!='a'||b[p+3]!='B')continue;
            const auto size=std::size_t(read32le(b,p+4)>>8),off=std::size_t(read32le(b,p+12));
            if(off>b.size()-p||size>b.size()-p-off||size<76)continue;
            byCandidate[unsigned(b[p+off+74])].push_back(article);
        }
    }
    std::cout<<"MATERIAL CANDIDATE DISTRIBUTION: raw aB payload byte 74 across all articles\\n";
    for(const auto& group:byCandidate){
        std::cout<<"  value="<<group.first<<" signed="<<(group.first>=128?int(group.first)-256:int(group.first))
                 <<" count="<<group.second.size()<<" articles=";
        for(const auto article:group.second)
            std::cout<<article<<"("<<articleName(b,article)<<") ";
        std::cout<<"\n";
    }
    std::cout<<"NOTE: this is a byte-frequency survey, not confirmed material or FSH identification.\\n";
}

void inspectGlassLightMaterialRefs(const Bytes& b) {
    const std::size_t n=read32le(b,4)>>5,dir=std::size_t(read32le(b,12))*16;
    if(dir>b.size()||n>(b.size()-dir)/16)throw std::runtime_error("invalid article directory");
    for(const std::size_t article: {std::size_t(36),std::size_t(32),std::size_t(17),std::size_t(18),std::size_t(46)}) {
        if(article>=n)continue;
        const auto at=dir+article*16,rel=std::size_t(read32le(b,at+12)),len=std::size_t(read32le(b,at+8));
        if(rel>(b.size()-at)/16)throw std::runtime_error("invalid article offset");
        const auto begin=at+rel*16;
        if(len>(b.size()-begin)/16)throw std::runtime_error("invalid article descriptors");
        std::cout<<"MATERIAL REF article="<<article<<" name="<<articleName(b,article)<<"\n";
        for(std::size_t i=0;i<len;++i) {
            const auto p=begin+i*16;
            const auto size=std::size_t(read32le(b,p+4)>>8),off=std::size_t(read32le(b,p+12));
            if(off>b.size()-p||size>b.size()-p-off)continue;
            const std::string tag{char(b[p+2]),char(b[p+3])};
            const unsigned id=unsigned(b[p])|(unsigned(b[p+1])<<8);
            if(tag=="aB") {
                std::cout<<"  aB id=0x"<<std::hex<<id<<std::dec<<" bytes="<<size;
                if(size>=76)std::cout<<" geometryCandidate="<<unsigned(b[p+off+68])
                    <<" textureCandidate="<<unsigned(b[p+off+74]);
                std::cout<<" raw[64:96]=";
                for(std::size_t j=64;j<std::min<std::size_t>(96,size);++j)
                    std::cout<<std::hex<<std::setfill('0')<<std::setw(2)<<unsigned(b[p+off+j]);
                std::cout<<std::dec<<std::setfill(' ')<<"\n";
            } else if(tag=="rp"&&(id>>12)==1&&size>=48) {
                const auto base=p+off;
                std::cout<<"  rp group=0x"<<std::hex<<id<<std::dec
                    <<" indices="<<read32le(b,p+8)<<" header[0:40]=";
                for(std::size_t j=0;j<40;++j)
                    std::cout<<std::hex<<std::setfill('0')<<std::setw(2)<<unsigned(b[base+j]);
                std::cout<<std::dec<<std::setfill(' ')<<"\n";
            }
        }
    }
    std::cout<<"NOTE: raw aB bytes and rp header are candidate references, not confirmed FSH mappings.\\n";
}

void inspectGlassLightUv(const Bytes& b) {
    const auto n=std::size_t(read32le(b,4)>>5),dir=std::size_t(read32le(b,12))*16;
    if(dir>b.size()||n>(b.size()-dir)/16)throw std::runtime_error("bad directory");
    for(const std::size_t article: {std::size_t(36),std::size_t(32),std::size_t(17),std::size_t(18)}) {
        if(article>=n)continue;
        const auto at=dir+article*16,rel=std::size_t(read32le(b,at+12)),len=std::size_t(read32le(b,at+8));
        if(rel>(b.size()-at)/16)throw std::runtime_error("bad article offset");
        const auto begin=at+rel*16;
        if(len>(b.size()-begin)/16)throw std::runtime_error("bad article extent");
        std::size_t positions=0,uvs=0,normals=0;
        for(std::size_t i=0;i<len;++i) {
            const auto p=begin+i*16;
            const auto level=unsigned(b[p])|(unsigned(b[p+1])<<8);
            if(level!=1)continue;
            const std::string tag{char(b[p+2]),char(b[p+3])};
            const auto count=std::size_t(read32le(b,p+8));
            if(tag=="tv")positions=count;
            if(tag=="vu")uvs=count;
            if(tag=="mn")normals=count;
        }
        std::cout<<"Article "<<article<<" "<<articleName(b,article)
                 <<" positions="<<positions<<" uvPairs="<<uvs<<" normals="<<normals<<"\n";
        for(std::size_t i=0;i<len;++i) {
            const auto p=begin+i*16;
            if(b[p+2]!='r'||b[p+3]!='p')continue;
            const auto id=unsigned(b[p])|(unsigned(b[p+1])<<8);
            if((id>>12)!=1)continue;
            const auto bytes=std::size_t(read32le(b,p+4)>>8),off=std::size_t(read32le(b,p+12)),entries=std::size_t(read32le(b,p+8));
            if(off>b.size()-p||bytes>b.size()-p-off||bytes<48)continue;
            const auto base=p+off,infos=std::size_t(read32le(b,base+40)),streams=std::size_t(read32le(b,base+44));
            if(infos>(bytes-48)/16||streams>(bytes-48-infos*16)/8)continue;
            const auto data=48+infos*16+streams*8;
            std::cout<<"  polygon=0x"<<std::hex<<id<<std::dec<<" entries="<<entries;
            for(std::size_t k=0;k<infos;++k){
                const auto q=base+48+k*16;
                const auto attr=unsigned(b[q+10])|(unsigned(b[q+11])<<8);
                if(attr==0||attr==1||attr==2)
                    std::cout<<" attr"<<attr<<"=(offset:"<<read32le(b,q+4)<<",bytes:"
                             <<(unsigned(b[q+8])|(unsigned(b[q+9])<<8))<<")";
            }
            std::cout<<"\n";
            for(std::size_t k=0;k<streams;++k){
                const auto q=base+48+infos*16+k*8;
                const auto stream=unsigned(b[q+2])|(unsigned(b[q+3])<<8);
                const auto offset=std::size_t(read32le(b,q+4));
                std::cout<<"    stream=0x"<<std::hex<<stream<<std::dec<<" offset="<<offset;
                if(offset>bytes-data||entries>bytes-data-offset){std::cout<<" invalid range\\n";continue;}
                unsigned low=255,high=0;
                for(std::size_t j=0;j<entries;++j){unsigned v=b[base+data+offset+j];low=std::min(low,v);high=std::max(high,v);}
                std::cout<<" range="<<low<<".."<<high<<" sample=";
                for(std::size_t j=0;j<std::min<std::size_t>(9,entries);++j)
                    std::cout<<(j?",":"")<<unsigned(b[base+data+offset+j]);
                std::cout<<"\n";
            }
        }
    }
    std::cout<<"NOTE: range fits alone do not prove UV mapping or material selection.\\n";
}

void inspectComponentMetadata(const Bytes& b) {
    const std::size_t dir=std::size_t(read32le(b,12))*16,n=read32le(b,4)>>5;
    if(dir>b.size()||n>(b.size()-dir)/16)throw std::runtime_error("bad article directory");
    const std::size_t ids[]{4,5,13,28,46,47,48,49,52,53};
    for(const auto article: ids) {
        if(article>=n)continue;
        const std::size_t at=dir+article*16,off=read32le(b,at+12),len=read32le(b,at+8);
        if(off>(b.size()-at)/16)throw std::runtime_error("bad article offset");
        const auto begin=at+off*16;
        if(len>(b.size()-begin)/16)throw std::runtime_error("bad article length");
        std::cout<<"Article "<<article<<" "<<articleName(b,article)<<"\n";
        for(std::size_t p=begin;p<begin+len*16;p+=16) {
            const std::size_t rel=read32le(b,p+12),bytes=read32le(b,p+4)>>8;
            if(rel>b.size()-p||bytes>b.size()-p-rel)continue;
            const std::size_t start=p+rel;
            if(b[p+2]=='a'&&b[p+3]=='B') {
                if(bytes<100){std::cout<<"  Base payload too short: "<<bytes<<"\n";continue;}
                // CBase::Read: flags(16) + hasFloats(4) + floats(48) = 68.
                const std::size_t infoStart=start+68;
                auto v=[&](int i){return unsigned(b[infoStart+i]);};
                std::cout<<"  Base: geomIndex="<<v(0)<<" typeIndex="<<v(1)
                         <<" geomPlace="<<v(3)<<" wheelType="<<v(4)
                         <<" extraType="<<v(5)<<" textureType="<<v(6)
                         <<" geomType="<<v(7)<<" animCount="<<v(8)
                         <<" animType="<<v(9)<<" levelIndex="<<v(10)
                         <<" hand="<<v(14)<<"\n";
            }
            if(b[p+2]=='r'&&b[p+3]=='t'&&bytes>=64) {
                const unsigned info=unsigned(b[p])|(unsigned(b[p+1])<<8);
                if(info!=1)continue;
                std::cout<<"  level1 matrix (four rows of four):\n";
                for(int row=0;row<4;++row) {
                    std::cout<<"    ";
                    for(int col=0;col<4;++col) {
                        const std::uint32_t bits=read32le(b,start+4*(row*4+col));
                        float value;std::memcpy(&value,&bits,4);
                        std::cout<<(col?" ":"")<<value;
                    }
                    std::cout<<"\n";
                }
            }
        }
    }
}



void compareRearLids(const Bytes& b) {
    const std::size_t dir=std::size_t(read32le(b,12))*16,n=read32le(b,4)>>5;
    if(dir>b.size()||n>(b.size()-dir)/16)throw std::runtime_error("invalid directory");
    for(const std::size_t article: {std::size_t(4),std::size_t(6),std::size_t(39),
                                     std::size_t(52),std::size_t(53)}) {
        if(article>=n)continue;
        const std::size_t at=dir+article*16;
        const std::size_t rel=read32le(b,at+12);
        const std::size_t len=read32le(b,at+8);
        if(rel>(b.size()-at)/16)throw std::runtime_error("invalid article offset");
        const auto begin=at+rel*16;
        if(len>(b.size()-begin)/16)throw std::runtime_error("invalid article length");
        std::map<std::string,std::size_t> tags;
        std::map<unsigned,std::size_t> polygonLevels;
        std::cout<<"Article "<<article<<" "<<articleName(b,article)<<"\n";
        for(std::size_t p=begin;p<begin+len*16;p+=16) {
            const std::string tag{char(b[p+2]),char(b[p+3])};
            ++tags[tag];
            const std::size_t off=read32le(b,p+12),bytes=read32le(b,p+4)>>8;
            if(off>b.size()-p||bytes>b.size()-p-off)continue;
            const auto start=p+off;
            if(tag=="aB") {
                if(bytes<100)continue;
                const auto levels=read32le(b,start+12);
                const auto i=start+68;
                std::cout<<"  Base flags="<<read32le(b,start)
                    <<" geomIndex="<<unsigned(b[i])
                    <<" typeIndex="<<unsigned(b[i+1])
                    <<" geomPlace="<<unsigned(b[i+3])
                    <<" geomType="<<unsigned(b[i+7])
                    <<" extraType="<<unsigned(b[i+5])
                    <<" animType="<<unsigned(b[i+9])
                    <<" levelIndex="<<unsigned(b[i+10])
                    <<" levelCount="<<levels<<"\n";
                if(levels<=32&&bytes>=100+levels*12) {
                    for(std::size_t j=0;j<levels;++j) {
                        const auto m=start+100+j*12;
                        const auto level=unsigned(b[m+8])|(unsigned(b[m+9])<<8);
                        std::cout<<"    levelMask["<<j<<"] level="<<level
                            <<" min=0x"<<std::hex<<(unsigned(b[m+4])|(unsigned(b[m+5])<<8))
                            <<" max=0x"<<(unsigned(b[m+6])|(unsigned(b[m+7])<<8))
                            <<std::dec<<"\n";
                    }
                }
            }
            if(tag=="rt"&&bytes>=64) {
                const unsigned info=unsigned(b[p])|(unsigned(b[p+1])<<8);
                if(info==1) {
                    auto fl=[&](int k){const auto bits=read32le(b,start+48+4*k);float x;std::memcpy(&x,&bits,4);return x;};
                    std::cout<<"  level1 transform=("<<fl(0)<<","<<fl(1)<<","<<fl(2)<<")\n";
                }
            }
            if(tag=="rp"){
                const unsigned info=unsigned(b[p])|(unsigned(b[p+1])<<8);
                ++polygonLevels[info>>12];
            }
        }
        std::cout<<"  tag counts:";
        for(const auto& item:tags)std::cout<<" "<<item.first<<"="<<item.second;
        std::cout<<"\n  polygon descriptor levels:";
        for(const auto& item:polygonLevels)std::cout<<" "<<item.first<<"="<<item.second;
        std::cout<<"\n";
    }
}

void exportAssemblyMetadata(const Bytes& b, const std::filesystem::path& dest) {
    const std::size_t dir=std::size_t(read32le(b,12))*16,n=read32le(b,4)>>5;
    if(dir>b.size()||n>(b.size()-dir)/16)throw std::runtime_error("bad article table");
    if(std::filesystem::exists(dest))throw std::runtime_error("metadata output exists");
    std::ofstream out(dest);
    if(!out)throw std::runtime_error("cannot create metadata CSV");
    out<<"article,name,geom_index,type_index,geom_type,wheel_type,level_index,anim_type,tx,ty,tz,has_transform\n";
    for(std::size_t i=0;i<n;++i) {
        const std::size_t at=dir+i*16,rel=read32le(b,at+12),len=read32le(b,at+8);
        if(rel>(b.size()-at)/16)throw std::runtime_error("bad article offset");
        const auto begin=at+rel*16;
        if(len>(b.size()-begin)/16)throw std::runtime_error("bad article length");
        int geom=-1,type=-1,gtype=-1,wtype=-1,level=-1,anim=-1;
        float translation[3]{};
        bool hasTransform=false;
        for(std::size_t p=begin;p<begin+len*16;p+=16) {
            const std::size_t off=read32le(b,p+12),bytes=read32le(b,p+4)>>8;
            if(off>b.size()-p||bytes>b.size()-p-off)continue;
            const auto start=p+off;
            if(b[p+2]=='a'&&b[p+3]=='B'&&bytes>=100) {
                const auto info=start+68;
                geom=b[info];type=b[info+1];wtype=b[info+4];
                gtype=b[info+7];anim=b[info+9];level=b[info+10];
            }
            if(b[p+2]=='r'&&b[p+3]=='t'&&bytes>=64) {
                const unsigned info=unsigned(b[p])|(unsigned(b[p+1])<<8);
                if(info!=1)continue;
                for(int k=0;k<3;++k) {
                    const auto bits=read32le(b,start+48+k*4);
                    std::memcpy(&translation[k],&bits,4);
                    if(!std::isfinite(translation[k]))throw std::runtime_error("nonfinite transform");
                }
                hasTransform=true;
            }
        }
        out<<i<<","<<articleName(b,i)<<","<<geom<<","<<type<<","<<gtype<<","<<wtype
           <<","<<level<<","<<anim<<","<<translation[0]<<","<<translation[1]
           <<","<<translation[2]<<","<<(hasTransform?1:0)<<"\n";
    }
    if(!out)throw std::runtime_error("failed to write metadata");
    std::cout<<"Wrote assembly metadata for "<<n<<" articles: "<<dest<<"\n";
}

void exportBatch(const Bytes& b, const std::filesystem::path& destination) {
    if(std::filesystem::exists(destination))
        throw std::runtime_error("batch output directory already exists");
    std::filesystem::create_directories(destination);
    std::ofstream manifest(destination/"manifest.csv");
    if(!manifest)throw std::runtime_error("cannot write batch manifest");
    manifest<<"article,name,status,file_or_reason\n";
    const std::size_t count=read32le(b,4)>>5;
    std::size_t exported=0,failed=0;
    for(std::size_t i=0;i<count;++i) {
        const std::string name=articleName(b,i);
        const std::string filename=std::to_string(i)+"_"+name+".obj";
        try {
            exportArticleMesh(b,i,destination/filename);
            manifest<<i<<","<<name<<",exported,"<<filename<<"\n";
            ++exported;
        } catch(const std::exception& e) {
            manifest<<i<<","<<name<<",skipped,"<<'"'<<e.what()<<'"'<<"\n";
            ++failed;
        }
    }
    manifest.close();
    if(!manifest)throw std::runtime_error("failed writing manifest");
    std::cout<<"Batch complete: "<<exported<<" exported, "<<failed<<" skipped; details in "
             <<destination/"manifest.csv"<<"\n";
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


void inspectRearMeshGroups(const Bytes& b, bool spoiler=false) {
    const std::size_t n=read32le(b,4)>>5,dir=std::size_t(read32le(b,12))*16;
    if(dir>b.size()||n>(b.size()-dir)/16)throw std::runtime_error("invalid article directory");
    const std::vector<std::size_t> articles = spoiler ? std::vector<std::size_t>{52,53} : std::vector<std::size_t>{6,39,4};
    for(std::size_t article: articles) {
        if(article>=n)continue;
        const std::size_t at=dir+article*16,rel=read32le(b,at+12),len=read32le(b,at+8);
        if(rel>(b.size()-at)/16)throw std::runtime_error("invalid article offset");
        const std::size_t begin=at+rel*16;
        if(len>(b.size()-begin)/16)throw std::runtime_error("invalid article length");
        const std::size_t end=begin+len*16;
        std::size_t vertices=0,vertexStart=0,bufferCount=0;
        for(std::size_t p=begin;p<end;p+=16) {
            if(b[p+2]!='t'||b[p+3]!='v')continue;
            const unsigned info=unsigned(b[p])|(unsigned(b[p+1])<<8);
            const std::size_t size=read32le(b,p+4)>>8,count=read32le(b,p+8),off=read32le(b,p+12);
            if(info!=1||!count||count>SIZE_MAX/16||size!=count*16||off>b.size()-p||size>b.size()-p-off)continue;
            vertexStart=p+off;vertices=count;++bufferCount;
        }
        std::cout<<"Article "<<article<<" "<<articleName(b,article)
                 <<" level1 vertex buffers="<<bufferCount<<" vertex count="<<vertices<<"\n";
        if(bufferCount!=1)continue;
        auto coordinate=[&](std::size_t idx,int axis) {
            const auto bits=read32le(b,vertexStart+idx*16+axis*4);
            float value;std::memcpy(&value,&bits,4);return value;
        };
        std::size_t group=0;
        for(std::size_t p=begin;p<end;p+=16) {
            if(b[p+2]!='r'||b[p+3]!='p')continue;
            const unsigned info=unsigned(b[p])|(unsigned(b[p+1])<<8);
            if((info>>12)!=1)continue;
            ++group;
            const std::size_t size=read32le(b,p+4)>>8,count=read32le(b,p+8),off=read32le(b,p+12);
            std::cout<<"  group "<<group<<" descriptor=0x"<<std::hex<<info<<std::dec
                     <<" triangles="<<count/3;
            if(off>b.size()-p||size>b.size()-p-off||size<48||count%3) {
                std::cout<<" INVALID descriptor\n";continue;
            }
            const std::size_t base=p+off,infos=read32le(b,base+40),streams=read32le(b,base+44);
            if(infos>(size-48)/16||streams>(size-48-infos*16)/8||streams==0) {
                std::cout<<" INVALID tables\n";continue;
            }
            const std::size_t data=48+infos*16+streams*8;
            if(count>(size-data)/streams) {std::cout<<" INVALID stream data\n";continue;}
            std::size_t indexOffset=SIZE_MAX,adjust=SIZE_MAX;
            for(std::size_t k=0;k<streams;++k){
                const auto q=base+48+infos*16+k*8;
                const unsigned id=unsigned(b[q+2])|(unsigned(b[q+3])<<8);
                if(id==0x4976)indexOffset=read32le(b,q+4);
            }
            for(std::size_t k=0;k<infos;++k){
                const auto q=base+48+k*16;
                const unsigned id=unsigned(b[q+10])|(unsigned(b[q+11])<<8);
                const unsigned level=unsigned(b[q+12])|(unsigned(b[q+13])<<8);
                if(id==0&&level==1&&read32le(b,q+4)%16==0)
                    adjust=read32le(b,q+4)/16;
            }
            if(indexOffset==SIZE_MAX||adjust==SIZE_MAX||indexOffset>size-data||count>size-data-indexOffset){
                std::cout<<" INVALID offsets\n";continue;
            }
            float lo[3]={INFINITY,INFINITY,INFINITY},hi[3]={-INFINITY,-INFINITY,-INFINITY};
            std::size_t minIndex=SIZE_MAX,maxIndex=0;
            bool valid=true;
            for(std::size_t k=0;k<count;++k){
                const std::size_t idx=std::size_t(b[base+data+indexOffset+k])+adjust;
                if(idx>=vertices){valid=false;break;}
                minIndex=std::min(minIndex,idx);maxIndex=std::max(maxIndex,idx);
                for(int axis=0;axis<3;++axis){
                    const float value=coordinate(idx,axis);
                    if(!std::isfinite(value)){valid=false;break;}
                    lo[axis]=std::min(lo[axis],value);hi[axis]=std::max(hi[axis],value);
                }
                if(!valid)break;
            }
            if(!valid){std::cout<<" INVALID vertex indices/coordinates\n";continue;}
            std::cout<<" vertexSpan="<<minIndex<<".."<<maxIndex
                     <<" X="<<lo[0]<<".."<<hi[0]
                     <<" Y="<<lo[1]<<".."<<hi[1]
                     <<" Z="<<lo[2]<<".."<<hi[2]<<"\n";
        }
    }
}


void inspectSpoilerTopology(const Bytes& b) {
    const std::size_t n=read32le(b,4)>>5,dir=std::size_t(read32le(b,12))*16;
    if(dir>b.size()||n>(b.size()-dir)/16||n<=53)
        throw std::runtime_error("missing spoiler articles");
    struct Group {unsigned descriptor;std::vector<std::size_t> indices;};
    struct Mesh {std::vector<Group> groups;std::vector<std::array<float,3>> positions;};
    auto collect=[&](std::size_t article) {
        const auto at=dir+article*16;
        const std::size_t rel=read32le(b,at+12),len=read32le(b,at+8);
        if(rel>(b.size()-at)/16)throw std::runtime_error("article offset invalid");
        const auto begin=at+rel*16;
        if(len>(b.size()-begin)/16)throw std::runtime_error("article length invalid");
        const auto end=begin+len*16;
        std::size_t vertices=0,vertexStart=SIZE_MAX;
        for(std::size_t p=begin;p<end;p+=16) {
            const unsigned info=unsigned(b[p])|(unsigned(b[p+1])<<8);
            if(b[p+2]=='t'&&b[p+3]=='v'&&info==1){vertices=read32le(b,p+8);vertexStart=p+read32le(b,p+12);}
        }
        if(vertexStart==SIZE_MAX||vertices>100000||vertexStart>b.size()||vertices>(b.size()-vertexStart)/16)throw std::runtime_error("bad spoiler vertices");
        Mesh mesh;
        for(std::size_t i=0;i<vertices;++i){std::array<float,3> pos{};for(int k=0;k<3;++k){const auto bits=read32le(b,vertexStart+i*16+4*k);std::memcpy(&pos[k],&bits,4);}mesh.positions.push_back(pos);}
        auto& groups=mesh.groups;
        for(std::size_t p=begin;p<end;p+=16) {
            if(b[p+2]!='r'||b[p+3]!='p')continue;
            const unsigned info=unsigned(b[p])|(unsigned(b[p+1])<<8);
            if((info>>12)!=1)continue;
            const std::size_t bytes=read32le(b,p+4)>>8,count=read32le(b,p+8),relp=read32le(b,p+12);
            if(relp>b.size()-p||bytes>b.size()-p-relp||bytes<48||count%3)
                throw std::runtime_error("spoiler polygon descriptor invalid");
            const auto base=p+relp;
            const auto infos=read32le(b,base+40),streams=read32le(b,base+44);
            if(infos>(bytes-48)/16||streams>(bytes-48-infos*16)/8||!streams)
                throw std::runtime_error("spoiler polygon layout invalid");
            const auto data=48+infos*16+streams*8;
            std::size_t offset=SIZE_MAX,adjust=SIZE_MAX;
            for(std::size_t k=0;k<streams;++k){
                const auto q=base+48+infos*16+k*8;
                const unsigned id=unsigned(b[q+2])|(unsigned(b[q+3])<<8);
                if(id==0x4976)offset=read32le(b,q+4);
            }
            for(std::size_t k=0;k<infos;++k){
                const auto q=base+48+k*16;
                const unsigned id=unsigned(b[q+10])|(unsigned(b[q+11])<<8);
                const unsigned level=unsigned(b[q+12])|(unsigned(b[q+13])<<8);
                if(id==0&&level==1&&read32le(b,q+4)%16==0)adjust=read32le(b,q+4)/16;
            }
            if(offset==SIZE_MAX||adjust==SIZE_MAX||offset>bytes-data||count>bytes-data-offset)
                throw std::runtime_error("spoiler polygon index stream invalid");
            Group g{info,{}};
            for(std::size_t k=0;k<count;++k){
                const auto idx=std::size_t(b[base+data+offset+k])+adjust;
                if(idx>=vertices)throw std::runtime_error("spoiler vertex index out of range");
                g.indices.push_back(idx);
            }
            groups.push_back(std::move(g));
        }
        std::cout<<"Article "<<article<<": vertices="<<vertices<<" groups="<<groups.size()<<"\n";
        return mesh;
    };
    const auto down=collect(52),up=collect(53);
    for(const auto& d:down.groups) {
        const auto it=std::find_if(up.groups.begin(),up.groups.end(),[&](const Group& g){return g.descriptor==d.descriptor;});
        if(it==up.groups.end()){std::cout<<"  group 0x"<<std::hex<<d.descriptor<<std::dec<<" absent in raised state\n";continue;}
        const auto& u=*it;
        std::map<std::size_t,std::size_t> dm,um;
        for(auto idx:d.indices)if(!dm.count(idx))dm[idx]=dm.size();
        for(auto idx:u.indices)if(!um.count(idx))um[idx]=um.size();
        std::size_t same=0;
        const auto size=std::min(d.indices.size(),u.indices.size());
        for(std::size_t k=0;k<size;++k)if(d.indices[k]==u.indices[k])++same;
        // Compare triangle centroids in raw CRP coordinates. Greedy unique
        // nearest-centroid pairing is a heuristic, not a topology proof.
        auto centroid=[](const Mesh& mesh,const Group& g,std::size_t tri){
            std::array<double,3> c{};
            for(int j=0;j<3;++j){const auto& p=mesh.positions[g.indices[tri*3+j]];
                for(int k=0;k<3;++k)c[k]+=p[k]/3.0;}
            return c;
        };
        const std::size_t ntri=d.indices.size()/3;
        std::vector<bool> used(u.indices.size()/3,false);
        double total=0,maxDistance=0;
        std::size_t orderMatches=0;
        for(std::size_t i=0;i<ntri;++i){
            const auto a=centroid(down,d,i);
            double best=INFINITY;std::size_t bestj=SIZE_MAX;
            for(std::size_t j=0;j<used.size();++j){
                if(used[j])continue;
                const auto b=centroid(up,u,j);
                double distance=0;
                for(int k=0;k<3;++k)distance+=(a[k]-b[k])*(a[k]-b[k]);
                if(distance<best){best=distance;bestj=j;}
            }
            if(bestj==SIZE_MAX)break;
            used[bestj]=true;
            if(i==bestj)++orderMatches;
            const double dist=std::sqrt(best);
            total+=dist;maxDistance=std::max(maxDistance,dist);
        }
        std::cout<<"  group 0x"<<std::hex<<d.descriptor<<std::dec
                 <<" triangles="<<d.indices.size()/3<<"/"<<u.indices.size()/3
                 <<" unique_vertices="<<dm.size()<<"/"<<um.size()
                 <<" matching_raw_indices="<<same<<"/"<<size
                 <<" nearest_centroid_mean="<<(ntri?total/ntri:0)
                 <<" nearest_centroid_max="<<maxDistance
                 <<" same_triangle_order="<<orderMatches<<"/"<<ntri
                 <<"\n";
    }
    std::cout<<"NOTE: equal triangle counts do not establish vertex correspondence or morph compatibility.\n";
}

void inspectPanelAnimationRecords(const Bytes& b) {
    const std::size_t dir=std::size_t(read32le(b,12))*16,n=read32le(b,4)>>5;
    if(dir>b.size()||n>(b.size()-dir)/16)throw std::runtime_error("bad article directory");
    // Compare known showroom-capable panels against competing rear-lid variants.
    for(std::size_t article: {std::size_t(13),std::size_t(28),std::size_t(6),
                               std::size_t(39),std::size_t(4),std::size_t(52),std::size_t(53)}) {
        if(article>=n)continue;
        const std::size_t at=dir+article*16;
        const std::size_t rel=read32le(b,at+12),len=read32le(b,at+8);
        if(rel>(b.size()-at)/16)throw std::runtime_error("bad article offset");
        const std::size_t begin=at+rel*16;
        if(len>(b.size()-begin)/16)throw std::runtime_error("bad article length");
        std::cout<<"Article "<<article<<" "<<articleName(b,article)<<"\n";
        for(std::size_t p=begin;p<begin+len*16;p+=16) {
            const std::string tag{char(b[p+2]),char(b[p+3])};
            if(tag!="aB"&&tag!="aN"&&tag!="mn"&&tag!="rt")continue;
            const unsigned info=unsigned(b[p])|(unsigned(b[p+1])<<8);
            const std::size_t bytes=read32le(b,p+4)>>8,relative=read32le(b,p+12);
            if(relative>b.size()-p||bytes>b.size()-p-relative) {
                std::cout<<"  "<<tag<<" info=0x"<<std::hex<<info<<std::dec<<" BAD RANGE\n";
                continue;
            }
            const std::size_t start=p+relative;
            std::cout<<"  "<<tag<<" info=0x"<<std::hex<<info<<std::dec
                     <<" length="<<bytes;
            if(tag=="aB"&&bytes>=100) {
                const std::size_t i=start+68;
                std::cout<<" flags="<<read32le(b,start)
                         <<" geomIndex="<<unsigned(b[i])
                         <<" typeIndex="<<unsigned(b[i+1])
                         <<" geomType="<<unsigned(b[i+7])
                         <<" animCount="<<unsigned(b[i+8])
                         <<" animType="<<unsigned(b[i+9]);
                std::cout<<" baseInfoRemaining=";
                for(std::size_t k=0;k<32&&i+k<start+bytes;++k) {
                    if(k)std::cout<<" ";
                    std::cout<<std::hex<<std::setfill('0')<<std::setw(2)<<unsigned(b[i+k])<<std::dec;
                }
                std::cout<<std::setfill(' ');
                if(bytes>100){
                    std::cout<<" trailingBaseBytes="<<(bytes-100)<<" trailingPrefix=";
                    for(std::size_t k=100;k<std::min<std::size_t>(bytes,124);++k) {
                        if(k!=100)std::cout<<" ";
                        std::cout<<std::hex<<std::setfill('0')<<std::setw(2)<<unsigned(b[start+k])<<std::dec;
                    }
                    std::cout<<std::setfill(' ');
                }
            }
            if(tag=="rt"&&bytes>=64){
                auto rd=[&](int k){const auto bits=read32le(b,start+4*k);float x;std::memcpy(&x,&bits,4);return x;};
                std::cout<<" translation=("<<rd(12)<<","<<rd(13)<<","<<rd(14)<<")";
                std::cout<<" basis3x3=[";
                for(int row=0;row<3;++row){
                    if(row)std::cout<<";";
                    for(int col=0;col<3;++col){
                        if(col)std::cout<<",";
                        std::cout<<rd(row*4+col);
                    }
                }
                std::cout<<"]";
            }
            if(tag=="aN"||tag=="mn") {
                std::cout<<" prefix=";
                for(std::size_t k=0;k<std::min<std::size_t>(bytes,32);++k){
                    if(k)std::cout<<" ";
                    std::cout<<std::hex<<std::setfill('0')<<std::setw(2)<<unsigned(b[start+k])<<std::dec;
                }
                std::cout<<std::setfill(' ');
            }
            std::cout<<"\n";
        }
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
                  << " levelCandidate=" << ((info >> 12) & 0xFu)
                  << " partGroupCandidate=" << ((info >> 12) & 0xFu)
                  << " subindexCandidate=" << (info & 0xFu)
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
                if (streamSafe && infoCount <= 8) {
                    for (std::size_t row = 0; row < infoCount; ++row) {
                        const std::size_t q = base + 48 + row * 16;
                        const auto rmOffset = read32le(b, q);
                        const auto byteOffset = read32le(b, q+4);
                        const unsigned byteLength = unsigned(b[q+8]) | (unsigned(b[q+9]) << 8);
                        const unsigned id = unsigned(b[q+10]) | (unsigned(b[q+11]) << 8);
                        const unsigned level = unsigned(b[q+12]) | (unsigned(b[q+13]) << 8);
                        const unsigned ref = unsigned(b[q+14]) | (unsigned(b[q+15]) << 8);
                        if (found <= 8)
                            std::cout << "    info[" << row << "] id=" << id
                                      << " level=" << level << " indexRef=" << ref
                                      << " byteOffset=" << byteOffset
                                      << " byteLength=" << byteLength
                                      << " rmOffset=" << rmOffset << "\n";
                    }
                }
                if (streamSafe && indexCount >= 1 && entryCount >= 3) {
                    const std::size_t indexData = base + streamStart;
                    std::uint8_t maximum = 0, minimum = 255;
                    for (std::size_t j = 0; j < entryCount; ++j) {
                        maximum = std::max(maximum, b[indexData+j]);
                        minimum = std::min(minimum, b[indexData+j]);
                    }
                    std::cout << "  Vertex index range: " << unsigned(minimum)
                              << ".." << unsigned(maximum)
                              << " sample triangles:";
                    for (std::size_t j = 0; j+2 < std::min<std::size_t>(entryCount, 9); j+=3)
                        std::cout << " (" << unsigned(b[indexData+j]) << ","
                                  << unsigned(b[indexData+j+1]) << ","
                                  << unsigned(b[indexData+j+2]) << ")";
                    std::cout << "\n";
                }
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
    if (argc != 2 && !(argc == 5 && (std::string(argv[2]) == "--article-mesh" || std::string(argv[2]) == "--wheel-uv-mesh" || std::string(argv[2]) == "--article-uv-mesh" || (std::string(argv[2]) == "--article-normal-mesh" || std::string(argv[2]) == "--article-normal-mesh-reversed"))) && !(argc == 3 && (std::string(argv[2]) == "--parts" || std::string(argv[2]) == "--wheel-placement" || std::string(argv[2]) == "--component-metadata" || std::string(argv[2]) == "--surface-descriptors" || std::string(argv[2]) == "--triangle-attribute-samples" || std::string(argv[2]) == "--attribute-layout" || std::string(argv[2]) == "--wheel-reference-map" || std::string(argv[2]) == "--wheel-stream-samples" || std::string(argv[2]) == "--wheel-index-streams" || std::string(argv[2]) == "--crp-textures" || std::string(argv[2]) == "--body-normal-alignment" || std::string(argv[2]) == "--glass-light-uv" || std::string(argv[2]) == "--glass-light-material-refs" || std::string(argv[2]) == "--material-candidate-distribution" || std::string(argv[2]) == "--material-record-comparison" || std::string(argv[2]) == "--material-word-candidates" || std::string(argv[2]) == "--rear-lid-compare" || std::string(argv[2]) == "--rear-mesh-groups" || std::string(argv[2]) == "--spoiler-mesh-groups" || std::string(argv[2]) == "--spoiler-topology" || std::string(argv[2]) == "--panel-animation-records")) && !(argc == 4 && (std::string(argv[2]) == "--extract-fsh" || std::string(argv[2]) == "--assembly-metadata" || std::string(argv[2]) == "--transforms" || std::string(argv[2]) == "--batch-mesh" || std::string(argv[2]) == "--body-mesh" || std::string(argv[2]) == "--polygons" || std::string(argv[2]) == "--dump" || std::string(argv[2]) == "--vertices" || std::string(argv[2]) == "--vertices-level0")) ) {
        std::cerr << "Usage: nfs5-inspector <path-to-crp> [--dump <new-output-file> | --vertices <new-obj-file> | --vertices-level0 <new-obj-file> | --body-mesh <new-obj-file> | --article-mesh <index> <new-obj-file> | --wheel-uv-mesh <46|47> <new-obj-file> | --article-uv-mesh <17|18|32|36> <new-obj-file> | --article-normal-mesh <index> <new-obj-file> | --article-normal-mesh-reversed <index> <new-obj-file> | --batch-mesh <new-directory> | --assembly-metadata <new-csv-file> | --wheel-placement | --component-metadata | --surface-descriptors | --triangle-attribute-samples | --attribute-layout | --wheel-reference-map | --wheel-stream-samples | --wheel-index-streams | --crp-textures | --body-normal-alignment | --glass-light-uv | --glass-light-material-refs | --material-candidate-distribution | --material-record-comparison | --material-word-candidates | --extract-fsh <new-directory> | --rear-lid-compare | --rear-mesh-groups | --spoiler-mesh-groups | --spoiler-topology | --panel-animation-records | --transforms <article-index> | --polygons <article-index>] | --self-test\n";
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
        if (argc == 3 && std::string(argv[2]) == "--wheel-placement") inspectWheelPlacement(output);
        if (argc == 3 && std::string(argv[2]) == "--component-metadata") inspectComponentMetadata(output);
        if (argc == 3 && std::string(argv[2]) == "--surface-descriptors") inspectSurfaceDescriptors(output);
        if (argc == 3 && std::string(argv[2]) == "--triangle-attribute-samples") inspectTriangleAttributeSamples(output);
        if (argc == 3 && std::string(argv[2]) == "--attribute-layout") inspectAttributeLayout(output);
        if (argc == 3 && std::string(argv[2]) == "--wheel-reference-map") inspectWheelReferences(output);
        if (argc == 3 && std::string(argv[2]) == "--wheel-stream-samples") inspectWheelStreamSamples(output);
        if (argc == 3 && std::string(argv[2]) == "--wheel-index-streams") inspectWheelIndexStreams(output);
        if (argc == 3 && std::string(argv[2]) == "--crp-textures") inspectCrpTextures(output);
        if (argc == 3 && std::string(argv[2]) == "--body-normal-alignment") inspectBodyNormalAlignment(output);
        if (argc == 3 && std::string(argv[2]) == "--glass-light-uv") inspectGlassLightUv(output);
        if (argc == 3 && std::string(argv[2]) == "--glass-light-material-refs") inspectGlassLightMaterialRefs(output);
        if (argc == 3 && std::string(argv[2]) == "--material-candidate-distribution") inspectMaterialCandidateDistribution(output);
        if (argc == 3 && std::string(argv[2]) == "--material-record-comparison") inspectMaterialRecordComparison(output);
        if (argc == 3 && std::string(argv[2]) == "--material-word-candidates") inspectMaterialWordCandidates(output);
        if (argc == 4 && std::string(argv[2]) == "--extract-fsh") exportEmbeddedFsh(output, std::filesystem::path(argv[3]));
        if (argc == 3 && std::string(argv[2]) == "--rear-lid-compare") compareRearLids(output);
        if (argc == 3 && std::string(argv[2]) == "--rear-mesh-groups") inspectRearMeshGroups(output);
        if (argc == 3 && std::string(argv[2]) == "--spoiler-mesh-groups") inspectRearMeshGroups(output, true);
        if (argc == 3 && std::string(argv[2]) == "--spoiler-topology") inspectSpoilerTopology(output);
        if (argc == 3 && std::string(argv[2]) == "--panel-animation-records") inspectPanelAnimationRecords(output);
        if (argc == 4 && std::string(argv[2]) == "--body-mesh")
            exportBodyMesh(output, std::filesystem::path(argv[3]));
        if (argc == 5 && (std::string(argv[2]) == "--article-mesh" || std::string(argv[2]) == "--wheel-uv-mesh" || std::string(argv[2]) == "--article-uv-mesh" || (std::string(argv[2]) == "--article-normal-mesh" || std::string(argv[2]) == "--article-normal-mesh-reversed"))) {
            const std::string value(argv[3]);
            std::size_t consumed = 0;
            const auto index = std::stoull(value, &consumed, 10);
            if (consumed != value.size()) throw std::runtime_error("invalid article index");
            exportArticleMesh(output, static_cast<std::size_t>(index), std::filesystem::path(argv[4]), (std::string(argv[2])=="--wheel-uv-mesh" || std::string(argv[2])=="--article-uv-mesh"), (std::string(argv[2])=="--article-normal-mesh" || std::string(argv[2])=="--article-normal-mesh-reversed"), std::string(argv[2])=="--article-normal-mesh-reversed", std::string(argv[2])=="--article-uv-mesh");
        }
        if (argc == 4 && std::string(argv[2]) == "--polygons") {
            const std::string arg(argv[3]);
            std::size_t consumed = 0;
            const auto idx = std::stoull(arg, &consumed, 10);
            if (consumed != arg.size()) throw std::runtime_error("invalid article index");
            inspectPolygons(output, static_cast<std::size_t>(idx));
        }
        if (argc == 4 && (std::string(argv[2]) == "--vertices" || std::string(argv[2]) == "--vertices-level0"))
            exportVertices(output, std::filesystem::path(argv[3]), std::string(argv[2]) == "--vertices-level0");
        if (argc == 4 && std::string(argv[2]) == "--assembly-metadata")
            exportAssemblyMetadata(output,std::filesystem::path(argv[3]));
        if (argc == 4 && std::string(argv[2]) == "--batch-mesh")
            exportBatch(output, std::filesystem::path(argv[3]));
        if (argc == 4 && std::string(argv[2]) == "--transforms") {
            const std::string value(argv[3]);
            std::size_t consumed=0;
            const auto idx=std::stoull(value,&consumed,10);
            if(consumed!=value.size()||idx>SIZE_MAX) throw std::runtime_error("invalid article index");
            inspectTransforms(output,static_cast<std::size_t>(idx));
        }
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
