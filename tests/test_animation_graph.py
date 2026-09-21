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
