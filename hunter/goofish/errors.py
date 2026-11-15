"""传输层异常：把闲鱼的各种 ret 归成四种可处理的情况。"""
from __future__ import annotations


class GoofishError(Exception):
    """所有传输层异常的基类。"""


class LoginRequired(GoofishError):
    """登录态失效，需要重新扫码。"""


class RiskControl(GoofishError):
    """触发闲鱼风控（滑块/验证/限流），继续跑只会更糟，必须停下来。"""


class TokenExpired(GoofishError):
    """mtop token 过期，通常刷新页面即可自愈。"""


class ApiError(GoofishError):
    """业务错误（参数不对、商品下架等），重试没有意义。"""
