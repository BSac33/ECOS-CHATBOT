'''
Logique d'authentification / autorisation pour l'API

Benjamin Sacristan - 2026

'''

from datetime import datetime, timedelta, timezone
from math import e, log
import stat
from typing import Optional, Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import jwt
from pwdlib import PasswordHash
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel, Field
from sqlmodel import Session
from urllib3 import HTTPResponse
from db import get_session
from models import User, UserRole
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

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)

SECRET_KEY = os.getenv("SECRET_KEY", None)
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable not set")

ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))  # 30 minutes par défaut

password_hash = PasswordHash.recommended()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

class CreateUserRequest(BaseModel):
    username: str = Field()
    password: str = Field()
    role: UserRole = Field(default=UserRole.student)
    
class Token(BaseModel):
    access_token: str
    token_type: str
    
class TokenData(BaseModel):
    username: str

class UserInDB(User):
    hashed_password: str
    
db_dependency = Annotated[Session, Depends(get_session)]

## HELPER FUNCTIONS

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return password_hash.hash(password)

def get_user(session: Session, username: str) -> Optional[UserInDB]:
    statement = select(User).where(User.username == username)
    user = session.exec(statement).first()
    if user:
        return UserInDB.model_validate(user)
    return None

def authenticate_user(session: Session, username: str, password: str) -> Optional[UserInDB]:
    user = get_user(session, username)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user

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

def decode_access_token(token: str) -> dict:
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

def check_authorization(required_role: UserRole, token: Token) -> bool | HTTPException:
    try:
        payload = decode_access_token(token.access_token)
        if "role" in payload and payload["role"] == required_role.value:
            return True
        else:           
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not have the required role",
            )
    except HTTPException as e:
        raise e

async def get_current_user(session: Session, token: Annotated[str, Depends(oauth2_scheme)]):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except InvalidTokenError:
        raise credentials_exception
    user = get_user(session=session, username=token_data.username)
    if user is None:
        raise credentials_exception
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
    session: db_dependency
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

@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: db_dependency
):
    user = authenticate_user(session, form_data.username, form_data.password)
    if not user:
        logger.warning(f"Authentication failed for username: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role.value}, expires_delta=access_token_expires
    )
    logger.info(f"User {form_data.username} authenticated successfully")
    return {"access_token": access_token, "token_type": "bearer"}