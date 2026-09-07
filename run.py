import uvicorn
import asyncio
from config import settings

import sys
sys.stdout.reconfigure(encoding="utf-8")

def main():
    print("==================================================")
    print(f"Starting {settings.APP_NAME}")
    print(f"Store: {settings.STORE_NAME} ({settings.STORE_GSTIN})")
    print(f"URL: http://{settings.HOST}:{settings.PORT}")
    print("==================================================")
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True
    )

if __name__ == "__main__":
    main()
