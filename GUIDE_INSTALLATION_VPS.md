# Guide d'Installation et Lancement sur VPS Linux

Guide rapide de A à Z pour installer et lancer CryptoBot sur un VPS Linux.

## Prérequis

- Un VPS Linux (Ubuntu/Debian recommandé)
- Accès SSH au VPS
- Clés API (optionnel selon le mode)

---

## Installation Rapide (Méthode Automatique)

### 1. Se connecter au VPS

```bash
ssh user@votre-vps-ip
```

### 2. Télécharger et exécuter le script d'installation

**Option A : Télécharger le script depuis GitHub (recommandé)**

```bash
# Télécharger le script directement
curl -o setup_vps.sh https://raw.githubusercontent.com/jossdip/CryptoBot/main/deploy/setup_vps.sh

# Rendre exécutable
chmod +x setup_vps.sh

# Exécuter avec votre URL de repo Git (HTTPS par défaut, plus simple)
./setup_vps.sh https://github.com/jossdip/CryptoBot.git main

# OU si vous avez configuré SSH :
# ./setup_vps.sh git@github.com:jossdip/CryptoBot.git main
```

### 3. Lancer l'interface interactive (recommandé)

```bash
cd ~/CryptoBot
source .venv/bin/activate

# Lancer l'interface CLI personnalisée
cryptobot
# ou
cb
```

Dans l'interface, vous pouvez utiliser par exemple :

```bash
[CryptoBot@Hyperliquid:STOPPED] > start --config configs/live.hyperliquid.yaml
[CryptoBot@Hyperliquid:ACTIVE] > monitor --trades 20 --refresh 3 --insights --live
[CryptoBot@Hyperliquid:ACTIVE] > trades --limit 10
[CryptoBot@Hyperliquid:ACTIVE] > portfolio
[CryptoBot@Hyperliquid:ACTIVE] > performance --period 24h
```

Si la commande `cryptobot` n'est pas trouvée, assurez-vous que l'environnement virtuel est activé et installez les entrypoints:

```bash
pip install -e .
```

**Option B : Installation manuelle (si vous préférez)**

```bash
# 1. Installer les dépendances système
sudo apt update
sudo apt -y upgrade
sudo apt -y install git python3 python3-venv python3-pip

# 2. Cloner le repo (HTTPS par défaut, plus simple)
cd ~
git clone https://github.com/jossdip/CryptoBot.git
cd CryptoBot
git checkout main

# OU si vous avez configuré SSH :
# git clone git@github.com:jossdip/CryptoBot.git

# 3. Créer l'environnement virtuel
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt

# 4. Créer le fichier .env
cp env.example .env
nano .env  # Remplir vos clés
```

Le script fait automatiquement :
- ✅ Installation de Python 3, pip, venv, git
- ✅ Clonage du repo
- ✅ Création de l'environnement virtuel
- ✅ Installation des dépendances
- ✅ Création du fichier `.env` (à remplir ensuite)

### 4. Configurer les variables d'environnement

```bash
cd ~/CryptoBot
nano .env  # ou vi .env
```

Remplissez au minimum :
- `LLM_API_KEY` (si vous utilisez DeepSeek)
- `EXCHANGE_API_KEY` et `EXCHANGE_API_SECRET` (si vous tradez en live)
- `HYPERLIQUID_*` (si vous utilisez Hyperliquid)

**Exemple minimal pour paper trading :**
```bash
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
LLM_API_KEY=votre_cle_deepseek
```

---

## 🔐 Configuration Complète du .env pour Hyperliquid Testnet

### Explication : Pourquoi DeepSeek est utilisé sans lancer le bot ?

**⚠️ IMPORTANT :** Si vous avez mis votre clé DeepSeek dans le `.env` hier soir et que vous voyez déjà **une centaine de requêtes API** alors que vous n'avez pas lancé le bot, voici les causes possibles :

#### 🔍 Causes Probables (par ordre de probabilité)

1. **Un service systemd tourne en arrière-plan** (le plus probable)
   - Si vous avez installé le service systemd, il peut tourner automatiquement
   - Le bot peut redémarrer automatiquement après un crash
   - Vérifiez avec : `sudo systemctl status cryptobot-*`

2. **Un processus Python orphelin**
   - Un ancien lancement du bot qui n'a pas été arrêté proprement
   - Un processus qui tourne dans un screen/tmux que vous avez oublié

3. **Des tests ou scripts lancés par erreur**
   - Quelqu'un a lancé un test ou un script qui utilise la clé
   - Un cron job ou un script automatique

