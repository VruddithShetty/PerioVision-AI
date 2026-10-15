import os
import logging
from pymongo import MongoClient
import pymongo.errors
from app import config  # also loads ENV_FILE / .env before anything reads the environment
from app.security.secrets import run_secrets_audit, enforce_mongo_tls

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseConnection:
    """
    Singleton pattern for MongoDB connection handling.
    Uses DB_MODE to switch explicitly between production and demo behavior.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseConnection, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Initialize the database connection."""
        db_mode = os.getenv("DB_MODE", "production").strip().lower()

        # Perform security audit on startup
        # The findings are reported: an audit whose result is discarded is a control in
        # name only. Startup is not blocked, because a false positive must not take a
        # clinical system down - the operator decides.
        if os.environ.get("SECRETS_AUDIT_ON_STARTUP", "true").lower() == "true":
            findings = run_secrets_audit(config.PROJECT_ROOT)
            if findings:
                logger.error("[SECURITY] Possible hardcoded secrets found in %d place(s):", len(findings))
                for f in findings[:20]:
                    # Location and kind only - never the matched value.
                    logger.error("[SECURITY]   %s:%s  %s", f["file"], f["line"], f["type"])
                if len(findings) > 20:
                    logger.error("[SECURITY]   ... and %d more", len(findings) - 20)
            
        mongo_uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "dental_prediction_db")

        if db_mode == "demo":
            logger.warning("[DEMO MODE] Using in-memory database. Data will not persist.")
            import mongomock
            self.client = mongomock.MongoClient()
            self.db = self.client[db_name]
            return

        if db_mode != "production":
            raise RuntimeError(
                f"Invalid DB_MODE='{db_mode}'. Expected 'production' or 'demo'."
            )
        
        # Enforce TLS for production connections
        mongo_uri = enforce_mongo_tls(mongo_uri)
        
        try:
            # Attempt to connect to real MongoDB with a 2-second timeout
            self.client = MongoClient(mongo_uri, serverSelectionTimeoutMS=2000)
            self.client.server_info()  # Force connection check to trigger timeout if offline
            self.db = self.client[db_name]
        except pymongo.errors.ServerSelectionTimeoutError:
            raise RuntimeError(
                "MongoDB is unreachable in production mode. Set DB_MODE=demo for local demo runs or fix MONGO_URI."
            ) from None

# Export a single db object used by all managers
db = DatabaseConnection().db
