# Third-Party Notices

This file covers the Milestone 0 development workspace. It is an inventory aid, not a replacement for each dependency's licence text. Exact resolved versions and transitive components are recorded in `pnpm-lock.yaml`, `uv.lock`, and the generated CycloneDX SBOM.

## Licence families accepted by the automated gate

The default resolved dependency graph contains software under `Apache-2.0`, `MIT`, `BSD-2-Clause`, `BSD-3-Clause`, `ISC`, `MPL-2.0`, `PSF-2.0`, `Python-2.0`, and `BlueOak-1.0.0`. Dependency licence texts remain available in installed package distributions and their upstream source repositories.

## Direct JavaScript and TypeScript dependencies

| Component group                     | Purpose                           | Licence                                 |
| ----------------------------------- | --------------------------------- | --------------------------------------- |
| React and React DOM                 | Studio scaffold rendering         | `MIT`                                   |
| Vite and `@vitejs/plugin-react`     | Studio build                      | `MIT`                                   |
| Ajv and ajv-formats                 | JSON Schema validation            | `MIT`                                   |
| TypeScript                          | Type generation and compilation   | `Apache-2.0`                            |
| ESLint, typescript-eslint, Prettier | Static analysis and formatting    | `MIT` / `Apache-2.0` transitive helpers |
| Vitest                              | TypeScript tests                  | `MIT`                                   |
| Blockly                             | Block editor                      | `Apache-2.0`                            |
| Pyodide                             | Browser student Python runtime    | `MPL-2.0`                               |
| json-schema-to-typescript           | Protocol model generation         | `MIT`                                   |
| yaml                                | Configuration validation tooling  | `ISC`                                   |
| Open Home Foundation Matter Server  | Local Matter controller           | `Apache-2.0`                            |
| matter.js / Matter Server packages  | Matter protocol and WebSocket API | `Apache-2.0`                            |
| stoprocent noble/HCI modules        | Windows Matter BLE commissioning  | `MIT`                                   |

The Matter Bluetooth graph includes `@nornagon/put` 0.0.8. Its legacy package
metadata declares an object-valued `MIT/X11` licence and ships the complete MIT
text. The automated gate normalizes that exact legacy declaration to SPDX
`MIT`; it does not generally accept object-valued or unknown licence metadata.
Some pinned Open Home Foundation Matter packages omit the `license` field while
shipping an Apache License 2.0 file. For only the `matter-server`,
`@matter-server/*`, and `@matter/*` namespaces, the gate verifies that installed
licence text before normalizing it to `Apache-2.0`.
The same BLE graph includes `pause-stream` 0.0.11, whose legacy metadata lists
`MIT` and `Apache2` choices and whose shipped licence contains both texts. The
gate normalizes only that standard legacy `Apache2` spelling to `Apache-2.0`.
The transitive `jsonify` 0.0.1 package declares `Public Domain` in its installed
metadata and ships no separate licence file. The gate accepts that declaration
only for this exact pinned identity and records it here rather than pretending
it is an SPDX licence.

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
| matter-ble-proxy          | Local Windows Matter BLE proxy   | `Apache-2.0`           |
| aiohttp and multidict     | Transitive Matter BLE networking | `Apache-2.0` / `MIT`   |

The pinned Windows Matter BLE graph includes `aiohttp` 3.14.3, whose installed
metadata declares `Apache-2.0 AND MIT` and ships Apache-2.0 plus vendored
`llhttp` MIT texts, and `multidict` 6.7.1, whose metadata spells Apache-2.0 as
`Apache License 2.0`. The Python gate normalizes only these standard exact
metadata values; both resulting SPDX identifiers remain subject to the same
allowlist.

## Optional local vision runtime

The root `vision` extra installs Ultralytics for tutor-requested YOLO-World
inference. The resolved Ultralytics packages declare
`AGPL-3.0-or-later` or `AGPL-3.0-only`; they are not relicensed as Apache 2.0
and are loaded only when a tutor asks Classroom Control to recognize objects.
Its upstream source and licence are available from
<https://github.com/ultralytics/ultralytics>. Camera frames stay in the
runtime's replace-only memory slot and are not added to the semantic recorder.
Anyone distributing or offering a modified networked version must comply with
the applicable AGPL source-availability terms. A separate Ultralytics
enterprise licence may be required for deployments that do not use the AGPL
terms.

The locked inference stack also contains PyTorch, Torchvision, NumPy, Pillow,
Matplotlib, tqdm, and their bundled components. Their installed metadata and
licence files identify `Apache-2.0`, `BSD-2-Clause`, `BSD-3-Clause`, `MIT`,
`MPL-2.0`, `PSF-2.0`, `0BSD`, `BSL-1.0`, `CC0-1.0`, `CNRI-Python`,
`LLVM-exception`, `MIT-CMU`, and `Zlib`. These identifiers are allowlisted for
the optional local vision graph; the distribution's own licence files remain
authoritative.

