"""
轻量级认证模块 - 仅用于 JWT token 验证
不依赖 quantFinance，避免引入过多依赖
"""

import os
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional

# JWT 配置（应与 quantFinance 保持一致）
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"

security = HTTPBearer()


async def get_current_active_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """
    验证 JWT token 并返回用户信息
    
    这是一个轻量级实现，只验证 token 有效性，不访问数据库
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # 解码 JWT token
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        user_id: str = payload.get("user_id")  # 如果 token 中包含 user_id
        
        print(f"[simple_auth] Token decoded: username={username}, user_id={user_id}")
        
        if username is None:
            raise credentials_exception
        
        # 返回用户信息（从 token 中提取，不查询数据库）
        return {
            "id": user_id or username,  # 使用 user_id 或 username
            "username": username,
            "is_active": True
        }
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.JWTError:
        raise credentials_exception
