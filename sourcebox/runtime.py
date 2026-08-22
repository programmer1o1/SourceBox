"""Small runtime capability checks shared by scenes."""


def pygame_font_available() -> bool:
    try:
        import pygame.font

        pygame.font.init()
        pygame.font.Font(None, 12)
        return True
    except Exception:
        return False
