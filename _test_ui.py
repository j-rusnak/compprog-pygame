import sys, traceback
sys.path.insert(0, 'src')
try:
    import pygame
    pygame.init()
    screen = pygame.display.set_mode((1280, 800))

    from compprog_pygame.games.hex_colony.game import Game
    from compprog_pygame.games.hex_colony.buildings import BuildingType

    g = Game()
    g._building_info.tier_tracker = g.tier_tracker
    g._resource_bar.tier_tracker = g.tier_tracker
    g._resource_bar.tech_tree = g.tech_tree
    g._resource_bar.world = g.world

    g._resource_bar.layout(1280, 800)
    g._bottom_bar.layout(1280, 800)
    g._building_info.layout(1280, 800)
    g._tile_info.layout(1280, 800)
    g._minimap.layout(1280, 800)
    g._pause_overlay.layout(1280, 800)
    g._game_over_overlay.layout(1280, 800)
    g._help_overlay.layout(1280, 800)
    g._tech_tree_overlay.layout(1280, 800)

    g._resource_bar.draw(screen, g.world)
    print('resource_bar OK')
    g._bottom_bar.draw(screen, g.world)
    print('bottom_bar OK')

    camp = [b for b in g.world.buildings.buildings if b.type == BuildingType.CAMP][0]
    g._building_info.building = camp
    g._building_info.draw(screen, g.world)
    print('camp popup OK')

    from compprog_pygame.games.hex_colony.hex_grid import HexCoord
    c = HexCoord(3, 3)
    if c in list(g.world.grid.coords()):
        g._tile_info.tile = g.world.grid[c]
        g._tile_info.coord = c
        g._tile_info.draw(screen, g.world)
        print('tile_info OK')

    g._minimap.camera = g.camera
    g._minimap.draw(screen, g.world)
    print('minimap OK')

    g._pause_overlay.show()
    g._pause_overlay.draw(screen, g.world)
    g._pause_overlay.state = 'options'
    g._pause_overlay.draw(screen, g.world)
    g._pause_overlay.hide()
    print('pause_overlay OK')

    g._help_overlay.visible = True
    g._help_overlay.draw(screen, g.world)
    print('help_overlay OK')

    g._game_over_overlay.active = True
    g._game_over_overlay.draw(screen, g.world)
    print('game_over OK')

    g._tech_tree_overlay.tech_tree = g.tech_tree
    g._tech_tree_overlay.visible = True
    g._tech_tree_overlay.draw(screen, g.world)
    print('tech_tree_overlay OK')

    screen2 = pygame.display.set_mode((800, 600))
    g._resource_bar.layout(800, 600)
    g._resource_bar.sandbox = True
    g._resource_bar.sim_speed = 3
    g._resource_bar.delete_mode = True
    g._resource_bar.draw(screen2, g.world)
    print('small screen resource bar OK')

    g._bottom_bar.layout(800, 600)
    g._bottom_bar._active = 0
    g._bottom_bar.layout(800, 600)
    g._bottom_bar.draw(screen2, g.world)
    print('small screen bottom bar OK')

    g._building_info.layout(800, 600)
    g._building_info.draw(screen2, g.world)
    print('small screen building info OK')

    pygame.quit()
    print('ALL OK')
except Exception as e:
    traceback.print_exc()
    sys.exit(1)
