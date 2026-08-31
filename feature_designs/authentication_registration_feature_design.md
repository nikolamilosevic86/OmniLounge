# User Authentication and Registration Feature Design

## 0. Implementation Status At A Glance (read this first)

*This section is the single source of truth for "is X done yet?" — it's a compact rollup of §9's detailed Progress Dashboard and §13's Acceptance Criteria checklist, kept in sync with them on every implementation pass. Last updated: 2026-08-31.*

**Configuration**: there is no static config *file* to hand-edit — `server/auth/config.py` builds everything from environment variables at process startup (and fails fast if `JWT_SECRET_KEY` is missing or too short). Every variable it (and the rest of the server) reads is listed, with comments, in [`.env.example`](../.env.example) at the repo root (committed, no real secrets). `server/main.py` loads a real `.env` (gitignored) automatically via `python-dotenv`; running [`run.sh`](../run.sh) (macOS/Linux) or [`run.bat`](../run.bat) (Windows) generates one for you from the template (`scripts/generate_env.py`, with a random dev JWT secret) and starts the database + backend + frontend together in a single command.

**✅ Done, unit-tested, and validated end-to-end against a real Postgres database:**
- Local email/password auth: register, login, logout, refresh, JWT access + refresh tokens, bcrypt password hashing.
- Admin-only registration mode: admin creates/lists/updates/disables/enables/soft-deletes users, bulk CSV import, audit log, RBAC (`require_role`).
- Email verification (real SMTP via aiosmtplib, or a dev-mode logging fallback when no SMTP server is configured) + password reset, both via short-lived single-use tokens. Login now actually rejects an unverified account with 403 when `AUTH_REQUIRE_EMAIL_VERIFICATION=true` (previously that setting only controlled whether the verification *email* was sent).
- User profile + session management: view/edit profile, change password, list/revoke active sessions, periodic expired-session cleanup.
- Security hardening: per-IP rate limiting on login/registration, account lockout after repeated failures (now also emails the account owner once per lockout), password history (blocks reusing recent passwords), password expiration (`AUTH_PASSWORD_EXPIRY_DAYS`), generic non-account-enumerating error messages, timing-attack mitigation on login.
- Initial admin bootstrap: either automatic (env vars, on an empty `users` table at startup) or via `python -m server.scripts.create_admin` (interactive CLI, no password in shell history).
- **Disabling guest/anonymous access**: `AUTH_ALLOW_GUEST_ACCESS` (default `true`, preserving this app's original anonymous-play design). Set to `false` to hide the "Continue as a guest" link on the login page and redirect an anonymous visitor away from the main game to the login page instead. This is a client-side UX gate — pair it with `AUTH_REQUIRE_SOCKET_AUTH=true` for an actual backend-enforced boundary on real-time game connections.

**🟡 Done and unit-tested, but NOT yet exercised against a real/live external provider (only a locally-generated RSA keypair + scripted HTTP transport):**
- Azure Entra ID SSO (PKCE, RS256 id_token verification via JWKS, `allowed_groups` enforcement).
- Google / GitHub / AWS Cognito OAuth2 (same generic framework; GitHub has no id_token and uses its REST profile API instead).
- A genuinely unreachable provider now correctly returns 503 instead of a misleading 401 — this part *is* fully testable without a live provider, and is done.

**🟡 Frontend: minimal, not the full design**
- Real, working pages: login/register (`client/login.html`), OAuth2 callback (`client/auth-callback.html`), and the main game (`client/js/main.js`) now restores a session on load and shows a sign-in/sign-out toggle in the HUD.
- **Not built**: the Material 3 Web Components library (a hand-rolled equivalent design-token CSS is used instead — see Deliberate Deviations), an admin dashboard/user table/audit-log viewer, a self-service profile/session-management page, a forced-password-change page, an email-verification-pending page, and any role-gated room/game action (a logged-in and an anonymous player can do exactly the same things in a room today).

**❌ Not implemented, deliberately deferred (with rationale in "Deliberate deviations from this design doc"):**
- Redis-backed distributed rate limiting — current limiter is in-memory/single-process, which is correct for this app's current single-instance deployment.
- CSRF tokens — not applicable yet, since the API is bearer-token based, not cookie-session based.
- External security pentest / third-party OWASP audit.
- Load/performance testing and benchmarks.
- Curated API reference docs and a standalone admin/deployment guide (beyond this design doc + FastAPI's automatic `/docs`).
- Anything under §14 "Future Enhancements" (MFA/WebAuthn, account linking, SAML, etc.) — never in scope for this pass.

**Test counts** (updated every pass): 1588 Python + 746 JS tests passing; measured `server/auth` coverage is 94%.

---

## 1. Product Intent

This feature set enables Hobboverse to support multiple authentication models, allowing administrators to configure the system for different organizational needs:

- **Open Registration Mode**: Users can self-register and create accounts
- **Admin-Only Registration Mode**: Only administrators can create user accounts; users log in with provided credentials
- **Enterprise SSO Mode**: Integration with Azure Entra ID (Microsoft identity platform) for enterprise deployments
- **Multi-OAuth2 Support**: Support for additional OAuth2 providers (AWS Cognito, Google, GitHub) for flexible integrations
- **Session Management**: Secure token-based sessions with automatic logout and refresh capabilities
- **User Profiles**: Basic user profiles with avatar association, preferences, and account management

The core design principle is **flexible access control**: the authentication system adapts to organizational governance needs without code changes—only configuration.

---

## 2. Experience Principles

- **Configuration-First**: Authentication models are configured via server config; no code changes needed for switching modes
- **Minimal Friction for Users**: Login/registration flows are quick and clear, with clear error messages
- **Security by Default**: Sessions are short-lived, tokens are httpOnly where possible, passwords are never stored in plain text
- **Admin Control**: Administrators can manage users, reset passwords, toggle registration modes, and audit access
- **Graceful Fallbacks**: If OAuth2 is unavailable, the system falls back to local authentication
- **First-Time UX**: New users get a guided intro after login; returning users see the room lobby immediately

---

## 3. Primary Personas

### 3.1 Administrator
- Sets up and configures the Hobboverse instance
- Decides which authentication mode(s) to enable
- Manages user accounts (in admin-only registration mode)
- Resets passwords and manages permissions
- Views audit logs and usage reports

### 3.2 Learner / Casual User (Open Registration)
- Registers with email and password
- Logs in to join rooms
- Manages personal profile and preferences
- Never interacts with admin features

### 3.3 Enterprise User (Entra ID / OAuth2)
- Uses existing company/organization identity
- One-click login via Azure/Cognito
- Profile auto-populated from identity provider
- No separate password to manage

### 3.4 Moderator / Room Creator
- Same login flow as learner
- Has additional permissions to create and manage rooms
- Can moderate content and user behavior (future phase)

---

## 4. Authentication Models: Configuration Options

### 4.1 Open Registration Model
**Use Case**: Public education platforms, open communities, academic institutions

**Flow**:
1. User arrives at app → sees "Register" or "Login" buttons
2. Registration: user enters email, password, display name
3. Email verification (optional, configurable)
4. User creates avatar
5. User enters room lobby

**Features**:
- Email/password registration
- Optional email verification before account activation
- Password reset via email link
- Rate limiting on registration to prevent abuse

**Security**:
- Passwords hashed with bcrypt (cost: 12)
- Email uniqueness enforced
- Account lockout after N failed login attempts

---

### 4.2 Admin-Only Registration Model
**Use Case**: Private organizations, training programs, controlled classroom environments

**Flow**:
1. Administrator creates user account via admin panel
2. Admin sends user a temporary password and username
3. User logs in with username/temporary password
4. User is forced to change password on first login
5. User creates avatar
6. User enters room lobby

**Features**:
- Admin creates accounts with email, username, initial password
- First-login password reset (forced)
- User cannot register independently
- Admin can disable accounts without deleting them
- Bulk user import from CSV

**Security**:
- Initial passwords are randomly generated
- Passwords must be changed on first login
- All account creations/modifications are audited

---

### 4.3 Azure Entra ID Integration
**Use Case**: Enterprises using Microsoft 365, corporate governance required

**Flow**:
1. User clicks "Sign in with Microsoft" / "Sign in with Azure"
2. User redirected to Azure login
3. User authenticates with corporate credentials
4. User grants permission for Hobboverse to access basic profile
5. Hobboverse creates/updates local user with Entra ID identity
6. User creates/confirms avatar
7. User enters room lobby

**Features**:
- OAuth2 Authorization Code Flow with PKCE
- Automatic user provisioning on first login
- Profile fields synced from Entra ID (name, email, profile picture)
- Group-based access control (optional: only certain Entra ID groups can access)
- Logout revokes Hobboverse access token

**Configuration**:
```yaml
auth:
  azure_entra_id:
    enabled: true
    client_id: "${AZURE_CLIENT_ID}"
    client_secret: "${AZURE_CLIENT_SECRET}"
    tenant_id: "${AZURE_TENANT_ID}"
    redirect_uri: "https://app.example.com/auth/callback/azure"
    scopes:
      - openid
      - profile
      - email
    # Optional: restrict to specific Entra ID groups
    allowed_groups:
      - "educators"
      - "administrators"
    # Default role for new users
    default_role: "learner"
```

**Security**:
- Authorization code not exposed to frontend
- PKCE flow prevents code interception
- ID token validated server-side
- User matched by sub claim (immutable Entra ID ID)

---

### 4.4 OAuth2 Generic Support (Cognito, Google, GitHub)
**Use Case**: Flexible deployments, integration with existing identity providers

**Supported Providers** (in order of priority):
1. AWS Cognito
2. Google OAuth2
3. GitHub OAuth2
4. Custom OAuth2 (generic)

**Flow** (same as Entra ID):
1. User clicks "Sign in with [Provider]"
2. User authenticates with provider
3. Hobboverse creates/updates local user
4. User proceeds to avatar creation
5. User enters room lobby

**Configuration Example (Cognito)**:
```yaml
auth:
  oauth2_providers:
    - name: "cognito"
      enabled: true
      provider_type: "cognito"
      client_id: "${COGNITO_CLIENT_ID}"
      client_secret: "${COGNITO_CLIENT_SECRET}"
      domain: "hobbo.auth.us-east-1.amazoncognito.com"
      redirect_uri: "https://app.example.com/auth/callback/cognito"
      scopes:
        - "openid"
        - "email"
        - "profile"

    - name: "google"
      enabled: false
      provider_type: "google"
      client_id: "${GOOGLE_CLIENT_ID}"
      client_secret: "${GOOGLE_CLIENT_SECRET}"
      redirect_uri: "https://app.example.com/auth/callback/google"
      scopes:
        - "openid"
        - "email"
        - "profile"

    - name: "github"
      enabled: false
      provider_type: "github"
      client_id: "${GITHUB_CLIENT_ID}"
      client_secret: "${GITHUB_CLIENT_SECRET}"
      redirect_uri: "https://app.example.com/auth/callback/github"
      scopes:
        - "read:user"
        - "user:email"
```

**Security**:
- PKCE enforced for all flows
- State parameter prevents CSRF attacks
- Access token stored securely (httpOnly cookie or secure session)
- Refresh token rotation if supported by provider

---

## 5. Configuration System

### 5.1 Master Configuration File
**File**: `server/config.py` and environment-based overrides

**Structure**:
```python
import os
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

@dataclass
class PasswordPolicy:
    """Password complexity requirements"""
    min_length: int = 8
    require_uppercase: bool = True
    require_lowercase: bool = True
    require_digits: bool = True
    require_special: bool = True
    special_chars: str = "!@#$%^&*()_+-=[]{}|;:,.<>?"
    expiry_days: Optional[int] = None  # None = never expires

@dataclass
class SessionConfig:
    """Session and token settings"""
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    max_sessions_per_user: int = 5
    session_timeout_minutes: int = 30  # Inactivity timeout

@dataclass
class AzureEntraIDConfig:
    """Azure Entra ID OAuth2 configuration"""
    enabled: bool = False
    client_id: str = ""
    client_secret: str = ""
    tenant_id: str = ""
    redirect_uri: str = ""
    scopes: List[str] = None
    allowed_groups: Optional[List[str]] = None
    default_role: str = "learner"
    auto_provision: bool = True

@dataclass
class OAuth2ProviderConfig:
    """Generic OAuth2 provider configuration"""
    name: str
    enabled: bool = False
    provider_type: str  # "cognito", "google", "github", "custom"
    client_id: str = ""
    client_secret: str = ""
    authorization_endpoint: str = ""
    token_endpoint: str = ""
    userinfo_endpoint: str = ""
    redirect_uri: str = ""
    scopes: List[str] = None
    default_role: str = "learner"

@dataclass
class AuthConfig:
    """Master authentication configuration"""
    # Authentication models
    enable_local_registration: bool = False
    enable_local_login: bool = True
    admin_only_registration: bool = False
    
    # OAuth2
    enable_oauth2: bool = False
    oauth2_providers: List[OAuth2ProviderConfig] = None
    
    # Azure Entra ID
    azure_entra_id: Optional[AzureEntraIDConfig] = None
    
    # Password and session policies
    password_policy: PasswordPolicy = None
    session_config: SessionConfig = None
    
    # Email verification
    require_email_verification: bool = False
    email_verification_token_expire_hours: int = 24
    
    # Rate limiting
    registration_rate_limit_per_hour: int = 10
    login_rate_limit_per_hour: int = 100
    failed_login_lockout_threshold: int = 5
    failed_login_lockout_minutes: int = 15
    
    # Security
    require_https: bool = True
    cors_allowed_origins: List[str] = None
    
    # Feature flags
    allow_password_reset: bool = True
    allow_profile_editing: bool = True
    require_avatar_on_first_login: bool = True

# Load from environment
auth_config = AuthConfig(
    enable_local_registration=os.getenv("AUTH_ENABLE_LOCAL_REGISTRATION", "false").lower() == "true",
    enable_local_login=os.getenv("AUTH_ENABLE_LOCAL_LOGIN", "true").lower() == "true",
    admin_only_registration=os.getenv("AUTH_ADMIN_ONLY_REGISTRATION", "false").lower() == "true",
    enable_oauth2=os.getenv("AUTH_ENABLE_OAUTH2", "false").lower() == "true",
    require_email_verification=os.getenv("AUTH_REQUIRE_EMAIL_VERIFICATION", "false").lower() == "true",
    require_https=os.getenv("REQUIRE_HTTPS", "true").lower() == "true",
    cors_allowed_origins=(
        os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",")
    ),
)
```

### 5.2 Environment Variables
**Production `.env` example**:
```bash
# Deployment
REQUIRE_HTTPS=true
CORS_ALLOWED_ORIGINS=https://app.example.com,https://staging.example.com

# Local Authentication
AUTH_ENABLE_LOCAL_REGISTRATION=false
AUTH_ENABLE_LOCAL_LOGIN=true
AUTH_ADMIN_ONLY_REGISTRATION=true
AUTH_REQUIRE_EMAIL_VERIFICATION=true

# Azure Entra ID
AUTH_ENABLE_OAUTH2=true
AZURE_CLIENT_ID=your-app-id
AZURE_CLIENT_SECRET=your-secret
AZURE_TENANT_ID=your-tenant-id
AZURE_REDIRECT_URI=https://app.example.com/auth/callback/azure

# Password Policy
AUTH_PASSWORD_MIN_LENGTH=12
AUTH_PASSWORD_REQUIRE_UPPERCASE=true
AUTH_PASSWORD_REQUIRE_SPECIAL=true

# Session
AUTH_ACCESS_TOKEN_EXPIRE_MINUTES=60
AUTH_REFRESH_TOKEN_EXPIRE_DAYS=30
AUTH_SESSION_TIMEOUT_MINUTES=60

# Rate Limiting
AUTH_LOGIN_RATE_LIMIT_PER_HOUR=100
AUTH_FAILED_LOGIN_LOCKOUT_THRESHOLD=5

# Email (for verification and password reset)
SMTP_SERVER=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USERNAME=apikey
SMTP_PASSWORD=your-sendgrid-api-key
ADMIN_EMAIL=admin@example.com
```

---

## 6. Database Schema

### 6.1 Users Table
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(100) UNIQUE,  -- NULL for OAuth2-only users
    display_name VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255),  -- NULL for OAuth2-only users
    avatar_id UUID,
    
    -- OAuth2 / Entra ID
    entra_id_sub VARCHAR(255) UNIQUE,  -- Azure Entra ID subject claim
    -- NOTE: These two columns track the LAST used generic OAuth2 provider as a convenience
    -- cache. The source of truth for ALL linked identities (including Entra ID) is the
    -- oauth2_identities table. A user may have multiple rows there (one per provider).
    oauth2_sub VARCHAR(255),  -- Last-used generic OAuth2 subject claim (cache)
    oauth2_provider VARCHAR(50),  -- Last-used generic OAuth2 provider name (cache)
    
    -- Account Status
    is_active BOOLEAN DEFAULT true,
    is_admin BOOLEAN DEFAULT false,
    is_moderator BOOLEAN DEFAULT false,
    role VARCHAR(50) DEFAULT 'learner',  -- learner, educator, admin, moderator
    
    -- Profile
    bio TEXT,
    avatar_customization JSONB,  -- Avatar color/style preferences
    preferred_topics TEXT[],
    
    -- Email Verification
    email_verified BOOLEAN DEFAULT false,
    email_verified_at TIMESTAMP,
    
    -- Account Management
    password_changed_at TIMESTAMP,
    password_expires_at TIMESTAMP,  -- NULL if no expiry
    last_login_at TIMESTAMP,
    failed_login_attempts INTEGER DEFAULT 0,
    locked_until TIMESTAMP,  -- Account lockout timestamp
    
    -- Audit
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by UUID REFERENCES users(id),  -- Admin who created account
    deleted_at TIMESTAMP  -- Soft delete
);

