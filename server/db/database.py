import asyncpg

from server.config import DATABASE_URL


class Database:
    def __init__(self):
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self.pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)

    async def disconnect(self) -> None:
        if self.pool:
            await self.pool.close()

    async def save_avatar(self, avatar: dict) -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO avatars (username, skin_color, hair, beard, glasses, clothes, accessory)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (username) DO UPDATE SET
                    skin_color = EXCLUDED.skin_color,
                    hair = EXCLUDED.hair,
                    beard = EXCLUDED.beard,
                    glasses = EXCLUDED.glasses,
                    clothes = EXCLUDED.clothes,
                    accessory = EXCLUDED.accessory,
                    updated_at = NOW()
                """,
                avatar["username"],
                avatar["skinColor"],
                avatar["hair"],
                avatar["beard"],
                avatar["glasses"],
                avatar["clothes"],
                avatar["accessory"],
            )

    async def get_avatar(self, username: str) -> dict | None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM avatars WHERE username = $1",
                username,
            )
        if not row:
            return None
        return {
            "username": row["username"],
            "skinColor": row["skin_color"],
            "hair": row["hair"],
            "beard": row["beard"],
            "glasses": row["glasses"],
            "clothes": row["clothes"],
            "accessory": row["accessory"],
        }

    async def save_message(self, message: dict, room_id: str = "lobby") -> None:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO messages (id, room_id, sender_id, sender_name, text, type, recipient_id, timestamp_ms)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (id) DO NOTHING
                """,
                message["id"],
                room_id,
                message["senderId"],
                message["senderName"],
                message["text"],
                message["type"],
                message.get("recipientId"),
                message["timestamp"],
            )

    async def get_recent_messages(self, room_id: str = "lobby", limit: int = 50) -> list[dict]:
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, sender_id, sender_name, text, type, recipient_id, timestamp_ms
                FROM messages
                WHERE room_id = $1
                ORDER BY timestamp_ms DESC
                LIMIT $2
                """,
                room_id,
                limit,
            )
        return [
            {
                "id": row["id"],
                "senderId": row["sender_id"],
                "senderName": row["sender_name"],
                "text": row["text"],
                "type": row["type"],
                "recipientId": row["recipient_id"],
                "timestamp": row["timestamp_ms"],
            }
            for row in reversed(rows)
        ]
