/** Generated from config/capability-catalog.yaml. Do not edit. */
export const DEVICE_CONTROL_INTENT_DESCRIPTOR = {
  name: "interaction.intent.device_control",
  version: "1.0",
  maximumRateHz: 4,
  latencyClass: "interactive",
  safetyClassification: "informational",
  dataClassification: "operational",
  constraints: {
    semanticOnly: true,
    structuredIntentOnly: true,
    rawTranscriptExcluded: true,
    confirmedOnly: true,
    exactLessonRoleSelection: true,
    correlatedBatchId: true,
    actions: [
      "forward",
      "backward",
      "left",
      "right",
      "stop",
      "light",
      "demo",
      "takeoff",
      "land",
      "power_on",
      "power_off",
      "activate",
    ],
    targets: [
      "ground_outputs",
      "tello_fleet",
      "power_outputs",
      "assigned_output",
      "all_outputs",
    ],
    payload: {
      action: {
        type: "string",
        enum: [
          "forward",
          "backward",
          "left",
          "right",
          "stop",
          "light",
          "demo",
          "takeoff",
          "land",
          "power_on",
          "power_off",
          "activate",
        ],
      },
      target: {
        type: "string",
        enum: [
          "ground_outputs",
          "tello_fleet",
          "power_outputs",
          "assigned_output",
          "all_outputs",
        ],
      },
      targetRole: {
        type: "string",
        pattern: "^[A-Za-z0-9][A-Za-z0-9._-]*$",
      },
      batchId: {
        type: "string",
        format: "uuid",
      },
      confirmed: {
        type: "boolean",
        const: true,
      },
    },
  },
} as const;
export const DEVICE_CONTROL_INTENT_NAME = DEVICE_CONTROL_INTENT_DESCRIPTOR.name;
export const DEVICE_CONTROL_ACTIONS =
  DEVICE_CONTROL_INTENT_DESCRIPTOR.constraints.actions;
export const DEVICE_CONTROL_TARGETS =
  DEVICE_CONTROL_INTENT_DESCRIPTOR.constraints.targets;
export type DeviceControlAction = (typeof DEVICE_CONTROL_ACTIONS)[number];
export type DeviceControlTarget = (typeof DEVICE_CONTROL_TARGETS)[number];
