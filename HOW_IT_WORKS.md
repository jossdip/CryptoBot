# Comment fonctionne le bot CryptoBot : Le Guide pour Débutant

Ce document a pour but de vous expliquer, sans jargon technique complexe, comment fonctionne ce robot de trading. Imaginez ce logiciel non pas comme une simple calculatrice, mais comme une **petite entreprise de trading autonome** qui travaille pour vous 24h/24.

---

## 1. Introduction

### Quel est le but ?
Le but de ce bot est d'acheter et de vendre des cryptomonnaies (sur la plateforme Hyperliquid) pour générer du profit. Il essaie d'acheter quand c'est "bas" et de revendre quand c'est "haut", ou inversement (parier à la baisse).

### L'Analogie de l'Entreprise
Pour comprendre comment il marche, imaginez une salle de marché avec plusieurs employés. Il y a un **Chef** qui supervise, des **Experts** spécialisés chacun dans une technique, et des **Assistants** qui vont chercher l'information. Le code du bot organise la collaboration entre tous ces "employés" virtuels.

---

## 2. L'Équipe (L'Architecture du Code)

Voici les différents composants du logiciel et leur rôle :

### 👤 Le Chef : L'Orchestrateur (LLM)
*Dans le code : `LLMOrchestrator`*

C'est le cerveau, l'Intelligence Artificielle.
*   **Son rôle** : Il ne regarde pas chaque petite variation de prix seconde par seconde. Son travail est de **décider de la stratégie globale**.
*   **Ce qu'il fait** : Toutes les quelques minutes, il analyse la situation générale (les news, la tendance globale) et dit : *"Le marché est calme, donnez plus de budget à l'expert Market Maker"* ou *"Ça bouge fort, laissez faire le spécialiste du Momentum"*. Il répartit le "poids" (l'importance) de chaque stratégie.

### 🧑‍🏫 Les Experts : Les Stratégies
*Dans le code : Dossier `strategy/`*

Ce sont des modules spécialisés. Chacun a sa propre méthode pour gagner de l'argent. Ils travaillent en parallèle.

1.  **L'Épicier (Market Maker)** :
    *   *Philosophie* : "J'achète des pommes 1€ et je les revends 1.02€".
    *   *Action* : Il place des ordres d'achat un peu en dessous du prix et de vente un peu au-dessus. Il gagne sur la différence (le "spread") tant que le prix ne bouge pas trop violemment.
2.  **Le Surfeur (Momentum)** :
    *   *Philosophie* : "La vague monte, je monte avec elle".
    *   *Action* : Si le prix monte fort avec beaucoup de volume, il achète pour profiter de la hausse continue.
3.  **Le Nerveux (Scalper)** :
    *   *Philosophie* : "Un petit profit tout de suite vaut mieux qu'un gros peut-être".
    *   *Action* : Il fait des allers-retours très rapides pour gratter quelques centimes à chaque fois.
4.  **Le Mathématicien (Arbitrage)** :
    *   *Philosophie* : "C'est illogique que ce prix soit différent ici et là".
    *   *Action* : Il cherche des incohérences mathématiques entre les prix (par exemple entre le prix "spot" et le prix "futur") pour gagner à coup sûr (ou presque).
5.  **Le Chasseur d'Explosions (Breakout)** :
    *   *Philosophie* : "Si ça casse ce plafond, ça va monter jusqu'au ciel".
    *   *Action* : Il surveille des niveaux de prix clés. Si le prix traverse ces niveaux avec force, il fonce.
6.  **Le Tireur d'Élite (Sniping)** :
    *   *Philosophie* : "Une seule balle, une seule opportunité".
    *   *Action* : Il cherche des situations très spécifiques et rares mais potentiellement très rentables.

### 👀 Les Yeux et Oreilles : Données & Sentiment
*Dans le code : `MarketContextAggregator`*

C'est le service de renseignement.
*   **Les Yeux** : Il regarde les prix, les volumes et les carnets d'ordres sur les bourses (Binance, Hyperliquid).
*   **Les Oreilles (Sentiment)** : Il écoute ce qui se dit sur les réseaux sociaux (**Reddit**, **Twitter**) et regarde les paris sur les marchés de prédiction (**Polymarket**). Si tout le monde est paniqué sur Twitter, il prévient le Chef.

---

## 3. Le Cycle de Vie d'une Décision (Comment ça marche ?)

Le bot tourne en boucle (une "boucle infinie"). Voici ce qui se passe à chaque tour :

1.  **Observation** 🕵️
    L'aggrégateur rassemble toutes les infos : le prix du Bitcoin, le volume des échanges, et l'humeur sur Reddit.