CREATE INDEX idx_users_email ON users(email) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_username ON users(username) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_entra_id_sub ON users(entra_id_sub) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_oauth2_sub ON users(oauth2_provider, oauth2_sub) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_role ON users(role);
```

### 6.2 Sessions Table
```sql
CREATE TABLE user_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Token Management
    access_token_hash VARCHAR(255) NOT NULL UNIQUE,  -- Hash of token
    refresh_token_hash VARCHAR(255) UNIQUE,
    access_token_expires_at TIMESTAMP NOT NULL,
    refresh_token_expires_at TIMESTAMP,
    
    -- Session Info
    device_name VARCHAR(255),  -- "Chrome on macOS", etc.
    user_agent VARCHAR(500),
    ip_address VARCHAR(45),  -- IPv4 or IPv6
    
    -- Status
    is_active BOOLEAN DEFAULT true,
    revoked_at TIMESTAMP,
    
    -- Audit
    created_at TIMESTAMP DEFAULT NOW(),
    last_activity_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_sessions_user_id ON user_sessions(user_id);
CREATE INDEX idx_sessions_access_token_hash ON user_sessions(access_token_hash);
CREATE INDEX idx_sessions_refresh_token_hash ON user_sessions(refresh_token_hash);
```

### 6.3 OAuth2 Identities Table
```sql
CREATE TABLE oauth2_identities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Provider Info
    provider VARCHAR(50) NOT NULL,  -- "azure", "cognito", "google", "github"
    provider_user_id VARCHAR(255) NOT NULL,  -- Subject claim from provider
    
    -- Synced Profile Data
    profile_data JSONB,  -- { "name": "...", "email": "...", "picture": "..." }
    
    -- Audit
    created_at TIMESTAMP DEFAULT NOW(),
    last_synced_at TIMESTAMP,
    
    UNIQUE(provider, provider_user_id)
);

CREATE INDEX idx_oauth2_identities_user_id ON oauth2_identities(user_id);
```

### 6.4 Email Verification Tokens Table
```sql
CREATE TABLE email_verification_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    token_hash VARCHAR(255) NOT NULL UNIQUE,
    expires_at TIMESTAMP NOT NULL,
    used_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_verification_tokens_user_id ON email_verification_tokens(user_id);
```

### 6.5 Password Reset Tokens Table
```sql
CREATE TABLE password_reset_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    token_hash VARCHAR(255) NOT NULL UNIQUE,
    expires_at TIMESTAMP NOT NULL,
    used_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_password_reset_tokens_user_id ON password_reset_tokens(user_id);
```

### 6.6 Audit Log Table
```sql
CREATE TABLE auth_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    
    event_type VARCHAR(100),  -- "login", "registration", "password_change", "oauth2_sync", etc.
    event_status VARCHAR(50),  -- "success", "failure"
    event_message TEXT,
    
    ip_address VARCHAR(45),
    user_agent VARCHAR(500),
    
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_audit_log_user_id ON auth_audit_log(user_id);
CREATE INDEX idx_audit_log_event_type ON auth_audit_log(event_type);
CREATE INDEX idx_audit_log_created_at ON auth_audit_log(created_at DESC);
```

---

## 7. API Endpoints

### 7.1 Authentication Endpoints

#### 7.1.1 Register (Local)
**POST** `/api/auth/register`

**Request**:
```json
{
  "email": "user@example.com",
  "password": "SecurePass123!",
  "display_name": "John Learner",
  "agreed_to_terms": true
}
```

**Response (201 Created)**:
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "display_name": "John Learner",
  "email_verified": false,
  "requires_avatar": true,
  "message": "Registration successful. Please check your email to verify your account."
}
```

**Errors**:
- 400: Invalid email format, password too weak, user already exists
- 429: Rate limit exceeded
- 503: Service unavailable

---

#### 7.1.2 Login (Local)
**POST** `/api/auth/login`

**Request**:
```json
{
  "email_or_username": "user@example.com",
  "password": "SecurePass123!"
}
```

**Response (200 OK)**:
```json
{
  "access_token": "eyJhbGc...",
  "refresh_token": "eyJhbGc...",
  "expires_in": 1800,
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "display_name": "John Learner",
    "avatar_id": "uuid-or-null",
    "role": "learner"
  }
}
```

**Errors**:
- 400: Missing fields
- 401: Invalid credentials
- 403: Account locked (too many failed attempts)
- 429: Rate limit exceeded

---

#### 7.1.3 Get Current Auth Status
**GET** `/api/auth/me`

**Headers**:
```
Authorization: Bearer {access_token}
```

