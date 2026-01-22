#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import json
from typing import Optional, Any, Dict, List
from pathlib import Path

import httpx
import typer

app = typer.Typer(add_completion=False, help="CLI pour tester le chatbot / routes FastAPI (Attempts + Chat).")

# Fichier pour stocker les cookies de session
COOKIE_FILE = Path.home() / ".ecos_cookies.json"


def _base_url() -> str:
    return os.getenv("ECOS_BASE_URL", "http://localhost:8000").rstrip("/")


def _save_cookies(cookies: httpx.Cookies) -> None:
    """Sauvegarde les cookies dans un fichier."""
    cookie_dict = {name: value for name, value in cookies.items()}
    COOKIE_FILE.write_text(json.dumps(cookie_dict))


def _load_cookies() -> httpx.Cookies:
    """Charge les cookies depuis le fichier."""
    if COOKIE_FILE.exists():
        try:
            cookie_dict = json.loads(COOKIE_FILE.read_text())
            cookies = httpx.Cookies()
            for name, value in cookie_dict.items():
                cookies.set(name, value)
            return cookies
        except Exception:
            pass
    return httpx.Cookies()


def _clear_cookies() -> None:
    """Supprime les cookies sauvegardés."""
    if COOKIE_FILE.exists():
        COOKIE_FILE.unlink()


def _auth_headers(token: Optional[str]) -> Dict[str, str]:
    """Headers d'authentification par token (fallback si pas de cookies)."""
    token = token or os.getenv("ECOS_TOKEN")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def _client(token: Optional[str] = None, timeout: float = 30.0, use_cookies: bool = True) -> httpx.Client:
    """Client HTTP avec support cookies + token."""
    cookies = _load_cookies() if use_cookies else None
    
    return httpx.Client(
        base_url=_base_url(),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            **_auth_headers(token),
        },
        cookies=cookies,
        timeout=timeout,
    )


def _print_json(data: Any) -> None:
    typer.echo(json.dumps(data, ensure_ascii=False, indent=2))


