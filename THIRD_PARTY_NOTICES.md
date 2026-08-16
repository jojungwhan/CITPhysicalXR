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

| Component group           | Purpose                          | Licence                |
| ------------------------- | -------------------------------- | ---------------------- |
| Pydantic                  | Generated protocol models        | `MIT`                  |
| jsonschema                | Runtime/configuration validation | `MIT`                  |
| PyYAML                    | Safe YAML loading                | `MIT`                  |
| datamodel-code-generator  | Python protocol generation       | `MIT`                  |
| pytest and pytest-asyncio | Contract and safety tests        | `MIT` / `Apache-2.0`   |
| Ruff                      | Lint and format checks           | `MIT`                  |
| mypy and types-PyYAML     | Type checking                    | `MIT` / `Apache-2.0`   |
| Hatchling and build       | Python package builds            | `MIT`                  |
| FastAPI and Starlette     | Local runtime API                | `MIT` / `BSD-3-Clause` |
| uvicorn and websockets    | Local runtime transport          | `BSD-3-Clause`         |

## Generated files

`packages/protocol-ts/src/generated` and `packages/protocol-py/src/cit_protocol/generated.py` are generated from the repository's original JSON Schema. Generator dependencies are tooling only; generated output remains part of this Apache-2.0 project to the extent permitted by those tools.

## Audited external repositories and runtimes

The Agent CLI Mesh, RoboMaster gesture-control, and classroom RoboMaster repositories listed in `docs/REUSE_AUDIT.md` are external checkouts. Their original code is not copied, linked, packaged, or relicensed here. At the audited revisions, each lacks a top-level owner licence and is recorded as `owner-private-unlicensed`; any later reuse requires explicit compatible licensing and a new provenance entry.

The DJI RoboMaster SDK/runtime, Ultraleap runtime, Godot/OpenXR tooling, Meta/Quest tooling, Pybricks firmware/runtime, and smart-glasses SDKs are not distributed by Milestone 0. Future milestones must add their exact versions, source, and licence terms before distribution.