4. **Le bot a été lancé puis arrêté rapidement**
   - Vous avez peut-être lancé le bot pour tester puis oublié
   - Le bot a fait quelques cycles avant d'être arrêté

#### ✅ Comment Vérifier et Arrêter

**Sur votre VPS, exécutez ces commandes :**

```bash
# 1. Vérifier tous les processus Python qui tournent
ps aux | grep python | grep -v grep

# 2. Vérifier spécifiquement les processus cryptobot
ps aux | grep cryptobot | grep -v grep

# 3. Vérifier les services systemd actifs
sudo systemctl list-units --type=service | grep cryptobot

# 4. Vérifier le statut de chaque service cryptobot
sudo systemctl status cryptobot-paper@$(whoami) 2>/dev/null || echo "Service paper non trouvé"
sudo systemctl status cryptobot-live@$(whoami) 2>/dev/null || echo "Service live non trouvé"
sudo systemctl status cryptobot-hyperliquid@$(whoami) 2>/dev/null || echo "Service hyperliquid non trouvé"

# 5. Vérifier les sessions screen/tmux
screen -ls 2>/dev/null || echo "Aucune session screen"
tmux ls 2>/dev/null || echo "Aucune session tmux"
```

#### 🛑 Comment Arrêter Tout Processus Actif

```bash
# Arrêter tous les services systemd cryptobot
sudo systemctl stop cryptobot-paper@$(whoami) 2>/dev/null
sudo systemctl stop cryptobot-live@$(whoami) 2>/dev/null
sudo systemctl stop cryptobot-hyperliquid@$(whoami) 2>/dev/null

# Tuer tous les processus Python cryptobot (si nécessaire)
pkill -f "cryptobot" || echo "Aucun processus cryptobot trouvé"

# Vérifier qu'il n'y a plus rien qui tourne
ps aux | grep -E "(cryptobot|python.*cryptobot)" | grep -v grep || echo "✅ Aucun processus actif"
```

#### 🔒 Comment Éviter que ça se Reproduise

1. **Ne mettez la clé DeepSeek dans le `.env` que quand vous êtes prêt à lancer le bot**
2. **Vérifiez toujours qu'aucun processus ne tourne avant de mettre la clé**
3. **Utilisez un budget mensuel** dans la config YAML pour limiter les coûts :
   ```yaml
   llm:
     monthly_budget_usd: 32.0  # Arrête le bot si budget dépassé
   ```
4. **Surveillez les coûts régulièrement** :
   ```bash
   python scripts/show_llm_costs.py  # Affiche les stats de coûts
   ```

#### 📊 Vérifier les Coûts Actuels

```bash
# Sur votre VPS, vérifier les coûts LLM
cd ~/CryptoBot
source .venv/bin/activate
python scripts/show_llm_costs.py
```

Cela vous montrera :
- Le nombre total d'appels API
- Le coût total
- Les appels par type
- Une estimation mensuelle

---

### Configuration Complète pour Hyperliquid Testnet

Voici **exactement** ce que vous devez mettre dans votre fichier `.env` sur le VPS pour lancer le bot sur le **testnet Hyperliquid** :

```bash
# ============================================
# DEEPSEEK LLM (OBLIGATOIRE pour le bot)
# ============================================
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
LLM_API_KEY=sk-votre_cle_deepseek_ici

# Limites de coût (optionnel mais recommandé)
LLM_MIN_COOLDOWN_SEC=300
LLM_MIN_ATR_RATIO=0.0015

# ============================================
# HYPERLIQUID TESTNET (OBLIGATOIRE)
# ============================================
# Votre adresse wallet (la même pour testnet et mainnet)
HYPERLIQUID_WALLET_ADDRESS=0xVotreAdresseWalletIci

# Clé privée TESTNET (pour tester sans risque)
HYPERLIQUID_TESTNET_PRIVATE_KEY=0xVotreClePriveeTestnetIci

# ⚠️ NE PAS REMPLIR pour le testnet :
# HYPERLIQUID_LIVE_PRIVATE_KEY=  # LAISSEZ VIDE pour testnet !

# URLs (optionnel, valeurs par défaut déjà correctes)
HYPERLIQUID_TESTNET_URL=https://api.hyperliquid-testnet.xyz
HYPERLIQUID_LIVE_URL=https://api.hyperliquid.xyz

# ============================================
# AUTRES EXCHANGES (OPTIONNEL)
# ============================================
# Pour arbitrage entre exchanges (optionnel)
EXCHANGE_API_KEY=
EXCHANGE_API_SECRET=
```

