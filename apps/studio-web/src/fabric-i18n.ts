import type {
  CoursePack,
  IntegrationNode,
  InteractionSession,
} from "@citxr/protocol";

import type {
  FabricDiscoveryCandidate,
  FabricIntegrationDiscovery,
  FabricMediaSource,
} from "./fabric-client.js";
import type { Locale } from "./i18n.js";

const EN = {
  "language.label": "Interface language",
  "language.ko": "한국어",
  "language.en": "English",
  "document.title": "CIT Classroom Control",

  "login.eyebrow": "Classroom device control",
  "login.opening": "Opening your classroom…",
  "login.welcome": "Welcome to CIT Classroom Control",
  "login.connectingLead":
    "Securely connecting to the devices on this computer.",
  "login.welcomeLead":
    "Set up a lesson, connect devices, check safety, and teach from one screen.",
  "login.wait": "Just a moment",
  "login.launcherCompleting": "The launcher is completing local sign-in.",
  "login.useButton": "Use the CIT button",
  "login.useButtonHelp":
    "Open CIT Classroom Control from the Windows Desktop or Start menu, then choose Start classroom devices. CIT will reopen this page and sign you in automatically.",
  "login.continueBrowser": "Continue in the browser",
  "login.continueBrowserHelp":
    "Choose a lesson, connect devices, check safety, and teach. No account or device password is needed.",
  "login.hideAccess": "Hide access-code sign in",
  "login.useAccess": "Launcher unavailable? Use an access code",
  "login.pasteAccess": "Paste your classroom access code",
  "login.accessHelp":
    "Use this recovery option only if automatic opening failed. Ask the classroom technician for a temporary access code.",
  "login.accessLabel": "Access code",
  "login.accessPlaceholder": "Paste access code",
  "login.continue": "Continue to classroom controls",
  "login.accessMemory":
    "The code stays in this tab only and is cleared when you sign out or reload.",
  "login.needHelp":
    "Need help? Ask the classroom technician to start the local CIT service. Device credentials never belong in this box.",

  "header.eyebrow": "CIT classroom",
  "header.title": "Classroom Control",
  "header.connected": "Connected locally",
  "header.tutor": "Tutor controls",
  "header.signOut": "Sign out",
  "header.stopAll": "Stop all devices",
  "header.refresh": "Refresh",
  "header.nextStep": "Your next step",

  "notice.ready": "Ready to set up your classroom.",
  "notice.secureOpen": "Classroom controls opened securely on this computer.",
  "notice.connected": "Classroom controls connected on this computer.",
  "notice.signedOut":
    "Signed out. Reopen the console from the CIT launcher to return.",
  "notice.lessonCreatedAuto":
    "Lesson created and {count} available device(s) were connected automatically.",
  "notice.lessonCreated":
    "Lesson created. Choose the devices you want to use next.",
  "notice.roleReady": "{device} is ready for {role}.",
  "notice.lessonStatus": "Lesson status: {status}.",
  "notice.physicalResumed":
    "Physical controls enabled; the monitoring lesson resumed.",
  "notice.physicalReady":
    "Physical controls enabled. Start the lesson when ready.",
  "notice.emergencyStop":
    "Emergency stop {status}: {sessions} session(s), {nodes} adapter node(s).",
  "notice.deviceCheck":
    "Device check finished: {connected} connected, {found} found or ready. Review the cards below for anything that still needs setup.",
  "notice.integrationConnected":
    "Connection started for {name}. Physical outputs remain disarmed.",
  "notice.matterAdded": "The Matter plug was added locally and remains off.",
  "notice.legoConnected": "The LEGO hub was connected for unarmed monitoring.",
  "notice.wonderConnected":
    "Connected {count} selected Dash/Dot robot(s) for unarmed monitoring.",
  "notice.noneConnected": "No connection completed.",
  "notice.groupsConnected":
    "Connection completed for {count} device group(s): {names}.",
  "notice.outputsLocked":
    "Physical outputs remain disarmed until a tutor starts an approved lesson.",
  "notice.someAttention": "Some devices still need attention. {details}",
  "notice.setupCopied":
    "{name} setup command copied. Paste it into PowerShell on this tutor computer.",
  "notice.cameraPairing":
    "Meta camera pairing is ready for five minutes. Enter the address and one-time code in the phone companion.",
  "notice.copied":
    "{label} copied. Paste it into the CIT Meta Camera phone companion.",
  "notice.inputReceived": "Student input was received from {source} at {time}.",
  "notice.noObjects": "No configured objects were recognized in {source}.",
  "notice.objects":
    "Recognized {labels} in {source}. Review the boxes before choosing any device action.",

  "busy.authenticating": "Authenticating",
  "busy.creatingSession": "Creating lesson",
  "busy.assigningRole": "Assigning a device",
  "busy.changingSession": "Updating lesson",
  "busy.enablingPhysical": "Enabling physical controls",
  "busy.emergencyStop": "Stopping all devices",
  "busy.findingDevices": "Finding devices",
  "busy.connectingDevice": "Connecting {name}",
  "busy.addingMatter": "Adding Matter smart plug",
  "busy.connectingLego": "Connecting LEGO hub",
  "busy.connectingWonder": "Connecting selected Dash and Dot robots",
  "busy.wonderCommand": "Sending a bounded Dash/Dot control",
  "busy.connectingAll": "Connecting available devices",
  "busy.copyingSetup": "Copying setup instructions",
  "busy.cameraPairing": "Preparing Meta camera pairing",
  "busy.copying": "Copying {label}",
  "busy.testingInput": "Testing input",
  "busy.testingOutput": "Testing output",
  "busy.smartPlug": "Changing smart-plug power",
  "busy.telloLand": "Landing Tello",
  "busy.telloEmergency": "Emergency-stopping Tello",
  "busy.brainArm": "Arming one-shot MindWave demo",
  "busy.brainStop": "Stopping MindWave demo",
  "busy.fleetArm": "Arming one sequential fleet launch",
  "busy.fleetStart": "Starting the armed fleet sequence",
  "busy.fleetStop": "Stopping and landing the selected fleet",
  "busy.vision": "Recognizing objects in {name}",

  "error.selectCourse": "Select an installed course pack.",
  "error.selectSession": "Select a lesson first.",
  "error.selectPhysicalSession": "Select a physical lesson first.",
  "error.selectNode": "Select a compatible device for {role}.",
  "error.setupFirst": "This integration needs its setup step first.",
  "error.wonderUnassigned":
    "Assign this Dash or Dot to a Wonder robot role first.",
  "error.grounded":
    "Confirm that every aircraft is grounded before connecting.",
  "error.noConnection":
    "No verified connection is ready. Follow the Setup needed cards, then find devices again.",
  "error.groundedAll":
    "Confirm that every aircraft is grounded before connecting all available devices.",
  "error.noSetupCommand": "No setup command is available for this integration.",
  "error.clipboard": "Clipboard access is unavailable in this browser.",
  "error.noInput": "No semantic input has arrived from an assigned device yet.",
  "error.startOutput": "Start the lesson before testing an output.",
  "error.assignRole": "Assign {role} before running this test.",
  "error.smartPlugSession": "Select a smart-plug lesson first.",
  "error.assignPlug": "Assign the classroom plug before controlling power.",
  "error.startLoad": "Start the lesson before turning on a load.",
  "error.armLoad": "Enable physical controls before turning on a load.",
  "error.monitoringSession": "Select the device-monitoring lesson first.",
  "error.droneUnassigned": "That Tello is no longer assigned to this lesson.",
  "error.brainController": "Assign the bounded MindWave demo controller first.",
  "error.startDemo": "Start the lesson before arming the demo.",
  "error.armFlight": "Enable physical controls before arming flight.",
  "error.fleetLesson": "Select the devices and safe demos lesson first.",
  "error.fleetController":
    "Assign the bounded fleet sequence controller first.",
  "error.startSequence": "Start the lesson before arming the sequence.",
  "error.auth":
    "That access code is invalid or expired. Reopen Classroom Control from the CIT launcher.",
  "error.physicalDisabled":
    "Real-device control is locked by the local runtime. Restart CIT with physical devices enabled, or use a simulator.",
  "error.sessionInactive": "Start the lesson before using that device.",
  "error.nodeUnavailable":
    "That device is no longer connected. Check its power and adapter, then refresh.",
  "error.rolesMissing":
    "Connect every required device before starting the lesson.",
  "error.requestFailed": "The Fabric request failed.",

  "guide.find.title": "Find the classroom devices",
  "guide.find.description":
    "Power on today’s equipment, plug in USB devices, then let CIT check this computer and its local connections.",
  "guide.choose.title": "Choose today’s lesson",
  "guide.choose.description":
    "Pick an experience below. CIT will create a safe classroom session and find matching devices.",
  "guide.ended.title": "This lesson has ended",
  "guide.ended.description":
    "Choose a lesson to create a fresh session. Connected devices remain available.",
  "guide.connect.title": "Connect {count} more device(s)",
  "guide.connect.description":
    "Choose a connected device for each empty slot. If nothing is listed, start that device’s CIT adapter and refresh.",
  "guide.safety.title": "Review safety before enabling devices",
  "guide.safety.description":
    "Check the room, keep the emergency stop visible, then confirm that physical control can be enabled.",
  "guide.teach.title": "Lesson running",
  "guide.teach.description":
    "Devices are ready. Use the lesson controls below and end the session when class is finished.",
  "guide.ready.title": "Everything is ready",
  "guide.ready.description":
    "Review the summary, then start the lesson when your students are ready.",
  "guide.action.find": "Find devices",
  "guide.action.choose": "Choose a lesson",
  "guide.action.connect": "Choose devices",
  "guide.action.teach": "Go to live controls",
  "guide.action.ended": "Set up another lesson",
  "guide.action.review": "Review and start",
  "guide.progress": "Lesson setup progress",
  "guide.step.find": "Find devices",
  "guide.step.choose": "Choose lesson",
  "guide.step.assign": "Assign devices",
  "guide.step.safety": "Safety check",
  "guide.step.teach": "Teach",

  "discovery.step": "Step 1",
  "discovery.title": "Find classroom devices",
  "discovery.intro":
    "Power devices on, plug in USB equipment, and choose Find devices. CIT checks current USB and Bluetooth links, active Wi-Fi routes, local services, and authorized Android phones connected by USB or Wi-Fi debugging.",
  "discovery.checking": "Checking…",
  "discovery.find": "Find devices",
  "discovery.noMovement": "No device will move, fly, or switch on",
  "discovery.safeTitle": "Safe discovery only",
  "discovery.safeBody":
    "Finding devices never arms robots, starts propellers, moves a motor, turns on a plug, starts an agent, or stores raw audio, video, or biosignals.",
  "discovery.connectionsReady": "{count} safe connection(s) ready",
  "discovery.connectAllHelp":
    "Connect every verified adapter in one step. Robots, drones, plugs, and lesson sessions remain disarmed.",
  "discovery.aircraftGrounded":
    "Every aircraft is grounded; propellers are removed or guarded.",
  "discovery.connecting": "Connecting…",
  "discovery.connectAll": "Connect all available",
  "discovery.offState": "No movement; approved plugs enter the off safe state",
  "discovery.startHost": "Start the physical device host first",
  "discovery.checked": "Checked {time}",
  "discovery.notChecked": "Not checked yet",
  "discovery.physicalAvailable": "Physical control is available but locked",
  "discovery.physicalDisabled": "Physical control is disabled in this runtime",
  "discovery.warningTitle": "Some checks need attention",
  "discovery.warningBody":
    "One or more local checks need attention. Open Technical diagnostics for the original message.",
  "discovery.loading": "Loading the device checklist",
  "discovery.loadingHelp": "CIT is preparing the supported hardware list.",
  "discovery.empty": "No supported devices are listed in this group yet.",
  "discovery.signal": "{percent}% signal",
  "discovery.connect": "Connect",
  "discovery.copySetup": "Copy setup command",
  "discovery.connectionDetails": "Connection details",
  "discovery.whatToDo": "What do I need to do?",
  "discovery.nodes": "CIT nodes: {nodes}",
  "discovery.summary.connected": "{count} CIT node(s) are connected.",
  "discovery.summary.found":
    "Windows or a local service found matching hardware. Complete the card’s connection step before using it in a lesson.",
  "discovery.summary.ready":
    "This computer is ready. Power on the device or complete the remaining setup step.",
  "discovery.summary.missing":
    "No matching device is currently visible. Follow the setup steps, then scan again.",
  "candidate.attached":
    "Windows reports this device as attached. Its CIT adapter must still confirm readiness.",
  "candidate.connected":
    "A current local connection was found. Its CIT adapter must still confirm application readiness.",
  "candidate.recent":
    "This device was active recently. Reconnect it before starting a lesson.",
  "candidate.visible":
    "The device is visible nearby. Verify its exact classroom identity before connecting.",
  "candidate.paired":
    "The device is paired in Windows. Start its CIT adapter to use it in a lesson.",
  "candidate.provisioned":
    "Configuration is saved, but the current device connection still needs confirmation.",
  "candidate.ready": "The required local service is ready.",
  "candidate.generic":
    "Read-only discovery evidence was found. The adapter handshake still confirms the device.",
  "link.attached": "Attached now",
  "link.connected": "Connected now",
  "link.recent": "Recently active",
  "link.visible": "Visible nearby",
  "link.paired": "Paired",
  "link.provisioned": "Configured",
  "link.ready": "Computer ready",

  "io.input.title": "Inputs",
  "io.input.discovery":
    "These send gestures, voice intents, buttons, or sensor readings into a lesson.",
  "io.input.role": "Devices that supply the lesson trigger or readings",
  "io.input.label": "Input only",
  "io.bidirectional.title": "Inputs + outputs",
  "io.bidirectional.discovery":
    "These both report state or interactions and receive bounded instructions.",
  "io.bidirectional.role":
    "Devices that both report information and accept actions",
  "io.bidirectional.label": "Input + output",
  "io.output.title": "Outputs",
  "io.output.discovery":
    "These only receive lesson instructions, such as a display or actuator.",
  "io.output.role": "Devices that receive the lesson’s bounded actions",
  "io.output.label": "Output only",

  "status.connected": "Connected",
  "status.found": "Found",
  "status.ready": "Computer ready",
  "status.setup": "Setup needed",
  "status.notFound": "Not found",
  "status.unavailable": "Unavailable",
  "status.notChecked": "Not checked",
  "status.none": "None yet",
  "status.notSetUp": "Not set up",
  "status.selectLesson": "Select a lesson",
  "status.enabled": "Enabled",
  "status.locked": "Locked",
  "status.optional": "optional",
  "status.assigned": "assigned",
  "status.notIncluded": "Not included",

  "overview.devices": "Connected devices",
  "overview.lesson": "Current lesson",
  "overview.lessonStatus": "Lesson status",
  "overview.physical": "Physical devices",

  "lesson.step2": "Step 2",
  "lesson.chooseTitle": "Choose a lesson",
  "lesson.choosePrompt": "What do you want students to do today?",
  "lesson.selected": "Selected",
  "lesson.choose": "Choose",
  "lesson.settings": "Room and device settings",
  "lesson.site": "Site",
  "lesson.room": "Room",
  "lesson.devicesUsed": "Devices used in this lesson",
  "lesson.simulation": "Simulators only — safest for practice",
  "lesson.physical": "Real classroom devices — safety check required",
  "lesson.setup": "Set up this lesson",
  "lesson.continue": "Or continue a session already set up",
  "lesson.existing": "Choose an existing session",
  "lesson.step3": "Step 3",
  "lesson.assignTitle": "Assign lesson devices",
  "lesson.assignIntro":
    "CIT only shows devices that can perform each job in this lesson.",
  "lesson.chooseFirst": "Choose and set up a lesson first",
  "lesson.matchesAppear":
    "Your matching devices will appear here automatically.",

  "role.deviceFor": "Device for {role}",
  "role.noMatch": "No matching device connected",
  "role.chooseDevice": "Choose a device",
  "role.useDevice": "Use this device",
  "role.change": "Change",
  "role.startAdapter":
    "Start the device’s CIT adapter, then choose Refresh at the top of this page.",

  "parallel.runsTogether": "Runs together",
  "parallel.title": "Simultaneous output plan",
  "parallel.assigned": "{ready}/{total} assigned",
  "parallel.description":
    "One {trigger} input fans out to every assigned output below. Unassigned optional outputs are skipped.",
  "parallel.safety":
    "Commands launch concurrently, but each output still has its own capability check, safety decision, control lease, result, and emergency-stop path. Tello takeoff also requires the separate fleet checklist below.",

  "safety.step4": "Step 4",
  "safety.title": "Review and start",
  "safety.setupFirst": "Set up a lesson to continue",
  "safety.simulation": "Simulation mode — physical devices stay locked",
  "safety.enabled": "Physical device control is enabled",
  "safety.locked": "Physical devices are locked",
  "safety.physicalHelp":
    "Keep the Stop all devices button visible and make sure the activity area is clear.",
  "safety.simulationHelp":
    "Practice safely before switching this lesson to real classroom hardware.",
  "safety.confirm":
    "I can see the devices, the activity area is clear, and I know where “Stop all devices” is.",
  "safety.pauseEnable": "Pause briefly and enable physical controls",
  "safety.enable": "Enable physical controls",
  "safety.lock": "Lock physical devices",
  "safety.resume": "Resume lesson",
  "safety.start": "Start lesson",
  "safety.pause": "Pause lesson",
  "safety.end": "End lesson and lock devices",

  "test.step5": "Step 5",
  "test.title": "Teach and test",
  "test.runningHelp":
    "The lesson is running. Use only the checks that match today’s activity.",
  "test.waitingHelp":
    "Start the lesson in Step 4 to unlock its teaching controls.",
  "test.input": "Check student input",
  "test.inputHelp": "Ask for a gesture, button press, or voice input",
  "test.agent": "Check coding assistant",
  "test.agentHelp": "Send one safe connectivity message",
  "test.glasses": "Check glasses display",
  "test.glassesHelp": "Show one fixed classroom message",
  "test.robotStop": "Check robot stop",
  "test.robotStopHelp": "Confirm the robot accepts its safe stop command",
  "test.running": "Lesson is running",
  "test.waiting": "Teaching controls are waiting",
  "test.inProgress": "{count} device action(s) in progress",
  "test.agentPrompt":
    "Reply with a short CIT Fabric connectivity acknowledgement.",
  "test.displayMessage": "CIT Fabric display test",

  "media.eyebrow": "Classroom vision",
  "media.title": "Live cameras and object recognition",
  "media.intro":
    "Meta glasses, RoboMaster, Tello, and other approved local camera publishers appear together here. Frames stay in memory, are not added to lesson recordings, and are replaced by the next frame.",
  "media.connectMeta": "Connect a Meta glasses camera",
  "media.connectMetaHelp":
    "Keep the phone on the classroom Wi-Fi, then pair the CIT Meta Camera companion. Start live sharing on the phone; older glasses firmware can use the snapshot fallback.",
  "media.createPairing": "Create phone pairing",
  "media.pairStep1": "Open CIT Meta Camera on the Android phone.",
  "media.pairStep2": "Enter the classroom address and one-time code below.",
  "media.pairStep3":
    "Tap Pair, approve Meta camera access, then tap Share live camera. Use snapshot fallback only if live frames fail.",
  "media.address": "Classroom address",
  "media.code": "One-time pairing code",
  "media.copy": "Copy",
  "media.expiry":
    "Expires {time} and works once. The phone receives publish-only access for {site}/{room}; it cannot read cameras or control devices.",
  "media.replaceCode": "Replace with a new code",
  "media.none": "No camera source is publishing yet.",
  "media.noneHelp":
    "Start an approved camera bridge. Meta glasses require the CIT phone companion, camera permission, and visible camera-use indicator.",
  "media.privacy":
    "Object recognition never operates a robot, drone, or plug by itself. A tutor must review the detection and press an explicit bounded control.",
  "media.waitFrame": "Waiting for first frame",
  "media.live": "Live",
  "media.waiting": "Waiting",
  "media.captureVideo": "Live frames",
  "media.captureSnapshot": "Snapshot fallback",
  "media.latestAlt": "Latest view from {name}",
  "media.noDimensions": "No image dimensions yet",
  "media.noFrame": "No frame received",
  "media.updated": "Updated {time}",
  "media.recognize": "Recognize lamps, drones, and robots",
  "media.noneFound": "No configured object found",
  "media.objectsFound": "Objects found",
  "media.assignPlug":
    "Assign a classroom plug session to control an approved lamp.",
  "media.explicitPlug": "Explicit tutor control for {name}",
  "media.plugOn": "Turn linked plug on",
  "media.plugOff": "Turn linked plug off",
  "media.droneAdvisory":
    "Drone recognition is advisory. Use an assigned, armed flight lesson for bounded drone controls; vision cannot arm or fly it.",
  "media.noMappedAction":
    "No device action is mapped to this visual class. Use an assigned lesson control if one is available.",

  "sensor.eyebrow": "Live sensors",
  "sensor.title": "Classroom readings",
  "sensor.intro":
    "The latest normalized LEGO, robot, biosignal, and battery readings appear automatically when an adapter publishes them.",
  "sensor.none": "No sensor readings have arrived in the selected lesson yet.",

  "plug.eyebrow": "Lesson control",
  "plug.title": "Classroom plug",
  "plug.noneAssigned": "No classroom plug assigned",
  "plug.compatible": "{count} compatible device(s) connected",
  "plug.stateUnknown": "State has not been observed in this lesson",
  "plug.observed": "Observed {time}{source}",
  "plug.turnOn": "Turn on",
  "plug.turnOnHelp": "Turn on the approved classroom load",
  "plug.afterSafety": "Available after the lesson safety check",
  "plug.turnOff": "Turn off",
  "plug.turnOffHelp": "Always available as the safe state",
  "plug.onState": "ON",
  "plug.offState": "OFF",
  "plug.help":
    "Use only the approved classroom load. The tutor can always turn it off, even when physical controls are locked.",

  "nodes.eyebrow": "Device status",
  "nodes.title": "Everything connected to this classroom",
  "nodes.intro":
    "Glasses, sensors, robots, smart plugs, coding assistants, and simulators all appear here when their CIT adapter is running.",
  "nodes.simulator": "Simulator",
  "nodes.physical": "Real device",
  "nodes.technical": "Technical details",
  "nodes.host": "host",
  "nodes.sends": "Sends",
  "nodes.receives": "Receives",
  "nodes.empty": "No devices in this group yet.",
  "nodes.none": "None",

  "diagnostics.title": "Technical diagnostics",
  "diagnostics.subtitle":
    "Signals, command history, identifiers, and audit records",
  "diagnostics.signalEyebrow": "Device signals",
  "diagnostics.signalTitle": "Recent activity",
  "diagnostics.noSignals": "No selected-lesson signals yet.",
  "diagnostics.commandEyebrow": "Device instructions",
  "diagnostics.commandTitle": "Command progress",
  "diagnostics.noCommands": "No command decisions yet.",
  "diagnostics.offlineEyebrow": "Adapter history",
  "diagnostics.offlineTitle": "{count} offline record(s) hidden",
  "diagnostics.offlineHelp":
    "Disconnected adapter records are retained for diagnostics and audit, but they are excluded from connected-device totals and lesson assignment choices.",
  "diagnostics.auditEyebrow": "Audit history",
  "diagnostics.auditTitle": "Recent control changes",

  "matter.add": "Add a Matter plug",
  "matter.addAnother": "Add another Matter plug",
  "matter.help":
    "Hold the plug’s pairing button until its light flashes, then enter the Matter code printed beside its QR label. No proprietary vendor app, account, cloud API, device ID, or local key is used.",
  "matter.code": "Matter setup code",
  "matter.placeholder": "MT:… or 1234-567-8901",
  "matter.adding": "Adding plug…",
  "matter.addLocally": "Add plug locally",
  "matter.addAnotherButton": "Add another plug",
  "matter.memory":
    "Setup can take two or three minutes. CIT keeps the code only in page memory for this request and clears it after success.",

  "lego.setup": "Set up this LEGO hub",
  "lego.another": "Connect another LEGO hub",
  "lego.help":
    "Enter the exact Bluetooth name shown by Pybricks and what is plugged into each port. CIT will never choose the nearest anonymous hub.",
  "lego.name": "Exact advertised hub name",
  "lego.model": "Hub model",
  "lego.ports": "Connected ports",
  "lego.port": "Port {port}",
  "lego.empty": "Empty",
  "lego.motor": "Motor",
  "lego.distance": "Distance sensor",
  "lego.color": "Color sensor",
  "lego.force": "Force sensor",
  "lego.connecting": "Connecting hub…",
  "lego.connect": "Save and connect hub",
  "lego.safety":
    "Starts unarmed sensor monitoring only. A sensor-only hub is supported. If motors are connected, keep wheels raised for the first test; a separate armed lesson is required for movement.",

  "wonder.setup": "Choose the exact robots to connect",
  "wonder.setupHelp":
    "Only robots found in this scan can be selected. Names and signal levels help you match the physical robot; CIT never chooses the nearest one automatically.",
  "wonder.noneVisible":
    "No exact robot advertisement is selectable yet. Switch on Dash or Dot, close other robot apps, then choose Find devices again.",
  "wonder.selectExact": "Visible Dash and Dot robots",
  "wonder.dash": "Dash · drive, head, lights, sound, sensors",
  "wonder.dot": "Dot · lights, sound, sensors (no drive)",
  "wonder.connecting": "Connecting selected robots…",
  "wonder.connectSelected": "Connect selected robots",
  "wonder.connectSafety":
    "Connection starts sensor monitoring only. No movement, head, light, or sound command is sent.",
  "wonder.eyebrow": "Robot controls",
  "wonder.title": "Wonder Workshop Dash and Dot",
  "wonder.help":
    "Lights are available in a running lesson. Sound, Dash head motion, and short drive nudges require a running, armed physical lesson. Dot has no drive controls.",
  "wonder.lights": "Lights",
  "wonder.sounds": "Fixed classroom sounds",
  "wonder.color.blue": "Blue",
  "wonder.color.orange": "Orange",
  "wonder.color.green": "Green",
  "wonder.color.off": "Lights off",
  "wonder.soundLabel": "Sound {number}",
  "wonder.drive": "Dash short movement",
  "wonder.forward": "Forward",
  "wonder.backward": "Backward",
  "wonder.left": "Left",
  "wonder.right": "Right",
  "wonder.stop": "Stop",
  "wonder.nudge":
    "Each arrow is a short nudge. Dash stops locally within 350 ms unless another approved command arrives.",
  "wonder.head": "Dash head",
  "wonder.center": "Center",
  "wonder.up": "Up",
  "wonder.down": "Down",
  "wonder.locked":
    "Locked: start the monitoring lesson, choose Enable physical controls, and confirm the clear-area safety check.",

  "drone.eyebrow": "Safety controls",
  "drone.title": "Tello safe-state controls",
  "drone.help":
    "This monitoring slice can land or emergency-stop an assigned aircraft. It cannot take off, move, rotate, or arm a drone.",
  "drone.role": "Safety drone {number}",
  "drone.land": "Land",
  "drone.landHelp": "Request a normal landing",
  "drone.emergency": "Emergency motor stop",
  "drone.emergencyHelp": "Use only when stopping motors is safer than flight",
  "drone.confirm":
    "Emergency-stop {name}? An airborne drone can fall immediately.",

  "brain.eyebrow": "Guided MindWave demo",
  "brain.title": "One signal, one bounded Tello demonstration",
  "brain.simulation": "SIMULATION — no aircraft can move",
  "brain.physical": "PHYSICAL FLIGHT",
  "brain.help":
    "Choose the vendor-derived MindWave signal and threshold. Arming waits for one qualifying signal, triggers Brain2Devices once, then clears itself. It is not continuous brain control and it exposes no manual takeoff or movement command.",
  "brain.current": "Current state",
  "brain.progress": "Progress",
  "brain.waiting": "Waiting for the controller’s first status update.",
  "brain.chooseSignal": "1. Choose what starts the one-shot demo",
  "brain.attention": "Attention (NeuroSky eSense)",
  "brain.attentionHelp":
    "Must stay strictly above this value. This is a vendor-derived interaction signal, not an objective attention measurement.",
  "brain.meditation": "Meditation (NeuroSky eSense)",
  "brain.meditationHelp":
    "Must stay strictly above this value. It is shown independently from Attention.",
  "brain.blink": "Blink strength",
  "brain.blinkHelp":
    "One new blink strictly above the threshold qualifies immediately; dwell time does not apply.",
  "brain.threshold": "{label} threshold",
  "brain.hold": "Hold Attention or Meditation above threshold for",
  "brain.seconds": "seconds",
  "brain.dwellHelp":
    "Use 2 seconds for the first hardware test. Zero accepts the first qualifying sample.",
  "brain.flightCheck": "2. Instructor flight check — all three required",
  "brain.present": "I am present and supervising this flight.",
  "brain.areaClear":
    "The full flight area is clear; all visible Tellos are verified and grounded.",
  "brain.emergencyReady":
    "I can reach Land and Emergency stop and understand that a released rapid-handoff aircraft may no longer be reachable from the current Wi-Fi adapter.",
  "brain.runSimulation": "Run safe simulation",
  "brain.arm": "Arm one-shot flight demo",
  "brain.waitCondition": "Waits for the selected MindWave condition",
  "brain.startFirst": "Start the lesson first",
  "brain.startArmFirst": "Start and arm the physical lesson first",
  "brain.stop": "Stop / disarm demo",
  "brain.stopHelp": "Safe-state command; available before or during a trigger",

  "fleet.eyebrow": "Multi-input drone sequence",
  "fleet.title": "Launch several Tellos, one confirmed aircraft at a time",
  "fleet.helpBefore": "First arm one ordered plan. Then use",
  "fleet.startNow": "Start now",
  "fleet.helpAfter":
    "the Leap open-hand→pinch gesture, or say “Start drone sequence” through an assigned G2 or Meta glasses node. A trigger cannot arm flight; it can only consume the tutor’s current one-shot plan.",
  "fleet.current": "Current state",
  "fleet.airborne": "Confirmed airborne",
  "fleet.waiting": "Waiting for the fleet controller’s first status update.",
  "fleet.order": "1. Choose launch order (top launches first)",
  "fleet.connectController":
    "Connect the Brain2Devices fleet controller to list approved aircraft.",
  "fleet.aircraftState": "{connection} · {flight} · battery {battery}%",
  "fleet.earlier": "Move {name} earlier",
  "fleet.later": "Move {name} later",
  "fleet.remove": "Remove",
  "fleet.interval": "Seconds between confirmed launches",
  "fleet.minimumBattery": "Minimum battery for every aircraft",
  "fleet.inputs": "2. Choose what may consume this one-shot arm",
  "fleet.tutorButton": "Tutor’s Start now button",
  "fleet.noInputs":
    "No Leap, G2, or Meta input is assigned. The tutor button still works.",
  "fleet.flightCheck": "3. Instructor flight check — all four required",
  "fleet.present": "I am present and supervising every aircraft.",
  "fleet.areaClear":
    "The full flight area is clear and every selected aircraft is visibly grounded.",
  "fleet.emergencyReady":
    "I can reach Stop & land and each aircraft’s emergency control.",
  "fleet.routes":
    "Each stock Tello has its own connected Wi-Fi route, or each station-mode aircraft has a unique reachable address.",
  "fleet.notReady":
    "Every selected aircraft must be connected, confirmed landed, and at or above the minimum battery.",
  "fleet.arm": "Arm this sequence once",
  "fleet.armHelp": "No aircraft launches yet · expires after 60 seconds",
  "fleet.startArmFirst": "Start and arm the lesson first",
  "fleet.startHelp": "Uses the same bounded command as Leap and glasses",
  "fleet.stop": "Stop & land selected fleet",
  "fleet.stopHelp": "Also cancels launches that have not started",
  "fleet.leapInstruction": "open hand, then pinch",
  "fleet.voiceInstruction": "say “Start drone sequence”",

  "course.deviceMonitoring.name": "Devices, sensors, cameras, and safe demos",
  "course.deviceMonitoring.summary": "Cameras, sensors + bounded drone demos",
  "course.deviceMonitoring.description":
    "Shows cameras, Tello telemetry, MindWave vendor signals, and LEGO readings. Optional guided panels add an explicitly armed MindWave demo and a tutor-armed sequential fleet launched by button, Leap, G2, or Meta.",
  "course.glasses.name": "Glasses and coding assistant",
  "course.glasses.summary": "Glasses + coding assistant",
  "course.glasses.description":
    "Students send a request from their glasses to a coding assistant and receive the response on a classroom display.",
  "course.gesture.name": "Gesture-controlled robot",
  "course.gesture.summary": "Gesture + classroom robot",
  "course.gesture.description":
    "Students steer a classroom robot with hand gestures while CIT keeps movement within the lesson’s safety limits.",
  "course.simultaneous.name": "Simultaneous multi-device cue",
  "course.simultaneous.summary": "One input + several simultaneous outputs",
  "course.simultaneous.description":
    "One approved Leap or glasses cue simultaneously sends bounded actions to an assigned RoboMaster, LEGO hub, armed Tello fleet, Meta display, and G2 display. Every output remains independently safety checked.",
  "course.plug.name": "Classroom smart plug",
  "course.plug.summary": "Tutor-controlled classroom plug",
  "course.plug.description":
    "The tutor turns one approved classroom lamp or other low-risk load on and off from this screen.",
  "course.fallback": "{count} classroom device role(s)",

  "role.brain.name": "One-shot MindWave flight demo",
  "role.brain.description":
    "Waits for one instructor-configured MindWave threshold, runs the bounded Brain2Devices demonstration once, then disarms",
  "role.biosignal.name": "MindWave headset",
  "role.biosignal.description":
    "Publishes vendor-labelled MindWave readings without raw EEG",
  "role.fleet.name": "Sequential drone controller",
  "role.fleet.description":
    "Owns one tutor-armed launch order and confirms each aircraft before advancing",
  "role.plug.name": "Classroom plug",
  "role.plug.description": "Turns one approved classroom load on or off",
  "role.agent.name": "Coding assistant",
  "role.agent.description":
    "Receives student prompts and returns coding progress",
  "role.feedback.name": "Feedback display",
  "role.feedback.description": "Shows coding progress and lesson messages",
  "role.gesture.name": "Gesture controller",
  "role.gesture.description": "Sends hand movements to the lesson",
  "role.console.name": "Tutor display",
  "role.console.description": "Shows lesson activity to the tutor",
  "role.glasses.name": "Student glasses",
  "role.glasses.description":
    "Sends student input and displays lesson feedback",
  "role.robot.name": "Classroom robot",
  "role.robot.description": "Receives bounded movement and stop instructions",
  "role.safetyDrone.name": "Safety drone {number}",
  "role.safetyDrone.description":
    "Publishes Tello telemetry and accepts only Land or Emergency Stop",
  "role.fleetInput.name": "Fleet trigger {number}",
  "role.fleetInput.description":
    "Requests the currently armed sequence through Leap, G2, or Meta",
  "role.groundOutput.name": "Ground robot output {number}",
  "role.groundOutput.description":
    "Receives the same bounded, watchdog-limited movement cue; assign RoboMaster or a mobile LEGO hub",
  "role.messageOutput.name": "Glasses message output {number}",
  "role.messageOutput.description":
    "Receives the same fixed lesson message; assign G2 or Meta glasses",
  "role.robotSensor.name": "Robot sensor {number}",
  "role.robotSensor.description":
    "Publishes LEGO or robot sensor and battery readings",
  "role.fallback.description": "Fills this part of the classroom lesson",

  "session.notStarted": "Not started",
  "session.draft": "Needs devices",
  "session.ready": "Ready to start",
  "session.active": "Running",
  "session.paused": "Paused",
  "session.stopped": "Ended",
  "session.emergency": "Emergency stopped",
  "session.failed": "Needs attention",
  "connection.connected": "Connected",
  "connection.degraded": "Connected · needs attention",
  "connection.unavailable": "Unavailable",
  "connection.disconnected": "Disconnected",
  "connection.connecting": "Connecting",
  "health.healthy": "Healthy",
  "health.degraded": "Needs attention",
  "health.unhealthy": "Not working",
  "health.unknown": "Health unknown",
  "command.success": "{label} worked.",
  "command.failed":
    "{label} was not completed. Open Technical diagnostics for details.",
  "command.stopped":
    "{label} stopped before it finished. Try again or check the device.",
  "command.sent": "{label} was sent to the device.",
} as const;

