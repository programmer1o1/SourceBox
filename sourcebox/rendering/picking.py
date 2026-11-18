"""Exact mouse picking for the main-menu shapes.

Pure Python (no OpenGL) so it can be unit-tested headlessly. Each shape is
tested in its own local space, using the same model matrix draw_object()
applies, so a click only counts where the shape is actually drawn.
"""

import math

from sourcebox.rendering.shadows import invert_affine

_EPSILON = 1e-9


def _to_local(inverse, origin, direction):
    o = [sum(inverse[r][c] * origin[c] for c in range(3)) + inverse[r][3] for r in range(3)]
    d = [sum(inverse[r][c] * direction[c] for c in range(3)) for r in range(3)]
    return o, d


def _smallest_positive(*values):
    hits = [v for v in values if v is not None and v >= 0.0]
    return min(hits) if hits else None


def _hit_sphere(o, d):
    # unit-diameter sphere at the origin (gluSphere radius 0.5)
    a = d[0] * d[0] + d[1] * d[1] + d[2] * d[2]
    b = 2.0 * (o[0] * d[0] + o[1] * d[1] + o[2] * d[2])
    c = o[0] * o[0] + o[1] * o[1] + o[2] * o[2] - 0.25
    disc = b * b - 4.0 * a * c
    if a < _EPSILON or disc < 0.0:
        return None
    root = math.sqrt(disc)
    return _smallest_positive((-b - root) / (2.0 * a), (-b + root) / (2.0 * a))


def _hit_cube(o, d):
    # slab test against [-0.5, 0.5]^3
    t_near, t_far = -math.inf, math.inf
    for axis in range(3):
        if abs(d[axis]) < _EPSILON:
            if abs(o[axis]) > 0.5:
                return None
            continue
        t0 = (-0.5 - o[axis]) / d[axis]
        t1 = (0.5 - o[axis]) / d[axis]
        if t0 > t1:
            t0, t1 = t1, t0
        t_near, t_far = max(t_near, t0), min(t_far, t1)
        if t_near > t_far:
            return None
    if t_far < 0.0:
        return None
    return t_near if t_near >= 0.0 else t_far


def _hit_cone(o, d):
    # gluCylinder(0.5, 0, 1): base radius 0.5 at z = 0, apex at z = 1, plus base disc
    hits = []
    k = 0.25  # (radius / height) ** 2
    a = d[0] * d[0] + d[1] * d[1] - k * d[2] * d[2]
    b = 2.0 * (o[0] * d[0] + o[1] * d[1] + k * (1.0 - o[2]) * d[2])
    c = o[0] * o[0] + o[1] * o[1] - k * (1.0 - o[2]) ** 2
    if abs(a) > _EPSILON:
        disc = b * b - 4.0 * a * c
        if disc >= 0.0:
            root = math.sqrt(disc)
            hits += [(-b - root) / (2.0 * a), (-b + root) / (2.0 * a)]
    elif abs(b) > _EPSILON:
        hits.append(-c / b)
    hits = [t for t in hits if 0.0 <= o[2] + t * d[2] <= 1.0]
    if abs(d[2]) > _EPSILON:
        t = -o[2] / d[2]
        x, y = o[0] + t * d[0], o[1] + t * d[1]
        if x * x + y * y <= 0.25:
            hits.append(t)
    return _smallest_positive(*hits)


_SHAPES = {"sphere": _hit_sphere, "cube": _hit_cube, "cone": _hit_cone}


def ray_hit_distance(shape, model_matrix, origin, direction):
    """Ray parameter t of the first hit on the shape, or None if it misses.

    The point hit is origin + t * direction, whatever the direction's length.
    """
    test = _SHAPES.get(shape)
    inverse = invert_affine(model_matrix)
    if test is None or inverse is None:
        return None
    return test(*_to_local(inverse, origin, direction))


def pick(candidates, origin, direction):
    """Pick what the ray hits first.

    candidates: (item, shape, model_matrix, without_depth) tuples. without_depth
    marks shapes drawn without writing depth (the spinning cube): every other
    shape shows in front of them, so they are only picked when nothing else is hit.
    """
    best, best_t = None, math.inf
    behind, behind_t = None, math.inf
    for item, shape, matrix, without_depth in candidates:
        t = ray_hit_distance(shape, matrix, origin, direction)
        if t is None:
            continue
        if without_depth:
            if t < behind_t:
                behind, behind_t = item, t
        elif t < best_t:
            best, best_t = item, t
    return best if best is not None else behind
