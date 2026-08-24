import os
import re
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def get_secret(secret_name: str) -> str:
    """
    Fetches secret from AWS Secrets Manager if USE_AWS_SECRETS is set.
    Otherwise falls back to environment variables.
    """
    if os.environ.get("USE_AWS_SECRETS", "").lower() == "true":
        try:
            import boto3
            import json
            client = boto3.client('secretsmanager')
            # In a real setup, you might map secret_name to an AWS ARN
            # For simplicity, assuming the secret name matches AWS
            response = client.get_secret_value(SecretId=secret_name)
            if 'SecretString' in response:
                secret_dict = json.loads(response['SecretString'])
                return secret_dict.get(secret_name, response['SecretString'])
        except Exception as e:
            logger.error(f"Failed to fetch secret from AWS: {e}")
            
    # Fallback to env injection (e.g. CI/CD)
    return os.environ.get(secret_name)

def run_secrets_audit(project_root="."):
    """
    Scans the project for hardcoded secrets.
    """
    findings = []
    patterns = {
        "MONGODB_URI": r'mongodb(?:\+srv)?://[^\s"\'@]+:[^\s"\'@]+@[^\s"\']+',
        "IP_ADDRESS": r'(?:[0-9]{1,3}\.){3}[0-9]{1,3}',
        "PASSWORD_ASSIGNMENT": r'password\s*=\s*["\'][^"\']+["\']',
        "SECRET_KEY": r'SECRET_KEY\s*=\s*["\'][^"\']{8,}'
    }
    
    for py_file in Path(project_root).rglob("*.py"):
        if any(x in str(py_file) for x in ["venv", ".venv", "secrets.py", "scripts"]): continue
        try:
            with open(py_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, 1):
                    for p_name, p_regex in patterns.items():
                        if re.search(p_regex, line):
                            findings.append({"file": str(py_file), "line": line_num, "type": p_name})
        except: pass
    return findings

def enforce_mongo_tls(mongo_uri: str) -> str:
    if not mongo_uri: return mongo_uri
    if "localhost" in mongo_uri or "127.0.0.1" in mongo_uri:
        return mongo_uri
    if "tls=true" in mongo_uri.lower() or "ssl=true" in mongo_uri.lower():
        return mongo_uri
    separator = "&" if "?" in mongo_uri else "?"
    return f"{mongo_uri}{separator}tls=true&tlsAllowInvalidCertificates=false"
