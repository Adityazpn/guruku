"""Imports every ORM model so the full schema is registered on Base.metadata.
Any process that touches the database (API, Celery worker, Alembic) must import this module."""
import app.admin.models  # noqa: F401
import app.ai_engine.models  # noqa: F401
import app.ai_providers.models  # noqa: F401
import app.auth.models  # noqa: F401
import app.credits.models  # noqa: F401
import app.credits.pricing_models  # noqa: F401
import app.documents.models  # noqa: F401
import app.library.models  # noqa: F401
import app.payments.models  # noqa: F401
import app.subscriptions.models  # noqa: F401
import app.users.models  # noqa: F401
