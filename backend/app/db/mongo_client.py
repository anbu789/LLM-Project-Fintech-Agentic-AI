"""
FinTech Agent — MongoDB Client and Database Access Layer
Enforces least-privilege connection separation, comprehensive read-only database proxying,
and native query timeout enforcement across all collection and database access paths.
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

    def explain(self, *args, **kwargs) -> Dict[str, Any]:
        """Provides read-only query execution plan inspection."""
        return self._cursor.explain(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
        return getattr(self._cursor, name)


class ReadOnlyCollectionProxy:
    """
    Explicit read-only wrapper around PyMongo Collection.
    Strictly intercepts and blocks all write and mutation methods, enforces query timeouts,
    and prevents unwrapped database or collection leakage.
    """

    BLOCKED_METHODS = {
        "insert_one", "insert_many",
        "update_one", "update_many", "replace_one",
        "delete_one", "delete_many",
        "find_one_and_delete", "find_one_and_replace", "find_one_and_update",
        "drop", "rename",
        "create_index", "create_indexes", "drop_index", "drop_indexes",
        "bulk_write", "map_reduce", "reindex",
        "create_search_index", "create_search_indexes",
        "drop_search_index", "update_search_index"
    }

    def __init__(self, collection: Collection, database_proxy: Optional["ReadOnlyDatabaseProxy"] = None):
        self._collection = collection
        self._database_proxy = database_proxy

    @property
    def name(self) -> str:
        """Returns collection name."""
        return self._collection.name

    @property
    def full_name(self) -> str:
        """Returns database-qualified collection name."""
        return self._collection.full_name

    @property
    def database(self) -> "ReadOnlyDatabaseProxy":
        """Returns the protected ReadOnlyDatabaseProxy, never the unwrapped PyMongo Database."""
        if self._database_proxy is None:
            self._database_proxy = ReadOnlyDatabaseProxy(self._collection.database)
        return self._database_proxy

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

    def aggregate(self, pipeline: Any, *args, **kwargs) -> ReadOnlyCursorProxy:
        """Executes aggregation pipeline after strictly blocking mutating stages ($out, $merge)."""
        if not hasattr(pipeline, "__iter__"):
            raise ValueError("Aggregation pipeline must be an iterable of stage dictionaries.")

        for stage in pipeline:
            if isinstance(stage, dict):
                for stage_key in stage.keys():
                    key_clean = str(stage_key).strip().lower()
                    if key_clean in ("$out", "$merge"):
                        raise DatabaseWriteProhibitedError(
                            f"aggregate with stage '{stage_key}'",
                            details="Pipeline stages $out and $merge mutate data and are strictly prohibited."
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

    def list_indexes(self, *args, **kwargs):
        """Allows read-only index inspection."""
        return self._collection.list_indexes(*args, **kwargs)

    def index_information(self, *args, **kwargs):
        """Allows read-only index metadata inspection."""
        return self._collection.index_information(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        """Blocks mutation methods and unauthorized attribute access."""
        mutation_prefixes = ("insert", "update", "delete", "replace", "drop", "create", "bulk", "rename")
        if name in self.BLOCKED_METHODS or any(name.startswith(p) for p in mutation_prefixes):
            raise DatabaseWriteProhibitedError(name)
        if name.startswith("_"):
            raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
        raise DatabaseWriteProhibitedError(
            name,
            details=f"Method or property '{name}' is not permitted on read-only collections."
        )


class ReadOnlyDatabaseProxy:
    """
    Wrapper around PyMongo Database to enforce read-only semantics.
    Protects item access, attribute access (db.customers), get_collection(),
    and blocks all administrative or mutating database commands.
    """

    BLOCKED_DATABASE_COMMANDS = {
        "drop", "dropdatabase", "create", "createindexes", "insert",
        "update", "delete", "collmod", "renamecollection", "applyops",
        "converttocapped", "reindex", "eval"
    }

    def __init__(self, database: Database):
        self._database = database

    @property
    def name(self) -> str:
        return self._database.name

    def __getitem__(self, name: str) -> ReadOnlyCollectionProxy:
        return self.get_collection(name)

    def get_collection(self, name: str, *args, **kwargs) -> ReadOnlyCollectionProxy:
        """Returns a protected ReadOnlyCollectionProxy for the requested collection."""
        raw_col = self._database.get_collection(name, *args, **kwargs)
        return ReadOnlyCollectionProxy(raw_col, database_proxy=self)

    def list_collection_names(self, *args, **kwargs) -> List[str]:
        return self._database.list_collection_names(*args, **kwargs)

    def list_collections(self, *args, **kwargs):
        return self._database.list_collections(*args, **kwargs)

    def validate_collection(self, name_or_collection, *args, **kwargs):
        return self._database.validate_collection(name_or_collection, *args, **kwargs)

    def drop_collection(self, name: str) -> None:
        raise DatabaseWriteProhibitedError("drop_collection")

    def create_collection(self, name: str, *args, **kwargs) -> None:
        raise DatabaseWriteProhibitedError("create_collection")

    def command(self, cmd: Any, *args, **kwargs) -> Any:
        """Inspects database commands and blocks all administrative/mutating operations."""
        if isinstance(cmd, str):
            cmd_clean = cmd.strip().lower()
            if cmd_clean in self.BLOCKED_DATABASE_COMMANDS:
                raise DatabaseWriteProhibitedError(f"Database command '{cmd}'")
        elif isinstance(cmd, dict):
            for k in cmd.keys():
                k_clean = str(k).strip().lower()
                if k_clean in self.BLOCKED_DATABASE_COMMANDS:
                    raise DatabaseWriteProhibitedError(f"Database command with key '{k}'")
        return self._database.command(cmd, *args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        """Intercepts attribute access so db.customers returns a ReadOnlyCollectionProxy."""
        if name.startswith("_"):
            raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
        if name in {"drop_collection", "create_collection"}:
            raise DatabaseWriteProhibitedError(name)
        if name == "client":
            raise DatabaseWriteProhibitedError("Direct client access from ReadOnlyDatabaseProxy is prohibited.")
        # Any collection accessed via attribute (e.g. db.customers, db.accounts) is wrapped
        return self.get_collection(name)


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

    @property
    def banking_db(self) -> Any:
        """Convenience property for get_banking_db()."""
        return self.get_banking_db()

    def get_metadata_db(self) -> Database:
        """
        Returns the application metadata database (agent_metadata_db).
        Allows readWrite access for scheduler, history, and audit jobs.
        """
        client = self.get_metadata_client()
        return client[settings.MONGO_METADATA_DB]

    @property
    def metadata_db(self) -> Database:
        """Convenience property for get_metadata_db()."""
        return self.get_metadata_db()

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
    """Verify banking and metadata access independently using their least-privilege accounts."""
    banking_client = None
    metadata_client = None
    try:
        # Banking verification uses only the dedicated read-only banking identity.
        banking_client = MongoClient(
            settings.get_banking_uri(),
            serverSelectionTimeoutMS=timeout_ms,
        )
        banking_client.admin.command("ping")
        banking_collections = banking_client[settings.MONGO_BANKING_DB].list_collection_names()

        # Metadata verification uses its separate read-write application identity.
        metadata_client = MongoClient(
            settings.get_metadata_uri(),
            serverSelectionTimeoutMS=timeout_ms,
        )
        metadata_client.admin.command("ping")
        metadata_collections = metadata_client[settings.MONGO_METADATA_DB].list_collection_names()

        # buildInfo is optional: a restricted read account may not have this privilege.
        version = None
        try:
            version = banking_client.admin.command("buildInfo").get("version")
        except pymongo.errors.PyMongoError:
            pass

        databases = []
        if banking_collections:
            databases.append(settings.MONGO_BANKING_DB)
        if metadata_collections:
            databases.append(settings.MONGO_METADATA_DB)

        return {
            "status": "connected",
            "version": version,
            "databases": databases,
            "banking_db_exists": bool(banking_collections),
            "metadata_db_exists": bool(metadata_collections),
            "auth_enabled": settings.MONGO_AUTH_ENABLED,
            "query_timeout_ms": settings.QUERY_TIMEOUT_MS,
        }
    except Exception as e:
        return {
            "status": "error",
            "error_type": type(e).__name__,
            "error_message": str(e)
        }
    finally:
        if banking_client is not None:
            banking_client.close()
        if metadata_client is not None:
            metadata_client.close()

def get_collection_inventory(db_name: Optional[str] = None) -> Dict[str, int]:
    """Retrieves document counts for all collections in the target database."""
    target_db = db_name or settings.MONGO_BANKING_DB
    if target_db == settings.MONGO_BANKING_DB:
        db = mongo_manager.get_banking_db(enforce_proxy=True)
        return {col: db[col].count_documents({}) for col in sorted(db.list_collection_names())}
    client = mongo_manager.get_metadata_client()
    db = client[target_db]
    return {col: db[col].count_documents({}) for col in sorted(db.list_collection_names())}


def get_bounded_samples(collection_name: str, limit: int = 3, db_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves bounded sample documents without modifying any records."""
    target_db = db_name or settings.MONGO_BANKING_DB
    if target_db == settings.MONGO_BANKING_DB:
        db = mongo_manager.get_banking_db(enforce_proxy=True)
        cursor = db[collection_name].find({}, {"_id": 0}).limit(limit)
        return list(cursor)
    client = mongo_manager.get_metadata_client()
    db = client[target_db]
    cursor = db[collection_name].find({}, {"_id": 0}).limit(limit)
    return list(cursor)
