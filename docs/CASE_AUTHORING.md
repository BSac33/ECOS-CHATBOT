# Atelier de création de stations

Les enseignants créent leurs stations ECOS sans écrire de prompt. Ils décrivent **des faits**
(qui est le patient, ce qu'il sait, comment il le dit, ce qu'il n'a pas), la plateforme en
compile le jeu du patient, le contexte de l'évaluateur et la grille. Un assistant (« Générer »)
complète les fiches incomplètes à partir du **référentiel officiel du 2e cycle**.

Accès : menu ▸ *Atelier de stations* (`/atelier`), rôles `teacher` et `admin`.

## Parcours de l'enseignant

1. **Créer** une station (titre) : un brouillon vide est créé.
2. **Remplir** les onglets : *Station*, *Patient*, *Ce que sait le patient*, *Examen clinique*,
   *Correction*. Chaque modification est enregistrée automatiquement (1,2 s après la frappe).
3. **Suivre les vérifications** (panneau de droite) : un clic sur un message amène au champ concerné.
4. **Générer** : l'assistant propose des faits, des reformulations, le personnage, la grille ou
   l'examen clinique. L'enseignant ajoute ou ignore chaque proposition ; ce qu'il ajoute porte le
   badge *Proposé par l'assistant · à relire* jusqu'à ce qu'il clique sur *Valider*.
5. **Tester le patient** : ouvre une consultation sur le brouillon tel quel (texte ou voix), dans un
   nouvel onglet. Ces tentatives de test sont exclues des statistiques.
6. **Publier** (refusé tant qu'il reste des erreurs) : crée une **version figée**. Les étudiants
   jouent toujours la dernière version publiée ; une tentative commencée garde la version avec
   laquelle elle a été jouée, y compris pour sa correction.
7. **Relecture par un collègue (facultative)** : voir ci-dessous. Une station se publie avec ou
   sans relecture.

## Relecture par un collègue

Statut porté par la station (`clinical_cases.review_status`), indépendant de la publication :

| Statut | Signification | Qui |
|---|---|---|
| *(aucun)* | pas de relecture demandée | — |
| **À relire** (`a_relire`) | l'auteur demande une relecture ; la station apparaît dans la liste « À relire pour mes collègues » de tous les enseignants | l'auteur (ou un administrateur) la demande ou la retire |
| **Relue** (`relue`) | un collègue l'a relue, avec une remarque facultative pour l'auteur | un autre enseignant que l'auteur, ou un administrateur |

- Le relecteur ouvre la station **en lecture seule**, peut **tester le patient**, puis laisse sa
  remarque et la marque comme relue (panneau *Vérifications*). Il ne peut ni la modifier ni la publier.
- Si l'auteur modifie la fiche après la relecture, la station affiche *Relue · modifiée depuis*
  (empreinte de la fiche relue, `reviewed_sheet_hash`) ; il peut demander une nouvelle relecture.
- **La publication n'est jamais bloquée** : une station à relire, relue ou jamais relue se publie
  de la même façon. Le statut n'est pas montré aux étudiants.

## La fiche de cas (`case_sheet.py`)

| Partie | Contenu |
|---|---|
| `station` | titre (visible des étudiants), lieu, rôle de l'étudiant, consignes, durée, items EDN (R2C), situations de départ, voix |
| `patient` | identité, profession, situation de vie, caractère, état émotionnel, registre de langage, inquiétudes, questions qu'il pose, réactions (« si l'étudiant… → il… ») |
| `facts` | un fait = catégorie, note médicale (`label`), **mots du patient** (`patient_words`), divulgation (`spontane` : le dit de lui-même ; `sur_question` : seulement si on lui demande) et thème neutre de la question (`asked_about`, ex. « le tabac ») |
| `never_says` | mots que le patient ne prononce jamais (diagnostic...) ; aussi filtrés de ses réponses |
| `exam_findings` | ce que l'examinateur communique à la demande (outil `resultat_examen_clinique`) |
| `correction` | diagnostic et prise en charge attendus, grille ; chaque item est relié aux faits (`fact_ids`) que l'étudiant doit obtenir |

Catégories de faits : motif, histoire, symptôme associé, **signe négatif**, antécédent, traitement,
allergie, mode de vie, contexte, autre. Les signes négatifs et les catégories classiques de
l'interrogatoire sont importants : sans réponse dans la fiche, le patient a tendance à inventer.

### Compilation

`compile_case(sheet)` produit les champs d'exécution :

- **prompt du patient** : identité, caractère et état, ce qu'il dit de lui-même, ce qu'il ne dit
  que si on lui demande (« Si on te pose des questions sur le tabac : « … » »), ce qu'il n'a pas,
  inquiétudes, questions, réactions, et ce qu'il ne sait pas (pas de diagnostic, mots interdits,
  « je ne sais pas » pour ce qui n'est pas dans la fiche). Les notes médicales n'y figurent pas ;
- **contexte de l'évaluateur** : patient, diagnostic et prise en charge attendus, éléments du dossier ;
- **grille** (`{id, criterion, points, description}`) et total des points ;
- résultats d'examen clinique, voix, durée.

L'onglet *Aperçu* affiche le prompt compilé, en lecture seule.

### Vérifications (`check_sheet`)

| Niveau | Exemples |
|---|---|
| **erreur** (bloque la publication) | pas de titre, de consignes, de faits ou de motif ; le patient dirait un mot interdit ; grille vide, item à 0 point ou relié à un fait supprimé ; identifiants de faits en double |
| **attention** | jargon dans la bouche du patient ; fait sans mots du patient ; titre qui révèle le diagnostic ; item de grille relié à aucun fait (sauf communication / diagnostic / examens) ; pas d'âge, d'item EDN ou de diagnostic attendu ; propositions de l'assistant non relues |
| **conseil** | pas de signes négatifs ; catégorie d'interrogatoire non couverte (antécédents, traitements, allergies, mode de vie, contexte) ; caractère non décrit |

## Versions (`case_publishing.py`, table `case_versions`)

- `publish()` fige la fiche compilée (`status="published"`, numéro croissant), met à jour les champs
  d'exécution de `clinical_cases`, la grille (`evaluation_grids`) et les liens vers les items EDN.
- `snapshot(..., "test")` fige le brouillon pour une tentative de test (`attempts.is_test = true`).
- `POST /chat/attempts` rattache la tentative à la dernière version publiée
  (`attempts.case_version_id`) ; le chat, la voix et l'évaluation lisent cette version.
- Les étudiants ne peuvent pas lancer un brouillon. Les cas créés avant l'atelier (sans fiche ni
  version) fonctionnent comme avant.

