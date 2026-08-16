# Compatibility Matrix

Status date: 2026-08-16

## Foundation toolchain

| Component | Pinned/test target  | Windows discovery host | Ubuntu CI                                     | Notes                       |
| --------- | ------------------- | ---------------------- | --------------------------------------------- | --------------------------- |
| Node.js   | 22.17.0             | Passed                 | Ubuntu 24.04 container passed                 | Exact CI pin                |
| pnpm      | 10.28.2             | Passed                 | Ubuntu 24.04 container passed                 | Exact package-manager pin   |
| uv        | 0.4.30              | Passed                 | Ubuntu 24.04 container passed                 | Exact action input          |
| CPython   | 3.11 and 3.13       | Managed 3.13.0 passed  | Container 3.13.0 passed; CI targets 3.11/3.13 | Hardware Python is separate |
| Godot     | unresolved until M5 | Not installed          | Static text check only                        | No OpenXR/export claim      |

## External reuse checkouts

| Asset                             | Windows evidence                                            | Linux path | Revision/version                           | M0 status                                            |
| --------------------------------- | ----------------------------------------------------------- | ---------- | ------------------------------------------ | ---------------------------------------------------- |
| Agent CLI Mesh                    | `D:\dev\glasses2CLI`                                        | Unresolved | `79983dfadc378566168343e57814a046089c2047` | Audited read-only; owner-private-unlicensed          |
| RoboMaster gesture/Leap reference | `D:\dev\robomaster-gesture-control-reference`               | Unresolved | `e5a94865451dc8a9a266bb9223f8ed090ac11681` | Audited read-only; expected built DLL/runtime absent |
| RoboMaster classroom checkout     | `D:\dev\robomasterCITCourse`                                | Unresolved | `2f54bc7f2de6925b1e388632c45cb4dd7296d660` | Clean read-only checkout                             |
| DJI Python environment            | `D:\dev\robomasterCITCourse\.venv-robot\Scripts\python.exe` | Unresolved | Python 3.8.10, `robomaster` 0.1.1.68       | Detected; not executed against hardware or modified  |

## Hardware targets

| Target                                 | Planned milestone                   | M0 evidence                                                                                                      |
| -------------------------------------- | ----------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| RoboMaster S1                          | M2                                  | Fake contract only; no connection                                                                                |
| Ultraleap/Leap Motion                  | M2                                  | Fake contract only; local runtime/service and bridge DLL unresolved                                              |
| LEGO SPIKE / Robot Inventor            | M4                                  | Adapter, hub agent, and protocol built and tested against a simulated hub; no BLE, no hub, no firmware installed |
| Quest 2 baseline / Quest 3 enhancement | M5                                  | Godot text scaffold only; no SDK, APK, or device test                                                            |
| Even G2 / Meta glasses                 | M7 through existing Agent Mesh apps | Reuse audit and policy scaffold only                                                                             |

On 2026-08-16, an ephemeral `ubuntu:24.04` container copied a read-only source mount into a clean filesystem and passed locked installation, generation drift, schemas, Quest structure, secret scan, formatting, lint, strict type checks, TypeScript builds, 70 tests, licence checks, SBOM generation, and all five Python package builds. No device was passed into the container. This is Linux software evidence, not hardware evidence. GitHub Actions remains unreported until the repository is pushed.

## LEGO hubs (Milestone 4)

Every row is a _declared_ requirement. No hub was connected: the development host has no Bluetooth adapter (`/sys/class/bluetooth/` is empty), so none of this is hardware evidence.

| Hub                            | Model id          | Ports | Pybricks class | Minimum firmware | Minimum BLE profile | Status                                     |
| ------------------------------ | ----------------- | ----- | -------------- | ---------------- | ------------------- | ------------------------------------------ |
| LEGO SPIKE Prime Hub           | `spike-prime`     | A–F   | `PrimeHub`     | 3.3.0            | 1.2.0               | Adapter written; untested against hardware |
| LEGO SPIKE Essential Hub       | `spike-essential` | A–B   | `EssentialHub` | 3.3.0            | 1.2.0               | Adapter written; untested against hardware |
| LEGO MINDSTORMS Robot Inventor | `robot-inventor`  | A–F   | `InventorHub`  | 3.3.0            | 1.2.0               | Same Pybricks path as SPIKE Prime (FR-054) |

Recent SPIKE Prime and Robot Inventor hubs use the STM32H5 microcontroller and need the Pybricks 4.1 beta build. Read the hub revision before installing firmware (`docs/LEGO_SETUP.md`).

Host-side software evidence on 2026-08-16, Ubuntu (Linux 7.0.0-29-generic), CPython 3.11.15, Node 22.22.1, pnpm 10.28.2: all eleven repository gates pass with 313 Python and 78 TypeScript tests, and the block-to-hub path was driven in Chromium against a runtime whose LEGO device is the real adapter over an in-memory hub. That is software evidence. It is not evidence that a motor turned.
