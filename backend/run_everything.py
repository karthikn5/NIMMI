import asyncio
import os
import subprocess
import sys

# Ensure we are in the backend directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

async def main():
    print("--- 🚀 STARTING FINAL MIGRATION & BACKEND ---")
    
    # 1. Run Migration
    print("Step 1: Running Full Migration...")
    try:
        from full_migrate import run_migration
        await run_migration()
    except Exception as e:
        print(f"Migration Error: {e}")
        # Continue anyway to try starting server
        
    print("Step 2: Starting Uvicorn Server on port 8000...")
    # 2. Start Uvicorn
    # We use subprocess.Popen so it doesn't block this script
    cmd = [sys.executable, "-m", "uvicorn", "main:app", "--reload", "--port", "8000", "--host", "0.0.0.0"]
    process = subprocess.Popen(cmd)
    
    print(f"--- ✅ Backend is starting! PID: {process.pid} ---")
    print("Check your dashboard in 10 seconds.")

if __name__ == "__main__":
    asyncio.run(main())
