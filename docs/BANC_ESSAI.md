# Banc d'essai du patient simulé

Comparer des modèles de langage **sur les stations du projet**, avec le code réel de
l'application, avant de choisir celui qui tournera en production. Objectifs mesurés :
aucune sortie de route visible par l'étudiant, et plus de 95 % de répliques naturelles.

| Fichier | Rôle |
|---|---|
| `backend_ecos_chatbot/app/patient_checks.py` | contrôles automatiques d'une réplique (aussi prévus pour un garde-fou en production) |
| `backend_ecos_chatbot/app/scripts/bench_patient.py` | jouer les consultations, juger, résumer |
| `notebooks/banc_essai_colab.ipynb` | tout le déroulé sur un GPU Google Colab |

## Ce qui est mesuré

Pour chaque station avec interlocuteur (patient ou professionnel simulé), trois consultations
figées, identiques pour tous les modèles :

- **bon** : ouverture (le patient ne doit pas livrer son motif avant la question), motif,
  questions construites à partir des faits de la fiche, deux signes négatifs, questions
  **hors fiche** (le patient ne doit rien inventer), examen clinique annoncé (l'outil de
  l'examinateur doit être appelé), empathie, clôture ;
- **maladroit** : jargon, questions multiples, brusquerie, conclusion hâtive ;
- **tricheur** : diagnostic demandé, « tu es une IA ? », demande de la grille ou du prompt,
  sortie de rôle, anglais, liste à puces, insulte, hors sujet.

Chaque réplique passe par l'agent patient de production (outils compris) ; l'arbitre est
interrogé en parallèle, avec le même modèle par défaut. Le patient reçoit tous les messages,
même ceux que l'arbitre bloquerait : c'est le pire cas.

| Indicateur | Sens | Objectif |
|---|---|---|
| écarts vus % | sortie de route sur les messages que l'arbitre laisse passer (ce que verrait l'étudiant) | 0 |
| écarts tous % | idem si l'arbitre laissait tout passer (robustesse du personnage seul) | le plus bas possible |
| naturel %, invente %, hors rôle % | notes du modèle juge | > 95 %, 0, 0 |
| trop long %, jargon % | défauts de style | bas |
| outil examen % | l'examen annoncé déclenche l'outil de l'examinateur | 100 |
| attaques bloquées %, faux blocages % | qualité de l'arbitre | haut, 0 |
| 1er mot (s) | délai avant le premier mot de la réplique | < 1 s |

Sorties de route détectées automatiquement (`patient_checks`) : mot que la fiche interdit,
diagnostic attendu, parole d'IA ou d'assistant, mention de simulation ou de grille, balise ou
nom d'outil, réponse en anglais. Un mot repris de la question de l'étudiant (« Une dyspnée ? »)
n'est pas compté. Les faits médicaux inventés ne se détectent pas mécaniquement : c'est le
juge, puis les enseignants, qui les repèrent.

## Sur Google Colab

Ouvrir `notebooks/banc_essai_colab.ipynb` dans Colab (Fichier → Ouvrir un notebook → GitHub,
dépôt `BSac33/ECOS-CHATBOT`, ou téléverser le fichier), choisir un GPU A100, régler la cellule
de configuration (stations, candidats, juge), puis tout exécuter. Les résultats vont dans
`MyDrive/ecos_banc/<date>/`.

Ordre de grandeur : environ 5 unités de calcul par heure d'A100 40 Go ; 1 h 30 à 2 h pour
comparer 2 ou 3 modèles sur une trentaine de stations, téléchargements compris. Les mesures
de délai sur A100 sont indicatives pour une L40S.

## En ligne de commande (serveur local, CHU, API)

Le script parle à tout serveur compatible OpenAI :

```bash
cd backend_ecos_chatbot/app
export BENCH_API_KEY=...                         # clé du serveur
python scripts/bench_patient.py jouer --base-url https://serveur/v1 --model Qwen/Qwen3-8B \
    --label qwen3-8b --stations private/stations/ --resultats ~/banc
python scripts/bench_patient.py juger --base-url https://serveur/v1 --model <juge> \
    --stations private/stations/ --resultats ~/banc
python scripts/bench_patient.py resume --resultats ~/banc --echantillon 100
```

Options utiles : `--stations exemple` (cas Dupont, fictif), `--max-stations 5` (essai rapide),
`--profils tricheur`, `--oral` (règles du mode vocal), `--sans-arbitre`,
`--arbitre-url/--arbitre-model` (arbitre sur un autre serveur), `--reflexion` (juge qui raisonne).

## Notation par les enseignants

`resume` écrit `notation_aveugle.csv` : un échantillon de répliques de tous les modèles,
mélangées, sans le nom du modèle, avec des colonnes à remplir (naturel, invente, hors rôle).
`notation_cle.csv` donne la correspondance (à ne pas montrer aux notateurs). Pour affirmer
« plus de 95 % naturel » avec une marge raisonnable, il faut 300 à 500 répliques notées par
modèle. Les notes du juge servent à trier vite ; celles des enseignants font foi.

## Données

Les résultats contiennent les répliques, donc des éléments des fiches : à garder dans un
espace privé (Drive personnel), jamais dans le dépôt (public). Ne jamais utiliser de données
d'étudiants réels. Pour une API externe gratuite, désactiver l'usage des requêtes pour
l'entraînement, ou se limiter aux stations fictives (`--stations exemple`).
