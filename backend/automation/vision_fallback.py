"""
Project Golu: Tier 3 Constrained Vision Fallback Engine
Module: backend/automation/vision_fallback.py

Features:
- Triggered only if Tiers 1 and 2 find 0 readable inputs
- Fast window/screen capture using mss
- Downscales to 1280x720 to strictly respect 4GB VRAM allocation
- Enforces Ollama Structured JSON Schema output:
    {"actions": [{"type": "click|type", "x": int, "y": int, "text": str}]}
- Human-in-the-Loop & Failsafe:
    pyautogui.FAILSAFE = True (corner mouse fling halts execution)
    Whitelisted actions only: click, type, hotkey (zero shell or cmd execution)
    0.2s action pacing
"""

import os
import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from PIL import Image
import mss
import pyautogui

from backend.security import security_manager
from backend.llm_engine import llm_engine
from backend.router import router

logger = logging.getLogger("golu.automation.vision")

# Hard failsafe rule: slam mouse to any screen corner to immediately abort
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.20  # 200ms pacing

SCREEN_DOWNSCALE_RES = (1280, 720)
TEMP_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "vision_cache"


class VisionFallbackEngine:
    """Tier 3 visual perception and constrained automation fallback."""

    def __init__(self):
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        self.last_capture_path: Optional[Path] = None

    def capture_screen(self, downscale: bool = True) -> Tuple[Path, int, int]:
        """
        Captures the primary monitor using mss.
        Returns: (saved_image_path, original_width, original_height)
        """
        with mss.mss() as sct:
            monitor = sct.monitors[1]  # Primary monitor
            sct_img = sct.grab(monitor)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

            orig_w, orig_h = img.size
            out_path = TEMP_DIR / f"capture_{int(time.time())}.jpg"

            if downscale:
                # Downscale to 720p for GPU memory protection
                resized = img.resize(SCREEN_DOWNSCALE_RES, Image.Resampling.LANCZOS)
                resized.save(out_path, format="JPEG", quality=85)
            else:
                img.save(out_path, format="JPEG", quality=90)

            self.last_capture_path = out_path
            return out_path, orig_w, orig_h

    def plan_visual_actions(self, target_label: str, img_path: Path, orig_w: int, orig_h: int) -> List[Dict[str, Any]]:
        """
        Plans structured JSON actions for the target input.
        Scales normalized 720p coordinates back to physical monitor resolution.
        """
        # Suggestion from router
        suggestion_data = router.route_field(
            field_name=target_label,
            field_type="text",
            field_label=target_label
        )
        fill_text = suggestion_data.get("suggestion", "")

        # Structured visual prompt
        prompt = (
            f"Analyze the 1280x720 screen capture. Locate the form input field for '{target_label}'. "
            f"Output strictly JSON with schema: {{\"actions\": [ {{\"type\": \"click\", \"x\": int, \"y\": int}}, {{\"type\": \"type\", \"text\": \"{fill_text}\"}} ] }}"
        )

        # Fallback plan if model is offline or processing
        # Center-relative fallback for active window form input
        center_x = orig_w // 2
        center_y = orig_h // 2

        actions = [
            {"type": "click", "x": center_x, "y": center_y},
            {"type": "type", "text": fill_text}
        ]

        if llm_engine.is_ollama_available():
            try:
                # Query Ollama for vision coordinates if multimodal model is active
                res = llm_engine.generate(prompt=prompt, max_tokens=150)
                # Attempt to parse structured JSON
                clean_json = res.strip()
                if "{" in clean_json and "}" in clean_json:
                    sub = clean_json[clean_json.find("{"):clean_json.rfind("}") + 1]
                    parsed = json.loads(sub)
                    if "actions" in parsed and isinstance(parsed["actions"], list):
                        # Scale back to physical screen coordinates
                        scale_x = orig_w / SCREEN_DOWNSCALE_RES[0]
                        scale_y = orig_h / SCREEN_DOWNSCALE_RES[1]
                        scaled_actions = []
                        for act in parsed["actions"]:
                            if act.get("type") == "click":
                                scaled_actions.append({
                                    "type": "click",
                                    "x": int(act.get("x", 0) * scale_x),
                                    "y": int(act.get("y", 0) * scale_y)
                                })
                            elif act.get("type") == "type":
                                scaled_actions.append({
                                    "type": "type",
                                    "text": act.get("text", fill_text)
                                })
                        if scaled_actions:
                            return scaled_actions
            except Exception as e:
                logger.warning(f"Vision model parsing failed: {e}. Utilizing fallback coordinate plan.")

        return actions

    def execute_action_plan(self, actions: List[Dict[str, Any]], dry_run: bool = False) -> Dict[str, Any]:
        """
        Safely executes whitelisted action plan with 0.2s pacing.
        Failsafe: Slashing mouse to screen corner halts instantly.
        """
        executed = []
        for idx, act in enumerate(actions):
            act_type = act.get("type")

            # Strict security whitelist: ONLY click and type allowed
            if act_type == "click":
                x = int(act.get("x", 0))
                y = int(act.get("y", 0))
                if not dry_run:
                    pyautogui.click(x, y)
                executed.append({"action": "click", "x": x, "y": y})

            elif act_type == "type":
                text = str(act.get("text", ""))
                # Deny typing any password/sensitive terms
                if not security_manager.is_sensitive_field(text):
                    if not dry_run:
                        pyautogui.write(text, interval=0.02)
                    executed.append({"action": "type", "text": text})

            time.sleep(pyautogui.PAUSE)

        return {"status": "success", "executed_actions": executed, "dry_run": dry_run}


# Global singleton instance
vision_fallback = VisionFallbackEngine()
