"""老人档案、家属绑定与授权同意书。"""

from .schemas import (
    BindingCreate,
    BindingOut,
    BindingWithElderOut,
    ConsentCreate,
    ConsentOut,
    ElderCreate,
    ElderOut,
    ElderUpdate,
)
from .service import ElderService

__all__ = [
    "BindingCreate",
    "BindingOut",
    "BindingWithElderOut",
    "ConsentCreate",
    "ConsentOut",
    "ElderCreate",
    "ElderOut",
    "ElderService",
    "ElderUpdate",
]
