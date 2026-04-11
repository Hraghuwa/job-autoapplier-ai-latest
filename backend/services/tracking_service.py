from typing import Any, Dict, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.application import Application, ApplicationStatus

class TrackingService:
    async def log_event(
        self, 
        db: AsyncSession, 
        application: Application, 
        event_type: str, 
        message: str, 
        data: Optional[Dict[str, Any]] = None
    ):
        """
        Adds an event to the application history log.
        """
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "type": event_type,
            "message": message,
            "data": data or {}
        }
        
        if application.history is None:
            application.history = []
            
        # Append to history
        application.history.append(event)
        
        # Ensure SQLAlchemy detects the change in the JSON field
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(application, "history")
        
    async def update_status(
        self, 
        db: AsyncSession, 
        application: Application, 
        new_status: ApplicationStatus, 
        reason: str = ""
    ):
        """
        Updates the status of an application and logs the transition.
        """
        old_status = application.status
        application.status = new_status
        
        await self.log_event(
            db, 
            application, 
            "status_change", 
            f"Status changed from {old_status} to {new_status}",
            {"old_status": str(old_status), "new_status": str(new_status), "reason": reason}
        )

tracking_service = TrackingService()
