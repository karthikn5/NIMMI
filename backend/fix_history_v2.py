import asyncio
from database import async_session
from models import Transaction
from sqlalchemy.future import select

async def fix_history():
    user_id = "6e4b4b88-ce6d-4d49-a27e-eeaceaf8ccd6"
    async with async_session() as db:
        result = await db.execute(select(Transaction).where(Transaction.user_id == user_id))
        transactions = result.scalars().all()
        
        for tx in transactions:
            if tx.amount == 99 or tx.amount == 499 or tx.amount == 999:
                if tx.status != "success":
                    print(f"Fixing transaction {tx.id} to success")
                    tx.status = "success"
        
        await db.commit()
        print("Database updated.")

if __name__ == "__main__":
    asyncio.run(fix_history())
