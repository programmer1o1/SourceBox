import pygame
import math
import os
import sys
import time
import random
from pathlib import Path
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *

import platform  

from cone_scene import ConeScene

# platform detection
PLATFORM = platform.system()

# hide console window on windows
if PLATFORM == 'Windows':
    try:
        import ctypes
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except:
        pass

# conditional glut import
try:
    from OpenGL.GLUT import *
    GLUT_AVAILABLE = True
except ImportError:
    GLUT_AVAILABLE = False
    print("Warning: GLUT not available, some features may be limited")

# import source_bridge conditionally
try:
    from source_bridge import SourceBridge
    BRIDGE_AVAILABLE = True
except ImportError:
    BRIDGE_AVAILABLE = False
    print("Warning: source_bridge not available")

def get_resource_path(filename):
    """get absolute path to resource file, works for dev and pyinstaller"""
    if hasattr(sys, '_MEIPASS'):
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path(__file__).parent if '__file__' in globals() else Path.cwd()
    
    return str(base_path / filename)

def find_resource(filenames):
    """find first existing resource from list of filenames"""
    if isinstance(filenames, str):
        filenames = [filenames]
    
    for filename in filenames:
        path = get_resource_path(filename)
        if os.path.exists(path):
            return path
    return None

class Object3D:
    def __init__(self, obj_type, position=(0, 0, 0), rotation=(0, 0, 0), scale=1.0, scale_xyz=[1.0, 1.0, 1.0], brightness=0.6):
        self.type = obj_type
        self.position = list(position)
        self.rotation = list(rotation)
        self.base_rotation = list(rotation)
        self.base_scale = max(0.01, abs(scale))
        self.scale = self.base_scale
        self.target_scale = self.base_scale
        self.scale_xyz = [max(0.01, abs(s)) for s in scale_xyz]
        self.brightness = max(0.0, min(1.0, brightness))
        self.base_brightness = self.brightness
        self.is_hovered = False
        self.is_rotating = False
        self.rotation_angle = 0.0
        self.hover_timer = 0.0
        self.hover_animation_duration = 0.1
        self.hover_scale_amount = 0.05
        self.was_hovered = False
        self.display_list = None
        
        # precalculate bounding sphere radius
        if self.type == "sphere":
            self.bounding_radius = 0.5 * self.scale * max(self.scale_xyz)
        elif self.type == "cube":
            self.bounding_radius = 0.866 * self.scale * max(self.scale_xyz)
        elif self.type == "cone":
            self.bounding_radius = 0.6 * self.scale * max(self.scale_xyz)
        else:
            self.bounding_radius = 0.5 * self.scale * max(self.scale_xyz)
        
    def create_display_list(self):
        if self.display_list is not None:
            return
            
        try:
            self.display_list = glGenLists(1)
            if self.display_list == 0:
                return
                
            glNewList(self.display_list, GL_COMPILE)
            
            if self.type == "cube":
                self._draw_cube_geometry()
            elif self.type == "sphere":
                quadric = gluNewQuadric()
                if quadric:
                    gluQuadricNormals(quadric, GLU_SMOOTH)
                    gluSphere(quadric, 0.5, 32, 32)
                    gluDeleteQuadric(quadric)
            elif self.type == "cone":
                quadric = gluNewQuadric()
                if quadric:
                    gluQuadricNormals(quadric, GLU_SMOOTH)
                    gluCylinder(quadric, 0.5, 0.0, 1.0, 32, 4)
                    gluDeleteQuadric(quadric)
                    
                    glBegin(GL_TRIANGLE_FAN)
                    glNormal3f(0, 0, -1)
                    glVertex3f(0, 0, 0)
                    for i in range(33):
                        angle = (i / 32.0) * 2.0 * math.pi
                        x = 0.5 * math.cos(angle)
                        y = 0.5 * math.sin(angle)
                        glVertex3f(x, y, 0)
                    glEnd()
            
            glEndList()
        except Exception as e:
            print(f"Error creating display list for {self.type}: {e}")
            if self.display_list:
                try:
                    glDeleteLists(self.display_list, 1)
                except:
                    pass
                self.display_list = None
    
    def _draw_cube_geometry(self):
        glBegin(GL_QUADS)
        # top
        glNormal3f(0, 1, 0)
        glVertex3f(0.5, 0.5, -0.5)
        glVertex3f(-0.5, 0.5, -0.5)
        glVertex3f(-0.5, 0.5, 0.5)
        glVertex3f(0.5, 0.5, 0.5)
        # bottom
        glNormal3f(0, -1, 0)
        glVertex3f(0.5, -0.5, -0.5)
        glVertex3f(-0.5, -0.5, -0.5)
        glVertex3f(-0.5, -0.5, 0.5)
        glVertex3f(0.5, -0.5, 0.5)
        # right
        glNormal3f(1, 0, 0)
        glVertex3f(0.5, 0.5, -0.5)
        glVertex3f(0.5, 0.5, 0.5)
        glVertex3f(0.5, -0.5, 0.5)
        glVertex3f(0.5, -0.5, -0.5)
        # left
        glNormal3f(-1, 0, 0)
        glVertex3f(-0.5, 0.5, -0.5)
        glVertex3f(-0.5, 0.5, 0.5)
        glVertex3f(-0.5, -0.5, 0.5)
        glVertex3f(-0.5, -0.5, -0.5)
        # front
        glNormal3f(0, 0, -1)
        glVertex3f(0.5, 0.5, -0.5)
        glVertex3f(-0.5, 0.5, -0.5)
        glVertex3f(-0.5, -0.5, -0.5)
        glVertex3f(0.5, -0.5, -0.5)
        # back
        glNormal3f(0, 0, 1)
        glVertex3f(-0.5, 0.5, 0.5)
        glVertex3f(0.5, 0.5, 0.5)
        glVertex3f(0.5, -0.5, 0.5)
        glVertex3f(-0.5, -0.5, 0.5)
        glEnd()
    
    def cleanup(self):
        if self.display_list:
            try:
                glDeleteLists(self.display_list, 1)
            except:
                pass
            self.display_list = None