**Response (200 OK)**:
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "display_name": "John Learner",
  "role": "learner",
  "avatar_id": "uuid-or-null",
  "requires_password_change": false,
  "requires_avatar": false,
  "auth_provider": "local"
}
```

**Errors**:
- 401: Token missing, expired, or revoked

*Used by the frontend on page load to validate an existing token and restore app state without a full profile fetch.*

---

#### 7.1.4 Get Available Auth Providers
**GET** `/api/auth/providers`

*Public endpoint — no authentication required.*

**Response (200 OK)**:
```json
{
  "local_registration_enabled": false,
  "local_login_enabled": true,
  "oauth2_providers": [
    {
      "name": "azure",
      "label": "Sign in with Microsoft",
      "authorize_url": "/api/auth/oauth2/authorize/azure"
    },
    {
      "name": "google",
      "label": "Sign in with Google",
      "authorize_url": "/api/auth/oauth2/authorize/google"
    }
  ]
}
```

*The frontend calls this once at startup to dynamically render the login screen: show/hide the registration link and render provider buttons for each enabled OAuth2 provider.*

---

#### 7.1.5 Resend Email Verification
**POST** `/api/auth/resend-verification`

**Headers**:
```
Authorization: Bearer {access_token}
```

**Response (200 OK)**:
```json
{
  "message": "Verification email resent. Please check your inbox."
}
```

**Errors**:
- 400: Email already verified
- 429: Rate limit exceeded (max 3 resend requests per hour)

---

#### 7.1.6 OAuth2 Authorize
**GET** `/api/auth/oauth2/authorize/{provider}`

**Query Parameters**:
- `provider`: "azure", "cognito", "google", "github"
- `state`: PKCE state (generated by frontend)
- `code_challenge`: PKCE code challenge
- `code_challenge_method`: "S256"

**Response (302 Redirect)**:
Redirects to OAuth2 provider's authorization endpoint (e.g., Azure login)

---

#### 7.1.7 OAuth2 Callback
**POST** `/api/auth/oauth2/callback/{provider}`

**Request**:
```json
{
  "code": "auth_code_from_provider",
  "state": "original_state",
  "code_verifier": "pkce_verifier"
}
```

**Response (200 OK)**:
```json
{
  "access_token": "eyJhbGc...",
  "refresh_token": "eyJhbGc...",
  "expires_in": 1800,
  "is_new_user": true,
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "display_name": "John Learner",
    "avatar_id": null,
    "role": "learner"
  }
}
```

**Errors**:
- 400: Invalid authorization code, state mismatch
- 401: Provider authentication failed
- 500: Token exchange failed

---

#### 7.1.8 Refresh Token
**POST** `/api/auth/refresh`

**Request**:
```json
{
  "refresh_token": "eyJhbGc..."
}
```

**Response (200 OK)**:
```json
{
  "access_token": "eyJhbGc...",
  "expires_in": 1800
}
```

**Errors**:
- 400: Invalid refresh token
- 401: Refresh token expired

---

#### 7.1.9 Logout
**POST** `/api/auth/logout`

**Headers**:
```
Authorization: Bearer {access_token}
```

**Response (200 OK)**:
```json
{
  "message": "Logged out successfully"
}
```

---

#### 7.1.10 Verify Email
**POST** `/api/auth/verify-email`

**Request**:
```json
{
  "token": "email_verification_token"
}
```

**Response (200 OK)**:
```json
{
  "message": "Email verified successfully"
}
```

---

#### 7.1.11 Request Password Reset
**POST** `/api/auth/password-reset/request`

**Request**:
```json
{
  "email": "user@example.com"
}
```

**Response (200 OK)**:
```json
{
  "message": "If an account with this email exists, a password reset link has been sent."
}
```

---

#### 7.1.12 Reset Password
**POST** `/api/auth/password-reset/confirm`

**Request**:
```json
{
  "token": "password_reset_token",
  "new_password": "NewSecurePass123!"
}
```

**Response (200 OK)**:
```json
{
  "message": "Password reset successful. Please log in with your new password."
}
```

---

### 7.1.x Standard Error Response Envelope

All error responses across all auth endpoints share a consistent JSON structure:

```json
{
  "error": "INVALID_CREDENTIALS",
  "message": "The provided email or password is incorrect.",
  "details": {}
}
```

**Common `error` codes**:

| Code | HTTP Status | Meaning |
|------|-------------|----------|
| `INVALID_CREDENTIALS` | 401 | Wrong email/password |
| `ACCOUNT_LOCKED` | 403 | Too many failed attempts |
| `EMAIL_NOT_VERIFIED` | 403 | Email verification required |
| `PASSWORD_CHANGE_REQUIRED` | 403 | First-login password change required |
| `TOKEN_EXPIRED` | 401 | Access or refresh token expired |
| `TOKEN_INVALID` | 401 | Token is malformed or revoked |
| `EMAIL_TAKEN` | 409 | Email already registered |
| `USERNAME_TAKEN` | 409 | Username already taken |
| `WEAK_PASSWORD` | 400 | Password does not meet complexity policy |
| `REGISTRATION_DISABLED` | 403 | Open registration is turned off |
| `PROVIDER_UNAVAILABLE` | 503 | OAuth2 provider unreachable |
| `RATE_LIMITED` | 429 | Too many requests |
| `FORBIDDEN` | 403 | Insufficient permissions (e.g., not admin) |
| `NOT_FOUND` | 404 | Resource not found |
| `VALIDATION_ERROR` | 400 | Input field validation failed; `details` contains per-field errors |

---

### 7.2 User Management Endpoints (Admin Only)

#### 7.2.1 Create User (Admin)
**POST** `/api/admin/users`

**Headers**:
```
Authorization: Bearer {access_token}
```

**Request**:
```json
{
  "email": "user@example.com",
  "username": "john_learner",
  "display_name": "John Learner",
  "role": "learner",
  "send_welcome_email": true
}
```

**Response (201 Created)**:
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "username": "john_learner",
  "display_name": "John Learner",
  "temporary_password": "TempPass123!456",
  "message": "User created. Welcome email sent with temporary password."
}
```

---

#### 7.2.2 List Users (Admin)
**GET** `/api/admin/users?role=learner&is_active=true&limit=50&offset=0`

**Response (200 OK)**:
```json
{
  "users": [
    {
      "id": "uuid",
      "email": "user@example.com",
      "display_name": "John Learner",
      "role": "learner",
      "is_active": true,
      "last_login_at": "2026-08-24T10:30:00Z",
      "created_at": "2026-08-20T14:22:00Z"
    }
  ],
  "total": 150,
  "limit": 50,
  "offset": 0
}
```

---

#### 7.2.3 Get User (Admin)
**GET** `/api/admin/users/{user_id}`

**Response (200 OK)**:
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "username": "john_learner",
  "display_name": "John Learner",
  "role": "learner",
  "is_active": true,
  "is_admin": false,
  "is_moderator": false,
  "email_verified": true,
  "last_login_at": "2026-08-24T10:30:00Z",
  "password_changed_at": "2026-08-20T14:22:00Z",
  "created_at": "2026-08-20T14:22:00Z",
  "oauth2_provider": null
}
```

---

#### 7.2.4 Update User (Admin)
**PATCH** `/api/admin/users/{user_id}`

**Request**:
```json
{
  "display_name": "John Q. Learner",
  "role": "educator",
  "is_active": true
}
```

**Response (200 OK)**:
```json
{
  "id": "uuid",
  "display_name": "John Q. Learner",
  "role": "educator",
  "is_active": true
}
```

---

#### 7.2.5 Reset User Password (Admin)
**POST** `/api/admin/users/{user_id}/reset-password`

**Response (200 OK)**:
```json
{
  "temporary_password": "TempPass123!456",
  "message": "Password reset. User will be required to change it on next login."
}
```

---

#### 7.2.6 Disable/Lock User Account (Admin)
**POST** `/api/admin/users/{user_id}/disable`

**Response (200 OK)**:
```json
{
  "message": "User account disabled"
}
```

---

#### 7.2.7 Enable User Account (Admin)
**POST** `/api/admin/users/{user_id}/enable`

**Response (200 OK)**:
```json
{
  "message": "User account enabled"
}
```

---

#### 7.2.8 Delete User (Admin)
**DELETE** `/api/admin/users/{user_id}`

**Response (204 No Content)**

---

#### 7.2.9 Bulk Import Users (Admin)
**POST** `/api/admin/users/import`

**Content-Type**: `multipart/form-data`

**Request**: CSV file upload (`file` field)

**CSV Format**:
```csv
email,username,display_name,role
john@example.com,john_learner,John Learner,learner
jane@example.com,jane_edu,Jane Smith,educator
admin2@example.com,,Admin Two,admin
```

- `email`: Required. Must be unique.
- `username`: Optional. If omitted, derived from email local part.
- `display_name`: Required.
- `role`: Optional. Defaults to `learner`. Allowed: `learner`, `educator`, `moderator`, `admin`.

**Response (200 OK)**:
```json
{
  "imported": 2,
  "skipped": 1,
  "errors": [
    {
      "row": 3,
      "email": "duplicate@example.com",
      "reason": "Email already exists"
    }
  ]
}
```

---

#### 7.2.10 Unlock User Account (Admin)
**POST** `/api/admin/users/{user_id}/unlock`

Manually unlocks an account that has been locked due to excessive failed login attempts.

**Response (200 OK)**:
```json
{
  "message": "User account unlocked. Failed attempt counter reset."
}
```

---

#### 7.2.11 Audit Log (Admin)
**GET** `/api/admin/audit-log?user_id=uuid&event_type=login&limit=50`

**Response (200 OK)**:
```json
{
  "events": [
    {
      "id": "uuid",
      "user_id": "uuid",
      "event_type": "login",
      "event_status": "success",
      "ip_address": "192.0.2.1",
      "created_at": "2026-08-24T10:30:00Z"
    }
  ],
  "total": 1000
}
```

---

### 7.3 User Profile Endpoints

#### 7.3.1 Get Current User Profile
**GET** `/api/user/profile`

**Headers**:
```
Authorization: Bearer {access_token}
```

**Response (200 OK)**:
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "display_name": "John Learner",
  "avatar_id": "uuid-or-null",
  "role": "learner",
  "bio": "I love learning!",
  "preferred_topics": ["math", "science"],
  "created_at": "2026-08-20T14:22:00Z"
}
```

---

#### 7.3.2 Update Current User Profile
**PATCH** `/api/user/profile`

**Request**:
```json
{
  "display_name": "John Q. Learner",
  "bio": "I love learning science and math!",
  "preferred_topics": ["math", "science", "history"]
}
```

**Response (200 OK)**:
```json
{
  "id": "uuid",
  "display_name": "John Q. Learner",
  "bio": "I love learning science and math!",
  "preferred_topics": ["math", "science", "history"]
}
```

---

#### 7.3.3 Change Password
**POST** `/api/user/password-change`

**Request**:
```json
{
  "current_password": "OldPass123!",
  "new_password": "NewSecurePass123!"
}
```

**Response (200 OK)**:
```json
{
  "message": "Password changed successfully"
}
```

**Errors**:
- 400: Password validation failed
- 401: Current password incorrect

---

#### 7.3.4 Get User Sessions
**GET** `/api/user/sessions`

**Response (200 OK)**:
```json
{
  "sessions": [
    {
      "id": "uuid",
      "device_name": "Chrome on macOS",
      "ip_address": "192.0.2.1",
      "last_activity_at": "2026-08-24T10:30:00Z",
      "created_at": "2026-08-23T09:15:00Z",
      "is_current": true
    }
  ]
}
```

---

#### 7.3.5 Revoke Session
**POST** `/api/user/sessions/{session_id}/revoke`

**Response (200 OK)**:
```json
{
  "message": "Session revoked"
}
```

---

## 8. Implementation Plan

### Phase 1: Local Authentication Foundation (Weeks 1-2)
**Objective**: Establish basic local email/password authentication

**Tasks**:
1. **T1.1**: Create database schema (users, sessions, verification tokens, reset tokens tables)
   - Create migrations
   - Add indexes for performance
   - Test schema creation

2. **T1.2**: Implement password hashing and validation utilities
   - Use bcrypt for hashing
   - Implement password strength validation
   - Unit tests for password validation

3. **T1.3**: Create User model and database layer
   - `server/game/user.py` with CRUD operations
   - User repository pattern
   - Unit tests with mocking

4. **T1.4**: Implement JWT token generation and validation
   - Create `server/game/auth.py` with token utilities
   - Access token and refresh token generation
   - Token validation and expiration logic
   - Unit tests

5. **T1.5**: Build authentication endpoints (registration, login, logout)
   - POST `/api/auth/register`
   - POST `/api/auth/login`
   - POST `/api/auth/logout`
   - POST `/api/auth/refresh`
   - Rate limiting middleware
   - Input validation
   - Integration tests

6. **T1.6**: Implement auth middleware
   - Bearer token extraction
   - Token validation in request middleware
   - Attach user to request context
   - 401 handling

**Testing**:
- Unit tests for password validation (15+ test cases)
- Unit tests for token generation/validation (20+ test cases)
- Integration tests for registration flow (10+ test cases)
- Integration tests for login flow (10+ test cases)
- Rate limit tests (5+ test cases)

**Deliverables**:
- Database migrations
- Core auth utilities
- Registration + login endpoints
- Auth middleware
- API documentation

---

### Phase 2: Admin-Only Registration Mode (Weeks 3)
**Objective**: Add admin user management and admin-only registration mode

**Tasks**:
1. **T2.1**: Create admin user management endpoints
   - POST `/api/admin/users` (create user)
   - GET `/api/admin/users` (list users)
   - GET `/api/admin/users/{id}` (get user)
   - PATCH `/api/admin/users/{id}` (update user)
   - POST `/api/admin/users/{id}/reset-password`
   - DELETE `/api/admin/users/{id}`

2. **T2.2**: Implement admin authorization middleware
   - Role-based access control (RBAC)
   - `is_admin` decorator for endpoints
   - 403 Forbidden handling

3. **T2.3**: Create first-login password reset flow
   - Force password change on first login
   - Endpoint validation logic
   - Frontend integration guidance

4. **T2.4**: Implement audit logging
   - Create audit log table
   - Log all auth events (login, registration, password change, etc.)
   - Admin audit log endpoint: GET `/api/admin/audit-log`

5. **T2.5**: Add configuration system
   - `server/config.py` with AuthConfig dataclass
   - Environment variable loading
   - Toggle admin-only registration mode
   - Unit tests for config loading

6. **T2.6**: Bulk user import
   - CSV parser for user import
   - POST `/api/admin/users/import` endpoint
   - Validation and error reporting

