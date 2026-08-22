import importlib
import sys
import types
import unittest
from unittest import mock


def _import_cone_scene_without_runtime_dependencies():
    """Import behavior code without requiring a display or OpenGL runtime."""
    pygame = types.ModuleType("pygame")
    pygame.__path__ = []
    pygame_font = types.ModuleType("pygame.font")
    pygame.font = pygame_font

    opengl = types.ModuleType("OpenGL")
    opengl.__path__ = []
    opengl_gl = types.ModuleType("OpenGL.GL")
    opengl_glu = types.ModuleType("OpenGL.GLU")

    modules = {
        "pygame": pygame,
        "pygame.font": pygame_font,
        "OpenGL": opengl,
        "OpenGL.GL": opengl_gl,
        "OpenGL.GLU": opengl_glu,
    }
    with mock.patch.dict(sys.modules, modules):
        return importlib.import_module("cone_scene")


cone_scene = _import_cone_scene_without_runtime_dependencies()


class TeleportTimingTests(unittest.TestCase):
    def test_rapid_cut_range_is_preserved(self):
        with mock.patch.object(cone_scene.random, "random", return_value=0.01):
            with mock.patch.object(
                cone_scene.random, "uniform", return_value=0.2
            ) as uniform:
                self.assertEqual(cone_scene.ConeScene._next_teleport_interval(), 0.2)
                uniform.assert_called_once_with(0.08, 0.4)

    def test_normal_hold_range_is_preserved(self):
        with mock.patch.object(cone_scene.random, "random", return_value=0.5):
            with mock.patch.object(
                cone_scene.random, "uniform", return_value=2.0
            ) as uniform:
                self.assertEqual(cone_scene.ConeScene._next_teleport_interval(), 2.0)
                uniform.assert_called_once_with(0.7, 4.0)


class CameraBehaviorTests(unittest.TestCase):
    def test_teleport_keeps_random_roll_and_aims_at_target(self):
        scene = cone_scene.ConeScene.__new__(cone_scene.ConeScene)
        scene.target_position = [10.0, 20.0, 30.0]
        scene.camera_pos = [0.0, 0.0, 0.0]
        scene.camera_distance = 80.0

        with mock.patch.object(
            cone_scene.random, "uniform", side_effect=[12.0, 90.0]
        ):
            scene.teleport_to_target()

        self.assertAlmostEqual(scene.camera_pos[0], 90.0)
        self.assertAlmostEqual(scene.camera_pos[1], 20.0)
        self.assertAlmostEqual(scene.camera_pos[2], 30.0)
        self.assertAlmostEqual(scene.camera_rotation[0], 0.0)
        self.assertAlmostEqual(scene.camera_rotation[1], -90.0)
        self.assertEqual(scene.camera_rotation[2], 12.0)


class PointerBehaviorTests(unittest.TestCase):
    def test_rotating_pointer_updates_all_axes_slowly(self):
        pointer = cone_scene.GreyCone.__new__(cone_scene.GreyCone)
        pointer.rotates = True
        pointer.rotation = [359.0, 10.0, 20.0]
        pointer.rotation_speed = [2.0, -2.0, 1.0]
        pointer.state = "still"
        pointer.position = [0.0, 0.0, 0.0]
        pointer.velocity = [0.0, 0.0, 0.0]

        pointer.update(1.0)

        self.assertEqual(pointer.rotation, [1.0, 8.0, 21.0])
        self.assertEqual(pointer.position, [0.0, 0.0, 0.0])


if __name__ == "__main__":
    unittest.main()
