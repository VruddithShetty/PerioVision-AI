"""Lazily-created singletons for database stores, the model registry and ML models.

Creating these on first use (instead of at import time) keeps `import app`
fast and lets tests run without loading YOLO weights.
"""
from functools import lru_cache


@lru_cache(maxsize=None)
def patient_manager():
    from app.models.patients import PatientManager
    return PatientManager()


@lru_cache(maxsize=None)
def doctor_manager():
    from app.models.doctors import DoctorManager
    return DoctorManager()


@lru_cache(maxsize=None)
def session_store():
    from app.models.doctors import SessionStore
    return SessionStore()


@lru_cache(maxsize=None)
def analysis_store():
    from app.models.analyses import AnalysisStore
    return AnalysisStore()


@lru_cache(maxsize=None)
def report_store():
    from app.models.analyses import ReportStore
    return ReportStore()


@lru_cache(maxsize=None)
def chart_store():
    from app.models.analyses import PerioChartStore
    return PerioChartStore()


def registry():
    from app.ml.registry import registry as _registry
    return _registry()


@lru_cache(maxsize=None)
def tooth_detector():
    from app.ml.detection.yolo_detector import ToothDetectionModel
    return ToothDetectionModel()


@lru_cache(maxsize=None)
def landmark_detector():
    from app.ml.landmarks.cej_abc_extractor import LandmarkDetectionModel
    return LandmarkDetectionModel()


@lru_cache(maxsize=None)
def aligner():
    from app.ml.preprocessing.alignment import RadiographAligner
    return RadiographAligner()


def reset_models():
    """Forget loaded models (used after re-signing weights or in the Security Lab)."""
    tooth_detector.cache_clear()
    landmark_detector.cache_clear()
    registry().reset()
    from app.ml.panoramic import whole_film

    whole_film._instance = None
