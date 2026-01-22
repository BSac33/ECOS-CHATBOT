'''
Logique d'authentification / autorisation pour l'API

Benjamin Sacristan - 2026

'''

from datetime import datetime, timedelta, timezone
from math import e, log
import stat
from typing import Optional, Annotated, Callable
from annotated_types import T
from fastapi import APIRouter, Depends, HTTPException, Response, status, Request, Cookie
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import jwt
from pwdlib import PasswordHash
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel, Field
from sqlmodel import Session
from urllib3 import HTTPResponse
from db import get_session
from models import User, UserRole, UserOut
from uuid import UUID
import os
import logging

from sqlmodel import select


# logging configuration
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

handler = logging.StreamHandler()
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Configuration

router = APIRouter()

SECRET_KEY = os.getenv("SECRET_KEY", None)
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable not set")

ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))  # 30 minutes par défaut
SECURE_COOKIES = os.getenv("SECURE_COOKIES", "False").lower() == "true"  # True en production (HTTPS)

password_hash = PasswordHash.recommended()

# OAuth2PasswordBearer pour Swagger UI (optionnel)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)

# Fonction pour récupérer le token depuis les cookies OU le header Authorization
# Permet l'utilisation de Swagger ET du frontend avec cookies
async def get_token(
    access_token_cookie: Optional[str] = Cookie(None, alias="access_token"),
    authorization: Optional[str] = Depends(oauth2_scheme)
) -> str:
    """
    Récupère le token JWT depuis :
    1. Le cookie 'access_token' (priorité - pour le frontend)
    2. Le header Authorization (fallback - pour Swagger/tests)
    """
    # Priorité au cookie (frontend)
    if access_token_cookie:
        return access_token_cookie
    
    # Fallback au header Authorization (Swagger)
    if authorization:
        return authorization
    
    # Aucune authentification trouvée
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )

class CreateUserRequest(BaseModel):
    username: str = Field()
    password: str = Field()
    role: UserRole = Field(default=UserRole.student)
    
class Token(BaseModel):
    access_token: str
    token_type: str

class LoginResponse(BaseModel):
    message: str
    
class TokenData(BaseModel):
    username: str



## HELPER FUNCTIONS

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return password_hash.hash(password)

def get_user(session: Session, username: str) -> User:
    statement = select(User).where(User.username == username)
    user = session.exec(statement).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def authenticate_user(session: Session, form_data: OAuth2PasswordRequestForm) -> UserOut:
    try: 
        user = get_user(session, form_data.username)
        data=user.model_dump()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if not verify_password(form_data.password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Incorrect password")
        return UserOut.model_validate(data)
    except HTTPException as e:
        raise e

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    logger.info(f"Creating access token for data: {data}")
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> dict[str, str]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except InvalidTokenError as e:
        logger.error(f"Invalid token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
## dependency injection, returns a function to be included as a parameter in route functions

ROLE_LEVEL = {
    UserRole.student: 1,
    UserRole.teacher: 2,
    UserRole.admin: 3,
}

def check_authorization(required_role: UserRole = UserRole.student) -> Callable[..., User]:
    def _check(user: User = Depends(get_current_user)) -> User:
        if ROLE_LEVEL[user.role] < ROLE_LEVEL[required_role]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User does not have the required role",
                )  
        return user   
    return _check   

async def get_current_user(session: Annotated[Session, Depends(get_session)], token: Annotated[str, Depends(get_token)]):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        logger.info(f"Decoded token payload: {payload}")
        username = payload.get("sub")
        token_data = TokenData(username=username)
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = get_user(session=session, username=token_data.username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Inactive user")
    return user

async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
):
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

@router.post("/create-user", status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: CreateUserRequest,
    session: Annotated[Session, Depends(get_session)]
):
    
    logger.info(f"Creating user with username: {payload.username}")
    logger.info(f"Payload received: {payload}")
    
    if get_user(session, payload.username):
        logger.warning(f"User creation failed: username {payload.username} already exists")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    create_user_model = User(
        username=payload.username,
        hashed_password=get_password_hash(payload.password),
        role=payload.role,
        is_active=True
    )
    
    logger.info(f"Creating user: {create_user_model}")
    
    session.add(create_user_model)
    session.commit()
    session.refresh(create_user_model)
    return {"msg": "User created successfully"}

@router.post("/token", response_model=LoginResponse)
async def login_for_access_token(
    response: Response,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Annotated[Session, Depends(get_session)]
):
    user = authenticate_user(session, form_data)
    if not user:
        logger.warning(f"Authentication failed for username: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role}, expires_delta=access_token_expires
    )
    logger.info(f"User {form_data.username} authenticated successfully")
    response.set_cookie(
        key="access_token", 
        value=access_token, 
        httponly=True,  # Protection XSS : JS ne peut pas accéder au cookie
        samesite="lax",  # Protection CSRF : cookie envoyé uniquement sur même site
        secure=SECURE_COOKIES,  # True en production HTTPS, False en dev HTTP
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/"
    )

    return {"message": "ok"}

@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(response: Response):
    response.delete_cookie(key="access_token", path="/")
    return {"message": "Logged out successfully"}