export type FabricMessageKey = keyof typeof EN;

const KO: Record<FabricMessageKey, string> = {
  ...EN,
  "language.label": "화면 언어",
  "document.title": "CIT 수업 제어",
  "login.eyebrow": "교실 장치 제어",
  "login.opening": "교실을 여는 중…",
  "login.welcome": "CIT 수업 제어에 오신 것을 환영합니다",
  "login.connectingLead": "이 컴퓨터의 교실 장치에 안전하게 연결하고 있습니다.",
  "login.welcomeLead":
    "한 화면에서 수업을 준비하고, 장치를 연결하고, 안전을 확인한 뒤 수업을 진행하세요.",
  "login.wait": "잠시만 기다려 주세요",
  "login.launcherCompleting":
    "실행기가 이 컴퓨터에서 안전하게 로그인하고 있습니다.",
  "login.useButton": "CIT 버튼 사용",
  "login.useButtonHelp":
    "Windows 바탕 화면이나 시작 메뉴에서 CIT 수업 제어를 열고 ‘교실 장치 시작’을 선택하세요. CIT가 이 페이지를 다시 열고 자동으로 로그인합니다.",
  "login.continueBrowser": "브라우저에서 계속",
  "login.continueBrowserHelp":
    "수업을 고르고 장치를 연결한 뒤 안전을 확인하고 수업을 진행하세요. 별도 계정이나 장치 비밀번호는 필요하지 않습니다.",
  "login.hideAccess": "접속 코드 입력 숨기기",
  "login.useAccess": "실행기를 사용할 수 없나요? 접속 코드 사용",
  "login.pasteAccess": "교실 접속 코드를 붙여 넣으세요",
  "login.accessHelp":
    "자동 열기가 실패했을 때만 사용하는 복구 방법입니다. 교실 기술 담당자에게 임시 접속 코드를 요청하세요.",
  "login.accessLabel": "접속 코드",
  "login.accessPlaceholder": "접속 코드 붙여 넣기",
  "login.continue": "교실 제어로 계속",
  "login.accessMemory":
    "코드는 이 탭의 메모리에만 보관되며 로그아웃하거나 새로고침하면 지워집니다.",
  "login.needHelp":
    "도움이 필요하면 교실 기술 담당자에게 로컬 CIT 서비스를 시작해 달라고 요청하세요. 장치 비밀번호나 인증 정보는 이 입력란에 넣지 마세요.",
  "header.eyebrow": "CIT 교실",
  "header.title": "수업 제어",
  "header.connected": "이 컴퓨터에 연결됨",
  "header.tutor": "강사 제어",
  "header.signOut": "로그아웃",
  "header.stopAll": "모든 장치 정지",
  "header.refresh": "새로고침",
  "header.nextStep": "다음 단계",
  "notice.ready": "교실을 준비할 수 있습니다.",
  "notice.secureOpen": "이 컴퓨터에서 수업 제어를 안전하게 열었습니다.",
  "notice.connected": "이 컴퓨터의 수업 제어에 연결했습니다.",
  "notice.signedOut":
    "로그아웃했습니다. 다시 들어오려면 CIT 실행기에서 수업 제어를 여세요.",
  "notice.lessonCreatedAuto":
    "수업을 만들고 사용 가능한 장치 {count}대를 자동으로 배정했습니다.",
  "notice.lessonCreated":
    "수업을 만들었습니다. 다음으로 사용할 장치를 선택하세요.",
  "notice.roleReady": "{device} 장치를 ‘{role}’ 역할로 사용할 준비가 됐습니다.",
  "notice.lessonStatus": "수업 상태: {status}.",
  "notice.physicalResumed":
    "실제 장치 제어를 허용하고 모니터링 수업을 다시 시작했습니다.",
  "notice.physicalReady":
    "실제 장치 제어를 허용했습니다. 준비되면 수업을 시작하세요.",
  "notice.emergencyStop":
    "비상 정지 {status}: 세션 {sessions}개, 어댑터 노드 {nodes}개를 정지했습니다.",
  "notice.deviceCheck":
    "장치 확인 완료: 연결됨 {connected}개, 발견 또는 준비됨 {found}개. 설정이 더 필요한 장치는 아래 카드를 확인하세요.",
  "notice.integrationConnected":
    "{name} 연결을 시작했습니다. 실제 출력 장치는 계속 잠겨 있습니다.",
  "notice.matterAdded":
    "Matter 플러그를 로컬로 추가했습니다. 전원은 꺼진 안전 상태입니다.",
  "notice.legoConnected":
    "LEGO 허브를 모터 잠금 상태의 모니터링용으로 연결했습니다.",
  "notice.wonderConnected":
    "선택한 Dash/Dot 로봇 {count}대를 제어 잠금 상태의 모니터링용으로 연결했습니다.",
  "notice.noneConnected": "완료된 연결이 없습니다.",
  "notice.groupsConnected": "장치 그룹 {count}개를 연결했습니다: {names}.",
  "notice.outputsLocked":
    "강사가 승인된 수업을 시작할 때까지 실제 출력 장치는 잠긴 상태입니다.",
  "notice.someAttention": "일부 장치를 확인해야 합니다. {details}",
  "notice.setupCopied":
    "{name} 설정 명령을 복사했습니다. 이 강사용 컴퓨터의 PowerShell에 붙여 넣으세요.",
  "notice.cameraPairing":
    "Meta 카메라 페어링을 5분 동안 사용할 수 있습니다. 휴대전화 앱에 주소와 일회용 코드를 입력하세요.",
  "notice.copied":
    "{label}을(를) 복사했습니다. CIT Meta Camera 휴대전화 앱에 붙여 넣으세요.",
  "notice.inputReceived": "{time}에 {source}에서 학생 입력을 받았습니다.",
  "notice.noObjects": "{source} 영상에서 설정된 물체를 찾지 못했습니다.",
  "notice.objects":
    "{source} 영상에서 {labels}을(를) 찾았습니다. 장치 동작을 선택하기 전에 표시 상자를 확인하세요.",
  "busy.authenticating": "인증하는 중",
  "busy.creatingSession": "수업 만드는 중",
  "busy.assigningRole": "장치 배정 중",
  "busy.changingSession": "수업 상태 변경 중",
  "busy.enablingPhysical": "실제 장치 제어 허용 중",
  "busy.emergencyStop": "모든 장치 정지 중",
  "busy.findingDevices": "장치 찾는 중",
  "busy.connectingDevice": "{name} 연결 중",
  "busy.addingMatter": "Matter 스마트 플러그 추가 중",
  "busy.connectingLego": "LEGO 허브 연결 중",
  "busy.connectingWonder": "선택한 Dash/Dot 로봇 연결 중",
  "busy.wonderCommand": "제한된 Dash/Dot 제어 전송 중",
  "busy.connectingAll": "사용 가능한 장치 연결 중",
  "busy.copyingSetup": "설정 안내 복사 중",
  "busy.cameraPairing": "Meta 카메라 페어링 준비 중",
  "busy.copying": "{label} 복사 중",
  "busy.testingInput": "입력 확인 중",
  "busy.testingOutput": "출력 확인 중",
  "busy.smartPlug": "스마트 플러그 전원 변경 중",
  "busy.telloLand": "Tello 착륙 요청 중",
  "busy.telloEmergency": "Tello 비상 정지 중",
  "busy.brainArm": "MindWave 1회 데모 준비 중",
  "busy.brainStop": "MindWave 데모 정지 중",
  "busy.fleetArm": "순차 드론 비행 1회 준비 중",
  "busy.fleetStart": "준비된 드론 순차 비행 시작 중",
  "busy.fleetStop": "선택한 드론 정지 및 착륙 중",
  "busy.vision": "{name}에서 물체 인식 중",
  "error.selectCourse": "설치된 수업을 선택하세요.",
  "error.selectSession": "먼저 수업을 선택하세요.",
  "error.selectPhysicalSession": "먼저 실제 장치를 사용하는 수업을 선택하세요.",
  "error.selectNode": "{role} 역할에 맞는 장치를 선택하세요.",
  "error.setupFirst": "먼저 이 통합의 설정 단계를 완료하세요.",
  "error.wonderUnassigned":
    "먼저 이 Dash 또는 Dot을 Wonder 로봇 역할에 배정하세요.",
  "error.grounded": "연결하기 전에 모든 드론이 바닥에 있는지 확인하세요.",
  "error.noConnection":
    "지금 바로 연결할 수 있는 장치가 없습니다. ‘설정 필요’ 카드를 따른 뒤 장치를 다시 찾으세요.",
  "error.groundedAll":
    "사용 가능한 장치를 한꺼번에 연결하기 전에 모든 드론이 바닥에 있는지 확인하세요.",
  "error.noSetupCommand": "이 통합에는 복사할 설정 명령이 없습니다.",
  "error.clipboard": "이 브라우저에서 클립보드를 사용할 수 없습니다.",
  "error.noInput": "배정한 장치에서 아직 의미 있는 입력이 들어오지 않았습니다.",
  "error.startOutput": "출력을 확인하기 전에 수업을 시작하세요.",
  "error.assignRole": "확인하기 전에 {role} 역할을 배정하세요.",
  "error.smartPlugSession": "먼저 스마트 플러그 수업을 선택하세요.",
  "error.assignPlug": "전원을 제어하기 전에 교실 플러그를 배정하세요.",
  "error.startLoad": "부하 전원을 켜기 전에 수업을 시작하세요.",
  "error.armLoad": "부하 전원을 켜기 전에 실제 장치 제어를 허용하세요.",
  "error.monitoringSession": "먼저 장치 모니터링 수업을 선택하세요.",
  "error.droneUnassigned":
    "이 Tello는 더 이상 현재 수업에 배정되어 있지 않습니다.",
  "error.brainController": "먼저 제한된 MindWave 데모 컨트롤러를 배정하세요.",
  "error.startDemo": "데모를 준비하기 전에 수업을 시작하세요.",
  "error.armFlight": "비행을 준비하기 전에 실제 장치 제어를 허용하세요.",
  "error.fleetLesson": "먼저 ‘장치와 안전 데모’ 수업을 선택하세요.",
  "error.fleetController": "먼저 제한된 순차 드론 컨트롤러를 배정하세요.",
  "error.startSequence": "순차 비행을 준비하기 전에 수업을 시작하세요.",
  "error.auth":
    "접속 코드가 올바르지 않거나 만료되었습니다. CIT 실행기에서 수업 제어를 다시 여세요.",
  "error.physicalDisabled":
    "로컬 런타임에서 실제 장치 제어가 잠겨 있습니다. 실제 장치를 사용하도록 CIT를 다시 시작하거나 시뮬레이터를 사용하세요.",
  "error.sessionInactive": "이 장치를 사용하기 전에 수업을 시작하세요.",
  "error.nodeUnavailable":
    "장치 연결이 끊어졌습니다. 전원과 어댑터를 확인한 뒤 새로고침하세요.",
  "error.rolesMissing": "수업을 시작하기 전에 필수 장치를 모두 연결하세요.",
  "error.requestFailed": "Fabric 요청에 실패했습니다.",
  "guide.find.title": "교실 장치 찾기",
  "guide.find.description":
    "오늘 사용할 장치의 전원을 켜고 USB 장치를 연결한 뒤 CIT가 이 컴퓨터와 로컬 연결을 확인하도록 하세요.",
  "guide.choose.title": "오늘의 수업 선택",
  "guide.choose.description":
    "아래에서 활동을 고르세요. CIT가 안전한 수업 세션을 만들고 맞는 장치를 찾습니다.",
  "guide.ended.title": "이 수업은 끝났습니다",
  "guide.ended.description":
    "새 세션을 만들 수업을 선택하세요. 연결된 장치는 그대로 사용할 수 있습니다.",
  "guide.connect.title": "장치 {count}대 더 연결",
  "guide.connect.description":
    "빈 역할마다 연결된 장치를 선택하세요. 목록이 비어 있으면 해당 장치의 CIT 어댑터를 시작한 뒤 새로고침하세요.",
  "guide.safety.title": "장치 허용 전 안전 확인",
  "guide.safety.description":
    "교실을 확인하고 비상 정지 버튼을 보이게 둔 다음 실제 장치 제어 허용 여부를 확인하세요.",
  "guide.teach.title": "수업 진행 중",
  "guide.teach.description":
    "장치가 준비되었습니다. 아래 수업 제어를 사용하고 수업이 끝나면 세션을 종료하세요.",
  "guide.ready.title": "모두 준비되었습니다",
  "guide.ready.description":
    "요약을 확인한 뒤 학생들이 준비되면 수업을 시작하세요.",
  "guide.action.find": "장치 찾기",
  "guide.action.choose": "수업 선택",
  "guide.action.connect": "장치 선택",
  "guide.action.teach": "실시간 제어로 이동",
  "guide.action.ended": "다른 수업 준비",
  "guide.action.review": "확인 후 시작",
  "guide.progress": "수업 준비 진행 상황",
  "guide.step.find": "장치 찾기",
  "guide.step.choose": "수업 선택",
  "guide.step.assign": "장치 배정",
  "guide.step.safety": "안전 확인",
  "guide.step.teach": "수업 진행",
  "discovery.step": "1단계",
  "discovery.title": "교실 장치 찾기",
  "discovery.intro":
    "장치 전원을 켜고 USB 장치를 연결한 뒤 ‘장치 찾기’를 선택하세요. CIT는 현재 USB와 Bluetooth 연결, Wi-Fi 경로, 로컬 서비스, USB 또는 Wi-Fi 디버깅으로 승인된 Android 휴대전화를 확인합니다.",
  "discovery.checking": "확인 중…",
  "discovery.find": "장치 찾기",
  "discovery.noMovement": "어떤 장치도 움직이거나 날거나 켜지지 않습니다",
  "discovery.safeTitle": "안전한 검색만 수행",
  "discovery.safeBody":
    "장치 찾기는 로봇을 활성화하거나, 프로펠러를 돌리거나, 모터를 움직이거나, 플러그를 켜거나, 에이전트를 시작하거나, 원본 음성·영상·생체 신호를 저장하지 않습니다.",
  "discovery.connectionsReady": "안전하게 연결할 수 있는 항목 {count}개",
  "discovery.connectAllHelp":
    "확인된 어댑터를 한 번에 연결합니다. 로봇, 드론, 플러그와 수업 세션은 계속 잠긴 상태입니다.",
  "discovery.aircraftGrounded":
    "모든 드론이 바닥에 있고 프로펠러가 제거되었거나 보호되어 있습니다.",
  "discovery.connecting": "연결 중…",
  "discovery.connectAll": "사용 가능한 장치 모두 연결",
  "discovery.offState": "움직임 없음 · 승인된 플러그는 전원 꺼짐 상태",
  "discovery.startHost": "먼저 실제 장치 호스트를 시작하세요",
  "discovery.checked": "{time}에 확인",
  "discovery.notChecked": "아직 확인하지 않음",
  "discovery.physicalAvailable": "실제 장치 제어 사용 가능 · 현재 잠김",
  "discovery.physicalDisabled":
    "이 런타임에서는 실제 장치 제어를 사용할 수 없음",
  "discovery.warningTitle": "일부 확인 항목에 주의가 필요합니다",
  "discovery.warningBody":
    "하나 이상의 로컬 확인 항목에 주의가 필요합니다. 원문은 기술 진단에서 확인하세요.",
  "discovery.loading": "장치 목록 불러오는 중",
  "discovery.loadingHelp": "지원되는 하드웨어 목록을 준비하고 있습니다.",
  "discovery.empty": "이 그룹에 표시할 지원 장치가 아직 없습니다.",
  "discovery.signal": "신호 {percent}%",
  "discovery.connect": "연결",
  "discovery.copySetup": "설정 명령 복사",
  "discovery.connectionDetails": "연결 정보",
  "discovery.whatToDo": "무엇을 해야 하나요?",
  "discovery.nodes": "CIT 노드: {nodes}",
  "discovery.summary.connected": "CIT 노드 {count}개가 연결되어 있습니다.",
  "discovery.summary.found":
    "Windows 또는 로컬 서비스에서 맞는 하드웨어를 찾았습니다. 수업에서 사용하기 전에 카드의 연결 단계를 완료하세요.",
  "discovery.summary.ready":
    "이 컴퓨터는 준비되었습니다. 장치 전원을 켜거나 남은 설정 단계를 완료하세요.",
  "discovery.summary.missing":
    "현재 맞는 장치가 보이지 않습니다. 설정 단계를 따른 뒤 다시 찾으세요.",
  "candidate.attached":
    "Windows에서 이 장치가 연결된 것을 확인했습니다. 실제 준비 상태는 CIT 어댑터가 다시 확인합니다.",
  "candidate.connected":
    "현재 로컬 연결을 찾았습니다. 앱 준비 상태는 CIT 어댑터가 다시 확인합니다.",
  "candidate.recent":
    "최근에 사용한 장치입니다. 수업을 시작하기 전에 다시 연결하세요.",
  "candidate.visible":
    "근처에서 장치가 보입니다. 연결하기 전에 정확한 교실 장치인지 확인하세요.",
  "candidate.paired":
    "Windows에 페어링된 장치입니다. 수업에 사용하려면 CIT 어댑터를 시작하세요.",
  "candidate.provisioned":
    "설정은 저장되어 있지만 현재 연결 상태를 확인해야 합니다.",
  "candidate.ready": "필요한 로컬 서비스가 준비되었습니다.",
  "candidate.generic":
    "읽기 전용 검색 정보가 있습니다. 실제 장치는 어댑터 핸드셰이크로 확인합니다.",
  "link.attached": "현재 연결됨",
  "link.connected": "현재 접속됨",
  "link.recent": "최근 사용",
  "link.visible": "근처에서 보임",
  "link.paired": "페어링됨",
  "link.provisioned": "설정됨",
  "link.ready": "컴퓨터 준비됨",
  "io.input.title": "입력",
  "io.input.discovery":
    "수업에 제스처, 음성 의도, 버튼 또는 센서 값을 보냅니다.",
  "io.input.role": "수업의 시작 신호나 센서 값을 제공하는 장치",
  "io.input.label": "입력 전용",
  "io.bidirectional.title": "입력 + 출력",
  "io.bidirectional.discovery":
    "상태나 상호작용을 보내고 제한된 지시도 받습니다.",
  "io.bidirectional.role": "정보를 보내고 동작 지시도 받는 장치",
  "io.bidirectional.label": "입력 + 출력",
  "io.output.title": "출력",
  "io.output.discovery": "화면 표시나 액추에이터처럼 수업 지시만 받습니다.",
  "io.output.role": "수업의 제한된 동작을 실행하는 장치",
  "io.output.label": "출력 전용",
  "status.connected": "연결됨",
  "status.found": "발견됨",
  "status.ready": "컴퓨터 준비됨",
  "status.setup": "설정 필요",
  "status.notFound": "찾지 못함",
  "status.unavailable": "사용할 수 없음",
  "status.notChecked": "확인 전",
  "status.none": "아직 없음",
  "status.notSetUp": "설정 안 됨",
  "status.selectLesson": "수업 선택",
  "status.enabled": "허용됨",
  "status.locked": "잠김",
  "status.optional": "선택 사항",
  "status.assigned": "배정됨",
  "status.notIncluded": "포함 안 됨",
  "overview.devices": "연결된 장치",
  "overview.lesson": "현재 수업",
  "overview.lessonStatus": "수업 상태",
  "overview.physical": "실제 장치",
  "lesson.step2": "2단계",
  "lesson.chooseTitle": "수업 선택",
  "lesson.choosePrompt": "오늘 학생들과 무엇을 할까요?",
  "lesson.selected": "선택됨",
  "lesson.choose": "선택",
  "lesson.settings": "교실 및 장치 설정",
  "lesson.site": "사이트",
  "lesson.room": "교실",
  "lesson.devicesUsed": "이 수업에서 사용할 장치",
  "lesson.simulation": "시뮬레이터만 사용 · 연습에 가장 안전",
  "lesson.physical": "실제 교실 장치 사용 · 안전 확인 필요",
  "lesson.setup": "이 수업 설정",
  "lesson.continue": "이미 설정한 세션 이어서 사용",
  "lesson.existing": "기존 세션 선택",
  "lesson.step3": "3단계",
  "lesson.assignTitle": "수업 장치 배정",
  "lesson.assignIntro":
    "CIT는 이 수업의 각 역할을 수행할 수 있는 장치만 보여 줍니다.",
  "lesson.chooseFirst": "먼저 수업을 선택하고 설정하세요",
  "lesson.matchesAppear": "조건에 맞는 장치가 여기에 자동으로 표시됩니다.",
  "role.deviceFor": "{role} 역할 장치",
  "role.noMatch": "조건에 맞는 연결 장치 없음",
  "role.chooseDevice": "장치 선택",
  "role.useDevice": "이 장치 사용",
  "role.change": "변경",
  "role.startAdapter":
    "장치의 CIT 어댑터를 시작한 뒤 페이지 위쪽의 새로고침을 선택하세요.",
  "parallel.runsTogether": "동시에 실행",
  "parallel.title": "동시 출력 계획",
  "parallel.assigned": "{ready}/{total} 배정됨",
  "parallel.description":
    "{trigger} 입력 하나를 아래에서 배정한 모든 출력으로 동시에 보냅니다. 배정하지 않은 선택 출력은 건너뜁니다.",
  "parallel.safety":
    "명령은 동시에 시작하지만 출력마다 기능 확인, 안전 판단, 제어 임대, 실행 결과와 비상 정지 경로가 따로 적용됩니다. Tello 이륙에는 아래의 별도 드론 안전 확인도 필요합니다.",
  "safety.step4": "4단계",
  "safety.title": "검토 후 시작",
  "safety.setupFirst": "계속하려면 수업을 설정하세요",
  "safety.simulation": "시뮬레이션 모드 · 실제 장치는 계속 잠김",
  "safety.enabled": "실제 장치 제어가 허용되었습니다",
  "safety.locked": "실제 장치가 잠겨 있습니다",
  "safety.physicalHelp":
    "‘모든 장치 정지’ 버튼을 항상 보이게 두고 활동 구역이 비어 있는지 확인하세요.",
  "safety.simulationHelp":
    "실제 교실 장치로 전환하기 전에 안전하게 연습하세요.",
  "safety.confirm":
    "장치가 보이고 활동 구역이 비어 있으며 ‘모든 장치 정지’ 버튼의 위치를 알고 있습니다.",
  "safety.pauseEnable": "잠시 일시 정지하고 실제 장치 제어 허용",
  "safety.enable": "실제 장치 제어 허용",
  "safety.lock": "실제 장치 잠금",
  "safety.resume": "수업 다시 시작",
  "safety.start": "수업 시작",
  "safety.pause": "수업 일시 정지",
  "safety.end": "수업 종료 및 장치 잠금",
  "test.step5": "5단계",
  "test.title": "수업 진행 및 확인",
  "test.runningHelp":
    "수업이 진행 중입니다. 오늘 활동에 맞는 확인 기능만 사용하세요.",
  "test.waitingHelp":
    "4단계에서 수업을 시작하면 수업 제어를 사용할 수 있습니다.",
  "test.input": "학생 입력 확인",
  "test.inputHelp": "제스처, 버튼 또는 음성 입력을 요청하세요",
  "test.agent": "코딩 도우미 확인",
  "test.agentHelp": "안전한 연결 확인 메시지 한 개 보내기",
  "test.glasses": "안경 화면 확인",
  "test.glassesHelp": "고정된 교실 메시지 한 개 표시",
  "test.robotStop": "로봇 정지 확인",
  "test.robotStopHelp": "로봇이 안전 정지 명령을 받는지 확인",
  "test.running": "수업 진행 중",
  "test.waiting": "수업 제어 대기 중",
  "test.inProgress": "진행 중인 장치 동작 {count}개",
  "test.agentPrompt": "CIT Fabric 연결 확인을 짧게 답변해 주세요.",
  "test.displayMessage": "CIT Fabric 화면 연결 시험",
  "media.eyebrow": "교실 영상",
  "media.title": "실시간 카메라 및 물체 인식",
  "media.intro":
    "Meta 안경, RoboMaster, Tello 및 승인된 로컬 카메라 영상을 한곳에 표시합니다. 프레임은 메모리에만 있으며 수업 기록에 추가되지 않고 다음 프레임으로 교체됩니다.",
  "media.connectMeta": "Meta 안경 카메라 연결",
  "media.connectMetaHelp":
    "휴대전화를 교실 Wi-Fi에 두고 CIT Meta Camera 앱을 페어링하세요. 휴대전화에서 실시간 공유를 시작하고, 오래된 안경 펌웨어에서는 스냅샷 대체 방식을 사용할 수 있습니다.",
  "media.createPairing": "휴대전화 페어링 만들기",
  "media.pairStep1": "Android 휴대전화에서 CIT Meta Camera를 여세요.",
  "media.pairStep2": "아래의 교실 주소와 일회용 코드를 입력하세요.",
  "media.pairStep3":
    "페어링을 누르고 Meta 카메라 접근을 허용한 뒤 실시간 카메라 공유를 누르세요. 실시간 프레임이 실패할 때만 스냅샷 방식을 사용하세요.",
  "media.address": "교실 주소",
  "media.code": "일회용 페어링 코드",
  "media.copy": "복사",
  "media.expiry":
    "{time}에 만료되며 한 번만 사용할 수 있습니다. 휴대전화는 {site}/{room}에 게시만 할 수 있고 카메라를 읽거나 장치를 제어할 수 없습니다.",
  "media.replaceCode": "새 코드로 교체",
  "media.none": "아직 영상을 보내는 카메라가 없습니다.",
  "media.noneHelp":
    "승인된 카메라 브리지를 시작하세요. Meta 안경은 CIT 휴대전화 앱, 카메라 권한 및 화면에 보이는 카메라 사용 표시가 필요합니다.",
  "media.privacy":
    "물체 인식 결과만으로 로봇, 드론 또는 플러그가 작동하지 않습니다. 강사가 결과를 확인하고 제한된 제어 버튼을 직접 눌러야 합니다.",
  "media.waitFrame": "첫 프레임 대기 중",
  "media.live": "실시간",
  "media.waiting": "대기 중",
  "media.captureVideo": "실시간 프레임",
  "media.captureSnapshot": "스냅샷 대체",
  "media.latestAlt": "{name}의 최신 화면",
  "media.noDimensions": "영상 크기 정보 없음",
  "media.noFrame": "받은 프레임 없음",
  "media.updated": "{time}에 갱신",
  "media.recognize": "램프, 드론 및 로봇 인식",
  "media.noneFound": "설정된 물체를 찾지 못함",
  "media.objectsFound": "찾은 물체",
  "media.assignPlug": "승인된 램프를 제어하려면 교실 플러그 수업을 배정하세요.",
  "media.explicitPlug": "{name} 강사 직접 제어",
  "media.plugOn": "연결된 플러그 켜기",
  "media.plugOff": "연결된 플러그 끄기",
  "media.droneAdvisory":
    "드론 인식은 참고 정보입니다. 제한된 드론 제어에는 배정되고 활성화된 비행 수업을 사용하세요. 영상 인식으로 드론을 활성화하거나 비행시킬 수 없습니다.",
  "media.noMappedAction":
    "이 물체 종류에는 장치 동작이 연결되어 있지 않습니다. 사용할 수 있다면 배정된 수업 제어를 사용하세요.",
  "sensor.eyebrow": "실시간 센서",
  "sensor.title": "교실 측정값",
  "sensor.intro":
    "어댑터가 보내는 최신 LEGO, 로봇, 생체 신호 및 배터리 측정값을 자동으로 표시합니다.",
  "sensor.none": "선택한 수업에 아직 센서 값이 들어오지 않았습니다.",
  "plug.eyebrow": "수업 제어",
  "plug.title": "교실 플러그",
  "plug.noneAssigned": "배정된 교실 플러그 없음",
  "plug.compatible": "호환 장치 {count}개 연결됨",
  "plug.stateUnknown": "이 수업에서 아직 상태를 확인하지 못했습니다",
  "plug.observed": "{time}에 확인{source}",
  "plug.turnOn": "켜기",
  "plug.turnOnHelp": "승인된 교실 부하 켜기",
  "plug.afterSafety": "수업 안전 확인 후 사용 가능",
  "plug.turnOff": "끄기",
  "plug.turnOffHelp": "안전 상태이므로 언제나 사용 가능",
  "plug.onState": "켜짐",
  "plug.offState": "꺼짐",
  "plug.help":
    "승인된 교실 부하만 사용하세요. 실제 장치 제어가 잠겨 있어도 강사는 언제든 끌 수 있습니다.",
  "nodes.eyebrow": "장치 상태",
  "nodes.title": "이 교실에 연결된 모든 장치",
  "nodes.intro":
    "안경, 센서, 로봇, 스마트 플러그, 코딩 도우미와 시뮬레이터는 CIT 어댑터가 실행되면 여기에 표시됩니다.",
  "nodes.simulator": "시뮬레이터",
  "nodes.physical": "실제 장치",
  "nodes.technical": "기술 정보",
  "nodes.host": "호스트",
  "nodes.sends": "보내는 기능",
  "nodes.receives": "받는 기능",
  "nodes.empty": "이 그룹에 장치가 아직 없습니다.",
  "nodes.none": "없음",
  "diagnostics.title": "기술 진단",
  "diagnostics.subtitle": "신호, 명령 기록, 식별자 및 감사 기록",
  "diagnostics.signalEyebrow": "장치 신호",
  "diagnostics.signalTitle": "최근 활동",
  "diagnostics.noSignals": "선택한 수업에 아직 신호가 없습니다.",
  "diagnostics.commandEyebrow": "장치 지시",
  "diagnostics.commandTitle": "명령 진행 상황",
  "diagnostics.noCommands": "아직 명령 판단 기록이 없습니다.",
  "diagnostics.offlineEyebrow": "어댑터 기록",
  "diagnostics.offlineTitle": "오프라인 기록 {count}개 숨김",
  "diagnostics.offlineHelp":
    "연결이 끊긴 어댑터 기록은 진단과 감사를 위해 남겨 두지만 연결 장치 수와 수업 배정 목록에서는 제외합니다.",
  "diagnostics.auditEyebrow": "감사 기록",
  "diagnostics.auditTitle": "최근 제어 변경",
  "matter.add": "Matter 플러그 추가",
  "matter.addAnother": "Matter 플러그 하나 더 추가",
  "matter.help":
    "플러그의 페어링 버튼을 표시등이 깜박일 때까지 누른 뒤 QR 라벨 옆에 인쇄된 Matter 코드를 입력하세요. 제조사 앱, 계정, 클라우드 API, 장치 ID 또는 로컬 키는 사용하지 않습니다.",
  "matter.code": "Matter 설정 코드",
  "matter.adding": "플러그 추가 중…",
  "matter.addLocally": "로컬로 플러그 추가",
  "matter.addAnotherButton": "플러그 하나 더 추가",
  "matter.memory":
    "설정에는 2~3분이 걸릴 수 있습니다. CIT는 이 요청 동안 코드만 페이지 메모리에 보관하고 성공하면 지웁니다.",
  "lego.setup": "이 LEGO 허브 설정",
  "lego.another": "LEGO 허브 하나 더 연결",
  "lego.help":
    "Pybricks에 표시된 정확한 Bluetooth 이름과 각 포트에 연결된 부품을 입력하세요. CIT는 가장 가까운 익명 허브를 임의로 선택하지 않습니다.",
  "lego.name": "표시되는 정확한 허브 이름",
  "lego.model": "허브 모델",
  "lego.ports": "연결 포트",
  "lego.port": "포트 {port}",
  "lego.empty": "비어 있음",
  "lego.motor": "모터",
  "lego.distance": "거리 센서",
  "lego.color": "색상 센서",
  "lego.force": "힘 센서",
  "lego.connecting": "허브 연결 중…",
  "lego.connect": "저장하고 허브 연결",
  "lego.safety":
    "처음에는 모터가 잠긴 센서 모니터링만 시작합니다. 센서 전용 허브도 지원합니다. 모터가 연결되어 있으면 첫 시험에서 바퀴를 들어 두세요. 움직이려면 별도로 실제 장치를 허용한 수업이 필요합니다.",
  "wonder.setup": "연결할 정확한 로봇 선택",
  "wonder.setupHelp":
    "이번 검색에서 발견된 로봇만 선택할 수 있습니다. 이름과 신호 세기로 실제 로봇을 확인하세요. CIT는 가장 가까운 로봇을 자동 선택하지 않습니다.",
  "wonder.noneVisible":
    "아직 정확히 선택할 수 있는 로봇이 없습니다. Dash 또는 Dot 전원을 켜고 다른 로봇 앱을 닫은 뒤 ‘장치 찾기’를 다시 선택하세요.",
  "wonder.selectExact": "보이는 Dash 및 Dot 로봇",
  "wonder.dash": "Dash · 주행, 머리, 조명, 소리, 센서",
  "wonder.dot": "Dot · 조명, 소리, 센서(주행 없음)",
  "wonder.connecting": "선택한 로봇 연결 중…",
  "wonder.connectSelected": "선택한 로봇 연결",
  "wonder.connectSafety":
    "연결하면 센서 모니터링만 시작합니다. 이동, 머리, 조명 또는 소리 명령은 보내지 않습니다.",
  "wonder.eyebrow": "로봇 제어",
  "wonder.title": "Wonder Workshop Dash 및 Dot",
  "wonder.help":
    "실행 중인 수업에서는 조명을 사용할 수 있습니다. 소리, Dash 머리 이동 및 짧은 주행은 실행 중이며 실제 장치 제어가 허용된 수업에서만 가능합니다. Dot에는 주행 제어가 없습니다.",
  "wonder.lights": "조명",
  "wonder.sounds": "고정 교실 소리",
  "wonder.color.blue": "파랑",
  "wonder.color.orange": "주황",
  "wonder.color.green": "초록",
  "wonder.color.off": "조명 끄기",
  "wonder.soundLabel": "소리 {number}",
  "wonder.drive": "Dash 짧은 이동",
  "wonder.forward": "앞으로",
  "wonder.backward": "뒤로",
  "wonder.left": "왼쪽",
  "wonder.right": "오른쪽",
  "wonder.stop": "정지",
  "wonder.nudge":
    "화살표를 누를 때마다 짧게 이동합니다. 승인된 다음 명령이 없으면 Dash가 350ms 이내에 로컬에서 정지합니다.",
  "wonder.head": "Dash 머리",
  "wonder.center": "가운데",
  "wonder.up": "위",
  "wonder.down": "아래",
  "wonder.locked":
    "잠김: 모니터링 수업을 시작하고 ‘실제 장치 제어 허용’을 선택한 뒤 주변 공간 안전 확인을 완료하세요.",
  "drone.eyebrow": "안전 제어",
  "drone.title": "Tello 안전 상태 제어",
  "drone.help":
    "이 모니터링 기능은 배정된 드론에 착륙 또는 비상 정지를 요청할 수 있습니다. 이륙, 이동, 회전 또는 활성화는 할 수 없습니다.",
  "drone.role": "안전 드론 {number}",
  "drone.land": "착륙",
  "drone.landHelp": "정상 착륙 요청",
  "drone.emergency": "모터 비상 정지",
  "drone.emergencyHelp":
    "비행을 계속하는 것보다 모터 정지가 더 안전할 때만 사용",
  "drone.confirm":
    "{name}의 모터를 비상 정지할까요? 비행 중인 드론은 즉시 떨어질 수 있습니다.",
  "brain.eyebrow": "MindWave 안내 데모",
  "brain.title": "신호 한 번으로 실행하는 제한된 Tello 데모",
  "brain.simulation": "시뮬레이션 · 어떤 드론도 움직이지 않음",
  "brain.physical": "실제 비행",
  "brain.help":
    "제조사에서 제공하는 MindWave 신호와 임계값을 고르세요. 활성화하면 조건을 만족하는 신호 하나를 기다렸다가 Brain2Devices를 한 번 실행하고 자동으로 해제합니다. 지속적인 뇌파 제어가 아니며 수동 이륙이나 이동 명령을 제공하지 않습니다.",
  "brain.current": "현재 상태",
  "brain.progress": "진행률",
  "brain.waiting": "컨트롤러의 첫 상태 업데이트를 기다리는 중입니다.",
  "brain.chooseSignal": "1. 1회 데모를 시작할 조건 선택",
  "brain.attention": "Attention(NeuroSky eSense)",
  "brain.attentionHelp":
    "이 값보다 계속 높아야 합니다. 제조사에서 만든 상호작용 신호이며 객관적인 집중도 측정값이 아닙니다.",
  "brain.meditation": "Meditation(NeuroSky eSense)",
  "brain.meditationHelp":
    "이 값보다 계속 높아야 합니다. Attention과 별도로 표시됩니다.",
  "brain.blink": "눈 깜박임 강도",
  "brain.blinkHelp":
    "임계값보다 높은 새 눈 깜박임 한 번이면 즉시 조건을 만족합니다. 유지 시간은 적용되지 않습니다.",
  "brain.threshold": "{label} 임계값",
  "brain.hold": "Attention 또는 Meditation을 임계값보다 높게 유지",
  "brain.seconds": "초",
  "brain.dwellHelp":
    "첫 실제 장치 시험에서는 2초를 권장합니다. 0초는 조건을 만족하는 첫 샘플을 즉시 받습니다.",
  "brain.flightCheck": "2. 강사 비행 확인 · 세 항목 모두 필요",
  "brain.present": "제가 현장에서 이 비행을 감독하고 있습니다.",
  "brain.areaClear":
    "전체 비행 구역이 비어 있고 보이는 모든 Tello를 확인했으며 바닥에 있습니다.",
  "brain.emergencyReady":
    "착륙과 비상 정지에 바로 접근할 수 있으며, 빠른 전달 뒤 해제된 드론은 현재 Wi-Fi 어댑터에서 더 이상 연결되지 않을 수 있음을 이해했습니다.",
  "brain.runSimulation": "안전한 시뮬레이션 실행",
  "brain.arm": "1회 비행 데모 준비",
  "brain.waitCondition": "선택한 MindWave 조건을 기다립니다",
  "brain.startFirst": "먼저 수업을 시작하세요",
  "brain.startArmFirst": "먼저 수업을 시작하고 실제 장치 제어를 허용하세요",
  "brain.stop": "데모 정지 및 해제",
  "brain.stopHelp":
    "조건 대기 전이나 실행 중에도 사용할 수 있는 안전 상태 명령",
  "fleet.eyebrow": "다중 입력 드론 순차 비행",
  "fleet.title": "확인된 Tello를 한 대씩 순서대로 이륙",
  "fleet.helpBefore":
    "먼저 순서를 정해 한 번만 실행할 계획을 준비하세요. 그다음",
  "fleet.startNow": "지금 시작",
  "fleet.helpAfter":
    "버튼, Leap의 손 펼침→집기 제스처 또는 배정된 G2/Meta 안경의 ‘드론 순차 비행 시작’ 음성을 사용하세요. 입력은 비행을 활성화할 수 없으며 강사가 현재 준비한 1회 계획만 실행할 수 있습니다.",
  "fleet.current": "현재 상태",
  "fleet.airborne": "이륙 확인됨",
  "fleet.waiting": "드론 컨트롤러의 첫 상태 업데이트를 기다리는 중입니다.",
  "fleet.order": "1. 이륙 순서 선택(맨 위가 먼저)",
  "fleet.connectController":
    "승인된 드론 목록을 보려면 Brain2Devices 드론 컨트롤러를 연결하세요.",
  "fleet.aircraftState": "{connection} · {flight} · 배터리 {battery}%",
  "fleet.earlier": "{name}을(를) 앞 순서로 이동",
  "fleet.later": "{name}을(를) 뒤 순서로 이동",
  "fleet.remove": "제외",
  "fleet.interval": "이륙 확인 후 다음 이륙까지 초",
  "fleet.minimumBattery": "모든 드론의 최소 배터리",
  "fleet.inputs": "2. 이 1회 실행을 시작할 수 있는 입력 선택",
  "fleet.tutorButton": "강사의 ‘지금 시작’ 버튼",
  "fleet.noInputs":
    "Leap, G2 또는 Meta 입력이 배정되지 않았습니다. 강사 버튼은 계속 사용할 수 있습니다.",
  "fleet.flightCheck": "3. 강사 비행 확인 · 네 항목 모두 필요",
  "fleet.present": "제가 현장에서 모든 드론을 감독하고 있습니다.",
  "fleet.areaClear":
    "전체 비행 구역이 비어 있고 선택한 모든 드론이 바닥에 있는 것을 직접 확인했습니다.",
  "fleet.emergencyReady":
    "‘정지 및 착륙’과 각 드론의 비상 제어에 바로 접근할 수 있습니다.",
  "fleet.routes":
    "기본 Tello마다 연결된 Wi-Fi 경로가 하나씩 있거나 스테이션 모드 드론마다 서로 다른 접근 가능한 주소가 있습니다.",
  "fleet.notReady":
    "선택한 모든 드론이 연결되고 착륙 상태가 확인되며 최소 배터리 이상이어야 합니다.",
  "fleet.arm": "이 순차 비행 1회 준비",
  "fleet.armHelp": "아직 이륙하지 않음 · 60초 후 만료",
  "fleet.startArmFirst": "먼저 수업을 시작하고 실제 장치를 허용하세요",
  "fleet.startHelp": "Leap 및 안경과 같은 제한 명령을 사용합니다",
  "fleet.stop": "선택한 드론 정지 및 착륙",
  "fleet.stopHelp": "아직 시작하지 않은 이륙도 취소합니다",
  "fleet.leapInstruction": "손을 펼친 뒤 집기",
  "fleet.voiceInstruction": "‘드론 순차 비행 시작’이라고 말하기",
  "course.deviceMonitoring.name": "장치, 센서, 카메라 및 안전 데모",
  "course.deviceMonitoring.summary": "카메라, 센서 및 제한된 드론 데모",
  "course.deviceMonitoring.description":
    "카메라, Tello 텔레메트리, MindWave 제조사 신호와 LEGO 센서 값을 보여 줍니다. 선택 기능으로 명시적으로 활성화하는 MindWave 데모와 버튼, Leap, G2 또는 Meta로 시작하는 강사 승인 순차 드론 비행을 제공합니다.",
  "course.glasses.name": "안경과 코딩 도우미",
  "course.glasses.summary": "안경 + 코딩 도우미",
  "course.glasses.description":
    "학생이 안경에서 코딩 도우미에게 요청을 보내고 교실 화면에서 답변을 확인합니다.",
  "course.gesture.name": "제스처로 로봇 제어",
  "course.gesture.summary": "제스처 + 교실 로봇",
  "course.gesture.description":
    "학생이 손 제스처로 교실 로봇을 조종하고 CIT가 움직임을 수업 안전 범위로 제한합니다.",
  "course.simultaneous.name": "여러 장치 동시 실행",
  "course.simultaneous.summary": "입력 하나 + 여러 동시 출력",
  "course.simultaneous.description":
    "승인된 Leap 또는 안경 입력 하나로 배정된 RoboMaster, LEGO 허브, 활성화된 Tello 그룹, Meta 화면과 G2 화면에 제한된 동작을 동시에 보냅니다. 모든 출력은 따로 안전 검사를 받습니다.",
  "course.plug.name": "교실 스마트 플러그",
  "course.plug.summary": "강사가 제어하는 교실 플러그",
  "course.plug.description":
    "강사가 이 화면에서 승인된 교실 램프 또는 다른 저위험 부하를 켜고 끕니다.",
  "course.fallback": "교실 장치 역할 {count}개",
  "role.brain.name": "MindWave 1회 비행 데모",
  "role.brain.description":
    "강사가 설정한 MindWave 임계값을 한 번 기다린 뒤 제한된 Brain2Devices 데모를 실행하고 자동으로 해제합니다",
  "role.biosignal.name": "MindWave 헤드셋",
  "role.biosignal.description":
    "원본 EEG 없이 제조사 표시 MindWave 값만 보냅니다",
  "role.fleet.name": "순차 드론 컨트롤러",
  "role.fleet.description":
    "강사가 준비한 1회 이륙 순서를 관리하고 다음 단계 전에 각 드론을 확인합니다",
  "role.plug.name": "교실 플러그",
  "role.plug.description": "승인된 교실 부하 한 개를 켜거나 끕니다",
  "role.agent.name": "코딩 도우미",
  "role.agent.description": "학생 요청을 받고 코딩 진행 상황을 돌려줍니다",
  "role.feedback.name": "피드백 화면",
  "role.feedback.description": "코딩 진행 상황과 수업 메시지를 표시합니다",
  "role.gesture.name": "제스처 입력 장치",
  "role.gesture.description": "손 움직임을 수업에 보냅니다",
  "role.console.name": "강사 화면",
  "role.console.description": "강사에게 수업 활동을 보여 줍니다",
  "role.glasses.name": "학생 안경",
  "role.glasses.description": "학생 입력을 보내고 수업 피드백을 표시합니다",
  "role.robot.name": "교실 로봇",
  "role.robot.description": "제한된 이동 및 정지 지시를 받습니다",
  "role.safetyDrone.name": "안전 드론 {number}",
  "role.safetyDrone.description":
    "Tello 상태를 보내고 착륙 또는 비상 정지만 받습니다",
  "role.fleetInput.name": "드론 시작 입력 {number}",
  "role.fleetInput.description":
    "Leap, G2 또는 Meta를 통해 현재 준비된 순차 비행을 요청합니다",
  "role.groundOutput.name": "지상 로봇 출력 {number}",
  "role.groundOutput.description":
    "동일한 제한 속도 및 감시 타이머가 적용된 이동 신호를 받습니다. RoboMaster 또는 이동형 LEGO 허브를 배정하세요",
  "role.messageOutput.name": "안경 메시지 출력 {number}",
  "role.messageOutput.description":
    "동일한 고정 수업 메시지를 받습니다. G2 또는 Meta 안경을 배정하세요",
  "role.robotSensor.name": "로봇 센서 {number}",
  "role.robotSensor.description":
    "LEGO 또는 로봇의 센서 및 배터리 값을 보냅니다",
  "role.fallback.description": "수업에서 이 역할을 담당합니다",
  "session.notStarted": "시작 전",
  "session.draft": "장치 필요",
  "session.ready": "시작 준비됨",
  "session.active": "진행 중",
  "session.paused": "일시 정지",
  "session.stopped": "종료됨",
  "session.emergency": "비상 정지됨",
  "session.failed": "확인 필요",
  "connection.connected": "연결됨",
  "connection.degraded": "연결됨 · 확인 필요",
  "connection.unavailable": "사용할 수 없음",
  "connection.disconnected": "연결 끊김",
  "connection.connecting": "연결 중",
  "health.healthy": "정상",
  "health.degraded": "확인 필요",
  "health.unhealthy": "작동하지 않음",
  "health.unknown": "상태 알 수 없음",
  "command.success": "{label}: 정상 완료했습니다.",
  "command.failed":
    "{label}: 완료하지 못했습니다. 기술 진단에서 자세한 내용을 확인하세요.",
  "command.stopped":
    "{label}: 완료 전에 중지되었습니다. 다시 시도하거나 장치를 확인하세요.",
  "command.sent": "{label}: 장치에 보냈습니다.",
};

