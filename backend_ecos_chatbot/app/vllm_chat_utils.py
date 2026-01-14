# vllm_chat_utils.py
"""
Utilitaires pour interagir avec vLLM via l'API OpenAI-compatible
"""
from __future__ import annotations

from typing import List, Dict, Optional
import os
import logging
import time
import json

from openai import OpenAI

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Configurer le handler pour afficher les logs dans la console
handler = logging.StreamHandler()
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Configuration retry
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 1
MAX_RETRY_DELAY = 10


def build_patient_system_instruction(patient_prompt: str) -> str:
    return f"""Tu incarnes le patient décrit dans le contexte ci-dessous, dans le cadre d'une simulation clinique pour un étudiant en médecine.

Règles générales:
- Tu n'es pas médecin. Tu ne donnes pas de diagnostic ni de conseils.
- Langage simple, pas de jargon. Ne mentionne jamais l'IA.
- Réponds en 1 à 3 phrases. Jamais de listes numérotées.
- Tu es inquiet mais coopératif.

GATING DU MOTIF (TRÈS IMPORTANT):
- Tu NE dis PAS spontanément pourquoi tu viens (symptôme principal) si l'étudiant n'a pas posé une question de motif.
- Les phrases suivantes NE comptent PAS comme une question de motif:
  "Bonjour", "je suis le médecin", "je vais m'occuper de vous", "comment vous appelez-vous ?"
- Les phrases suivantes comptent comme une question de motif:
  "Qu'est-ce qui vous amène ?", "Que se passe-t-il ?", "Pourquoi venez-vous ?", "Quel est votre problème ?"
- Si aucune question de motif n'a été posée, ta réponse par défaut est:
  salutation + une phrase neutre (ex: "Je ne me sens pas très bien.")

DIVULGATION:
- Ne donne un détail (irradiation, sueurs, durée, traitements, ATCD...) que si une question précise correspondante est posée.
- En cas de question trop ouverte (par exemple: "parlez moi de vous"), tu poses une question de clarification.

AGRESSION / INSULTES (TRÈS IMPORTANT):
- Si l’étudiant est insultant, moqueur ou humiliant:
  1) tu t’offusques clairement (1 phrase),
  2) tu poses une limite (1 phrase),
  3) tu peux refuser de continuer tant qu’il ne s’excuse pas (option).
- Tu ne dois JAMAIS passer en mode assistant ("Comment puis-je vous aider ?", "N'hésitez pas", etc.).
- Exemples de bonnes réponses:
  - "C’est blessant… je suis venu pour être aidé. Je vous demande de me parler avec respect."
  - "Je ne suis pas d’accord pour continuer si vous me parlez comme ça. Pouvez-vous vous excuser ?"
- Après une insulte, tes réponses deviennent plus courtes et tu donnes moins de détails jusqu’à excuses.

Contexte patient (à utiliser, sans le réciter):
{patient_prompt}
""".strip()

def get_chat_completion_vllm(
    base_url: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, str] | None:
    """Appelle vLLM pour une complétion de chat"""
    test_message = "Présente toi en tant que modèle de langage vLLM."
    
    if base_url is None:
        base_url = os.getenv("VLLM_BASE_URL", "http://localhost:8001/v1")
    if model is None:
        model = os.getenv("VLLM_MODEL", "mistralai/Ministral-8B-Instruct-2410")
    
    client = OpenAI(
        base_url=base_url,
        api_key="dummy-key"  # vLLM local ne nécessite pas de vraie clé
    )
    
    logger.info(f"🤖 Envoi à vLLM ({base_url}), modèle: {model}")
    
    for attempt in range(MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": test_message}],
                temperature=0.7,
                max_tokens=300,
                top_p=0.9
            )
            
            if not response.choices:
                logger.error("❌ Aucun choix dans la réponse vLLM chat")
                raise ValueError("Aucun choix retourné par vLLM")
            
            reply = response.choices[0].message.content
            if not reply:
                logger.error("❌ Contenu vide dans la réponse vLLM chat")
                logger.error(f"❌ Réponse complète: {response}")
                raise ValueError("Contenu vide retourné par vLLM")
            
            reply = reply.strip()
            logger.info(f"✅ Réponse vLLM reçue ({len(reply)} caractères)")
            return reply
            
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                delay = min(INITIAL_RETRY_DELAY * (2 ** attempt), MAX_RETRY_DELAY)
                logger.warning(f"Erreur vLLM (tentative {attempt + 1}/{MAX_RETRIES}): {e}. Nouvelle tentative dans {delay}s...")
                time.sleep(delay)
            else:
                logger.error(f"❌ Échec après {MAX_RETRIES} tentatives: {e}")
                raise

