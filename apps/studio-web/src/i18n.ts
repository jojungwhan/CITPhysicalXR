/**
 * Interface language (UI 11.5).
 *
 * Two rules shape this file. Technical identifiers stay stable across
 * languages: a device id, a capability, a session state, and an error code read
 * the same in Korean as in English, because they are what a student and an
 * instructor say to each other when something is wrong. And the catalogs are
 * one object each, so a missing key is a type error rather than a blank label
 * discovered by a Korean-speaking child in a lesson.
 *
 * The Korean is written as Korean, not translated phrase by phrase from the
 * English. The two catalogs say the same thing; they are not the same sentence.
 */

export type Locale = "en" | "ko";

export const LOCALES: readonly Locale[] = ["en", "ko"];

const EN = {
  "app.title": "CIT Physical XR Studio",
  "app.subtitle": "Runtime console",

  "nav.projects": "Projects",
  "nav.program": "Program",
  "nav.devices": "Devices",
  "nav.xr": "XR",
  "nav.simulation": "Simulation",
  "nav.instructor": "Instructor",
  "nav.logs": "Logs",
  "nav.settings": "Settings",

  "signin.heading": "Join the classroom",
  "signin.explain":
    "The runtime needs to know who you are before it will do anything. Nothing here leaves this machine.",
  "signin.name": "Your name",
  "signin.role": "Role",
  "signin.role.student": "Student",
  "signin.role.instructor": "Instructor",
  "signin.passcode": "Instructor passcode",
  "signin.passcodeHint":
    "The runtime prints it once when it starts. Ask whoever started it.",
  "signin.explainNetwork":
    "This runtime is reached over the network, so it asks who you are and for the classroom passcode. What you type stays on the machine running the classroom.",
  "signin.classPasscode": "Classroom passcode",
  "signin.classPasscodeHint":
    "This classroom is open over the network, so it asks for a passcode. Ask whoever is running the lesson.",
  "signin.submit": "Join",
  "signin.signedInAs": "Signed in as",
  "signin.leave": "Sign out",

  "safety.simulation": "SIMULATION",
  "safety.physicalDisarmed": "PHYSICAL · DISARMED",
  "safety.physicalArmed": "PHYSICAL · ARMED",
  "safety.emergencyStopped": "EMERGENCY STOPPED",
  "safety.simulationMeaning": "Nothing physical can move.",
  "safety.physicalDisarmedMeaning":
    "Real devices are connected. None may move until an instructor arms one.",
  "safety.physicalArmedMeaning":
    "A real device may move. Hold the dead-man control while it does.",
  "safety.emergencyStoppedMeaning":
    "Everything was stopped. Start a new session to continue.",

  "action.stopAll": "Stop all",
  "action.refresh": "Refresh",
  "action.retry": "Try again",

  "runtime.heading": "Runtime",
  "runtime.id": "Runtime",
  "runtime.protocol": "Protocol",
  "runtime.mode": "Mode",
  "runtime.physical": "Physical devices",
  "runtime.enabled": "enabled",
  "runtime.disabled": "disabled",
  "runtime.unreachable": "Not connected.",

  "session.heading": "Session",
  "session.new": "New session",
  "session.bind": "Bind selected device",
  "session.validate": "Validate",
  "session.none": "No session yet. A command needs one.",
  "session.mode": "Execution mode",
  "session.simulation": "Simulation",
  "session.physical": "Physical devices",
  "session.safetyProfile": "Safety profile",
  "session.instructorOnly":
    "Only an instructor can start a session that moves real devices.",
  "session.state": "state",
  "session.bound": "bound",
  "session.nothingBound": "none",

  "devices.heading": "Devices",
  "devices.none": "No devices discovered.",
  "devices.simulated": "simulated",
  "devices.physical": "physical",
  "devices.armed": "armed",
  "devices.battery": "Battery",
  "devices.adapter": "Adapter",
  "devices.firmware": "Firmware",
  "devices.lease": "Lease",
  "devices.student": "Student",
  "devices.lastCommand": "Last command",
  "devices.lastTelemetry": "Last telemetry",
  "devices.unknown": "not reported",
  "devices.free": "free",
  "devices.discover": "Discover devices",
  "devices.disconnect": "Disconnect",
  "devices.revokeLease": "Revoke lease",
  "devices.arm": "Arm this device",
  "devices.armed.by": "Armed by",
  "devices.disarm": "Disarm",
  "devices.stop": "Stop this device",

  "drive.heading": "Drive",
  "drive.blocked":
    "Start a session, bind a device, and validate before driving. The runtime refuses anything else regardless of what this page allows.",
  "drive.forward": "Forward",
  "drive.back": "Back",
  "drive.left": "Left",
  "drive.right": "Right",
  "drive.overspeed": "Try speed 9.9",
  "drive.holdDeadman": "Hold to enable movement",
  "drive.deadmanHeld": "Dead-man held",
  "drive.deadmanExplain":
    "Physical movement needs this held. Let go, or close this page, and the robot stops within 300 ms.",
  "drive.accepted": "Accepted",
  "drive.refused": "Refused",
  "drive.clamped": "clamped",

  "program.heading": "Program",
  "program.run": "Run",
  "program.stop": "Stop program",
  "program.convert": "Convert to Python",
  "program.export": "Export",
  "program.needsSession":
    "A program needs a session and at least one bound device before it can run.",
  "program.blocksSnapshot":
    "The blocks above are a retained snapshot. The Python below is what runs.",
  "program.converted":
    "This project is Python now. The blocks are kept as a snapshot, but the change is one way.",
  "program.generatedPython": "Generated Python",
  "program.python": "Python",
  "program.emptyProgram": "# add a block to begin",
  "program.console": "Console",
  "program.consoleEmpty": "Nothing printed yet.",
  "program.blockEditor": "Block editor",

  "projects.heading": "Projects",
  "projects.new": "New project",
  "projects.open": "Open",
  "projects.delete": "Delete",
  "projects.none": "No saved projects yet.",
  "projects.owner": "Owner",
  "projects.updated": "Updated",
  "projects.saved": "Saved.",
  "projects.saving": "Saving…",
  "projects.unsaved": "Unsaved changes",
  "projects.save": "Save",
  "projects.confirmDelete": "Delete this project? This cannot be undone.",
  "projects.notStored":
    "Not on the runtime yet. Save once, and your edits are saved from then on.",
  "projects.autosaveFailed":
    "Could not save. Your work is still here; press Save to try again.",

  "download.saved": "Saved as {name}",

  "xr.heading": "XR",
  "xr.notInThisMilestone":
    "The Quest client is Milestone 5 and is not built yet. Nothing here is simulated in its place, because a fake headset would tell you a Quest was working when none exists.",
  "xr.plannedHeading": "What lands here",
  "xr.plannedPairing": "Pairing with a Quest over the local network",
  "xr.plannedTelemetry": "Robot telemetry rendered in the headset",
  "xr.plannedDeadman": "The headset's dead-man control",

  "simulation.heading": "Simulation and replay",
  "simulation.recordings": "Recordings",
  "simulation.startRecording": "Start recording",
  "simulation.stopRecording": "Stop recording",
  "simulation.recording": "Recording…",
  "simulation.replay": "Replay",
  "simulation.exportPackage": "Export",
  "simulation.delete": "Delete",
  "simulation.none": "Nothing recorded yet.",
  "simulation.events": "{count} events",
  "simulation.neverMoves":
    "Replay publishes recorded events to this page. It cannot reach a device: there is no code path from a recording to a robot.",
  "simulation.replayed": "Replayed {count} events. Nothing moved.",

  "instructor.heading": "Instructor console",
  "instructor.people": "In the room",
  "instructor.sessions": "Sessions",
  "instructor.queueDepth": "Queued commands",
  "instructor.disabledSources": "Disabled inputs",
  "instructor.noneDisabled": "none",
  "instructor.disableLeap": "Disable Leap input",
  "instructor.enableLeap": "Enable Leap input",
  "instructor.disableQuest": "Disconnect Quest control",
  "instructor.enableQuest": "Reconnect Quest control",
  "instructor.clearQueue": "Clear command queues",
  "instructor.disarmClass": "Disarm the class",
  "instructor.failurePolicy": "If one device fails",
  "instructor.failureStop": "Stop the others",
  "instructor.failureContinue": "Let the others continue",
  "instructor.studentsOnly":
    "This page is for instructors. You are signed in as a student.",
  "instructor.warnings": "Warnings",

  "logs.heading": "Logs",
  "logs.export": "Export the audit log",
  "logs.none": "Nothing recorded yet.",
  "logs.sequence": "#",
  "logs.time": "Time",
  "logs.action": "Action",
  "logs.actor": "Actor",
  "logs.context": "Context",
  "logs.events": "Events",
  "logs.eventsEmpty": "Nothing yet.",

  "settings.heading": "Settings",
  "settings.language": "Language",
  "settings.english": "English",
  "settings.korean": "한국어",
  "settings.retention": "How long recordings are kept",
  "settings.maxRecordings": "Most recent recordings kept",
  "settings.retentionDays": "Days kept",
  "settings.saveRetention": "Save",
  "settings.retentionExplain":
    "Recordings older than this, and anything past the count, are deleted on this machine as new ones are written.",
} as const;

