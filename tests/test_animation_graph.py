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

    def test_directional_blend_tree_contains_interpolated_weights(self) -> None:
        clips = [
            MotionClip("left", "Walk Left", "walk", 1.0, True, direction_degrees=270.0),
            MotionClip("forward", "Walk Forward", "walk", 1.0, True, direction_degrees=0.0),
            MotionClip("right", "Walk Right", "walk", 1.0, True, direction_degrees=90.0),
        ]
        output = AnimationGraph(clips).evaluate(AnimationInput(speed=1.0, direction_degrees=45.0))
        self.assertEqual({entry["clip_id"] for entry in output.blend_tree}, {"forward", "right"})
        self.assertAlmostEqual(sum(entry["weight"] for entry in output.blend_tree), 1.0)

    def test_speed_blend_interpolates_walk_and_sprint(self) -> None:
        clips = [
            MotionClip("walk", "Walk", "walk", 1.0, True),
            MotionClip("sprint", "Sprint", "sprint", 1.0, True),
        ]
        output = AnimationGraph(clips).evaluate(AnimationInput(speed=2.0))
        self.assertEqual({entry["clip_id"] for entry in output.blend_tree}, {"walk", "sprint"})
        self.assertAlmostEqual(sum(entry["weight"] for entry in output.blend_tree), 1.0)

    def test_airborne_states_and_configurable_transition(self) -> None:
        clips = [
            MotionClip("jump_start", "Jump Start", "jump_start", 1.0, False),
            MotionClip("jump_air", "Jump Air", "jump_air", 1.0, True),
            MotionClip("jump_land", "Jump Land", "jump_land", 1.0, False),
        ]
        graph = AnimationGraph(clips)
        self.assertEqual(graph.evaluate(AnimationInput(grounded=False, vertical_velocity=2.0)).state, "jump_start")
        self.assertEqual(graph.evaluate(AnimationInput(grounded=False, vertical_velocity=0.0)).state, "jump_air")
        output = graph.evaluate(AnimationInput(previous_state="jump_air", transition_duration=0.42))
        self.assertEqual(output.state, "jump_land")
        self.assertEqual(output.transition_duration, 0.42)