### 📝 Explication de Chaque Variable

| Variable | Description | Où la trouver ? |
|----------|-------------|-----------------|
| `LLM_API_KEY` | Clé API DeepSeek (obligatoire) | Sur https://platform.deepseek.com/ |
| `HYPERLIQUID_WALLET_ADDRESS` | Adresse de votre wallet (même pour testnet/mainnet) | Dans votre wallet MetaMask ou autre |
| `HYPERLIQUID_TESTNET_PRIVATE_KEY` | Clé privée pour le **testnet uniquement** | Export depuis votre wallet testnet |
| `HYPERLIQUID_LIVE_PRIVATE_KEY` | Clé privée pour le **mainnet** (⚠️ NE PAS REMPLIR pour testnet) | Export depuis votre wallet mainnet |

### 🔑 Comment Obtenir Vos Clés Hyperliquid

#### 1. Adresse Wallet (`HYPERLIQUID_WALLET_ADDRESS`)
- C'est votre adresse Ethereum (commence par `0x`)
- La même pour testnet et mainnet
- Exemple : `0x1234567890abcdef1234567890abcdef12345678`

#### 2. Clé Privée Testnet (`HYPERLIQUID_TESTNET_PRIVATE_KEY`)
- **Pour le testnet** : Créez un wallet de test ou utilisez un wallet existant
- Exportez la clé privée depuis MetaMask ou votre wallet
- Format : `0x` suivi de 64 caractères hexadécimaux
- Exemple : `0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890`

#### 3. Clé Privée Mainnet (`HYPERLIQUID_LIVE_PRIVATE_KEY`)
- **⚠️ NE PAS REMPLIR si vous testez sur testnet !**
- Laissez cette ligne vide ou commentez-la
- Ne la remplissez que quand vous passerez en mode live/mainnet

### ✅ Vérification de la Configuration

Après avoir rempli votre `.env`, vérifiez que tout est correct :

```bash
# Sur votre VPS, vérifier le contenu du .env
cd ~/CryptoBot
cat .env | grep -v "^#" | grep -v "^$"  # Affiche seulement les lignes non-vides et non-commentées

# Vérifier que les variables sont bien chargées
source .venv/bin/activate
python3 -c "import os; from dotenv import load_dotenv; load_dotenv(); print('LLM_API_KEY:', 'OK' if os.getenv('LLM_API_KEY') else 'MANQUANT'); print('HYPERLIQUID_WALLET_ADDRESS:', 'OK' if os.getenv('HYPERLIQUID_WALLET_ADDRESS') else 'MANQUANT'); print('HYPERLIQUID_TESTNET_PRIVATE_KEY:', 'OK' if os.getenv('HYPERLIQUID_TESTNET_PRIVATE_KEY') else 'MANQUANT')"
```

### 🚀 Lancer le Bot sur Testnet Hyperliquid

Une fois le `.env` configuré, lancez le bot avec :

```bash
cd ~/CryptoBot
source .venv/bin/activate

# Utiliser la config testnet optimisée
python -m cryptobot.cli.live_hyperliquid --config configs/live.hyperliquid.testnet.optimized.yaml

# OU utiliser la config standard (vérifiez que testnet: true est dans le YAML)
python -m cryptobot.cli.live_hyperliquid --config configs/live.hyperliquid.yaml
```

**Important :** Vérifiez que dans votre fichier YAML (`configs/live.hyperliquid.yaml`), vous avez :
```yaml
hyperliquid:
  testnet: true  # ✅ Doit être true pour testnet
```

### 🔄 Passer du Testnet au Mainnet

Quand vous serez prêt pour le mainnet :

1. **Modifiez le `.env`** :
   ```bash
   # Commentez ou supprimez la ligne testnet
   # HYPERLIQUID_TESTNET_PRIVATE_KEY=0x...  # NE PLUS UTILISER
   
   # Décommentez et remplissez la ligne mainnet
   HYPERLIQUID_LIVE_PRIVATE_KEY=0xVotreClePriveeMainnetIci
   ```

2. **Modifiez le fichier YAML** :
   ```yaml
   hyperliquid:
     testnet: false  # ✅ Passer à false pour mainnet
   ```

3. **Relancez le bot** avec la même commande

---

### ⚠️ Sécurité : Ne Jamais Committer le .env

```bash
# Vérifier que .env est dans .gitignore
grep "^\.env$" .gitignore || echo ".env" >> .gitignore

# Vérifier qu'il n'est pas suivi par Git
git check-ignore .env && echo "✅ .env est ignoré par Git" || echo "❌ .env n'est PAS ignoré !"
```

