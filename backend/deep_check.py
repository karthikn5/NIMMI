import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
USER_ID = "6e4b4b88-ce6d-4d49-a27e-eeaceaf8ccd6"

async def check_full_data():
    engine = create_async_engine(DATABASE_URL)
    async with engine.connect() as conn:
        print(f"--- Data for User: {USER_ID} ---")
        
        # Bots
        result = await conn.execute(
            text("SELECT bot_id, bot_name, export_unlocked FROM bots WHERE user_id = :uid"),
            {"uid": USER_ID}
        )
        bots = result.fetchall()
        print(f"\nBots ({len(bots)}):")
        for b in bots:
            print(f"  ID: {b[0]}, Name: {b[1]}, Unlocked: {b[2]}")
            
        # Subscriptions
        result = await conn.execute(
            text("SELECT id, bot_id, plan_name, end_date, status FROM subscriptions WHERE user_id = :uid"),
            {"uid": USER_ID}
        )
        subs = result.fetchall()
        print(f"\nSubscriptions ({len(subs)}):")
        for s in subs:
            print(f"  ID: {s[0]}, Bot: {s[1]}, Plan: {s[2]}, End: {s[3]}, Status: {s[4]}")
            
        # Transactions
        result = await conn.execute(
            text("SELECT id, bot_id, amount, status FROM transactions WHERE user_id = :uid"),
            {"uid": USER_ID}
        )
        txs = result.fetchall()
        print(f"\nTransactions ({len(txs)}):")
        for t in txs:
            print(f"  ID: {t[0]}, Bot: {t[1]}, Amt: {t[2]}, Status: {t[3]}")
            
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check_full_data())
