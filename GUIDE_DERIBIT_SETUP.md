# Guide Pratique : Configurer Votre Bot pour Deribit

## 📝 Ce Guide Vous Explique

Comment adapter votre bot en **3 étapes simples** pour qu'il fonctionne avec Deribit (exchange qui accepte les Français).

---

## ✅ Étape 1 : Vérifier Que CCXT Supporte Deribit

**Ce que vous devez faire :**

1. Ouvrez un terminal dans votre projet
2. Tapez cette commande :

```bash
python -c "import ccxt; print('deribit' in dir(ccxt))"
```

**Résultat attendu :** `True`

Si ça dit `True`, c'est bon ! Votre version de CCXT supporte Deribit.

**Si ça dit `False` ou une erreur :**

Mettez à jour CCXT :

```bash
pip install --upgrade ccxt
```

---

## ✅ Étape 2 : Créer Un Fichier de Configuration pour Deribit

**Ce que vous devez faire :**

1. Ouvrez le fichier `configs/live.deribit.yaml` (je vais le créer pour vous)
2. Copiez votre clé API Deribit et votre secret API
3. Mettez-les dans votre fichier `.env`

**Le fichier de config que je vais créer pour vous :**

```yaml
general:
  seed: 42
  start: "2024-01-01"
  end: "2030-01-01"
  timeframe: "1m"
  capital: 100.0  # Commencez petit pour tester (100€)
  symbols: ["BTC-PERPETUAL"]  # ⚠️ IMPORTANT : Format Deribit
  market_type: futures
  exchange_id: deribit  # ⚠️ CHANGE ICI : "deribit" au lieu de "bybit"

data:
  provider: ccxt
  steps_per_bar: 20
  drift: 0.0
  volatility: 0.02

broker:
  fee_bps: 2           # Deribit : ~0.02% taker fee
  slippage_bps: 5
  testnet: false       # ⚠️ IMPORTANT : false = compte réel (pas de testnet Deribit pour futures)
  margin_mode: isolated
  default_leverage: 5
  max_leverage: 10     # Deribit : jusqu'à 100x pour BTC, mettez ce que vous voulez
  place_on_testnet: false  # ⚠️ false = ordres réels (mettez true seulement si vous voulez tester)

risk:
  max_position_pct: 1.0
  max_daily_drawdown_pct: 5

strategy:
  name: nof1_baseline
  params:
    rsi_period: 14
    rsi_buy: 30
    rsi_sell: 70
    ema_fast: 12
    ema_slow: 26
    atr_period: 14
    volatility_floor: 0.002

ensemble:
  weights:
    llm: 1.5
    nof1_baseline: 0.5
  llm_overlay:
    enabled: true

backtest:
  report:
    output_dir: logs/reports
```

**Les 3 changements importants :**