class Camera:
    def __init__(self):
        self.position = [0.0, -1.0, -10.0]
        self.rotation = [92.97, -9.00, -10.38]
        self.fov = max(1.0, min(179.0, 53.25))
        self.matrices_dirty = True
    
    def apply(self):
        glLoadIdentity()
        glTranslatef(*self.position)
        glRotatef(self.rotation[0], 1, 0, 0)
        glRotatef(self.rotation[1], 0, 1, 0)
        glRotatef(self.rotation[2], 0, 0, 1)

class Light:
    def __init__(self):
        self.position = [107.10, 2.85, -185.15, 1.0]
        self.ambient = [0.1, 0.1, 0.1, 1.0]
        self.diffuse = [1.0, 1.0, 1.0, 1.0]
        self.specular = [1.0, 1.0, 1.0, 1.0]
        self.setup_done = False
    
    def apply(self):
        if not self.setup_done:
            glLightfv(GL_LIGHT0, GL_AMBIENT, self.ambient)
            glLightfv(GL_LIGHT0, GL_DIFFUSE, self.diffuse)
            glLightfv(GL_LIGHT0, GL_SPECULAR, self.specular)
            self.setup_done = True
        glLightfv(GL_LIGHT0, GL_POSITION, self.position)

class Checkerboard:
    def __init__(self):
        self.size = 30
        self.position = [-25.87, 0.53, 6.68]
        self.rotation = [0, 0, 0]
        self.scale = [1.55, 0.63, 1.22]
        self.dark_color = [0.2, 0.2, 0.2]
        self.light_color = [0.0, 0.0, 0.0]
        self.brightness = 2
        self.display_list = None
    
    def create_display_list(self):
        if self.display_list is not None:
            return
            
        try:
            self.display_list = glGenLists(1)
            if self.display_list == 0:
                return
                
            glNewList(self.display_list, GL_COMPILE)
            
            size = self.size
            dark_r = self.dark_color[0] * self.brightness
            dark_g = self.dark_color[1] * self.brightness
            dark_b = self.dark_color[2] * self.brightness
            light_r = self.light_color[0] * self.brightness
            light_g = self.light_color[1] * self.brightness
            light_b = self.light_color[2] * self.brightness
            
            glNormal3f(0, 1, 0)
            glBegin(GL_QUADS)
            for x in range(-size, size):
                for z in range(-size, size):
                    if (x + z) & 1:
                        glColor3f(light_r, light_g, light_b)
                    else:
                        glColor3f(dark_r, dark_g, dark_b)
                    
                    glVertex3f(x, 0, z)
                    glVertex3f(x, 0, z+1)
                    glVertex3f(x+1, 0, z+1)
                    glVertex3f(x+1, 0, z)
            glEnd()
            
            glEndList()
        except Exception as e:
            print(f"Error creating checkerboard display list: {e}")
            if self.display_list:
                try:
                    glDeleteLists(self.display_list, 1)
                except:
                    pass
                self.display_list = None
    
    def draw(self):
        if self.display_list is None:
            return
            
        glPushMatrix()
        glTranslatef(*self.position)
        if self.rotation[0] or self.rotation[1] or self.rotation[2]:
            glRotatef(self.rotation[0], 1, 0, 0)
            glRotatef(self.rotation[1], 0, 1, 0)
            glRotatef(self.rotation[2], 0, 0, 1)
        glScalef(self.scale[0], self.scale[1], self.scale[2])
        glCallList(self.display_list)
        glPopMatrix()
    
    def cleanup(self):
        if self.display_list:
            try:
                glDeleteLists(self.display_list, 1)
            except:
                pass
            self.display_list = None

