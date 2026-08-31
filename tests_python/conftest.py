"""Test-suite-wide setup for tests_python/.

Provides a default JWT_SECRET_KEY so importing server.auth.config (which
deliberately refuses to import without one -- see that module's docstring)
never fails just because a real deployment secret isn't configured in the
test environment. This must run before any test module imports
server.auth.config, so it lives in module-level code here rather than in a
fixture.
"""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-key-not-for-production-use-1234567890")
