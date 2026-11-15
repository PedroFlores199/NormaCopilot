import asyncio
from app.main import retriever,update_corpus

async def run():
    await retriever.open()
    try:
        print("Passages indexed:",await update_corpus())
    finally:
        await retriever.pool.close()

if __name__ == "__main__":
    asyncio.run(run())
