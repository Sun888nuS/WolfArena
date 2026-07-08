# Alembic migrations

Auth persistence migrations live here. The app also creates missing tables on
startup for local first-run convenience, but production deployments should run
Alembic migrations explicitly.
