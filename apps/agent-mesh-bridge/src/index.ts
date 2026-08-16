/**
 * Milestone 0 exposes policy only. No WebSocket, credential, or command
 * transport is created until the separately approved Agent Mesh milestone.
 */
export {
  authorizeBridgeOperation,
  type BridgeAuthorization,
  type BridgeOperation,
} from "./policy.js";
