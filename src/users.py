import uuid
import secrets

from fastapi_users.password import PasswordHelper
from fastapi import Depends, Request, HTTPException
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin, models
from fastapi_users.authentication import (
    
    AuthenticationBackend,
    CookieTransport,
    JWTStrategy,
)
from fastapi_users.db import SQLAlchemyUserDatabase

from src.db import User, get_user_db

SECRET = secrets.token_urlsafe(32)

class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    
    reset_password_token_secret = SECRET
        
    verification_token_secret = SECRET

    
async def on_after_register(self, user: User, request: Request | None = None):
        
    print(f"User {user.id} has registered.")

    
async def on_after_forgot_password(
        
    self, user: User, token: str, request: Request | None = None
    
    ):
    print(f"User {user.id} has forgot their password. Reset token: {token}")

async def simple_reset_password(self, email: str, new_password: str):
        """
        сбрасывает пароль пользователя по email без проверки токена.
        """
        # поиск пользователя по email
        user = await self.get_by_email(email)
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # хеширование нового пароля
        password_helper = PasswordHelper()
        hashed_password = password_helper.hash(new_password)
        
        # обновление пароля в базе данных
        user.hashed_password = hashed_password
        await self.user_db.update(user)
        
        print(f"✅ Password reset for user {user.email} (ID: {user.id})")
        
        return {"message": f"Password reset successfully for {user.email}"}
    
async def on_after_request_verify(
        
    self, user: User, token: str, request: Request | None = None
        
    ):
            
    print(f"Verification requested for user {user.id}. Verification token: {token}")


async def get_user_manager(user_db: SQLAlchemyUserDatabase = Depends(get_user_db)):
    
    yield UserManager(user_db)

cookie_transport = CookieTransport(
    cookie_max_age=3600,
    cookie_httponly=True,
    cookie_samesite='lax')

def get_jwt_strategy() -> JWTStrategy[models.UP, models.ID]:
    
    return JWTStrategy(secret=SECRET, lifetime_seconds=3600)


auth_backend = AuthenticationBackend(
    
name="jwt",  
transport=cookie_transport,  
get_strategy=get_jwt_strategy,
)

'''Создает все эндпоинты для авторизации (/auth/jwt/login, /auth/register, и т.д.)

Управляет сессиями пользователей

Обрабатывает регистрацию, вход, выход'''

fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])

current_active_user = fastapi_users.current_user(active=True)