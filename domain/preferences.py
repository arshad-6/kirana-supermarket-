from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from database.models import OwnerPreference, utcnow

class PreferenceService:
    @staticmethod
    async def get_preference(
        session: AsyncSession,
        key: str,
        owner_id: str = "owner_default",
        default: Optional[str] = None
    ) -> Optional[str]:
        """Fetch preference value by key."""
        stmt = select(OwnerPreference).filter(
            OwnerPreference.owner_id == owner_id,
            OwnerPreference.key == key.strip().lower()
        )
        res = await session.execute(stmt)
        pref = res.scalar_one_or_none()
        return pref.value if pref else default

    @staticmethod
    async def set_preference(
        session: AsyncSession,
        key: str,
        value: str,
        owner_id: str = "owner_default"
    ) -> Dict[str, Any]:
        """Set or update persistent store preference."""
        clean_key = key.strip().lower()
        stmt = select(OwnerPreference).filter(
            OwnerPreference.owner_id == owner_id,
            OwnerPreference.key == clean_key
        )
        res = await session.execute(stmt)
        pref = res.scalar_one_or_none()

        if pref:
            pref.value = value.strip()
            pref.updated_at = utcnow()
        else:
            pref = OwnerPreference(
                owner_id=owner_id,
                key=clean_key,
                value=value.strip()
            )
            session.add(pref)

        await session.commit()
        return {
            "success": True,
            "key": pref.key,
            "value": pref.value
        }

    @staticmethod
    async def list_preferences(
        session: AsyncSession,
        owner_id: str = "owner_default"
    ) -> Dict[str, str]:
        """Return all persistent store preferences for owner."""
        stmt = select(OwnerPreference).filter(OwnerPreference.owner_id == owner_id)
        res = await session.execute(stmt)
        prefs = res.scalars().all()
        return {p.key: p.value for p in prefs}
