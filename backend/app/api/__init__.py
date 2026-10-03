from .anthropic import router as anthropic_router
from .fabrica import router as fabrica_router
from .render import router as render_router
from .requisitos import router as requisitos_router
from .vercel import router as vercel_router

__all__ = [
    "fabrica_router",
    "requisitos_router",
    "vercel_router",
    "render_router",
    "anthropic_router",
]