1. ✅ `exchange_id: deribit` (au lieu de `bybit`)
2. ✅ `symbols: ["BTC-PERPETUAL"]` (au lieu de `["BTC/USDT"]`)
3. ✅ `testnet: false` (Deribit n'a pas de testnet pour les futures réels)

---

## ✅ Étape 3 : Configurer Vos Clés API Deribit

**Ce que vous devez faire :**

1. **Ouvrez votre fichier `.env`** (ou créez-le à la racine du projet)

2. **Ajoutez ces lignes :**

```bash
# Deribit API Keys (à remplir avec VOS vraies clés)
EXCHANGE_API_KEY=votre_cle_api_deribit
EXCHANGE_API_SECRET=votre_secret_api_deribit

# DeepSeek (optionnel, si vous utilisez l'IA)
LLM_API_KEY=votre_cle_deepseek
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

3. **Remplissez avec vos vraies clés Deribit :**
   - Allez sur Deribit → Account → API
   - Copiez votre "API Key" → collez-la après `EXCHANGE_API_KEY=`
   - Copiez votre "API Secret" → collez-la après `EXCHANGE_API_SECRET=`

**⚠️ IMPORTANT : Sécurité**

- Ne partagez JAMAIS vos clés API
- Ne mettez JAMAIS vos clés dans Git (le fichier `.env` doit être dans `.gitignore`)
- Activez la restriction d'IP sur Deribit (mettez l'IP de votre VPS)

---

## ✅ Étape 4 : Tester Que Ça Marche

**Ce que vous devez faire :**

1. **Testez d'abord en lecture seule (pas d'ordres) :**

Modifiez temporairement `configs/live.deribit.yaml` :

```yaml
broker:
  place_on_testnet: false  # Pas d'ordres pour l'instant
```

2. **Lancez le bot en mode "data only" (juste pour voir si la connexion fonctionne) :**

```bash
python -m cryptobot.cli.live --config configs/live.deribit.yaml --provider ccxt
```

**Ce que vous devez voir :**
- ✅ Pas d'erreur de connexion
- ✅ Le bot récupère des données de prix
- ✅ Les logs montrent "Loaded X markets from deribit"

**Si vous voyez des erreurs :**
- ❌ "Invalid API key" → Vérifiez vos clés dans `.env`
- ❌ "Symbol not found" → Vérifiez que le symbole est bien `BTC-PERPETUAL` (avec tiret)
- ❌ "Connection error" → Vérifiez votre connexion internet

3. **Une fois que ça marche, testez avec de petits ordres :**

Modifiez `configs/live.deribit.yaml` :

```yaml
broker:
  place_on_testnet: false  # Ordres réels activés
```

**⚠️ ATTENTION :** Commencez avec très peu d'argent (50-100€) pour tester !

---

## 📋 Liste des Symboles Deribit

**Pour Bitcoin :**
- `BTC-PERPETUAL` (perpetual futures)
- `BTC-USD` (futures avec échéance)

**Pour Ethereum :**
- `ETH-PERPETUAL` (perpetual futures)
- `ETH-USD` (futures avec échéance)

**Dans votre config, utilisez :**

```yaml
symbols: ["BTC-PERPETUAL"]  # Bitcoin perpetual
# OU
symbols: ["ETH-PERPETUAL"]  # Ethereum perpetual
# OU les deux
symbols: ["BTC-PERPETUAL", "ETH-PERPETUAL"]
```

---

## 🔧 Résolution de Problèmes

### Problème 1 : "Symbol not found" ou "Invalid symbol"

**Cause :** Format du symbole incorrect

**Solution :** 
- Deribit utilise `BTC-PERPETUAL` (avec tiret)
- PAS `BTC/USDT` ou `BTCUSDT`
- Vérifiez votre config : `symbols: ["BTC-PERPETUAL"]`

### Problème 2 : "Invalid API key" ou "Unauthorized"

**Cause :** Clés API incorrectes ou non configurées

**Solution :**
1. Vérifiez que vos clés sont dans le fichier `.env`
2. Vérifiez que vous avez bien copié-collé sans espaces
3. Vérifiez sur Deribit que votre clé API est active
4. Vérifiez que les permissions "Trade" et "Read" sont activées

### Problème 3 : "Insufficient balance"

**Cause :** Pas assez d'argent sur votre compte Deribit

**Solution :**
1. Allez sur Deribit → Wallet
2. Déposez de l'argent (Bitcoin ou Ethereum, ou Euros via SEPA)
3. Vérifiez que vous avez assez de marge pour ouvrir une position

### Problème 4 : Le bot ne passe pas d'ordres

**Cause :** Le mode testnet ou les permissions API

**Solution :**
1. Vérifiez `place_on_testnet: false` (pour ordres réels)
2. Vérifiez que votre clé API a la permission "Trade" activée
3. Vérifiez que vous avez assez de marge

### Problème 5 : Erreur "IP not whitelisted"

**Cause :** Vous avez activé la restriction d'IP sur Deribit mais votre IP n'est pas autorisée

**Solution :**
1. Allez sur Deribit → Account → API → Votre clé API
2. Ajoutez l'IP de votre VPS dans la liste blanche
3. **OU** désactivez temporairement la restriction d'IP (moins sûr)

---

## 🎯 Checklist Avant de Lancer en Réel

- [ ] J'ai créé un compte Deribit
- [ ] J'ai fait la vérification KYC (identité vérifiée)
- [ ] J'ai déposé de l'argent sur Deribit (commencez petit : 50-100€)
- [ ] J'ai créé une clé API avec permissions "Trade" et "Read"
- [ ] J'ai mis mes clés API dans le fichier `.env`
- [ ] J'ai créé le fichier `configs/live.deribit.yaml` avec les bons symboles
- [ ] J'ai testé la connexion en mode lecture seule (ça marche)
- [ ] J'ai vérifié que j'ai assez de marge pour trader
- [ ] J'ai activé la restriction d'IP sur Deribit (sécurité)
- [ ] Je suis prêt à surveiller le bot au début (regardez les logs)

---

## 🚀 Lancement Final

**Quand tout est prêt :**

```bash
python -m cryptobot.cli.live --config configs/live.deribit.yaml --provider ccxt
```

**Ce que vous devez voir :**
- ✅ Connexion réussie à Deribit
- ✅ Récupération des données de prix en temps réel
- ✅ Le bot prend des décisions et passe des ordres
- ✅ Les logs montrent les transactions

**Surveillez régulièrement :**
- Les logs du bot (`logs/cryptobot.log`)
- Votre compte Deribit pour voir les positions ouvertes
- Votre équity (valeur totale) pour voir si ça monte ou descend

---

## 💡 Conseils

1. **Commencez petit :** 50-100€ pour tester, augmentez progressivement
2. **Surveillez au début :** Regardez les logs quotidiennement les premiers jours
3. **Gérez vos risques :** Ne tradez jamais plus que ce que vous pouvez perdre
4. **Testez d'abord :** Laissez tourner quelques heures avec très peu d'argent avant d'augmenter

---

## ❓ Questions ?

Si vous avez des problèmes :
1. Regardez les logs : `tail -f logs/cryptobot.log`
2. Vérifiez la checklist ci-dessus
3. Testez étape par étape (connexion d'abord, puis ordres)

**Prêt à commencer ?** Suivez les étapes une par une !

