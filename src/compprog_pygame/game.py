from __future__ import annotations

import random
from dataclasses import dataclass

import pygame

from compprog_pygame.settings import DEFAULT_SETTINGS, GameSettings


BACKGROUND = (9, 12, 25)
STAR_COLOR = (170, 215, 255)
PLAYER_FILL = (255, 192, 84)
PLAYER_OUTLINE = (255, 245, 214)
ORB_COLOR = (85, 241, 196)
TEXT_COLOR = (242, 244, 255)
HUD_PANEL = (16, 24, 45)


@dataclass(slots=True)
class Star:
    x: float
    y: float
    radius: int
    speed: float


class Player:
    def __init__(self, settings: GameSettings) -> None:
        self.size = 54
        self.speed = settings.player_speed
        self.position = pygame.Vector2(settings.width / 2, settings.height / 2)
        self.rect = pygame.Rect(0, 0, self.size, self.size)
        self.rect.center = self.position

    def update(self, dt: float, pressed: pygame.key.ScancodeWrapper, bounds: pygame.Rect) -> None:
        move = pygame.Vector2(
            pressed[pygame.K_d] - pressed[pygame.K_a],
            pressed[pygame.K_s] - pressed[pygame.K_w],
        )
        move.x += pressed[pygame.K_RIGHT] - pressed[pygame.K_LEFT]
        move.y += pressed[pygame.K_DOWN] - pressed[pygame.K_UP]
        if move.length_squared() > 0:
            move = move.normalize()
            self.position += move * self.speed * dt

        half_size = self.size / 2
        self.position.x = max(bounds.left + half_size, min(bounds.right - half_size, self.position.x))
        self.position.y = max(bounds.top + half_size, min(bounds.bottom - half_size, self.position.y))
        self.rect.center = (round(self.position.x), round(self.position.y))

    def draw(self, surface: pygame.Surface) -> None:
        pygame.draw.rect(surface, PLAYER_FILL, self.rect, border_radius=14)
        pygame.draw.rect(surface, PLAYER_OUTLINE, self.rect, width=3, border_radius=14)


class Pickup:
    def __init__(self, settings: GameSettings) -> None:
        self.radius = settings.pickup_radius
        self.position = pygame.Vector2()
        self.respawn(settings)

    def respawn(self, settings: GameSettings) -> None:
        padding = 48
        self.position.xy = (
            random.randint(padding, settings.width - padding),
            random.randint(padding, settings.height - padding),
        )

    def draw(self, surface: pygame.Surface) -> None:
        center = (round(self.position.x), round(self.position.y))
        pygame.draw.circle(surface, ORB_COLOR, center, self.radius)
        pygame.draw.circle(surface, TEXT_COLOR, center, self.radius, width=2)


class Game:
    def __init__(self, settings: GameSettings = DEFAULT_SETTINGS) -> None:
        self.settings = settings
        self.screen = pygame.display.set_mode((settings.width, settings.height))
        pygame.display.set_caption(settings.title)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 34)
        self.big_font = pygame.font.Font(None, 72)
        self.bounds = self.screen.get_rect()
        self.player = Player(settings)
        self.pickup = Pickup(settings)
        self.score = 0
        self.running = True
        self.stars = self._create_stars(40)

    def _create_stars(self, count: int) -> list[Star]:
        stars: list[Star] = []
        for _ in range(count):
            stars.append(
                Star(
                    x=random.uniform(0, self.settings.width),
                    y=random.uniform(0, self.settings.height),
                    radius=random.randint(1, 3),
                    speed=random.uniform(24.0, 120.0),
                )
            )
        return stars

    def run(self) -> None:
        while self.running:
            dt = self.clock.tick(self.settings.fps) / 1000
            self._handle_events()
            self._update(dt)
            self._draw()

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.running = False

    def _update(self, dt: float) -> None:
        pressed = pygame.key.get_pressed()
        self.player.update(dt, pressed, self.bounds)

        for star in self.stars:
            star.y += star.speed * dt
            if star.y > self.settings.height:
                star.y = 0
                star.x = random.uniform(0, self.settings.width)

        distance = self.player.position.distance_to(self.pickup.position)
        if distance <= (self.player.size / 2) + self.pickup.radius:
            self.score += 1
            self.pickup.respawn(self.settings)

    def _draw(self) -> None:
        self.screen.fill(BACKGROUND)
        for star in self.stars:
            pygame.draw.circle(self.screen, STAR_COLOR, (round(star.x), round(star.y)), star.radius)

        self.pickup.draw(self.screen)
        self.player.draw(self.screen)
        self._draw_hud()
        pygame.display.flip()

    def _draw_hud(self) -> None:
        title = self.big_font.render("Starter Arena", True, TEXT_COLOR)
        subtitle = self.font.render("Move with WASD or arrow keys. Collect the orbs.", True, TEXT_COLOR)
        score = self.font.render(f"Score: {self.score}", True, TEXT_COLOR)

        panel = pygame.Rect(24, 24, 460, 132)
        pygame.draw.rect(self.screen, HUD_PANEL, panel, border_radius=18)
        pygame.draw.rect(self.screen, STAR_COLOR, panel, width=2, border_radius=18)

        self.screen.blit(title, (panel.x + 20, panel.y + 18))
        self.screen.blit(subtitle, (panel.x + 22, panel.y + 74))
        self.screen.blit(score, (panel.x + 22, panel.y + 100))


def main() -> None:
    pygame.init()
    try:
        game = Game()
        game.run()
    finally:
        pygame.quit()