const CATALOGS: Record<Locale, Record<FabricMessageKey, string>> = {
  en: EN,
  ko: KO,
};

export type FabricTranslate = (
  key: FabricMessageKey,
  values?: Record<string, string | number>,
) => string;

export const translateFabric = (
  locale: Locale,
  key: FabricMessageKey,
  values?: Record<string, string | number>,
): string => {
  const message = CATALOGS[locale][key] ?? EN[key] ?? key;
  if (values === undefined) return message;
  return Object.entries(values).reduce(
    (text, [name, value]) => text.replaceAll(`{${name}}`, String(value)),
    message,
  );
};

export const fabricTranslatorFor =
  (locale: Locale): FabricTranslate =>
  (key, values) =>
    translateFabric(locale, key, values);

export const fabricMessageKeys = (): FabricMessageKey[] =>
  Object.keys(EN) as FabricMessageKey[];

export const fabricCatalog = (
  locale: Locale,
): Record<FabricMessageKey, string> => CATALOGS[locale];

interface IntegrationCopy {
  displayName: string;
  connectionMethod: string;
  setupSteps: readonly string[];
  safetyNote: string;
}

const KO_INTEGRATIONS: Record<string, IntegrationCopy> = {
  "even-realities-g2": {
    displayName: "Even Realities G2",
    connectionMethod: "Android, Bluetooth 또는 Agent Mesh",
    setupSteps: [
      "설정 진단에는 승인된 USB 또는 Wi-Fi 디버깅 Android 휴대전화를 연결하거나 이미 설정된 Agent Mesh 휴대전화 경로를 사용하세요.",
      "휴대전화 또는 교실 호스트에서 승인된 Even 보조 브리지를 시작하세요.",
      "G2를 착용하고 음성 또는 버튼 입력이 Agent Mesh에 나타나는지 확인하세요.",
      "코딩 에이전트 카드에서 연결을 선택해 공용 브리지를 붙이세요. 이후 이 카드는 G2 상태를 따로 보여 줍니다.",
    ],
    safetyNote:
      "Fabric에는 의미 있는 상호작용과 제한된 화면 텍스트만 들어옵니다. 원본 마이크 음성은 검색하거나 기록하지 않습니다.",
  },
  "meta-rayban": {
    displayName: "Meta Ray-Ban",
    connectionMethod: "Android, Bluetooth 또는 Agent Mesh",
    setupSteps: [
      "설정 진단에는 승인된 USB 또는 Wi-Fi 디버깅 Android 휴대전화를 연결하거나 이미 설정된 Agent Mesh 경로를 사용하세요.",
      "승인된 Meta 휴대전화 브리지를 시작하고 휴대전화를 교실 네트워크에 두세요.",
      "안경을 착용하고 의미 있는 상호작용이 Agent Mesh에 나타나는지 확인하세요.",
      "에이전트 요청에는 코딩 에이전트 카드의 연결을 사용하고, 카메라 공유에는 별도 미디어 제어를 사용하세요.",
    ],
    safetyNote:
      "Agent Mesh는 의미 있는 상호작용만 전달합니다. 카메라 영상은 명시적으로 켠 미디어 앱을 사용하며 장치 검색에는 기록되지 않습니다.",
  },
  "coding-agents": {
    displayName: "Codex 및 Claude 코딩 에이전트",
    connectionMethod: "감독되는 로컬 프로세스",
    setupSteps: [
      "승인된 수업 작업 공간에서 Codex 또는 Claude를 시작하세요.",
      "연결을 선택해 승인된 실행 세션을 붙이세요.",
    ],
    safetyNote:
      "장치 검색은 에이전트를 시작하거나 파일 시스템, 셸 또는 장치 인증 권한을 부여하지 않습니다.",
  },
  "leap-motion": {
    displayName: "Leap Motion",
    connectionMethod: "USB / Ultraleap 서비스",
    setupSteps: [
      "컨트롤러를 USB에 직접 연결하고 Ultraleap Tracking을 시작하세요.",
      "컨트롤러가 발견되면 입력 연결을 선택하세요.",
    ],
    safetyNote: "검색은 추적 스트림을 열지 않으며 로봇 명령을 만들지 않습니다.",
  },
  "robomaster-s1": {
    displayName: "DJI RoboMaster S1",
    connectionMethod: "Wi-Fi, USB/RNDIS 또는 DJI 앱 브리지",
    setupSteps: [
      "첫 시험에서는 바퀴를 들어 둔 상태로 로봇 전원을 켜세요.",
      "STA, AP, RNDIS 또는 기본 S1 앱 연결 방식을 선택하세요.",
      "잠긴 상태로 연결한 뒤 수업 제어에서 실제 장치를 허용하세요.",
    ],
    safetyNote:
      "네트워크 이름만으로 로봇이라고 판단하지 않습니다. 어댑터 핸드셰이크가 실제 장치를 확인하며 이동은 계속 잠긴 상태입니다.",
  },
  "sphero-bolt": {
    displayName: "Sphero BOLT",
    connectionMethod: "Bluetooth 저전력(BLE)",
    setupSteps: [
      "BOLT를 충전하고 충전대에서 깨운 뒤 LED에 표시되는 SB-XXXX 이름을 확인하세요.",
      "현재 이 로봇에 연결된 Sphero Edu, Sphero Play 또는 다른 프로그램을 닫으세요.",
      "장치 찾기를 선택하세요. CIT Sphero 어댑터를 사용할 수 있게 되면 가장 가까운 익명 로봇이 아니라 정확한 SB-XXXX를 선택하세요.",
    ],
    safetyNote:
      "검색은 Windows Bluetooth 존재 여부만 읽습니다. 연결, 깨우기, 굴리기, 방향 지정 또는 LED 변경을 하지 않습니다. 실제 이동에는 제한된 CIT 어댑터와 허용된 수업이 필요합니다.",
  },
  "wonder-workshop-dash-dot": {
    displayName: "Wonder Workshop Dash 및 Dot",
    connectionMethod: "로컬 Bluetooth 저전력(BLE)",
    setupSteps: [
      "Dash 또는 Dot을 충전하고 전원을 켠 뒤 이 Windows 컴퓨터 가까이에 두세요.",
      "현재 로봇에 연결된 Wonder, Blockly 또는 다른 앱을 닫으세요.",
      "‘장치 찾기’를 선택하고 정확한 이름의 Dash 또는 Dot을 고른 뒤 ‘선택한 로봇 연결’을 선택하세요.",
      "센서 모니터링은 제어 잠금 상태로 시작합니다. Dash 이동, 머리 이동 및 소리는 강사가 실제 장치 제어를 허용할 때까지 잠겨 있습니다.",
    ],
    safetyNote:
      "검색은 읽기 전용이며 가장 가까운 로봇을 자동 선택하지 않습니다. Dash 이동에는 제한과 350ms 로컬 자동 정지가 적용되며 Dot에는 이동 기능이 표시되지 않습니다.",
  },
  "tello-drones": {
    displayName: "DJI / Ryze Tello 드론",
    connectionMethod: "드론마다 독립된 Wi-Fi 경로",
    setupSteps: [
      "첫 연결 시험에서는 프로펠러를 제거하고 바닥에 둔 드론의 전원을 켜세요.",
      "기본 Tello마다 물리 USB Wi-Fi 어댑터를 하나씩 사용하거나 스테이션 모드에서 서로 다른 주소를 사용하세요.",
      "바닥에 둔 드론 연결을 선택한 뒤 통합 화면에서 드론 컨트롤러와 입력을 배정하세요.",
      "비행은 네 가지 강사 확인을 거치는 별도의 1회 활성화가 필요합니다.",
    ],
    safetyNote:
      "검색과 연결은 이륙이나 이동 명령을 보내지 않습니다. 드론 노드는 상태, 착륙 및 비상 정지만 제공하며 별도 컨트롤러만 제한된 순차 비행을 제공합니다.",
  },
  "mindwave-mobile2": {
    displayName: "MindWave Mobile 2",
    connectionMethod: "ThinkGear Connector를 통한 Bluetooth",
    setupSteps: [
      "Windows Bluetooth 설정에서 MindWave Mobile 2를 페어링하세요.",
      "ThinkGear Connector를 시작하고 헤드셋의 출력 COM 포트를 선택하세요.",
      "ThinkGear Connector가 준비되면 헤드셋 연결을 선택하세요.",
    ],
    safetyNote:
      "제조사에서 이름 붙인 의미 값만 표시합니다. 원본 EEG는 보내거나 저장하지 않습니다.",
  },
  "mindwave-tello-demo": {
    displayName: "MindWave-Tello 안내 데모",
    connectionMethod: "제한된 로컬 Brain2Devices 호환 노드",
    setupSteps: [
      "위 장치 카드에서 Brain2Devices 드론 슬롯 하나와 MindWave를 연결하세요.",
      "‘장치, 센서, 카메라 및 안전 데모’ 수업에서 제한된 데모 컨트롤러를 배정하세요.",
      "먼저 시뮬레이션으로 연습하세요. 실제 활성화에는 화면의 강사 확인이 필요합니다.",
    ],
    safetyNote:
      "센서 및 드론 어댑터와 분리된 1회 실행 과정입니다. 일반 이륙이나 이동 명령이 없으며 자동 에이전트가 활성화할 수 없습니다.",
  },
  "matter-smart-plugs": {
    displayName: "Matter 스마트 플러그(클라우드 불필요)",
    connectionMethod: "로컬 Matter over Wi-Fi / IPv6",
    setupSteps: [
      "포장이나 라벨에 Matter 로고와 설정 코드가 있는 플러그를 사용하세요.",
      "교실 네트워크에서 플러그를 페어링 모드로 전환하세요.",
      "수업 제어에 인쇄된 코드를 입력하세요. 제조사 계정은 필요하지 않습니다.",
    ],
    safetyNote:
      "등록할 때 부하 전원을 켜지 않습니다. 연결하면 승인된 콘센트를 전원 꺼짐 안전 상태로 둡니다.",
  },
  "lego-hubs": {
    displayName: "LEGO SPIKE 및 MINDSTORMS",
    connectionMethod: "Bluetooth / Pybricks",
    setupSteps: [
      "지원되는 허브에 Pybricks 펌웨어를 설치하세요.",
      "각 교실 허브에 서로 다른 표시 이름을 지정하고 그 정확한 이름을 배정하세요.",
      "첫 프레임 프로토콜 시험에서는 모터나 바퀴를 들어 두세요.",
    ],
    safetyNote:
      "검색은 가장 가까운 익명 BLE 허브를 선택하지 않으며 모터를 활성화하지 않습니다.",
  },
};

