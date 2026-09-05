import pytest

from fenrys.ui.app import FenrysApp
from fenrys.ui.wizard import SetupWizardApp, SetupScreen


@pytest.mark.asyncio
async def test_wizard_renders_real_children(temp_config):
    async with SetupWizardApp(temp_config).run_test() as pilot:
        wizard = pilot.app.query_one(SetupScreen)
        assert isinstance(wizard, SetupScreen)
        assert len(wizard.query("#wizard").first().children) >= 2
        assert wizard.query_one("#next")


@pytest.mark.asyncio
async def test_dashboard_setup_binding_pushes_screen(temp_config, tmp_path):
    temp_config.save("config.yaml", {
        "database_path": str(tmp_path / "state.db"),
        "raw_output_dir": str(tmp_path / "raw"),
    })
    async with FenrysApp(temp_config).run_test() as pilot:
        await pilot.pause(1.1)
        assert pilot.app.query_one("#command")
        pilot.app.action_setup()
        await pilot.pause()
        assert isinstance(pilot.app.screen_stack[-1], SetupScreen)