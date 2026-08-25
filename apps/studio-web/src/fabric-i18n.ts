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
  "common.moreInfo": "More information",

  "g2.guide.title": "What the glasses connection can do",
  "g2.guide.input":
    "Send voice or button input to the assigned Codex or Claude session.",
  "g2.guide.output":
    "Receive coding-agent completions and configured notifications through the glasses display or audio.",
  "g2.guide.deviceControl":
    "Control every assigned RoboMaster, Sphero, LEGO, or Dash together, and request an armed Tello sequence.",
  "g2.guide.commandsTitle": "Voice examples:",
  "g2.guide.commands":
    "“CIT robots forward”, “CIT robots left”, “CIT robots stop”, “CIT drones take off”, or “CIT drones land”.",
  "g2.guide.controlSetup":
    "Choose Glasses device control, assign this glasses input and each output, start and arm the lesson, then speak. Movement and takeoff require one more press to confirm.",
  "g2.guide.telegram":
    "Install Telegram on the paired phone, not on the glasses. For G2, enable Telegram in Even app → Settings → Notification; Meta uses the paired phone’s notification/audio path.",
  "g2.guide.directMessage":
    "This console does not yet include a composer for arbitrary G2 text; agent completions and configured notifications are supported.",
  "lesson.glassesControl.title": "Connect the glasses to this lesson",
  "lesson.glassesControl.body":
    "Open the CIT bridge on the G2 or Meta phone, then attach the available glasses. Only devices assigned below can respond.",
  "lesson.glassesControl.connect": "Connect G2 / Meta",
  "lesson.glassesControl.prepare":
    "Choose Physical devices, then set up this lesson first.",

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
  "header.installAnother": "Install another PC",

  "installation.eyebrow": "Move or expand this classroom",
  "installation.title": "Install CIT on another Windows computer",
  "installation.intro":
    "Download one verified setup package, copy it to the new computer, and follow the four tutor-friendly steps below.",
  "installation.platform": "Windows 11 x64",
  "installation.internetTitle": "Internet is required during installation",
  "installation.internetBody":
    "The installer obtains pinned Microsoft, OpenJS, Python, npm, PyPI, and Git prerequisites. It can be carried by USB, but it is not a fully offline installer.",
  "installation.noCloud":
    "After setup, classroom control remains local-first. CIT does not require a Tuya, Gosund, or Tapo cloud account.",
  "installation.step1.title": "Download both setup files",
  "installation.step1.body":
    "Save the Windows setup ZIP and the small site template from this page. The template contains only the site and room names.",
  "installation.step2.title": "Copy and extract on the new computer",
  "installation.step2.body":
    "Move the files by USB or a trusted private transfer. Extract the ZIP and place cit-site-template.json beside Install-CIT.cmd.",
  "installation.step3.title": "Run Install-CIT.cmd",
  "installation.step3.body":
    "Double-click the installer, approve prerequisites, and enter the new classroom Wi-Fi password only in the local prompt.",
  "installation.step4.title": "Open, find, and pair devices",
  "installation.step4.body":
    "Use the installed CIT Classroom Control button, find devices, complete any Windows Bluetooth pairing, and factory-reset then recommission Matter plugs at the new site.",
  "installation.loadingTitle": "Checking the local setup package",
  "installation.loadingBody":
    "CIT is validating the release metadata before showing the download.",
  "installation.unavailableTitle":
    "The transfer package has not been built yet",
  "installation.unavailableBody":
    "Ask the classroom technician to publish the Windows package. The download button will appear here after the local runtime restarts.",
  "installation.technical": "Technician build command",
  "installation.packageEyebrow": "Verified local release",
  "installation.version": "Version",
  "installation.revision": "Revision",
  "installation.size": "Download size",
  "installation.checksum": "SHA-256 integrity checksum",
  "installation.download": "Download Windows setup ZIP",
  "installation.downloadHelp": "Authenticated and checksum-verified",
  "installation.siteTemplate": "Download this site template",
  "installation.siteTemplateHelp":
    "Move this JSON beside Install-CIT.cmd; it contains no password or token.",
  "installation.permission":
    "This local role cannot download installers. Ask an instructor or administrator.",
  "installation.includedTitle": "Included",
  "installation.includedBody":
    "CIT source, local runtime, web interface, independent device adapters, launchers, bilingual guides, exact dependency locks, and setup checks.",
  "installation.excludedTitle": "Never copied",
  "installation.excludedBody":
    "Access tokens, Wi-Fi passwords, Matter operational keys or controller databases, vendor credentials, recordings, logs, dependency caches, and prior classroom state.",
  "installation.checksumFailed":
    "The downloaded setup did not match its SHA-256 checksum. Nothing was saved; ask the technician to rebuild it.",

  "notice.ready": "Ready to set up your classroom.",
  "notice.secureOpen": "Classroom controls opened securely on this computer.",
  "notice.connected": "Classroom controls connected on this computer.",
  "notice.signedOut":
    "Signed out. Reopen the console from the CIT launcher to return.",
  "notice.installerDownloaded":
    "Windows setup downloaded and verified. Copy it with the site template to the new computer.",
  "notice.siteTemplateDownloaded":
    "Site template downloaded. It contains only {site} / {room}; no credential or Wi-Fi password.",
  "notice.lessonCreatedAuto":
    "Lesson created and {count} available device(s) were connected automatically.",
  "notice.lessonCreated":
    "Lesson created. Choose the devices you want to use next.",
  "notice.glassesControlConnected":
    "G2 / Meta input is connected to this lesson. Assign outputs, complete safety setup, and start the lesson.",
  "notice.roleReady": "{device} is ready for {role}.",
  "notice.lessonStatus": "Lesson status: {status}.",
  "notice.emergencyStop":
    "Emergency stop {status}: {sessions} session(s), {nodes} adapter node(s).",
  "notice.deviceCheck":
    "Device check finished: {connected} connected, {found} found or ready. Review the cards below for anything that still needs setup.",
  "notice.integrationConnected":
    "Connection started for {name}. Physical outputs remain disarmed.",
  "notice.integrationScanned":
    "{name} scan refreshed: {status}. Use Connect or the setup controls in this card.",
  "notice.matterAdded": "The Matter plug was added locally and remains off.",
  "notice.matterWifiConfigured":
    "Classroom Wi-Fi was saved only in the local Matter controller. You can now add the plug.",
  "notice.legoConnected": "The LEGO hub was connected for unarmed monitoring.",
  "notice.wonderConnected":
    "Connected {count} selected Dash/Dot robot(s) for unarmed monitoring.",
  "notice.spheroConnected":
    "Connected {count} selected Sphero BOLT robot(s) for unarmed monitoring.",
  "notice.ollieConnected":
    "Connected {count} selected Sphero Ollie robot(s) for unarmed monitoring.",
  "notice.noneConnected": "No connection completed.",
  "notice.groupsConnected":
    "Connection completed for {count} device group(s): {names}.",
  "notice.rememberedConnected":
    "Remembered reconnect finished: {connected} reconnected, {already} already connected, {skipped} safely skipped.",
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
  "busy.downloadingInstaller": "Downloading and verifying Windows setup",
  "busy.downloadingSiteTemplate": "Preparing the non-secret site template",
  "busy.creatingSession": "Creating lesson",
  "busy.assigningRole": "Assigning a device",
  "busy.changingSession": "Updating lesson",
  "busy.emergencyStop": "Stopping all devices",
  "busy.findingDevices": "Finding devices",
  "busy.scanningIntegration": "Scanning {name}",
  "busy.connectingDevice": "Connecting {name}",
  "busy.connectingGlassesControl": "Connecting G2 / Meta to this lesson",
  "busy.addingMatter": "Adding Matter smart plug",
  "busy.configuringMatterWifi": "Saving Matter classroom Wi-Fi",
  "busy.connectingLego": "Connecting LEGO hub",
  "busy.connectingWonder": "Connecting selected Dash and Dot robots",
  "busy.wonderCommand": "Sending a bounded Dash/Dot control",
  "busy.connectingSphero": "Connecting selected Sphero BOLT robots",
  "busy.connectingOllie": "Connecting selected Sphero Ollie robots",
  "busy.spheroCommand": "Sending a bounded Sphero BOLT control",
  "busy.syncPreparing": "Preparing synchronized motor control",
  "busy.syncCommand": "Sending synchronized bounded movement",
  "busy.syncWearables": "Connecting wearable control inputs",
  "busy.syncDisabling": "Stopping synchronized motor control",
  "busy.connectingAll": "Connecting available devices",
  "busy.connectingRemembered": "Reconnecting remembered devices",
  "busy.copyingSetup": "Copying setup instructions",
  "busy.cameraPairing": "Preparing Meta camera pairing",
  "busy.copying": "Copying {label}",
  "busy.testingInput": "Testing input",
  "busy.testingOutput": "Testing output",
  "busy.smartPlug": "Changing smart-plug power",
  "busy.telloLand": "Landing Tello",
  "busy.telloEmergency": "Emergency-stopping Tello",
  "busy.telloCommand": "Sending Tello command",
  "busy.brainArm": "Arming one-shot MindWave demo",
  "busy.brainStop": "Stopping MindWave demo",
  "busy.fleetArm": "Arming one sequential fleet launch",
  "busy.fleetStart": "Starting the armed fleet sequence",
  "busy.fleetStop": "Stopping and landing the selected fleet",
  "busy.vision": "Recognizing objects in {name}",

  "error.selectCourse": "Select an installed course pack.",
  "error.glassesControlSession":
    "Set up and select a Glasses device control lesson first.",
  "error.glassesControlPhysical":
    "Choose Physical devices before connecting G2 or Meta.",
  "error.selectSession": "Select a lesson first.",
  "error.selectPhysicalSession": "Select a physical lesson first.",
  "error.selectNode": "Select a compatible device for {role}.",
  "error.setupFirst": "This integration needs its setup step first.",
  "error.wonderUnassigned":
    "Assign this Dash or Dot to a Wonder robot role first.",
  "error.spheroUnassigned":
    "Assign this Sphero BOLT to a robot sensor role first.",
  "error.noSynchronizedMotors":
    "Connect at least one Sphero BOLT or Ollie first.",
  "error.syncPartial": "{failed} of {count} synchronized commands failed.",
  "error.noSynchronizedInputs":
    "Connect G2, R1, Meta, or MindWave from its device card first.",
  "error.spheroSession": "Open a Sphero BOLT control session first.",
  "error.noSpheroRobots": "No connected Sphero BOLT robots are available.",
  "error.spheroSetupPermission":
    "This tutor account cannot prepare a Sphero BOLT control session.",
  "error.spheroCourse": "The device-monitoring course is not installed.",
  "error.noTelloDrones": "No connected Tello drones are available.",
  "error.telloSetupPermission":
    "An instructor or administrator must prepare Tello controls.",
  "error.telloCourse": "The device-monitoring course is not installed.",
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
  "error.noSmartPlugs": "No connected smart plugs are available.",
  "error.smartPlugSetupPermission":
    "This tutor account cannot prepare a smart-plug control session.",
  "error.smartPlugCourse": "The smart-plug control course is not installed.",
  "error.safetyConfirmation":
    "Confirm the visible classroom safety check before starting.",
  "error.directControlSessionNotReady":
    "The device control session could not be prepared.",
  "error.smartPlugSessionNotReady":
    "The smart-plug control session could not be started.",
  "error.assignPlug": "Assign the classroom plug before controlling power.",
  "error.monitoringSession": "Select the device-monitoring lesson first.",
  "error.droneUnassigned": "That Tello is no longer assigned to this lesson.",
  "error.brainController": "Assign the bounded MindWave demo controller first.",
  "error.startDemo": "Start the lesson before arming the demo.",
  "error.armFlight": "Start the physical lesson before arming flight.",
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
  "error.telloNotVisible":
    "Tello Wi-Fi is not visible now. Power on the drone, scan again when TELLO-* appears, then connect it.",
  "error.telloSessionActive":
    "The drone connection remains active. Its in-use aircraft session prevented only the Wi-Fi route change.",
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
  "guide.safety.title": "Review safety before starting",
  "guide.safety.description":
    "Check the room, keep the emergency stop visible, then start the lesson.",
  "guide.teach.title": "Lesson running",
  "guide.teach.description":
    "Devices are ready. Use the lesson controls below and end the session when class is finished.",
  "guide.ready.title": "Everything is ready",
  "guide.ready.description":
    "Review the summary, then start the lesson when your students are ready.",
  "guide.action.find": "Go to device discovery",
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
    "Turn on devices, connect USB equipment, then select Find devices. CIT checks USB, Bluetooth, Wi-Fi, local services, and authorized Android phones.",
  "discovery.checking": "Checking…",
  "discovery.find": "Find devices",
  "discovery.noMovement": "Devices are not turned on automatically",
  "discovery.safeTitle": "Safe scan",
  "discovery.safeBody":
    "Scanning only checks connections. It does not activate devices or save raw sensor data.",
  "discovery.connectionsReady": "{count} safe connection(s) ready",
  "discovery.connectAllHelp":
    "Connect every verified adapter in one step. Robots, drones, plugs, and lesson sessions remain disarmed.",
  "discovery.aircraftGrounded":
    "Every aircraft is grounded; propellers are removed or guarded.",
  "discovery.connecting": "Connecting…",
  "discovery.connectAll": "Connect all available",
  "discovery.offState": "No movement; approved plugs enter the off safe state",
  "discovery.rememberedReady": "{count} remembered connection group(s)",
  "discovery.rememberedHelp":
    "Reconnect exact adapter profiles saved on this computer without the broad USB, Bluetooth, Wi-Fi, and Android scan. Physical outputs stay locked and remembered plugs enter the off safe state.",
  "discovery.connectRemembered": "Connect remembered devices",
  "discovery.reconnectingRemembered": "Reconnecting…",
  "discovery.rememberedNoScan": "Fast reconnect · outputs locked",
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
  "discovery.readinessOverview": "Device readiness summary",
  "discovery.tier.connected.title": "Connected now",
  "discovery.tier.connected.description":
    "Live devices appear first and are ready to assign to a lesson.",
  "discovery.tier.connected.empty": "No devices are connected yet.",
  "discovery.tier.available.title": "Available now",
  "discovery.tier.available.description":
    "Detected hardware and prepared local services that can be connected now.",
  "discovery.tier.available.empty":
    "No additional devices are currently ready to connect.",
  "discovery.tier.unavailable.title": "Not currently available",
  "discovery.tier.unavailable.description":
    "Supported devices that need power, pairing, setup, or another scan.",
  "discovery.tier.unavailable.empty":
    "No supported devices currently need setup.",
  "discovery.tier.count": "{count} item(s)",
  "discovery.detectedPaths": "{count} detected connection path(s)",
  "discovery.signal": "{percent}% signal",
  "discovery.connect": "Connect",
  "discovery.scanThisDevice": "Scan this device again",
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

  "deviceIo.title": "Live input and output",
  "deviceIo.help": "Available signals and controls are shown here.",
  "deviceIo.inputs": "Inputs from device",
  "deviceIo.outputs": "Outputs to device",
  "deviceIo.live": "Latest sensor values",

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
  "lesson.overview": "Lesson overview",
  "lesson.materials": "Lesson materials",
  "lesson.materialsSummary": "Cameras and sensor readings",
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
  "safety.locked": "Ready — direct controls prepare devices on first use",
  "safety.physicalHelp":
    "Keep the Stop all devices button visible and make sure the activity area is clear.",
  "safety.nonSpatialHelp":
    "Choose a device control directly. CIT prepares its local session automatically.",
  "safety.simulationHelp":
    "Practice safely before switching this lesson to real classroom hardware.",
  "safety.confirm":
    "I can see the devices, the activity area is clear, and I know where “Stop all devices” is.",
  "flight.confirmOnce":
    "I am present and have checked the flight area, emergency controls, and each drone route.",
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
  "media.previewRate": "Preview {rate} fps",
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

  "leap.eyebrow": "Leap Motion",
  "leap.title": "Live hand detection",
  "leap.intro":
    "Place a hand above the controller. This semantic view shows the detected palm, pinch, grab, and bounded movement output without sending raw Leap frames to the page.",
  "leap.handDetected": "Hand detected",
  "leap.waitingHand": "Controller ready",
  "leap.waitingSignal": "Waiting for tracking",
  "leap.visualAltDetected": "Live semantic view of the detected {hand} hand",
  "leap.visualAltWaiting": "Leap Motion detection area waiting for a hand",
  "leap.left": "LEFT",
  "leap.forward": "FORWARD",
  "leap.right": "RIGHT",
  "leap.leftHand": "Left hand",
  "leap.rightHand": "Right hand",
  "leap.hand": "Detected hand",
  "leap.pinch": "Pinch",
  "leap.grab": "Grab",
  "leap.palm": "Palm x / y / z",
  "leap.output": "Forward / right output",
  "leap.frameRate": "Sensor rate",
  "leap.noState": "NO SIGNAL",
  "leap.placeHand": "Place one open hand 10–40 cm above the controller.",
  "leap.selectLesson":
    "Select the Leap lesson session to view its live signal.",
  "leap.noReading":
    "The adapter is connected; waiting for its first hand sample.",
  "leap.updated": "Last hand sample {time}",
  "leap.privacy":
    "Only reduced palm and gesture measurements are shown. Raw Leap frames and camera images are not transmitted or recorded by this panel.",

  "sensor.eyebrow": "Live sensors",
  "sensor.title": "Classroom readings",
  "sensor.intro":
    "The latest normalized LEGO, robot, smart-plug electrical, biosignal, and battery readings appear automatically when an adapter publishes them.",
  "sensor.none": "No sensor readings have arrived in the selected lesson yet.",

  "plug.eyebrow": "Lesson control",
  "plug.title": "Classroom plugs",
  "plug.noneAssigned": "No classroom plugs assigned",
  "plug.compatible": "{count} compatible device(s) connected",
  "plug.unknownState": "UNKNOWN",
  "plug.stateUnknown": "State has not been observed in this lesson",
  "plug.observed": "Observed {time}{source}",
  "plug.turnOn": "Turn on",
  "plug.turnOnHelp": "Turn on the approved classroom load",
  "plug.turnOff": "Turn off",
  "plug.turnOffHelp": "Always available as the safe state",
  "plug.onState": "ON",
  "plug.offState": "OFF",
  "plug.help":
    "Choose On or Off directly. CIT prepares the local control session automatically; use only an approved classroom load.",

  "nodes.eyebrow": "Device status",
  "nodes.title": "Everything connected to this classroom",
  "nodes.directorySummary": "Input, output, and connection status",
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
    "Tapo P110M and compatible Matter Wi-Fi plugs connect directly to CIT. No proprietary vendor app, account, cloud API, device ID, or local key is used.",
  "matter.ready": "Ready",
  "matter.required": "Required",
  "matter.wifi.title": "Save classroom Wi-Fi once",
  "matter.wifi.ready":
    "The local controller has Wi-Fi and is ready to add Matter devices.",
  "matter.wifi.required":
    "Enter the 2.4 GHz classroom Wi-Fi used by this computer and the plugs.",
  "matter.wifi.scanFirst":
    "Choose Find devices above so CIT can check the local controller first.",
  "matter.wifi.ssid": "Wi-Fi name (SSID)",
  "matter.wifi.ssidPlaceholder": "Exact 2.4 GHz network name",
  "matter.wifi.password": "Wi-Fi password",
  "matter.wifi.passwordPlaceholder": "8–63 characters",
  "matter.wifi.save": "Save Wi-Fi locally",
  "matter.wifi.saving": "Saving Wi-Fi…",
  "matter.wifi.memory":
    "The password is sent only to the loopback Matter controller, is never logged, and is cleared from this page after success.",
  "matter.device.title": "Put each plug in setup mode",
  "matter.device.help":
    "Plug it in and hold Reset for 10 seconds. Then choose Find devices again.",
  "matter.device.found": "{count} nearby",
  "matter.device.waiting": "Waiting",
  "matter.code.title": "Add using the printed Matter code",
  "matter.code.help":
    "Enter the 11-digit manual code or scan text printed next to the Matter QR label.",
  "matter.code.locked": "Complete classroom Wi-Fi setup in step 1 first.",
  "matter.tapo.title": "Tapo P110M — direct local setup",
  "matter.tapo.support":
    "Supported through Matter over your classroom Wi-Fi, independently of the Tapo app and TP-Link cloud.",
  "matter.tapo.reset":
    "For a new or previously configured plug, hold Reset for 10 seconds to factory-reset it.",
  "matter.tapo.window":
    "Power-cycle the plug and add it within its 15-minute Matter setup window.",
  "matter.tapo.network":
    "Keep this computer on the same local network; the P110M uses 2.4 GHz Wi-Fi and local IPv6/mDNS.",
  "matter.tapo.code":
    "Use the original Matter QR/manual code printed on the plug or packaging—not a Tapo account or local key.",
  "matter.tapo.energy":
    "On/off works with standard Matter firmware. Power and energy appear automatically when the plug firmware exposes the standard Matter 1.3 measurement clusters.",
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

  "sphero.setup": "Detected Sphero BOLT robots",
  "sphero.wake": "Charge BOLT and remove it from its cradle to wake it.",
  "sphero.closeApps":
    "Close Sphero Edu, Sphero Play, and any other app connected to BOLT.",
  "sphero.noPairing":
    "Do not pair BOLT in Windows Settings. CIT connects directly over BLE.",
  "sphero.noneVisible":
    "No exact SB-XXXX advertisement is visible. Wake BOLT, bring it nearby, close other apps, then choose Find devices again.",
  "sphero.boltCapabilities": "BOLT · roll, lights, sensors",
  "sphero.capabilities": "BOLT · roll, lights, sensors",
  "sphero.connecting": "Connecting…",
  "sphero.connectRobot": "Connect",
  "sphero.connectSafety":
    "Connection starts unarmed sensor monitoring. It does not aim, light, or roll BOLT.",
  "sphero.eyebrow": "Robot controls",
  "sphero.title": "Sphero BOLT robot",
  "sphero.help":
    "Put BOLT on a clear floor, set forward, then use the direct bounded controls. Keep Stop all devices visible.",
  "sphero.aimTitle": "1. Set the forward direction",
  "sphero.aimHelp":
    "Place BOLT on the floor and turn the blue tail light toward you. The direction away from you becomes forward.",
  "sphero.aimButton": "Set this direction as forward",
  "sphero.drive": "2. Test a short movement",
  "sphero.forward": "Forward",
  "sphero.backward": "Backward",
  "sphero.left": "Left",
  "sphero.right": "Right",
  "sphero.stop": "Stop",
  "sphero.nudge":
    "Each arrow requests a bounded 0.20 m/s nudge. BOLT stops locally within 750 ms unless another approved command arrives.",
  "sphero.lights": "3. Test the matrix and aiming LEDs",
  "sphero.color.blue": "Blue",
  "sphero.color.orange": "Orange",
  "sphero.color.green": "Green",
  "sphero.color.off": "Lights off",

  "ollie.setup": "Detected Sphero Ollie robots",
  "ollie.wake": "Charge Ollie and switch it on.",
  "ollie.closeApps": "Close Sphero Edu and any other app connected to Ollie.",
  "ollie.noPairing":
    "Do not pair Ollie in Windows Settings. CIT connects directly over BLE.",
  "ollie.noneVisible":
    "No exact 2B-XXXX advertisement is visible. Switch Ollie on, bring it nearby, close other apps, then choose Find devices again.",
  "ollie.capabilities": "Ollie · roll, main LED, sensors",
  "ollie.connecting": "Connecting…",
  "ollie.connectRobot": "Connect",
  "ollie.connectSafety":
    "Connection starts unarmed sensor monitoring and sends no movement. Vendor-safe startup may clear the current LEDs.",
  "ollie.title": "Sphero Ollie robot",
  "ollie.help":
    "Put Ollie on a clear floor, set forward, then use the bounded controls. Keep Stop all devices visible.",
  "ollie.aimTitle": "1. Set the forward direction",
  "ollie.aimHelp":
    "Point Ollie's blue tail light toward you. The direction away from you becomes forward.",
  "ollie.aimButton": "Set this direction as forward",
  "ollie.drive": "2. Test a short movement",
  "ollie.nudge":
    "Each arrow requests a conservative short movement. Ollie stops locally within 750 ms unless another approved command arrives.",
  "ollie.lights": "3. Test the main LED",

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
    "Choose a control directly; CIT prepares the local session automatically. Dash movement remains short and bounded. Dot has no drive controls.",
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

  "drone.eyebrow": "Drone control",
  "drone.title": "Tello flight controls",
  "drone.help":
    "Confirm safety once, then use bounded 20 cm movement and 30° rotation controls.",
  "drone.role": "Safety drone {number}",
  "drone.checks": "One flight confirmation",
  "drone.instructorPresent": "Instructor present",
  "drone.flightAreaClear": "Flight area clear",
  "drone.emergencyPlanReady": "Emergency response ready",
  "drone.sessionReady": "The physical session is armed and active.",
  "drone.sessionAutoPrepare":
    "The first flight action safely arms and starts this device session.",
  "drone.restartAdapter":
    "Reconnect this Tello to load the current bounded-flight adapter.",
  "drone.takeoff": "Take off",
  "drone.takeoffConfirm": "Take off {name} now?",
  "drone.forward": "Forward 20 cm",
  "drone.back": "Back 20 cm",
  "drone.left": "Left 20 cm",
  "drone.right": "Right 20 cm",
  "drone.up": "Up 20 cm",
  "drone.down": "Down 20 cm",
  "drone.rotateCounterclockwise": "Counterclockwise 30°",
  "drone.rotateClockwise": "Clockwise 30°",
  "drone.land": "Land",
  "drone.landHelp": "Request a normal landing",
  "drone.emergency": "Emergency motor stop",
  "drone.emergencyHelp": "Use only when stopping motors is safer than flight",
  "drone.manual": "Manual movement",
  "drone.confirm":
    "Emergency-stop {name}? An airborne drone can fall immediately.",

  "sync.eyebrow": "Group control",
  "sync.title": "Synchronized motor control",
  "sync.enable": "Control connected BOLT and Ollie together",
  "sync.groundTargets": "BOLT · Ollie: {count}",
  "sync.includeTello": "Include Tello movement ({count})",
  "sync.telloSafety":
    "Confirm flight safety and take off from the Tello controls first.",
  "sync.controls": "Synchronized movement controls",
  "sync.forward": "Move all forward",
  "sync.backward": "Move all backward",
  "sync.left": "Move all left",
  "sync.right": "Move all right",
  "sync.stop": "Stop all ground robots",
  "sync.inputs": "Semantic inputs",
  "sync.input.g2": "G2 voice",
  "sync.input.r1": "R1 ring",
  "sync.input.meta": "Meta voice",
  "sync.input.mindwave": "MindWave blink",
  "sync.connectWearables": "Assign connected inputs",
  "sync.inputHelp":
    "G2/Meta voice and R1 gestures use the same bounded directions. One MindWave blink starts one 10 cm demonstration; it is not a measure of attention.",
  "sync.ready":
    "Synchronized motor control is ready for {count} ground robots.",
  "sync.disabled": "Synchronized motor control is off.",
  "sync.sent": "Sent {direction} to {count} devices.",

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
  "brain.flightCheck": "2. Confirm flight safety once",
  "brain.present": "I am present and supervising this flight.",
  "brain.areaClear":
    "The full flight area is clear; all visible Tellos are verified and grounded.",
  "brain.emergencyReady":
    "I can reach Land and Emergency stop and understand that a released rapid-handoff aircraft may no longer be reachable from the current Wi-Fi adapter.",
  "brain.runSimulation": "Run safe simulation",
  "brain.arm": "Connect, prepare, and arm once",
  "brain.waitCondition": "Waits for the selected MindWave condition",
  "brain.startFirst": "Start the lesson first",
  "brain.startArmFirst": "Starts and arms the lesson automatically",
  "brain.stop": "Stop / disarm demo",
  "brain.stopHelp": "Safe-state command; available before or during a trigger",

  "fleet.eyebrow": "Multi-input drone sequence",
  "fleet.title": "Tello fleet controls",
  "fleet.helpBefore": "First arm one ordered plan. Then use",
  "fleet.startNow": "Start now",
  "fleet.helpAfter":
    "the Leap open-hand→pinch gesture, or say “Start drone sequence” through an assigned G2 or Meta glasses node. A trigger cannot arm flight; it can only consume the tutor’s current one-shot plan.",
  "fleet.current": "Current state",
  "fleet.airborne": "Confirmed airborne",
  "fleet.waiting": "Waiting for the fleet controller’s first status update.",
  "fleet.order": "Takeoff and landing order",
  "fleet.connectController":
    "Connect the Brain2Devices fleet controller to list approved aircraft.",
  "fleet.aircraftState": "{connection} · {flight} · battery {battery}%",
  "fleet.earlier": "Move {name} earlier",
  "fleet.later": "Move {name} later",
  "fleet.remove": "Remove",
  "fleet.interval": "Seconds between confirmed launches",
  "fleet.minimumBattery": "Minimum battery for every aircraft",
  "fleet.inputs": "Allowed triggers",
  "fleet.tutorButton": "Tutor’s Start now button",
  "fleet.noInputs":
    "No Leap, G2, or Meta input is assigned. The tutor button still works.",
  "fleet.flightCheck": "Confirm flight safety once",
  "fleet.present": "I am present and supervising every aircraft.",
  "fleet.areaClear":
    "The full flight area is clear and every selected aircraft is visibly grounded.",
  "fleet.emergencyReady":
    "I can reach Stop & land and each aircraft’s emergency control.",
  "fleet.routes":
    "Each stock Tello has its own connected Wi-Fi route, or each station-mode aircraft has a unique reachable address.",
  "fleet.notReady":
    "Every selected aircraft must be connected, confirmed landed, and at or above the minimum battery.",
  "fleet.arm": "Connect, prepare, and arm once",
  "fleet.prepareTriggers": "Prepare ring / sensor trigger",
  "fleet.takeoffOneByOne": "Take off one by one",
  "fleet.landOneByOne": "Land one by one",
  "fleet.options": "Order and trigger options",
  "fleet.optionsSummary":
    "{interval}s spacing · {battery}% minimum · {inputs} triggers",
  "fleet.armHelp": "No aircraft launches yet · expires after 60 seconds",
  "fleet.startArmFirst": "Starts and arms the lesson automatically",
  "fleet.startHelp": "Uses the same bounded command as Leap and glasses",
  "fleet.stop": "Stop & land selected fleet",
  "fleet.stopHelp": "Also cancels launches that have not started",
  "fleet.leapInstruction": "open hand, then pinch",
  "fleet.ringInstruction": "double-tap the R1 ring",
  "fleet.voiceInstruction": "say “Start drone sequence”",

  "course.deviceMonitoring.name": "Devices, sensors, cameras, and safe demos",
  "course.deviceMonitoring.summary": "Cameras, sensors + bounded drone demos",
  "course.deviceMonitoring.description":
    "Shows cameras, Tello telemetry, MindWave vendor signals, and LEGO readings. Optional guided panels add an explicitly armed MindWave demo and a tutor-armed sequential fleet launched by button, Leap, R1, G2, or Meta.",
  "course.glasses.name": "Glasses and coding assistant",
  "course.glasses.summary": "Glasses + coding assistant",
  "course.glasses.description":
    "Students send a request from their glasses to a coding assistant and receive the response on a classroom display.",
  "course.glassesControl.name": "Glasses device control",
  "course.glassesControl.summary": "G2 or Meta + assigned robots and drones",
  "course.glassesControl.description":
    "Confirmed G2 or Meta voice commands move every assigned RoboMaster, Sphero, LEGO, or Dash at once. Tello takeoff still requires the separate tutor flight checklist and one-shot arm.",
  "course.gesture.name": "Gesture-controlled robot",
  "course.gesture.summary": "Gesture + classroom robot",
  "course.gesture.description":
    "Students steer a classroom robot with hand gestures while CIT keeps movement within the lesson’s safety limits.",
  "course.ring.name": "R1 smart-ring device control",
  "course.ring.summary": "R1 input + assigned robots and drones",
  "course.ring.description":
    "Scroll R1 for short bounded forward or backward cues on assigned RoboMaster, Sphero, LEGO, or Dash devices. Tap requests zero velocity. Double-tap can start only a separately armed Tello sequence.",
  "course.simultaneous.name": "Simultaneous multi-device cue",
  "course.simultaneous.summary": "One input + several simultaneous outputs",
  "course.simultaneous.description":
    "One approved Leap, R1, or glasses cue simultaneously sends bounded actions to assigned RoboMaster, Sphero, LEGO, Dash, an armed Tello fleet, and glasses displays. Every output remains independently safety checked.",
  "course.synchronized.name": "Synchronized motor control",
  "course.synchronized.summary": "G2 · R1 · Meta · MindWave + BOLT · Ollie",
  "course.synchronized.description":
    "An explicit group-control switch lets G2/Meta voice, R1 gestures, and one debounced MindWave blink move assigned BOLT and Ollie robots together. Tello remains a separate opt-in route with its own flight checks.",
  "course.plug.name": "Classroom smart plug",
  "course.plug.summary": "Tutor-controlled classroom plugs",
  "course.plug.description":
    "The tutor independently controls up to two approved classroom lamps or other low-risk loads from this screen.",
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
  "role.plug.name": "Classroom plug 1",
  "role.plug.description": "Turns the first approved classroom load on or off",
  "role.plug2.name": "Classroom plug 2",
  "role.plug2.description":
    "Optionally controls a second approved classroom load independently",
  "role.agent.name": "Coding assistant",
  "role.agent.description":
    "Receives student prompts and returns coding progress",
  "role.feedback.name": "Feedback display",
  "role.feedback.description": "Shows coding progress and lesson messages",
  "role.gesture.name": "Gesture controller",
  "role.gesture.description": "Sends hand movements to the lesson",
  "role.smartRing.name": "R1 smart-ring input",
  "role.smartRing.description":
    "Publishes structured tap, double-tap, and scroll gestures through the paired G2 phone bridge",
  "role.console.name": "Tutor display",
  "role.console.description": "Shows lesson activity to the tutor",
  "role.glasses.name": "Student glasses",
  "role.glasses.description":
    "Sends student input and displays lesson feedback",
  "role.glassesInput.name": "Glasses control input {number}",
  "role.glassesInput.description":
    "Publishes confirmed, structured G2 or Meta device commands without raw transcripts or vendor packets",
  "role.robot.name": "Classroom robot",
  "role.robot.description": "Receives bounded movement and stop instructions",
  "role.safetyDrone.name": "Safety drone {number}",
  "role.safetyDrone.description":
    "Publishes Tello telemetry and accepts only Land or Emergency Stop",
  "role.fleetInput.name": "Fleet trigger {number}",
  "role.fleetInput.description":
    "Requests the currently armed sequence through Leap, R1, G2, or Meta",
  "role.groundOutput.name": "Ground robot output {number}",
  "role.groundOutput.description":
    "Receives the same bounded, watchdog-limited movement cue; assign RoboMaster, Sphero, LEGO, or Dash",
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
  "common.moreInfo": "자세히",

  "g2.guide.title": "안경 연결로 할 수 있는 일",
  "g2.guide.input":
    "음성·버튼 입력을 배정된 Codex 또는 Claude 세션으로 보낼 수 있습니다.",
  "g2.guide.output":
    "코딩 에이전트 완료 결과와 설정된 알림을 안경 화면 또는 음성으로 받을 수 있습니다.",
  "g2.guide.deviceControl":
    "배정한 RoboMaster, Sphero, LEGO 또는 Dash를 동시에 제어하고 준비된 Tello 순차 비행을 요청할 수 있습니다.",
  "g2.guide.commandsTitle": "음성 예시:",
  "g2.guide.commands":
    "‘CIT 로봇 앞으로’, ‘CIT 로봇 왼쪽’, ‘CIT 로봇 정지’, ‘CIT 드론 이륙’ 또는 ‘CIT 드론 착륙’.",
  "g2.guide.controlSetup":
    "‘안경으로 장치 제어’를 선택하고 안경 입력과 각 출력을 배정한 뒤 수업을 시작·준비하세요. 이동과 이륙은 한 번 더 눌러 확인해야 합니다.",
  "g2.guide.telegram":
    "Telegram은 안경이 아니라 페어링한 휴대전화에 설치합니다. G2는 Even 앱 → 설정 → 알림에서 Telegram을 켜고, Meta는 휴대전화 알림·음성 경로를 사용합니다.",
  "g2.guide.directMessage":
    "이 화면에는 아직 일반 문구를 직접 보내는 작성창이 없습니다. 에이전트 완료 결과와 설정된 알림은 지원합니다.",
  "lesson.glassesControl.title": "이 수업에 안경 연결",
  "lesson.glassesControl.body":
    "G2 또는 Meta 휴대폰에서 CIT 브리지를 연 뒤 사용 가능한 안경을 연결하세요. 아래에 배정한 장치만 반응합니다.",
  "lesson.glassesControl.connect": "G2 / Meta 연결",
  "lesson.glassesControl.prepare":
    "실물 장치를 선택하고 먼저 이 수업을 설정하세요.",
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
  "header.installAnother": "다른 PC 설치",
  "installation.eyebrow": "교실 이전 또는 확장",
  "installation.title": "다른 Windows 컴퓨터에 CIT 설치",
  "installation.intro":
    "검증된 설치 패키지 하나를 받아 새 컴퓨터로 옮긴 뒤, 아래의 강사용 4단계를 따르면 됩니다.",
  "installation.platform": "Windows 11 64비트",
  "installation.internetTitle": "설치하는 동안 인터넷 연결이 필요합니다",
  "installation.internetBody":
    "설치 프로그램은 고정된 Microsoft, OpenJS, Python, npm, PyPI 및 Git 필수 항목을 받습니다. USB로 옮길 수 있지만 완전한 오프라인 설치 파일은 아닙니다.",
  "installation.noCloud":
    "설치 후 교실 제어는 로컬 우선으로 작동합니다. CIT에는 Tuya, Gosund 또는 Tapo 클라우드 계정이 필요하지 않습니다.",
  "installation.step1.title": "설치 파일 2개 받기",
  "installation.step1.body":
    "이 페이지에서 Windows 설치 ZIP과 작은 사이트 설정 파일을 모두 저장하세요. 설정 파일에는 사이트와 교실 이름만 들어 있습니다.",
  "installation.step2.title": "새 컴퓨터에서 복사하고 압축 풀기",
  "installation.step2.body":
    "USB 또는 신뢰할 수 있는 사설 전송으로 파일을 옮기세요. ZIP 압축을 풀고 cit-site-template.json을 Install-CIT.cmd 옆에 두세요.",
  "installation.step3.title": "Install-CIT.cmd 실행",
  "installation.step3.body":
    "설치 파일을 더블클릭하고 필수 프로그램 설치를 승인한 뒤, 새 교실 Wi-Fi 비밀번호는 로컬 입력창에만 입력하세요.",
  "installation.step4.title": "열기, 찾기, 장치 연결",
  "installation.step4.body":
    "설치된 CIT Classroom Control 버튼을 열어 장치를 찾고, 필요한 Windows Bluetooth 페어링을 완료하세요. 새 장소의 Matter 플러그는 공장 초기화한 뒤 다시 등록하세요.",
  "installation.loadingTitle": "로컬 설치 패키지 확인 중",
  "installation.loadingBody":
    "다운로드를 표시하기 전에 CIT가 릴리스 정보를 검증하고 있습니다.",
  "installation.unavailableTitle": "아직 전송용 설치 패키지가 없습니다",
  "installation.unavailableBody":
    "교실 기술 담당자에게 Windows 패키지 게시를 요청하세요. 로컬 런타임을 다시 시작하면 이곳에 다운로드 버튼이 나타납니다.",
  "installation.technical": "기술 담당자용 빌드 명령",
  "installation.packageEyebrow": "검증된 로컬 릴리스",
  "installation.version": "버전",
  "installation.revision": "소스 리비전",
  "installation.size": "받을 파일 크기",
  "installation.checksum": "SHA-256 무결성 검사값",
  "installation.download": "Windows 설치 ZIP 받기",
  "installation.downloadHelp": "인증 후 검사값까지 확인",
  "installation.siteTemplate": "현재 사이트 설정 받기",
  "installation.siteTemplateHelp":
    "이 JSON을 Install-CIT.cmd 옆으로 옮기세요. 비밀번호나 토큰은 들어 있지 않습니다.",
  "installation.permission":
    "현재 로컬 역할에는 설치 파일 권한이 없습니다. 강사 또는 관리자에게 요청하세요.",
  "installation.includedTitle": "포함되는 항목",
  "installation.includedBody":
    "CIT 소스, 로컬 런타임, 웹 화면, 독립 장치 어댑터, 실행기, 한영 안내서, 정확한 의존성 잠금 파일 및 설치 확인 기능입니다.",
  "installation.excludedTitle": "절대 복사하지 않는 항목",
  "installation.excludedBody":
    "접속 토큰, Wi-Fi 비밀번호, Matter 운영 키와 컨트롤러 DB, 제조사 인증 정보, 녹화, 로그, 의존성 캐시 및 이전 교실 상태입니다.",
  "installation.checksumFailed":
    "받은 설치 파일의 SHA-256 검사값이 맞지 않습니다. 파일을 저장하지 않았으니 기술 담당자에게 다시 빌드해 달라고 요청하세요.",
  "notice.ready": "교실을 준비할 수 있습니다.",
  "notice.secureOpen": "이 컴퓨터에서 수업 제어를 안전하게 열었습니다.",
  "notice.connected": "이 컴퓨터의 수업 제어에 연결했습니다.",
  "notice.signedOut":
    "로그아웃했습니다. 다시 들어오려면 CIT 실행기에서 수업 제어를 여세요.",
  "notice.installerDownloaded":
    "Windows 설치 파일을 받고 검증했습니다. 사이트 설정 파일과 함께 새 컴퓨터로 옮기세요.",
  "notice.siteTemplateDownloaded":
    "사이트 설정 파일을 받았습니다. {site} / {room} 이름만 있으며 인증 정보나 Wi-Fi 비밀번호는 없습니다.",
  "notice.lessonCreatedAuto":
    "수업을 만들고 사용 가능한 장치 {count}대를 자동으로 배정했습니다.",
  "notice.lessonCreated":
    "수업을 만들었습니다. 다음으로 사용할 장치를 선택하세요.",
  "notice.glassesControlConnected":
    "G2 / Meta 입력을 이 수업에 연결했습니다. 출력을 배정하고 안전 설정 후 수업을 시작하세요.",
  "notice.roleReady": "{device} 장치를 ‘{role}’ 역할로 사용할 준비가 됐습니다.",
  "notice.lessonStatus": "수업 상태: {status}.",
  "notice.emergencyStop":
    "비상 정지 {status}: 세션 {sessions}개, 어댑터 노드 {nodes}개를 정지했습니다.",
  "notice.deviceCheck":
    "장치 확인 완료: 연결됨 {connected}개, 발견 또는 준비됨 {found}개. 설정이 더 필요한 장치는 아래 카드를 확인하세요.",
  "notice.integrationConnected":
    "{name} 연결을 시작했습니다. 실제 출력 장치는 계속 잠겨 있습니다.",
  "notice.integrationScanned":
    "{name} 다시 검색 완료: {status}. 이 카드의 연결 또는 설정을 사용하세요.",
  "notice.matterAdded":
    "Matter 플러그를 로컬로 추가했습니다. 전원은 꺼진 안전 상태입니다.",
  "notice.matterWifiConfigured":
    "교실 Wi-Fi를 로컬 Matter 컨트롤러에만 저장했습니다. 이제 플러그를 추가할 수 있습니다.",
  "notice.legoConnected":
    "LEGO 허브를 모터 잠금 상태의 모니터링용으로 연결했습니다.",
  "notice.wonderConnected":
    "선택한 Dash/Dot 로봇 {count}대를 제어 잠금 상태의 모니터링용으로 연결했습니다.",
  "notice.spheroConnected":
    "선택한 Sphero BOLT 로봇 {count}대를 제어 잠금 상태의 모니터링용으로 연결했습니다.",
  "notice.ollieConnected":
    "선택한 Sphero Ollie 로봇 {count}대를 제어 잠금 상태의 모니터링용으로 연결했습니다.",
  "notice.noneConnected": "완료된 연결이 없습니다.",
  "notice.groupsConnected": "장치 그룹 {count}개를 연결했습니다: {names}.",
  "notice.rememberedConnected":
    "기억한 장치 연결 완료: {connected}개 다시 연결, {already}개 이미 연결됨, {skipped}개 안전하게 건너뜀.",
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
  "busy.downloadingInstaller": "Windows 설치 파일을 받고 검증하는 중",
  "busy.downloadingSiteTemplate": "인증 정보 없는 사이트 설정 준비 중",
  "busy.creatingSession": "수업 만드는 중",
  "busy.assigningRole": "장치 배정 중",
  "busy.changingSession": "수업 상태 변경 중",
  "busy.emergencyStop": "모든 장치 정지 중",
  "busy.findingDevices": "장치 찾는 중",
  "busy.scanningIntegration": "{name} 다시 검색 중",
  "busy.connectingDevice": "{name} 연결 중",
  "busy.connectingGlassesControl": "G2 / Meta를 이 수업에 연결하는 중",
  "busy.addingMatter": "Matter 스마트 플러그 추가 중",
  "busy.configuringMatterWifi": "Matter 교실 Wi-Fi 저장 중",
  "busy.connectingLego": "LEGO 허브 연결 중",
  "busy.connectingWonder": "선택한 Dash/Dot 로봇 연결 중",
  "busy.wonderCommand": "제한된 Dash/Dot 제어 전송 중",
  "busy.connectingSphero": "선택한 Sphero BOLT 로봇 연결 중",
  "busy.connectingOllie": "선택한 Sphero Ollie 로봇 연결 중",
  "busy.spheroCommand": "제한된 Sphero BOLT 제어 전송 중",
  "busy.syncPreparing": "동기 장치 제어 준비 중",
  "busy.syncCommand": "동기 제한 이동 전송 중",
  "busy.syncWearables": "웨어러블 제어 입력 연결 중",
  "busy.syncDisabling": "동기 장치 제어 정지 중",
  "busy.connectingAll": "사용 가능한 장치 연결 중",
  "busy.connectingRemembered": "기억한 장치 다시 연결 중",
  "busy.copyingSetup": "설정 안내 복사 중",
  "busy.cameraPairing": "Meta 카메라 페어링 준비 중",
  "busy.copying": "{label} 복사 중",
  "busy.testingInput": "입력 확인 중",
  "busy.testingOutput": "출력 확인 중",
  "busy.smartPlug": "스마트 플러그 전원 변경 중",
  "busy.telloLand": "Tello 착륙 요청 중",
  "busy.telloEmergency": "Tello 비상 정지 중",
  "busy.telloCommand": "Tello 명령 전송 중",
  "busy.brainArm": "MindWave 1회 데모 준비 중",
  "busy.brainStop": "MindWave 데모 정지 중",
  "busy.fleetArm": "순차 드론 비행 1회 준비 중",
  "busy.fleetStart": "준비된 드론 순차 비행 시작 중",
  "busy.fleetStop": "선택한 드론 정지 및 착륙 중",
  "busy.vision": "{name}에서 물체 인식 중",
  "error.selectCourse": "설치된 수업을 선택하세요.",
  "error.glassesControlSession":
    "먼저 ‘안경으로 장치 제어’ 수업을 설정하고 선택하세요.",
  "error.glassesControlPhysical":
    "G2 또는 Meta를 연결하기 전에 실물 장치를 선택하세요.",
  "error.selectSession": "먼저 수업을 선택하세요.",
  "error.selectPhysicalSession": "먼저 실제 장치를 사용하는 수업을 선택하세요.",
  "error.selectNode": "{role} 역할에 맞는 장치를 선택하세요.",
  "error.setupFirst": "먼저 이 통합의 설정 단계를 완료하세요.",
  "error.wonderUnassigned":
    "먼저 이 Dash 또는 Dot을 Wonder 로봇 역할에 배정하세요.",
  "error.spheroUnassigned":
    "먼저 이 Sphero BOLT를 로봇 센서 역할에 배정하세요.",
  "error.noSynchronizedMotors":
    "먼저 Sphero BOLT 또는 Ollie를 한 대 이상 연결하세요.",
  "error.syncPartial": "동기 명령 {count}개 중 {failed}개가 실패했습니다.",
  "error.noSynchronizedInputs":
    "먼저 장치 카드에서 G2, R1, Meta 또는 MindWave를 연결하세요.",
  "error.spheroSession": "먼저 Sphero BOLT 제어 화면을 여세요.",
  "error.noSpheroRobots": "연결된 Sphero BOLT가 없습니다.",
  "error.spheroSetupPermission":
    "이 강사 계정으로 Sphero BOLT 제어 세션을 준비할 수 없습니다.",
  "error.spheroCourse": "장치 모니터링 수업이 설치되어 있지 않습니다.",
  "error.noTelloDrones": "연결된 Tello 드론이 없습니다.",
  "error.telloSetupPermission":
    "강사 또는 관리자가 Tello 제어를 준비해야 합니다.",
  "error.telloCourse": "장치 모니터링 수업이 설치되어 있지 않습니다.",
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
  "error.noSmartPlugs": "연결된 스마트 플러그가 없습니다.",
  "error.smartPlugSetupPermission":
    "이 강사 계정으로 스마트 플러그 제어 세션을 준비할 수 없습니다.",
  "error.smartPlugCourse": "스마트 플러그 제어 수업이 설치되어 있지 않습니다.",
  "error.safetyConfirmation":
    "시작하기 전에 화면의 교실 안전 확인에 동의하세요.",
  "error.directControlSessionNotReady": "장치 제어 세션을 준비하지 못했습니다.",
  "error.smartPlugSessionNotReady":
    "스마트 플러그 제어 세션을 시작하지 못했습니다.",
  "error.assignPlug": "전원을 제어하기 전에 교실 플러그를 배정하세요.",
  "error.monitoringSession": "먼저 장치 모니터링 수업을 선택하세요.",
  "error.droneUnassigned":
    "이 Tello는 더 이상 현재 수업에 배정되어 있지 않습니다.",
  "error.brainController": "먼저 제한된 MindWave 데모 컨트롤러를 배정하세요.",
  "error.startDemo": "데모를 준비하기 전에 수업을 시작하세요.",
  "error.armFlight": "비행을 준비하기 전에 실제 장치 수업을 시작하세요.",
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
  "error.telloNotVisible":
    "Tello Wi-Fi가 현재 보이지 않습니다. 드론 전원을 켜고 TELLO-*가 표시되면 장치를 다시 검색한 뒤 연결하세요.",
  "error.telloSessionActive":
    "드론 연결은 유지됩니다. 사용 중인 기체 세션 때문에 Wi-Fi 경로만 변경하지 않았습니다.",
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
  "guide.safety.title": "시작 전 안전 확인",
  "guide.safety.description":
    "교실을 확인하고 비상 정지 버튼을 보이게 둔 다음 수업을 시작하세요.",
  "guide.teach.title": "수업 진행 중",
  "guide.teach.description":
    "장치가 준비되었습니다. 아래 수업 제어를 사용하고 수업이 끝나면 세션을 종료하세요.",
  "guide.ready.title": "모두 준비되었습니다",
  "guide.ready.description":
    "요약을 확인한 뒤 학생들이 준비되면 수업을 시작하세요.",
  "guide.action.find": "장치 검색 단계로 이동",
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
    "장치 전원을 켜고 USB 장치를 연결한 뒤 ‘장치 찾기’를 선택하세요. USB, Bluetooth, Wi-Fi, 로컬 서비스와 승인된 Android 휴대전화를 확인합니다.",
  "discovery.checking": "확인 중…",
  "discovery.find": "장치 찾기",
  "discovery.noMovement": "장치는 자동으로 켜지지 않습니다",
  "discovery.safeTitle": "안전한 검색",
  "discovery.safeBody":
    "연결만 확인합니다. 장치를 작동시키거나 원본 센서 데이터를 저장하지 않습니다.",
  "discovery.connectionsReady": "안전하게 연결할 수 있는 항목 {count}개",
  "discovery.connectAllHelp":
    "확인된 어댑터를 한 번에 연결합니다. 로봇, 드론, 플러그와 수업 세션은 계속 잠긴 상태입니다.",
  "discovery.aircraftGrounded":
    "모든 드론이 바닥에 있고 프로펠러가 제거되었거나 보호되어 있습니다.",
  "discovery.connecting": "연결 중…",
  "discovery.connectAll": "사용 가능한 장치 모두 연결",
  "discovery.offState": "움직임 없음 · 승인된 플러그는 전원 꺼짐 상태",
  "discovery.rememberedReady": "기억한 연결 그룹 {count}개",
  "discovery.rememberedHelp":
    "USB, Bluetooth, Wi-Fi 및 Android 전체 검색 없이 이 컴퓨터에 저장된 정확한 어댑터 프로필을 다시 연결합니다. 실제 출력은 잠긴 상태이고 기억한 플러그는 전원 꺼짐 안전 상태가 됩니다.",
  "discovery.connectRemembered": "기억한 장치 연결",
  "discovery.reconnectingRemembered": "다시 연결 중…",
  "discovery.rememberedNoScan": "빠른 재연결 · 출력 잠금 유지",
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
  "discovery.readinessOverview": "장치 준비 상태 요약",
  "discovery.tier.connected.title": "현재 연결됨",
  "discovery.tier.connected.description":
    "실시간 연결이 확인되어 수업에 배정할 수 있는 장치입니다.",
  "discovery.tier.connected.empty": "현재 연결된 장치가 없습니다.",
  "discovery.tier.available.title": "지금 연결 가능",
  "discovery.tier.available.description":
    "발견된 하드웨어와 바로 연결할 수 있는 로컬 서비스입니다.",
  "discovery.tier.available.empty": "지금 추가로 연결할 장치가 없습니다.",
  "discovery.tier.unavailable.title": "현재 사용 불가",
  "discovery.tier.unavailable.description":
    "전원, 페어링, 설정 또는 재검색이 필요한 지원 장치입니다.",
  "discovery.tier.unavailable.empty":
    "현재 별도 설정이 필요한 지원 장치가 없습니다.",
  "discovery.tier.count": "항목 {count}개",
  "discovery.detectedPaths": "발견된 연결 경로 {count}개",
  "discovery.signal": "신호 {percent}%",
  "discovery.connect": "연결",
  "discovery.scanThisDevice": "이 장치 다시 검색",
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

  "deviceIo.title": "실시간 입력 및 출력",
  "deviceIo.help": "사용 가능한 신호와 제어를 바로 표시합니다.",
  "deviceIo.inputs": "장치 입력",
  "deviceIo.outputs": "장치 출력",
  "deviceIo.live": "최신 센서 값",
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
  "lesson.overview": "수업 안내",
  "lesson.materials": "수업 자료",
  "lesson.materialsSummary": "카메라 · 센서",
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
  "safety.locked": "준비됨 · 처음 제어할 때 장치를 자동 준비",
  "safety.physicalHelp":
    "‘모든 장치 정지’ 버튼을 항상 보이게 두고 활동 구역이 비어 있는지 확인하세요.",
  "safety.nonSpatialHelp":
    "장치 제어를 바로 선택하세요. CIT가 로컬 세션을 자동으로 준비합니다.",
  "safety.simulationHelp":
    "실제 교실 장치로 전환하기 전에 안전하게 연습하세요.",
  "safety.confirm":
    "장치가 보이고 활동 구역이 비어 있으며 ‘모든 장치 정지’ 버튼의 위치를 알고 있습니다.",
  "flight.confirmOnce":
    "강사가 현장에 있고, 비행 구역·비상 대응·각 드론 연결 경로를 확인했습니다.",
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
  "media.previewRate": "미리보기 {rate} fps",
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
  "leap.eyebrow": "Leap Motion",
  "leap.title": "실시간 손 감지",
  "leap.intro":
    "컨트롤러 위에 손을 올리세요. 원시 Leap 프레임을 페이지로 보내지 않고 감지된 손바닥, 집기, 쥐기 및 제한된 이동 출력을 의미 기반 화면으로 보여 줍니다.",
  "leap.handDetected": "손 감지됨",
  "leap.waitingHand": "컨트롤러 준비됨",
  "leap.waitingSignal": "추적 신호 대기 중",
  "leap.visualAltDetected": "감지된 {hand}의 실시간 의미 기반 화면",
  "leap.visualAltWaiting": "손을 기다리는 Leap Motion 감지 영역",
  "leap.left": "왼쪽",
  "leap.forward": "앞쪽",
  "leap.right": "오른쪽",
  "leap.leftHand": "왼손",
  "leap.rightHand": "오른손",
  "leap.hand": "감지된 손",
  "leap.pinch": "집기",
  "leap.grab": "쥐기",
  "leap.palm": "손바닥 x / y / z",
  "leap.output": "전진 / 오른쪽 출력",
  "leap.frameRate": "센서 속도",
  "leap.noState": "신호 없음",
  "leap.placeHand": "펼친 손 하나를 컨트롤러 위 10~40 cm에 놓으세요.",
  "leap.selectLesson": "실시간 신호를 볼 Leap 수업 세션을 선택하세요.",
  "leap.noReading": "어댑터가 연결되었습니다. 첫 손 샘플을 기다리는 중입니다.",
  "leap.updated": "최근 손 샘플 {time}",
  "leap.privacy":
    "축약된 손바닥 및 제스처 측정값만 표시합니다. 이 패널은 원시 Leap 프레임이나 카메라 영상을 전송하거나 기록하지 않습니다.",
  "sensor.eyebrow": "실시간 센서",
  "sensor.title": "교실 측정값",
  "sensor.intro":
    "어댑터가 보내는 최신 LEGO, 로봇, 스마트 플러그 전력, 생체 신호 및 배터리 측정값을 자동으로 표시합니다.",
  "sensor.none": "선택한 수업에 아직 센서 값이 들어오지 않았습니다.",
  "plug.eyebrow": "수업 제어",
  "plug.title": "교실 플러그",
  "plug.noneAssigned": "배정된 교실 플러그 없음",
  "plug.compatible": "호환 장치 {count}개 연결됨",
  "plug.unknownState": "알 수 없음",
  "plug.stateUnknown": "이 수업에서 아직 상태를 확인하지 못했습니다",
  "plug.observed": "{time}에 확인{source}",
  "plug.turnOn": "켜기",
  "plug.turnOnHelp": "승인된 교실 부하 켜기",
  "plug.turnOff": "끄기",
  "plug.turnOffHelp": "안전 상태이므로 언제나 사용 가능",
  "plug.onState": "켜짐",
  "plug.offState": "꺼짐",
  "plug.help":
    "켜기 또는 끄기를 바로 선택하세요. CIT가 로컬 제어 세션을 자동으로 준비하며 승인된 교실 부하만 사용해야 합니다.",
  "nodes.eyebrow": "장치 상태",
  "nodes.title": "이 교실에 연결된 모든 장치",
  "nodes.directorySummary": "입력 · 출력 · 연결 상태",
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
    "Tapo P110M 및 호환 Matter Wi-Fi 플러그를 CIT에 직접 연결합니다. 제조사 앱, 계정, 클라우드 API, 장치 ID 또는 로컬 키는 사용하지 않습니다.",
  "matter.ready": "준비됨",
  "matter.required": "필수",
  "matter.wifi.title": "교실 Wi-Fi 한 번 저장",
  "matter.wifi.ready":
    "로컬 컨트롤러에 Wi-Fi가 저장되어 Matter 장치를 추가할 준비가 되었습니다.",
  "matter.wifi.required":
    "이 컴퓨터와 플러그가 사용할 교실 2.4GHz Wi-Fi를 입력하세요.",
  "matter.wifi.scanFirst":
    "먼저 위의 ‘장치 찾기’를 눌러 로컬 컨트롤러 상태를 확인하세요.",
  "matter.wifi.ssid": "Wi-Fi 이름(SSID)",
  "matter.wifi.ssidPlaceholder": "정확한 2.4GHz 네트워크 이름",
  "matter.wifi.password": "Wi-Fi 비밀번호",
  "matter.wifi.passwordPlaceholder": "8~63자",
  "matter.wifi.save": "Wi-Fi를 로컬에 저장",
  "matter.wifi.saving": "Wi-Fi 저장 중…",
  "matter.wifi.memory":
    "비밀번호는 이 PC의 Matter 컨트롤러로만 전송되고 기록되지 않으며 성공 후 페이지에서 지워집니다.",
  "matter.device.title": "각 플러그를 설정 모드로 전환",
  "matter.device.help":
    "플러그를 콘센트에 꽂고 Reset을 10초간 누르세요. 그런 다음 ‘장치 찾기’를 다시 누르세요.",
  "matter.device.found": "주변 {count}개",
  "matter.device.waiting": "대기 중",
  "matter.code.title": "인쇄된 Matter 코드로 추가",
  "matter.code.help":
    "Matter QR 라벨 옆에 인쇄된 11자리 수동 코드 또는 QR 문자열을 입력하세요.",
  "matter.code.locked": "먼저 1단계에서 교실 Wi-Fi 설정을 완료하세요.",
  "matter.tapo.title": "Tapo P110M — 로컬 직접 설정",
  "matter.tapo.support":
    "Tapo 앱과 TP-Link 클라우드 없이 교실 Wi-Fi의 Matter로 지원합니다.",
  "matter.tapo.reset":
    "새 플러그이거나 이전에 설정한 플러그라면 Reset 버튼을 10초간 눌러 공장 초기화하세요.",
  "matter.tapo.window":
    "전원을 껐다 켠 뒤 15분 동안 열리는 Matter 설정 시간 안에 추가하세요.",
  "matter.tapo.network":
    "이 컴퓨터를 같은 로컬 네트워크에 두세요. P110M은 2.4GHz Wi-Fi와 로컬 IPv6/mDNS를 사용합니다.",
  "matter.tapo.code":
    "Tapo 계정이나 로컬 키가 아니라 플러그 본체 또는 포장에 인쇄된 원래 Matter QR/수동 코드를 사용하세요.",
  "matter.tapo.energy":
    "표준 Matter 펌웨어에서 켜기/끄기가 작동합니다. 플러그 펌웨어가 표준 Matter 1.3 측정 클러스터를 제공하면 전력과 에너지가 자동으로 표시됩니다.",
  "matter.code": "Matter 설정 코드",
  "matter.placeholder": "MT:… 또는 1234-567-8901",
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
  "sphero.setup": "발견된 Sphero BOLT",
  "sphero.wake": "BOLT를 충전한 뒤 충전대에서 꺼내 깨우세요.",
  "sphero.closeApps":
    "Sphero Edu, Sphero Play 및 BOLT에 연결된 다른 앱을 모두 닫으세요.",
  "sphero.noPairing":
    "Windows 설정에서 BOLT를 페어링하지 마세요. CIT가 BLE로 직접 연결합니다.",
  "sphero.noneVisible":
    "정확한 SB-XXXX 신호가 보이지 않습니다. BOLT를 깨우고 가까이 둔 뒤 다른 앱을 닫고 ‘장치 찾기’를 다시 선택하세요.",
  "sphero.boltCapabilities": "BOLT · 이동, 조명, 센서",
  "sphero.capabilities": "BOLT · 이동, 조명, 센서",
  "sphero.connecting": "연결 중…",
  "sphero.connectRobot": "연결",
  "sphero.connectSafety":
    "연결하면 제어 잠금 상태의 센서 모니터링만 시작합니다. 방향 지정, 조명 또는 이동 명령은 보내지 않습니다.",
  "sphero.eyebrow": "로봇 제어",
  "sphero.title": "Sphero BOLT",
  "sphero.help":
    "BOLT를 빈 바닥에 놓고 앞 방향을 지정한 뒤 제한된 제어를 바로 사용하세요. ‘모든 장치 정지’를 보이게 두세요.",
  "sphero.aimTitle": "1. 앞 방향 지정",
  "sphero.aimHelp":
    "BOLT를 바닥에 놓고 파란 꼬리 조명이 강사를 향하게 돌리세요. 강사 반대쪽이 앞으로 설정됩니다.",
  "sphero.aimButton": "현재 방향을 앞으로 설정",
  "sphero.drive": "2. 짧은 이동 시험",
  "sphero.forward": "앞으로",
  "sphero.backward": "뒤로",
  "sphero.left": "왼쪽",
  "sphero.right": "오른쪽",
  "sphero.stop": "정지",
  "sphero.nudge":
    "화살표마다 제한된 0.20m/s 짧은 이동을 요청합니다. 승인된 다음 명령이 없으면 BOLT가 750ms 이내에 로컬에서 정지합니다.",
  "sphero.lights": "3. 매트릭스 및 방향 표시등 시험",
  "sphero.color.blue": "파랑",
  "sphero.color.orange": "주황",
  "sphero.color.green": "초록",
  "sphero.color.off": "조명 끄기",
  "ollie.setup": "발견된 Sphero Ollie",
  "ollie.wake": "Ollie를 충전하고 전원을 켜세요.",
  "ollie.closeApps": "Sphero Edu 및 Ollie에 연결된 다른 앱을 모두 닫으세요.",
  "ollie.noPairing":
    "Windows 설정에서 Ollie를 페어링하지 마세요. CIT가 BLE로 직접 연결합니다.",
  "ollie.noneVisible":
    "정확한 2B-XXXX 신호가 보이지 않습니다. Ollie 전원을 켜고 가까이 둔 뒤 다른 앱을 닫고 ‘장치 찾기’를 다시 선택하세요.",
  "ollie.capabilities": "Ollie · 이동, 주 조명, 센서",
  "ollie.connecting": "연결 중…",
  "ollie.connectRobot": "연결",
  "ollie.connectSafety":
    "연결하면 제어 잠금 상태의 센서 모니터링을 시작하고 이동 명령은 보내지 않습니다. 안전 초기화 중 기존 조명이 꺼질 수 있습니다.",
  "ollie.title": "Sphero Ollie",
  "ollie.help":
    "Ollie를 빈 바닥에 놓고 앞 방향을 지정한 뒤 제한된 제어를 사용하세요. ‘모든 장치 정지’를 보이게 두세요.",
  "ollie.aimTitle": "1. 앞 방향 지정",
  "ollie.aimHelp":
    "Ollie의 파란 꼬리 조명을 강사 쪽으로 향하게 하세요. 강사 반대쪽이 앞으로 설정됩니다.",
  "ollie.aimButton": "현재 방향을 앞으로 설정",
  "ollie.drive": "2. 짧은 이동 시험",
  "ollie.nudge":
    "화살표마다 보수적으로 제한된 짧은 이동을 요청합니다. 승인된 다음 명령이 없으면 Ollie가 750ms 이내에 로컬에서 정지합니다.",
  "ollie.lights": "3. 주 조명 시험",
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
    "제어를 바로 선택하면 CIT가 로컬 세션을 자동으로 준비합니다. Dash 이동은 짧고 제한되며 Dot에는 주행 제어가 없습니다.",
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
  "drone.eyebrow": "드론 제어",
  "drone.title": "Tello 비행 제어",
  "drone.help":
    "안전을 한 번 확인한 뒤 이륙하거나 20cm 이동·30° 회전할 수 있습니다.",
  "drone.role": "안전 드론 {number}",
  "drone.checks": "비행 안전 한 번 확인",
  "drone.instructorPresent": "강사 현장 확인",
  "drone.flightAreaClear": "비행 구역 확인",
  "drone.emergencyPlanReady": "비상 대응 확인",
  "drone.sessionReady": "실제 장치 세션이 준비되었습니다.",
  "drone.sessionAutoPrepare": "첫 비행 명령 때 이 장치 세션을 준비합니다.",
  "drone.restartAdapter":
    "현재 비행 제어를 불러오려면 Tello를 다시 연결하세요.",
  "drone.takeoff": "이륙",
  "drone.takeoffConfirm": "{name}을(를) 지금 이륙할까요?",
  "drone.forward": "앞으로 20cm",
  "drone.back": "뒤로 20cm",
  "drone.left": "왼쪽 20cm",
  "drone.right": "오른쪽 20cm",
  "drone.up": "위로 20cm",
  "drone.down": "아래로 20cm",
  "drone.rotateCounterclockwise": "반시계 방향 30°",
  "drone.rotateClockwise": "시계 방향 30°",
  "drone.land": "착륙",
  "drone.landHelp": "정상 착륙 요청",
  "drone.emergency": "모터 비상 정지",
  "drone.emergencyHelp":
    "비행을 계속하는 것보다 모터 정지가 더 안전할 때만 사용",
  "drone.manual": "수동 이동",
  "drone.confirm":
    "{name}의 모터를 비상 정지할까요? 비행 중인 드론은 즉시 떨어질 수 있습니다.",
  "sync.eyebrow": "장치 전체 제어",
  "sync.title": "동기 이동",
  "sync.enable": "연결된 BOLT와 Ollie 함께 제어",
  "sync.groundTargets": "BOLT·Ollie {count}대",
  "sync.includeTello": "Tello 포함 ({count}대)",
  "sync.telloSafety": "비행 안전 확인 후 Tello 제어에서 먼저 이륙하세요.",
  "sync.controls": "동기 이동 제어",
  "sync.forward": "모두 앞으로",
  "sync.backward": "모두 뒤로",
  "sync.left": "모두 왼쪽",
  "sync.right": "모두 오른쪽",
  "sync.stop": "지상 로봇 모두 정지",
  "sync.inputs": "의미 입력",
  "sync.input.g2": "G2 음성",
  "sync.input.r1": "R1 링",
  "sync.input.meta": "Meta 음성",
  "sync.input.mindwave": "MindWave 깜박임",
  "sync.connectWearables": "연결된 입력 배정",
  "sync.inputHelp":
    "G2·Meta 음성과 R1 제스처는 같은 제한 이동을 사용합니다. MindWave 깜박임 한 번은 10cm 데모 한 번만 시작하며 집중도 측정으로 해석하지 않습니다.",
  "sync.ready": "지상 로봇 {count}대의 동기 제어가 준비되었습니다.",
  "sync.disabled": "동기 장치 제어를 껐습니다.",
  "sync.sent": "{count}대에 {direction} 동작을 보냈습니다.",
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
  "brain.flightCheck": "2. 비행 안전 한 번 확인",
  "brain.present": "제가 현장에서 이 비행을 감독하고 있습니다.",
  "brain.areaClear":
    "전체 비행 구역이 비어 있고 보이는 모든 Tello를 확인했으며 바닥에 있습니다.",
  "brain.emergencyReady":
    "착륙과 비상 정지에 바로 접근할 수 있으며, 빠른 전달 뒤 해제된 드론은 현재 Wi-Fi 어댑터에서 더 이상 연결되지 않을 수 있음을 이해했습니다.",
  "brain.runSimulation": "안전한 시뮬레이션 실행",
  "brain.arm": "연결·준비 후 1회 활성화",
  "brain.waitCondition": "선택한 MindWave 조건을 기다립니다",
  "brain.startFirst": "먼저 수업을 시작하세요",
  "brain.startArmFirst": "수업 시작과 실제 장치 준비를 함께 처리합니다",
  "brain.stop": "데모 정지 및 해제",
  "brain.stopHelp":
    "조건 대기 전이나 실행 중에도 사용할 수 있는 안전 상태 명령",
  "fleet.eyebrow": "다중 입력 드론 순차 비행",
  "fleet.title": "Tello 드론 전체 제어",
  "fleet.helpBefore":
    "먼저 순서를 정해 한 번만 실행할 계획을 준비하세요. 그다음",
  "fleet.startNow": "지금 시작",
  "fleet.helpAfter":
    "버튼, Leap의 손 펼침→집기 제스처 또는 배정된 G2/Meta 안경의 ‘드론 순차 비행 시작’ 음성을 사용하세요. 입력은 비행을 활성화할 수 없으며 강사가 현재 준비한 1회 계획만 실행할 수 있습니다.",
  "fleet.current": "현재 상태",
  "fleet.airborne": "이륙 확인됨",
  "fleet.waiting": "드론 컨트롤러의 첫 상태 업데이트를 기다리는 중입니다.",
  "fleet.order": "이륙·착륙 순서",
  "fleet.connectController":
    "승인된 드론 목록을 보려면 Brain2Devices 드론 컨트롤러를 연결하세요.",
  "fleet.aircraftState": "{connection} · {flight} · 배터리 {battery}%",
  "fleet.earlier": "{name}을(를) 앞 순서로 이동",
  "fleet.later": "{name}을(를) 뒤 순서로 이동",
  "fleet.remove": "제외",
  "fleet.interval": "이륙 확인 후 다음 이륙까지 초",
  "fleet.minimumBattery": "모든 드론의 최소 배터리",
  "fleet.inputs": "허용할 입력",
  "fleet.tutorButton": "강사의 ‘지금 시작’ 버튼",
  "fleet.noInputs":
    "Leap, G2 또는 Meta 입력이 배정되지 않았습니다. 강사 버튼은 계속 사용할 수 있습니다.",
  "fleet.flightCheck": "비행 안전 한 번 확인",
  "fleet.present": "제가 현장에서 모든 드론을 감독하고 있습니다.",
  "fleet.areaClear":
    "전체 비행 구역이 비어 있고 선택한 모든 드론이 바닥에 있는 것을 직접 확인했습니다.",
  "fleet.emergencyReady":
    "‘정지 및 착륙’과 각 드론의 비상 제어에 바로 접근할 수 있습니다.",
  "fleet.routes":
    "기본 Tello마다 연결된 Wi-Fi 경로가 하나씩 있거나 스테이션 모드 드론마다 서로 다른 접근 가능한 주소가 있습니다.",
  "fleet.notReady":
    "선택한 모든 드론이 연결되고 착륙 상태가 확인되며 최소 배터리 이상이어야 합니다.",
  "fleet.arm": "연결·준비 후 1회 활성화",
  "fleet.prepareTriggers": "링·센서 입력 준비",
  "fleet.takeoffOneByOne": "한 대씩 이륙",
  "fleet.landOneByOne": "한 대씩 착륙",
  "fleet.options": "순서·입력 설정",
  "fleet.optionsSummary":
    "{interval}초 간격 · 배터리 {battery}% 이상 · 입력 {inputs}개",
  "fleet.armHelp": "아직 이륙하지 않음 · 60초 후 만료",
  "fleet.startArmFirst": "수업 시작과 실제 장치 준비를 함께 처리합니다",
  "fleet.startHelp": "Leap 및 안경과 같은 제한 명령을 사용합니다",
  "fleet.stop": "선택한 드론 정지 및 착륙",
  "fleet.stopHelp": "아직 시작하지 않은 이륙도 취소합니다",
  "fleet.leapInstruction": "손을 펼친 뒤 집기",
  "fleet.ringInstruction": "R1 링 두 번 탭",
  "fleet.voiceInstruction": "‘드론 순차 비행 시작’이라고 말하기",
  "course.deviceMonitoring.name": "장치, 센서, 카메라 및 안전 데모",
  "course.deviceMonitoring.summary": "카메라, 센서 및 제한된 드론 데모",
  "course.deviceMonitoring.description":
    "카메라, Tello 텔레메트리, MindWave 제조사 신호와 LEGO 센서 값을 보여 줍니다. 선택 기능으로 명시적으로 활성화하는 MindWave 데모와 버튼, Leap, R1, G2 또는 Meta로 시작하는 강사 승인 순차 드론 비행을 제공합니다.",
  "course.glasses.name": "안경과 코딩 도우미",
  "course.glasses.summary": "안경 + 코딩 도우미",
  "course.glasses.description":
    "학생이 안경에서 코딩 도우미에게 요청을 보내고 교실 화면에서 답변을 확인합니다.",
  "course.glassesControl.name": "안경으로 장치 제어",
  "course.glassesControl.summary": "G2 또는 Meta + 배정한 로봇과 드론",
  "course.glassesControl.description":
    "확인된 G2 또는 Meta 음성 명령으로 배정한 RoboMaster, Sphero, LEGO 또는 Dash를 동시에 움직입니다. Tello 이륙에는 별도의 강사 비행 확인과 1회 준비가 계속 필요합니다.",
  "course.gesture.name": "제스처로 로봇 제어",
  "course.gesture.summary": "제스처 + 교실 로봇",
  "course.gesture.description":
    "학생이 손 제스처로 교실 로봇을 조종하고 CIT가 움직임을 수업 안전 범위로 제한합니다.",
  "course.ring.name": "R1 스마트 링 장치 제어",
  "course.ring.summary": "R1 입력 + 배정한 로봇과 드론",
  "course.ring.description":
    "R1을 위아래로 스크롤하면 배정한 RoboMaster, Sphero, LEGO 또는 Dash에 짧고 제한된 전진·후진 신호를 보냅니다. 탭은 속도 0을 요청하고, 더블 탭은 별도로 준비된 Tello 순차 비행만 시작할 수 있습니다.",
  "course.simultaneous.name": "여러 장치 동시 실행",
  "course.simultaneous.summary": "입력 하나 + 여러 동시 출력",
  "course.simultaneous.description":
    "승인된 Leap, R1 또는 안경 입력 하나로 배정된 RoboMaster, Sphero, LEGO, Dash, 활성화된 Tello 그룹과 안경 화면에 제한된 동작을 동시에 보냅니다. 모든 출력은 따로 안전 검사를 받습니다.",
  "course.synchronized.name": "동기 모터 장치 제어",
  "course.synchronized.summary": "G2·R1·Meta·MindWave + BOLT·Ollie",
  "course.synchronized.description":
    "명시적인 전체 제어 체크박스로 G2·Meta 음성, R1 제스처와 한 번씩 처리되는 MindWave 깜박임을 배정한 BOLT·Ollie에 함께 보냅니다. Tello는 별도 비행 확인이 필요한 선택 경로입니다.",
  "course.plug.name": "교실 스마트 플러그",
  "course.plug.summary": "강사가 개별 제어하는 교실 플러그",
  "course.plug.description":
    "강사가 이 화면에서 승인된 교실 램프 또는 다른 저위험 부하를 최대 두 개까지 각각 켜고 끕니다.",
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
  "role.plug.name": "교실 플러그 1",
  "role.plug.description": "첫 번째 승인된 교실 부하를 켜거나 끕니다",
  "role.plug2.name": "교실 플러그 2",
  "role.plug2.description":
    "두 번째 승인된 교실 부하를 선택적으로 개별 제어합니다",
  "role.agent.name": "코딩 도우미",
  "role.agent.description": "학생 요청을 받고 코딩 진행 상황을 돌려줍니다",
  "role.feedback.name": "피드백 화면",
  "role.feedback.description": "코딩 진행 상황과 수업 메시지를 표시합니다",
  "role.gesture.name": "제스처 입력 장치",
  "role.gesture.description": "손 움직임을 수업에 보냅니다",
  "role.smartRing.name": "R1 스마트 링 입력",
  "role.smartRing.description":
    "G2와 연결된 휴대폰 경로를 통해 탭, 더블 탭 및 스크롤 동작을 구조화하여 보냅니다",
  "role.console.name": "강사 화면",
  "role.console.description": "강사에게 수업 활동을 보여 줍니다",
  "role.glasses.name": "학생 안경",
  "role.glasses.description": "학생 입력을 보내고 수업 피드백을 표시합니다",
  "role.glassesInput.name": "안경 제어 입력 {number}",
  "role.glassesInput.description":
    "원본 음성 기록이나 제조사 패킷 없이 확인된 G2 또는 Meta 장치 명령만 구조화하여 보냅니다",
  "role.robot.name": "교실 로봇",
  "role.robot.description": "제한된 이동 및 정지 지시를 받습니다",
  "role.safetyDrone.name": "안전 드론 {number}",
  "role.safetyDrone.description":
    "Tello 상태를 보내고 착륙 또는 비상 정지만 받습니다",
  "role.fleetInput.name": "드론 시작 입력 {number}",
  "role.fleetInput.description":
    "Leap, R1, G2 또는 Meta를 통해 현재 준비된 순차 비행을 요청합니다",
  "role.groundOutput.name": "지상 로봇 출력 {number}",
  "role.groundOutput.description":
    "동일한 제한 속도 및 감시 타이머가 적용된 이동 신호를 받습니다. RoboMaster, Sphero, LEGO 또는 Dash를 배정하세요",
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
      "페어링된 Android 휴대전화에서 Tailscale을 연결하고 Even 앱을 여세요.",
      "Even Hub에서 설정된 CIT 안경 프로토타입을 여세요.",
      "이 카드에서 G2 연결을 선택하고 안경을 착용한 뒤 음성 또는 버튼 입력을 한 번 사용하세요.",
      "다시 검색하면 실시간 보조 앱 신호를 받은 G2가 연결됨으로 표시됩니다.",
      "‘안경과 코딩 에이전트’ 수업에서 G2와 Codex 또는 Claude 세션을 배정하면 음성·버튼 요청을 보내고 완료 문구를 받을 수 있습니다.",
      "Telegram은 페어링한 휴대전화에 두고 Even 앱 → 설정 → 알림에서 Telegram을 켜면 휴대전화 알림을 G2에 표시할 수 있습니다.",
    ],
    safetyNote:
      "Fabric에는 의미 있는 상호작용과 제한된 화면 텍스트만 들어옵니다. 원본 마이크 음성은 검색하거나 기록하지 않습니다.",
  },
  "even-realities-r1": {
    displayName: "Even R1 스마트 링",
    connectionMethod: "Even 앱과 G2를 통한 Bluetooth",
    setupSteps: [
      "Even 앱에 G2를 먼저 연결한 뒤 같은 앱에서 R1 링을 추가하세요.",
      "휴대전화의 Even Hub에서 설정된 CIT 안경 플러그인을 여세요.",
      "이 카드에서 R1 입력 연결을 선택한 뒤 R1을 한 번 탭하거나 스크롤해 링 입력을 등록하세요.",
      "R1 스마트 링 장치 제어를 선택하고 R1을 입력 역할에, 사용할 로봇 또는 드론 컨트롤러를 출력 역할에 배정하세요.",
      "수업을 시작하세요. 스크롤은 짧은 지상 이동, 탭은 속도 0, 더블 탭은 별도로 준비된 Tello 순차 비행을 요청합니다.",
    ],
    safetyNote:
      "링 제스처는 구조화된 입력으로만 전달됩니다. 두 번 탭해도 수업 시작, 중재 및 드론 안전 검사를 건너뛸 수 없습니다.",
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
      "연결한 뒤 수업을 시작하거나 화면의 제한된 장치 제어를 바로 선택하세요.",
    ],
    safetyNote:
      "네트워크 이름만으로 로봇이라고 판단하지 않습니다. 어댑터 핸드셰이크가 실제 장치를 확인하며 이동은 계속 잠긴 상태입니다.",
  },
  "sphero-bolt": {
    displayName: "Sphero BOLT",
    connectionMethod: "로컬 Bluetooth 저전력(BLE)",
    setupSteps: [
      "BOLT를 충전하고 충전대에서 꺼내 깨운 뒤 정확한 SB-XXXX 이름을 확인하세요. Windows 설정에서 페어링하지 마세요.",
      "현재 이 로봇에 연결된 Sphero Edu, Sphero Play 또는 다른 프로그램을 닫으세요.",
      "‘장치 찾기’를 선택한 뒤 연결할 정확한 SB-XXXX ID 버튼을 선택하세요.",
      "파란 꼬리 조명이 강사를 향하게 한 뒤 화면에서 현재 방향을 앞으로 설정하세요. CIT가 제어 세션을 자동으로 준비합니다.",
    ],
    safetyNote:
      "검색은 읽기 전용이며 가장 가까운 로봇을 자동 선택하지 않습니다. 이동은 0.20m/s로 제한되고 750ms 로컬 자동 정지가 적용됩니다.",
  },
  "sphero-ollie": {
    displayName: "Sphero Ollie",
    connectionMethod: "로컬 Bluetooth 저전력(BLE)",
    setupSteps: [
      "Ollie를 충전하고 전원을 켠 뒤 정확한 2B-XXXX 이름을 확인하세요. Windows 설정에서 페어링하지 마세요.",
      "현재 이 로봇에 연결된 Sphero Edu 또는 다른 프로그램을 닫으세요.",
      "‘장치 찾기’를 선택한 뒤 연결할 정확한 2B-XXXX ID 버튼을 선택하세요.",
      "빈 바닥에서 파란 꼬리 조명이 강사를 향하게 한 뒤 화면에서 현재 방향을 앞으로 설정하세요.",
    ],
    safetyNote:
      "검색은 읽기 전용이며 가장 가까운 로봇을 자동 선택하지 않습니다. 이동에는 보수적인 속도 상한과 750ms 로컬 자동 정지가 적용됩니다.",
  },
  "wonder-workshop-dash-dot": {
    displayName: "Wonder Workshop Dash 및 Dot",
    connectionMethod: "로컬 Bluetooth 저전력(BLE)",
    setupSteps: [
      "Dash 또는 Dot을 충전하고 전원을 켠 뒤 이 Windows 컴퓨터 가까이에 두세요.",
      "현재 로봇에 연결된 Wonder, Blockly 또는 다른 앱을 닫으세요.",
      "‘장치 찾기’를 선택하고 정확한 이름의 Dash 또는 Dot을 고른 뒤 ‘선택한 로봇 연결’을 선택하세요.",
      "연결 후 화면에서 조명, 소리, 머리 또는 제한된 이동 제어를 바로 선택하세요. CIT가 제어 세션을 자동으로 준비합니다.",
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
      "‘연결 가능한 모든 드론 연결’을 선택하세요. 연결된 드론과 호환 입력은 자동 선택됩니다.",
      "비행 안전을 한 번 확인한 뒤 ‘한 대씩 이륙’ 또는 ‘링·센서 입력 준비’를 선택하세요.",
    ],
    safetyNote:
      "검색과 연결은 이륙이나 이동 명령을 보내지 않습니다. 수동 제어는 강사 확인과 이동 제한을 적용하고, 별도 컨트롤러는 드론 1~8대의 제한된 순차 비행만 제공합니다.",
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
      "Attention은 기본 선택됩니다. 안전을 한 번 확인한 뒤 ‘연결·준비 후 1회 활성화’를 선택하면 수업 시작과 실제 장치 준비를 함께 처리합니다.",
    ],
    safetyNote:
      "센서 및 드론 어댑터와 분리된 1회 실행 과정입니다. 일반 이륙이나 이동 명령이 없으며 자동 에이전트가 활성화할 수 없습니다.",
  },
  "matter-smart-plugs": {
    displayName: "Matter 스마트 플러그",
    connectionMethod: "로컬 Matter over Wi-Fi / IPv6",
    setupSteps: [
      "Tapo P110M은 플러그 본체나 포장에 인쇄된 Matter 코드로 지원합니다. Tapo 앱이나 TP-Link 계정은 필요하지 않습니다.",
      "새 P110M 또는 초기화한 P110M은 Reset 버튼을 10초간 누르고 전원을 껐다 켠 뒤 15분의 Matter 설정 시간 안에 추가하세요.",
      "CIT 컴퓨터를 IPv6/mDNS가 되는 같은 로컬 네트워크에 두고, 플러그에는 2.4GHz Wi-Fi를 사용한 뒤 아래에 인쇄된 코드를 입력하세요.",
    ],
    safetyNote:
      "추가 과정에서 부하를 켜지 않습니다. 연결 시 승인된 각 콘센트를 꺼진 안전 상태로 두며, 표준 Matter 1.3 에너지 정보가 있으면 읽기 전용으로 표시합니다.",
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
  "cit.even-g2.connect": "G2 연결",
  "cit.even-r1.connect": "R1 입력 연결",
  "cit.robomaster-leap.connect": "RoboMaster와 Leap 연결",
  "cit.matter-smart-plug.connect": "등록된 플러그 연결",
  "cit.lego-pybricks.connect": "설정된 LEGO 허브 연결",
  "brain2devices.mindwave.connect": "헤드셋 연결",
  "brain2devices.tello.connect-all": "연결 가능한 모든 드론 연결",
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
  "glasses-device-control": [
    "course.glassesControl.name",
    "course.glassesControl.summary",
    "course.glassesControl.description",
  ],
  "gesture-ground-robot": [
    "course.gesture.name",
    "course.gesture.summary",
    "course.gesture.description",
  ],
  "smart-ring-device-control": [
    "course.ring.name",
    "course.ring.summary",
    "course.ring.description",
  ],
  "simultaneous-device-cue": [
    "course.simultaneous.name",
    "course.simultaneous.summary",
    "course.simultaneous.description",
  ],
  "synchronized-motor-control": [
    "course.synchronized.name",
    "course.synchronized.summary",
    "course.synchronized.description",
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
    classroom_plug_2: ["role.plug2.name", "role.plug2.description"],
    coding_agent: ["role.agent.name", "role.agent.description"],
    feedback_display: ["role.feedback.name", "role.feedback.description"],
    gesture_input: ["role.gesture.name", "role.gesture.description"],
    smart_ring_input: ["role.smartRing.name", "role.smartRing.description"],
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
      /^glasses_input_(\d+)$/,
      "role.glassesInput.name",
      "role.glassesInput.description",
    ) ??
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
    "sphero.aim.reset": "Sphero 앞 방향 재설정",
    "telemetry.power.electrical": "플러그 전력 및 에너지",
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
