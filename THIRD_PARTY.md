# Third-Party Notices

This repository contains modified source code derived from `dsh-remembers` / `companion-memory`.

## dsh-remembers / companion-memory

- Copyright (c) 2026 derkinL
- License: MIT
- Included in this repository at:
  - `plugins/dsh-remembers/` — DSH plugin source
  - `service/` — companion-memory service source
- License copy:
  - `plugins/dsh-remembers/LICENSE`
  - `service/LICENSE`

This project has modified the upstream code, including but not limited to:

- moving recall and L0 write policy behind `/hook/pre-step` and `/hook/turn-end`
- splitting the plugin into `app.mjs`, `hooks/`, `tools/`
- first-person memory policy, prefix stripping, batch L1/L3/L4 handling
- persona storage/context formatting and `/persona/*` routes
- service route modules under `api/routes/`
- local path/config handling

The original MIT copyright notice is preserved. Files that were changed remain under the MIT license.

## dsh-bili-scroll

- License: MIT
- Upstream: `https://github.com/c1overzz/dsh-bili-scroll`
- Not bundled in this repository; used as an external DSH plugin/tool dependency.

## SnowLuma

- License: see upstream `EULA.md` / package metadata
- Not bundled in this repository. Install and use it separately under its own terms.

## DSH (DeepSeek Harness)

- Proprietary host runtime; not bundled in this repository.
- Install it separately and follow its license/terms.

## Models and APIs

- DeepSeek / SiliconFlow API keys are not included.
- Model outputs and generated persona text are not included as data.

## Character images / stickers

- `stickers/` and other image assets are not included in the public repository.
- Do not add third-party character art or meme images without permission.
