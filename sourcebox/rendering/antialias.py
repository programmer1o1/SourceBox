"""Multisample anti-aliasing that works even when the window has no MSAA.

Some drivers (virtual machines in particular) accept a multisampled window
request but silently hand back a plain one. In that case every frame is drawn
into an offscreen multisampled framebuffer and resolved to the window just
before it is shown. When the window already has MSAA, or framebuffer objects
are unavailable, frames are drawn to the window directly.
"""

import pygame
from OpenGL.GL import *


class MultisampleTarget:
    def __init__(self, samples=4):
        self.requested_samples = samples
        self.samples = 0
        self.size = None
        self.framebuffer = None
        self.color_buffer = None
        self.depth_buffer = None

    @property
    def active(self):
        return self.framebuffer is not None

    def setup(self, size):
        """(Re)create the offscreen buffer for a window of this size and bind it."""
        size = (int(size[0]), int(size[1]))
        if self.active and size == self.size:
            glBindFramebuffer(GL_FRAMEBUFFER, self.framebuffer)
            return
        self.cleanup()
        self.size = size

        try:
            glBindFramebuffer(GL_FRAMEBUFFER, 0)
            if glGetIntegerv(GL_SAMPLE_BUFFERS):
                self.samples = int(glGetIntegerv(GL_SAMPLES))
                return  # the window itself is multisampled

            samples = min(self.requested_samples, int(glGetIntegerv(GL_MAX_SAMPLES)))
            if samples < 2:
                return

            self.framebuffer = glGenFramebuffers(1)
            self.color_buffer, self.depth_buffer = glGenRenderbuffers(2)
            glBindRenderbuffer(GL_RENDERBUFFER, self.color_buffer)
            glRenderbufferStorageMultisample(GL_RENDERBUFFER, samples, GL_RGBA8, *size)
            glBindRenderbuffer(GL_RENDERBUFFER, self.depth_buffer)
            glRenderbufferStorageMultisample(GL_RENDERBUFFER, samples, GL_DEPTH_COMPONENT24, *size)
            glBindRenderbuffer(GL_RENDERBUFFER, 0)

            glBindFramebuffer(GL_FRAMEBUFFER, self.framebuffer)
            glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_RENDERBUFFER, self.color_buffer)
            glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, self.depth_buffer)
            if glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE:
                raise RuntimeError("multisampled framebuffer incomplete")
            self.samples = samples
        except Exception as error:
            print(f"Offscreen anti-aliasing unavailable ({error}), continuing without it")
            self.cleanup()

    def present(self):
        """Show the finished frame, resolving the offscreen buffer first."""
        if self.active:
            width, height = self.size
            glBindFramebuffer(GL_READ_FRAMEBUFFER, self.framebuffer)
            glBindFramebuffer(GL_DRAW_FRAMEBUFFER, 0)
            glBlitFramebuffer(0, 0, width, height, 0, 0, width, height, GL_COLOR_BUFFER_BIT, GL_NEAREST)
            glBindFramebuffer(GL_FRAMEBUFFER, 0)
            pygame.display.flip()
            glBindFramebuffer(GL_FRAMEBUFFER, self.framebuffer)
        else:
            pygame.display.flip()

    def cleanup(self):
        try:
            glBindFramebuffer(GL_FRAMEBUFFER, 0)
            if self.framebuffer is not None:
                glDeleteFramebuffers(1, [self.framebuffer])
            buffers = [b for b in (self.color_buffer, self.depth_buffer) if b]
            if buffers:
                glDeleteRenderbuffers(len(buffers), buffers)
        except Exception:
            pass
        self.framebuffer = self.color_buffer = self.depth_buffer = None
        self.samples = 0
