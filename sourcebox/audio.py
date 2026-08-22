"""Sound-effect and music management."""

from sourcebox.resources import find_resource
class SoundManager:
    def __init__(self):
        self.sounds = {}
        self.music_loaded = False
        self.initialized = False
        self._mixer = None

        try:
            import pygame.mixer as mixer

            mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            self._mixer = mixer
            self.initialized = True
        except Exception as e:
            print(f"Failed to initialize audio: {e}")

    def load_sound(self, name, filepath):
        if not self.initialized or not self._mixer:
            return False

        try:
            sound_path = find_resource(filepath)
            if sound_path:
                self.sounds[name] = self._mixer.Sound(sound_path)
                return True
            return False
        except Exception as e:
            print(f"Error loading sound {name}: {e}")
            return False

    def stop_sound(self, name):
        if self.initialized and name in self.sounds:
            try:
                self.sounds[name].stop()
            except:
                pass

    def get_sound_duration(self, name):
        if self.initialized and name in self.sounds:
            try:
                return self.sounds[name].get_length()
            except:
                return 0.0
        return 0.0

    def load_music(self, filepath):
        if not self.initialized or not self._mixer:
            return False

        try:
            music_path = find_resource(filepath)
            if music_path:
                self._mixer.music.load(music_path)
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

    def play_music(self, loops=-1, volume=0.5, start=0.0):
        if self.initialized and self.music_loaded and self._mixer:
            try:
                self._mixer.music.set_volume(max(0.0, min(1.0, volume)))
                self._mixer.music.play(loops, start=start)
            except:
                pass

    def stop_music(self):
        if self.initialized and self.music_loaded and self._mixer:
            try:
                self._mixer.music.stop()
            except:
                pass