const KO_ACTION_LABELS: Record<string, string> = {
  "cit.glasses-agent.connect": "안경 및 코딩 에이전트 연결",
  "cit.robomaster-leap.connect": "RoboMaster와 Leap 연결",
  "cit.matter-smart-plug.connect": "등록된 플러그 연결",
  "cit.lego-pybricks.connect": "설정된 LEGO 허브 연결",
  "brain2devices.mindwave.connect": "헤드셋 연결",
  "brain2devices.tello.connect-all": "바닥에 둔 드론 연결",
  "brain2devices.tello.connect-primary": "현재 Tello 경로 연결",
};

const localizedCandidateDetail = (
  locale: Locale,
  candidate: FabricDiscoveryCandidate,
  t: FabricTranslate,
): string => {
  if (locale === "en") return candidate.detail;
  switch (candidate.linkState) {
    case "attached":
      return t("candidate.attached");
    case "connected":
      return t("candidate.connected");
    case "recently_active":
      return t("candidate.recent");
    case "visible":
      return t("candidate.visible");
    case "paired":
      return t("candidate.paired");
    case "provisioned":
      return t("candidate.provisioned");
    case "ready":
      return t("candidate.ready");
    default:
      return t("candidate.generic");
  }
};

const localizedCandidateDisplayName = (
  locale: Locale,
  displayName: string,
): string => {
  if (locale === "en") return displayName;
  const mindWave = /^Paired MindWave device (\d+)$/.exec(displayName);
  if (mindWave !== null) return `페어링된 MindWave 장치 ${mindWave[1]}`;
  const g2 = /^Provisioned G2 companion (\d+)$/.exec(displayName);
  if (g2 !== null) return `설정된 G2 보조 앱 ${g2[1]}`;
  const meta = /^Provisioned Meta companion (\d+)$/.exec(displayName);
  if (meta !== null) return `설정된 Meta 보조 앱 ${meta[1]}`;
  return displayName;
};

