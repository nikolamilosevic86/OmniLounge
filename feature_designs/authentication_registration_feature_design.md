# User Authentication and Registration Feature Design

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

### Sample Progress Dashboard (to be filled in as development proceeds)

| Phase | Status | Tasks | Tests | Coverage | Bugs | Next |
|-------|--------|-------|-------|----------|------|------|
| 1: Local Auth | Not Started | 0/6 | 0/70 | 0% | 0 | Migrations |
| 2: Admin Reg | Not Started | 0/6 | 0/41 | 0% | 0 | - |
| 3: Email | Not Started | 0/5 | 0/33 | 0% | 0 | - |
| 4: Azure | Not Started | 0/6 | 0/45 | 0% | 0 | - |
| 5: Multi-OAuth | Not Started | 0/6 | 0/48 | 0% | 0 | - |
| 6: Profiles | Not Started | 0/5 | 0/36 | 0% | 0 | - |
| 7: Security | Not Started | 0/5 | 0/38 | 0% | 0 | - |
| 8: Docs | Not Started | 0/5 | 0/70 | 0% | 0 | - |

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

### All Phases
- [ ] All unit tests pass (coverage > 85%)
- [ ] All integration tests pass
- [ ] Database migrations run without errors
- [ ] API documentation complete (OpenAPI/Swagger)
- [ ] Configuration guide for admins complete
- [ ] No security vulnerabilities (per OWASP)
- [ ] Performance benchmarks met (login < 500ms)

### Phase 1
- [ ] Users can register with email/password
- [ ] Users can log in with credentials
- [ ] Access token grants access to protected endpoints
- [ ] Refresh token works and issues new access token
- [ ] Users can log out and token is revoked

### Phase 2
- [ ] Admin can create users
- [ ] Created users can log in
- [ ] Created users forced to change password on first login
- [ ] Admin can list, view, update, delete users
- [ ] All admin actions logged in audit log

### Phase 3
- [ ] Email verification works end-to-end
- [ ] Password reset works end-to-end
- [ ] Tokens expire correctly
- [ ] Email templates are professional and clear

### Phase 4
- [ ] Azure Entra ID login flow works
- [ ] User is auto-provisioned on first Entra ID login
- [ ] Profile synced from Entra ID
- [ ] Logout revokes access

### Phase 5
- [ ] All OAuth2 providers work independently
- [ ] Configuration supports multiple providers
- [ ] Frontend shows available providers
- [ ] Provider-specific profiles synced correctly

### Phase 6
- [ ] Users can view and edit their profile
- [ ] Users can see active sessions
- [ ] Users can revoke sessions
- [ ] Users can change password

### Phase 7
- [ ] Rate limiting blocks after threshold
- [ ] Failed login lockout works
- [ ] Password complexity enforced
- [ ] No CSRF vulnerabilities

### Phase 8
- [ ] Full e2e flow works (register → login → room → profile)
- [ ] All security tests pass
- [ ] Performance under load acceptable
- [ ] Documentation complete and reviewed

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
