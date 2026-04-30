"""
Vercel entry point — wraps the FastAPI app with Mangum (ASGI → Lambda adapter).
"""
from main import app
from mangum import Mangum

handler = Mangum(app, lifespan="off")
