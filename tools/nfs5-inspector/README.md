# NFS5 CRP inspector (initial probe)

This standalone read-only diagnostic utility prints file size, a short hex prefix and offsets/counts of possible CRP container markers. It does **not** decompress CRP files, validate the file format, extract textures or parse geometry. A marker occurrence does not necessarily establish a valid header.

Build independently from the main engine:

```bash
cmake -S tools/nfs5-inspector -B build/nfs5-inspector -G Ninja
cmake --build build/nfs5-inspector
```

From the OpenNFS repository root, run against **your own** installation:

```bash
./build/nfs5-inspector/nfs5-inspector resources/NFS_5/gamedata/CarModel/993.crp
```

No proprietary assets should be committed or uploaded. The tool limits input files to 64 MiB. Future work: inspect the CRP compression wrapper, safely decode the inner container, then expose geometry counts.
