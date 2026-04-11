from compprog_pygame.settings import ASSET_DIR, DEFAULT_SETTINGS


def test_default_settings_are_valid() -> None:
    assert DEFAULT_SETTINGS.width > 0
    assert DEFAULT_SETTINGS.height > 0
    assert DEFAULT_SETTINGS.fps >= 30
    assert DEFAULT_SETTINGS.columns > 0
    assert DEFAULT_SETTINGS.rows > 0
    assert DEFAULT_SETTINGS.cell_size > 0
    assert DEFAULT_SETTINGS.gravity > 0


def test_asset_directory_points_to_repo_assets() -> None:
    assert ASSET_DIR.name == "assets"