**Testing**:
- Integration tests for user creation (8+ test cases)
- Authorization tests (10+ test cases)
- First-login password reset flow tests (5+ test cases)
- Audit log verification (5+ test cases)
- CSV import tests (8+ test cases)

**Deliverables**:
- Admin user management endpoints
- RBAC system
- Audit logging system
- Configuration system
- CSV import capability

---

### Phase 3: Email Verification and Password Recovery (Weeks 4)
**Objective**: Add email-based account verification and password reset flows

**Tasks**:
1. **T3.1**: Implement email verification
   - Email verification token generation
   - POST `/api/auth/verify-email` endpoint
   - Email sending integration (SendGrid, Mailgun, or SMTP)
   - Resend verification email endpoint

2. **T3.2**: Implement password reset flow
   - POST `/api/auth/password-reset/request` (request reset)
   - POST `/api/auth/password-reset/confirm` (confirm reset)
   - Password reset token generation and validation
   - Email sending

3. **T3.3**: Email template system
   - Verification email template
   - Password reset email template
   - Welcome email template (for admin-created users)
   - Email sending service

4. **T3.4**: Configuration for email settings
   - SMTP configuration in config.py
   - Environment variables for email credentials
   - Email verification toggle

5. **T3.5**: Frontend guidance for email flows
   - Email verification page
   - Password reset page
   - Documentation

**Testing**:
- Email token generation/validation tests (8+ test cases)
- Password reset flow tests (10+ test cases)
- Email delivery tests (with mock SMTP)
- Token expiration tests (5+ test cases)

**Deliverables**:
- Email verification system
- Password reset system
- Email templates
- Email service integration

---

### Phase 4: Azure Entra ID Integration (Weeks 5-6)
**Objective**: Add enterprise SSO via Azure Entra ID

**Tasks**:
1. **T4.1**: Implement OAuth2 flow (PKCE)
   - State and code challenge generation (frontend)
   - Authorization endpoint redirect
   - Token exchange and validation
   - ID token verification (including JWT validation)

2. **T4.2**: Create OAuth2 identities table and model
   - Store provider user ID mapping
   - OAuth2Identities model
   - Sync user profile from Entra ID

3. **T4.3**: Build Entra ID token exchange endpoint
   - POST `/api/auth/oauth2/callback/azure`
   - Authorization code exchange for access token
   - ID token validation (JWT signature, claims)
   - User provisioning (create or update local user)

4. **T4.4**: Auto-user provisioning from Entra ID
   - Create user on first login
   - Sync profile data (name, email, profile picture)
   - Assign default role
   - Handle group-based role assignment (optional)

5. **T4.5**: Configuration for Azure Entra ID
   - Client ID, secret, tenant ID in config.py
   - Environment variables
   - Redirect URI configuration

6. **T4.6**: Implement Azure login UI (Frontend)
   - "Sign in with Microsoft" button
   - PKCE state/code challenge generation
   - Token handling and storage
   - Redirect after login

**Testing**:
- OAuth2 flow tests with mock provider (12+ test cases)
- JWT validation tests (10+ test cases)
- User provisioning tests (8+ test cases)
- Profile sync tests (5+ test cases)
- Error handling tests (10+ test cases)

**Deliverables**:
- OAuth2 callback endpoint
- Azure Entra ID integration
- User provisioning system
- ID token validation
- Frontend OAuth2 login flow
- Configuration documentation

---

### Phase 5: Multi-OAuth2 Support (Cognito, Google, GitHub) (Weeks 7-8)
**Objective**: Add support for additional OAuth2 providers

**Tasks**:
1. **T5.1**: Refactor OAuth2 to generic provider pattern
   - Base OAuth2Provider class
   - Provider-specific implementations (CognitoProvider, GoogleProvider, GitHubProvider)
   - Dynamic provider loading from config

2. **T5.2**: Implement AWS Cognito integration
   - Cognito authorization endpoint
   - Token exchange (with client credentials)
   - User info endpoint calls
   - Profile mapping

3. **T5.3**: Implement Google OAuth2
   - Google authorization endpoint
   - Token exchange
   - User info from Google
   - Profile picture handling

4. **T5.4**: Implement GitHub OAuth2
   - GitHub authorization endpoint
   - Token exchange
   - User info from GitHub API
   - Optional: GitHub organizations/teams for access control

5. **T5.5**: Configuration system for multiple providers
   - Update config.py with OAuth2ProviderConfig
   - Environment variables for each provider
   - Provider enable/disable toggles

6. **T5.6**: Frontend provider selection
   - Show available OAuth2 providers
   - Dynamic login button generation
   - Provider-specific redirect handling

**Testing**:
- Provider abstraction tests (8+ test cases)
- Cognito integration tests with mock (10+ test cases)
- Google integration tests with mock (10+ test cases)
- GitHub integration tests with mock (10+ test cases)
- Multi-provider configuration tests (8+ test cases)

**Deliverables**:
- Generic OAuth2 provider framework
- Cognito, Google, GitHub provider implementations
- Configuration system for multiple providers
- Frontend provider selection UI

---

### Phase 6: User Profiles and Session Management (Weeks 9)
**Objective**: User profile management and session tracking

**Tasks**:
1. **T6.1**: Implement user profile endpoints
   - GET `/api/user/profile`
   - PATCH `/api/user/profile`
   - Profile fields: bio, preferred_topics, avatar customization

2. **T6.2**: Implement session management endpoints
   - GET `/api/user/sessions` (list sessions)
   - POST `/api/user/sessions/{id}/revoke` (revoke session)
   - Device tracking (device_name, IP, user agent)

3. **T6.3**: Implement password change endpoint
   - POST `/api/user/password-change`
   - Require current password verification

4. **T6.4**: Session cleanup and activity tracking
   - Background job to clean up expired sessions
   - Last activity tracking
   - Session timeout on inactivity

5. **T6.5**: Multiple session support
   - Allow N active sessions per user
   - Revoke oldest session if limit exceeded
   - Device detection and labeling

**Testing**:
- Profile CRUD tests (8+ test cases)
- Session management tests (10+ test cases)
- Password change tests (8+ test cases)
- Session expiration tests (5+ test cases)
- Device tracking tests (5+ test cases)

**Deliverables**:
- User profile endpoints
- Session management system
- Device tracking
- Background cleanup jobs

---

### Phase 7: Security Hardening & Rate Limiting (Weeks 10)
**Objective**: Add security features and rate limiting

**Tasks**:
1. **T7.1**: Implement rate limiting
   - Registration rate limit
   - Login rate limit
   - Failed login lockout
   - Distributed rate limiting (Redis support)

2. **T7.2**: Account lockout mechanism
   - Track failed login attempts
   - Lock account after N failures
   - Automatic unlock after time period
   - Admin manual unlock

