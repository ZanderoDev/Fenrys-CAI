from __future__ import annotations

import os
import platform

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Select

from fenrys.config import ConfigManager
from fenrys.doctor import format_doctor, run_doctor
from .theme.nightshade import NIGHTSHADE_CSS


class SetupScreen(Screen):
    """The wizard is a Screen so it can be opened from the dashboard safely."""

    def __init__(self, config: ConfigManager | None = None, standalone: bool = False):
        super().__init__()
        self.config = config or ConfigManager()
        self.standalone = standalone
        self.step = 0
        self.target = ""
        self.mode = "CTF"
        self.provider = "anthropic"
        self.model = "claude-sonnet-5"
        self.api_key = ""
        self.hexstrike_url = "http://127.0.0.1:8888"
        self.doctor_result = ""
        self.agent_mappings = {
            agent: self.config.resolve_agent(agent)
            for agent in self.config.load("agents.yaml").get("agents", {})
        }

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(id="wizard")
        yield Footer()

    def on_mount(self) -> None:
        self.render_step()

    def render_step(self) -> None:
        """Mount concrete widgets; do not use yield here (it is not compose())."""
        panel = self.query_one("#wizard")
        panel.remove_children()
        titles = [
            "Welcome", "Platform Check", "Provider Setup", "Agent ↔ Model Mapping",
            "HexStrike Detection", "Scope & Mode", "Review", "Finalize", "Ready",
        ]
        content = [Label(f"SETUP WIZARD  {self.step + 1}/9  —  {titles[self.step]}", classes="title")]
        if self.step == 0:
            content += [
                Label("Configure Fenrys-CAI for local-first, authorized security work.", classes="panel"),
                Label("The wizard never writes API key values to disk."),
            ]
        elif self.step == 1:
            content += [
                Label(f"✓ Python {platform.python_version()}"),
                Label(f"✓ Platform {platform.system()} {platform.machine()}"),
                Label("✓ SQLite (stdlib)"),
                Label("Optional: uv and HexStrike are checked by doctor.", classes="muted"),
            ]
        elif self.step == 2:
            providers = sorted(self.config.load("providers.yaml").get("providers", {}))
            content += [
                Label("Choose a configured provider and optionally test it now."),
                Select([(name, name) for name in providers], value=self.provider, id="provider"),
                Input(value=self.model, placeholder="Model name", id="model"),
                Input(placeholder="API key (used in memory for this test only)", password=True, id="api-key"),
                Label("Not tested yet", id="provider-status", classes="muted"),
                Button("Test Connection", id="test-provider"),
            ]
        elif self.step == 3:
            content += [
                Label("Recommended model tiers are loaded from agents.yaml."),
                Label("Edit provider/model per agent. Changes apply to the next task without restart.", classes="muted"),
            ]
            providers = sorted(self.config.load("providers.yaml").get("providers", {}))
            for agent, mapping in self.agent_mappings.items():
                content += [
                    Label(agent.upper(), classes="title"),
                    Select([(name, name) for name in providers], value=mapping["provider"], id=f"map-provider-{agent}"),
                    Input(value=mapping["model"], id=f"map-model-{agent}"),
                ]
        elif self.step == 4:
            content += [
                Label("Default HexStrike endpoint"),
                Input(value=self.hexstrike_url, id="hexstrike-url"),
                Label("Health is checked by fenrys doctor and cached tool discovery happens once per process.", classes="muted"),
            ]
        elif self.step == 5:
            content += [
                Label("Default operating mode"),
                Select([(m, m) for m in ("CTF", "LAB", "AUTHORIZED_PENTEST", "NORMAL")], value=self.mode, id="mode"),
                Input(value=self.target, placeholder="Initial target (optional)", id="target"),
            ]
        elif self.step == 6:
            content += [
                Label(f"Provider: {self.provider} / {self.model}"),
                Label(f"HexStrike: {self.hexstrike_url}"),
                Label(f"Mode: {self.mode}"),
                Label(f"Target: {self.target or 'not set'}"),
            ]
        elif self.step == 7:
            content += [
                Label("Configuration is ready to be written with atomic updates and .bak backups..."),
                Label("Provider secrets are referenced by environment variable only.", classes="muted"),
            ]
        else:
            content += [
                Label("Fenrys-CAI is ready.", classes="ok"),
                Label("Commands: fenrys doctor · fenrys model list · fenrys session new"),
                Label(self.doctor_result or "Doctor has not run yet.", classes="muted"),
            ]
        buttons = []
        if self.step > 0:
            buttons.append(Button("Back", id="back"))
        if self.step < 7:
            buttons.append(Button("Next", variant="primary", id="next"))
        elif self.step == 7:
            buttons.append(Button("Finalize", variant="success", id="finalize"))
        else:
            buttons.append(Button("Launch Dashboard", variant="primary", id="launch"))
        panel.mount(Vertical(*content, classes="panel"), Horizontal(*buttons, classes="panel"))

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "test-provider":
            self.capture()
            if self.api_key:
                entry = self.config.load("providers.yaml")["providers"].get(self.provider, {})
                env_name = entry.get("api_key_env")
                if env_name:
                    os.environ[env_name] = self.api_key
            from fenrys.providers import ProviderRegistry
            health = await ProviderRegistry(self.config).build(self.provider, self.model).health_check()
            status = self.query_one("#provider-status", Label)
            status.update(("✓ " if health.ok else "✗ ") + health.reason)
            status.set_class(not health.ok, "danger")
            status.set_class(health.ok, "ok")
            return
        if button_id == "next":
            self.capture()
            self.step += 1
            self.render_step()
        elif button_id == "back":
            self.capture()
            self.step -= 1
            self.render_step()
        elif button_id == "finalize":
            self.capture()
            self.config.write_initial(self.mode, self.target or None)
            self.config.save("config.yaml", {**self.config.load("config.yaml"), "hexstrike_url": self.hexstrike_url})
            agents = self.config.load("agents.yaml")
            agents["agents"].update(self.agent_mappings)
            self.config.save("agents.yaml", agents)
            self.doctor_result = format_doctor(await run_doctor(self.config))
            self.step = 8
            self.render_step()
        elif button_id == "launch":
            if self.standalone:
                self.app.exit()
            else:
                self.dismiss(True)

    def capture(self) -> None:
        provider = self.query("#provider")
        model = self.query("#model")
        api_key = self.query("#api-key")
        hexstrike = self.query("#hexstrike-url")
        mode = self.query("#mode")
        target = self.query("#target")
        if provider and provider.first(Select).value:
            self.provider = str(provider.first(Select).value)
        if model:
            self.model = model.first(Input).value.strip() or self.model
        if api_key:
            self.api_key = api_key.first(Input).value
        if hexstrike:
            self.hexstrike_url = hexstrike.first(Input).value.strip() or self.hexstrike_url
        if mode and mode.first(Select).value:
            self.mode = str(mode.first(Select).value)
        if target:
            self.target = target.first(Input).value.strip()
        for agent in self.agent_mappings:
            provider_widget = self.query(f"#map-provider-{agent}")
            model_widget = self.query(f"#map-model-{agent}")
            if provider_widget and provider_widget.first(Select).value and model_widget:
                self.agent_mappings[agent] = {
                    "provider": str(provider_widget.first(Select).value),
                    "model": model_widget.first(Input).value.strip() or self.agent_mappings[agent]["model"],
                }


class SetupWizardApp(App):
    TITLE = "Fenrys-CAI Setup"
    CSS = NIGHTSHADE_CSS

    def __init__(self, config: ConfigManager | None = None):
        super().__init__()
        self.config = config or ConfigManager()

    def compose(self) -> ComposeResult:
        yield SetupScreen(self.config, standalone=True)