class MissingTextureScene:
    def __init__(self, sound_manager=None, display_scale=1.0):
        self.display_list = None
        self.text = "WARNING: NO GRAPHICS DRIVER DETECTED. PLEASE ENABLE A VALID GRAPHICS DRIVER."
        self.text_visible = True
        self.flash_timer = 0.0
        self.next_flash_interval = random.choice([0.1, 0.3, 0.5])
        self.text_texture = None
        self.text_width = 0
        self.text_height = 0
        self.sound_manager = sound_manager
        self.display_scale = display_scale
        self.create_text_texture()
        
    def create_text_texture(self):
        try:
            font_name = None
            font_size = 36
            
            if PLATFORM == 'Windows':
                font_candidates = ['Trebuchet MS', 'Arial', 'Verdana']
            else:
                font_candidates = ['DejaVu Sans', 'Liberation Sans', 'FreeSans', 'Arial']
            
            for font_candidate in font_candidates:
                try:
                    font = pygame.font.SysFont(font_candidate, font_size)
                    break
                except:
                    continue
            else:
                font = pygame.font.Font(None, font_size)
            
            char_spacing = 2
            
            total_width = 0
            char_surfaces = []
            for char in self.text:
                char_surf = font.render(char, True, (255, 0, 0))
                char_surfaces.append(char_surf)
                total_width += char_surf.get_width() + char_spacing
            
            total_width -= char_spacing
            
            max_height = max(surf.get_height() for surf in char_surfaces)
            
            text_surface = pygame.Surface((total_width, max_height), pygame.SRCALPHA)
            text_surface.fill((0, 0, 0, 0))
            
            x_offset = 0
            for char_surf in char_surfaces:
                text_surface.blit(char_surf, (x_offset, 0))
                x_offset += char_surf.get_width() + char_spacing
            
            text_data = pygame.image.tostring(text_surface, "RGBA", True)
            
            self.text_width = text_surface.get_width()
            self.text_height = text_surface.get_height()
            
            self.text_texture = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, self.text_texture)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, self.text_width, self.text_height, 0, GL_RGBA, GL_UNSIGNED_BYTE, text_data)
        except Exception as e:
            print(f"Error creating text texture: {e}")
            self.text_texture = None
        
    def create_display_list(self):
        if self.display_list is not None:
            return
            
        try:
            self.display_list = glGenLists(1)
            if self.display_list == 0:
                return
                
            glNewList(self.display_list, GL_COMPILE)
            
            size = 50
            block_width = 0.7
            block_height = 0.5
            
            glBegin(GL_QUADS)
            for x in range(-size, size):
                for z in range(-size, size):
                    if (x + z) & 1:
                        glColor3f(1.0, 0.0, 1.0)
                    else:
                        glColor3f(0.0, 0.0, 0.0)
                    
                    center_x = 0
                    center_z = 0
                    
                    corners = [
                        (x, z),
                        (x, z+1),
                        (x+1, z+1),
                        (x+1, z)
                    ]
                    
                    vertices = []
                    for cx, cz in corners:
                        dx = cx - center_x
                        dz = cz - center_z
                        dist = math.sqrt(dx*dx + dz*dz)
                        
                        push_amount = dist * 0.03
                        
                        if dist > 0:
                            push_x = (dx / dist) * push_amount
                            push_z = (dz / dist) * push_amount
                        else:
                            push_x = 0
                            push_z = 0
                        
                        x_pos = cx * block_width + push_x
                        z_pos = cz * block_height + push_z
                        
                        vertices.append((x_pos, z_pos))
                    
                    glVertex3f(vertices[0][0], vertices[0][1], 0)
                    glVertex3f(vertices[1][0], vertices[1][1], 0)
                    glVertex3f(vertices[2][0], vertices[2][1], 0)
                    glVertex3f(vertices[3][0], vertices[3][1], 0)
            glEnd()
            
            glEndList()
        except Exception as e:
            print(f"Error creating missing texture display list: {e}")
            if self.display_list:
                try:
                    glDeleteLists(self.display_list, 1)
                except:
                    pass
                self.display_list = None     
                
    def update(self, dt):
        self.flash_timer += dt
        if self.flash_timer >= self.next_flash_interval:
            self.text_visible = not self.text_visible
            self.flash_timer = 0.0
            self.next_flash_interval = random.choice([0.01, 0.05, 0.09])
    
    def draw(self, display_width, display_height):
        glDisable(GL_LIGHTING)
        glDisable(GL_DEPTH_TEST)
        
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(-display_width/200.0, display_width/200.0, -display_height/200.0, display_height/200.0, -1, 1)
        
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()
        
        if self.display_list:
            glCallList(self.display_list)
        
        if self.text_visible and self.text_texture:
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glEnable(GL_TEXTURE_2D)
            glBindTexture(GL_TEXTURE_2D, self.text_texture)
            glColor4f(1.0, 1.0, 1.0, 1.0)
            
            target_width_percentage = 0.8
            ortho_width = display_width / 100.0
            target_width = ortho_width * target_width_percentage
            
            scale_factor = target_width / self.text_width
            
            w = self.text_width * scale_factor
            h = self.text_height * scale_factor
            
            x = -w / 2.0
            y = -h / 24.0
            
            glBegin(GL_QUADS)
            glTexCoord2f(0, 0); glVertex2f(x, y)
            glTexCoord2f(1, 0); glVertex2f(x + w, y)
            glTexCoord2f(1, 1); glVertex2f(x + w, y + h)
            glTexCoord2f(0, 1); glVertex2f(x, y + h)
            glEnd()
            
            glDisable(GL_TEXTURE_2D)
            glDisable(GL_BLEND)
        
        glPopMatrix()
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
        
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)
    
    def cleanup(self):
        if self.display_list:
            try:
                glDeleteLists(self.display_list, 1)
            except:
                pass
            self.display_list = None
        if self.text_texture:
            try:
                glDeleteTextures([self.text_texture])
            except:
                pass
            self.text_texture = None

