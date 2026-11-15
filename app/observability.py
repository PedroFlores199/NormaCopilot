from contextlib import nullcontext
from functools import lru_cache
from langfuse import Langfuse
from .config import settings


@lru_cache
def client():
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        return None
    return Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        base_url=settings.langfuse_base_url,
    )


def observation(name, kind="span", **kwargs):
    lf = client()
    return (
        lf.start_as_current_observation(name=name, as_type=kind, **kwargs)
        if lf
        else nullcontext()
    )
