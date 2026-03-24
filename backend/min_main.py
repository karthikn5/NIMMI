import uvicorn
from fastapi import FastAPI
import os

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Minimal backend is running!", "port": os.environ.get("PORT", 8000)}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
