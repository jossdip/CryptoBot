from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from .base import Command


class ConfigCommand(Command):
    name = "config"
    aliases = ["cfg"]

    def __init__(self, context: Dict[str, Any]):
        super().__init__(context)
        self.console = Console()
        self.config_path = context.get("config_path", "configs/live.hyperliquid.yaml")
        self.env_paths = [
            Path.home() / ".cryptobot" / ".env",  # Global
            Path(".env"),  # Project-level
        ]

    def run(self, args: List[str]) -> None:  # pragma: no cover - interactive
        """Menu interactif de configuration."""
        if not args:
            self._show_main_menu()
            return

        subcommand = args[0].lower()
        if subcommand == "apis":
            self._config_apis()
        elif subcommand == "strategies":
            self._config_strategies()
        elif subcommand == "weights":
            self._config_weights()
        elif subcommand == "risk":
            self._config_risk()
        elif subcommand == "general":
            self._config_general()
        elif subcommand == "broker":
            self._config_broker()
        elif subcommand == "llm":
            self._config_llm()
        elif subcommand == "hyperliquid":
            self._config_hyperliquid()
        elif subcommand == "show":
            self._show_config()
        elif subcommand == "save":
            self._save_config()
        else:
            self.console.print(f"[red]Unknown subcommand: {subcommand}[/red]")
            self._show_main_menu()

    def _show_main_menu(self) -> None:
        """Affiche le menu principal de configuration."""
        table = Table(title="[cyan]Configuration Menu[/cyan]", show_header=False, box=None)
        table.add_row("[bold cyan]1.[/bold cyan]", "[yellow]APIs[/yellow]", "- Configurer les clés API (Hyperliquid, LLM, Exchange)")
        table.add_row("[bold cyan]2.[/bold cyan]", "[yellow]Strategies[/yellow]", "- Configurer les stratégies et leurs paramètres")
        table.add_row("[bold cyan]3.[/bold cyan]", "[yellow]Weights[/yellow]", "- Configurer les poids des stratégies")
        table.add_row("[bold cyan]4.[/bold cyan]", "[yellow]Risk[/yellow]", "- Configurer les paramètres de risque")
        table.add_row("[bold cyan]5.[/bold cyan]", "[yellow]General[/yellow]", "- Configurer les paramètres généraux (symbols, capital, etc.)")
        table.add_row("[bold cyan]6.[/bold cyan]", "[yellow]Broker[/yellow]", "- Configurer les paramètres du broker")
        table.add_row("[bold cyan]7.[/bold cyan]", "[yellow]LLM[/yellow]", "- Configurer les paramètres LLM")
        table.add_row("[bold cyan]8.[/bold cyan]", "[yellow]Hyperliquid[/yellow]", "- Configurer les paramètres Hyperliquid")
        table.add_row("[bold cyan]9.[/bold cyan]", "[yellow]Show[/yellow]", "- Afficher la configuration actuelle")
        table.add_row("[bold cyan]0.[/bold cyan]", "[yellow]Exit[/yellow]", "- Quitter le menu de configuration")
        
        self.console.print(table)
        
        choice = Prompt.ask("\n[cyan]Choisissez une option[/cyan]", choices=["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"], default="0")
        
        if choice == "1":
            self._config_apis()
        elif choice == "2":
            self._config_strategies()
        elif choice == "3":
            self._config_weights()
        elif choice == "4":
            self._config_risk()
        elif choice == "5":
            self._config_general()
        elif choice == "6":
            self._config_broker()
        elif choice == "7":
            self._config_llm()
        elif choice == "8":
            self._config_hyperliquid()
        elif choice == "9":
            self._show_config()

    def _get_env_file(self) -> Path:
        """Retourne le chemin du fichier .env à utiliser."""
        # Préférer le fichier global s'il existe, sinon le projet
        for env_path in self.env_paths:
            if env_path.exists():
                return env_path
        # Si aucun n'existe, créer le fichier global
        env_path = self.env_paths[0]
        env_path.parent.mkdir(parents=True, exist_ok=True)
        return env_path

    def _read_env_file(self) -> Dict[str, str]:
        """Lit le fichier .env et retourne un dictionnaire."""
        env_file = self._get_env_file()
        env_vars = {}
        if env_file.exists():
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    # Ignorer les commentaires et lignes vides
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        env_vars[key.strip()] = value.strip()
        return env_vars

    def _write_env_file(self, env_vars: Dict[str, str]) -> None:
        """Écrit le dictionnaire dans le fichier .env en préservant les commentaires."""
        env_file = self._get_env_file()
        
        # Lire le fichier existant pour préserver les commentaires et l'ordre
        existing_lines = []
        if env_file.exists():
            with open(env_file, "r", encoding="utf-8") as f:
                existing_lines = f.readlines()
        
        # Créer un mapping des variables existantes
        existing_vars = set()
        for line in existing_lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.split("=", 1)[0].strip()
                existing_vars.add(key)
        
        # Écrire le fichier en préservant l'ordre et les commentaires
        written_vars = set()
        with open(env_file, "w", encoding="utf-8") as f:
            # Parcourir les lignes existantes et les mettre à jour
            i = 0
            while i < len(existing_lines):
                line = existing_lines[i]
                stripped = line.strip()
                
                if stripped.startswith("#"):
                    # Écrire le commentaire tel quel
                    f.write(line)
                    i += 1
                elif stripped and "=" in stripped:
                    # Variable existante
                    key = stripped.split("=", 1)[0].strip()
                    if key in env_vars:
                        # Mettre à jour la variable
                        f.write(f"{key}={env_vars[key]}\n")
                        written_vars.add(key)
                    else:
                        # Garder la variable si elle n'est pas dans env_vars
                        f.write(line)
                    i += 1
                else:
                    # Ligne vide ou autre
                    f.write(line)
                    i += 1
            
            # Ajouter les nouvelles variables qui n'existaient pas
            for key, value in env_vars.items():
                if key not in written_vars:
                    f.write(f"{key}={value}\n")
        
        self.console.print(f"[green]✓ Configuration sauvegardée dans {env_file}[/green]")

    def _config_apis(self) -> None:
        """Configure les clés API."""
        self.console.print(Panel("[cyan]Configuration des Clés API[/cyan]", border_style="cyan"))
        
        env_vars = self._read_env_file()
        
        # Hyperliquid
        self.console.print("\n[bold yellow]Hyperliquid[/bold yellow]")
        wallet = Prompt.ask(
            "Wallet Address",
            default=env_vars.get("HYPERLIQUID_WALLET_ADDRESS", ""),
            show_default=True
        )
        if wallet:
            env_vars["HYPERLIQUID_WALLET_ADDRESS"] = wallet
        
        testnet_key = Prompt.ask(
            "Testnet Private Key (0x...)",
            default=env_vars.get("HYPERLIQUID_TESTNET_PRIVATE_KEY", ""),
            show_default=True,
            password=True
        )
        if testnet_key:
            env_vars["HYPERLIQUID_TESTNET_PRIVATE_KEY"] = testnet_key
        
        live_key = Prompt.ask(
            "Live Private Key (0x...) [OPTIONAL]",
            default=env_vars.get("HYPERLIQUID_LIVE_PRIVATE_KEY", ""),
            show_default=True,
            password=True
        )
        if live_key:
            env_vars["HYPERLIQUID_LIVE_PRIVATE_KEY"] = live_key
        
        # LLM / DeepSeek
        self.console.print("\n[bold yellow]LLM / DeepSeek[/bold yellow]")
        llm_key = Prompt.ask(
            "LLM API Key (sk-...)",
            default=env_vars.get("LLM_API_KEY", ""),
            show_default=True,
            password=True
        )
        if llm_key:
            env_vars["LLM_API_KEY"] = llm_key
        
        llm_url = Prompt.ask(
            "LLM Base URL",
            default=env_vars.get("LLM_BASE_URL", "https://api.deepseek.com/v1"),
            show_default=True
        )
        if llm_url:
            env_vars["LLM_BASE_URL"] = llm_url
        
        llm_model = Prompt.ask(
            "LLM Model",
            default=env_vars.get("LLM_MODEL", "deepseek-chat"),
            show_default=True
        )
        if llm_model:
            env_vars["LLM_MODEL"] = llm_model
        
        # Exchange (optionnel)
        self.console.print("\n[bold yellow]Exchange (Optionnel)[/bold yellow]")
        exchange_key = Prompt.ask(
            "Exchange API Key",
            default=env_vars.get("EXCHANGE_API_KEY", ""),
            show_default=True
        )
        if exchange_key:
            env_vars["EXCHANGE_API_KEY"] = exchange_key
        
        exchange_secret = Prompt.ask(
            "Exchange API Secret",
            default=env_vars.get("EXCHANGE_API_SECRET", ""),
            show_default=True,
            password=True
        )
        if exchange_secret:
            env_vars["EXCHANGE_API_SECRET"] = exchange_secret
        
        if Confirm.ask("\n[cyan]Sauvegarder les modifications?[/cyan]", default=True):
            self._write_env_file(env_vars)
            self.console.print("[green]✓ Clés API sauvegardées![/green]")

    def _load_yaml_config(self) -> Dict[str, Any]:
        """Charge la configuration YAML."""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            self.console.print(f"[red]Fichier de configuration non trouvé: {self.config_path}[/red]")
            return {}
        except Exception as e:
            self.console.print(f"[red]Erreur lors du chargement: {e}[/red]")
            return {}

    def _save_yaml_config(self, config: Dict[str, Any]) -> None:
        """Sauvegarde la configuration YAML."""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
            self.console.print(f"[green]✓ Configuration sauvegardée dans {self.config_path}[/green]")
        except Exception as e:
            self.console.print(f"[red]Erreur lors de la sauvegarde: {e}[/red]")

    def _config_weights(self) -> None:
        """Configure les poids des stratégies."""
        self.console.print(Panel("[cyan]Configuration des Poids des Stratégies[/cyan]", border_style="cyan"))
        
        config = self._load_yaml_config()
        weights = config.get("strategy_weights", {}).get("initial_weights", {})
        
        strategies = ["market_making", "momentum", "scalping", "arbitrage", "breakout", "sniping"]
        
        self.console.print("\n[bold]Poids actuels:[/bold]")
        for strat in strategies:
            current = weights.get(strat, 0.0)
            self.console.print(f"  {strat}: {current * 100:.1f}%")
        
        self.console.print("\n[bold]Modifier les poids (en pourcentage, total doit faire 100%):[/bold]")
        
        new_weights = {}
        total = 0.0
        for strat in strategies:
            current_pct = weights.get(strat, 0.0) * 100
            value = Prompt.ask(
                f"{strat} (%)",
                default=str(current_pct),
                show_default=True
            )
            try:
                pct = float(value)
                new_weights[strat] = pct / 100.0
                total += pct
            except ValueError:
                self.console.print(f"[red]Valeur invalide pour {strat}, ignorée[/red]")
        
        if abs(total - 100.0) > 0.1:
            self.console.print(f"[yellow]⚠ Total = {total:.1f}%, normalisation automatique...[/yellow]")
            # Normaliser
            for strat in new_weights:
                new_weights[strat] = new_weights[strat] / total
        
        if "strategy_weights" not in config:
            config["strategy_weights"] = {}
        config["strategy_weights"]["initial_weights"] = new_weights
        
        if Confirm.ask("\n[cyan]Sauvegarder les modifications?[/cyan]", default=True):
            self._save_yaml_config(config)

    def _config_risk(self) -> None:
        """Configure les paramètres de risque."""
        self.console.print(Panel("[cyan]Configuration des Paramètres de Risque[/cyan]", border_style="cyan"))
        
        config = self._load_yaml_config()
        risk = config.get("risk", {})
        
        max_position = Prompt.ask(
            "Max Position % (0.0-1.0)",
            default=str(risk.get("max_position_pct", 0.2)),
            show_default=True
        )
        try:
            risk["max_position_pct"] = float(max_position)
        except ValueError:
            self.console.print("[red]Valeur invalide[/red]")
            return
        
        max_drawdown = Prompt.ask(
            "Max Daily Drawdown %",
            default=str(risk.get("max_daily_drawdown_pct", 5.0)),
            show_default=True
        )
        try:
            risk["max_daily_drawdown_pct"] = float(max_drawdown)
        except ValueError:
            self.console.print("[red]Valeur invalide[/red]")
            return
        
        config["risk"] = risk
        
        if Confirm.ask("\n[cyan]Sauvegarder les modifications?[/cyan]", default=True):
            self._save_yaml_config(config)

    def _config_general(self) -> None:
        """Configure les paramètres généraux."""
        self.console.print(Panel("[cyan]Configuration Générale[/cyan]", border_style="cyan"))
        
        config = self._load_yaml_config()
        general = config.get("general", {})
        
        capital = Prompt.ask(
            "Capital initial (USD)",
            default=str(general.get("capital", 10000.0)),
            show_default=True
        )
        try:
            general["capital"] = float(capital)
        except ValueError:
            self.console.print("[red]Valeur invalide[/red]")
            return
        
        symbols_str = Prompt.ask(
            "Symboles (séparés par des virgules)",
            default=", ".join(general.get("symbols", ["BTC/USD:USD"])),
            show_default=True
        )
        general["symbols"] = [s.strip() for s in symbols_str.split(",")]
        
        timeframe = Prompt.ask(
            "Timeframe (1m, 5m, 15m, 1h, etc.)",
            default=general.get("timeframe", "1m"),
            show_default=True
        )
        general["timeframe"] = timeframe
        
        exchange_id = Prompt.ask(
            "Exchange ID (hyperliquid, binance, bybit, etc.)",
            default=general.get("exchange_id", "hyperliquid"),
            show_default=True
        )
        general["exchange_id"] = exchange_id
        
        market_type = Prompt.ask(
            "Market Type (spot, futures)",
            default=general.get("market_type", "futures"),
            show_default=True,
            choices=["spot", "futures"]
        )
        general["market_type"] = market_type
        
        config["general"] = general
        
        if Confirm.ask("\n[cyan]Sauvegarder les modifications?[/cyan]", default=True):
            self._save_yaml_config(config)

    def _config_broker(self) -> None:
        """Configure les paramètres du broker."""
        self.console.print(Panel("[cyan]Configuration du Broker[/cyan]", border_style="cyan"))
        
        config = self._load_yaml_config()
        broker = config.get("broker", {})
        
        fee_bps = Prompt.ask(
            "Fee (bps)",
            default=str(broker.get("fee_bps", 10.0)),
            show_default=True
        )
        try:
            broker["fee_bps"] = float(fee_bps)
        except ValueError:
            self.console.print("[red]Valeur invalide[/red]")
            return
        
        slippage_bps = Prompt.ask(
            "Slippage (bps)",
            default=str(broker.get("slippage_bps", 5.0)),
            show_default=True
        )
        try:
            broker["slippage_bps"] = float(slippage_bps)
        except ValueError:
            self.console.print("[red]Valeur invalide[/red]")
            return
        
        default_leverage = Prompt.ask(
            "Default Leverage",
            default=str(broker.get("default_leverage", 10)),
            show_default=True
        )
        try:
            broker["default_leverage"] = int(default_leverage)
        except ValueError:
            self.console.print("[red]Valeur invalide[/red]")
            return
        
        max_leverage = Prompt.ask(
            "Max Leverage",
            default=str(broker.get("max_leverage", 50)),
            show_default=True
        )
        try:
            broker["max_leverage"] = int(max_leverage)
        except ValueError:
            self.console.print("[red]Valeur invalide[/red]")
            return
        
        margin_mode = Prompt.ask(
            "Margin Mode (isolated, cross)",
            default=broker.get("margin_mode", "isolated"),
            show_default=True,
            choices=["isolated", "cross"]
        )
        broker["margin_mode"] = margin_mode
        
        config["broker"] = broker
        
        if Confirm.ask("\n[cyan]Sauvegarder les modifications?[/cyan]", default=True):
            self._save_yaml_config(config)

    def _config_llm(self) -> None:
        """Configure les paramètres LLM."""
        self.console.print(Panel("[cyan]Configuration LLM[/cyan]", border_style="cyan"))
        
        config = self._load_yaml_config()
        llm = config.get("llm", {})
        
        enabled = Confirm.ask(
            "LLM Enabled?",
            default=llm.get("enabled", True)
        )
        llm["enabled"] = enabled
        
        if enabled:
            decision_interval = Prompt.ask(
                "Decision Interval (seconds)",
                default=str(llm.get("decision_interval_sec", 90)),
                show_default=True
            )
            try:
                llm["decision_interval_sec"] = int(decision_interval)
            except ValueError:
                self.console.print("[red]Valeur invalide[/red]")
                return
            
            context_window = Prompt.ask(
                "Context Window (bars)",
                default=str(llm.get("context_window_bars", 30)),
                show_default=True
            )
            try:
                llm["context_window_bars"] = int(context_window)
            except ValueError:
                self.console.print("[red]Valeur invalide[/red]")
                return
            
            monthly_budget = Prompt.ask(
                "Monthly Budget (USD)",
                default=str(llm.get("monthly_budget_usd", 32.0)),
                show_default=True
            )
            try:
                llm["monthly_budget_usd"] = float(monthly_budget)
            except ValueError:
                self.console.print("[red]Valeur invalide[/red]")
                return
        
        config["llm"] = llm
        
        if Confirm.ask("\n[cyan]Sauvegarder les modifications?[/cyan]", default=True):
            self._save_yaml_config(config)

    def _config_hyperliquid(self) -> None:
        """Configure les paramètres Hyperliquid."""
        self.console.print(Panel("[cyan]Configuration Hyperliquid[/cyan]", border_style="cyan"))
        
        config = self._load_yaml_config()
        hyperliquid = config.get("hyperliquid", {})
        
        testnet = Confirm.ask(
            "Testnet Mode?",
            default=hyperliquid.get("testnet", True)
        )
        hyperliquid["testnet"] = testnet
        
        default_leverage = Prompt.ask(
            "Default Leverage",
            default=str(hyperliquid.get("default_leverage", 10)),
            show_default=True
        )
        try:
            hyperliquid["default_leverage"] = int(default_leverage)
        except ValueError:
            self.console.print("[red]Valeur invalide[/red]")
            return
        
        max_leverage = Prompt.ask(
            "Max Leverage",
            default=str(hyperliquid.get("max_leverage", 50)),
            show_default=True
        )
        try:
            hyperliquid["max_leverage"] = int(max_leverage)
        except ValueError:
            self.console.print("[red]Valeur invalide[/red]")
            return
        
        margin_mode = Prompt.ask(
            "Margin Mode (isolated, cross)",
            default=hyperliquid.get("margin_mode", "isolated"),
            show_default=True,
            choices=["isolated", "cross"]
        )
        hyperliquid["margin_mode"] = margin_mode
        
        config["hyperliquid"] = hyperliquid
        
        if Confirm.ask("\n[cyan]Sauvegarder les modifications?[/cyan]", default=True):
            self._save_yaml_config(config)

    def _config_strategies(self) -> None:
        """Configure les stratégies (placeholder pour l'instant)."""
        self.console.print(Panel("[cyan]Configuration des Stratégies[/cyan]", border_style="cyan"))
        self.console.print("[yellow]Cette fonctionnalité sera implémentée prochainement.[/yellow]")
        self.console.print("Pour l'instant, utilisez 'config weights' pour configurer les poids des stratégies.")

    def _show_config(self) -> None:
        """Affiche la configuration actuelle."""
        self.console.print(Panel("[cyan]Configuration Actuelle[/cyan]", border_style="cyan"))
        
        config = self._load_yaml_config()
        
        # Afficher les sections principales
        sections = ["general", "risk", "broker", "llm", "hyperliquid", "strategy_weights"]
        for section in sections:
            if section in config:
                self.console.print(f"\n[bold]{section}:[/bold]")
                self.console.print(yaml.dump({section: config[section]}, default_flow_style=False, allow_unicode=True))

    def _save_config(self) -> None:
        """Sauvegarde la configuration (alias pour compatibilité)."""
        self.console.print("[yellow]Utilisez les sous-menus pour sauvegarder automatiquement.[/yellow]")

