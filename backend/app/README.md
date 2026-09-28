# app

The Flask backend package. `create_app()` in `__init__.py` builds the app; `config.py` holds all paths, secrets (read from `.env`) and thresholds. Sub-folders separate HTTP routes, business logic, ML, security and database code.