## Optional hardware dependencies

`adapters/lego-pybricks`, `adapters/sphero-bolt`, and
`adapters/wonder-workshop` declare optional
`hardware` extras. They are not installed by default and are not required for
ordinary build, test, or simulation. The Dash/Dot extra adds only Bleak; its
small packet subset is implemented at the adapter boundary rather than pulling
an unofficial robot package into the runtime.

| Component                      | Purpose                                               | Licence                                                             |
| ------------------------------ | ----------------------------------------------------- | ------------------------------------------------------------------- |
| `pybricksdev`                  | Pybricks BLE protocol, program compile and download   | `MIT`                                                               |
| `bleak`                        | Cross-platform Bluetooth Low Energy (via pybricksdev) | `MIT`                                                               |
| `asyncssh`                     | Transitive: pybricksdev's ev3dev support              | `EPL-2.0 OR GPL-2.0-or-later` — **not allowlisted**                 |
| `cffi`                         | Transitive                                            | `MIT-0`                                                             |
| `mpy-cross-v5`, `mpy-cross-v6` | Transitive: MicroPython compilers                     | no licence metadata published — **not allowlisted**                 |
| `aioserial`, `tqdm`            | Transitive                                            | `MPL-2.0`, `MPL-2.0 AND MIT` (allowed; metadata does not normalize) |
| `bleak`                        | Direct optional Dash/Dot BLE transport                | `MIT`                                                               |
| `spherov2`                     | Optional Sphero BOLT command and sensor protocol      | `MIT`                                                               |
| `transforms3d`                 | Transitive spherov2 sensor transformation helper      | `BSD-3-Clause`                                                      |
| `numpy`                        | Transitive spherov2 numerical helper                  | `BSD-3-Clause`                                                      |

The Dash/Dot byte-level subset is adapted with attribution from
[`mewmix/bleak-dash`](https://github.com/mewmix/bleak-dash) at revision
`290f74e35a7c49206ba4bb8fa473708f9be85dc0`, whose notice applies Apache
License 2.0 to code adapted from `IlyaSukhanov/morseapi` and
`havnfun/python-dash-robot`. CIT does not install or redistribute that package;
the exact reference pin is maintained in `config/external-sources.yaml`.

The optional Sphero BOLT boundary uses `spherov2` 0.12.1, pinned to
[`artificial-intelligence-class/spherov2.py`](https://github.com/artificial-intelligence-class/spherov2.py)
revision `4252ddb1a12a25db725257d66e3e8ec3057dd48b` under the MIT licence.
It is reverse-engineered and not an official Sphero BOLT SDK. CIT supplies a
modern exact-device Bleak adapter around it and does not claim physical
firmware compatibility until the hardware checklist passes.

Installing the extra therefore makes `pnpm license:check` fail on that machine. This is recorded, not resolved: see ADR-023 in `docs/DECISIONS.md`. No LEGO hardware work should proceed until the owner decides which way it goes.

LEGO hardware, the Pybricks firmware installed on a hub, and the Pybricks Code web installer are not distributed by this repository.

The Windows business installer can create a separate Python environment for
the exact-pinned external Brain2Devices checkout. Its runtime graph includes
DJITelloPy, PyMindWave2, Flask/Waitress, NumPy, OpenCV, Pillow, and PyAV at the
versions in `config/brain2devices-windows-requirements.txt`. Those packages and
the Brain2Devices source do not become part of this repository's default Python
workspace or Apache-2.0 source. Their own installed metadata and licence texts
remain authoritative.

## Generated files

`packages/protocol-ts/src/generated` and `packages/protocol-py/src/cit_protocol/generated.py` are generated from the repository's original JSON Schema. Generator dependencies are tooling only; generated output remains part of this Apache-2.0 project to the extent permitted by those tools.

## Audited external repositories and runtimes

Brain2Devices, Agent CLI Mesh, RoboMaster gesture-control, and the classroom
RoboMaster repositories listed in `docs/REUSE_AUDIT.md` are external checkouts.
Their original code is not copied, packaged, or relicensed here. At the audited
revisions each lacks a top-level owner licence; CIT uses only explicit
external-process boundaries and records the exact source revision.

Unlike those unlicensed owner checkouts, the Dash/Dot protocol reference has
an explicit Apache-2.0 notice and is used only as an attributed protocol source.

The DJI RoboMaster SDK/runtime, Ultraleap runtime, Godot/OpenXR tooling, Meta/Quest tooling, Pybricks firmware/runtime, and smart-glasses SDKs are not distributed by Milestone 0. Future milestones must add their exact versions, source, and licence terms before distribution.
