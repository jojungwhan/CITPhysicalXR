# Third-Party Notices

This file covers the Milestone 0 development workspace. It is an inventory aid, not a replacement for each dependency's licence text. Exact resolved versions and transitive components are recorded in `pnpm-lock.yaml`, `uv.lock`, and the generated CycloneDX SBOM.

## Licence families accepted by the automated gate

The current resolved dependency graph contains software under `Apache-2.0`, `MIT`, `BSD-2-Clause`, `BSD-3-Clause`, `ISC`, `MPL-2.0`, `PSF-2.0`, `Python-2.0`, and `BlueOak-1.0.0`. Dependency licence texts remain available in installed package distributions and their upstream source repositories.

## Direct JavaScript and TypeScript dependencies

| Component group                     | Purpose                          | Licence                                 |
| ----------------------------------- | -------------------------------- | --------------------------------------- |
| React and React DOM                 | Studio scaffold rendering        | `MIT`                                   |
| Vite and `@vitejs/plugin-react`     | Studio build                     | `MIT`                                   |
| Ajv and ajv-formats                 | JSON Schema validation           | `MIT`                                   |
| TypeScript                          | Type generation and compilation  | `Apache-2.0`                            |
| ESLint, typescript-eslint, Prettier | Static analysis and formatting   | `MIT` / `Apache-2.0` transitive helpers |
| Vitest                              | TypeScript tests                 | `MIT`                                   |
| Blockly                             | Block editor                     | `Apache-2.0`                            |
| Pyodide                             | Browser student Python runtime   | `MPL-2.0`                               |
| json-schema-to-typescript           | Protocol model generation        | `MIT`                                   |
| yaml                                | Configuration validation tooling | `ISC`                                   |

## Direct Python dependencies

| Component group           | Purpose                            | Licence                |
| ------------------------- | ---------------------------------- | ---------------------- |
| Pydantic                  | Generated protocol models          | `MIT`                  |
| jsonschema                | Runtime/configuration validation   | `MIT`                  |
| PyYAML                    | Safe YAML loading                  | `MIT`                  |
| datamodel-code-generator  | Python protocol generation         | `MIT`                  |
| pytest and pytest-asyncio | Contract and safety tests          | `MIT` / `Apache-2.0`   |
| Ruff                      | Lint and format checks             | `MIT`                  |
| mypy and types-PyYAML     | Type checking                      | `MIT` / `Apache-2.0`   |
| Hatchling and build       | Python package builds              | `MIT`                  |
| FastAPI and Starlette     | Local runtime API                  | `MIT` / `BSD-3-Clause` |
| uvicorn and websockets    | Local runtime transport            | `BSD-3-Clause`         |
| TinyTuya                  | Local Tuya-compatible LAN control  | `MIT`                  |
| Requests                  | TinyTuya HTTP support (transitive) | `Apache-2.0`           |

## Optional hardware dependencies

`adapters/lego-pybricks` declares an optional `hardware` extra. It is not installed by default, is not required to build, test, or run this repository, and is needed only on a machine that will connect to a LEGO hub over Bluetooth.

| Component                      | Purpose                                               | Licence                                                             |
| ------------------------------ | ----------------------------------------------------- | ------------------------------------------------------------------- |
| `pybricksdev`                  | Pybricks BLE protocol, program compile and download   | `MIT`                                                               |
| `bleak`                        | Cross-platform Bluetooth Low Energy (via pybricksdev) | `MIT`                                                               |
| `asyncssh`                     | Transitive: pybricksdev's ev3dev support              | `EPL-2.0 OR GPL-2.0-or-later` — **not allowlisted**                 |
| `cffi`                         | Transitive                                            | `MIT-0` — **not allowlisted**                                       |
| `mpy-cross-v5`, `mpy-cross-v6` | Transitive: MicroPython compilers                     | no licence metadata published — **not allowlisted**                 |
| `aioserial`, `tqdm`            | Transitive                                            | `MPL-2.0`, `MPL-2.0 AND MIT` (allowed; metadata does not normalize) |

Installing the extra therefore makes `pnpm license:check` fail on that machine. This is recorded, not resolved: see ADR-023 in `docs/DECISIONS.md`. No LEGO hardware work should proceed until the owner decides which way it goes.

`adapters/tuya-smart-plug` similarly declares a `lan` extra, selected from the
root as `smart-plug-lan`. TinyTuya is `MIT`, but its installed cryptography stack
includes `cffi` with `MIT-0`, which is outside the current default allowlist.
The simulator and default CI do not install this extra. A hardware host may use
the explicitly locked extra, must record that exception, and can restore the
default environment with `uv sync --all-packages --frozen`.

LEGO hardware, the Pybricks firmware installed on a hub, and the Pybricks Code web installer are not distributed by this repository.

## Generated files

`packages/protocol-ts/src/generated` and `packages/protocol-py/src/cit_protocol/generated.py` are generated from the repository's original JSON Schema. Generator dependencies are tooling only; generated output remains part of this Apache-2.0 project to the extent permitted by those tools.

## Audited external repositories and runtimes

The Agent CLI Mesh, RoboMaster gesture-control, and classroom RoboMaster repositories listed in `docs/REUSE_AUDIT.md` are external checkouts. Their original code is not copied, linked, packaged, or relicensed here. At the audited revisions, each lacks a top-level owner licence and is recorded as `owner-private-unlicensed`; any later reuse requires explicit compatible licensing and a new provenance entry.

The DJI RoboMaster SDK/runtime, Ultraleap runtime, Godot/OpenXR tooling, Meta/Quest tooling, Pybricks firmware/runtime, and smart-glasses SDKs are not distributed by Milestone 0. Future milestones must add their exact versions, source, and licence terms before distribution.
