# Routes Utilisateur - Documentation API

## Vue d'ensemble

Les routes utilisateur permettent de gérer et consulter les tentatives (attempts) d'un utilisateur, ainsi que ses statistiques globales. Ces routes sont essentielles pour construire une interface utilisateur avec dashboard et historique.

## Endpoints disponibles

### 1. Liste des tentatives avec filtres

```http
GET /api/users/me/attempts
```

**Query Parameters:**
- `completed` (boolean, optional) : Filtrer par statut
  - `true` : Uniquement les tentatives complétées
  - `false` : Uniquement les tentatives en cours
  - Non spécifié : Toutes les tentatives
- `case_id` (int, optional) : Filtrer par cas clinique spécifique
- `station_type` (string, optional) : Filtrer par type de station
  - `patient_interview`
  - `exam_analysis`
  - `procedure`
  - `diagnosis_announcement`
  - `mixed`
- `limit` (int, default=50) : Nombre maximum de résultats (1-200)
- `offset` (int, default=0) : Décalage pour pagination

**Réponse:**
```json
{
  "attempts": [
    {
      "id": "uuid-string",
      "case_id": 1,
      "case_title": "Douleur thoracique - Suspicion de SCA",
      "station_type": "patient_interview",
      "created_at": "2026-01-12T10:30:00",
      "completed_at": "2026-01-12T10:36:30",
      "is_completed": true,
      "message_count": 12,
      "duration_seconds": 390
    }
  ],
  "stats": {
    "total_attempts": 5,
    "completed_attempts": 3,
    "in_progress_attempts": 2,
    "total_messages": 48,
    "cases_attempted": [1, 2, 3],
    "favorite_discipline": null
  }
}
```

**Cas d'usage:**
- Dashboard principal : afficher l'historique complet
- Filtrage par statut : voir uniquement les tentatives en cours
- Filtrage par cas : voir toutes les tentatives d'un cas spécifique
- Pagination : charger les tentatives par lot

### 2. Détail d'une tentative

```http
GET /api/users/me/attempts/{attempt_id}
```

**Paramètres:**
- `attempt_id` (UUID) : Identifiant de la tentative

**Réponse:**
```json
{
  "id": "uuid-string",
  "case_id": 1,
  "case_title": "Douleur thoracique - Suspicion de SCA",
  "station_type": "patient_interview",
  "created_at": "2026-01-12T10:30:00",
  "completed_at": "2026-01-12T10:36:30",
  "is_completed": true,
  "message_count": 12,
  "duration_seconds": 390
}
```

**Cas d'usage:**
- Afficher les détails d'une tentative spécifique
- Vérifier l'état d'une tentative avant de la reprendre

### 3. Statistiques utilisateur

```http
GET /api/users/me/stats
```

**Réponse:**
```json
{
  "total_attempts": 5,
  "completed_attempts": 3,
  "in_progress_attempts": 2,
  "total_messages": 48,
  "cases_attempted": [1, 2, 3],
  "favorite_discipline": null
}
```

**Cas d'usage:**
- Dashboard : afficher les statistiques globales
- Endpoint léger pour mise à jour rapide des compteurs
- Analytics : taux de complétion, engagement

### 4. Supprimer une tentative

```http
DELETE /api/users/me/attempts/{attempt_id}
```

**Paramètres:**
- `attempt_id` (UUID) : Identifiant de la tentative

**Réponse:**
```json
{
  "message": "Attempt deleted successfully",
  "id": "uuid-string"
}
```

**Comportement:**
- Supprime la tentative ET tous ses messages (cascade)
- Vérifie que la tentative appartient à l'utilisateur
- Retourne 403 si accès refusé

## Commandes CLI

### Lister les tentatives

```bash
# Toutes les tentatives
python ecos_cli.py user-attempts

# Uniquement les tentatives complétées
python ecos_cli.py user-attempts --completed

# Uniquement les tentatives en cours
python ecos_cli.py user-attempts --no-completed

# Filtrer par cas
python ecos_cli.py user-attempts --case-id 1

# Limiter les résultats
python ecos_cli.py user-attempts --limit 10
```

### Afficher les statistiques

```bash
python ecos_cli.py user-stats
```

**Sortie exemple:**
```
📊 STATISTIQUES UTILISATEUR
============================================================

📈 Total tentatives: 5
   ✅ Complétées: 3
   🔄 En cours: 2
   📊 Taux de complétion: 60.0%

💬 Messages envoyés: 48
📚 Cas différents tentés: 3

============================================================
```

## Workflow d'utilisation

### 1. Voir l'historique complet

```bash
python ecos_cli.py user-attempts
```

### 2. Filtrer les tentatives en cours pour les reprendre

```bash
python ecos_cli.py user-attempts --no-completed
```

Récupérer l'UUID d'une tentative en cours et la reprendre:

```bash
python ecos_cli.py chat-loop 1  # Continue avec l'attempt existante
```

### 3. Voir les statistiques pour le dashboard

```bash
python ecos_cli.py user-stats
```

## Intégration frontend

### Exemple React/Vue : Dashboard

```typescript
// Récupérer les données du dashboard
const response = await fetch('/api/users/me/attempts?limit=10');
const data = await response.json();

// Afficher les stats
const { stats, attempts } = data;

// Stats globales
console.log(`Taux de complétion: ${(stats.completed_attempts / stats.total_attempts * 100).toFixed(1)}%`);

// Liste des dernières tentatives
attempts.forEach(attempt => {
  console.log(`${attempt.case_title} - ${attempt.is_completed ? 'Terminé' : 'En cours'}`);
});
```

### Exemple : Reprise d'une tentative en cours

```typescript
// Récupérer les tentatives en cours
const response = await fetch('/api/users/me/attempts?completed=false');
const data = await response.json();

if (data.attempts.length > 0) {
  const inProgress = data.attempts[0];
  // Rediriger vers la tentative en cours
  navigate(`/attempt/${inProgress.id}`);
}
```

### Exemple : Historique avec pagination

```typescript
async function loadAttempts(page: number, perPage: number = 20) {
  const offset = page * perPage;
  const response = await fetch(
    `/api/users/me/attempts?limit=${perPage}&offset=${offset}`
  );
  return await response.json();
}
```

## Notes techniques

### Calcul de la durée

La durée d'une tentative est calculée comme :
```
duration_seconds = completed_at - created_at
```

Disponible uniquement si `is_completed = true` et `completed_at` est défini.

### Comptage des messages

Le champ `message_count` inclut tous les messages (student + patient) de la tentative.

### Authentification

Pour l'instant, `get_current_user_id()` retourne toujours `1` (user de test).
À remplacer par une vraie authentification JWT dans le futur.

### Performances

- La requête liste utilise un JOIN avec agrégation (COUNT)
- Indexation sur `user_id`, `is_completed`, `case_id`
- Pagination recommandée pour grands volumes

## Évolutions futures

1. **Discipline préférée** : Calculer à partir des liens CaseDiscipline
2. **Score moyen** : Agréger les scores d'évaluation
3. **Temps moyen par cas** : Statistiques de performance
4. **Filtres avancés** : Par période, par score, par discipline
5. **Export** : CSV/PDF des tentatives pour révision