3. **T7.3**: Password policy enforcement
   - Configurable password complexity
   - Password expiration (optional)
   - Password history (don't allow recent passwords)

4. **T7.4**: CSRF and CORS hardening
   - CSRF token generation (if needed)
   - CORS configuration
   - Secure cookie settings
   - Same-site cookie policy

5. **T7.5**: Logging and monitoring
   - Detailed auth event logging
   - Suspicious activity detection
   - Alert system for anomalies (multiple failed logins, etc.)

**Testing**:
- Rate limit tests (12+ test cases)
- Account lockout tests (8+ test cases)
- Password policy tests (10+ test cases)
- CSRF/CORS tests (8+ test cases)

**Deliverables**:
- Rate limiting system
- Account lockout mechanism
- Password policy enforcement
- Security monitoring

---

### Phase 8: Testing and Documentation (Weeks 11-12)
**Objective**: Comprehensive testing, documentation, and deployment readiness

**Tasks**:
1. **T8.1**: End-to-end testing
   - Full registration → login → room join flow
   - Admin user creation → first login → password reset
   - OAuth2 flows for all providers
   - Session management and logout
   - Password recovery flow

2. **T8.2**: Security testing
   - Penetration testing for common vulnerabilities (OWASP Top 10)
   - Token leakage tests
   - SQL injection tests
   - XSS tests (frontend)
   - CSRF tests

3. **T8.3**: Performance testing
   - Load testing on login endpoints
   - Database query optimization
   - Token validation performance
   - OAuth2 provider integration performance

4. **T8.4**: Documentation
   - API documentation (OpenAPI/Swagger)
   - Configuration guide for admins
   - Deployment guide (Docker, env setup)
   - User guide (registration, login, profile)
   - Developer guide (extending OAuth2 providers)

5. **T8.5**: Release preparation
   - Database migration scripts
   - Deployment checklist
   - Rollback plan
   - Monitoring and alerts setup

**Testing**:
- 50+ end-to-end test cases
- 20+ security test cases
- Load testing (1000+ concurrent users)
- Performance benchmarks

**Deliverables**:
- Comprehensive API documentation
- Admin configuration guide
- User guides
- Developer documentation
- Security audit report

---

## 9. Development Progress Tracking

### Tracking Template
For each phase, track:
- **Phase Status**: Not Started → In Progress → Testing → Complete
- **Tasks Completed**: X/Y
- **Test Coverage**: X%
- **Bugs Found**: X (Critical, High, Medium, Low)
- **Known Issues**: List of blockers
- **Next Milestone**: Date and deliverables

### Progress Dashboard (last updated after the password-expiration + email-verification-login-gate + lockout-alert-email + OAuth2-provider-unavailable-handling + main-game-login-state + .env-config + guest-access-toggle + run-scripts TDD pass)

**Overall status**: Phases 1, 2, 3, 6, and Bootstrap (§18) are fully complete and validated against a real Postgres database. Phases 4 and 5 (Azure/OAuth2) are code-complete and fully unit-tested but not yet validated against a live identity provider tenant. Phase 7 core hardening is done, including a configurable guest/anonymous-access toggle; Redis-backed rate limiting, CSRF tokens, and an external pentest remain deferred by design. Phase 8 testing is done for everything implemented; formal external docs/security audit have not started. Phase 19 (frontend) has working login/register/OAuth2-callback pages, the main game restores/shows login state on load and can redirect anonymous visitors away when guest access is disabled, but there's still no admin dashboard, profile UI, or role-gated room actions. See §13 for a per-criterion checklist and the row-by-row notes below for exact caveats.

| Phase | Status | Tests | Notes |
|-------|--------|-------|-------|
| 1: Local Auth | **Complete** | 84 passing (`passwords`, `tokens`, `config`, `db/database` auth methods) | HS256 JWT (not RS256+rotation), bcrypt cost 12 directly (no passlib) |
| 2: Admin Reg | **Complete** | Covered by `service` admin methods (incl. bulk import), `routes`, `admin_routes` (15, incl. CSV import) | Full CRUD + disable/enable/unlock/soft-delete + audit log + **bulk CSV import** (`POST /api/admin/users/import`, §7.2.9) + RBAC via `require_role` |
| 6: Profiles/Sessions | **Complete** | 8 (`user_routes`) + session-cleanup coverage in `test_database_auth` | Profile get/update, password change, list/revoke sessions, admin-side revoke-via-`admin_reset_password`/`admin_disable_user`, **and** a periodic `session_cleanup_loop` (T6.4) that purges rows whose tokens can never be valid again, started from `lifespan` alongside the existing game loop |
| Bootstrap (§18) | **Complete** | 10 passing (`bootstrap`) + 8 passing (`test_create_admin_script`) | `INITIAL_ADMIN_EMAIL`/`INITIAL_ADMIN_PASSWORD` env-driven first-admin creation, run from `lifespan`. **§18.2 CLI script** `python -m server.scripts.create_admin --email ... --display-name ...` also implemented: prompts for a password with no terminal echo (`getpass`, with confirm-match retry), for operators who don't want a real admin password sitting in shell history/.env files. |
| 3: Email/Password Recovery | **Complete** | 7 passing (`email`) + service/route wiring tests | `server/auth/email.py` adds a real `SmtpEmailSender` (aiosmtplib) plus a `LoggingEmailSender` dev fallback used when `SMTP_SERVER` is unset. Registration (when `AUTH_REQUIRE_EMAIL_VERIFICATION=true`), password-reset-request, and admin-created-user welcome emails all now dispatch through this layer. **`login()` now actually enforces `AUTH_REQUIRE_EMAIL_VERIFICATION`**: previously the setting only controlled whether a verification email was sent at registration, but an unverified user could still log in and use the app regardless — a real gap between the doc's own `EMAIL_NOT_VERIFIED` error code (§7.1.x) and the code, since that error was never actually raised anywhere. Login now raises a 403 `EMAIL_NOT_VERIFIED` for an unverified local account when the setting is on (checked *after* password verification, so it can't be used to enumerate unverified accounts without already knowing a valid password); admin-created and OAuth2-provisioned accounts are unaffected since both already force `email_verified=True` at creation time. Not yet tested against a real SMTP server/inbox (no mail provider credentials in this environment) — verified via mocked `aiosmtplib.send` instead. |
| 4: Azure Entra ID | **Complete (code-level; validated against a real Postgres, not yet against a live tenant)** | Covered by `oidc` (9), `oauth2` (16 total incl. Azure path + `groups` claim + provider-unavailable), `oauth2_providers` (9, incl. `AZURE_ALLOWED_GROUPS`), `oauth2_routes` (10, incl. group-rejection 403 + provider-unavailable 503) | Full PKCE authorize/callback flow, RS256 id_token signature verification via a live JWKS fetch (`server/auth/oidc.py`), `aud`/`iss`/`exp` claim checks, auto-provisioning + account-linking by email, and **§4.3 `allowed_groups` enforcement**: `AZURE_ALLOWED_GROUPS` (comma-separated) is checked against the id_token's `groups` claim on *every* login (not just first), so removing someone from the group takes effect immediately; a non-member gets a 403 `FORBIDDEN`. A genuinely unreachable provider (token endpoint, JWKS endpoint, or profile endpoint down/timing out) now correctly returns 503 `PROVIDER_UNAVAILABLE` instead of a misleading 401 `INVALID_CREDENTIALS` (fixed this pass — see Deliberate Deviations). `AZURE_CLIENT_ID`/`AZURE_CLIENT_SECRET`/`AZURE_TENANT_ID` env-driven. No real Azure AD tenant was available to test end-to-end, so the JWKS/token-exchange HTTP calls are verified with a locally-generated RSA keypair and a scripted `httpx` transport rather than a live Microsoft login. |
| 5: Multi-OAuth2 (Cognito/Google/GitHub) | **Complete (code-level; untested against live providers)** | Same test files as Phase 4 (generic framework), plus GitHub-specific profile-fetch tests | Google and Cognito reuse the same OIDC id_token path as Azure (`server/auth/oidc.py`); GitHub uses its REST `/user` + `/user/emails` endpoints instead (no id_token), and a network failure reaching any of those now also maps to 503 `PROVIDER_UNAVAILABLE` rather than a raw unhandled exception. `GOOGLE_CLIENT_ID`/`GITHUB_CLIENT_ID`/`COGNITO_CLIENT_ID`(+`_DOMAIN`/`_REGION`/`_USER_POOL_ID`) env-driven; a provider only appears in `GET /api/auth/providers` once its credentials are set — no separate `enabled` flag to keep in sync. Same caveat as Phase 4: no real provider credentials were available to test against live. |
| 7: Security Hardening & Rate Limiting | **Core hardening complete; Redis/CSRF/pentest deferred** | – | Done: bcrypt cost 12, dummy-hash timing mitigation on login, account lockout after N failures (now correctly **cleared by a successful password reset**), **password history** (T7.3 — `AUTH_PASSWORD_HISTORY_COUNT`, default 5; rejects reusing the live password or any of the last N-1 retired ones on both `change_password` and `confirm_password_reset`, checked via real bcrypt comparison against stored hashes in a new `password_history` table, not just token/timestamp matching), **password expiration** (§5.1 `PasswordPolicy.expiry_days`, env `AUTH_PASSWORD_EXPIRY_DAYS`, default `None`/disabled; `users.password_changed_at` is now populated at both `create_user` and `set_password` time using the app's own epoch-ms clock — not SQL-side `NOW()` — so it can be compared deterministically against `login()`'s `now_ms`; a login with an expired password sets `requires_password_change=True` as a **soft** flag, matching the existing, already-non-blocking semantics of that same flag elsewhere — it does not hard-block the login itself, the frontend is expected to redirect on seeing it), **T7.5 lockout alert email** (§10.6 "alert on multiple failed logins": the account owner now gets an email the moment their account crosses the failed-attempt threshold and gets locked, via a new `build_account_locked_email` template — sent exactly once per lockout event, not on every subsequent attempt while still locked), **guest/anonymous-access toggle** (`AUTH_ALLOW_GUEST_ACCESS`, default `true`; exposed via `GET /api/auth/providers`'s new `allow_guest_access` field; when `false`, `client/login.html` hides its "Continue as a guest" link and `client/js/main.js` redirects an anonymous visitor to the login page instead of showing the creator screen — a client-side UX gate, not the actual enforcement boundary; combine with `AUTH_REQUIRE_SOCKET_AUTH=true` for a real backend-enforced one), in-memory sliding-window rate limits on login/registration/OAuth2 login, generic (non-account-enumerating) error messages, SQL parametrization + column allowlisting, JWT algorithm pinned to HS256, OIDC id_token algorithm pinned to RS256 (rejects `alg=none`/confusion attacks), OAuth2 email-verified-claim check before account linking/auto-provisioning (prevents unverified-email account takeover), OAuth2 `allowed_groups` enforcement (§4.3), bounded request field/query/file-upload lengths on all new auth+OAuth2+admin endpoints, **optional Socket.IO JWT enforcement** (`AUTH_REQUIRE_SOCKET_AUTH`, off by default — see §16 notes below). Deferred: Redis-backed distributed rate limiting (current limiter is in-memory/single-process only), CSRF tokens (not needed yet since the API is bearer-token based, not cookie-session based), broader anomaly/suspicious-pattern detection beyond the lockout-threshold email (§10.6's "new device/location" alerting), full external pentest. |
| 8: Testing and Documentation | **Testing done for implemented phases, including three real-Postgres validation passes; external docs/pentest not started** | 1588 Python + 746 JS suite passes | No dedicated user-facing docs page or third-party security audit performed. |
| 19: Frontend UI | **Partial — login/register/OAuth2-callback pages shipped, main game restores/displays login state and enforces the guest-access toggle; not Material Web components; still no admin/profile/session-list UI** | 30 passing (`tests/auth-client.test.js`) | `client/login.html` + `client/js/auth-page.js` (tabs for sign-in/register, dynamic OAuth2 provider buttons from `GET /api/auth/providers`) and `client/auth-callback.html` + `client/js/auth-callback-page.js` (PKCE callback, state-mismatch protection) are real, working pages reusing this app's existing dark Material-3-*token*-based CSS (not the literal `@material/web` custom-element library — see deviations). The pure client logic (form validation, PKCE generation, token storage, all API calls, and now a new `bootstrapSession()` helper) lives in `src/auth-client.js` and is fully unit-tested; the thin DOM-wiring files (`auth-page.js`, `auth-callback-page.js`, `main.js`) are not, matching this repo's existing convention that only `src/*.js` is vitest-covered. **Fixed this pass — main game login-state gap**: `client/js/main.js` now calls `bootstrapSession()` on load to exchange a stored refresh token for an access token + profile; if it succeeds, the global-controls "Sign in" link becomes a "Sign out (name)" control instead, and the access token is attached to the Socket.IO connection's `auth: { token }` option (design doc §16.1) so `AUTH_REQUIRE_SOCKET_AUTH=true` deployments actually work for a real logged-in player, not just anonymous ones. Signing out calls `POST /api/auth/logout`, clears the stored refresh token, and reloads. **New this pass — guest-access toggle**: `client/js/auth-page.js`'s `initProviders()` now also reads `allow_guest_access` from `GET /api/auth/providers` and reveals/hides the "Continue as a guest instead" link on the login page accordingly (fails *open*/visible if the fetch itself fails, matching the backend's own fail-open default); `main.js`'s `initAuthSession()` fetches the same field in parallel with `bootstrapSession()` and redirects an anonymous visitor to `/login.html?redirect=...` when it's `false`. This is a client-side UX gate, not the real security boundary — see the Phase 7 row and Deliberate Deviations for what that means in practice. **Still not done**: profile page, admin dashboard/user table/audit-log viewer, session-list UI, first-login forced password-change page, email-verification-pending page — none of those are reachable from the main game yet, only the sign-in/sign-out toggle. |

**Total new automated tests added for this feature**: 338 (25 passwords + 12 tokens + 12 config + 42 database auth methods + 81 service + 11 dependencies + 24 routes + 15 admin routes + 8 user routes + 10 bootstrap + 8 create_admin_script + 7 email + 9 oidc + 16 oauth2 + 9 oauth2_providers + 10 oauth2_routes + 6 socket auth + 30 frontend auth-client + 3 generate_env script), all passing. Full repository suite: **1588 Python passed / 746 JS passed**, 0 failed.

### Frontend implementation notes (§19)
- **What exists**: a real login/register page and a real OAuth2 callback page, both fully wired to the backend (register, login, provider discovery, PKCE authorize/callback) and visually verified in a browser. Two real bugs were found and fixed during that visual check:
  1. A CSS bug where `.auth-divider`/`.auth-providers` set `display: flex` unconditionally, silently overriding the native `[hidden]` attribute so the OAuth2 "or" divider stayed visible even with zero configured providers.
  2. A logic bug where showing the post-registration success banner *before* switching back to the login tab lost the message, because the tab-switch helper unconditionally clears the banner — fixed by reordering.
  3. **Security-relevant**: the access token was briefly written to `sessionStorage` after login/OAuth2 callback even though nothing yet reads it back out (the main game has no auth integration), which only added unnecessary XSS exposure for no functional benefit. Removed — only the refresh token is persisted (in `sessionStorage`, never `localStorage`), exactly matching §19.6's documented rationale.
- **What's deliberately deferred**: the full Material 3 Web Components library (`@material/web`) was **not** added as a dependency; this app already has a hand-built dark theme using the same M3 color/shape/elevation *design tokens* (`--md-*` CSS custom properties in `styles.css`) without the custom-element library itself, so the new pages reuse that existing system for visual consistency rather than introducing a second, parallel component library. Admin dashboard UI (§7.2's user table/audit log), the self-service profile/session-management UI (§7.3), and first-login forced-password-change UI remain unbuilt — those endpoints are complete and tested on the backend but have no frontend yet.
- **Fixed this pass — main game now restores login state**: `client/js/main.js` calls a new `bootstrapSession()` helper (`src/auth-client.js`, unit-tested) on load, which exchanges a stored refresh token for an access token + `/api/auth/me` profile. On success, the global-controls "Sign in" link becomes a "Sign out (<name>)" control (calls `POST /api/auth/logout`, clears the stored refresh token, reloads), and the access token is attached to the Socket.IO connection's `auth: { token }` option so §16's optional `AUTH_REQUIRE_SOCKET_AUTH` actually has a real token to check for a logged-in player, not just anonymous ones. This is intentionally minimal (a HUD toggle, not a profile/account page) and doesn't gate any room/game actions by role yet — that remains a future increment.

