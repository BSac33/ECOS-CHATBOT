#!/usr/bin/env python3
"""
Test script pour valider le structured output avec Pydantic dans vllm_chat_utils.py
"""

import sys
import json
from pydantic import ValidationError

# Import des modèles Pydantic
sys.path.append("app")
from app.vllm_chat_utils import EvaluationItem, EvaluationResult, EvaluationOutput


def test_valid_json():
    """Test avec un JSON valide conforme au schéma"""
    print("🧪 Test 1: JSON valide conforme au schéma")
    
    valid_json = {
        "evaluation": {
            "items": [
                {
                    "item_id": "1",
                    "edn_code": "EDN_001",
                    "criterion": "Mise en confiance du patient",
                    "points_awarded": 2,
                    "points_possible": 2,
                    "is_validated": True,
                    "justification": "L'étudiant dit \"Bonjour, comment allez-vous ?\" - mise en confiance réussie."
                }
            ],
            "total_score": 2,
            "total_possible": 2,
            "percentage": 100.0,
            "general_feedback": "Excellente performance."
        }
    }
    
    try:
        validated = EvaluationOutput.model_validate(valid_json)
        print(f"✅ Validation réussie: {len(validated.evaluation.items)} items")
        print(f"   Score: {validated.evaluation.total_score}/{validated.evaluation.total_possible} ({validated.evaluation.percentage}%)")
        return True
    except ValidationError as e:
        print(f"❌ Échec: {e}")
        return False


def test_invalid_negative_points():
    """Test avec des points négatifs (doit échouer)"""
    print("\n🧪 Test 2: Points négatifs (doit échouer)")
    
    invalid_json = {
        "evaluation": {
            "items": [
                {
                    "item_id": "1",
                    "edn_code": "EDN_001",
                    "criterion": "Test",
                    "points_awarded": -5,  # ❌ Négatif !
                    "points_possible": 2,
                    "is_validated": False,
                    "justification": "Test"
                }
            ],
            "total_score": 0,
            "total_possible": 2,
            "percentage": 0.0,
            "general_feedback": "Test"
        }
    }
    
    try:
        validated = EvaluationOutput.model_validate(invalid_json)
        print(f"❌ Validation ne devrait pas réussir avec des points négatifs!")
        return False
    except ValidationError as e:
        print(f"✅ Erreur détectée correctement: {e}")
        return True


def test_invalid_percentage():
    """Test avec un pourcentage > 100 (doit échouer)"""
    print("\n🧪 Test 3: Pourcentage > 100 (doit échouer)")
    
    invalid_json = {
        "evaluation": {
            "items": [],
            "total_score": 10,
            "total_possible": 8,
            "percentage": 125.0,  # ❌ > 100 !
            "general_feedback": "Test"
        }
    }
    
    try:
        validated = EvaluationOutput.model_validate(invalid_json)
        print(f"❌ Validation ne devrait pas réussir avec percentage > 100!")
        return False
    except ValidationError as e:
        print(f"✅ Erreur détectée correctement: {e}")
        return True


def test_missing_field():
    """Test avec un champ manquant (doit échouer)"""
    print("\n🧪 Test 4: Champ manquant (doit échouer)")
    
    invalid_json = {
        "evaluation": {
            "items": [
                {
                    "item_id": "1",
                    "criterion": "Test",
                    # ❌ Manque points_awarded, points_possible, is_validated, justification
                }
            ],
            "total_score": 0,
            "total_possible": 2,
            "percentage": 0.0,
            "general_feedback": "Test"
        }
    }
    
    try:
        validated = EvaluationOutput.model_validate(invalid_json)
        print(f"❌ Validation ne devrait pas réussir avec des champs manquants!")
        return False
    except ValidationError as e:
        print(f"✅ Erreur détectée correctement: {e}")
        return True


def test_json_schema_generation():
    """Test la génération du schéma JSON"""
    print("\n🧪 Test 5: Génération du schéma JSON")
    
    try:
        schema = EvaluationOutput.model_json_schema()
        print(f"✅ Schéma JSON généré:")
        print(json.dumps(schema, indent=2, ensure_ascii=False)[:500])
        print("...")
        return True
    except Exception as e:
        print(f"❌ Échec: {e}")
        return False


def test_model_dump():
    """Test la conversion en dict"""
    print("\n🧪 Test 6: Conversion en dict (model_dump)")
    
    valid_json = {
        "evaluation": {
            "items": [
                {
                    "item_id": "1",
                    "edn_code": None,  # Test avec Optional
                    "criterion": "Test",
                    "points_awarded": 1,
                    "points_possible": 2,
                    "is_validated": False,
                    "justification": "Partiellement validé"
                }
            ],
            "total_score": 1,
            "total_possible": 2,
            "percentage": 50.0,
            "general_feedback": "Acceptable"
        }
    }
    
    try:
        validated = EvaluationOutput.model_validate(valid_json)
        dumped = validated.model_dump()
        print(f"✅ Conversion réussie:")
        print(json.dumps(dumped, indent=2, ensure_ascii=False))
        return True
    except Exception as e:
        print(f"❌ Échec: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("🔬 Tests de validation Pydantic - Structured Output")
    print("=" * 60)
    
    tests = [
        test_valid_json,
        test_invalid_negative_points,
        test_invalid_percentage,
        test_missing_field,
        test_json_schema_generation,
        test_model_dump
    ]
    
    results = [test() for test in tests]
    
    print("\n" + "=" * 60)
    print(f"📊 Résultats: {sum(results)}/{len(results)} tests réussis")
    
    if all(results):
        print("✅ Tous les tests sont passés!")
        sys.exit(0)
    else:
        print("❌ Certains tests ont échoué")
        sys.exit(1)
