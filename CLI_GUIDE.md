# 🏥 ECOS CLI - Guide d'utilisation

Interface en ligne de commande pour interagir avec le chatbot ECOS.

## 📋 Prérequis

```bash
# Activer l'environnement virtuel
source .venv/bin/activate

# Installer les dépendances (déjà fait)
pip install httpx typer
```

## 🚀 Démarrage rapide

### Méthode 1 : Workflow complet automatique (Recommandé)

```bash
python ecos_cli.py start
```

Cette commande unique :
1. ✅ Demande vos identifiants (username/password)
2. ✅ Se connecte et sauvegarde la session
3. ✅ Affiche la liste des cas cliniques disponibles
4. ✅ Lance le cas de votre choix en mode interactif

**Exemple d'utilisation :**
```
🏥 ECOS CHATBOT - Interface CLI
============================================================

📝 CONNEXION
------------------------------------------------------------
Username: bensac
Password: ********
✅ Connecté en tant que bensac

📚 CAS CLINIQUES DISPONIBLES
------------------------------------------------------------

1. [ID: 1] Douleur thoracique chez un homme de 55 ans
   Type: Anamnèse | Durée: 10min

2. [ID: 2] Dyspnée aiguë chez une femme de 70 ans
   Type: Examen clinique | Durée: 15min

Choisissez un cas (numéro ou ID): 1

🚀 Lancement du cas: Douleur thoracique chez un homme de 55 ans

✅ Attempt créée: abc-123-def-456

📋 CONSIGNES:
============================================================
Vous êtes interne de garde aux urgences...
============================================================

⏱️  Durée: 10 minutes

💬 CONVERSATION
Commandes: /history, /time, /finalize, /quit
------------------------------------------------------------

ÉTUDIANT > Bonjour Monsieur, je suis le Dr. Martin...
PATIENT > Bonjour Docteur. J'ai une douleur dans la poitrine...
```

### Méthode 2 : Commandes séparées

#### 1. Se connecter

```bash
python ecos_cli.py login
```

Ou avec les identifiants en paramètres :
```bash
python ecos_cli.py login -u bensac -p monmotdepasse
```

#### 2. Lister les cas disponibles

```bash
python ecos_cli.py list-cases
```

Avec filtres :
```bash
# Par type de station
python ecos_cli.py list-cases --type "Anamnèse"

# Par discipline
python ecos_cli.py list-cases --discipline "Cardiologie"
```

#### 3. Lancer un cas en mode interactif

```bash
python ecos_cli.py chat-loop 1
```

## 💬 Commandes pendant la conversation

Une fois dans le mode interactif, vous pouvez utiliser :

| Commande | Description |
|----------|-------------|
| `/history` | Afficher l'historique complet des messages |
| `/time` | Voir le temps restant |
| `/finalize` | Terminer la tentative et passer à l'évaluation |
| `/quit` ou `/exit` | Quitter sans finaliser |

## 📊 Commandes avancées

### Voir vos tentatives précédentes

```bash
# Toutes vos tentatives
python ecos_cli.py user-attempts

# Filtrer par statut
python ecos_cli.py user-attempts --completed
python ecos_cli.py user-attempts --no-completed

# Filtrer par cas
python ecos_cli.py user-attempts --case-id 1

# Limiter le nombre de résultats
python ecos_cli.py user-attempts --limit 10
```

### Voir vos statistiques

```bash
python ecos_cli.py user-stats
```

### Évaluer une tentative

```bash
python ecos_cli.py attempt-evaluate <attempt-id>
```

**Exemple :**
```bash
python ecos_cli.py attempt-evaluate abc-123-def-456
```

### Voir le transcript d'une tentative

```bash
python ecos_cli.py attempt-transcript <attempt-id>
```

## 🔐 Authentification

### Méthode 1 : Session persistante (Recommandé)

Utilisez `python ecos_cli.py login` une seule fois. La session est sauvegardée dans `~/.ecos_cookies.json` et réutilisée automatiquement pour toutes les commandes suivantes.

**Pour se déconnecter :**
```bash
python ecos_cli.py logout
```

### Méthode 2 : Variable d'environnement (Legacy)

Si vous préférez utiliser un token directement :

```bash
export ECOS_TOKEN="votre_token_jwt_ici"
python ecos_cli.py chat-loop 1
```

## 🛠️ Commandes utiles

### Vérifier la connexion au serveur

```bash
python ecos_cli.py health
```

### Créer manuellement une tentative

```bash
python ecos_cli.py attempt-create 1
```

### Envoyer un message unique

```bash
python ecos_cli.py attempt-chat <attempt-id> "Bonjour, comment allez-vous ?"
```

### Finaliser manuellement une tentative

```bash
python ecos_cli.py attempt-finalize <attempt-id>
```

## 📝 Workflow complet typique

```bash
# 1. Démarrage (tout en un)
python ecos_cli.py start

# Ou étape par étape :

# 2. Connexion
python ecos_cli.py login

# 3. Liste des cas
python ecos_cli.py list-cases

# 4. Lancer un cas
python ecos_cli.py chat-loop 1

# 5. Après avoir finalisé avec /finalize, évaluer
python ecos_cli.py attempt-evaluate <attempt-id>

# 6. Voir le transcript
python ecos_cli.py attempt-transcript <attempt-id>

# 7. Voir vos statistiques
python ecos_cli.py user-stats
```

## 🆘 Dépannage

### "Non authentifié" après login

Vérifiez que le fichier `~/.ecos_cookies.json` existe :
```bash
ls -la ~/.ecos_cookies.json
```

Si le problème persiste, reconnectez-vous :
```bash
python ecos_cli.py logout
python ecos_cli.py login
```

### Erreur de connexion au serveur

Vérifiez que le backend est démarré :
```bash
docker compose ps
```

Par défaut, le CLI se connecte à `http://localhost:8000`. Pour changer :
```bash
export ECOS_BASE_URL="http://autre-url:8000"
```

## 🎨 Exemples d'utilisation avancée

### Script automatisé pour tester plusieurs cas

```bash
#!/bin/bash
source .venv/bin/activate

# Login une fois
python ecos_cli.py login -u bensac -p password

# Lancer plusieurs cas
for case_id in 1 2 3; do
    echo "Test du cas $case_id"
    python ecos_cli.py chat-loop $case_id < test_inputs_${case_id}.txt
done

# Voir les stats finales
python ecos_cli.py user-stats
```

### Utilisation en CI/CD

```yaml
# .github/workflows/test-ecos.yml
- name: Test ECOS CLI
  run: |
    source .venv/bin/activate
    python ecos_cli.py login -u test_user -p ${{ secrets.TEST_PASSWORD }}
    python ecos_cli.py list-cases
```

## 📖 Aide

Pour voir toutes les commandes disponibles :
```bash
python ecos_cli.py --help
```

Pour l'aide d'une commande spécifique :
```bash
python ecos_cli.py chat-loop --help
```

---

**Bon entraînement ! 🎓**