### Real-Postgres validation pass (critical bugs found and fixed)
All auth persistence tests use hand-rolled `FakePool`/`FakeUserRepo` doubles (see Testing Convention notes throughout this doc's history), which never enforce real asyncpg/Postgres type semantics. As part of this update, the auth schema was applied to the project's actual `docker-compose` Postgres instance and exercised end-to-end (register → login → lockout → password-reset → bulk-import → OAuth2 login), which surfaced two real bugs invisible to the mocked test suite:

1. **Epoch-ms vs. TIMESTAMPTZ type mismatch (critical)**: `AuthService` works entirely in epoch-millisecond floats, but `user_sessions.access/refresh_token_expires_at`, `users.locked_until`, `email_verification_tokens.expires_at`, and `password_reset_tokens.expires_at` are all `TIMESTAMPTZ` columns. asyncpg requires a real `datetime` for a timestamptz parameter and raises `DataError` on a bare float — meaning **every login, registration, password-reset-request, and email-verification-request would have failed against a real database**, despite 200+ passing mocked unit tests. Fixed with an `_epoch_ms_to_datetime()` conversion helper in `server/db/database.py`, applied at every write site.
2. **Lockout not cleared by password reset**: `confirm_password_reset` changed the password but left `locked_until`/`failed_login_attempts` untouched, so a user who forgot their password and successfully reset it via email still had to wait out the lockout timer. Fixed by calling `unlock_account` inside `confirm_password_reset`, since a completed email-based reset is a stronger identity proof than the mechanism the lockout guards against.

Both fixes are covered by new/updated unit tests, and the full flow (including bulk import and an OAuth2 login writing to `oauth2_identities`' JSONB `profile_data` column) was re-run successfully against the live Postgres container after the fixes.

**Second validation pass** (after adding password history + the CLI bootstrap script): the updated schema (new `password_history` table) was re-applied to the same live container and re-exercised end-to-end — a real password-reuse rejection (bcrypt-comparing the new password against stored historical hashes, not just a format check) and a real CLI-driven admin creation both succeeded against actual Postgres on the first try, with no further type-mismatch surprises.

**Third validation pass** (password expiration): before this feature, `Database.set_password()` was the one remaining write path still using SQL-side `NOW()` for a timestamp instead of the app's own `now_ms` clock, unlike every other timestamp in the auth system. This was fixed in passing (it's now `set_password(user_id, password_hash, now_ms)`, converted via the same `_epoch_ms_to_datetime()` helper as everywhere else) since `login()`'s new expiry check needs to compare its own `now_ms` against `password_changed_at` deterministically — if the latter were set by the database's clock instead, a test (or a real deployment with clock skew between the app host and DB host) couldn't reason about the comparison precisely. An ad-hoc script exercised `create_user` → `set_password` → `get_user_by_id` against the live container to confirm the round-tripped `password_changed_at` value matches the `now_ms` that was sent within a couple of seconds; no mismatch was found, so no further code changes were required (this pass was confirmatory rather than bug-finding, unlike the first two).

### Deliberate deviations from this design doc
- **JSON casing**: camelCase over the wire (`displayName`, `emailOrUsername`, `newPassword`, `codeVerifier`, ...) instead of the doc's snake_case examples, to match this codebase's existing convention (`server/game/story.py`).
- **JWT**: HS256 with a single secret, not RS256 + key rotation (§17) — this is a single-process app with no downstream service that independently verifies tokens, so the added complexity isn't justified yet. (Note: OIDC id_tokens *from providers* are still verified as RS256, per each provider's own JWKS — this deviation is only about the tokens this app itself issues.)
- **Password hashing**: `bcrypt` used directly (cost factor 12), not via `passlib`, due to known passlib/bcrypt compatibility issues.
- **Rate limiting**: in-memory `SlidingWindowRateLimiter` (already existed in `server/game/rate_limiter.py`), not Redis. Fine for a single-instance deployment; would need to move to Redis before horizontally scaling the server.
- **OAuth2 provider "enabled" flag**: a provider is considered enabled purely by having its client_id (and, for Azure/Cognito, tenant/domain) env vars set — there is no separate `AUTH_ENABLE_OAUTH2`/per-provider `enabled: true` flag as shown in the doc's YAML example, since supplying real credentials already is the opt-in and avoids a second setting that could drift out of sync.
- **PKCE state ownership**: `state` and `code_verifier` are generated and stored by the frontend across the redirect (matching §7.1.6/§7.1.7's request shapes); the backend's authorize/callback routes are a stateless relay and keep no server-side copy of either value.
- **Socket.IO auth (§16)**: implemented as an **opt-in** capability gated by `AUTH_REQUIRE_SOCKET_AUTH` (default `false`), rather than always-on, to avoid breaking the current anonymous play experience. `server.main.authenticate_socket_connection()` validates the JWT passed in the client's `auth: { token }` option and attaches `{user_id, role}` to the Socket.IO session when enabled; when disabled (the default) it is a no-op and the connect handler behaves exactly as before.
- **CORS**: no `CORSMiddleware` was added to the FastAPI app — the existing `ALLOWED_ORIGINS` config only governs Socket.IO. Since the SPA and API are served from the same FastAPI origin, no CORS headers are required for same-origin requests; a split frontend/backend deployment would need to add `CORSMiddleware` explicitly.
- **Role vs. `is_admin`**: the `users.role` enum includes `'admin'` and there is a separate `is_admin` boolean column. `require_role("admin")` grants access if *either* is true, so this redundancy doesn't create a privilege-check bypass, but it is worth collapsing into a single source of truth in a later cleanup.
- **JWT key management (§17.4 rotation)**: not implemented, since only one HS256 secret is used in this deployment model; no `kid`-based key rotation exists for this app's own tokens.
- **Bulk import row/file-size caps**: `MAX_BULK_IMPORT_ROWS` (1000) and a 2MB upload cap are enforced but not specified in the design doc — defense-in-depth against an oversized synchronous import on an admin-only endpoint.
- **OAuth2 callback route shape**: the design doc's frontend route map (§19.1) shows `/auth/callback/:provider` as a client-side-router path segment; this app has no client-side router (it's a plain multi-page Vite build), so the default `redirect_uri` instead points at a real static file, `/auth-callback.html?provider={provider}`, with the provider read from the query string. Still overridable per-provider via `AZURE_REDIRECT_URI`/etc. if a deployment wants a different shape.
- **Password history semantics**: `AUTH_PASSWORD_HISTORY_COUNT` (default 5) counts the *live* password as one of the N — i.e. with the default, a user cycles through 4 distinct retired passwords before a 5th change can reuse the very first one. A history-reuse rejection during `confirm_password_reset` does consume the (single-use) reset token, unlike a plain weak-password-format rejection, which intentionally leaves the token usable for a retry — reusing a password requires DB access to check, so the token must already be consumed to know which user's history to check.
- **§18.2 CLI script scope**: `python -m server.scripts.create_admin` creates the account with the operator-supplied password directly (`requires_password_change=False`), unlike admin-created users via the HTTP API (`admin_create_user`), which always get a random temporary password and are forced to change it — the CLI operator is assumed to already be choosing a real, considered password interactively.
- **Bug fixed this pass — `EMAIL_NOT_VERIFIED` never actually enforced**: the doc's own error table (§7.1.x) lists `EMAIL_NOT_VERIFIED` (403), but no code path ever raised it — `AUTH_REQUIRE_EMAIL_VERIFICATION=true` only controlled whether a verification email was *sent* at registration, not whether an unverified account could actually log in and use the app. `AuthService.login()` now raises a new `EmailNotVerifiedError` → 403 `EMAIL_NOT_VERIFIED` for a local account with `email_verified=False` when the setting is on. The check runs *after* password verification (like the existing lockout/disabled-account checks), so it can't be used to enumerate unverified accounts by email address alone. Admin-created accounts and OAuth2-provisioned accounts are both unaffected, since both already set `email_verified=True` unconditionally at creation time.
- **Bug fixed this pass — `PROVIDER_UNAVAILABLE` never actually enforced**: same class of gap as above, one row down in the same error table. Any network-level failure reaching an OAuth2/OIDC provider (token endpoint, JWKS endpoint, or GitHub's REST profile endpoints) was being folded into the same generic `OAuth2Error` as an actively-rejected/invalid code or token, and reported to the client as 401 `INVALID_CREDENTIALS` — actively misleading, since it implies the *user's* authorization code or token was the problem when the real cause was the provider being transiently unreachable (nothing the user can fix by re-entering credentials). Worse, GitHub's profile-fetch calls had no network-error handling at all, so a connection failure there would have propagated as a raw, unhandled `httpx` exception rather than any typed auth error. Fixed with a new `OAuth2ProviderUnavailableError` (subclass of `OAuth2Error`) and a new `JwksUnavailableError` (subclass of `IdTokenVerificationError`) raised specifically for network/timeout/non-2xx-transport failures at the token, JWKS, and GitHub profile endpoints; `oauth2_routes.py` now maps it to 503 `PROVIDER_UNAVAILABLE` (checked before the generic 401 case, since it's a subclass).
- **Consistency fix this pass — `now_ms` threading**: `change_password`, `confirm_password_reset`, and `admin_reset_password`'s HTTP route callers were updated to explicitly pass `now_ms=time.time() * 1000`, matching every other route call into `AuthService` (`register`, `login`, `refresh`, `logout`, `request_password_reset`, `request_email_verification` all already did this) — these three had briefly relied on an internal service-layer default instead, introduced in the same pass that added the `password_changed_at`/`set_password(now_ms)` plumbing for password expiration. The optional default is kept on the service methods themselves since several existing unit tests call them without a clock argument.
- **Config source of truth is `.env`, not a checked-in config file**: `server/config.py` and `server/auth/config.py` build their settings entirely from environment variables at import time — there was never a YAML/JSON config file to edit, unlike the illustrative `yaml:` blocks in §4.3/§4.4 above (those were always just documentation of the *shape* of the settings, not a literal file this codebase reads). `.env.example` (repo root, committed) now documents every single environment variable the server reads, grouped by feature area; `python -m server.main` loads a real `.env` (gitignored, never committed) via `python-dotenv` with `override=False`, so real environment variables set by `docker-compose.yml` or a hosting platform always win over `.env`. **Bug fixed while building `.env.example`**: `server/auth/config.py`'s `_int_env`/`_optional_int_env` helpers crashed with `ValueError: invalid literal for int() with base 10: ''` on a *blank* env var (e.g. `AUTH_PASSWORD_EXPIRY_DAYS=` with nothing after the `=`) — which is the conventional way a `.env` file represents "this key exists for discoverability but isn't set", as opposed to omitting the line entirely. Both helpers now treat a blank string exactly like an absent variable.
- **Single-command local dev bootstrap (`run.sh` / `run.bat`)**: neither script is part of the design doc's original scope, but both directly serve §12's "Initial Deployment" migration story for a *local* dev environment — running one command installs Node + Python dependencies (if missing) and starts Postgres + backend + frontend together (same three processes as `npm run dev`). Each also calls `scripts/generate_env.py` on first run, which copies `.env.example` to `.env` and fills in a freshly generated random `JWT_SECRET_KEY` plus `AUTH_ENABLE_LOCAL_REGISTRATION=true` — so a completely fresh checkout works immediately without hand-editing anything, while `.env.example` itself stays a safe, secret-free template. `package.json`'s `dev:server`/`start` scripts were also made cross-platform (`python3 -m server.main || python -m server.main`) since Windows typically has no `python3` command at all, only `python`.
- **Guest/anonymous-access toggle is a client-side gate, not a hard security boundary**: `AUTH_ALLOW_GUEST_ACCESS=false` hides the login page's guest link and redirects an anonymous visitor away from the main game's creator screen, but this happens *after* a network round-trip on page load (checking `GET /api/auth/providers` and attempting session restoration in parallel), so a visitor may briefly see the creator screen flash before being redirected, and a determined client could still call the game's APIs directly. The actual backend-enforced boundary for real-time gameplay is the separate, pre-existing `AUTH_REQUIRE_SOCKET_AUTH` flag (design doc §16), which rejects a Socket.IO connection outright without a valid JWT; a deployment that wants guest access to be genuinely unreachable, not just hidden from the UI, should enable both flags together.

### Notes on Phase 4/5 testing without live providers
All OAuth2/OIDC code paths (PKCE URL construction, authorization-code exchange, id_token signature verification, GitHub REST profile fetch, account linking/auto-provisioning, email-verification-claim enforcement) are exercised by tests that build a real RSA keypair and a matching JWKS document locally, and replay scripted `httpx` responses instead of calling a real identity provider. This gives genuine confidence in the *logic* (including negative cases: wrong signing key, expired token, wrong audience/issuer, unknown `kid`, `alg=none` forgery, unverified provider email), but it has **not** been validated against a real Azure AD tenant, Google Cloud OAuth client, GitHub OAuth App, or Cognito user pool (it *has*, however, been validated against a real Postgres database — see above). Before enabling any of these in production, an operator should perform one real end-to-end login against each enabled provider.

### Metrics to Track
- **Code Coverage**: Target > 85% for auth module
- **Test Pass Rate**: Target 100%
- **Security Issues**: Target 0 critical/high
- **Performance**: Login endpoint < 500ms, token refresh < 200ms
- **Uptime**: Target 99.9% during testing

---

## 10. Security Considerations

### 10.1 Passwords
- ✅ Hash with bcrypt (cost 12+)
- ✅ Never log passwords
- ✅ Enforce complexity requirements
- ✅ Support password expiration (optional)
- ✅ Password reset via email token (short-lived)

### 10.2 Tokens (JWT)
- ✅ Short-lived access tokens (30 mins)
- ✅ Longer-lived refresh tokens (7 days)
- ✅ Rotate refresh tokens (optional)
- ✅ Store tokens in httpOnly cookies (backend sets)
- ✅ Validate signature and expiration server-side
- ✅ Include user ID and role in token claims

