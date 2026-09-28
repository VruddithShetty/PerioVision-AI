# app/api

Thin HTTP route handlers (Flask blueprints), one file per area: auth, patients, radiographs, analysis, progression, reports, audit, security, health. Routes validate input and call `app/services`; they hold no business logic.
