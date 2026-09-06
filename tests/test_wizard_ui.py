import pytest
from textual.widgets import Button

from fenrys.ui.app import FenrysApp
from fenrys.ui.wizard import SetupWizardApp, SetupScreen


@pytest.mark.asyncio
async def test_wizard_renders_real_children(temp_config):
    async with SetupWizardApp(temp_config).run_test(size=(120, 50)) as pilot:
        wizard = pilot.app.query_one(SetupScreen)
        assert wizard.size.width > 0
        assert wizard.size.height > 0
        assert isinstance(wizard, SetupScreen)
        assert len(wizard.query("#wizard").first().children) >= 2
        assert wizard.query_one("#next")
        wizard.step = 2
        wizard.render_step()
        await pilot.pause()
        assert wizard.query_one("#save-custom-provider")
        wizard.query_one("#custom-provider-name").value = "openrouter"
        wizard.query_one("#custom-base-url").value = "https://openrouter.ai/api/v1"
        wizard.query_one("#custom-api-env").value = "OPENROUTER_API_KEY"
        await wizard.on_button_pressed(Button.Pressed(wizard.query_one("#save-custom-provider")))
        assert temp_config.load("providers.yaml")["providers"]["openrouter"]["type"] == "custom"
        assert "Saved openrouter" in wizard.provider_status


@pytest.mark.asyncio
async def test_provider_test_reports_missing_key_without_crashing(temp_config, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    async with SetupWizardApp(temp_config).run_test(size=(120, 50)) as pilot:
        wizard = pilot.app.query_one(SetupScreen)
        wizard.step = 2
        wizard.render_step()
        await pilot.pause()
        await wizard.on_button_pressed(Button.Pressed(wizard.query_one("#test-provider")))

        assert "OPENROUTER_API_KEY" in wizard.provider_status


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
