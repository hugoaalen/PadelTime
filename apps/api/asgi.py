"""Explicit ASGI callable for Vercel Services; imports no local lifespan worker."""
from padeltime.cloud import app as cloud_app


async def app(scope, receive, send):
    await cloud_app(scope, receive, send)