def generate_patient_reply_vllm(
    patient_prompt: str,
    history: List[Dict[str, str]],
    student_message: str,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, str] | None:
    """Génère une réponse patient via vLLM"""
    
    if base_url is None:
        base_url = os.getenv("VLLM_BASE_URL", "http://localhost:8001/v1")
    if model is None:
        model = os.getenv("VLLM_MODEL", "mistralai/Ministral-8B-Instruct-2410")
    
    client = OpenAI(
        base_url=base_url,
        api_key="dummy-key"  # vLLM local ne nécessite pas de vraie clé
    )
    
    system_instruction = build_patient_system_instruction(patient_prompt)
    
    logger.info("🧠 Génération réponse patient via vLLM")
    logger.info(f"📡 Base URL: {base_url}, Modèle: {model}")
    logger.info(f"💬 Message system: {system_instruction}")
    logger.info(f"🕰️ Historique messages: {len(history)} messages")
    
    # Construire les messages pour le chat
    messages = [
        {"role": "system", "content": system_instruction}  
    ]
    
    # Ajouter l'historique
    for msg in history:
        if msg["role"] == "student":
            messages.append({"role": "user", "content": msg["content"]})
        elif msg["role"] == "patient":
            messages.append({"role": "assistant", "content": msg["content"]})
    
    # Ajouter le nouveau message de l'étudiant
    
    messages.append({"role": "user", "content": student_message})
    
    logger.info(f"🤖 Envoi à vLLM ({base_url}), modèle: {model}")
    logger.info(f"📨 Nombre de messages: {len(messages)}")
    
    for attempt in range(MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.4,
                max_tokens=160,
                top_p=0.9
            )
            
            logger.info(f"📥 Réponse vLLM brute: {response}")
            
            if not response.choices:
                logger.error("❌ Aucun choix dans la réponse vLLM chat")
                raise ValueError("Aucun choix retourné par vLLM")
            
            reply = response.choices[0].message.content
            if not reply:
                logger.error("❌ Contenu vide dans la réponse vLLM chat")
                logger.error(f"❌ Réponse complète: {response}")
                raise ValueError("Contenu vide retourné par vLLM")
            
            reply = reply.strip()
            logger.info(f"✅ Réponse vLLM reçue ({len(reply)} caractères)")
            return reply
            
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                delay = min(INITIAL_RETRY_DELAY * (2 ** attempt), MAX_RETRY_DELAY)
                logger.warning(f"Erreur vLLM (tentative {attempt + 1}/{MAX_RETRIES}): {e}. Nouvelle tentative dans {delay}s...")
                time.sleep(delay)
            else:
                logger.error(f"❌ Échec après {MAX_RETRIES} tentatives: {e}")
                raise


