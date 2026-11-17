# scoring.py
"""
Note d'une station ECOS à partir de la réponse de l'évaluateur LLM.

Comme aux ECOS nationaux :
- items de la grille d'observation (observé / non observé) : aptitudes cliniques ;
- échelles d'attitude cotées de 0 (inacceptable) à 4 (remarquable) : communication ;
- évaluation globale de la performance (0 à 4) : affichée, non comptée dans la note.

note /20 = 20 × ((1 − p) × items obtenus / items possibles + p × moyenne des échelles / 4)
avec p = part des attitudes (0,25 par défaut ; 20 à 30 % aux ECOS-N). Sans échelle
évaluable, la note ne dépend que des items. Les totaux sont recalculés ici : on ne fait
jamais confiance aux sommes renvoyées par le LLM.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from case_sheet import LEVEL_NAMES

GLOBAL_LABEL = "Évaluation globale de la performance"


def _level(value: Any) -> Optional[int]:
    try:
        level = int(value)
    except (TypeError, ValueError):
        return None
    return min(4, max(0, level))


def score_evaluation(result: Dict[str, Any], grid: Dict[str, Any]) -> Dict[str, Any]:
    """Complète result["evaluation"] (sortie du LLM) avec les totaux, les échelles et la note /20."""
    evaluation = dict(result.get("evaluation") or result)
    points = {str(i.get("id")): float(i.get("points", 1)) for i in grid.get("items", [])}

    # Items : points bornés par la grille, un item par entrée de grille
    by_id = {str(i.get("item_id")): i for i in evaluation.get("items") or []}
    items = []
    for gi in grid.get("items", []):
        item_id = str(gi.get("id"))
        possible = points.get(item_id, 1.0)
        raw = by_id.get(item_id, {})
        awarded = min(possible, max(0.0, float(raw.get("points_awarded") or 0)))
        items.append({
            "item_id": item_id,
            "criterion": gi.get("criterion", raw.get("criterion", "")),
            "points_awarded": awarded,
            "points_possible": possible,
            "is_validated": awarded > 0,
            "justification": raw.get("justification") or "Non évalué.",
        })
    items_score = sum(i["points_awarded"] for i in items)
    items_possible = sum(i["points_possible"] for i in items)
    items_ratio = items_score / items_possible if items_possible else 0.0

    # Échelles d'attitude
    ratings = {str(r.get("scale_id")): r for r in evaluation.get("scales") or []}
    scales = []
    for sc in grid.get("scales") or []:
        rating = ratings.get(str(sc["id"])) if sc.get("observable", True) else None
        level = _level(rating.get("level")) if rating else None
        scales.append({
            "scale_id": sc["id"],
            "label": sc["label"],
            "observable": bool(sc.get("observable", True)),
            "level": level,
            "level_name": LEVEL_NAMES[level] if level is not None else None,
            "justification": (rating or {}).get("justification")
            or ("Non évaluable sur la plateforme (regard, posture)." if not sc.get("observable", True)
                else "Non évalué."),
        })
    rated = [s["level"] for s in scales if s["level"] is not None]
    weight = float(grid.get("attitude_weight", 0.25)) if rated else 0.0
    scales_ratio = (sum(rated) / (4 * len(rated))) if rated else 0.0
    score_20 = round(20 * ((1 - weight) * items_ratio + weight * scales_ratio), 2)

    global_performance = None
    if grid.get("global_rating"):
        raw = evaluation.get("global_performance") or {}
        level = _level(raw.get("level"))
        global_performance = {
            "label": GLOBAL_LABEL,
            "level": level,
            "level_name": LEVEL_NAMES[level] if level is not None else None,
            "justification": raw.get("justification") or ("Non évalué." if level is None else ""),
        }

    evaluation.update({
        "items": items,
        "total_score": items_score,
        "total_possible": items_possible,
        "items_score": items_score,
        "items_possible": items_possible,
        "scales": scales,
        "global_performance": global_performance,
        "attitude_weight": weight,
        "score_20": score_20,
        "percentage": round(score_20 * 5, 1),
        "general_feedback": evaluation.get("general_feedback") or "",
    })
    return {"evaluation": evaluation}


def scales_prompt(scales: List[dict], global_rating: bool) -> str:
    """Section du prompt de l'évaluateur décrivant les échelles à coter."""
    lines: List[str] = []
    observable = [s for s in scales if s.get("observable", True)]
    if observable:
        lines.append("[ÉCHELLES D'ATTITUDE] Cote chaque échelle de 0 à 4 d'après le transcript :")
        for sc in observable:
            lines.append(f"- {sc['id']} : {sc['label']}")
            for level, text in enumerate(sc["levels"]):
                lines.append(f"    {level} = {text}")
    if global_rating:
        lines.append("[ÉVALUATION GLOBALE DE LA PERFORMANCE] Cote de 0 à 4 : 0 inacceptable (délétère, dangereuse), "
                     "1 insuffisante (en dessous des attentes), 2 suffisante (tout juste aux attentes), "
                     "3 satisfaisante (au-dessus des attentes sans être impressionnante), 4 remarquable.")
    if lines:
        lines.append("Pour chaque échelle et pour l'évaluation globale, justifie le niveau par des passages "
                     "du transcript ; la communication non verbale n'est pas observable ici et n'est pas demandée.")
    return "\n".join(lines)
