# vllm_chat_utils.py
"""
Patient simulé SANS outils (agent désactivé : PATIENT_AGENT_ENABLED=false), via un serveur
vLLM compatible OpenAI. Le chemin normal est l'agent avec outils (patient_agent.py) ; la
correction automatique est dans evaluation_service.py.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Dict, List, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)

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


def generate_patient_reply_vllm(
    patient_prompt: str,
    history: List[Dict[str, str]],
    student_message: str,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """Réponse du patient en un seul appel (sans outils). Appelée dans un thread."""
    base_url = base_url or os.getenv("VLLM_BASE_URL", "http://localhost:8001/v1")
    model = model or os.getenv("VLLM_MODEL", "Qwen/Qwen3-8B")
    client = OpenAI(base_url=base_url, api_key=os.getenv("VLLM_API_KEY", "dummy-key"),
                    timeout=float(os.getenv("PATIENT_AGENT_TIMEOUT", "30")), max_retries=0)
    messages = [{"role": "system", "content": build_patient_system_instruction(patient_prompt)}]
    for msg in history:
        if msg["role"] == "student":
            messages.append({"role": "user", "content": msg["content"]})
        elif msg["role"] == "patient":
            messages.append({"role": "assistant", "content": msg["content"]})
    messages.append({"role": "user", "content": student_message})
    extra = {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}} if "qwen3" in model.lower() else {}

    for attempt in range(MAX_RETRIES):
        try:
            response = client.chat.completions.create(model=model, messages=messages, temperature=0.4,
                                                      max_tokens=160, top_p=0.9, **extra)
            reply = (response.choices[0].message.content if response.choices else "") or ""
            if not reply.strip():
                raise ValueError("réponse vide")
            return reply.strip()
        except Exception as exc:  # noqa: BLE001
            if attempt == MAX_RETRIES - 1:
                logger.error("Patient (sans outils) : échec après %d essais (%s)", MAX_RETRIES, type(exc).__name__)
                raise
            delay = min(INITIAL_RETRY_DELAY * (2 ** attempt), MAX_RETRY_DELAY)
            logger.warning("Patient (sans outils) : essai %d échoué (%s)", attempt + 1, type(exc).__name__)
            time.sleep(delay)
    raise RuntimeError("inaccessible")
