import asyncio
import uuid
from database import async_session
from models import Transaction, UserUsage
from sqlalchemy.future import select

async def check_transactions():
    user_id = "6e4b4b88-ce6d-4d49-a27e-eeaceaf8ccd6"
    async with async_session() as db:
        # Check transactions
        result = await db.execute(select(Transaction).where(Transaction.user_id == user_id))
        transactions = result.scalars().all()
        print(f"--- Transactions for {user_id} ---")
        for tx in transactions:
            print(f"ID: {tx.id}, Plan: {tx.plan_name}, Status: {tx.status}, Amount: {tx.amount}")
            
            # If it's a 99 plan and pending, let's fix it for the user
            if tx.plan_name == "Starter Plan" and tx.status != "success":
                print(f"Found pending transaction. Fixing it...")
                tx.status = "success"
        
        # Check usage
        usage_res = await db.execute(select(UserUsage).where(UserUsage.user_id == user_id))
        usage = usage_res.scalars().first()
        if usage:
            print(f"--- Usage ---")
            print(f"Total: {usage.total_credits}, Used: {usage.used_credits}")
            
        await db.commit()
        print("Done.")

if __name__ == "__main__":
    asyncio.run(check_transactions())
