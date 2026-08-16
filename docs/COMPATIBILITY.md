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

| Target                                 | Planned milestone                   | M0 evidence                                                         |
| -------------------------------------- | ----------------------------------- | ------------------------------------------------------------------- |
| RoboMaster S1                          | M2                                  | Fake contract only; no connection                                   |
| Ultraleap/Leap Motion                  | M2                                  | Fake contract only; local runtime/service and bridge DLL unresolved |
| LEGO SPIKE / Robot Inventor            | M4                                  | Fake contract only; no BLE/firmware work                            |
| Quest 2 baseline / Quest 3 enhancement | M5                                  | Godot text scaffold only; no SDK, APK, or device test               |
| Even G2 / Meta glasses                 | M7 through existing Agent Mesh apps | Reuse audit and policy scaffold only                                |

On 2026-08-16, an ephemeral `ubuntu:24.04` container copied a read-only source mount into a clean filesystem and passed locked installation, generation drift, schemas, Quest structure, secret scan, formatting, lint, strict type checks, TypeScript builds, 70 tests, licence checks, SBOM generation, and all five Python package builds. No device was passed into the container. This is Linux software evidence, not hardware evidence. GitHub Actions remains unreported until the repository is pushed.
