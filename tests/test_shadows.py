import math
import unittest

from sourcebox.rendering.shadows import (
    clip_polygon_to_square,
    invert_affine,
    model_matrix,
    sphere_shadow_on_cube,
    sphere_terminator,
)


def _transform(matrix, point):
    return [sum(matrix[r][c] * point[c] for c in range(3)) + matrix[r][3] for r in range(3)]


def _area(points):
    total = 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]):
        total += x0 * y1 - x1 * y0
    return abs(total) / 2.0


class MatrixTests(unittest.TestCase):
    def test_model_matrix_scales_then_rotates_then_translates(self):
        matrix = model_matrix([1.0, 2.0, 3.0], [0.0, 0.0, 90.0], [2.0, 1.0, 1.0])
        x, y, z = _transform(matrix, [1.0, 0.0, 0.0])
        self.assertAlmostEqual(x, 1.0)
        self.assertAlmostEqual(y, 4.0)
        self.assertAlmostEqual(z, 3.0)

    def test_spin_is_applied_about_local_z_before_scale(self):
        matrix = model_matrix([0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [2.0, 1.0, 1.0], spin=90.0)
        x, y, z = _transform(matrix, [1.0, 0.0, 0.0])
        self.assertAlmostEqual(x, 0.0)
        self.assertAlmostEqual(y, 2.0)
        self.assertAlmostEqual(z, 0.0)

    def test_invert_affine_round_trips_points(self):
        matrix = model_matrix([0.4, -1.2, 5.0], [33.0, -71.0, 12.5], [1.3, 0.7, 2.1])
        inverse = invert_affine(matrix)
        point = [0.25, -0.5, 0.75]
        for got, want in zip(_transform(inverse, _transform(matrix, point)), point):
            self.assertAlmostEqual(got, want)

    def test_invert_affine_rejects_degenerate_scale(self):
        self.assertIsNone(invert_affine(model_matrix([0, 0, 0], [0, 0, 0], [1.0, 0.0, 1.0])))


class ClipTests(unittest.TestCase):
    def test_polygon_covering_the_face_clips_to_the_face(self):
        big = [(-3.0, -3.0), (3.0, -3.0), (3.0, 3.0), (-3.0, 3.0)]
        self.assertAlmostEqual(_area(clip_polygon_to_square(big)), 1.0)

    def test_polygon_outside_the_face_is_dropped(self):
        outside = [(2.0, 2.0), (3.0, 2.0), (3.0, 3.0)]
        self.assertEqual(clip_polygon_to_square(outside), [])

    def test_polygon_inside_the_face_is_unchanged(self):
        inside = [(-0.2, -0.2), (0.2, -0.2), (0.0, 0.3)]
        self.assertEqual(clip_polygon_to_square(inside), inside)


class SphereShadowTests(unittest.TestCase):
    CUBE = model_matrix([0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [1.0, 1.0, 1.0])

    @staticmethod
    def _sphere(x, diameter=0.4):
        return model_matrix([x, 0.0, 0.0], [0.0, 0.0, 0.0], [diameter] * 3)

    def test_directional_light_casts_sphere_sized_disc_on_the_facing_side(self):
        polygons = sphere_shadow_on_cube([1.0, 0.0, 0.0, 0.0], self._sphere(2.0), self.CUBE, segments=256)
        self.assertEqual(len(polygons), 1)
        normal, points = polygons[0]
        self.assertEqual(normal, [1.0, 0.0, 0.0])
        for x, y, z in points:
            self.assertAlmostEqual(x, 0.5)
            self.assertAlmostEqual(math.hypot(y, z), 0.2, places=6)

    def test_shadow_is_clipped_to_the_face(self):
        sphere = model_matrix([2.0, 0.5, 0.0], [0.0, 0.0, 0.0], [0.4] * 3)
        (_normal, points), = sphere_shadow_on_cube([1.0, 0.0, 0.0, 0.0], sphere, self.CUBE, segments=256)
        self.assertTrue(all(y <= 0.5 + 1e-9 for _x, y, _z in points))
        self.assertAlmostEqual(_area([(y, z) for _x, y, z in points]), math.pi * 0.2 ** 2 / 2, places=3)

    def test_sphere_behind_the_cube_casts_nothing(self):
        self.assertEqual(sphere_shadow_on_cube([1.0, 0.0, 0.0, 0.0], self._sphere(-2.0), self.CUBE), [])

    def test_slanted_light_only_shadows_faces_it_reaches(self):
        light = [1.0, 1.0, 0.0, 0.0]
        normals = [normal for normal, _points in sphere_shadow_on_cube(light, self._sphere(1.0), self.CUBE)]
        self.assertEqual(normals, [[1.0, 0.0, 0.0]])

    def test_positional_light_spreads_the_shadow(self):
        (_normal, points), = sphere_shadow_on_cube([4.0, 0.0, 0.0, 1.0], self._sphere(2.0), self.CUBE, segments=256)
        radius = max(math.hypot(y, z) for _x, y, z in points)
        self.assertGreater(radius, 0.2)
        self.assertLess(radius, 0.5)

    def test_shadow_follows_a_scaled_and_rotated_cube(self):
        cube = model_matrix([0.0, 0.0, 0.0], [0.0, 0.0, 90.0], [2.0, 2.0, 2.0])
        polygons = sphere_shadow_on_cube([1.0, 0.0, 0.0, 0.0], self._sphere(3.0), cube, segments=256)
        (normal, points), = polygons
        # world +X is the rotated cube's local -Y face
        self.assertEqual(normal, [0.0, -1.0, 0.0])
        self.assertAlmostEqual(max(math.hypot(x, z) for x, _y, z in points), 0.1, places=6)

    def test_terminator_lies_on_the_sphere(self):
        sphere = model_matrix([1.0, 2.0, 3.0], [0.0, 0.0, 0.0], [2.0] * 3)
        for point in sphere_terminator([0.0, 5.0, 0.0, 1.0], sphere):
            self.assertAlmostEqual(math.dist(point, [1.0, 2.0, 3.0]), 1.0)


if __name__ == "__main__":
    unittest.main()