### 10.3 OAuth2 Security
- ✅ Use PKCE (Proof Key for Code Exchange)
- ✅ Validate state parameter (CSRF prevention)
- ✅ Verify ID token signature
- ✅ Validate ID token claims (aud, iss, iat, exp)
- ✅ Use HTTPS for all OAuth2 flows
- ✅ Keep client secret secure (never expose to frontend)

### 10.4 Rate Limiting
- ✅ Registration: 10 per hour per IP
- ✅ Login: 100 per hour per IP
- ✅ Failed login lockout: 5 attempts → 15 min lock
- ✅ Use Redis for distributed rate limiting

### 10.5 Session Management
- ✅ Revoke sessions on password change
- ✅ Revoke all sessions on logout
- ✅ Track device/IP for session
- ✅ Detect and flag suspicious sessions (new location, etc.)

### 10.6 Audit & Monitoring
- ✅ Log all auth events
- ✅ Alert on multiple failed logins
- ✅ Alert on suspicious patterns (new device, bulk user creation)
- ✅ Retention: Keep audit logs for 90 days minimum

### 10.7 Data Privacy
- ✅ Encrypt sensitive data at rest (passwords, tokens)
- ✅ Use HTTPS for all API communication
- ✅ Implement GDPR deletion (soft delete users)
- ✅ Provide data export for users (future phase)

---

## 11. Configuration Examples

### 11.1 Development Environment
```bash
# .env.development
AUTH_ENABLE_LOCAL_REGISTRATION=true
AUTH_ENABLE_LOCAL_LOGIN=true
AUTH_ADMIN_ONLY_REGISTRATION=false
AUTH_REQUIRE_EMAIL_VERIFICATION=false
AUTH_ENABLE_OAUTH2=false
AUTH_PASSWORD_MIN_LENGTH=6
AUTH_ACCESS_TOKEN_EXPIRE_MINUTES=30
REQUIRE_HTTPS=false
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000
SMTP_SERVER=localhost
SMTP_PORT=1025
```

### 11.2 Education Instance (Admin-Only Registration)
```bash
# .env.production-education
AUTH_ENABLE_LOCAL_REGISTRATION=false
AUTH_ENABLE_LOCAL_LOGIN=true
AUTH_ADMIN_ONLY_REGISTRATION=true
AUTH_REQUIRE_EMAIL_VERIFICATION=true
AUTH_ENABLE_OAUTH2=false
AUTH_PASSWORD_MIN_LENGTH=8
AUTH_PASSWORD_REQUIRE_SPECIAL=true
AUTH_ACCESS_TOKEN_EXPIRE_MINUTES=60
REQUIRE_HTTPS=true
CORS_ALLOWED_ORIGINS=https://education.example.com
SMTP_SERVER=smtp.sendgrid.net
```

### 11.3 Enterprise Instance (Azure Entra ID)
```bash
# .env.production-enterprise
AUTH_ENABLE_LOCAL_REGISTRATION=false
AUTH_ENABLE_LOCAL_LOGIN=false
AUTH_ADMIN_ONLY_REGISTRATION=false
AUTH_ENABLE_OAUTH2=true
AZURE_CLIENT_ID=xxxxx
AZURE_CLIENT_SECRET=xxxxx
AZURE_TENANT_ID=xxxxx
AZURE_REDIRECT_URI=https://app.company.com/auth/callback/azure
AUTH_ACCESS_TOKEN_EXPIRE_MINUTES=120
AUTH_REFRESH_TOKEN_EXPIRE_DAYS=30
REQUIRE_HTTPS=true
CORS_ALLOWED_ORIGINS=https://app.company.com
```

### 11.4 Community Instance (Multiple OAuth2 + Local Registration)
```bash
# .env.production-community
AUTH_ENABLE_LOCAL_REGISTRATION=true
AUTH_ENABLE_LOCAL_LOGIN=true
AUTH_ADMIN_ONLY_REGISTRATION=false
AUTH_REQUIRE_EMAIL_VERIFICATION=true
AUTH_ENABLE_OAUTH2=true
# Google OAuth2
GOOGLE_CLIENT_ID=xxxxx
GOOGLE_CLIENT_SECRET=xxxxx
GOOGLE_REDIRECT_URI=https://community.example.com/auth/callback/google
# GitHub OAuth2
GITHUB_CLIENT_ID=xxxxx
GITHUB_CLIENT_SECRET=xxxxx
GITHUB_REDIRECT_URI=https://community.example.com/auth/callback/github
```

---

## 12. Migration Strategy

### 12.1 Initial Deployment
1. Deploy with local authentication only (Phase 1-2)
2. Create initial admin account via SQL script
3. Admin creates additional accounts (in admin-only mode)
4. Users log in and create avatars
5. Monitor and gather feedback

### 12.2 Enable Email Verification (Phase 3)
1. Migrate database (add email_verified, email_verified_at columns)
2. Set all existing users as verified (email_verified = true)
3. Enable verification for new registrations
4. No impact on existing users

### 12.3 Add OAuth2 Integration (Phase 4+)
1. Deploy Azure Entra ID support
2. Add "Sign in with Microsoft" button alongside local login
3. Existing users continue with local login
4. New users can choose either method
5. Eventually: Allow linking multiple auth methods to same account (future)

### 12.4 Gradual OAuth2 Rollout
1. Soft launch: OAuth2 optional, local auth always available
2. Monitor provider health and token exchange success rates
3. Gradually increase promotion of OAuth2 login
4. Eventually: Make OAuth2 primary, local auth secondary

---

## 13. Acceptance Criteria

*Checkboxes below reflect actual verified status as of this pass (see §9
Progress Dashboard for the authoritative, detailed per-phase breakdown and
caveats — this section is a compact rollup of the same information).*

### All Phases
- [x] All unit tests pass (coverage > 85%) — 1583 Python + 746 JS passing; measured `server/auth` coverage is **94%** (`pytest --cov=server.auth`).
- [x] All integration tests pass — includes `fastapi.testclient.TestClient`-based HTTP wiring tests per router, not just direct function calls.
- [x] Database migrations run without errors — no formal migration tool (Alembic etc.); `server/db/schema.sql` uses idempotent `CREATE TABLE/INDEX IF NOT EXISTS` and has been re-applied to a real Postgres container multiple times this project with no errors.
- [ ] API documentation complete (OpenAPI/Swagger) — FastAPI's automatic `/docs` exists by default, but no one has curated descriptions/examples beyond what Pydantic models produce automatically.
- [ ] Configuration guide for admins complete — env vars are documented inline in this doc (§5.2, §11) but there's no separate standalone admin/deployment guide.
- [ ] No security vulnerabilities (per OWASP) — no external pentest performed (deliberately deferred, see §8 Phase 8 notes); can't be checked off on self-review alone.
- [ ] Performance benchmarks met (login < 500ms) — never measured under load.

### Phase 1
- [x] Users can register with email/password
- [x] Users can log in with credentials
- [x] Access token grants access to protected endpoints
- [x] Refresh token works and issues new access token
- [x] Users can log out and token is revoked

### Phase 2
- [x] Admin can create users
- [x] Created users can log in
- [x] Created users forced to change password on first login
- [x] Admin can list, view, update, delete users
- [x] All admin actions logged in audit log

### Phase 3
- [x] Email verification works end-to-end — including `login()` now actually rejecting an unverified account with 403 `EMAIL_NOT_VERIFIED` when `AUTH_REQUIRE_EMAIL_VERIFICATION=true` (fixed this pass — previously the setting only gated whether the email was sent, not login itself).
- [x] Password reset works end-to-end
- [x] Tokens expire correctly
- [ ] Email templates are professional and clear — functional plain-text templates only (`server/auth/email.py`); no HTML styling/branding pass has been done.

### Phase 4
*Azure code path is complete and unit-tested against a locally-generated RSA keypair + scripted JWKS/httpx transport, but has never been exercised against a real Azure Entra ID tenant — treat the four boxes below as "code-level verified", not "verified live".*
- [x] Azure Entra ID login flow works
- [x] User is auto-provisioned on first Entra ID login
- [x] Profile synced from Entra ID
- [x] Logout revokes access

### Phase 5
*Same live-provider caveat as Phase 4 — Google/GitHub/Cognito paths are code-complete and tested against scripted transports, not real provider credentials.*
- [x] All OAuth2 providers work independently
- [x] Configuration supports multiple providers
- [x] Frontend shows available providers
- [x] Provider-specific profiles synced correctly

### Phase 6
- [x] Users can view and edit their profile
- [x] Users can see active sessions
- [x] Users can revoke sessions
- [x] Users can change password

### Phase 7
- [x] Rate limiting blocks after threshold
- [x] Failed login lockout works
- [x] Password complexity enforced
- [ ] No CSRF vulnerabilities — N/A rather than failed: this is a bearer-token API with no cookie-based sessions, so classic CSRF doesn't apply to it today (see Deliberate Deviations); this box is left unchecked because that's an architectural non-applicability judgment, not a verified test result, and would need re-examining if cookie-based auth were ever introduced.

### Phase 8
- [ ] Full e2e flow works (register → login → room → profile) — a player can now register, log in, see their signed-in state persist and show in the HUD (sign-out control, restored on page reload via a stored refresh token), and join a room — but there's no in-game profile page, and no room/game action is actually gated by the logged-in identity yet (rooms work identically for a logged-in and an anonymous player today). See §19 Frontend implementation notes.
- [ ] All security tests pass — this repo's own auth test suite passes, but no external/professional security testing has been performed (see the OWASP box above).
- [ ] Performance under load acceptable — not load-tested.
- [ ] Documentation complete and reviewed — this design doc is kept up to date, but there's no separate user-facing or API reference documentation.

---

## 14. Future Enhancements (Not in MVP)

1. **Multi-Factor Authentication (MFA)**
   - SMS/TOTP-based 2FA
   - WebAuthn/FIDO2 support

2. **Social Login Linking**
   - Link multiple auth methods to same account
   - Account merge for existing users

3. **Advanced RBAC**
   - Custom roles and permissions
   - Granular resource-level permissions

4. **Audit & Compliance**
   - GDPR data export
   - SOC2 compliance features
   - PII encryption at rest

5. **Admin Features**
   - User groups/teams
   - Bulk actions and exports
   - Single Sign-Out (SLO)
   - SAML support

6. **Identity Verification**
   - Email/phone verification
   - Social profile verification
   - User federation/delegation

---

## 15. Success Metrics

### Adoption
- Authentication method distribution (local vs OAuth2)
- User registration rate and completion rate
- Time-to-first-room (minutes from registration)

### Reliability
- Auth endpoint availability (target 99.9%)
- Token validation latency (p95 < 50ms)
- OAuth2 provider availability
- Session refresh success rate

### Security
- Failed login rate
- Account lockout incidents
- Audit log entries per day
- Suspicious login alerts
- Zero security breaches

### User Satisfaction
- Password reset success rate
- Support tickets related to auth
- User survey on auth experience
- Time spent on login/registration page

---

## 16. Socket.IO Authentication

The game loop uses Socket.IO for real-time communication. Auth tokens must be validated on every socket connection and refreshed transparently.

### 16.1 Connection Handshake

The frontend passes the access token in the Socket.IO `auth` option at connect time:

```javascript
// client/js/main.js
import { io } from 'socket.io-client';

const socket = io({
  auth: { token: getAccessToken() },
  reconnectionAttempts: 5,
});

socket.on('connect_error', (err) => {
  if (err.message === 'TOKEN_EXPIRED') {
    refreshTokenAndReconnect();
  } else if (err.message === 'TOKEN_INVALID') {
    redirectToLogin();
  }
});
```

### 16.2 Server-Side Socket Auth Middleware

The FastAPI/python-socketio backend validates the token on every connection using a Socket.IO middleware:

```python
# server/game/socket_auth.py
async def authenticate_socket(sid, environ, auth):
    """
    Socket.IO connection middleware.
    Raises ConnectionRefusedError if token is missing or invalid.
    """
    if not auth or 'token' not in auth:
        raise ConnectionRefusedError('TOKEN_MISSING')

    user = validate_access_token(auth['token'])
    if user is None:
        raise ConnectionRefusedError('TOKEN_INVALID')
    if is_token_expired(auth['token']):
        raise ConnectionRefusedError('TOKEN_EXPIRED')
    if not user.is_active:
        raise ConnectionRefusedError('ACCOUNT_DISABLED')

    # Attach user to socket session
    await sio.save_session(sid, {'user_id': str(user.id), 'role': user.role})
```

