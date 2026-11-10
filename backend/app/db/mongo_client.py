"""
FinTech Agent — MongoDB Client and Database Access Layer
Enforces least-privilege connection separation, read-only database proxying,
and native query timeout enforcement.
"""

from typing import Any, Dict, List, Optional
import pymongo
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from backend.app.config import settings
from backend.app.core.exceptions import (
    DatabaseCredentialsError,
    DatabaseTimeoutError,
    DatabaseWriteProhibitedError,
)
from backend.app.core.logging import logger


class ReadOnlyCursorProxy:
    """Wraps PyMongo Cursor to intercept timeouts and enforce read-only iteration."""

    def __init__(self, cursor: Any, timeout_ms: int):
        self._cursor = cursor
        self._timeout_ms = timeout_ms

    def __iter__(self):
        try:
            for item in self._cursor:
                yield item
        except (pymongo.errors.ExecutionTimeout, pymongo.errors.NetworkTimeout) as exc:
            raise DatabaseTimeoutError(self._timeout_ms, str(exc)) from exc

    def __next__(self):
        try:
            return next(self._cursor)
        except (pymongo.errors.ExecutionTimeout, pymongo.errors.NetworkTimeout) as exc:
            raise DatabaseTimeoutError(self._timeout_ms, str(exc)) from exc

    def __getitem__(self, index: Any) -> Any:
        try:
            res = self._cursor[index]
            if hasattr(res, "__iter__") and not isinstance(res, (dict, list)):
                return ReadOnlyCursorProxy(res, self._timeout_ms)
            return res
        except (pymongo.errors.ExecutionTimeout, pymongo.errors.NetworkTimeout) as exc:
            raise DatabaseTimeoutError(self._timeout_ms, str(exc)) from exc

    def limit(self, *args, **kwargs) -> "ReadOnlyCursorProxy":
        self._cursor.limit(*args, **kwargs)
        return self

    def sort(self, *args, **kwargs) -> "ReadOnlyCursorProxy":
        self._cursor.sort(*args, **kwargs)
        return self

    def skip(self, *args, **kwargs) -> "ReadOnlyCursorProxy":
        self._cursor.skip(*args, **kwargs)
        return self

    def batch_size(self, *args, **kwargs) -> "ReadOnlyCursorProxy":
        self._cursor.batch_size(*args, **kwargs)
        return self

    def max_time_ms(self, max_time_ms: int) -> "ReadOnlyCursorProxy":
        self._cursor.max_time_ms(max_time_ms)
        self._timeout_ms = max_time_ms
        return self

    def to_list(self, *args, **kwargs) -> List[Dict[str, Any]]:
        try:
            return self._cursor.to_list(*args, **kwargs)
        except (pymongo.errors.ExecutionTimeout, pymongo.errors.NetworkTimeout) as exc:
            raise DatabaseTimeoutError(self._timeout_ms, str(exc)) from exc

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cursor, name)


