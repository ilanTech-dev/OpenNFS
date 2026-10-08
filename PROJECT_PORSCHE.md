# Project Porsche — NFS5 prototype

## Goal

Build a native Linux proof-of-concept for **Need for Speed: Porsche Unleashed (NFS5 PC)** on top of OpenNFS, using game data supplied locally by the owner. The initial prototype should render one original Porsche and one original track and permit basic free driving.

This is an experimental fork of [OpenNFS](https://github.com/OpenNFS/OpenNFS), not an official release or redistribution of the game.

## Initial milestones

1. **Build baseline:** Compile the fork and submodules on Linux Mint; document exact compiler, CMake, dependencies and runtime errors.
2. **Inspect NFS5 parsers:** Identify vehicle, track and texture code paths in LibOpenNFS; record unsupported formats and test fixtures.
3. **Asset inspection tool:** Read selected NFS5 game files and report validated header/geometry/material data and actionable parse errors, without rendering.
4. **First render:** Display one textured Porsche model and one original track in the existing OpenNFS renderer.
5. **Free drive:** Add controllable vehicle, collision, chase camera and frame-time diagnostics.

## Engineering principles

- Retain the original OpenNFS engine architecture at first; defer renderer/physics rewrites until there is evidence they are needed.
- Keep changes narrowly scoped and reviewable, preferably on the `feature/nfs5-prototype` branch.
- Use deterministic, small parser tests that handle malformed files safely.
- Do not commit proprietary NFS3/NFS5 game files, extracted artwork, music or other EA assets.
- Document how owners can configure paths to their own locally installed game data.
- Aim first for a playable proof of concept, **not** full parity with Evolution or Factory Driver mode.

## Next action

Build the current fork on Katana, confirm NFS3 runtime asset paths, and inventory the NFS5 parser code before choosing the first Porsche/track fixtures.

## Upstream

- Engine: https://github.com/OpenNFS/OpenNFS
- Parsers: https://github.com/OpenNFS/LibOpenNFS