export type MessageKey = keyof typeof EN;

const KO: Record<MessageKey, string> = {
  "app.title": "CIT Physical XR 스튜디오",
  "app.subtitle": "런타임 콘솔",

  "nav.projects": "프로젝트",
  "nav.program": "프로그램",
  "nav.devices": "장치",
  "nav.xr": "XR",
  "nav.simulation": "시뮬레이션",
  "nav.instructor": "강사",
  "nav.logs": "기록",
  "nav.settings": "설정",

  "signin.heading": "수업 참여",
  "signin.explain":
    "런타임은 누가 쓰는지 확인한 뒤에 움직입니다. 여기 입력한 내용은 이 컴퓨터를 벗어나지 않습니다.",
  "signin.name": "이름",
  "signin.role": "역할",
  "signin.role.student": "학생",
  "signin.role.instructor": "강사",
  "signin.passcode": "강사 코드",
  "signin.passcodeHint":
    "런타임을 실행할 때 한 번 표시됩니다. 실행한 분에게 물어보세요.",
  "signin.explainNetwork":
    "이 런타임은 네트워크로 연결합니다. 그래서 누구인지와 참여 코드를 확인합니다. 여기 입력한 내용은 수업을 실행하는 컴퓨터를 벗어나지 않습니다.",
  "signin.classPasscode": "수업 참여 코드",
  "signin.classPasscodeHint":
    "이 수업은 네트워크로 열려 있어서 참여 코드를 받습니다. 수업을 여는 분에게 물어보세요.",
  "signin.submit": "참여",
  "signin.signedInAs": "접속 중",
  "signin.leave": "나가기",

  "safety.simulation": "시뮬레이션",
  "safety.physicalDisarmed": "실제 장치 · 작동 잠김",
  "safety.physicalArmed": "실제 장치 · 작동 허용",
  "safety.emergencyStopped": "비상 정지됨",
  "safety.simulationMeaning": "실제로 움직이는 것은 없습니다.",
  "safety.physicalDisarmedMeaning":
    "실제 장치가 연결돼 있습니다. 강사가 허용하기 전까지는 움직이지 않습니다.",
  "safety.physicalArmedMeaning":
    "실제 장치가 움직일 수 있습니다. 움직이는 동안 안전 버튼을 누르고 계세요.",
  "safety.emergencyStoppedMeaning":
    "전부 정지했습니다. 이어서 하려면 세션을 새로 시작하세요.",

  "action.stopAll": "전체 정지",
  "action.refresh": "새로고침",
  "action.retry": "다시 시도",

  "runtime.heading": "런타임",
  "runtime.id": "런타임",
  "runtime.protocol": "프로토콜",
  "runtime.mode": "모드",
  "runtime.physical": "실제 장치",
  "runtime.enabled": "사용",
  "runtime.disabled": "사용 안 함",
  "runtime.unreachable": "연결되지 않았습니다.",

  "session.heading": "세션",
  "session.new": "새 세션",
  "session.bind": "선택한 장치 연결",
  "session.validate": "검사",
  "session.none": "세션이 없습니다. 명령을 보내려면 세션이 필요합니다.",
  "session.mode": "실행 모드",
  "session.simulation": "시뮬레이션",
  "session.physical": "실제 장치",
  "session.safetyProfile": "안전 프로필",
  "session.instructorOnly":
    "실제 장치를 움직이는 세션은 강사만 시작할 수 있습니다.",
  "session.state": "상태",
  "session.bound": "연결된 장치",
  "session.nothingBound": "없음",

  "devices.heading": "장치",
  "devices.none": "찾은 장치가 없습니다.",
  "devices.simulated": "가상",
  "devices.physical": "실제",
  "devices.armed": "작동 허용",
  "devices.battery": "배터리",
  "devices.adapter": "어댑터",
  "devices.firmware": "펌웨어",
  "devices.lease": "사용 중",
  "devices.student": "학생",
  "devices.lastCommand": "마지막 명령",
  "devices.lastTelemetry": "마지막 신호",
  "devices.unknown": "보고 없음",
  "devices.free": "없음",
  "devices.discover": "장치 찾기",
  "devices.disconnect": "연결 끊기",
  "devices.revokeLease": "사용 권한 회수",
  "devices.arm": "이 장치 작동 허용",
  "devices.armed.by": "허용한 사람",
  "devices.disarm": "작동 잠금",
  "devices.stop": "이 장치 정지",

  "drive.heading": "조종",
  "drive.blocked":
    "세션을 시작하고 장치를 연결한 뒤 검사를 마쳐야 조종할 수 있습니다. 이 화면에서 버튼이 눌리더라도 허용 여부는 런타임이 판단합니다.",
  "drive.forward": "앞으로",
  "drive.back": "뒤로",
  "drive.left": "왼쪽",
  "drive.right": "오른쪽",
  "drive.overspeed": "속도 9.9로 시도",
  "drive.holdDeadman": "안전 버튼 누르고 있기",
  "drive.deadmanHeld": "누르는 중",
  "drive.deadmanExplain":
    "실제 장치는 이 버튼을 누르고 있어야 움직입니다. 손을 떼거나 이 화면을 닫으면 0.3초 안에 멈춥니다.",
  "drive.accepted": "실행",
  "drive.refused": "거절",
  "drive.clamped": "제한됨",

  "program.heading": "프로그램",
  "program.run": "실행",
  "program.stop": "프로그램 정지",
  "program.convert": "파이썬으로 전환",
  "program.export": "내보내기",
  "program.needsSession":
    "프로그램을 실행하려면 세션과 연결된 장치가 하나 이상 있어야 합니다.",
  "program.blocksSnapshot":
    "위의 블록은 남겨 둔 사본입니다. 실제로 실행되는 것은 아래 파이썬 코드입니다.",
  "program.converted":
    "이 프로젝트는 이제 파이썬입니다. 블록은 사본으로 남지만, 되돌릴 수는 없습니다.",
  "program.generatedPython": "생성된 파이썬",
  "program.python": "파이썬",
  "program.emptyProgram": "# 블록을 하나 놓아 보세요",
  "program.console": "출력",
  "program.consoleEmpty": "아직 출력된 내용이 없습니다.",
  "program.blockEditor": "블록 편집기",

  "projects.heading": "프로젝트",
  "projects.new": "새 프로젝트",
  "projects.open": "열기",
  "projects.delete": "삭제",
  "projects.none": "저장된 프로젝트가 없습니다.",
  "projects.owner": "만든 사람",
  "projects.updated": "수정일",
  "projects.saved": "저장했습니다.",
  "projects.saving": "저장 중…",
  "projects.unsaved": "저장하지 않은 변경",
  "projects.save": "저장",
  "projects.confirmDelete": "이 프로젝트를 삭제할까요? 되돌릴 수 없습니다.",
  "projects.notStored":
    "아직 런타임에 저장하지 않았습니다. 한 번 저장하면 그다음부터는 알아서 저장합니다.",
  "projects.autosaveFailed":
    "자동 저장에 실패했습니다. 작업한 내용은 그대로 있으니 저장을 눌러 다시 해 보세요.",

  "download.saved": "{name} 파일로 저장했습니다.",

  "xr.heading": "XR",
  "xr.notInThisMilestone":
    "Quest 앱은 아직 없습니다. 마일스톤 5에서 만듭니다. 흉내만 내는 화면을 대신 두지도 않았습니다. 헤드셋이 없는데 동작하는 것처럼 보이면 안 되기 때문입니다.",
  "xr.plannedHeading": "여기에 들어올 기능",
  "xr.plannedPairing": "같은 네트워크의 Quest와 연결",
  "xr.plannedTelemetry": "로봇 상태를 헤드셋 안에서 보기",
  "xr.plannedDeadman": "헤드셋의 안전 버튼",

  "simulation.heading": "시뮬레이션과 다시 보기",
  "simulation.recordings": "기록",
  "simulation.startRecording": "기록 시작",
  "simulation.stopRecording": "기록 정지",
  "simulation.recording": "기록 중…",
  "simulation.replay": "다시 보기",
  "simulation.exportPackage": "내보내기",
  "simulation.delete": "삭제",
  "simulation.none": "기록해 둔 것이 없습니다.",
  "simulation.events": "이벤트 {count}개",
  "simulation.neverMoves":
    "다시 보기는 기록해 둔 이벤트를 이 화면에 다시 보여 줍니다. 장치에는 전달되지 않습니다. 기록에서 로봇으로 이어지는 경로 자체가 없습니다.",
  "simulation.replayed":
    "이벤트 {count}개를 다시 재생했습니다. 움직인 것은 없습니다.",

  "instructor.heading": "강사 콘솔",
  "instructor.people": "접속한 사람",
  "instructor.sessions": "세션",
  "instructor.queueDepth": "대기 중인 명령",
  "instructor.disabledSources": "차단한 입력",
  "instructor.noneDisabled": "없음",
  "instructor.disableLeap": "Leap 입력 차단",
  "instructor.enableLeap": "Leap 입력 허용",
  "instructor.disableQuest": "Quest 조종 끊기",
  "instructor.enableQuest": "Quest 조종 다시 연결",
  "instructor.clearQueue": "명령 대기열 비우기",
  "instructor.disarmClass": "전체 작동 잠금",
  "instructor.failurePolicy": "한 대가 실패하면",
  "instructor.failureStop": "나머지도 멈춥니다",
  "instructor.failureContinue": "나머지는 계속합니다",
  "instructor.studentsOnly":
    "이 화면은 강사용입니다. 지금은 학생으로 접속해 있습니다.",
  "instructor.warnings": "주의",

  "logs.heading": "기록",
  "logs.export": "감사 기록 내보내기",
  "logs.none": "기록된 내용이 없습니다.",
  "logs.sequence": "번호",
  "logs.time": "시각",
  "logs.action": "동작",
  "logs.actor": "실행한 사람",
  "logs.context": "내용",
  "logs.events": "이벤트",
  "logs.eventsEmpty": "아직 없습니다.",

  "settings.heading": "설정",
  "settings.language": "언어",
  "settings.english": "English",
  "settings.korean": "한국어",
  "settings.retention": "기록 보관 기간",
  "settings.maxRecordings": "보관할 최근 기록 수",
  "settings.retentionDays": "보관 일수",
  "settings.saveRetention": "저장",
  "settings.retentionExplain":
    "정한 기간이 지났거나 개수를 넘긴 기록은 지워집니다. 새 기록을 저장할 때 이 컴퓨터에서 함께 정리합니다.",
};

const CATALOGS: Record<Locale, Record<MessageKey, string>> = { en: EN, ko: KO };

/**
 * Look up a message.
 *
 * A key missing from one catalog falls back to English rather than to the key
 * itself: a student reading "simulation.heading" learns nothing, while an
 * English label at least says what the control does. A key missing from both is
 * returned as itself, which is ugly on purpose -- it is a bug, and a blank
 * button hides it while a visible key does not. A test asserts the catalogs
 * agree, so neither fallback should fire in a shipped build.
 */
export function translate(
  locale: Locale,
  key: MessageKey,
  values?: Record<string, string | number>,
): string {
  const message = CATALOGS[locale][key] ?? EN[key] ?? key;
  if (values === undefined) return message;
  return Object.entries(values).reduce(
    (text, [name, value]) => text.replaceAll(`{${name}}`, String(value)),
    message,
  );
}

export function messageKeys(): MessageKey[] {
  return Object.keys(EN) as MessageKey[];
}

export function catalog(locale: Locale): Record<MessageKey, string> {
  return CATALOGS[locale];
}

export type Translate = (
  key: MessageKey,
  values?: Record<string, string | number>,
) => string;

export function translatorFor(locale: Locale): Translate {
  return (key, values) => translate(locale, key, values);
}
