"""
Abstraction pour le stockage de fichiers (local ou cloud)
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO, Optional
import os


class StorageBackend(ABC):
    """Interface abstraite pour le stockage de fichiers"""
    
    @abstractmethod
    async def save_file(self, file_data: bytes, path: str) -> str:
        """Sauvegarde un fichier et retourne l'URL d'accès"""
        pass
    
    @abstractmethod
    async def get_file(self, path: str) -> bytes:
        """Récupère le contenu d'un fichier"""
        pass
    
    @abstractmethod
    async def delete_file(self, path: str) -> bool:
        """Supprime un fichier"""
        pass
    
    @abstractmethod
    def get_url(self, path: str) -> str:
        """Retourne l'URL publique du fichier"""
        pass


class LocalStorage(StorageBackend):
    """Stockage sur le système de fichiers local"""
    
    def __init__(self, base_path: str = "storage"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        # Créer la structure de dossiers
        for subdir in ["images", "videos", "documents", "transcripts", "audio"]:
            (self.base_path / subdir).mkdir(exist_ok=True)
    
    async def save_file(self, file_data: bytes, path: str) -> str:
        file_path = self.base_path / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(file_data)
        return f"/files/{path}"
    
    async def get_file(self, path: str) -> bytes:
        file_path = self.base_path / path
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return file_path.read_bytes()
    
    async def delete_file(self, path: str) -> bool:
        file_path = self.base_path / path
        if file_path.exists():
            file_path.unlink()
            return True
        return False
    
    def get_url(self, path: str) -> str:
        return f"/files/{path}"


class S3Storage(StorageBackend):
    """Stockage sur S3/MinIO (pour migration future)"""
    
    def __init__(self, bucket: str, endpoint: Optional[str] = None):
        # Import différé pour ne pas avoir boto3 comme dépendance obligatoire
        import boto3
        
        self.bucket = bucket
        config = {}
        if endpoint:
            config['endpoint_url'] = endpoint
        
        self.s3 = boto3.client('s3', **config)
    
    async def save_file(self, file_data: bytes, path: str) -> str:
        self.s3.put_object(Bucket=self.bucket, Key=path, Body=file_data)
        return self.get_url(path)
    
    async def get_file(self, path: str) -> bytes:
        obj = self.s3.get_object(Bucket=self.bucket, Key=path)
        return obj['Body'].read()
    
    async def delete_file(self, path: str) -> bool:
        self.s3.delete_object(Bucket=self.bucket, Key=path)
        return True
    
    def get_url(self, path: str) -> str:
        return f"https://{self.bucket}.s3.amazonaws.com/{path}"


# Factory pour créer le bon backend selon la config
def get_storage() -> StorageBackend:
    storage_type = os.getenv("STORAGE_TYPE", "local")
    
    if storage_type == "local":
        return LocalStorage(os.getenv("STORAGE_PATH", "storage"))
    elif storage_type in ["s3", "minio"]:
        return S3Storage(
            bucket=os.getenv("S3_BUCKET", "ecos-chatbot"),
            endpoint=os.getenv("S3_ENDPOINT")  # Pour MinIO
        )
    else:
        raise ValueError(f"Unknown storage type: {storage_type}")


# Instance singleton
storage = get_storage()
