# NFS5 CRP inspector

A read-only standalone tool for NFS5 PC CRP files. It supports the `10 FB` compressed wrapper using bounded LZ77-style decompression derived from the legacy LibOpenNFS algorithm. No proprietary files are written.

Reports input/decompressed sizes, header identifier, candidate article count, miscellaneous count, and article-table-offset field. **Does not** yet parse geometry or validate complete CRP table structure.

From the repository root:

```bash
git pull --ff-only origin feature/nfs5-prototype
cmake -S tools/nfs5-inspector -B build/nfs5-inspector -G Ninja
cmake --build build/nfs5-inspector
./build/nfs5-inspector/nfs5-inspector --self-test
./build/nfs5-inspector/nfs5-inspector resources/NFS_5/gamedata/CarModel/993.crp
```

Both compressed and decompressed buffers are limited to 64 MiB. Keep all original EA files outside Git. Next: validate the CRP article table and extract mesh metadata.
