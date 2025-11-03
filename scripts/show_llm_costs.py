#!/usr/bin/env python3
"""
Script pour afficher les statistiques de coûts LLM du bot.

Usage:
    python scripts/show_llm_costs.py
    python scripts/show_llm_costs.py --reset  # Reset les compteurs
"""

import argparse
import sys
from pathlib import Path

# Ajouter le répertoire parent au path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cryptobot.llm.client import LLMClient


def format_currency(amount: float) -> str:
    """Format un montant en USD."""
    if amount < 0.01:
        return f"${amount:.6f}"
    return f"${amount:.2f}"


def print_stats(stats: dict) -> None:
    """Affiche les statistiques de coûts de manière lisible."""
    print("\n" + "=" * 70)
    print("📊 STATISTIQUES DE COÛTS LLM (DeepSeek API)")
    print("=" * 70)
    
    print(f"\n💰 Coûts Totaux:")
    print(f"  • Coût total cumulé : {format_currency(stats['total_cost_usd'])}")
    print(f"  • Coût par heure     : {format_currency(stats['cost_per_hour'])}")
    print(f"  • Estimation/jour    : {format_currency(stats['estimated_daily_cost'])}")
    print(f"  • Estimation/mois    : {format_currency(stats['estimated_monthly_cost'])}")
    
    print(f"\n📞 Appels API:")
    print(f"  • Total appels       : {stats['total_calls']:,}")
    print(f"  • Appels par heure   : {stats['calls_per_hour']:.2f}")
    print(f"  • Cache hit rate     : {stats['cache_hit_rate']*100:.1f}%")
    
    print(f"\n🔢 Tokens:")
    print(f"  • Tokens entrée      : {stats['total_tokens_input']:,}")
    print(f"  • Tokens sortie      : {stats['total_tokens_output']:,}")
    print(f"  • Tokens totaux      : {stats['total_tokens_input'] + stats['total_tokens_output']:,}")
    
    if stats['calls_by_type']:
        print(f"\n📊 Appels par Type:")
        for call_type, count in sorted(stats['calls_by_type'].items(), key=lambda x: x[1], reverse=True):
            cost = stats['costs_by_type'].get(call_type, 0.0)
            pct = (count / stats['total_calls'] * 100) if stats['total_calls'] > 0 else 0.0
            print(f"  • {call_type:20s} : {count:6,} appels ({pct:5.1f}%) - {format_currency(cost)}")
    
    if stats['costs_by_type']:
        print(f"\n💵 Coûts par Type:")
        for call_type, cost in sorted(stats['costs_by_type'].items(), key=lambda x: x[1], reverse=True):
            pct = (cost / stats['total_cost_usd'] * 100) if stats['total_cost_usd'] > 0 else 0.0
            print(f"  • {call_type:20s} : {format_currency(cost)} ({pct:5.1f}%)")
    
    print("\n" + "=" * 70)
    print("💡 Pour réinitialiser les compteurs: python scripts/show_llm_costs.py --reset")
    print("=" * 70 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Affiche les statistiques de coûts LLM")
    parser.add_argument("--reset", action="store_true", help="Réinitialise les compteurs de coûts")
    args = parser.parse_args()
    
    # Créer un client LLM (peut être vide, juste pour accéder au tracker)
    client = LLMClient.from_env()
    
    if args.reset:
        client._cost_tracker.reset()
        print("✅ Compteurs de coûts réinitialisés")
        return
    
    stats = client._cost_tracker.get_stats()
    
    if stats['total_calls'] == 0:
        print("\n⚠️  Aucun appel LLM enregistré pour le moment.")
        print("   Lancez le bot pour commencer à tracker les coûts.\n")
        return
    
    print_stats(stats)


if __name__ == "__main__":
    main()