class CursorRenderer:
    def __init__(self, cursor_file):
        self.texture_id = None
        self.width = 0
        self.height = 0
        self.enabled = False
        self.scale = 1.0  
        self.load_cursor(cursor_file)
        
    def load_cursor(self, cursor_file):
        try:
            cursor_candidates = [
                'assets/images/cursor.png',
                cursor_file,
                'cursor.png'
            ]
            cursor_path = find_resource(cursor_candidates)

            if cursor_path:
                try:
                    cursor_img = pygame.image.load(cursor_path).convert_alpha()
                    cursor_img = pygame.transform.flip(cursor_img, False, True)
                    self._create_texture(cursor_img)
                    self.enabled = True
                    print(f"Cursor loaded: {cursor_path}")
                    return True
                except Exception as e:
                    print(f"Error loading cursor from {cursor_path}: {e}")
            
            print("No cursor loaded, using system cursor")
            return False
        except Exception as e:
            print(f"Cursor loading error: {e}")
            return False
    
    def _create_texture(self, cursor_img):
        try:
            cursor_data = pygame.image.tostring(cursor_img, "RGBA", True)
            self.width = cursor_img.get_width()
            self.height = cursor_img.get_height()
            
            self.texture_id = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, self.texture_id)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, self.width, self.height, 0, GL_RGBA, GL_UNSIGNED_BYTE, cursor_data)
        except Exception as e:
            print(f"Error creating cursor texture: {e}")
            self.texture_id = None
    
    def set_scale(self, scale):
        """set cursor scale factor"""
        self.scale = max(1.0, min(2.0, scale))
    
    def draw(self, mouse_pos, display_width, display_height):
        if not self.enabled or self.texture_id is None:
            return
        
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_LIGHTING)
        
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, display_width, display_height, 0, -1, 1)
        
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()
        
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, self.texture_id)
        
        glColor4f(1.0, 1.0, 1.0, 1.0)
        x, y = mouse_pos
        w = self.width * self.scale
        h = self.height * self.scale
        
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0); glVertex2f(x, y)
        glTexCoord2f(1, 0); glVertex2f(x + w, y)
        glTexCoord2f(1, 1); glVertex2f(x + w, y + h)
        glTexCoord2f(0, 1); glVertex2f(x, y + h)
        glEnd()
        
        glDisable(GL_TEXTURE_2D)
        glDisable(GL_BLEND)
        
        glPopMatrix()
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
        
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)
    
    def cleanup(self):
        if self.texture_id:
            try:
                glDeleteTextures([self.texture_id])
            except:
                pass
            self.texture_id = None
            
class SoundManager:
    def __init__(self):
        self.sounds = {}
        self.music_loaded = False
        self.initialized = False
        
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            self.initialized = True
        except Exception as e:
            print(f"Failed to initialize audio: {e}")
        
    def load_sound(self, name, filepath):
        if not self.initialized:
            return False
            
        try:
            sound_path = find_resource(filepath)
            if sound_path:
                self.sounds[name] = pygame.mixer.Sound(sound_path)
                return True
            return False
        except Exception as e:
            print(f"Error loading sound {name}: {e}")
            return False

    def get_sound_duration(self, name):
        if self.initialized and name in self.sounds:
            try:
                return self.sounds[name].get_length()
            except:
                return 0.0
        return 0.0
    
    def load_music(self, filepath):
        if not self.initialized:
            return False
            
        try:
            music_path = find_resource(filepath)
            if music_path:
                pygame.mixer.music.load(music_path)
                self.music_loaded = True
                return True
            return False
        except Exception as e:
            print(f"Error loading music: {e}")
            return False
    
    def play_sound(self, name):
        if self.initialized and name in self.sounds:
            try:
                self.sounds[name].play()
            except:
                pass
    
    def play_music(self, loops=-1, volume=0.5):
        if self.initialized and self.music_loaded:
            try:
                pygame.mixer.music.set_volume(max(0.0, min(1.0, volume)))
                pygame.mixer.music.play(loops)
            except:
                pass
    
    def stop_music(self):
        if self.initialized and self.music_loaded:
            try:
                pygame.mixer.music.stop()
            except:
                pass