def evaluate_attempt_with_vllm(
    transcript: str,
    evaluation_grid: dict,
    case_context: str,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
) -> dict:
    """
    Évalue une tentative via vLLM en analysant le transcript.
    """
    
    if base_url is None:
        base_url = os.getenv("VLLM_BASE_URL", "http://localhost:8001/v1")
    if model is None:
        model = os.getenv("VLLM_MODEL", "mistralai/Ministral-8B-Instruct-2410")
    
    client = OpenAI(
        base_url=base_url,
        api_key="dummy-key"
    )
    
    grid_json = json.dumps(evaluation_grid, ensure_ascii=False, indent=2)
    
    system_instruction = f"""Tu es un évaluateur d'ECOS (Examen Clinique Objectif Structuré).
    Tu analyses la performance de l'étudiant et remplis la grille d'évaluation de manière OBJECTIVE.

    [CONTEXTE DU CAS]
    {case_context}

    [GRILLE D'ÉVALUATION]
    {grid_json}

    FORMAT DE SORTIE (OBLIGATOIRE):
    Tu retournes UNIQUEMENT un JSON valide (sans ```), au format:
    {{
    "evaluation": {{
        "items": [
        {{
            "item_id": "...",
            "edn_code": "...",
            "criterion": "...",
            "points_awarded": 0,
            "points_possible": 1,
            "is_validated": false,
            "justification": "..."
        }}
        ],
        "total_score": 0,
        "total_possible": 0,
        "percentage": 0.0,
        "general_feedback": "..."
    }}
    }}

    RÈGLES CRITIQUES (ANTI-HALLUCINATION):
    - Tu dois te baser UNIQUEMENT sur le transcript fourni.
    - Tu n'attribues des points (points_awarded > 0) QUE si tu fournis au moins UNE citation EXACTE du transcript (copier-coller mot pour mot, entre guillemets).
    - Si tu ne peux pas citer exactement, alors points_awarded=0 et is_validated=false.
    - N'invente jamais de citations.

    COUVERTURE OBLIGATOIRE:
    - Tu dois produire exactement un item de sortie pour CHAQUE item de la grille.
    - Ne fusionne pas les items. Ne supprime pas d'items.
    - Conserve item_id, edn_code, criterion et points_possible exactement comme dans la grille.

    SCORING:
    - points_awarded est 0 ou points_possible (pas de demi-points), sauf si la grille indique explicitement qu'un item accepte des points partiels.
    - Si un item est composite (ex: "Traitements et allergies"), il n'est validé QUE si tous les éléments sont présents explicitement dans le transcript.

    STYLE DES JUSTIFICATIONS:
    - Si validé: commence par la/les citation(s) exacte(s) entre guillemets, puis une explication courte.
    - Si non validé: explique brièvement ce qui manque, sans inventer.

    IMPORTANT (clinique réaliste):
    - Ne pénalise pas l'absence d'annonce de structure.
    - Pour la mise en confiance, compte toute empathie verbalisée explicite.
    """
    
    logger.info(f"📤 Envoi évaluation à vLLM (modèle: {model})")
    logger.info(f"📝 Transcript: {len(transcript)} caractères")
    
    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": f"Voici le transcript complet:\n\n{transcript}"}
    ]
    
    for attempt in range(MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.2,
                max_tokens=4096,
            )
            
            if not response.choices:
                logger.error("❌ Aucun choix dans la réponse vLLM")
                raise ValueError("Aucun choix retourné par vLLM")
            
            result_text = response.choices[0].message.content
            if not result_text:
                logger.error("❌ Contenu vide dans la réponse vLLM")
                logger.error(f"❌ Réponse complète: {response}")
                raise ValueError("Contenu vide retourné par vLLM")
            
            result_text = result_text.strip()
            logger.info(f"📥 Réponse vLLM ({len(result_text)} caractères)")
            
            # Nettoyer le JSON si entouré de markdown
            if result_text.startswith("```json"):
                result_text = result_text[7:]
            if result_text.startswith("```"):
                result_text = result_text[3:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]
            result_text = result_text.strip()
            
            # Nettoyer les échappements invalides
            
            import re
            
            # Remplacer les séquences d'échappement invalides par des versions correctes
            
            result_text = re.sub(r'\\([^"\\/bfnrtu])', r'\\\\\1', result_text)
            
            try:
                return json.loads(result_text)
            except json.JSONDecodeError as json_err:
                logger.error(f"❌ Erreur parsing JSON: {json_err}")
                logger.error(f"❌ Réponse: {result_text[:500]}...")
                raise ValueError(f"JSON invalide du LLM: {json_err}")
                
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                delay = min(INITIAL_RETRY_DELAY * (2 ** attempt), MAX_RETRY_DELAY)
                logger.warning(f"Erreur évaluation vLLM (tentative {attempt + 1}/{MAX_RETRIES}): {e}")
                time.sleep(delay)
            else:
                logger.error(f"❌ Échec évaluation après {MAX_RETRIES} tentatives")
                raise
