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
    speed: float | None = None


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
    vertical_velocity: float = 0.0
    transition_duration: float | None = None


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
    blend_tree: tuple[dict, ...] = ()


class AnimationGraph:
    DEFAULT_TRANSITIONS = {
        ("idle", "walk"): 0.18,
        ("walk", "run"): 0.14,
        ("run", "sprint"): 0.12,
        ("sprint", "run"): 0.12,
        ("walk", "idle"): 0.2,
        ("run", "idle"): 0.24,
        ("sprint", "idle"): 0.28,
    }

    def __init__(self, clips: Iterable[MotionClip], transition_durations: dict[tuple[str, str], float] | None = None) -> None:
        self.clips = tuple(clips)
        self.transition_durations = {**self.DEFAULT_TRANSITIONS, **(transition_durations or {})}

    def evaluate(self, inputs: AnimationInput) -> AnimationOutput:
        if inputs.emote:
            clip = self._select(inputs.emote, inputs.equipment_type, inputs.combo_index)
            return self._output("emote", clip, inputs.action_time, False, "emote input", inputs)
        if inputs.action:
            state = self._action_state(inputs.action, inputs.action_time)
            clip = self._select(inputs.action, inputs.equipment_type, inputs.combo_index)
            return self._output(state, clip, inputs.action_time, False, "action state", inputs)
        if not inputs.grounded:
            state = "jump_start" if inputs.vertical_velocity > 0.1 else "jump_air" if inputs.vertical_velocity >= -0.1 else "fall"
            clip = self._select(state, inputs.equipment_type, 0) or self._select("jump", inputs.equipment_type, 0)
            return self._output(state, clip, 0.0, True, "not grounded", inputs)
        if inputs.previous_state in {"jump_start", "jump_air", "fall"}:
            clip = self._select("jump_land", inputs.equipment_type, 0) or self._select("jump", inputs.equipment_type, 0)
            return self._output("jump_land", clip, 0.0, False, "landed after airborne state", inputs)
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
        blend_tree = self._locomotion_blend(state, speed, inputs.direction_degrees, inputs.equipment_type, inputs.sprinting)
        clip = self.clips_by_id(blend_tree[0]["clip_id"]) if blend_tree else None
        return self._output(state, clip, 0.0, True, f"locomotion speed={speed:.3f} direction={inputs.direction_degrees:.1f}", inputs, blend_tree=blend_tree)

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

    def _directional_blend(self, state: str, direction_degrees: float, equipment_type: str | None) -> list[dict]:
        candidates = [clip for clip in self.clips if self._matches(clip, state, equipment_type)]
        if not candidates:
            return []
        desired = direction_degrees % 360.0

        def angle(clip: MotionClip) -> float | None:
            if clip.direction_degrees is not None:
                return clip.direction_degrees % 360.0
            name = f"{clip.category} {clip.name}".lower()
            aliases = {"forward": 0.0, "right": 90.0, "back": 180.0, "left": 270.0}
            for alias, value in aliases.items():
                if alias in name:
                    return value
            return None

        directional = [(clip, angle(clip)) for clip in candidates]
        directional = [(clip, value) for clip, value in directional if value is not None]
        if len(directional) < 2:
            return [{"clip_id": self._select_directional(state, direction_degrees, equipment_type).id, "action_name": self._select_directional(state, direction_degrees, equipment_type).name, "weight": 1.0}]
        directional.sort(key=lambda item: abs((item[1] - desired + 180.0) % 360.0 - 180.0))
        first, second = directional[:2]
        first_distance = abs((first[1] - desired + 180.0) % 360.0 - 180.0)
        second_distance = abs((second[1] - desired + 180.0) % 360.0 - 180.0)
        total = first_distance + second_distance
        first_weight = 0.5 if total <= 1e-6 else second_distance / total
        second_weight = 1.0 - first_weight
        return [
            {"clip_id": first[0].id, "action_name": first[0].name, "weight": round(first_weight, 6)},
            {"clip_id": second[0].id, "action_name": second[0].name, "weight": round(second_weight, 6)},
        ]

    def _locomotion_blend(self, state: str, speed: float, direction_degrees: float, equipment_type: str | None, sprinting: bool) -> tuple[dict, ...]:
        if state == "idle":
            clip = self._select_directional("idle", direction_degrees, equipment_type)
            return () if clip is None else ({"clip_id": clip.id, "action_name": clip.name, "weight": 1.0},)
        target_speed = 3.0 if sprinting or state == "sprint" else max(0.1, speed)
        state_candidates: list[tuple[float, list[dict]]] = []
        for candidate_state, nominal_speed in (("walk", 1.0), ("run", 2.0), ("sprint", 3.0)):
            entries = self._directional_blend(candidate_state, direction_degrees, equipment_type)
            if entries and not any(abs(nominal_speed - current[0]) < 1e-6 for current in state_candidates):
                state_candidates.append((nominal_speed, entries))
        if not state_candidates:
            clip = self._select_directional(state, direction_degrees, equipment_type)
            return () if clip is None else ({"clip_id": clip.id, "action_name": clip.name, "weight": 1.0},)
        ordered = sorted(state_candidates, key=lambda item: item[0])
        if len(ordered) == 1:
            return tuple(ordered[0][1])
        lower = max((item for item in ordered if item[0] <= target_speed), default=ordered[0])
        upper = min((item for item in ordered if item[0] >= target_speed), default=ordered[-1])
        if lower[0] == upper[0]:
            return tuple(lower[1])
        span = max(upper[0] - lower[0], 1e-6)
        upper_weight = min(1.0, max(0.0, (target_speed - lower[0]) / span))
        lower_weight = 1.0 - upper_weight
        return tuple(
            {**entry, "weight": round(float(entry["weight"]) * lower_weight, 6)}
            for entry in lower[1]
        ) + tuple(
            {**entry, "weight": round(float(entry["weight"]) * upper_weight, 6)}
            for entry in upper[1]
        )

    def clips_by_id(self, clip_id: str) -> MotionClip | None:
        return next((clip for clip in self.clips if clip.id == clip_id), None)

    @staticmethod
    def _matches(clip: MotionClip, state: str, equipment_type: str | None) -> bool:
        normalized = f"{clip.category} {clip.name}".lower()
        if state.lower() not in normalized:
            return False
        return clip.required_equipment_type is None or clip.required_equipment_type == equipment_type

    def _output(self, state: str, clip: MotionClip | None, elapsed: float, root_motion: bool, reason: str, inputs: AnimationInput, blend_tree: tuple[dict, ...] = ()) -> AnimationOutput:
        transition = f"{inputs.previous_state}->{state}" if inputs.previous_state and inputs.previous_state != state else None
        transition_duration = inputs.transition_duration if inputs.transition_duration is not None else self.transition_durations.get((inputs.previous_state or "", state), 0.18 if transition else 0.0)
        if clip is None:
            return AnimationOutput(state=state, clip_id=None, blend=0.0, normalized_time=0.0, root_motion=False, reason=f"No compatible clip: {reason}", direction_degrees=inputs.direction_degrees, transition=transition, transition_duration=transition_duration, blend_tree=blend_tree)
        if not blend_tree:
            blend_tree = ({"clip_id": clip.id, "action_name": clip.name, "weight": 1.0},)
        normalized_time = (elapsed / clip.duration) % 1.0 if clip.duration > 0 else 0.0
        use_root_motion = root_motion and inputs.root_motion_enabled and clip.root_motion
        layers: list[dict] = [{"name": "base", "blend_tree": blend_tree, "clip_id": clip.id, "weight": 1.0, "mask": "full_body"}]
        additive = next((candidate for candidate in self.clips if candidate.additive and self._matches(candidate, state, inputs.equipment_type)), None)
        if additive:
            layers.append({"name": "additive", "clip_id": additive.id, "weight": 0.35, "mask": "upper_body"})
        if inputs.upper_body_action:
            upper = self._select(inputs.upper_body_action, inputs.equipment_type, inputs.combo_index)
            if upper:
                layers.append({"name": "upper_body", "clip_id": upper.id, "weight": 1.0, "mask": "spine_to_hands"})
        return AnimationOutput(state=state, clip_id=clip.id, blend=max(float(item["weight"]) for item in blend_tree), normalized_time=normalized_time, root_motion=use_root_motion, reason=reason, action_name=clip.name, direction_degrees=inputs.direction_degrees, transition=transition, transition_duration=transition_duration, layers=tuple(layers), root_motion_mode="apply" if use_root_motion else "in_place", additive_clip_id=additive.id if additive else None, blend_tree=blend_tree)
