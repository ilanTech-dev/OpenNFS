#include <algorithm>
#include <cctype>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <iterator>
#include <string>
#include <vector>

int main(int argc, char* argv[]) {
    if (argc != 2) {
        std::cerr << "Usage: nfs5-inspector <path-to-crp>\n";
        return 2;
    }

    const std::filesystem::path path(argv[1]);
    std::error_code ec;
    const auto length = std::filesystem::file_size(path, ec);
    if (ec) {
        std::cerr << "Cannot stat file: " << ec.message() << "\n";
        return 1;
    }
    constexpr std::uintmax_t maxBytes = 64ULL * 1024 * 1024;
    if (length > maxBytes) {
        std::cerr << "File too large for prototype inspector (64 MiB limit)\n";
        return 1;
    }
    std::ifstream input(path, std::ios::binary);
    if (!input) {
        std::cerr << "Cannot open file\n";
        return 1;
    }
    std::vector<unsigned char> bytes((std::istreambuf_iterator<char>(input)),
                                      std::istreambuf_iterator<char>());
    if (input.bad() || bytes.size() != length) {
        std::cerr << "Error reading file\n";
        return 1;
    }

    std::cout << "NFS5 CRP Inspector (read-only)\n"
              << "Path: " << path << "\n"
              << "Size: " << bytes.size() << " bytes\n"
              << "First bytes:";
    for (std::size_t i = 0; i < std::min<std::size_t>(32, bytes.size()); ++i) {
        std::cout << ' ' << std::hex << std::setfill('0')
                  << std::setw(2) << static_cast<unsigned>(bytes[i]);
    }
    std::cout << std::dec << "\n";

    // Search for candidate format markers. Occurrence alone is not proof
    // of an uncompressed CRP container or a valid article.
    const std::vector<std::string> markers{"Car ", " raC", "Arti", "itrA", "Trak", "karT"};
    for (const auto& marker : markers) {
        std::size_t count = 0;
        std::cout << "Marker '" << marker << "' offsets:";
        for (std::size_t i = 0; i + marker.size() <= bytes.size(); ++i) {
            bool match = true;
            for (std::size_t j = 0; j < marker.size(); ++j) {
                if (bytes[i + j] != static_cast<unsigned char>(marker[j])) {
                    match = false;
                    break;
                }
            }
            if (match) {
                if (count < 8) std::cout << " 0x" << std::hex << i << std::dec;
                ++count;
            }
        }
        std::cout << " (count " << count << ")\n";
    }
    return 0;
}