const localizedCandidateTransport = (
  locale: Locale,
  transport: string,
): string => {
  if (locale === "en") return transport;
  const transports: Record<string, string> = {
    "Local Bluetooth bridge": "로컬 Bluetooth 브리지",
    "Supervised local process": "감독되는 로컬 프로세스",
    "Android companion / Agent Mesh": "Android 보조 앱 / Agent Mesh",
  };
  return transports[transport] ?? transport;
};

export const localizeFabricIntegration = (
  locale: Locale,
  integration: FabricIntegrationDiscovery,
  t: FabricTranslate = fabricTranslatorFor(locale),
): FabricIntegrationDiscovery => {
  if (locale === "en") return integration;
  const copy = KO_INTEGRATIONS[integration.integrationId];
  const summary =
    integration.status === "connected"
      ? t("discovery.summary.connected", {
          count: integration.connectedNodeIds.length,
        })
      : integration.status === "found"
        ? t("discovery.summary.found")
        : integration.status === "ready"
          ? t("discovery.summary.ready")
          : t("discovery.summary.missing");
  return {
    ...integration,
    ...(copy === undefined
      ? {}
      : {
          displayName: copy.displayName,
          connectionMethod: copy.connectionMethod,
          setupSteps: [...copy.setupSteps],
          safetyNote: copy.safetyNote,
        }),
    summary,
    candidates: integration.candidates.map((candidate) => ({
      ...candidate,
      displayName: localizedCandidateDisplayName(locale, candidate.displayName),
      transport: localizedCandidateTransport(locale, candidate.transport),
      detail: localizedCandidateDetail(locale, candidate, t),
    })),
    ...(integration.actionId === undefined
      ? {}
      : {
          actionLabel:
            KO_ACTION_LABELS[integration.actionId] ?? t("discovery.connect"),
        }),
  };
};

