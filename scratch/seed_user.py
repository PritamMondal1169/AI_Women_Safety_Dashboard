import asyncio
from coordinator.database import async_session
from coordinator.models import User
from coordinator.auth import hash_password

async def seed():
    async with async_session() as db:
        # Create test user
        user = User(
            email="user@example.com",
            name="Test User",
            phone="1234567890",
            hashed_password=hash_password("password"),
        )
        db.add(user)
        try:
            await db.commit()
            print("Successfully seeded test user: user@example.com / password")
        except Exception as e:
            print(f"Error seeding user (maybe already exists?): {e}")

if __name__ == "__main__":
    asyncio.run(seed())
