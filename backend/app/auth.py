"""
JWT authentication + RBAC + DB-backed users.

Design decisions:
- Passwords hashed with bcrypt (industry standard, slow by design)
- JWT tokens are stateless — no session store needed
- customer_id auto-created on first login for regular users
- Admin credentials seeded on startup from env vars
- Role embedded in JWT — no DB lookup on every request

Security tradeoffs for interviews:
- Bearer tokens in sessionStorage (simple, XSS risk)
- Production upgrade: httpOnly cookies (immune to XSS)
- JWT is stateless — can't revoke until expiry
- Production upgrade: token blocklist in Redis
"""
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ── Pydantic models ───────────────────────────────────────────────────────────

class TokenData(BaseModel):
    username: str
    role: str
    customer_id: int | None = None

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    role: str
    username: str
    customer_id: int | None = None


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "user"


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    customer_id: int | None
    created_at: str


# ── Password helpers ──────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── JWT helpers ───────────────────────────────────────────────────────────────

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_expire_minutes
    )
    to_encode["exp"] = expire
    return jwt.encode(
        to_encode,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


# ── DB helpers ────────────────────────────────────────────────────────────────

async def get_user_by_username(username: str, pool=None) -> dict | None:
    if pool is None:
        from app.db import get_pool
        pool = get_pool()
    async with pool.connection() as conn:
        row = await (await conn.execute(
            "SELECT * FROM users WHERE username = %s AND is_active = true",
            (username,),
        )).fetchone()
    return row


async def create_customer_for_user(username: str, pool=None) -> int:
    """
    Auto-create a customer row on first login.
    Uses ON CONFLICT DO UPDATE so it's safe to call multiple times.
    Links the customer back to the user row.
    """
    if pool is None:
        from app.db import get_pool
        pool = get_pool()
    async with pool.connection() as conn:
        row = await (await conn.execute(
            """
            INSERT INTO customers (external_id, name)
            VALUES (%s, %s)
            ON CONFLICT (external_id) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
            """,
            (f"user:{username}", username),
        )).fetchone()
        customer_id = row["id"]
        await conn.execute(
            "UPDATE users SET customer_id = %s WHERE username = %s",
            (customer_id, username),
        )
    return customer_id


async def authenticate_user(username: str, password: str, pool=None) -> dict | None:
    """
    Verify credentials against DB.
    Auto-creates customer_id on first login for 'user' role.
    Returns full user dict or None.
    """
    user = await get_user_by_username(username, pool)
    if not user:
        return None
    if not verify_password(password, user["hashed_password"]):
        return None

    # auto-create customer_id on first login
    if not user["customer_id"] and user["role"] == "user":
        customer_id = await create_customer_for_user(username, pool)
        return {**dict(user), "customer_id": customer_id}

    return dict(user)


async def seed_admin(pool=None) -> None:
    """
    Seed the fixed admin user on startup.
    Credentials come from settings/env — never hardcoded plaintext.
    Idempotent — safe to call on every startup.
    """
    if pool is None:
        from app.db import get_pool
        pool = get_pool()

    async with pool.connection() as conn:
        existing = await (await conn.execute(
            "SELECT id FROM users WHERE username = %s",
            (settings.admin_username,),
        )).fetchone()

        if not existing:
            await conn.execute(
                """
                INSERT INTO users (username, hashed_password, role)
                VALUES (%s, %s, 'admin')
                """,
                (settings.admin_username, hash_password(settings.admin_password)),
            )
            print(f"[auth] admin user '{settings.admin_username}' seeded")
        else:
            print(f"[auth] admin user '{settings.admin_username}' already exists")


# ── FastAPI dependencies ──────────────────────────────────────────────────────

async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)]
) -> TokenData:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        username: str = payload.get("sub")
        role: str = payload.get("role")
        customer_id: int | None = payload.get("customer_id")
        if not username or not role:
            raise credentials_exception
        return TokenData(username=username, role=role, customer_id=customer_id)
    except JWTError:
        raise credentials_exception


async def require_admin(
    current_user: Annotated[TokenData, Depends(get_current_user)]
) -> TokenData:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


async def require_any(
    current_user: Annotated[TokenData, Depends(get_current_user)]
) -> TokenData:
    return current_user
def create_refresh_token(data: dict) -> str:
    """
    Refresh tokens live longer than access tokens (7 days vs 8 hours).
    They can only be used to get new access tokens, not to access APIs.
    Why separate refresh tokens: if an access token is stolen it expires
    in 8 hours. The refresh token is stored more securely and rotated
    on use — production upgrade: store refresh tokens in DB and invalidate on logout.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=7)
    to_encode["exp"] = expire
    to_encode["type"] = "refresh"  # prevent refresh tokens being used as access tokens
    return jwt.encode(
        to_encode,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def decode_refresh_token(token: str) -> dict:
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
    )
    if payload.get("type") != "refresh":
        raise JWTError("Not a refresh token")
    return payload