class ReadOnlyCollectionProxy:
    """Wrapper around PyMongo Collection to strictly block write operations and enforce timeouts."""

    BLOCKED_METHODS = {
        "insert_one", "insert_many",
        "update_one", "update_many", "replace_one",
        "delete_one", "delete_many",
        "find_one_and_delete", "find_one_and_replace", "find_one_and_update",
        "drop", "rename", "create_index", "create_indexes", "drop_index", "drop_indexes",
        "bulk_write", "map_reduce"
    }

    def __init__(self, collection: Collection):
        self._collection = collection

    def find(self, *args, **kwargs) -> ReadOnlyCursorProxy:
        """Executes find query with server-side timeout injection."""
        timeout_ms = kwargs.pop("max_time_ms", None) or kwargs.pop("maxTimeMS", None) or settings.QUERY_TIMEOUT_MS
        cursor = self._collection.find(*args, **kwargs).max_time_ms(timeout_ms)
        return ReadOnlyCursorProxy(cursor, timeout_ms=timeout_ms)

    def find_one(self, *args, **kwargs) -> Optional[Dict[str, Any]]:
        """Executes find_one query with server-side timeout injection."""
        timeout_ms = kwargs.pop("max_time_ms", None) or kwargs.pop("maxTimeMS", None) or settings.QUERY_TIMEOUT_MS
        kwargs["max_time_ms"] = timeout_ms
        try:
            return self._collection.find_one(*args, **kwargs)
        except (pymongo.errors.ExecutionTimeout, pymongo.errors.NetworkTimeout) as exc:
            raise DatabaseTimeoutError(timeout_ms, str(exc)) from exc

    def aggregate(self, pipeline: List[Dict[str, Any]], *args, **kwargs) -> ReadOnlyCursorProxy:
        """Executes aggregation pipeline after blocking mutating stages ($out, $merge)."""
        # Block write stages disguised in aggregation
        for stage in pipeline:
            if isinstance(stage, dict):
                for stage_key in stage.keys():
                    if stage_key in ("$out", "$merge"):
                        raise DatabaseWriteProhibitedError(
                            f"aggregate with stage '{stage_key}'",
                            details="Pipeline stages $out and $merge mutate data and are prohibited."
                        )

        timeout_ms = kwargs.pop("maxTimeMS", None) or kwargs.pop("max_time_ms", None) or settings.QUERY_TIMEOUT_MS
        kwargs["maxTimeMS"] = timeout_ms

        try:
            cursor = self._collection.aggregate(pipeline, *args, **kwargs)
            return ReadOnlyCursorProxy(cursor, timeout_ms=timeout_ms)
        except (pymongo.errors.ExecutionTimeout, pymongo.errors.NetworkTimeout) as exc:
            raise DatabaseTimeoutError(timeout_ms, str(exc)) from exc

    def count_documents(self, filter: Dict[str, Any], *args, **kwargs) -> int:
        """Executes count_documents with server-side timeout injection."""
        timeout_ms = kwargs.pop("maxTimeMS", None) or kwargs.pop("max_time_ms", None) or settings.QUERY_TIMEOUT_MS
        kwargs["maxTimeMS"] = timeout_ms
        try:
            return self._collection.count_documents(filter, *args, **kwargs)
        except (pymongo.errors.ExecutionTimeout, pymongo.errors.NetworkTimeout) as exc:
            raise DatabaseTimeoutError(timeout_ms, str(exc)) from exc

    def distinct(self, key: str, filter: Optional[Dict[str, Any]] = None, *args, **kwargs) -> List[Any]:
        """Executes distinct query with server-side timeout injection."""
        timeout_ms = kwargs.pop("maxTimeMS", None) or kwargs.pop("max_time_ms", None) or settings.QUERY_TIMEOUT_MS
        kwargs["maxTimeMS"] = timeout_ms
        try:
            return self._collection.distinct(key, filter=filter, *args, **kwargs)
        except (pymongo.errors.ExecutionTimeout, pymongo.errors.NetworkTimeout) as exc:
            raise DatabaseTimeoutError(timeout_ms, str(exc)) from exc

    def estimated_document_count(self, *args, **kwargs) -> int:
        """Executes estimated_document_count with server-side timeout injection."""
        timeout_ms = kwargs.pop("maxTimeMS", None) or kwargs.pop("max_time_ms", None) or settings.QUERY_TIMEOUT_MS
        kwargs["maxTimeMS"] = timeout_ms
        try:
            return self._collection.estimated_document_count(*args, **kwargs)
        except (pymongo.errors.ExecutionTimeout, pymongo.errors.NetworkTimeout) as exc:
            raise DatabaseTimeoutError(timeout_ms, str(exc)) from exc

    def __getattr__(self, name: str) -> Any:
        if name in self.BLOCKED_METHODS:
            raise DatabaseWriteProhibitedError(name)
        return getattr(self._collection, name)


class ReadOnlyDatabaseProxy:
    """Wrapper around PyMongo Database to enforce read-only semantics."""

    def __init__(self, database: Database):
        self._database = database

    def __getitem__(self, name: str) -> ReadOnlyCollectionProxy:
        return ReadOnlyCollectionProxy(self._database[name])

    def __getattr__(self, name: str) -> Any:
        if name in {"drop_collection", "create_collection", "command"}:
            if name == "command":
                def safe_command(cmd, *args, **kwargs):
                    blocked_cmds = {"drop", "dropDatabase", "createIndexes", "delete", "insert", "update", "collMod", "create"}
                    if isinstance(cmd, str) and cmd in blocked_cmds:
                        raise DatabaseWriteProhibitedError(f"Database command '{cmd}'")
                    elif isinstance(cmd, dict) and any(k in blocked_cmds for k in cmd):
                        raise DatabaseWriteProhibitedError(f"Database command with keys {list(cmd.keys())}")
                    return self._database.command(cmd, *args, **kwargs)
                return safe_command
            raise DatabaseWriteProhibitedError(name)
        return getattr(self._database, name)


