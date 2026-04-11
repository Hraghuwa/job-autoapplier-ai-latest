from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict, Any

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.models.user import User
from backend.models.application import Application
from backend.models.profile import UserProfile
from backend.models.graph import GraphNodePosition
from backend.schemas.graph import PositionsUpdate
from backend.services.graph_service import graph_service

router = APIRouter()

@router.get("")
async def get_knowledge_graph(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # 1. Fetch User Profile
    res_prof = await db.execute(select(UserProfile).where(UserProfile.user_id == user.id))
    profile = res_prof.scalar_one_or_none()
    
    # 2. Fetch Applications
    res_apps = await db.execute(select(Application).where(Application.user_id == user.id))
    applications = res_apps.scalars().all()
    
    # 3. Fetch Stored Positions
    res_pos = await db.execute(select(GraphNodePosition).where(GraphNodePosition.user_id == user.id))
    stored_positions = {p.node_id: {"x": p.x, "y": p.y} for p in res_pos.scalars().all()}
    
    # 4. Generate Graph
    try:
        graph_data = await graph_service.generate_user_job_graph(user.id, list(applications), profile)
        
        # Merge stored positions
        for node in graph_data.get("nodes", []):
            if node["id"] in stored_positions:
                node["position"] = stored_positions[node["id"]]
                
        return graph_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate knowledge graph: {str(e)}")

@router.get("/stats")
async def get_graph_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Basic summary of entities for the dashboard
    res_apps = await db.execute(select(Application).where(Application.user_id == user.id))
    apps = res_apps.scalars().all()
    
    companies = set(app.company for app in apps)
    skills = set()
    for app in apps:
        if app.matched_skills:
            skills.update(app.matched_skills)
        if app.missing_skills:
            skills.update(app.missing_skills)
            
    return {
        "entity_counts": {
            "applications": len(apps),
            "companies": len(companies),
            "skills": len(skills)
        }
    }

@router.put("/positions")
async def update_node_positions(
    update: PositionsUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Saves custom layout coordinates for graph nodes."""
    for pos in update.positions:
        # Check if exists
        res = await db.execute(
            select(GraphNodePosition).where(
                GraphNodePosition.user_id == user.id,
                GraphNodePosition.node_id == pos.node_id
            )
        )
        existing = res.scalar_one_or_none()
        
        if existing:
            existing.x = pos.x
            existing.y = pos.y
        else:
            db.add(GraphNodePosition(
                user_id=user.id,
                node_id=pos.node_id,
                x=pos.x,
                y=pos.y
            ))
            
    await db.commit()
    return {"status": "success"}


@router.delete("/positions")
async def reset_positions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete all saved node positions so the graph resets to auto-layout."""
    from sqlalchemy import delete
    await db.execute(
        delete(GraphNodePosition).where(GraphNodePosition.user_id == user.id)
    )
    await db.commit()
    return {"status": "success"}
