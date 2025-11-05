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
curl -o setup_vps.sh https://raw.githubusercontent.com/votre-username/CryptoBot/main/deploy/setup_vps.sh

# Rendre exécutable
chmod +x setup_vps.sh

# Exécuter avec votre URL de repo Git
./setup_vps.sh git@github.com:votre-username/CryptoBot.git main
```

**Option B : Installation manuelle (si vous préférez)**

```bash
# 1. Installer les dépendances système
sudo apt update
sudo apt -y upgrade
sudo apt -y install git python3 python3-venv python3-pip

# 2. Cloner le repo
cd ~
git clone git@github.com:votre-username/CryptoBot.git
cd CryptoBot
git checkout main

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

### 3. Configurer les variables d'environnement

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

### Erreur "No such file or directory" pour deploy/setup_vps.sh

**Problème :** Vous essayez d'exécuter `./deploy/setup_vps.sh` mais le fichier n'existe pas encore sur le VPS.

**Solution :** Utilisez l'une des méthodes suivantes :

**Méthode 1 : Télécharger le script depuis GitHub**
```bash
curl -o setup_vps.sh https://raw.githubusercontent.com/votre-username/CryptoBot/main/deploy/setup_vps.sh
chmod +x setup_vps.sh
./setup_vps.sh git@github.com:votre-username/CryptoBot.git main
```

**Méthode 2 : Installation manuelle complète**
```bash
# Installer les dépendances
sudo apt update && sudo apt -y install git python3 python3-venv python3-pip

# Cloner le repo
cd ~
git clone git@github.com:votre-username/CryptoBot.git
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

# 2. Télécharger et installer (automatique)
curl -o setup_vps.sh https://raw.githubusercontent.com/votre-username/CryptoBot/main/deploy/setup_vps.sh
chmod +x setup_vps.sh
./setup_vps.sh git@github.com:votre-username/CryptoBot.git main

# 3. Configurer vos clés
nano ~/CryptoBot/.env  # Remplir vos clés

# 4. Installer le service systemd
cd ~/CryptoBot
sudo ./deploy/install_service.sh paper

# 5. Vérifier que ça tourne
sudo journalctl -u cryptobot-paper@$(whoami) -f
```

**C'est tout ! Le bot tourne maintenant en arrière-plan et redémarre automatiquement.**

**Note :** Si vous n'avez pas encore pushé le repo sur GitHub, utilisez l'**Option B (Installation manuelle)** ci-dessus.

---

## Support

Pour plus d'informations :
- `README.md` → Documentation générale
- `GUIDE_UTILISATION_HYPERLIQUID.md` → Guide Hyperliquid
- `GUIDE_DERIBIT_SETUP.md` → Guide Deribit (pour les Français)
- `RESUME_SOLUTION.md` → Solution légale pour la France

