# Guide Complet : Configuration du Bot avec Bybit Testnet

Ce guide vous explique étape par étape comment configurer le bot pour utiliser le **vrai compte testnet de Bybit** au lieu de la simulation locale.

---

## 🎯 Avantages du Testnet Bybit

✅ **Plus réaliste** : Frais, slippage, liquidations réels
✅ **Validation API** : Test des APIs avant de passer en live  
✅ **Moins de bugs** : Pas d'erreurs de simulation
✅ **Gratuit** : 10,000 USDT de test toutes les 24h
✅ **Sécurisé** : Aucun risque, fonds virtuels uniquement

---

## 📋 Prérequis

1. **Compte email valide** (pour s'inscrire sur Bybit Testnet)
2. **Clé API DeepSeek** (optionnelle, pour l'IA)
3. **Python 3.8+** avec les dépendances installées

---

## 🔧 Étape 1 : Créer un Compte Bybit Testnet

### 1.1 Inscription

1. **Accédez au site testnet** : https://testnet.bybit.com/
2. **Cliquez sur "S'inscrire"** (ou "Sign Up")
3. **Remplissez le formulaire** :
   - Email valide
   - Mot de passe sécurisé
4. **Vérifiez votre email** : Un code de vérification vous sera envoyé
5. **Entrez le code** pour activer votre compte

### 1.2 Demande de Fonds de Test

Après connexion :

1. **Naviguez vers "Actifs"** (ou "Assets") dans le menu
2. **Cliquez sur "Aperçu des actifs"** (ou "Asset Overview")
3. **Cliquez sur "Demander des pièces de test"** (ou "Request Test Coins")
4. **Confirmez** dans la pop-up
5. **Vous recevrez immédiatement** :
   - **10,000 USDT**
   - **1 BTC**

> ⚠️ **Note** : Vous pouvez demander ces fonds **une fois toutes les 24 heures**.

---

## 🔑 Étape 2 : Créer des Clés API Testnet

### 2.1 Accès à la G是不可能的 API

1. **Connectez-vous** sur https://testnet.bybit.com/
2. **Allez dans "Gestion des API"** (ou "API Management")
   - Menu utilisateur (icône profil) → "API Management"

### 2.2 Création de la Clé API

1. **Cliquez sur "Créer une nouvelle clé API"** (ou "Create New API Key")
2. **Configurez la clé** :
   - **Nom** : Par exemple "CryptoBot-Testnet"
   - **Autorisations** :
     - ✅ **Lecture** (Read) - OBLIGATOIRE
     - ✅ **Trade** (Trading) - OBLIGATOIRE
     - ❌ **Retrait** (Withdraw) - NON nécessaire pour testnet
   - **Restrictions IP** :
     - Si vous avez une IP statique : Ajoutez-la
     - Sinon : Utilisez `0.0.0.0/0` (moins sécurisé mais OK pour testnet)

3. **Confirmez** la création
4. **⚠️ IMPORTANT** : Copiez immédiatement :
   - **API Key** (clé publique)
   - **Secret Key** (clé secrète)

> 🚨 **ATTENTION** : La clé secrète ne sera affichée **qu'une seule fois**. Sauvegardez-la dans un endroit sûr !

---

## 🔐 Étape 3 : Configuration des Variables d'Environnement

### 3.1 Créer/Modifier le fichier `.env`

Créez un fichier `.env` à la racine du projet (ou modifiez l'existant) :

```bash
# Clés API Bybit Testnet (OBLIGATOIRES pour utiliser le testnet)
EXCHANGE_API_KEY=votre_api_key_bybit_testnet
EXCHANGE_API_SECRET=votre_secret_key_bybit_testnet

# Clé API DeepSeek (OPTIONNELLE, mais recommandée pour l'IA)
LLM_API_KEY=sk-votre_cle_deepseek
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

### 3.2 Remplacer les Valeurs

- **`EXCHANGE_API_KEY`** : Votre API Key Bybit Testnet (de l'étape 2.2)
- **`EXCHANGE_API_SECRET`** : Votre Secret Key Bybit Testnet (de l'étape 2.2)
- **`LLM_API_KEY`** : Votre clé DeepSeek (si vous en avez une)

### 3.3 Sécurité

```bash
# Assurez-vous que .env est dans .gitignore
echo ".env" >> .gitignore
```

---

## ⚙️ Étape 4 : Configuration du Fichier Config

### 4.1 Modifier `configs/live.frugal.yaml`

Ouvrez `configs/live.frugal.yaml` et assurez-vous que :

```yaml
general:
  capital: 1000.0  # Ignoré si testnet (on utilise les fonds du testnet)
  market_type: futures
  exchange_id: bybit  # Bybit pour testnet

broker:
  testnet: true        # ✅ ACTIVER testnet
  place_on_testnet: true  # ✅ ACTIVER placement d'ordres sur testnet
  margin_mode: isolated
  default_leverage: 5
  max_leverage: 20
```

**Points clés** :
- ✅ `testnet: true` : Active le mode testnet pour les données
- ✅ `place_on_testnet: true` : **ACTIVE le placement réel d'ordres sur le testnet**
- `exchange_id: bybit` : Bybit pour la France

---

## 🚀 Étape 5 : Tester la Connexion

### 5.1 Vérification Basique

Testez que les clés API fonctionnent :

```bash
# Dans votre terminal
python3 -c "
import os
from dotenv import load_dotenv
import ccxt

load_dotenv()

api_key = os.getenv('EXCHANGE_API_KEY')
api_secret = os.getenv('EXCHANGE_API_SECRET')

ex = ccxt.bybit({
    'apiKey': api_key,
    'secret': api_secret,
    'enableRateLimit': True,
    'options': {'defaultType': 'future'}
})
ex.set_sandbox_mode(True)
ex.load_markets()

balance = ex.fetch_balance({'type': 'future'})
print(f'Balance USDT: {balance[\"USDT\"][\"total\"]}')
"
```

**Résultat attendu** : Vous devriez voir votre balance testnet (environ 10,000 USDT).

### 5.2 Si ça ne marche pas

**Erreur commune** : `authentication failed`
- Vérifiez que vos clés API sont correctes
- Vérifiez que vous avez activé les permissions "Read" et "Trade"
- Vérifiez que vous utilisez les clés **testnet** (pas celles du compte réel !)

---

## 🎮 Étape 6 : Lancer le Bot

### 6.1 Lancer avec Testnet

```bash
# Activer l'environnement virtuel (si vous en avez un)
source .venv/bin/activate  # Linux/Mac
# ou
.venv\Scripts\activate  # Windows

# Lancer le bot
python -m cryptobot.cli.live --config configs/live.frugal.yaml --provider ccxt
```

### 6.2 Ce que vous devriez voir

```
============================================================
CryptoBot Live Runner starting...
Config: configs/live.frugal.yaml
Provider: ccxt
Exchange: bybit
============================================================
USING REAL EXCHANGE TESTNET BROKER
Orders will be placed on exchange testnet (virtual funds)
============================================================
Connected to bybit testnet successfully
Loaded 500+ markets from bybit
```

### 6.3 Logs d'Ordres

Quand le bot trade, vous verrez :

```
OPEN/LONG +0.02 BTC @ 50000.00 lev=5
Order executed on testnet: buy 0.02 BTC/USDT (order_id: abc123)
```

---

## 📊 Étape 7 : Vérifier sur Bybit Testnet

### 7.1 Vérifier les Ordres

1. **Connectez-vous** sur https://testnet.bybit.com/
2. **Allez dans "Ordres"** (ou "Orders") → Futures
3. **Vous devriez voir** les ordres placés par le bot

### 7.2 Vérifier les Positions

1. **Allez dans "Positions"** → Futures
2. **Vous devriez voir** les positions ouvertes par le bot

### 7.3 Vérifier le Solde

1. **Allez dans "Actifs"** → Futures
2. **Vérifiez** que le solde change selon les trades

---

## 🔍 Vérifications et Troubleshooting

### Problème 1 : Le bot utilise toujours le paper broker

**Solution** :
- Vérifiez que `place_on_testnet: true` dans la config
- Vérifiez que `EXCHANGE_API_KEY` et `EXCHANGE_API_SECRET` sont dans `.env`
- Relancez le bot

### Problème 2 : Erreur "Insufficient balance"

**Solution** :
- Demandez de nouveaux fonds test (voir Étape 1.2)
- Attendez 24h si vous venez de les demander

### Problème 3 : Erreur "Invalid symbol"

**Solution** :
- Vérifiez que le symbole dans la config est correct (ex: `BTC/USDT`)
- Les symboles futures Bybit sont formatés comme `BTC/USDT:USDT`

 implicitement à corriger dans le code si nécessaire

### Problème 4 : Leverage non défini

**Solution** :
- Configurez le levier manuellement sur Bybit Testnet dans l'interface
- Ou vérifiez que le bot essaie de le définir (logs)

---

## 🎯 Différences : Paper Broker vs Testnet Broker

| Aspect | Paper Broker (simulation) | Testnet Broker (réel) |
|--------|---------------------------|----------------------|
| **Frais** | Simulés (~0.02%) | Réels de l'exchange |
| **Slippage** | Simulé | Réel selon liquidité |
| **Liquidations** | Simulées | Règles réelles Bybit |
| **Balance** | Capital config (`capital: 1000`) | Balance testnet (10k USDT) |
| **API** | Pas de connexion | Connexion réelle |
| **Validation** | Limité | Complète avant live |

---

## 📝 Checklist Finale

Avant de lancer en production, vérifiez :

- [ ] Compte Bybit Testnet créé
- [ ] Fonds test demandés (10k USDT)
- [ ] Clés API testnet créées et sauvegardées
- [ ] Variables d'environnement configurées (`.env`)
- [ ] `place_on_testnet: true` dans la config
- [ ] Connexion testée et fonctionnelle
- [ ] Bot lancé et ordres visibles sur testnet

---

## 🔒 Sécurité

**IMPORTANT** :
- ⚠️ Ne JAMAIS utiliser les clés API du compte réel sur testnet
- ⚠️ Ne JAMAIS commit le fichier `.env` sur Git
- ⚠️ Les clés testnet sont gratuites, mais protégez-les quand même

---

## 🚀 Prochaines Étapes

Une fois que tout fonctionne sur testnet :

1. **Testez pendant quelques jours** pour valider la stratégie
2. **Analysez les performances** (logs, dashboard)
3. **Ajustez les paramètres** si besoin
4. **Quand vous êtes prêt** : Préparer la migration vers live (connexion à un compte réel, avec très petite mise au départ)

---

## 📞 Support

Si vous rencontrez des problèmes :

1. Vérifiez les logs dans `logs/cryptobot.log`
2. Vérifiez la documentation Bybit : https://bybit-exchange.github.io/docs/
3. Vérifiez les issues GitHub si c'est un projet open source

---

**Bonne chance avec votre bot ! 🚀**

