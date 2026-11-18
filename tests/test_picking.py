import unittest

from sourcebox.rendering.picking import pick, ray_hit_distance
from sourcebox.rendering.shadows import model_matrix

DOWN_Z = [0.0, 0.0, 1.0]


def _matrix(position, rotation=(0.0, 0.0, 0.0), scale=1.0):
    return model_matrix(list(position), list(rotation), [scale] * 3)


class ShapeHitTests(unittest.TestCase):
    def test_sphere_hit_distance_and_miss(self):
        sphere = _matrix([0.0, 0.0, 5.0], scale=2.0)
        self.assertAlmostEqual(ray_hit_distance("sphere", sphere, [0, 0, 0], DOWN_Z), 4.0)
        self.assertIsNone(ray_hit_distance("sphere", sphere, [1.1, 0, 0], DOWN_Z))

    def test_cube_corner_counts_but_bounding_sphere_gap_does_not(self):
        cube = _matrix([0.0, 0.0, 5.0], rotation=(0.0, 0.0, 45.0))
        # rotated 45 degrees about Z, the cube reaches sqrt(0.5) along X
        self.assertIsNotNone(ray_hit_distance("cube", cube, [0.69, 0, 0], DOWN_Z))
        # inside the old 0.866 bounding sphere, outside the cube
        self.assertIsNone(ray_hit_distance("cube", cube, [0.5, 0.5, 0], DOWN_Z))

    def test_cube_hit_from_inside_returns_exit(self):
        cube = _matrix([0.0, 0.0, 0.0])
        self.assertAlmostEqual(ray_hit_distance("cube", cube, [0, 0, 0], DOWN_Z), 0.5)

    def test_cone_side_base_and_miss_near_apex(self):
        # local +Z (apex) points along world +Y after a -90 degree X rotation
        cone = _matrix([0.0, 0.0, 5.0], rotation=(-90.0, 0.0, 0.0))
        # just above the base the cone is almost 0.5 wide
        self.assertIsNotNone(ray_hit_distance("cone", cone, [0.0, 0.1, 0.0], DOWN_Z))
        # near the apex it is narrow
        self.assertIsNone(ray_hit_distance("cone", cone, [0.3, 0.9, 0.0], DOWN_Z))
        # looking straight up through the base disc
        self.assertAlmostEqual(ray_hit_distance("cone", cone, [0.0, -5.0, 5.0], [0, 1, 0]), 5.0)

    def test_hit_behind_the_ray_is_ignored(self):
        sphere = _matrix([0.0, 0.0, -5.0])
        self.assertIsNone(ray_hit_distance("sphere", sphere, [0, 0, 0], DOWN_Z))

    def test_unknown_shape_never_hits(self):
        self.assertIsNone(ray_hit_distance("torus", _matrix([0, 0, 5]), [0, 0, 0], DOWN_Z))


class PickTests(unittest.TestCase):
    def setUp(self):
        self.near_cube = _matrix([0.0, 0.0, 3.0], scale=2.0)
        self.far_sphere = _matrix([0.0, 0.0, 6.0], scale=2.0)

    def test_nearest_shape_wins(self):
        candidates = [("cube", "cube", self.near_cube, False), ("sphere", "sphere", self.far_sphere, False)]
        self.assertEqual(pick(candidates, [0, 0, 0], DOWN_Z), "cube")

    def test_shape_drawn_without_depth_loses_to_anything_behind_it(self):
        candidates = [("cube", "cube", self.near_cube, True), ("sphere", "sphere", self.far_sphere, False)]
        self.assertEqual(pick(candidates, [0, 0, 0], DOWN_Z), "sphere")

    def test_shape_drawn_without_depth_is_picked_when_alone(self):
        candidates = [("cube", "cube", self.near_cube, True), ("sphere", "sphere", self.far_sphere, False)]
        self.assertEqual(pick(candidates, [0.95, 0.95, 0], DOWN_Z), "cube")

    def test_nothing_hit(self):
        candidates = [("sphere", "sphere", self.far_sphere, False)]
        self.assertIsNone(pick(candidates, [5, 5, 0], DOWN_Z))


if __name__ == "__main__":
    unittest.main()
