"""Flask extensions shared by the app factory and the route blueprints.

CSRF tokens are not used: the API authenticates with a Bearer token in the
Authorization header, which browsers never attach automatically, and the only
cookie (the refresh token) is SameSite=Strict and scoped to /api/auth.
"""
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=["120 per minute"])