class RayCaster:
    def __init__(self):
        self.viewport = None
        self.modelview = None
        self.projection = None
        self.last_mouse_pos = None
        self.cached_ray = (None, None)
        
    def update_matrices(self):
        self.viewport = glGetIntegerv(GL_VIEWPORT)
        self.modelview = glGetDoublev(GL_MODELVIEW_MATRIX)
        self.projection = glGetDoublev(GL_PROJECTION_MATRIX)
    
    def get_ray_from_mouse(self, mouse_x, mouse_y):
        if self.last_mouse_pos == (mouse_x, mouse_y) and self.cached_ray[0] is not None:
            return self.cached_ray
        
        self.last_mouse_pos = (mouse_x, mouse_y)
        
        if self.viewport is None:
            self.cached_ray = (None, None)
            return self.cached_ray
        
        try:
            y = self.viewport[3] - mouse_y
            
            near_point = gluUnProject(mouse_x, y, 0.0, self.modelview, self.projection, self.viewport)
            far_point = gluUnProject(mouse_x, y, 1.0, self.modelview, self.projection, self.viewport)
            
            dx = far_point[0] - near_point[0]
            dy = far_point[1] - near_point[1]
            dz = far_point[2] - near_point[2]
            
            length = math.sqrt(dx*dx + dy*dy + dz*dz)
            if length < 0.0001:
                self.cached_ray = (None, None)
                return self.cached_ray
            
            inv_length = 1.0 / length
            ray_dir = [dx * inv_length, dy * inv_length, dz * inv_length]
            
            self.cached_ray = (list(near_point), ray_dir)
            return self.cached_ray
        except:
            self.cached_ray = (None, None)
            return self.cached_ray
    
    @staticmethod
    def ray_sphere_intersection(ray_origin, ray_dir, sphere_pos, sphere_radius):
        if not ray_origin or not ray_dir or sphere_radius <= 0:
            return False
        
        oc_x = ray_origin[0] - sphere_pos[0]
        oc_y = ray_origin[1] - sphere_pos[1]
        oc_z = ray_origin[2] - sphere_pos[2]
        
        a = ray_dir[0]*ray_dir[0] + ray_dir[1]*ray_dir[1] + ray_dir[2]*ray_dir[2]
        if a < 0.0001:
            return False
        
        b = 2.0 * (oc_x * ray_dir[0] + oc_y * ray_dir[1] + oc_z * ray_dir[2])
        c = oc_x*oc_x + oc_y*oc_y + oc_z*oc_z - sphere_radius * sphere_radius
        
        discriminant = b*b - 4*a*c
        return discriminant >= 0

def get_display_scale(display_width, display_height):
    """calculate scale factor based on display resolution, base: 1920x1080"""
    base_width = 1920.0
    base_height = 1080.0
    
    width_scale = display_width / base_width
    height_scale = display_height / base_height
    
    scale = min(width_scale, height_scale)
    
    return scale

def init_pygame():
    try:
        pygame.init()
        
        if GLUT_AVAILABLE:
            try:
                glutInit()
            except:
                print("GLUT initialization failed, continuing without it")
        
        display_info = pygame.display.Info()
        screen_width = display_info.current_w
        screen_height = display_info.current_h
        
        print(f"Detected screen resolution: {screen_width}x{screen_height}")
        
        if screen_width <= 1366 or screen_height <= 768:
            display = (int(screen_width * 0.8), int(screen_height * 0.8))
        elif screen_width <= 1920 or screen_height <= 1080:
            display = (1280, 720)
        else:
            display = (1600, 900)
        
        print(f"Using display resolution: {display[0]}x{display[1]}")
        
        icon_candidates = [
            'assets/images/sourcebox.png',
            'assets/images/icon.png',
            'assets/images/icon.ico',
            'sourcebox.png',
            'icon.png'
        ]
        icon_path = find_resource(icon_candidates)

        if icon_path:
            try:
                icon = pygame.image.load(icon_path)
                pygame.display.set_icon(icon)
                print(f"Icon loaded: {icon_path}")
            except Exception as e:
                print(f"Failed to load icon: {e}")
        
        flags = DOUBLEBUF | OPENGL
        
        screen = pygame.display.set_mode(display, flags)
        pygame.display.set_caption('SourceBox')
        
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glEnable(GL_COLOR_MATERIAL)
        glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
        glShadeModel(GL_SMOOTH)
        glEnable(GL_NORMALIZE)
        
        try:
            pygame.display.gl_set_attribute(pygame.GL_SWAP_CONTROL, 1)
        except:
            pass
        
        glMatrixMode(GL_PROJECTION)
        aspect_ratio = display[0] / display[1]
        gluPerspective(53.25, aspect_ratio, 0.1, 50.0)
        glMatrixMode(GL_MODELVIEW)
        
        glClearColor(0.0, 0.0, 0.0, 1.0)
        
        return display, screen
        
    except Exception as e:
        print(f"Failed to initialize Pygame/OpenGL: {e}")
        sys.exit(1)