const COURSE_KEYS: Record<
  string,
  readonly [FabricMessageKey, FabricMessageKey, FabricMessageKey]
> = {
  "device-monitoring": [
    "course.deviceMonitoring.name",
    "course.deviceMonitoring.summary",
    "course.deviceMonitoring.description",
  ],
  "glasses-agent-control": [
    "course.glasses.name",
    "course.glasses.summary",
    "course.glasses.description",
  ],
  "gesture-ground-robot": [
    "course.gesture.name",
    "course.gesture.summary",
    "course.gesture.description",
  ],
  "simultaneous-device-cue": [
    "course.simultaneous.name",
    "course.simultaneous.summary",
    "course.simultaneous.description",
  ],
  "smart-plug-control": [
    "course.plug.name",
    "course.plug.summary",
    "course.plug.description",
  ],
};

export const fabricCourseText = (
  coursePack: CoursePack,
  t: FabricTranslate,
): { name: string; summary: string; description: string } => {
  const keys = COURSE_KEYS[coursePack.coursePackId];
  return keys === undefined
    ? {
        name: coursePack.displayName,
        summary: t("course.fallback", { count: coursePack.roles.length }),
        description:
          coursePack.description ??
          t("course.fallback", { count: coursePack.roles.length }),
      }
    : {
        name: t(keys[0]),
        summary: t(keys[1]),
        description: t(keys[2]),
      };
};