## Assistant de rédaction (`authoring_assistant.py`)

| Action | Propose | Appui du référentiel |
|---|---|---|
| Compléter l'interrogatoire | faits manquants, en priorité les catégories non couvertes | oui |
| Signes négatifs pertinents | ce que le patient n'a pas (diagnostics différentiels) | oui |
| Mots du patient | reformule les réponses trop techniques, trop courtes ou identiques à la note médicale | non |
| Compléter le personnage | caractère, état, inquiétudes, questions, réactions | non |
| Proposer la grille | 8 à 15 items reliés aux faits, d'après les objectifs de rang A et les notions indispensables | oui |
| Proposer l'examen clinique | constantes et appareils cohérents avec le diagnostic | oui |

Fonctionnement : recherche des extraits utiles (filtrée par les items de la station), appel du LLM
en **sortie structurée** (un schéma JSON par action), puis **filtrage déterministe** : propositions
contenant un mot interdit écartées, doublons écartés, faits inconnus retirés de la grille, sources
non fournies retirées, jargon signalé. Les éléments écartés sont listés sous la proposition. Une
*précision facultative* (ex. « patiente plus âgée, très anxieuse ») peut orienter l'assistant.

Configuration (`fastapi.env`) : un serveur **vLLM** (par défaut celui du patient, Qwen3-8B).
L'intégration Gemini de la codebase est historique et n'est pas utilisée par l'atelier.

```bash
AUTHORING_BASE_URL=   # vide = VLLM_BASE_URL (serveur du patient)
AUTHORING_MODEL=      # vide = VLLM_MODEL
AUTHORING_API_KEY=    # vide = VLLM_API_KEY
AUTHORING_TIMEOUT=120
```

