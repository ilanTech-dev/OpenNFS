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

## Vertex-only OBJ probe

After building, export a point-cloud OBJ outside this repository:

```bash
mkdir -p /tmp/project-porsche
./build/nfs5-inspector/nfs5-inspector resources/NFS_5/gamedata/CarModel/993.crp --vertices /tmp/project-porsche/993-vertices.obj
```

This writes every valid `tv` payload as OBJ `v` vertices and `p` point primitives, grouped by article and descriptor. **No faces, normals, UVs, per-part transforms or LOD filtering** are applied yet. Expect overlapping/duplicate geometry and potentially a confusing shape in Blender. The exporter refuses a pre-existing output path; delete the prior local test file before rerunning. It is an early diagnostic, not a finished 3D model. Do not commit extracted assets.