Register this as the Socket.IO `connect` event handler in `server/main.py`.

### 16.3 Per-Event Authorization

Sensitive socket events (e.g., room creation, admin commands) check the role stored in the socket session:

```python
@sio.event
async def create_room(sid, data):
    session = await sio.get_session(sid)
    if session['role'] not in ('educator', 'admin'):
        return {'error': 'FORBIDDEN'}
    # ... room creation logic
```

### 16.4 Token Expiry During an Active Session

When the access token expires mid-session:

1. The server continues to serve existing socket requests until the next connection attempt (tokens are only checked on `connect`).
2. The frontend proactively refreshes the token using the refresh token before expiry (5 minutes before `expires_in`).
3. After a successful refresh, the frontend reconnects the socket with the new token.
4. If the refresh also fails (refresh token expired), the frontend redirects to the login screen.

**Frontend refresh logic**:
```javascript
// Refresh token 5 minutes before access token expiry
const ACCESS_TOKEN_BUFFER_MS = 5 * 60 * 1000;

function scheduleTokenRefresh(expiresInSeconds) {
  const refreshInMs = (expiresInSeconds * 1000) - ACCESS_TOKEN_BUFFER_MS;
  setTimeout(() => refreshTokenAndReconnect(), Math.max(refreshInMs, 0));
}
```

### 16.5 Admin Socket Commands

Admin users can send privileged socket commands (e.g., kick user, broadcast message). These are validated against `session['role'] === 'admin'` in the event handler.

---

## 17. JWT Key Management

### 17.1 Algorithm

Use **RS256** (RSA + SHA-256) for production deployments:
- Private key signs tokens (server only)
- Public key verifies tokens (can be shared with downstream services)
- Supports key rotation without forcing all users to log out

Use **HS256** (HMAC + SHA-256) only for development/single-instance setups.

### 17.2 Key Storage

| Environment | Storage method |
|-------------|----------------|
| Development | `JWT_SECRET_KEY` env var (HS256) |
| Staging | Secret injected via Docker secrets or `.env` file |
| Production | AWS Secrets Manager, Azure Key Vault, or HashiCorp Vault — loaded at startup |

**Never** commit the private key to source control.

**Required env vars**:
```bash
# HS256 (dev only)
JWT_SECRET_KEY=a-very-long-random-secret-at-least-32-chars

# RS256 (production)
JWT_PRIVATE_KEY_PATH=/run/secrets/jwt_private.pem
JWT_PUBLIC_KEY_PATH=/run/secrets/jwt_public.pem
```

### 17.3 Token Claims

Minimum required claims in every access token:

```json
{
  "sub": "user-uuid",
  "email": "user@example.com",
  "role": "learner",
  "session_id": "session-uuid",
  "iat": 1724500000,
  "exp": 1724501800,
  "iss": "hobboverse"
}
```

- `sub`: User UUID. Immutable identifier.
- `role`: Current role at time of issuance.
- `session_id`: Links to `user_sessions` table for revocation checks.
- `iss`: Server identifier; reject tokens from unexpected issuers.

### 17.4 Key Rotation Strategy

1. Generate new key pair.
2. Deploy with both old and new public keys accepted for verification.
3. Issue all new tokens with the new private key (add `kid` header claim to identify key).
4. After all existing tokens expire (max `access_token_expire_minutes`), remove old public key.
5. Zero-downtime rotation — no forced logouts.

---

## 18. Initial Admin Bootstrapping

On a fresh deployment there are no admin accounts. The system must support creating the first admin securely.

### 18.1 Environment-Variable Bootstrap (Recommended)

Set these env vars before first startup:

```bash
INITIAL_ADMIN_EMAIL=admin@example.com
INITIAL_ADMIN_PASSWORD=ChangeMe!OnFirstLogin123
INITIAL_ADMIN_DISPLAY_NAME=System Administrator
```

On startup, `server/main.py` checks if no users exist. If the table is empty and `INITIAL_ADMIN_EMAIL` is set, it creates the admin account with `is_admin=true` and `password_change_required=true`.

After the first admin logs in and changes their password, the bootstrap env vars are no longer used.

### 18.2 CLI Bootstrap Script

An alternative for operators who do not want to put the password in env vars:

```bash
python -m server.scripts.create_admin \
  --email admin@example.com \
  --display-name "System Administrator"
```

This prompts securely for a password (no echo) and creates the admin account.

### 18.3 Docker Compose Setup

```yaml
# docker-compose.yml (initial setup only — remove vars after first login)
services:
  server:
    environment:
      - INITIAL_ADMIN_EMAIL=${INITIAL_ADMIN_EMAIL}
      - INITIAL_ADMIN_PASSWORD=${INITIAL_ADMIN_PASSWORD}
```

---

## 19. Frontend UI/UX Design (Material 3 Web)

All authentication screens are implemented with **Material Design 3 Web Components** (`@material/web`). This ensures visual consistency with the rest of the Hobboverse UI.

### 19.1 Frontend Route Map

| Route | Page | Auth Required |
|-------|------|---------------|
| `/login` | Login screen | No |
| `/register` | Registration form | No (only if open registration enabled) |
| `/verify-email` | Email verification landing | No |
| `/reset-password` | Password reset form | No |
| `/forgot-password` | Request password reset | No |
| `/profile` | User profile & settings | Yes |
| `/admin` | Admin dashboard | Yes (admin) |
| `/admin/users` | User management table | Yes (admin) |
| `/admin/users/:id` | Single user detail | Yes (admin) |
| `/admin/audit` | Audit log viewer | Yes (admin) |
| `/auth/callback/:provider` | OAuth2 redirect handler | No |

The existing `/` (lobby) and room routes require authentication. If an unauthenticated user reaches a protected route, they are redirected to `/login?redirect=<original_path>` and sent back after login.

### 19.2 Material 3 Component Mapping

| Auth UI Element | M3 Component |
|-----------------|-------------|
| Email/username input | `<md-outlined-text-field type="email">` |
| Password input | `<md-outlined-text-field type="password">` |
| Login / Register button | `<md-filled-button>` |
| OAuth2 provider button | `<md-outlined-button>` with provider icon |
| "Forgot password?" link | `<md-text-button>` |
| Error snackbar | `<md-snackbar>` |
| Loading state | `<md-circular-progress>` |
| Admin user table | `<md-data-table>` |
| Role badge | `<md-chip>` |
| Confirm dialog (delete user) | `<md-dialog>` with `<md-filled-button>` and `<md-text-button>` |
| Admin top navigation | `<md-top-app-bar>` |
| Admin side navigation | `<md-navigation-drawer>` |

### 19.3 Login Screen Layout

```
┌─────────────────────────────────────────┐
│         [Hobboverse Logo / Title]       │
│                                         │
│   ┌─────────────────────────────────┐   │
│   │  Email or username              │   │  md-outlined-text-field
│   └─────────────────────────────────┘   │
│   ┌─────────────────────────────────┐   │
│   │  Password                    👁 │   │  md-outlined-text-field (password)
│   └─────────────────────────────────┘   │
│                          Forgot password?│  md-text-button
│   ┌─────────────────────────────────┐   │
│   │           Sign In               │   │  md-filled-button
│   └─────────────────────────────────┘   │
│                                         │
│   ─────────── or ───────────────────   │  (shown if OAuth2 enabled)
│                                         │
│   ┌─────────────────────────────────┐   │
│   │  🪟  Sign in with Microsoft     │   │  md-outlined-button (per provider)
│   └─────────────────────────────────┘   │
│                                         │
│   Don't have an account? Register       │  (shown if open registration enabled)
└─────────────────────────────────────────┘
```

### 19.4 Registration Screen Layout

```
┌─────────────────────────────────────────┐
│         Create Your Account             │
│                                         │
│   ┌─────────────────────────────────┐   │
│   │  Display Name                   │   │
│   └─────────────────────────────────┘   │
│   ┌─────────────────────────────────┐   │
│   │  Email                          │   │
│   └─────────────────────────────────┘   │
│   ┌─────────────────────────────────┐   │
│   │  Password                    👁 │   │
│   └─────────────────────────────────┘   │
│   ┌─────────────────────────────────┐   │
│   │  Confirm Password            👁 │   │
│   └─────────────────────────────────┘   │
│   [x] I agree to the Terms of Service   │  md-checkbox
│                                         │
│   ┌─────────────────────────────────┐   │
│   │         Create Account          │   │  md-filled-button
│   └─────────────────────────────────┘   │
│                                         │
│   Already have an account? Sign in      │
└─────────────────────────────────────────┘
```

### 19.5 UX States

**Loading**: Show `md-circular-progress` inside the submit button; disable all inputs.

**Error**: Show `md-snackbar` with the human-readable `message` from the error envelope. For `VALIDATION_ERROR`, highlight the offending `md-outlined-text-field` with `error` and `error-text` attributes.

**First-Login Password Change**: After login, if `requires_password_change: true` is returned from `/api/auth/me`, redirect to a dedicated `/change-password` page before allowing access to any other route.

**Email Verification Pending**: After registration, show a full-page info card telling the user to check their email. Include a "Resend verification email" `md-text-button` that calls `POST /api/auth/resend-verification`.

**OAuth2 Callback**: The `/auth/callback/:provider` route handles the redirect from the provider. It extracts `code` and `state` from query params, calls `POST /api/auth/oauth2/callback/{provider}`, stores the received tokens, and redirects to `/?redirect` or `/` if the user is new (to avatar creation).

### 19.6 Token Storage

| Token | Storage location | Rationale |
|-------|-----------------|-----------|
| Access token | In-memory JS variable (`authState.accessToken`) | Never written to disk; lost on tab close |
| Refresh token | `sessionStorage` | Survives page refresh within the same tab; cleared on tab close |

Do **not** store tokens in `localStorage` — XSS can exfiltrate them.

The `socket.io` connection reads the in-memory access token directly from `authState`.

---

## 20. Python Dependencies

The following packages must be added to `requirements.txt` when implementing this feature:

```text
# Authentication & JWT
python-jose[cryptography]==3.3.0   # JWT generation and validation (RS256 / HS256)
passlib[bcrypt]==1.7.4              # Password hashing with bcrypt

# OAuth2 / HTTP client (for token exchange with providers)
httpx==0.27.0                       # Async HTTP client for OAuth2 token exchange
authlib==1.3.1                      # OAuth2 provider integration helpers

# Rate limiting
slowapi==0.1.9                      # Rate limiting for FastAPI (Starlette-based)
# Optional: use redis backend for distributed rate limiting
redis==5.0.6                        # Redis client (if RATE_LIMIT_BACKEND=redis)

# Email
aiosmtplib==3.0.1                   # Async SMTP client for sending emails
jinja2==3.1.4                       # Email template rendering (already a FastAPI dep)

# Password validation
zxcvbn==4.4.28                      # Password strength estimation (optional)

# CSV processing (bulk import)
# csv is part of stdlib — no additional package needed
```

---

## 21. References & Standards

- **OAuth2**: RFC 6749 - Authorization Framework
- **PKCE**: RFC 7636 - Proof Key for Public Clients
- **JWT**: RFC 7519 - JSON Web Tokens
- **OWASP**: Top 10 Security Risks
- **NIST**: SP 800-63B Digital Identity Guidelines (password and authenticator guidance)
- **GDPR**: General Data Protection Regulation
- **Material Design 3**: https://m3.material.io — component guidelines for all auth UI
- **Material Web**: https://github.com/material-components/material-web — `@material/web` package reference

---

**Document Version**: 1.1  
**Last Updated**: 2026-08-24  
**Changelog**:
- v1.1: Added Socket.IO auth (§16), JWT key management (§17), initial admin bootstrapping (§18), frontend UI/UX with Material 3 Web (§19), Python dependencies (§20); filled missing API endpoints (`/auth/me`, `/auth/providers`, `/auth/resend-verification`, admin enable/unlock/bulk-import); added standard error envelope (§7.1.x); clarified oauth2_identities table vs users table columns; fixed progress dashboard placeholder.
- v1.0: Initial design  
**Next Review**: Upon completion of Phase 1
