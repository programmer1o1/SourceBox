"""Projected shadow of the main-menu sphere onto the cube's faces.

Pure-Python geometry (no OpenGL, no numpy) so it can be unit-tested headlessly.
Fixed-function OpenGL has no shadows, so the shadow the sphere casts on the cube
is computed analytically: the sphere's terminator (the outline the light sees)
is projected along the light rays onto each lit cube face and clipped to it.
"""

import math


def _mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def _rotation(angle_deg, axis):
    c = math.cos(math.radians(angle_deg))
    s = math.sin(math.radians(angle_deg))
    m = [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]
    if axis == 0:
        m[1][1], m[1][2], m[2][1], m[2][2] = c, -s, s, c
    elif axis == 1:
        m[0][0], m[0][2], m[2][0], m[2][2] = c, s, -s, c
    else:
        m[0][0], m[0][1], m[1][0], m[1][1] = c, -s, s, c
    return m


def model_matrix(position, rotation, scale_xyz, spin=0.0):
    """Match draw_object(): translate, rotate X/Y/Z, optional Z spin, then scale."""
    m = [[1.0, 0.0, 0.0, position[0]],
         [0.0, 1.0, 0.0, position[1]],
         [0.0, 0.0, 1.0, position[2]],
         [0.0, 0.0, 0.0, 1.0]]
    for axis in range(3):
        if rotation[axis]:
            m = _mat_mul(m, _rotation(rotation[axis], axis))
    if spin:
        m = _mat_mul(m, _rotation(spin, 2))
    scale = [[scale_xyz[0], 0.0, 0.0, 0.0],
             [0.0, scale_xyz[1], 0.0, 0.0],
             [0.0, 0.0, scale_xyz[2], 0.0],
             [0.0, 0.0, 0.0, 1.0]]
    return _mat_mul(m, scale)


def invert_affine(m):
    """Invert a 4x4 affine matrix (rotation/scale block plus translation)."""
    a, b, c = m[0][0], m[0][1], m[0][2]
    d, e, f = m[1][0], m[1][1], m[1][2]
    g, h, i = m[2][0], m[2][1], m[2][2]
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if abs(det) < 1e-12:
        return None
    inv = [[(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det],
           [(f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det],
           [(d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det]]
    t = [m[0][3], m[1][3], m[2][3]]
    out = [row + [-sum(row[k] * t[k] for k in range(3))] for row in inv]
    out.append([0.0, 0.0, 0.0, 1.0])
    return out


def _apply(m, v, w):
    return [m[r][0] * v[0] + m[r][1] * v[1] + m[r][2] * v[2] + m[r][3] * w for r in range(3)]


def _normalize(v):
    length = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if length < 1e-12:
        return None
    return [v[0] / length, v[1] / length, v[2] / length]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def clip_polygon_to_square(points, half=0.5):
    """Sutherland-Hodgman clip of a 2D polygon against [-half, half]^2."""
    for axis in (0, 1):
        for sign in (1.0, -1.0):
            if not points:
                return []
            clipped = []
            previous = points[-1]
            previous_inside = sign * previous[axis] <= half
            for current in points:
                current_inside = sign * current[axis] <= half
                if current_inside != previous_inside:
                    t = (sign * half - previous[axis]) / (current[axis] - previous[axis])
                    clipped.append((previous[0] + t * (current[0] - previous[0]),
                                    previous[1] + t * (current[1] - previous[1])))
                if current_inside:
                    clipped.append(current)
                previous, previous_inside = current, current_inside
            points = clipped
    return points


def sphere_terminator(light, sphere_matrix, radius=0.5, segments=48):
    """World-space outline of the sphere as seen from the light.

    light is an OpenGL light position: w == 0 is directional, otherwise positional.
    """
    inverse = invert_affine(sphere_matrix)
    if inverse is None:
        return []
    directional = len(light) < 4 or light[3] == 0
    local = _apply(inverse, light, 0.0 if directional else 1.0)
    axis = _normalize(local)
    if axis is None:
        return []
    offset, ring = 0.0, radius
    if not directional:
        distance = math.sqrt(sum(c * c for c in local))
        if distance <= radius:
            return []
        offset = radius * radius / distance
        ring = radius * math.sqrt(1.0 - (radius / distance) ** 2)
    helper = [1.0, 0.0, 0.0] if abs(axis[0]) < 0.9 else [0.0, 1.0, 0.0]
    u = _normalize(_cross(axis, helper))
    v = _cross(axis, u)
    points = []
    for step in range(segments):
        angle = 2.0 * math.pi * step / segments
        ca, sa = math.cos(angle) * ring, math.sin(angle) * ring
        local_point = [axis[k] * offset + u[k] * ca + v[k] * sa for k in range(3)]
        points.append(_apply(sphere_matrix, local_point, 1.0))
    return points


def sphere_shadow_on_cube(light, sphere_matrix, cube_matrix, segments=48):
    """Shadow polygons of the sphere on the lit faces of a unit cube.

    Returns a list of (normal, points) in the cube's local space, where the cube
    spans [-0.5, 0.5] on every axis. Each polygon is convex and lies on its face.
    """
    cube_inverse = invert_affine(cube_matrix)
    if cube_inverse is None:
        return []
    outline = [_apply(cube_inverse, p, 1.0)
               for p in sphere_terminator(light, sphere_matrix, segments=segments)]
    if not outline:
        return []
    directional = len(light) < 4 or light[3] == 0
    light_local = _apply(cube_inverse, light, 0.0 if directional else 1.0)

    polygons = []
    for axis in range(3):
        others = [k for k in range(3) if k != axis]
        for sign in (1.0, -1.0):
            plane = 0.5 * sign
            projected = []
            occluded = False
            for point in outline:
                if directional:
                    ray = light_local
                else:
                    ray = [light_local[k] - point[k] for k in range(3)]
                if sign * ray[axis] <= 1e-9:
                    # the light is behind this face, so it is unlit anyway
                    projected = []
                    break
                t = (point[axis] - plane) / ray[axis]
                if t > 0:
                    occluded = True
                projected.append((point[others[0]] - ray[others[0]] * t,
                                  point[others[1]] - ray[others[1]] * t))
            if not projected or not occluded:
                continue
            clipped = clip_polygon_to_square(projected)
            if len(clipped) < 3:
                continue
            normal = [0.0, 0.0, 0.0]
            normal[axis] = sign
            points = []
            for a, b in clipped:
                vertex = [0.0, 0.0, 0.0]
                vertex[axis] = plane
                vertex[others[0]] = a
                vertex[others[1]] = b
                points.append(vertex)
            polygons.append((normal, points))
    return polygons