2.  **Réunion Stratégique** 🧠
    Le Chef (LLM) regarde ces infos. Il décide de la répartition des forces. Par exemple : *35% Market Making, 25% Momentum, 15% Scalping*.

3.  **Chasse aux Opportunités** 🔎
    Chaque "Expert" (stratégie) scanne le marché selon ses propres règles.
    *   *Le Surfeur dit* : "Hey, le Bitcoin monte fort, j'ai envie d'acheter !"
    *   *L'Épicier dit* : "Rien pour moi, c'est trop agité."

4.  **Validation & Filtrage** 🛡️
    On ne peut pas tout acheter. Le système note chaque idée.
    *   Est-ce que c'est risqué ?
    *   Est-ce que le Chef (LLM) est d'accord ? On lui envoie l'idée : *"Le Surfeur veut acheter du BTC, tu valides ?"*. Le LLM donne un score de confiance.

5.  **Action** 🚀
    Si le Chef valide et que la confiance est suffisante, le **Courtier (Broker)** envoie l'ordre réel à la bourse Hyperliquid. L'achat est fait.

---

## 4. La Gestion des Risques (La Sécurité)

C'est l'assurance-vie du bot. Il ne suffit pas de savoir attaquer, il faut savoir défendre.

*   **Le Disjoncteur (Circuit Breaker)** : Comme à la maison. Si le bot perd trop d'argent trop vite dans la journée (par exemple -5% de votre capital), il "saute". Il arrête tout, annule les ordres et se met en pause pour éviter de tout perdre.
*   **Stop Loss (SL) / Take Profit (TP)** : C'est le filet de sécurité.
    *   *Stop Loss* : "Si je perds 1%, je vends tout de suite pour ne pas perdre 10%".
    *   *Take Profit* : "J'ai gagné 2%, je vends pour encaisser mes gains avant que ça redescende".
*   **Taille des positions** : Le bot calcule combien miser. Il ne mettra jamais 100% de votre argent sur un seul coup de tête du "Nerveux".

---

## 5. L'Apprentissage (Le Cerveau qui grandit)

Le bot possède une forme de mémoire et d'apprentissage (située dans le dossier `learn/`).

*   **La Mémoire (Episodes)** : Chaque fois qu'il fait un trade, il enregistre tout : "J'ai acheté parce que Reddit était positif et que le prix montait. Résultat : J'ai gagné 10$".
*   **Les Bandits** : C'est un algorithme mathématique simple. Imaginez qu'il a plusieurs machines à sous (les stratégies). Si la machine "Momentum" donne souvent des gains, il va avoir tendance à jouer plus souvent avec elle. Si la machine "Sniping" lui fait perdre de l'argent, il l'utilisera moins. Il ajuste sa confiance en fonction des résultats réels.

---

## 6. Points Forts et Points Faibles

### ✅ Les Points Forts
1.  **Sang-froid** : Il n'a pas peur, il n'est pas avide. Il suit le plan.
2.  **Infatigable** : Il surveille le marché 24h/24, 7j/7.
3.  **Adaptatif** : Grâce à l'IA (LLM), il peut changer de comportement si le marché change (passer de l'attaque à la défense).
4.  **Diversifié** : Il n'utilise pas qu'une seule méthode, ce qui réduit les risques.

### ⚠️ Les Points Faibles et Risques
1.  **Coûts** : L'intelligence artificielle (le Chef) coûte de l'argent à chaque réflexion (frais d'API LLM).
2.  **Latence** : L'IA prend quelques secondes pour réfléchir. Ce n'est pas du trading haute fréquence à la microseconde.
3.  **Risque de Marché** : Si le marché des cryptos s'effondre brutalement partout, même la meilleure stratégie peut perdre de l'argent.
4.  **Complexité** : C'est une machine complexe. Si un rouage casse (bug, problème de connexion), tout peut s'arrêter.

---

## 7. Glossaire pour Débutant

*   **Long** : Parier que le prix va **monter** (J'achète).
*   **Short** : Parier que le prix va **descendre** (Je vends à découvert).
*   **Levier (Leverage)** : Emprunter de l'argent à la bourse pour multiplier ses gains (mais aussi ses pertes !). *Exemple : Avec 100€ et un levier x10, je parie comme si j'avais 1000€. Si ça monte de 10%, je double ma mise. Si ça baisse de 10%, je perds tout.*
*   **Volatilité** : À quel point le prix bouge. *Forte volatilité = montagnes russes.*
*   **Slippage** : La différence entre le prix que vous vouliez et le prix que vous avez réellement eu (souvent à cause d'un mouvement très rapide).
*   **PnL (Profit and Loss)** : Vos Gains et Pertes. *PnL positif = Argent gagné.*

