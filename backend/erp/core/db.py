from motor.motor_asyncio import AsyncIOMotorClient
from erp.core import config

client = AsyncIOMotorClient(config.MONGO_URL)
db = client[config.DB_NAME]