const ROLE_KEYS: Record<string, readonly [FabricMessageKey, FabricMessageKey]> =
  {
    brain_flight_demo: ["role.brain.name", "role.brain.description"],
    biosignal_input: ["role.biosignal.name", "role.biosignal.description"],
    fleet_sequence_controller: ["role.fleet.name", "role.fleet.description"],
    classroom_plug: ["role.plug.name", "role.plug.description"],
    coding_agent: ["role.agent.name", "role.agent.description"],
    feedback_display: ["role.feedback.name", "role.feedback.description"],
    gesture_input: ["role.gesture.name", "role.gesture.description"],
    instructor_console: ["role.console.name", "role.console.description"],
    primary_glasses: ["role.glasses.name", "role.glasses.description"],
    student_robot: ["role.robot.name", "role.robot.description"],
  };

export const fabricRoleText = (
  role: string,
  t: FabricTranslate,
): { name: string; description: string } => {
  const exact = ROLE_KEYS[role];
  if (exact !== undefined) {
    return { name: t(exact[0]), description: t(exact[1]) };
  }
  const dynamic = (
    expression: RegExp,
    name: FabricMessageKey,
    description: FabricMessageKey,
  ) => {
    const match = role.match(expression);
    return match === null
      ? undefined
      : {
          name: t(name, { number: match[1] ?? "" }),
          description: t(description),
        };
  };
  return (
    dynamic(
      /^safety_drone_(\d+)$/,
      "role.safetyDrone.name",
      "role.safetyDrone.description",
    ) ??
    dynamic(
      /^fleet_sequence_input_(\d+)$/,
      "role.fleetInput.name",
      "role.fleetInput.description",
    ) ??
    dynamic(
      /^ground_output_(\d+)$/,
      "role.groundOutput.name",
      "role.groundOutput.description",
    ) ??
    dynamic(
      /^message_output_(\d+)$/,
      "role.messageOutput.name",
      "role.messageOutput.description",
    ) ??
    dynamic(
      /^robot_sensor_(\d+)$/,
      "role.robotSensor.name",
      "role.robotSensor.description",
    ) ?? {
      name: role.replaceAll("_", " "),
      description: t("role.fallback.description"),
    }
  );
};