def update_object_animation(obj, dt):
    if dt <= 0 or dt > 1.0:
        return
    
    if obj.is_hovered and not obj.was_hovered:
        obj.hover_timer = 0.0
        obj.was_hovered = True
    elif not obj.is_hovered and obj.was_hovered:
        obj.hover_timer = 0.0
        obj.scale = obj.base_scale
        obj.was_hovered = False
        return
    
    if obj.is_hovered:
        obj.hover_timer += dt
        
        if obj.hover_timer <= obj.hover_animation_duration:
            progress = obj.hover_timer / obj.hover_animation_duration
            
            if progress <= 0.5:
                scale_progress = progress * 5.0
                obj.scale = obj.base_scale * (1.0 + obj.hover_scale_amount * scale_progress)
            else:
                scale_progress = (progress - 0.5) * 3.0
                obj.scale = obj.base_scale * (1.0 + obj.hover_scale_amount * (1.0 - scale_progress))
        else:
            obj.scale = obj.base_scale

def draw_object(obj):
    if obj.display_list is None:
        return
    
    glPushMatrix()
    glTranslatef(*obj.position)
    
    if obj.base_rotation[0]:
        glRotatef(obj.base_rotation[0], 1, 0, 0)
    if obj.base_rotation[1]:
        glRotatef(obj.base_rotation[1], 0, 1, 0)
    if obj.base_rotation[2]:
        glRotatef(obj.base_rotation[2], 0, 0, 1)
    
    lighting_disabled = False
    if obj.is_rotating or obj.is_hovered:
        glDisable(GL_LIGHTING)
        lighting_disabled = True
        if obj.is_rotating:
            glRotatef(obj.rotation_angle, 0, 0, 1)
    
    sx = obj.scale * obj.scale_xyz[0]
    sy = obj.scale * obj.scale_xyz[1]
    sz = obj.scale * obj.scale_xyz[2]
    glScalef(sx, sy, sz)
    
    if obj.is_rotating:
        glColor3f(0.0, 0.9, 1.0)
    elif obj.is_hovered:
        glColor3f(0.8, 0.0, 0.0)
    else:
        brightness_map = {"cube": 0.6, "sphere": 0.7, "cone": 0.65}
        b = brightness_map.get(obj.type, 0.6) * obj.brightness
        glColor3f(b, b, b)
    
    glCallList(obj.display_list)
    
    if lighting_disabled:
        glEnable(GL_LIGHTING)
    
    glPopMatrix()

def update_object_rotation(obj, dt):
    if dt > 0 and dt <= 1.0 and obj.is_rotating:
        obj.rotation_angle = (obj.rotation_angle + 45.0 * dt) % 360.0

def check_object_hover(mouse_pos, ray_caster, objects, sound_manager):
    if not objects:
        return None
    
    mouse_x, mouse_y = mouse_pos
    ray_origin, ray_dir = ray_caster.get_ray_from_mouse(mouse_x, mouse_y)
    
    if ray_origin is None or ray_dir is None:
        return None
    
    hovered_obj = None
    min_distance = float('inf')
    
    for obj in objects:
        if obj.is_rotating:
            continue
        
        if ray_caster.ray_sphere_intersection(ray_origin, ray_dir, obj.position, obj.bounding_radius):
            dx = obj.position[0] - ray_origin[0]
            dy = obj.position[1] - ray_origin[1]
            dz = obj.position[2] - ray_origin[2]
            distance = dx*dx + dy*dy + dz*dz
            
            if distance < min_distance:
                min_distance = distance
                hovered_obj = obj
    
    for obj in objects:
        new_hover_state = (obj == hovered_obj)
        if new_hover_state and not obj.is_hovered:
            sound_manager.play_sound('hover')
        obj.is_hovered = new_hover_state
    
    return hovered_obj

def check_object_click(mouse_pos, ray_caster, objects):
    if not objects:
        return None
    
    mouse_x, mouse_y = mouse_pos
    ray_origin, ray_dir = ray_caster.get_ray_from_mouse(mouse_x, mouse_y)
    
    if ray_origin is None or ray_dir is None:
        return None
    
    clicked_obj = None
    min_distance = float('inf')
    
    for obj in objects:
        if ray_caster.ray_sphere_intersection(ray_origin, ray_dir, obj.position, obj.bounding_radius):
            dx = obj.position[0] - ray_origin[0]
            dy = obj.position[1] - ray_origin[1]
            dz = obj.position[2] - ray_origin[2]
            distance = dx*dx + dy*dy + dz*dz
            
            if distance < min_distance:
                min_distance = distance
                clicked_obj = obj
    
    return clicked_obj

