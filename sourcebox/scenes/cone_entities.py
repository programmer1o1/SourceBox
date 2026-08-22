"""Entities used by the Voidside cone scene."""

import random

from OpenGL.GL import *
from OpenGL.GLU import *


class GreyCone:
    """A grey XYZ pointer with independent movement and rotation behavior."""

    def __init__(self, position):
        self.position = list(position)
        self.velocity = [0, 0, 0]
        self.state = random.choices(
            ["still", "moving", "falling"], weights=[1, 4, 3], k=1
        )[0]

        if self.state == "moving":
            self.velocity = [
                random.uniform(-10, 10),
                random.uniform(-10, 10),
                random.uniform(-10, 10),
            ]
        elif self.state == "falling":
            self.velocity = [0, -random.uniform(5, 15), 0]

        self.size = random.uniform(0.3, 3.0)
        self.rotation = [
            random.uniform(0, 360),
            random.uniform(0, 360),
            random.uniform(0, 360),
        ]
        self.rotates = random.random() < 0.5
        self.rotation_speed = [
            random.uniform(-3.0, 3.0),
            random.uniform(-3.0, 3.0),
            random.uniform(-3.0, 3.0),
        ]

    def update(self, dt):
        if self.rotates:
            for axis in range(3):
                self.rotation[axis] = (
                    self.rotation[axis] + self.rotation_speed[axis] * dt
                ) % 360.0

        if self.state != "still":
            self.position[0] += self.velocity[0] * dt
            self.position[1] += self.velocity[1] * dt
            self.position[2] += self.velocity[2] * dt

            if self.state == "falling":
                self.velocity[1] -= 80.0 * dt

    def draw(self):
        glPushMatrix()
        glTranslatef(*self.position)
        glRotatef(self.rotation[0], 1, 0, 0)
        glRotatef(self.rotation[1], 0, 1, 0)
        glRotatef(self.rotation[2], 0, 0, 1)

        axis_length = self.size * 2.5
        glLineWidth(2.0)

        glBegin(GL_LINES)
        glColor3f(1.0, 0.35, 0.35)
        glVertex3f(0.0, 0.0, 0.0)
        glVertex3f(axis_length, 0.0, 0.0)

        glColor3f(0.35, 1.0, 0.35)
        glVertex3f(0.0, 0.0, 0.0)
        glVertex3f(0.0, axis_length, 0.0)

        glColor3f(0.35, 0.35, 1.0)
        glVertex3f(0.0, 0.0, 0.0)
        glVertex3f(0.0, 0.0, axis_length)
        glEnd()

        glColor3f(0.5, 0.5, 0.5)
        glPushMatrix()
        glRotatef(-90, 1, 0, 0)
        quadric = gluNewQuadric()
        if quadric:
            gluCylinder(quadric, self.size * 0.1, 0.0, self.size * 0.3, 16, 4)
            gluDeleteQuadric(quadric)
        glPopMatrix()

        glPopMatrix()