### 4. Installer le service systemd (recommandé)

```bash
cd ~/CryptoBot

# Pour le mode paper (recommandé pour débuter)
sudo ./deploy/install_service.sh paper

# OU pour le mode live
sudo ./deploy/install_service.sh live
```

Le service démarre automatiquement et redémarre en cas de crash.

### 5. Vérifier que le bot tourne

```bash
# Voir les logs en temps réel
sudo journalctl -u cryptobot-paper@$(whoami) -f

# Voir le statut
sudo systemctl status cryptobot-paper@$(whoami)
```

---

## Installation Manuelle (Méthode Alternative)

Si vous préférez faire tout manuellement :

### 1. Installer les dépendances système

```bash
sudo apt update
sudo apt -y upgrade
sudo apt -y install git python3 python3-venv python3-pip
```

### 2. Cloner le projet

```bash
cd ~
git clone https://github.com/votre-username/CryptoBot.git
cd CryptoBot
git checkout main
```

### 3. Créer l'environnement virtuel

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
pip install -e .  # installe la commande 'cryptobot' / 'cb'
```

### 4. Configurer l'environnement

```bash
# Copier le fichier d'exemple
cp env.example .env

# Éditer avec vos clés
nano .env
```

### 5. Lancer le bot

#### Option A : Mode Paper (recommandé pour débuter)

```bash
source .venv/bin/activate
python -m cryptobot.cli.live --config configs/live.deepseek.paper.yaml --provider random
```

#### Option B : Mode Live (avec clés exchange)

```bash
source .venv/bin/activate
python -m cryptobot.cli.live --config configs/live.frugal.yaml --provider ccxt
```

#### Option C : Avec Hyperliquid

```bash
source .venv/bin/activate
python -m cryptobot.cli.live_hyperliquid --config configs/live.hyperliquid.yaml
```

#### Option D : Interface interactive (recommandé)

```bash
source .venv/bin/activate
pip install -e .  # s'assure que les entrypoints CLI sont installés
cryptobot
# ou
cb

# Exemples dans l'interface
[CryptoBot@Hyperliquid:STOPPED] > start --config configs/live.hyperliquid.yaml
[CryptoBot@Hyperliquid:ACTIVE] > monitor --trades 20 --refresh 3 --insights --live
```

---

## Gestion du Service Systemd

### Commandes utiles

```bash
# Démarrer le service
sudo systemctl start cryptobot-paper@$(whoami)

# Arrêter le service
sudo systemctl stop cryptobot-paper@$(whoami)

# Redémarrer le service
sudo systemctl restart cryptobot-paper@$(whoami)

# Voir le statut
sudo systemctl status cryptobot-paper@$(whoami)

# Voir les logs
sudo journalctl -u cryptobot-paper@$(whoami) -f

# Désactiver le démarrage automatique
sudo systemctl disable cryptobot-paper@$(whoami)

# Activer le démarrage automatique
sudo systemctl enable cryptobot-paper@$(whoami)
```

### Mettre à jour le bot

```bash
cd ~/CryptoBot
./deploy/update.sh paper  # ou 'live' selon votre service
```

Ce script :
- ✅ Met à jour le code depuis Git
- ✅ Installe les nouvelles dépendances
- ✅ Redémarre le service

---

## Configuration des Fichiers

### Choix de la configuration

Le bot utilise des fichiers YAML dans `configs/` :

- **`live.deepseek.paper.yaml`** → Mode paper avec LLM (DeepSeek)
- **`live.frugal.yaml`** → Mode live frugal (20 USDT, futures)
- **`live.hyperliquid.yaml`** → Mode live avec Hyperliquid
- **`live.deribit.yaml`** → Mode live avec Deribit (pour les Français)

### Personnaliser la configuration

```bash
# Copier un fichier de config existant
cp configs/live.frugal.yaml configs/mon-config.yaml

# Éditer selon vos besoins
nano configs/mon-config.yaml
```

**Important :** Les clés API ne doivent JAMAIS être dans les fichiers YAML. Elles doivent être uniquement dans `.env`.

---

## Dépannage

### Erreur "Permission denied (publickey)" lors du clone Git

**Problème :** Vous essayez de cloner avec SSH (`git@github.com:...`) mais votre VPS n'a pas de clé SSH configurée.

**Solution :** Utilisez HTTPS à la place (plus simple, pas besoin de configuration) :

```bash
# Utilisez HTTPS au lieu de SSH
git clone https://github.com/jossdip/CryptoBot.git

