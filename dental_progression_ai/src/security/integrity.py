import hashlib
import os
import joblib
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from dotenv import load_dotenv

load_dotenv()

class ModelIntegrityVerifier:
    """
    Verifies the integrity of machine learning weights using RSA-4096 digital signatures.
    """
    
    def __init__(self):
        self.keys_dir = "keys"
        os.makedirs(self.keys_dir, exist_ok=True)
        self.priv_path = os.path.join(self.keys_dir, "model_signing.pem")
        self.pub_path = os.path.join(self.keys_dir, "model_signing.pub")
        self.password = os.environ.get("MODEL_SIGNING_PASSWORD", "default_secure_pass").encode()

    def _get_private_key(self):
        if os.path.exists(self.priv_path):
            try:
                with open(self.priv_path, "rb") as f:
                    return serialization.load_pem_private_key(f.read(), password=self.password)
            except Exception:
                try:
                    os.remove(self.priv_path)
                    os.remove(self.pub_path)
                except Exception:
                    pass
                    
        from cryptography.hazmat.primitives.asymmetric import rsa
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
        with open(self.priv_path, "wb") as f:
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.BestAvailableEncryption(self.password)
            ))
        with open(self.pub_path, "wb") as f:
            f.write(private_key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            ))
        return private_key

    def sign_model(self, model_path: str):
        """Generates a .sig file for the model weights."""
        with open(model_path, "rb") as f:
            data = f.read()
        
        priv_key = self._get_private_key()
        signature = priv_key.sign(
            data,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256()
        )
        
        sig_path = f"{model_path}.sig"
        with open(sig_path, "wb") as f:
            f.write(signature)
        return hashlib.sha256(data).hexdigest()

    def verify_model(self, model_path: str) -> dict:
        """Verifies model weights against their signature."""
        sig_path = f"{model_path}.sig"
        if not os.path.exists(sig_path):
            return {"verified": False, "reason": "Signature file missing"}
            
        with open(model_path, "rb") as f:
            data = f.read()
        with open(sig_path, "rb") as f:
            signature = f.read()
        with open(self.pub_path, "rb") as f:
            pub_key = serialization.load_pem_public_key(f.read())
            
        try:
            pub_key.verify(
                signature,
                data,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256()
            )
            return {"verified": True, "sha256": hashlib.sha256(data).hexdigest()}
        except Exception:
            return {"verified": False, "reason": "Signature verification failed - model tampered"}

    def safe_load_sklearn_model(self, model_path: str):
        """Verifies then loads a scikit-learn model."""
        res = self.verify_model(model_path)
        if not res["verified"]:
            raise Exception(f"Refusing to load untrusted model: {res['reason']}")
        return joblib.load(model_path)
