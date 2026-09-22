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
    direction_degrees: float | None = None
    layer: str = "base"
    additive: bool = False
    root_motion: bool = True


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
    previous_state: str | None = None
    delta_time: float = 0.0
    root_motion_enabled: bool = True
    upper_body_action: str | None = None
    emote: str | None = None


@dataclass(frozen=True)
class AnimationOutput:
    state: str
    clip_id: str | None
    blend: float
    normalized_time: float
    root_motion: bool
    reason: str
    action_name: str | None = None
    direction_degrees: float = 0.0
    transition: str | None = None
    transition_duration: float = 0.0
    layers: tuple[dict, ...] = ()
    root_motion_mode: str = "disabled"
    additive_clip_id: str | None = None


class AnimationGraph:
    def __init__(self, clips: Iterable[MotionClip]) -> None:
        self.clips = tuple(clips)

    def evaluate(self, inputs: AnimationInput) -> AnimationOutput:
        if inputs.emote:
            clip = self._select(inputs.emote, inputs.equipment_type, inputs.combo_index)
            return self._output("emote", clip, inputs.action_time, False, "emote input", inputs)
        if inputs.action:
            state = self._action_state(inputs.action, inputs.action_time)
            clip = self._select(inputs.action, inputs.equipment_type, inputs.combo_index)
            return self._output(state, clip, inputs.action_time, False, "action state", inputs)
        if not inputs.grounded:
            clip = self._select("jump", inputs.equipment_type, 0)
            return self._output("jump", clip, 0.0, True, "not grounded", inputs)
        if inputs.crouched:
            clip = self._select("crouch", inputs.equipment_type, 0)
            return self._output("crouch", clip, 0.0, True, "crouch input", inputs)
        speed = max(0.0, inputs.speed)
        if speed < 0.1:
            state = "idle"
        elif inputs.sprinting:
            state = "sprint"
        elif speed < 2.0:
            state = "walk"
        else:
            state = "run"
        clip = self._select_directional(state, inputs.direction_degrees, inputs.equipment_type)
        return self._output(state, clip, 0.0, True, f"locomotion speed={speed:.3f} direction={inputs.direction_degrees:.1f}", inputs)

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

    def _select_directional(self, state: str, direction_degrees: float, equipment_type: str | None) -> MotionClip | None:
        candidates = [clip for clip in self.clips if self._matches(clip, state, equipment_type)]
        if not candidates:
            return None
        desired = direction_degrees % 360.0
        def distance(clip: MotionClip) -> float:
            if clip.direction_degrees is not None:
                raw = abs((clip.direction_degrees - desired + 180.0) % 360.0 - 180.0)
                return raw
            name = f"{clip.category} {clip.name}".lower()
            aliases = {"forward": 0.0, "right": 90.0, "back": 180.0, "left": 270.0}
            for alias, angle in aliases.items():
                if alias in name:
                    return abs((angle - desired + 180.0) % 360.0 - 180.0)
            return 45.0
        return min(candidates, key=lambda clip: (0 if clip.required_equipment_type == equipment_type else 1, distance(clip)))

    @staticmethod
    def _matches(clip: MotionClip, state: str, equipment_type: str | None) -> bool:
        normalized = f"{clip.category} {clip.name}".lower()
        if state.lower() not in normalized:
            return False
        return clip.required_equipment_type is None or clip.required_equipment_type == equipment_type

    def _output(self, state: str, clip: MotionClip | None, elapsed: float, root_motion: bool, reason: str, inputs: AnimationInput) -> AnimationOutput:
        transition = f"{inputs.previous_state}->{state}" if inputs.previous_state and inputs.previous_state != state else None
        transition_duration = 0.18 if transition else 0.0
        if clip is None:
            return AnimationOutput(state=state, clip_id=None, blend=0.0, normalized_time=0.0, root_motion=False, reason=f"No compatible clip: {reason}", direction_degrees=inputs.direction_degrees, transition=transition, transition_duration=transition_duration)
        normalized_time = (elapsed / clip.duration) % 1.0 if clip.duration > 0 else 0.0
        use_root_motion = root_motion and inputs.root_motion_enabled and clip.root_motion
        layers: list[dict] = [{"name": "base", "clip_id": clip.id, "weight": 1.0, "mask": "full_body"}]
        additive = next((candidate for candidate in self.clips if candidate.additive and self._matches(candidate, state, inputs.equipment_type)), None)
        if additive:
            layers.append({"name": "additive", "clip_id": additive.id, "weight": 0.35, "mask": "upper_body"})
        if inputs.upper_body_action:
            upper = self._select(inputs.upper_body_action, inputs.equipment_type, inputs.combo_index)
            if upper:
                layers.append({"name": "upper_body", "clip_id": upper.id, "weight": 1.0, "mask": "spine_to_hands"})
        return AnimationOutput(state=state, clip_id=clip.id, blend=1.0, normalized_time=normalized_time, root_motion=use_root_motion, reason=reason, action_name=clip.name, direction_degrees=inputs.direction_degrees, transition=transition, transition_duration=transition_duration, layers=tuple(layers), root_motion_mode="apply" if use_root_motion else "in_place", additive_clip_id=additive.id if additive else None)