def main():
    print(f"Running on: {PLATFORM}")
    
    display, screen = init_pygame()
    
    original_display = display
    
    display_scale = get_display_scale(display[0], display[1])
    print(f"Display scale factor: {display_scale:.2f}")
    
    sound_manager = SoundManager()
    sound_manager.load_sound('hover', 'assets/sounds/click.wav')
    sound_manager.load_sound('cube_click', 'assets/sounds/friend_join.wav')
    sound_manager.load_sound('cone_click', 'assets/sounds/cone.wav')  
    sound_manager.load_music('assets/sounds/sourcebox.mp3')
    sound_manager.play_music(loops=-1, volume=0.3)
    
    bridge = None
    if BRIDGE_AVAILABLE:
        try:
            bridge = SourceBridge()
            if bridge and bridge.active_game:
                # only install VScript features for supported games
                if bridge.vscripts_path:
                    bridge.install_listener()
                    bridge.install_picker()     
                    bridge.install_awp_quit()
                    bridge.install_auto_spawner()  
                    bridge.setup_mapspawn()
                    bridge.setup_autoexec()
                    bridge.start_listening()
                
                print("\n" + "="*70)
                print("SETUP COMPLETE")
                print("="*70)
                print(f"\n[game] {bridge.active_game}")
                print(f"[session] {bridge.session_id}")
                print("\n[features]")
                
                if bridge.vscripts_path:
                    print("  python bridge - spawn the cube from sourcebox")
                    print("  picker - aimbot (script PickerToggle and PickerNext)")
                    print("  awp quit - shoot srcbox with awp to quit the game")
                    print("  auto-spawner - spawns 1 cube at random locations on map load")
                    print("\n[auto-load] all scripts start automatically on map load")
                    print("\n[manual] if needed:")
                    print("         script_execute python_listener")
                else:
                    print("  source game with no vscript! ONLY srcbox spawn is supported!")
                    print("  mode: automatic console command injection (however you may have issues with this)")
                    print("\n[usage] click cube in SourceBox to spawn")
                
                print("="*70 + "\n")
        except Exception as e:
            print(f"Bridge initialization error: {e}")
            bridge = None
    
    cursor_renderer = CursorRenderer('assets/images/cursor.png')
    cursor_renderer.set_scale(display_scale)
    if cursor_renderer.enabled:
        pygame.mouse.set_visible(False)
        pygame.event.set_grab(False)
    
    objects = [
        Object3D("cube", 
                 position=[-1.21, 2.11, -1.14], 
                 rotation=[1467.99, -1441.71, 27.87], 
                 scale=1.22, 
                 scale_xyz=[1.09, 0.99, 1.04],
                 brightness=0.7),
        Object3D("sphere", 
                 position=[0.03, 2.68, -1.03], 
                 rotation=[-269.60, -18.40, 0.00], 
                 scale=1.69, 
                 scale_xyz=[0.96, 0.97, 0.98],
                 brightness=0.7),
        Object3D("cone", 
                 position=[6.29, 2.49, 1.49], 
                 rotation=[157.67, 19.35, 335.96], 
                 scale=1.06, 
                 scale_xyz=[0.73, 1.51, 1.11],
                 brightness=0.7)
    ]
    
    camera = Camera()
    light = Light()
    board = Checkerboard()
    ray_caster = RayCaster()
    missing_texture_scene = MissingTextureScene(sound_manager, display_scale)
    cone_scene = ConeScene(sound_manager, display_scale)
    
    current_scene = "main"
    
    board.create_display_list()
    for obj in objects:
        obj.create_display_list()
    missing_texture_scene.create_display_list()
    cone_scene.create_display_list()
    
    clock = pygame.time.Clock()
    running = True
    
    frame_count = 0
    fps_timer = time.time()
    
    try:
        while running:
            dt = clock.tick(60) / 1000.0
            dt = min(dt, 0.1)
            
            mouse_pos = pygame.mouse.get_pos()
            
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    if current_scene == "cone":
                        cone_scene.handle_event(event)
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        if current_scene == "main":
                            clicked_obj = check_object_click(mouse_pos, ray_caster, objects)
                            
                            if clicked_obj and clicked_obj.type == "sphere":
                                current_scene = "error"
                                sound_manager.stop_music()
                                pygame.mouse.set_visible(False)
                                cursor_renderer.enabled = False
                            
                            elif clicked_obj and clicked_obj.type == "cone":
                                sound_manager.play_sound('cone_click')
                                
                                cone_duration = sound_manager.get_sound_duration('cone_click')
                                if cone_duration > 0:
                                    pygame.time.wait(int(cone_duration * 1000))  
                                else:
                                    pygame.time.wait(500)  
                                
                                display_info = pygame.display.Info()
                                screen_width = display_info.current_w
                                screen_height = display_info.current_h
                                
                                new_width = 548
                                new_height = 525
                                
                                os.environ['SDL_VIDEO_WINDOW_POS'] = f"{(screen_width - new_width) // 2},{(screen_height - new_height) // 2}"
                                
                                screen = pygame.display.set_mode((new_width, new_height), DOUBLEBUF | OPENGL)
                                display = (new_width, new_height)
                                
                                glViewport(0, 0, new_width, new_height)
                                
                                current_scene = "cone"
                                sound_manager.play_music(loops=-1, volume=0.3)
                                
                            elif clicked_obj and clicked_obj.type == "cube":
                                sound_manager.play_sound('cube_click')
                                
                                if bridge and bridge.active_game:
                                    try:
                                        bridge.spawn("props/srcbox/srcbox.mdl", 200)
                                        time.sleep(0.1) 
                                        bridge.reinstall_awp_outputs()
                                    except Exception as e:
                                        print(f"Bridge spawn error: {e}")
                                        
                                if clicked_obj.is_rotating:
                                    clicked_obj.rotation_angle = 0.0
                                else:
                                    clicked_obj.rotation_angle = 0.0
                                    clicked_obj.is_rotating = True
                                    clicked_obj.position = [-0.69, 1.43, -1.61]
                                    clicked_obj.base_rotation = [1422.99, -1461.21, 24.37]
                                    clicked_obj.scale = 1.22
                                    clicked_obj.scale_xyz = [1.15, 1.19, 1.19]
                        
                        elif current_scene == "cone":
                            # check triangle click in cone scene (LEFT-CLICK ONLY)
                            if cone_scene.check_triangle_click(mouse_pos, display[0], display[1]):
                                # play friend_join sound
                                sound_manager.play_sound('cube_click')
                                
                                # 3 second delay
                                pygame.time.wait(3000)
                                
                                # return to main menu
                                current_scene = "main"
                                
                                # restore to ORIGINAL display size
                                display_info = pygame.display.Info()
                                screen_width = display_info.current_w
                                screen_height = display_info.current_h
                                
                                # center the window with original size
                                os.environ['SDL_VIDEO_WINDOW_POS'] = f"{(screen_width - original_display[0]) // 2},{(screen_height - original_display[1]) // 2}"
                                
                                screen = pygame.display.set_mode(original_display, DOUBLEBUF | OPENGL)
                                display = original_display
                                
                                # restore OpenGL viewport and perspective
                                glViewport(0, 0, display[0], display[1])
                                
                                glMatrixMode(GL_PROJECTION)
                                glLoadIdentity()
                                aspect_ratio = display[0] / display[1]
                                gluPerspective(53.25, aspect_ratio, 0.1, 50.0)
                                glMatrixMode(GL_MODELVIEW)
                                
                                # restore cursor
                                cursor_renderer.enabled = True
                                pygame.mouse.set_visible(False)
                                
                                # restart music
                                sound_manager.stop_music()
                                sound_manager.play_music(loops=-1, volume=0.3)
            
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            
            if current_scene == "main":
                for obj in objects:
                    update_object_rotation(obj, dt)
                    update_object_animation(obj, dt)
                
                camera.apply()
                light.apply()
                
                ray_caster.update_matrices()
                
                check_object_hover(mouse_pos, ray_caster, objects, sound_manager)
                
                board.draw()
                
                for obj in objects:
                    draw_object(obj)
                
                cursor_renderer.draw(mouse_pos, display[0], display[1])
                
            elif current_scene == "error":
                missing_texture_scene.update(dt)
                missing_texture_scene.draw(display[0], display[1])

            elif current_scene == "cone":  
                cone_scene.update(dt)
                cone_scene.check_triangle_hover(mouse_pos, display[0], display[1])
                cone_scene.draw(display[0], display[1])
                cursor_renderer.draw(mouse_pos, display[0], display[1])

            pygame.display.flip()
            
            frame_count += 1
            if time.time() - fps_timer >= 1.0:
                frame_count = 0
                fps_timer = time.time()
            
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"Runtime error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("Cleaning up...")
        
        cursor_renderer.cleanup()
        sound_manager.stop_music()
        
        board.cleanup()
        for obj in objects:
            obj.cleanup()
        missing_texture_scene.cleanup()
        cone_scene.cleanup()
        
        if bridge and BRIDGE_AVAILABLE and hasattr(bridge, 'active_game') and bridge.active_game:
            try:
                bridge.stop()
            except:
                pass
        
        try:
            pygame.quit()
        except:
            pass
        
        print("Goodbye!")

if __name__ == "__main__":
    main()