Un serveur vLLM distinct (modèle plus gros pour la rédaction, hors des heures d'examen) se
configure avec ces mêmes variables.

## Référentiel officiel (`corpus.py`)

### Source et droits

Référentiel de cardiologie du **Collège national des enseignants de cardiologie**, publié par la
Société française de cardiologie (<https://www.sfcardio.fr/formation/dfasm/>, 22 chapitres).
L'équipe du projet a obtenu l'accord du collège de cardiologie et d'UNESS pour cet usage (conservez
la trace écrite de cet accord). Les textes restent la propriété de leurs auteurs et éditeur :

- ils sont stockés **en base uniquement** (`corpus_chunks`), jamais dans le dépôt : les tests
  utilisent un chapitre fictif (`tests/fixtures/sfc_chapter_fictif.html`) ;
- chaque extrait garde son URL et sa section, cités sous chaque proposition de l'assistant ;
- les conditions d'usage sont enregistrées avec la source (`corpus_sources.license_note`).

### Import

```bash
make corpus                                       # dans le conteneur fastapi
# ou
cd backend_ecos_chatbot/app
python scripts/ingest_corpus.py                   # télécharge l'index puis les chapitres (pause de 2 s)
python scripts/ingest_corpus.py --cache-dir /data/sfc   # garde une copie du HTML
python scripts/ingest_corpus.py --from-dir /data/sfc    # réimport sans réseau
python scripts/ingest_corpus.py --dry-run --limit 2     # vérifie l'analyse sans écrire
```

L'import est idempotent (un chapitre réimporté remplace ses extraits). Il met à jour les items EDN
(numéro et titre R2C), les **situations de départ** et les liens item ↔ situation. Le seed ne vide
pas le référentiel et reconstruit les items EDN à partir de lui.

Pour chaque chapitre : item R2C, situations de départ, **objectifs hiérarchisés** (rang A/B,
rubrique, intitulé), extraits d'environ 1 200 caractères par section avec leur **rang** (badge
« Rang A/B » du texte) et leur type (`cours`, `objectif`, `vignette`, `points_cles`, `notions`).
Sur les 22 chapitres : 1 940 extraits, 122 situations de départ.

### Recherche

BM25 en Python (accents et pluriels neutralisés, mots vides retirés), filtrable par items et types.
Quelques milliers d'extraits et des requêtes rares : pas d'index vectoriel pour l'instant. L'onglet
*Référentiel* de l'éditeur permet aussi à l'enseignant de chercher lui-même.

Ajouter une autre spécialité : écrire son analyseur (même sortie `ParsedChapter`) et sa
`CorpusSource` avec sa note de droits, puis réutiliser `store_chapter` et `search_corpus`.

## API (`authoring_routes.py`, préfixe `/authoring`, rôle enseignant)

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/cases` | mes stations (toutes pour un administrateur) |
| POST | `/cases` | nouveau brouillon `{title}` |
| GET | `/cases/{id}` | fiche, aperçu compilé, vérifications, versions |
| PUT | `/cases/{id}/sheet` | enregistrer la fiche (renvoie vérifications et aperçu) |
| POST | `/cases/{id}/publish` | publier ; 422 avec `{message, issues}` s'il reste des erreurs ; 409 si le titre est pris |
| POST | `/cases/{id}/test` | tentative de test du brouillon → `{attempt_id, version_id}` (auteur ou relecteur) |
| POST | `/cases/{id}/review/request` | demander une relecture (auteur) |
| DELETE | `/cases/{id}/review` | retirer le statut de relecture (auteur) |
| POST | `/cases/{id}/review` | `{note}` : marquer comme relue (autre enseignant ou administrateur) |
| POST | `/cases/{id}/assist` | `{task, instructions?, sheet?}` → propositions (la fiche n'est pas modifiée) |
| GET | `/reference/items` | items EDN connus |
| GET | `/reference/situations?items=339,230` | situations de départ, celles des items d'abord |
| GET | `/corpus/search?q=&items=&kinds=` | extraits du référentiel |
| GET | `/corpus/objectives?items=` | objectifs hiérarchisés (rang A d'abord) |

Un enseignant modifie ses stations et lit celles de ses collègues qui demandent une relecture
(ainsi que celles qu'il a relues) ; un administrateur voit et modifie tout.

## Frontend (`frontend/src/authoring/`)

`AuthoringCases.vue` (liste), `CaseEditor.vue` (onglets, enregistrement automatique, vérifications,
test, publication), `FactsEditor.vue`, `GridEditor.vue`, `AssistantPanel.vue`, `CorpusSearch.vue`,
`api.ts` (types de la fiche et appels).

## Limites connues

- Les consignes de l'assistant n'ont été vérifiées qu'avec un faux serveur LLM : à valider sur le
  modèle réel (qualité des propositions, respect du schéma JSON).
- Les cas créés avant l'atelier n'ont pas de fiche ; pas de conversion automatique.
- Seule la cardiologie est importée.