export const fabricCourseName = (
  coursePacks: CoursePack[],
  session: InteractionSession,
  t: FabricTranslate,
): string => {
  const coursePack = coursePacks.find(
    (candidate) =>
      candidate.coursePackId === session.coursePackId &&
      candidate.version === session.coursePackVersion,
  );
  return coursePack === undefined
    ? session.coursePackId.replaceAll("-", " ")
    : fabricCourseText(coursePack, t).name;
};

export const fabricSessionState = (
  session: InteractionSession | undefined,
  t: FabricTranslate,
): string => {
  if (session === undefined) return t("session.notStarted");
  const keys: Record<string, FabricMessageKey> = {
    draft: "session.draft",
    ready: "session.ready",
    active: "session.active",
    paused: "session.paused",
    stopped: "session.stopped",
    emergency_stopped: "session.emergency",
    failed: "session.failed",
  };
  const key = keys[session.state];
  return key === undefined ? session.state : t(key);
};

export const fabricConnectionState = (
  node: IntegrationNode,
  t: FabricTranslate,
): string => {
  const keys: Record<string, FabricMessageKey> = {
    connected: "connection.connected",
    degraded: "connection.degraded",
    unavailable: "connection.unavailable",
    disconnected: "connection.disconnected",
    connecting: "connection.connecting",
  };
  const key = keys[node.connectionState];
  return key === undefined ? node.connectionState : t(key);
};

export const fabricHealthState = (
  state: string,
  t: FabricTranslate,
): string => {
  const keys: Record<string, FabricMessageKey> = {
    healthy: "health.healthy",
    degraded: "health.degraded",
    unhealthy: "health.unhealthy",
    unknown: "health.unknown",
  };
  const key = keys[state];
  return key === undefined ? state : t(key);
};

export const fabricCapabilityName = (
  capability: string,
  locale: Locale,
): string => {
  const ko: Record<string, string> = {
    "interaction.intent.flight_sequence_start": "드론 순차 비행 시작 입력",
    "mobility.ground.set_velocity": "지상 로봇 속도 설정",
    "mobility.flight.fleet_sequence.start": "드론 순차 비행 시작",
    "display.text.render": "텍스트 표시",
    "agent.prompt.submit": "코딩 에이전트 요청",
    "robot.sensor.state": "로봇 센서 상태",
    "robot.light.set": "로봇 조명 설정",
    "media.audio.cue.play": "로봇 고정 소리 재생",
    "robot.head.set_pose": "로봇 머리 위치 설정",
    "telemetry.flight.state": "드론 비행 상태",
  };
  if (locale === "ko") return ko[capability] ?? capability;
  return capability
    .split(".")
    .slice(1)
    .join(" ")
    .replaceAll("_", " ")
    .replace(/^./, (first) => first.toUpperCase());
};

export const fabricMediaKind = (
  kind: FabricMediaSource["kind"],
  locale: Locale,
): string => {
  const names: Record<Locale, Record<FabricMediaSource["kind"], string>> = {
    en: {
      meta_glasses: "Meta glasses",
      robomaster: "RoboMaster",
      tello: "Tello drone",
      usb_camera: "USB camera",
      simulator: "Simulated camera",
    },
    ko: {
      meta_glasses: "Meta 안경",
      robomaster: "RoboMaster",
      tello: "Tello 드론",
      usb_camera: "USB 카메라",
      simulator: "시뮬레이션 카메라",
    },
  };
  return names[locale][kind];
};

export const fabricPhase = (phase: string, locale: Locale): string => {
  if (locale === "en") {
    return phase
      .replaceAll("_", " ")
      .replace(/^./, (letter) => letter.toUpperCase());
  }
  const phases: Record<string, string> = {
    waiting_for_status: "상태 업데이트 대기 중",
    idle: "대기",
    armed: "실행 준비됨",
    waiting_for_signal: "신호 대기 중",
    launching: "실행 중",
    running: "진행 중",
    completed: "완료",
    stopped: "정지됨",
    failed: "실패",
    cancelled: "취소됨",
    connected: "연결됨",
    connecting: "연결 중",
    disconnected: "연결 끊김",
    degraded: "연결됨 · 확인 필요",
    unavailable: "사용할 수 없음",
    landed: "착륙 상태",
    airborne: "비행 중",
    flying: "비행 중",
    landing: "착륙 중",
    unknown: "상태 알 수 없음",
  };
  return phases[phase] ?? phase;
};

export const fabricFormatTime = (value: string, locale: Locale): string =>
  new Intl.DateTimeFormat(locale === "ko" ? "ko-KR" : "en", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