# OU dans le script setup_vps.sh
./setup_vps.sh https://github.com/jossdip/CryptoBot.git main
```

**Optionnel :** Si vous voulez configurer SSH (plus pratique à long terme) :

```bash
# 1. Générer une clé SSH sur votre VPS
ssh-keygen -t ed25519 -C "vps-cryptobot"
# Appuyez sur Entrée pour accepter les valeurs par défaut

# 2. Afficher la clé publique
cat ~/.ssh/id_ed25519.pub

# 3. Copier cette clé et l'ajouter sur GitHub :
#    - Allez sur https://github.com/settings/keys
#    - Cliquez "New SSH key"
#    - Collez la clé et sauvegardez

# 4. Maintenant vous pouvez utiliser SSH
git clone git@github.com:jossdip/CryptoBot.git
```

### Erreur "No such file or directory" pour deploy/setup_vps.sh

**Problème :** Vous essayez d'exécuter `./deploy/setup_vps.sh` mais le fichier n'existe pas encore sur le VPS.

**Solution :** Utilisez l'une des méthodes suivantes :

**Méthode 1 : Télécharger le script depuis GitHub (HTTPS)**
```bash
curl -o setup_vps.sh https://raw.githubusercontent.com/jossdip/CryptoBot/main/deploy/setup_vps.sh
chmod +x setup_vps.sh
./setup_vps.sh https://github.com/jossdip/CryptoBot.git main
```

**Méthode 2 : Installation manuelle complète (HTTPS)**
```bash
# Installer les dépendances
sudo apt update && sudo apt -y install git python3 python3-venv python3-pip

# Cloner le repo avec HTTPS (plus simple, pas besoin de clé SSH)
cd ~
git clone https://github.com/jossdip/CryptoBot.git
cd CryptoBot

# Installer Python
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt

# Créer .env
cp env.example .env
nano .env  # Remplir vos clés
```

### Le bot ne démarre pas

```bash
# Vérifier les logs
sudo journalctl -u cryptobot-paper@$(whoami) -n 50

# Vérifier que le .env existe et est correct
cat ~/CryptoBot/.env

# Tester manuellement
cd ~/CryptoBot
source .venv/bin/activate
python -m cryptobot.cli.live --config configs/live.deepseek.paper.yaml --provider random
```

### Erreur de permissions

```bash
# S'assurer que les scripts sont exécutables
chmod +x deploy/*.sh
chmod +x scripts/*.sh
```

### Le service ne démarre pas automatiquement

```bash
# Vérifier que le service est activé
sudo systemctl is-enabled cryptobot-paper@$(whoami)

# Si non, activer
sudo systemctl enable cryptobot-paper@$(whoami)
```

### Problème de connexion API

- Vérifiez que vos clés API sont correctes dans `.env`
- Vérifiez que les variables d'environnement sont bien chargées
- Testez la connexion manuellement avant de lancer le service

---

## Résumé Ultra-Rapide

```bash
# 1. Se connecter au VPS
ssh user@vps-ip

# 2. Télécharger et installer (automatique - HTTPS, pas besoin de clé SSH)
curl -o setup_vps.sh https://raw.githubusercontent.com/jossdip/CryptoBot/main/deploy/setup_vps.sh
chmod +x setup_vps.sh
./setup_vps.sh https://github.com/jossdip/CryptoBot.git main

# 3. Configurer vos clés
nano ~/CryptoBot/.env  # Remplir vos clés

# 4. Lancer l'interface interactive
cd ~/CryptoBot && source .venv/bin/activate
cryptobot  # ou 'cb'

# 5. Installer le service systemd (optionnel)
cd ~/CryptoBot
sudo ./deploy/install_service.sh paper

# 6. Vérifier que ça tourne
sudo journalctl -u cryptobot-paper@$(whoami) -f
```

**C'est tout ! Le bot tourne maintenant en arrière-plan et redémarre automatiquement.**

**Note :** Utilisez HTTPS (`https://github.com/...`) au lieu de SSH (`git@github.com:...`) si vous n'avez pas configuré de clé SSH sur votre VPS.

---

## Support

Pour plus d'informations :
- `README.md` → Documentation générale
- `GUIDE_UTILISATION_HYPERLIQUID.md` → Guide Hyperliquid
- `GUIDE_DERIBIT_SETUP.md` → Guide Deribit (pour les Français)
- `RESUME_SOLUTION.md` → Solution légale pour la France

