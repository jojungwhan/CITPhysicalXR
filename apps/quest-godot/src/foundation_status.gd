extends Control

const MILESTONE := 0
const PHYSICAL_CONTROL_ENABLED := false
const OPENXR_CONFIGURED := false


func foundation_status() -> Dictionary:
	return {
		"milestone": MILESTONE,
		"physical_control": PHYSICAL_CONTROL_ENABLED,
		"openxr_configured": OPENXR_CONFIGURED,
	}
