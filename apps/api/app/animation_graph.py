from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class MotionClip:
    id: str
    name: str
    category: str
    duration: float
    loop: bool
    required_equipment_type: str | None = None


@dataclass(frozen=True)
class AnimationInput:
    speed: float = 0.0
    direction_degrees: float = 0.0
    grounded: bool = True
    crouched: bool = False
    sprinting: bool = False
    equipment_type: str | None = None
    action: str | None = None
    action_time: float = 0.0
    combo_index: int = 0


@dataclass(frozen=True)
class AnimationOutput:
    state: str
    clip_id: str | None
    blend: float
    normalized_time: float
    root_motion: bool
    reason: str
    action_name: str | None = None


class AnimationGraph:
    def __init__(self, clips: Iterable[MotionClip]) -> None:
        self.clips = tuple(clips)

    def evaluate(self, inputs: AnimationInput) -> AnimationOutput:
        if inputs.action:
            state = self._action_state(inputs.action, inputs.action_time)
            clip = self._select(inputs.action, inputs.equipment_type, inputs.combo_index)
            return self._output(state, clip, inputs.action_time, False, "action state")
        if not inputs.grounded:
            clip = self._select("jump", inputs.equipment_type, 0)
            return self._output("jump", clip, 0.0, True, "not grounded")
        if inputs.crouched:
            clip = self._select("crouch", inputs.equipment_type, 0)
            return self._output("crouch", clip, 0.0, True, "crouch input")
        speed = max(0.0, inputs.speed)
        if speed < 0.1:
            state = "idle"
        elif inputs.sprinting:
            state = "sprint"
        elif speed < 2.0:
            state = "walk"
        else:
            state = "run"
        clip = self._select(state, inputs.equipment_type, 0)
        return self._output(state, clip, 0.0, True, f"locomotion speed={speed:.3f} direction={inputs.direction_degrees:.1f}")

    @staticmethod
    def _action_state(action: str, action_time: float) -> str:
        if action_time < 0.2:
            return f"{action}_start"
        if action_time < 0.65:
            return f"{action}_active"
        return f"{action}_recovery"

    def _select(self, state: str, equipment_type: str | None, combo_index: int) -> MotionClip | None:
        candidates = [clip for clip in self.clips if self._matches(clip, state, equipment_type)]
        if not candidates and state.endswith(("_start", "_active", "_recovery")):
            base = state.rsplit("_", 1)[0]
            candidates = [clip for clip in self.clips if self._matches(clip, base, equipment_type)]
        if not candidates:
            return None
        candidates.sort(key=lambda clip: 0 if clip.required_equipment_type == equipment_type else 1)
        return candidates[combo_index % len(candidates)]

    @staticmethod
    def _matches(clip: MotionClip, state: str, equipment_type: str | None) -> bool:
        normalized = f"{clip.category} {clip.name}".lower()
        if state.lower() not in normalized:
            return False
        return clip.required_equipment_type is None or clip.required_equipment_type == equipment_type

    @staticmethod
    def _output(state: str, clip: MotionClip | None, elapsed: float, root_motion: bool, reason: str) -> AnimationOutput:
        if clip is None:
            return AnimationOutput(state=state, clip_id=None, blend=0.0, normalized_time=0.0, root_motion=False, reason=f"No compatible clip: {reason}")
        normalized_time = (elapsed / clip.duration) % 1.0 if clip.duration > 0 else 0.0
        return AnimationOutput(state=state, clip_id=clip.id, blend=1.0, normalized_time=normalized_time, root_motion=root_motion, reason=reason, action_name=clip.name)