@app.command("login")
def login(
    username: Optional[str] = typer.Option(None, "--username", "-u", help="Nom d'utilisateur"),
    password: Optional[str] = typer.Option(None, "--password", "-p", help="Mot de passe"),
) -> None:
    """
    Se connecter et sauvegarder la session (cookies).
    """
    # Demander les identifiants si non fournis
    if not username:
        username = typer.prompt("Username")
    if not password:
        password = typer.prompt("Password", hide_input=True)
    
    # Appeler /auth/token avec form-data
    with httpx.Client(base_url=_base_url()) as c:
        r = c.post(
            "/auth/token",
            data={
                "username": username,
                "password": password,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        
        if r.is_error:
            typer.secho(f"❌ Échec de la connexion ({r.status_code}): {r.text}", fg=typer.colors.RED)
            raise typer.Exit(1)
        
        # Sauvegarder les cookies
        _save_cookies(r.cookies)
        
        typer.secho(f"✅ Connecté avec succès en tant que {username}", fg=typer.colors.GREEN)
        typer.echo()
        typer.secho("💡 Utilisez 'list-cases' pour voir les cas disponibles", fg=typer.colors.CYAN)


@app.command("logout")
def logout() -> None:
    """
    Se déconnecter et supprimer la session.
    """
    with _client() as c:
        try:
            c.post("/auth/logout")
        except Exception:
            pass
    
    _clear_cookies()
    typer.secho("✅ Déconnecté avec succès", fg=typer.colors.GREEN)


@app.command("list-cases")
def list_cases(
    station_type: Optional[str] = typer.Option(None, "--type", "-t", help="Filtrer par type de station"),
    discipline: Optional[str] = typer.Option(None, "--discipline", "-d", help="Filtrer par discipline"),
) -> None:
    """
    Liste tous les cas cliniques disponibles.
    """
    with _client() as c:
        params = {}
        if station_type:
            params["station_type"] = station_type
        if discipline:
            params["discipline"] = discipline
        
        r = c.get("/api/cases", params=params)
        
        if r.is_error:
            if r.status_code == 401:
                typer.secho("❌ Non authentifié. Utilisez 'login' d'abord.", fg=typer.colors.RED)
            else:
                typer.secho(f"Erreur {r.status_code}: {r.text}", fg=typer.colors.RED)
            raise typer.Exit(1)
        
        cases = r.json()
        
        if not cases:
            typer.secho("Aucun cas clinique trouvé.", fg=typer.colors.YELLOW)
            return
        
        typer.secho(f"\n📚 CAS CLINIQUES DISPONIBLES ({len(cases)})", fg=typer.colors.CYAN, bold=True)
        typer.secho("="*80, fg=typer.colors.CYAN)
        typer.echo()
        
        for case in cases:
            case_id = case.get("id")
            title = case.get("title", "Sans titre")
            station_type = case.get("station_type", "N/A")
            duration = case.get("duration_seconds", 0) // 60
            disciplines = ", ".join(case.get("disciplines", []))
            has_eval = "✅" if case.get("has_evaluation_grid") else "❌"
            
            typer.secho(f"ID: {case_id}", fg=typer.colors.GREEN, bold=True)
            typer.echo(f"   📝 {title}")
            typer.echo(f"   🏥 Type: {station_type}")
            typer.echo(f"   ⏱️  Durée: {duration} minutes")
            typer.echo(f"   📖 Disciplines: {disciplines}")
            typer.echo(f"   📊 Grille d'évaluation: {has_eval}")
            typer.echo()
            typer.secho(f"   ▶️  Lancer: python ecos_cli.py chat-loop {case_id}", fg=typer.colors.YELLOW, dim=True)
            typer.echo()
        
        typer.secho("="*80, fg=typer.colors.CYAN)


@app.command("start")
def start() -> None:
    """
    Workflow complet: login + liste des cas + lancement d'un cas.
    """
    typer.secho("\n🏥 ECOS CHATBOT - Interface CLI", fg=typer.colors.BLUE, bold=True)
    typer.secho("="*60, fg=typer.colors.BLUE)
    typer.echo()
    
    # Étape 1: Login
    typer.secho("📝 CONNEXION", fg=typer.colors.CYAN, bold=True)
    typer.secho("-"*60, fg=typer.colors.CYAN)
    
    username = typer.prompt("Username")
    password = typer.prompt("Password", hide_input=True)
    
    # Appeler /auth/token
    with httpx.Client(base_url=_base_url()) as c:
        r = c.post(
            "/auth/token",
            data={"username": username, "password": password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        
        if r.is_error:
            typer.secho(f"\n❌ Échec de la connexion ({r.status_code})", fg=typer.colors.RED)
            raise typer.Exit(1)
        
        # Sauvegarder les cookies
        _save_cookies(r.cookies)
        typer.secho(f"✅ Connecté en tant que {username}\n", fg=typer.colors.GREEN)
    
    # Étape 2: Liste des cas
    typer.secho("📚 CAS CLINIQUES DISPONIBLES", fg=typer.colors.CYAN, bold=True)
    typer.secho("-"*60, fg=typer.colors.CYAN)
    typer.echo()
    
    with _client() as c:
        r = c.get("/api/cases")
        if r.is_error:
            typer.secho(f"❌ Erreur lors de la récupération des cas: {r.text}", fg=typer.colors.RED)
            raise typer.Exit(1)
        
        cases = r.json()
        
        if not cases:
            typer.secho("Aucun cas clinique disponible.", fg=typer.colors.YELLOW)
            raise typer.Exit(0)
        
        # Afficher les cas de manière condensée
        for i, case in enumerate(cases, 1):
            case_id = case.get("id")
            title = case.get("title", "Sans titre")
            station_type = case.get("station_type", "N/A")
            duration = case.get("duration_seconds", 0) // 60
            
            typer.secho(f"{i}. ", fg=typer.colors.YELLOW, nl=False)
            typer.secho(f"[ID: {case_id}] ", fg=typer.colors.GREEN, nl=False, bold=True)
            typer.echo(f"{title}")
            typer.echo(f"   Type: {station_type} | Durée: {duration}min")
        
        typer.echo()
        
        # Étape 3: Choix du cas
        try:
            choice = typer.prompt("\nChoisissez un cas (numéro ou ID)", type=str)
            
            # Essayer de parser comme numéro ou ID
            if choice.isdigit():
                choice_num = int(choice)
                # Vérifier si c'est un numéro de liste (1-indexed)
                if 1 <= choice_num <= len(cases):
                    selected_case = cases[choice_num - 1]
                else:
                    # Sinon c'est peut-être un ID direct
                    selected_case = next((c for c in cases if c["id"] == choice_num), None)
                    if not selected_case:
                        typer.secho("❌ Cas introuvable", fg=typer.colors.RED)
                        raise typer.Exit(1)
            else:
                typer.secho("❌ Choix invalide", fg=typer.colors.RED)
                raise typer.Exit(1)
            
            case_id = selected_case["id"]
            case_title = selected_case["title"]
            
            typer.echo()
            typer.secho(f"🚀 Lancement du cas: {case_title}", fg=typer.colors.GREEN, bold=True)
            typer.echo()
            
            # Étape 4: Lancer le chat-loop
            # Créer l'attempt
            r = c.post("chat/attempts", json={"case_id": case_id})
            if r.is_error:
                typer.secho(f"❌ Erreur lors de la création de l'attempt: {r.text}", fg=typer.colors.RED)
                raise typer.Exit(1)
            
            attempt = r.json()
            attempt_id = attempt.get("id") or attempt.get("attempt_id")
            
            typer.secho(f"✅ Attempt créée: {attempt_id}", fg=typer.colors.GREEN)
            typer.echo()
            
            # Récupérer et afficher les consignes
            msgs_resp = c.get(f"chat/attempts/{attempt_id}/messages")
            if not msgs_resp.is_error:
                messages = msgs_resp.json()
                for msg in messages:
                    if msg.get("role") == "system":
                        typer.secho("📋 CONSIGNES:", fg=typer.colors.BLUE, bold=True)
                        typer.secho("="*60, fg=typer.colors.BLUE)
                        typer.echo(msg.get('content'))
                        typer.secho("="*60, fg=typer.colors.BLUE)
                        typer.echo()
                        break
            
            # Afficher la durée
            duration_mins = selected_case.get("duration_seconds", 0) // 60
            if duration_mins:
                typer.secho(f"⏱️  Durée: {duration_mins} minutes", fg=typer.colors.YELLOW)
                typer.echo()
            
            typer.secho("💬 CONVERSATION", fg=typer.colors.CYAN, bold=True)
            typer.secho("Commandes: /history, /time, /finalize, /quit", fg=typer.colors.WHITE, dim=True)
            typer.secho("-"*60, fg=typer.colors.CYAN)
            typer.echo()
            
            # Boucle de conversation
            while True:
                try:
                    user_in = typer.prompt("ÉTUDIANT", prompt_suffix=" > ").strip()
                except (KeyboardInterrupt, EOFError):
                    typer.echo("\n👋 Au revoir!")
                    return
                
                if not user_in:
                    continue
                
                if user_in in ("/quit", "/exit"):
                    typer.echo("👋 Au revoir!")
                    return
                
                if user_in == "/history":
                    rr = c.get(f"chat/attempts/{attempt_id}/messages")
                    if rr.is_error:
                        typer.secho(f"❌ Erreur: {rr.text}", fg=typer.colors.RED)
                    else:
                        _print_json(rr.json())
                    continue
                
                if user_in == "/time":
                    rr = c.get(f"chat/attempts/{attempt_id}/time-remaining")
                    if rr.is_error:
                        typer.secho(f"❌ Erreur: {rr.text}", fg=typer.colors.RED)
                    else:
                        time_data = rr.json()
                        if time_data.get("is_expired"):
                            typer.secho(f"⏱️  {time_data.get('message', 'Temps écoulé')}", fg=typer.colors.RED)
                        else:
                            secs = time_data.get("seconds_remaining")
                            if secs is not None:
                                mins = secs // 60
                                secs_left = secs % 60
                                color = typer.colors.GREEN if secs > 120 else typer.colors.YELLOW if secs > 60 else typer.colors.RED
                                typer.secho(f"⏱️  Temps restant: {mins}m {secs_left}s", fg=color)
                            else:
                                typer.secho("⏱️  Pas de limite de temps", fg=typer.colors.GREEN)
                    continue
                
                if user_in == "/finalize":
                    rr = c.post(f"chat/attempts/{attempt_id}/finalize")
                    if rr.is_error:
                        typer.secho(f"❌ Erreur: {rr.text}", fg=typer.colors.RED)
                    else:
                        typer.secho("✅ Attempt finalisée.", fg=typer.colors.GREEN)
                        typer.echo()
                        typer.secho("💡 Pour évaluer:", fg=typer.colors.YELLOW)
                        typer.secho(f"   python ecos_cli.py attempt-evaluate {attempt_id}", fg=typer.colors.CYAN)
                        typer.echo()
                    return
                
                # Envoyer le message
                rr = c.post(f"chat/attempts/{attempt_id}/chat", json={"message": user_in})
                if rr.is_error:
                    if rr.status_code == 408:
                        typer.secho("\n⏰ TEMPS ÉCOULÉ!", fg=typer.colors.RED, bold=True)
                        typer.echo()
                        typer.secho("💡 Pour évaluer:", fg=typer.colors.YELLOW)
                        typer.secho(f"   python ecos_cli.py attempt-evaluate {attempt_id}", fg=typer.colors.CYAN)
                        typer.echo()
                        return
                    else:
                        typer.secho(f"❌ Erreur: {rr.text}", fg=typer.colors.RED)
                    continue
                
                data = rr.json()
                if isinstance(data, dict) and "patient_reply" in data:
                    typer.secho("PATIENT", fg=typer.colors.CYAN, bold=True, nl=False)
                    typer.echo(f" > {data['patient_reply']}")
                else:
                    _print_json(data)
        
        except (KeyboardInterrupt, EOFError):
            typer.echo("\n👋 Au revoir!")
            return


@app.command("health")
def health() -> None:
    """Ping rapide du serveur."""
    with _client(token=None) as c:
        r = c.get("/")
        typer.echo(f"{r.status_code} {r.text[:200]}")


@app.command("attempt-create")
def attempt_create(
    case_id: int = typer.Argument(..., help="ID du cas clinique"),
) -> None:
    """
    Crée une attempt pour un case_id.
    Endpoint attendu: POST /chat/attempts {case_id}
    """
    payload = {"case_id": case_id}
    with _client() as c:
        r = c.post("chat/attempts", json=payload)
        if r.is_error:
            if r.status_code == 401:
                typer.secho("❌ Non authentifié. Utilisez 'login' d'abord.", fg=typer.colors.RED)
            else:
                typer.secho(f"Erreur {r.status_code}: {r.text}", fg=typer.colors.RED)
            raise typer.Exit(1)
        _print_json(r.json())


@app.command("attempt-messages")
def attempt_messages(
    attempt_id: int = typer.Argument(..., help="ID de l'attempt"),
) -> None:
    """
    Récupère l'historique d'une attempt.
    Endpoint attendu: GET /chat/attempts/{attempt_id}/messages
    """
    with _client() as c:
        r = c.get(f"chat/attempts/{attempt_id}/messages")
        if r.is_error:
            typer.secho(f"Erreur {r.status_code}: {r.text}", fg=typer.colors.RED)
            raise typer.Exit(1)
        _print_json(r.json())


@app.command("attempt-chat")
def attempt_chat(
    attempt_id: int = typer.Argument(..., help="ID de l'attempt"),
    message: str = typer.Argument(..., help="Message étudiant"),
) -> None:
    """
    Envoie un message étudiant et récupère la réponse patient.
    Endpoint attendu: POST /chat/attempts/{attempt_id}/chat {message}
    """
    payload = {"message": message}
    with _client() as c:
        r = c.post(f"chat/attempts/{attempt_id}/chat", json=payload)
        if r.is_error:
            typer.secho(f"Erreur {r.status_code}: {r.text}", fg=typer.colors.RED)
            raise typer.Exit(1)
        data = r.json()
        # Affichage sympa si la réponse est au format {patient_reply: "..."}
        if isinstance(data, dict) and "patient_reply" in data:
            typer.secho("\nPATIENT >", fg=typer.colors.CYAN, nl=False)
            typer.echo(f" {data['patient_reply']}\n")
        else:
            _print_json(data)


@app.command("attempt-finalize")
def attempt_finalize(
    attempt_id: int = typer.Argument(..., help="ID de l'attempt"),
) -> None:
    """
    Finalise une attempt.
    Endpoint attendu: POST /chat/attempts/{attempt_id}/finalize
    """
    with _client() as c:
        r = c.post(f"chat/attempts/{attempt_id}/finalize")
        if r.is_error:
            typer.secho(f"Erreur {r.status_code}: {r.text}", fg=typer.colors.RED)
            raise typer.Exit(1)
        _print_json(r.json())


@app.command("attempt-evaluate")
def attempt_evaluate(
    attempt_id: str = typer.Argument(..., help="UUID de l'attempt à évaluer"),
) -> None:
    """
    Évalue une attempt finalisée avec la grille d'évaluation.
    Endpoint attendu: POST /evaluation/attempts/{attempt_id}/evaluate
    """
    with _client(timeout=60.0) as c:  # Timeout plus long pour l'évaluation
        typer.secho(f"⏳ Évaluation en cours de l'attempt {attempt_id}...", fg=typer.colors.YELLOW)
        r = c.post(f"evaluation/attempts/{attempt_id}/evaluate")
        if r.is_error:
            typer.secho(f"Erreur {r.status_code}: {r.text}", fg=typer.colors.RED)
            raise typer.Exit(1)
        
        data = r.json()
        
        # Affichage formaté de l'évaluation
        if "evaluation" in data:
            eval_data = data["evaluation"]
            typer.secho("\n" + "="*60, fg=typer.colors.GREEN)
            typer.secho("📊 RÉSULTAT DE L'ÉVALUATION", fg=typer.colors.GREEN, bold=True)
            typer.secho("="*60 + "\n", fg=typer.colors.GREEN)
            
            # Score global
            total = eval_data.get("total_score", 0)
            possible = eval_data.get("total_possible", 20)
            percentage = eval_data.get("percentage", 0)
            
            color = typer.colors.GREEN if percentage >= 70 else typer.colors.YELLOW if percentage >= 50 else typer.colors.RED
            typer.secho(f"Score: {total}/{possible} points ({percentage:.1f}%)", fg=color, bold=True)
            typer.echo()
            
            # Items détaillés
            typer.secho("📋 Détail par critère:\n", fg=typer.colors.CYAN)
            for item in eval_data.get("items", []):
                awarded = item.get("points_awarded", 0)
                possible_item = item.get("points_possible", 0)
                is_validated = item.get("is_validated", False)
                
                icon = "✅" if is_validated else "❌"
                criterion = item.get("criterion", "N/A")
                edn_code = item.get("edn_code")
                edn_str = f"[EDN {edn_code}] " if edn_code else ""
                
                typer.secho(f"{icon} {edn_str}{criterion}", bold=True)
                typer.secho(f"   {awarded}/{possible_item} points", fg=typer.colors.WHITE)
                
                justification = item.get("justification", "")
                if justification:
                    # Affichage de la justification avec indentation
                    for line in justification.split("\n"):
                        typer.secho(f"   {line}", fg=typer.colors.WHITE, dim=True)
                typer.echo()
            
            # Feedback général
            feedback = eval_data.get("general_feedback", "")
            if feedback:
                typer.secho("💬 Feedback général:", fg=typer.colors.MAGENTA, bold=True)
                typer.echo()
                for line in feedback.split("\n"):
                    typer.secho(f"   {line}", fg=typer.colors.WHITE)
                typer.echo()
            
            typer.secho("="*60, fg=typer.colors.GREEN)
        else:
            _print_json(data)


@app.command("attempt-transcript")
def attempt_transcript(
    attempt_id: str = typer.Argument(..., help="UUID de l'attempt"),
) -> None:
    """
    Affiche le transcript complet d'une attempt.
    Endpoint attendu: GET /evaluation/attempts/{attempt_id}/transcript
    """
    with _client() as c:
        r = c.get(f"evaluation/attempts/{attempt_id}/transcript")
        if r.is_error:
            typer.secho(f"Erreur {r.status_code}: {r.text}", fg=typer.colors.RED)
            raise typer.Exit(1)
        
        data = r.json()
        
        # Affichage formaté du transcript
        typer.secho("\n" + "="*60, fg=typer.colors.BLUE)
        typer.secho("📝 TRANSCRIPT DE LA CONVERSATION", fg=typer.colors.BLUE, bold=True)
        typer.secho("="*60 + "\n", fg=typer.colors.BLUE)
        
        transcript = data.get("transcript", "")
        if transcript:
            typer.echo(transcript)
        else:
            _print_json(data)
        
        typer.secho("\n" + "="*60, fg=typer.colors.BLUE)


@app.command("user-attempts")
def user_attempts(
    completed: Optional[bool] = typer.Option(None, "--completed", help="Filtrer par statut (--completed/--no-completed)"),
    case_id: Optional[int] = typer.Option(None, "--case-id", help="Filtrer par cas clinique"),
    limit: int = typer.Option(20, "--limit", "-l", help="Nombre de résultats"),
) -> None:
    """
    Liste toutes les tentatives de l'utilisateur avec statistiques.
    Endpoint: GET /api/users/me/attempts
    """
    with _client() as c:
        params = {"limit": limit}
        if completed is not None:
            params["completed"] = str(completed).lower()
        if case_id is not None:
            params["case_id"] = case_id
        
        r = c.get("api/users/me/attempts", params=params)
        if r.is_error:
            typer.secho(f"Erreur {r.status_code}: {r.text}", fg=typer.colors.RED)
            raise typer.Exit(1)
        
        data = r.json()
        
        # Affichage des statistiques
        stats = data.get("stats", {})
        typer.secho("\n📊 STATISTIQUES", fg=typer.colors.CYAN, bold=True)
        typer.secho("="*60, fg=typer.colors.CYAN)
        typer.echo(f"Total tentatives: {stats.get('total_attempts', 0)}")
        typer.echo(f"Complétées: {stats.get('completed_attempts', 0)}")
        typer.echo(f"En cours: {stats.get('in_progress_attempts', 0)}")
        typer.echo(f"Messages envoyés: {stats.get('total_messages', 0)}")
        typer.echo(f"Cas tentés: {len(stats.get('cases_attempted', []))}")
        typer.echo()
        
        # Affichage des tentatives
        attempts = data.get("attempts", [])
        if not attempts:
            typer.secho("Aucune tentative trouvée.", fg=typer.colors.YELLOW)
            return
        
        typer.secho(f"📋 TENTATIVES ({len(attempts)})", fg=typer.colors.GREEN, bold=True)
        typer.secho("="*60, fg=typer.colors.GREEN)
        
        for attempt in attempts:
            status_icon = "✅" if attempt.get("is_completed") else "🔄"
            status_color = typer.colors.GREEN if attempt.get("is_completed") else typer.colors.YELLOW
            
            typer.echo()
            typer.secho(f"{status_icon} {attempt.get('case_title')}", fg=status_color, bold=True)
            typer.echo(f"   ID: {attempt.get('id')}")
            typer.echo(f"   Type: {attempt.get('station_type')}")
            typer.echo(f"   Case ID: {attempt.get('case_id')}")
            typer.echo(f"   Créée: {attempt.get('created_at')}")
            
            if attempt.get("is_completed"):
                typer.echo(f"   Terminée: {attempt.get('completed_at')}")
                duration = attempt.get("duration_seconds")
                if duration:
                    minutes = duration // 60
                    seconds = duration % 60
                    typer.echo(f"   Durée: {minutes}m {seconds}s")
            
            typer.echo(f"   Messages: {attempt.get('message_count', 0)}")
        
        typer.echo()
        typer.secho("="*60, fg=typer.colors.GREEN)


@app.command("user-stats")
def user_stats() -> None:
    """
    Affiche les statistiques de l'utilisateur.
    Endpoint: GET /api/users/me/stats
    """
    with _client() as c:
        r = c.get("api/users/me/stats")
        if r.is_error:
            typer.secho(f"Erreur {r.status_code}: {r.text}", fg=typer.colors.RED)
            raise typer.Exit(1)
        
        stats = r.json()
        
        typer.secho("\n📊 STATISTIQUES UTILISATEUR", fg=typer.colors.CYAN, bold=True)
        typer.secho("="*60, fg=typer.colors.CYAN)
        typer.echo()
        
        total = stats.get("total_attempts", 0)
        completed = stats.get("completed_attempts", 0)
        in_progress = stats.get("in_progress_attempts", 0)
        
        typer.secho(f"📈 Total tentatives: {total}", bold=True)
        typer.echo(f"   ✅ Complétées: {completed}")
        typer.echo(f"   🔄 En cours: {in_progress}")
        
        if total > 0:
            completion_rate = (completed / total) * 100
            typer.echo(f"   📊 Taux de complétion: {completion_rate:.1f}%")
        
        typer.echo()
        typer.echo(f"💬 Messages envoyés: {stats.get('total_messages', 0)}")
        typer.echo(f"📚 Cas différents tentés: {len(stats.get('cases_attempted', []))}")
        
        favorite = stats.get("favorite_discipline")
        if favorite:
            typer.echo(f"⭐ Discipline préférée: {favorite}")
        
        typer.echo()
        typer.secho("="*60, fg=typer.colors.CYAN)


@app.command("chat-loop")
def chat_loop(
    case_id: int = typer.Argument(..., help="ID du cas clinique"),
    show_history: bool = typer.Option(False, "--history", help="Affiche l'historique à chaque tour"),
) -> None:
    """
    Mode interactif: crée une attempt puis boucle lecture clavier -> /chat.
    
    Commandes disponibles:
    - /quit ou /exit : Quitter sans finaliser
    - /history : Afficher l'historique des messages
    - /time : Afficher le temps restant
    - /finalize : Terminer et passer à l'évaluation
    """
    # 1) create attempt
    with _client() as c:
        r = c.post("chat/attempts", json={"case_id": case_id})
        if r.is_error:
            typer.secho(f"Erreur create attempt {r.status_code}: {r.text}", fg=typer.colors.RED)
            raise typer.Exit(1)
        attempt = r.json()
        attempt_id = attempt.get("id") or attempt.get("attempt_id")
        if not attempt_id:
            typer.secho("La réponse /attempts ne contient pas 'id'/'attempt_id'.", fg=typer.colors.RED)
            _print_json(attempt)
            raise typer.Exit(1)

        typer.secho(f"✅ Attempt créée: {attempt_id}", fg=typer.colors.GREEN)
        typer.echo()
        
        # Récupérer et afficher les consignes
        msgs_resp = c.get(f"chat/attempts/{attempt_id}/messages")
        if not msgs_resp.is_error:
            messages = msgs_resp.json()
            # Afficher le premier message système (instructions)
            for msg in messages:
                if msg.get("role") == "system":
                    typer.secho("📋 CONSIGNES:", fg=typer.colors.BLUE, bold=True)
                    typer.secho(f"{msg.get('content')}", fg=typer.colors.CYAN)
                    typer.echo()
                    break
        
        # Récupérer le temps alloué
        case_resp = c.get(f"cases/{case_id}")
        duration_mins = None
        if not case_resp.is_error:
            case_data = case_resp.json()
            duration_mins = case_data.get("duration_seconds", 0) // 60
            if duration_mins:
                typer.secho(f"⏱️  Durée: {duration_mins} minutes", fg=typer.colors.YELLOW)
                typer.echo()

        # 2) loop
        while True:
            try:
                user_in = typer.prompt("STUDENT").strip()
            except (KeyboardInterrupt, EOFError):
                typer.echo("\nBye.")
                return

            if not user_in:
                continue

            if user_in in ("/quit", "/exit"):
                typer.echo("Bye.")
                return

            if user_in == "/history":
                rr = c.get(f"chat/attempts/{attempt_id}/messages")
                if rr.is_error:
                    typer.secho(f"Erreur history {rr.status_code}: {rr.text}", fg=typer.colors.RED)
                else:
                    _print_json(rr.json())
                continue
            
            if user_in == "/time":
                rr = c.get(f"chat/attempts/{attempt_id}/time-remaining")
                if rr.is_error:
                    typer.secho(f"Erreur time {rr.status_code}: {rr.text}", fg=typer.colors.RED)
                else:
                    time_data = rr.json()
                    if time_data.get("is_expired"):
                        typer.secho(f"⏱️  {time_data.get('message', 'Temps écoulé')}", fg=typer.colors.RED)
                    else:
                        secs = time_data.get("seconds_remaining")
                        if secs is not None:
                            mins = secs // 60
                            secs_left = secs % 60
                            color = typer.colors.GREEN if secs > 120 else typer.colors.YELLOW if secs > 60 else typer.colors.RED
                            typer.secho(f"⏱️  Temps restant: {mins}m {secs_left}s", fg=color)
                        else:
                            typer.secho("⏱️  Pas de limite de temps", fg=typer.colors.GREEN)
                continue

            if user_in == "/finalize":
                rr = c.post(f"chat/attempts/{attempt_id}/finalize")
                if rr.is_error:
                    typer.secho(f"Erreur finalize {rr.status_code}: {rr.text}", fg=typer.colors.RED)
                else:
                    typer.secho("✅ Attempt finalisée.", fg=typer.colors.GREEN)
                    _print_json(rr.json())
                    typer.echo()
                    typer.secho("💡 Pour évaluer cette attempt:", fg=typer.colors.YELLOW)
                    typer.secho(f"   python ecos_cli.py attempt-evaluate {attempt_id}", fg=typer.colors.CYAN)
                    typer.echo()
                return

            # send chat
            rr = c.post(f"chat/attempts/{attempt_id}/chat", json={"message": user_in})
            if rr.is_error:
                # Gérer l'erreur 408 (timeout)
                if rr.status_code == 408:
                    typer.secho("⏱️  ⏰ TEMPS ÉCOULÉ!", fg=typer.colors.RED, bold=True)
                    typer.echo()
                    error_data = rr.json() if rr.text else {}
                    error_msg = error_data.get("detail", "Le temps imparti est écoulé.")
                    typer.secho(error_msg, fg=typer.colors.YELLOW)
                    typer.echo()
                    typer.secho("💡 Pour évaluer cette attempt:", fg=typer.colors.YELLOW)
                    typer.secho(f"   python ecos_cli.py attempt-evaluate {attempt_id}", fg=typer.colors.CYAN)
                    typer.echo()
                    return
                else:
                    typer.secho(f"Erreur chat {rr.status_code}: {rr.text}", fg=typer.colors.RED)
                continue

            data = rr.json()
            if isinstance(data, dict) and "patient_reply" in data:
                typer.secho("PATIENT", fg=typer.colors.CYAN, nl=False)
                typer.echo(f": {data['patient_reply']}")
            else:
                _print_json(data)

            if show_history:
                hh = c.get(f"chat/attempts/{attempt_id}/messages")
                if not hh.is_error:
                    typer.echo("\n--- HISTORY ---")
                    _print_json(hh.json())
                    typer.echo("---------------\n")


def main() -> None:
    app()


if __name__ == "__main__":
    main()