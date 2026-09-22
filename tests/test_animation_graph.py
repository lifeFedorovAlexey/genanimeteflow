from __future__ import annotations

import unittest

from app.animation_graph import AnimationGraph, AnimationInput, MotionClip


CLIPS = [
    MotionClip("idle", "Idle", "idle", 1.0, True),
    MotionClip("walk", "Walk", "walk", 1.0, True),
    MotionClip("rifle_walk", "Rifle Walk", "walk", 1.0, True, "rifle"),
    MotionClip("sword_attack", "Sword Attack", "attack", 1.0, False, "sword"),
]


class AnimationGraphTests(unittest.TestCase):
    def test_locomotion_and_equipment_filtering(self) -> None:
        graph = AnimationGraph(CLIPS)
        self.assertEqual(graph.evaluate(AnimationInput()).clip_id, "idle")
        self.assertEqual(graph.evaluate(AnimationInput(speed=1.0, equipment_type="rifle")).clip_id, "rifle_walk")
        self.assertEqual(graph.evaluate(AnimationInput(speed=3.0, sprinting=True)).state, "sprint")

    def test_attack_has_start_active_recovery_phases(self) -> None:
        graph = AnimationGraph(CLIPS)
        self.assertEqual(graph.evaluate(AnimationInput(action="attack", action_time=0.1, equipment_type="sword")).state, "attack_start")
        self.assertEqual(graph.evaluate(AnimationInput(action="attack", action_time=0.3, equipment_type="sword")).state, "attack_active")
        self.assertEqual(graph.evaluate(AnimationInput(action="attack", action_time=0.8, equipment_type="sword")).state, "attack_recovery")

    def test_output_exposes_playable_action_name(self) -> None:
        output = AnimationGraph(CLIPS).evaluate(AnimationInput(speed=1.0))
        self.assertEqual(output.action_name, "Walk")

    def test_transition_and_root_motion_metadata_are_explicit(self) -> None:
        output = AnimationGraph(CLIPS).evaluate(AnimationInput(speed=1.0, previous_state="idle", root_motion_enabled=False))
        self.assertEqual(output.transition, "idle->walk")
        self.assertEqual(output.root_motion_mode, "in_place")
        self.assertEqual(output.layers[0]["mask"], "full_body")

    def test_directional_clip_is_selected_by_angle(self) -> None:
        clips = [MotionClip("left", "Walk Left", "walk", 1.0, True, direction_degrees=270.0), MotionClip("right", "Walk Right", "walk", 1.0, True, direction_degrees=90.0)]
        output = AnimationGraph(clips).evaluate(AnimationInput(speed=1.0, direction_degrees=85.0))
        self.assertEqual(output.clip_id, "right")
