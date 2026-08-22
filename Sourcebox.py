import pygame
import os
import sys
import time
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *

import platform

from cone_scene import ConeScene
from rendering_helpers import PIL_AVAILABLE, pil_load_image_rgba
from sourcebox.audio import SoundManager
from sourcebox.bridges import BridgeManager
from sourcebox.cursor import CursorRenderer
from sourcebox.diagnostics import configure_runtime_diagnostics
from sourcebox.raycast import RayCaster
from sourcebox.rendering.main_scene import Camera, Checkerboard, Light, Object3D
from sourcebox.resources import find_resource
from sourcebox.scenes.missing_texture import MissingTextureScene

# platform detection
OPERATING_SYSTEM = platform.system()

# hide console window on windows
if OPERATING_SYSTEM == 'Windows':
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
    from source_bridge import SourceBridge, WINDOWS_API_AVAILABLE
    BRIDGE_AVAILABLE = True
except ImportError:
    BRIDGE_AVAILABLE = False
    WINDOWS_API_AVAILABLE = False
    print("Warning: source_bridge not available")

try:
    from gmod_bridge import GModBridge
    GMOD_BRIDGE_AVAILABLE = True
except ImportError:
    GMOD_BRIDGE_AVAILABLE = False
    print("Warning: gmod_bridge not available")


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

        # get_desktop_sizes() is more reliable than display.Info() on Linux/Wayland,
        # especially after screen lock/unlock where display.Info() can return wrong values
        if hasattr(pygame.display, 'get_desktop_sizes'):
            desktop_sizes = pygame.display.get_desktop_sizes()
            if desktop_sizes:
                screen_width, screen_height = desktop_sizes[0]
            else:
                display_info = pygame.display.Info()
                screen_width = display_info.current_w
                screen_height = display_info.current_h
        else:
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
            except Exception as error:
                fallback_loaded = False
                if PIL_AVAILABLE:
                    pil_result = pil_load_image_rgba(icon_path, flip_y=False)
                    if pil_result:
                        icon_data, width, height = pil_result
                        try:
                            icon = pygame.image.frombuffer(icon_data, (width, height), "RGBA")
                            pygame.display.set_icon(icon)
                            print(f"Icon loaded: {icon_path}")
                            fallback_loaded = True
                        except Exception:
                            pass

                if not fallback_loaded:
                    print(f"Failed to load icon: {error}")

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
    configure_runtime_diagnostics()
    print(f"Running on: {OPERATING_SYSTEM}")

    display, _screen = init_pygame()

    original_display = display

    display_scale = get_display_scale(display[0], display[1])
    print(f"Display scale factor: {display_scale:.2f}")

    sound_manager = SoundManager()
    sound_manager.load_sound('hover', 'assets/sounds/click.wav')
    sound_manager.load_sound('cube_click', 'assets/sounds/friend_join.wav')
    sound_manager.load_sound('cone_click', 'assets/sounds/cone.wav')
    sound_manager.load_sound('cone_back', 'assets/sounds/coneback.wav')
    sound_manager.load_music('assets/sounds/sourcebox.dll.mp3')
    # sourcebox album version don't start until like 2 sec for some reason but i am keeping it
    # until like when person go to voidside tracker or person go back to main menu
    # when song restarts, it will start 2 sec later so lol
    sound_manager.play_music(loops=-1, volume=0.3)

    bridge_manager = BridgeManager(
        SourceBridge if BRIDGE_AVAILABLE else None,
        GModBridge if GMOD_BRIDGE_AVAILABLE else None,
        platform_name=OPERATING_SYSTEM,
        windows_api_available=WINDOWS_API_AVAILABLE,
    ).initialize()

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

                                # clear hover so cone shows normal color between flashes
                                clicked_obj.is_hovered = False

                                # red -> normal -> red -> normal -> red (fast)
                                flash_pattern = [True, False, True, False, True]
                                for is_red in flash_pattern:
                                    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
                                    camera.apply()
                                    light.apply()
                                    board.draw(display[0], display[1])
                                    glDisable(GL_TEXTURE_2D)
                                    glBindTexture(GL_TEXTURE_2D, 0)
                                    glEnable(GL_LIGHTING)
                                    glEnable(GL_DEPTH_TEST)
                                    glEnable(GL_COLOR_MATERIAL)
                                    glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
                                    for o in objects:
                                        if o == clicked_obj:
                                            glPushMatrix()
                                            glTranslatef(*o.position)
                                            if o.base_rotation[0]: glRotatef(o.base_rotation[0], 1, 0, 0)
                                            if o.base_rotation[1]: glRotatef(o.base_rotation[1], 0, 1, 0)
                                            if o.base_rotation[2]: glRotatef(o.base_rotation[2], 0, 0, 1)
                                            sx = o.scale * o.scale_xyz[0]
                                            sy = o.scale * o.scale_xyz[1]
                                            sz = o.scale * o.scale_xyz[2]
                                            glScalef(sx, sy, sz)
                                            if is_red:
                                                glDisable(GL_LIGHTING)
                                                glColor3f(1.0, 0.0, 0.0)
                                                glCallList(o.display_list)
                                                glEnable(GL_LIGHTING)
                                            else:
                                                b = 0.65 * o.brightness
                                                glColor3f(b, b, b)
                                                glCallList(o.display_list)
                                            glPopMatrix()
                                        else:
                                            draw_object(o)
                                    cursor_renderer.draw(mouse_pos, display[0], display[1])
                                    pygame.display.flip()
                                    pygame.time.wait(80)

                                cone_duration = sound_manager.get_sound_duration('cone_click')
                                remaining = int(cone_duration * 1000) - 400 if cone_duration > 0 else 100
                                if remaining > 0:
                                    pygame.time.wait(remaining)

                                if hasattr(pygame.display, 'get_desktop_sizes'):
                                    desktop_sizes = pygame.display.get_desktop_sizes()
                                    screen_width, screen_height = desktop_sizes[0] if desktop_sizes else (1920, 1080)
                                else:
                                    _di = pygame.display.Info()
                                    screen_width, screen_height = _di.current_w, _di.current_h

                                new_width = 548
                                new_height = 525

                                os.environ['SDL_VIDEO_WINDOW_POS'] = f"{(screen_width - new_width) // 2},{(screen_height - new_height) // 2}"

                                pygame.display.set_mode((new_width, new_height), DOUBLEBUF | OPENGL)
                                display = (new_width, new_height)

                                glViewport(0, 0, new_width, new_height)

                                current_scene = "cone"
                                sound_manager.play_music(loops=-1, volume=0.3, start=1.0)

                            elif clicked_obj and clicked_obj.type == "cube":
                                sound_manager.play_sound('cube_click')
                                bridge_manager.spawn_default_cube()

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
                                sound_manager.play_sound('cone_back')

                                # clear hover so triangle shows normal color between flashes
                                cone_scene.triangle_hovered = False

                                # red -> grey -> red -> grey -> red
                                flash_pattern = ["red", "grey", "red", "grey", "red"]
                                for state in flash_pattern:
                                    cone_scene.triangle_flash_red = state
                                    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
                                    cone_scene.draw(display[0], display[1])
                                    cursor_renderer.draw(mouse_pos, display[0], display[1])
                                    pygame.display.flip()
                                    pygame.time.wait(80)
                                cone_scene.triangle_flash_red = False

                                # 3 second delay (minus flash time)
                                pygame.time.wait(2600)

                                # return to main menu
                                current_scene = "main"

                                # restore to ORIGINAL display size
                                if hasattr(pygame.display, 'get_desktop_sizes'):
                                    desktop_sizes = pygame.display.get_desktop_sizes()
                                    screen_width, screen_height = desktop_sizes[0] if desktop_sizes else (1920, 1080)
                                else:
                                    _di = pygame.display.Info()
                                    screen_width, screen_height = _di.current_w, _di.current_h

                                # center the window with original size
                                os.environ['SDL_VIDEO_WINDOW_POS'] = f"{(screen_width - original_display[0]) // 2},{(screen_height - original_display[1]) // 2}"

                                pygame.display.set_mode(original_display, DOUBLEBUF | OPENGL)
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
                                sound_manager.play_music(loops=-1, volume=0.3, start=1.0)

            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

            if current_scene == "main":
                for obj in objects:
                    update_object_rotation(obj, dt)
                    update_object_animation(obj, dt)

                camera.apply()
                light.apply()

                ray_caster.update_matrices()

                check_object_hover(mouse_pos, ray_caster, objects, sound_manager)

                board.draw(display[0], display[1])
                glDisable(GL_TEXTURE_2D)
                glBindTexture(GL_TEXTURE_2D, 0)

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

        bridge_manager.cleanup()

        try:
            pygame.quit()
        except:
            pass

        print("Goodbye!")

if __name__ == "__main__":
    main()
