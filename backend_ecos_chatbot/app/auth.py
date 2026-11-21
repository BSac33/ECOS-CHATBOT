"""
Authentification (JWT en cookie HttpOnly) et autorisation par rôle.

Benjamin Sacristan - 2026
"""
from __future__ import annotations

import logging
import os
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Annotated, Callable, Deque, Dict, Optional

import jwt
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from db import get_session
from models import User, UserRole

logger = logging.getLogger(__name__)

router = APIRouter()

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable not set")

ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
SECURE_COOKIES = os.getenv("SECURE_COOKIES", "False").lower() == "true"  # True en production (HTTPS)
MIN_PASSWORD_LENGTH = 8

BAD_CREDENTIALS = "Identifiant ou mot de passe incorrect."
NOT_AUTHENTICATED = "Connexion requise."

password_hash = PasswordHash.recommended()
# Vérification factice quand le compte n'existe pas : même temps de réponse (pas d'énumération)
_DUMMY_HASH = password_hash.hash("compte-inexistant")

# Swagger (développement) : jeton aussi accepté dans l'en-tête Authorization
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)


def get_token(access_token_cookie: Optional[str] = Cookie(None, alias="access_token"),
              authorization: Optional[str] = Depends(oauth2_scheme)) -> str:
    """Jeton JWT : cookie « access_token » (frontend), sinon en-tête Authorization."""
    token = access_token_cookie or authorization
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, NOT_AUTHENTICATED, headers={"WWW-Authenticate": "Bearer"})
    return token


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64, pattern=r"^[A-Za-z0-9._@-]+$")
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=256)
    role: UserRole = UserRole.student
    full_name: Optional[str] = Field(default=None, max_length=200)


class LoginResponse(BaseModel):
    message: str


# ==================== OUTILS ====================

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return password_hash.hash(password)


def get_user(session: Session, username: str) -> Optional[User]:
    return session.exec(select(User).where(User.username == username)).first()


def authenticate_user(session: Session, username: str, password: str) -> Optional[User]:
    """L'utilisateur si identifiant et mot de passe sont bons, sinon None (même durée dans tous les cas)."""
    user = get_user(session, username)
    if user is None:
        password_hash.verify(password, _DUMMY_HASH)
        return None
    return user if verify_password(password, user.hashed_password) else None


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=15))
    return jwt.encode({**data, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


# ==================== LIMITATION DES ESSAIS DE CONNEXION ====================

class LoginThrottle:
    """Au-delà de N échecs en WINDOW secondes, les essais sont refusés (429) jusqu'à ce que la
    fenêtre se libère : 5 par identifiant, 30 par adresse (un campus sort souvent par une seule
    adresse : un seuil bas bloquerait toute la faculté). Mémoire du processus : complété par la
    limite de débit de nginx (frontend/nginx.conf)."""

    LIMITS = {"u": 5, "ip": 30}
    WINDOW = 15 * 60

    def __init__(self) -> None:
        self._failures: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> Deque[float]:
        q = self._failures[key]
        while q and now - q[0] > self.WINDOW:
            q.popleft()
        return q

    def blocked(self, *keys: str) -> bool:
        now = time.monotonic()
        with self._lock:
            return any(len(self._recent(k, now)) >= self.LIMITS.get(k.split(":", 1)[0], 5) for k in keys)

    def failure(self, *keys: str) -> None:
        now = time.monotonic()
        with self._lock:
            for k in keys:
                self._recent(k, now).append(now)

    def success(self, *keys: str) -> None:
        with self._lock:
            for k in keys:
                self._failures.pop(k, None)


login_throttle = LoginThrottle()


# ==================== DÉPENDANCES ====================

ROLE_LEVEL = {UserRole.student: 1, UserRole.teacher: 2, UserRole.admin: 3}


def get_current_user(session: Annotated[Session, Depends(get_session)],
                     token: Annotated[str, Depends(get_token)]) -> User:
    """Utilisateur du jeton, relu en base à chaque requête (dépendance synchrone : exécutée
    dans un thread, jamais dans la boucle async)."""
    try:
        username = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM]).get("sub")
    except InvalidTokenError:
        username = None
    user = get_user(session, username) if username else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, NOT_AUTHENTICATED, headers={"WWW-Authenticate": "Bearer"})
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Compte désactivé.")
    return user


def check_authorization(required_role: UserRole = UserRole.student) -> Callable[..., User]:
    def _check(user: User = Depends(get_current_user)) -> User:
        if ROLE_LEVEL[user.role] < ROLE_LEVEL[required_role]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Accès réservé.")
        return user
    return _check


# ==================== ROUTES ====================

@router.post("/create-user", status_code=status.HTTP_201_CREATED)
def create_user(payload: CreateUserRequest, session: Annotated[Session, Depends(get_session)],
                admin: Annotated[User, Depends(check_authorization(UserRole.admin))]):
    """Création d'un compte, réservée aux administrateurs (en ligne de commande :
    scripts/create_user.py)."""
    if get_user(session, payload.username):
        raise HTTPException(status.HTTP_409_CONFLICT, "Cet identifiant existe déjà.")
    user = User(username=payload.username, hashed_password=get_password_hash(payload.password),
                role=payload.role, full_name=payload.full_name, is_active=True)
    session.add(user)
    session.commit()
    logger.info("Compte créé par %s : %s (%s)", admin.username, payload.username, payload.role.value)
    return {"msg": "Compte créé."}


@router.post("/token", response_model=LoginResponse)
def login_for_access_token(request: Request, response: Response,
                           form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
                           session: Annotated[Session, Depends(get_session)]):
    keys = (f"u:{form_data.username.lower()}", f"ip:{request.client.host if request.client else '?'}")
    if login_throttle.blocked(*keys):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "Trop de tentatives de connexion. Réessayez dans quelques minutes.")
    user = authenticate_user(session, form_data.username, form_data.password)
    if user is None:
        login_throttle.failure(*keys)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, BAD_CREDENTIALS, headers={"WWW-Authenticate": "Bearer"})
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Compte désactivé.")
    login_throttle.success(keys[0])
    token = create_access_token({"sub": user.username, "role": user.role},
                                timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    response.set_cookie(key="access_token", value=token, httponly=True, samesite="lax", secure=SECURE_COOKIES,
                        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60, path="/")
    return {"message": "ok"}


@router.post("/logout", status_code=status.HTTP_200_OK)
def logout(response: Response):
    response.delete_cookie(key="access_token", path="/")
    return {"message": "Déconnecté."}
