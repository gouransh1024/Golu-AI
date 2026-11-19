"""
Project Golu: Tier 2 Desktop UI Automation Engine
Module: backend/automation/desktop_uia.py

Features:
- Inspects native Windows applications, PDF readers, and system dialogs
- Directly queries the Windows Accessibility Tree via uiautomation without taking screenshots
- Extracts input controls (EditControl, ComboBoxControl) with exact screen bounding coordinates
- Enforces security deny-list (ignores IsPassword controls and PIN/credential fields)
- Direct value injection via UIA ValuePattern or typed input
"""

import os
import sys
import time
import logging
from typing import List, Dict, Any, Optional

# Configure temporary comtypes cache to avoid permission errors
import tempfile
gen_dir = os.path.join(tempfile.gettempdir(), "golu_comtypes_cache")
os.makedirs(gen_dir, exist_ok=True)
os.environ["COMTYPES_CACHE"] = gen_dir

import uiautomation as auto
from backend.security import security_manager
from backend.router import router

logger = logging.getLogger("golu.automation.uia")


class DesktopUIAEngine:
    """Tier 2 native Windows Accessibility Tree automation engine."""

    def __init__(self):
        auto.SetGlobalSearchTimeout(1.5)

    def get_active_window(self) -> Optional[auto.WindowControl]:
        """Returns the currently focused top-level window."""
        try:
            return auto.GetForegroundControl()
        except Exception as e:
            logger.warning(f"Failed to get active window: {e}")
            return None

    def scan_window_inputs(self, window: Optional[auto.WindowControl] = None) -> List[Dict[str, Any]]:
        """
        Scans window controls and returns all visible, unblocked text edit controls.
        Returns:
            [
                {
                    "control": Control object,
                    "name": str,
                    "automation_id": str,
                    "type": "EditControl",
                    "rect": (left, top, right, bottom),
                    "current_value": str,
                    "is_password": bool
                }
            ]
        """
        target = window or self.get_active_window()
        if not target:
            return []

        discovered = []
        try:
            # Find all Edit controls (text fields)
            edit_controls = target.GetChildren()
            # Traverse depth-limited tree
            def traverse(ctrl, depth=0):
                if depth > 5:
                    return
                for child in ctrl.GetChildren():
                    ctrl_type = child.ControlTypeName
                    if ctrl_type in {"EditControl", "DocumentControl"}:
                        # Check password attribute
                        is_pwd = getattr(child, "IsPassword", False)
                        name = child.Name or child.AutomationId or "UnnamedField"

                        # Security check
                        if not is_pwd and not security_manager.is_sensitive_field(name):
                            rect = child.BoundingRectangle
                            # Verify valid onscreen coordinates
                            if rect.width() > 0 and rect.height() > 0:
                                current_val = ""
                                try:
                                    pattern = child.GetValuePattern()
                                    if pattern:
                                        current_val = pattern.Value or ""
                                except Exception:
                                    pass

                                discovered.append({
                                    "control": child,
                                    "name": name,
                                    "automation_id": child.AutomationId or "",
                                    "type": ctrl_type,
                                    "rect": (rect.left, rect.top, rect.right, rect.bottom),
                                    "current_value": current_val,
                                    "is_password": False
                                })
                    traverse(child, depth + 1)

            traverse(target)
        except Exception as e:
            logger.error(f"Error scanning desktop window: {e}")

        return discovered

    def autofill_active_window(self) -> Dict[str, Any]:
        """
        Scans inputs in active desktop window, queries Confidence Router,
        and fills available Vault or grounded RAG suggestions.
        """
        win = self.get_active_window()
        if not win:
            return {"status": "error", "message": "No active foreground window"}

        win_name = win.Name or "ActiveWindow"
        inputs = self.scan_window_inputs(win)

        if not inputs:
            logger.info(f"No accessible UIA input controls found in '{win_name}'. Triggering Tier 3 fallback.")
            return {"status": "fallback_needed", "count": 0, "window": win_name}

        filled_count = 0
        results = []

        for item in inputs:
            ctrl = item["control"]
            name = item["name"]

            # Query router
            suggestion_data = router.route_field(
                field_name=name,
                field_type="text",
                field_label=name
            )

            val = suggestion_data.get("suggestion", "")
            if val and suggestion_data.get("is_valid"):
                try:
                    # Focus and set value
                    ctrl.SetFocus()
                    time.sleep(0.05)
                    pattern = ctrl.GetValuePattern()
                    if pattern:
                        pattern.SetValue(val)
                    else:
                        ctrl.SendKeys(val)
                    filled_count += 1
                    results.append({
                        "field": name,
                        "value": val,
                        "source": suggestion_data.get("source")
                    })
                except Exception as e:
                    logger.warning(f"Failed to fill UIA control '{name}': {e}")

        return {
            "status": "success",
            "window": win_name,
            "filled_count": filled_count,
            "total_detected": len(inputs),
            "results": results
        }


# Global singleton instance
desktop_uia = DesktopUIAEngine()