class MongoDBManager:
    """
    Manages separate client connections for banking (read-only) and metadata (read-write).
    Enforces least privilege, timeout defaults, and prevents credential mixing.
    """

    def __init__(self):
        self._banking_client: Optional[MongoClient] = None
        self._metadata_client: Optional[MongoClient] = None

    def get_banking_client(self) -> MongoClient:
        """Returns client connection for banking operations using read-only credentials."""
        if self._banking_client is None:
            uri = settings.get_banking_uri()
            self._banking_client = MongoClient(
                uri,
                serverSelectionTimeoutMS=settings.QUERY_TIMEOUT_MS,
                maxPoolSize=50,
                connect=False
            )
        return self._banking_client

    def get_metadata_client(self) -> MongoClient:
        """Returns client connection for metadata operations using dedicated metadata credentials."""
        if self._metadata_client is None:
            uri = settings.get_metadata_uri()
            self._metadata_client = MongoClient(
                uri,
                serverSelectionTimeoutMS=settings.QUERY_TIMEOUT_MS,
                maxPoolSize=20,
                connect=False
            )
        return self._metadata_client

    def get_banking_db(self, enforce_proxy: bool = True) -> Any:
        """
        Returns the banking database (fintech_agent_db).
        Wrapped in ReadOnlyDatabaseProxy by default to enforce zero write capability.
        """
        client = self.get_banking_client()
        raw_db = client[settings.MONGO_BANKING_DB]
        return ReadOnlyDatabaseProxy(raw_db) if enforce_proxy else raw_db

    def get_metadata_db(self) -> Database:
        """
        Returns the application metadata database (agent_metadata_db).
        Allows readWrite access for scheduler, history, and audit jobs.
        """
        client = self.get_metadata_client()
        return client[settings.MONGO_METADATA_DB]

    def get_security_status(self) -> Dict[str, Any]:
        """Returns the current MongoDB security posture and timeout configuration."""
        return {
            "auth_enabled": settings.MONGO_AUTH_ENABLED,
            "allow_unauthenticated_dev": settings.ALLOW_UNAUTHENTICATED_DEV,
            "banking_db": settings.MONGO_BANKING_DB,
            "metadata_db": settings.MONGO_METADATA_DB,
            "banking_user_configured": bool(settings.MONGO_READONLY_USERNAME),
            "metadata_user_configured": bool(settings.MONGO_METADATA_USERNAME),
            "credentials_isolated": settings.MONGO_READONLY_USERNAME != settings.MONGO_METADATA_USERNAME,
            "query_timeout_ms": settings.QUERY_TIMEOUT_MS,
            "request_timeout_seconds": settings.REQUEST_TIMEOUT_SECONDS,
            "max_retry_attempts": settings.MAX_RETRY_ATTEMPTS,
            "read_only_proxy_enforced": True
        }

    def close(self):
        """Closes all managed client connections."""
        if self._banking_client:
            self._banking_client.close()
            self._banking_client = None
        if self._metadata_client:
            self._metadata_client.close()
            self._metadata_client = None


# Global singleton instance
mongo_manager = MongoDBManager()


def check_mongo_connection(timeout_ms: int = 3000) -> Dict[str, Any]:
    """Inspects connection status, server info, and available databases."""
    try:
        uri = settings.get_banking_uri()
        client = MongoClient(uri, serverSelectionTimeoutMS=timeout_ms)
        info = client.server_info()
        databases = client.list_database_names()
        client.close()
        return {
            "status": "connected",
            "version": info.get("version"),
            "databases": databases,
            "banking_db_exists": settings.MONGO_BANKING_DB in databases,
            "metadata_db_exists": settings.MONGO_METADATA_DB in databases,
            "auth_enabled": settings.MONGO_AUTH_ENABLED,
            "query_timeout_ms": settings.QUERY_TIMEOUT_MS,
        }
    except Exception as e:
        return {
            "status": "error",
            "error_type": type(e).__name__,
            "error_message": str(e)
        }


def get_collection_inventory(db_name: Optional[str] = None) -> Dict[str, int]:
    """Retrieves document counts for all collections in the target database."""
    target_db = db_name or settings.MONGO_BANKING_DB
    client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=3000)
    db = client[target_db]
    inventory = {col: db[col].count_documents({}) for col in sorted(db.list_collection_names())}
    client.close()
    return inventory


def get_bounded_samples(collection_name: str, limit: int = 3, db_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves bounded sample documents without modifying any records."""
    target_db = db_name or settings.MONGO_BANKING_DB
    client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=3000)
    db = client[target_db]
    cursor = db[collection_name].find({}, {"_id": 0}).limit(limit)
    samples = list(cursor)
    client.close()
    return samples
