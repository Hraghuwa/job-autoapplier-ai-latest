from typing import List, Dict, Any
import networkx as nx
from backend.models.application import Application
from backend.models.profile import UserProfile
import json

class GraphService:
    def __init__(self):
        self.graph = nx.Graph()

    async def generate_user_job_graph(self, user_id: str, applications: List[Application], profile: UserProfile) -> Dict[str, Any]:
        """
        Generates a graph representing the user's skills and their relationship to applied jobs.
        """
        G = nx.Graph()
        
        # 1. User Node
        G.add_node("user", label="You", type="user", color="#4f46e5")
        
        # 2. Add Skills from Profile
        skills = []
        if profile and profile.extracted_data:
            # Assuming extracted_data has a 'skills' key
            skills = profile.extracted_data.get("skills", [])
            for skill in skills:
                G.add_node(f"skill:{skill}", label=skill, type="skill", color="#10b981")
                G.add_edge("user", f"skill:{skill}", weight=1.0)
        
        # 3. Add Jobs and Companies
        for app in applications:
            job_node = f"job:{app.id}"
            G.add_node(job_node, label=app.job_title, type="job", color="#f59e0b", status=app.status)
            
            company_node = f"company:{app.company}"
            G.add_node(company_node, label=app.company, type="company", color="#ef4444")
            
            # Relation: Job belongs to Company
            G.add_edge(job_node, company_node, type="belongs_to")
            
            # Relation: User applied to Job
            G.add_edge("user", job_node, type="applied", status=app.status)
            
            # 4. Link Jobs to Skills
            # Assuming app.matched_skills and app.missing_skills exist
            matched = app.matched_skills or []
            missing = app.missing_skills or []
            
            for skill in matched:
                skill_node = f"skill:{skill}"
                if not G.has_node(skill_node):
                    G.add_node(skill_node, label=skill, type="skill", color="#10b981")
                G.add_edge(job_node, skill_node, type="matched", weight=1.2)
                
            for skill in missing:
                skill_node = f"skill:{skill}"
                if not G.has_node(skill_node):
                    G.add_node(skill_node, label=skill, type="skill", color="#94a3b8") # Grey for missing
                G.add_edge(job_node, skill_node, type="missing", weight=0.8)

        # Calculate positions using networkx spring layout
        # scale=500 to spread them out for ReactFlow
        pos = nx.spring_layout(G, k=1.0, iterations=50, seed=42)
        
        # Convert to serialized format for frontend (Nodes and Edges)
        nodes = []
        for n, d in G.nodes(data=True):
            # Scale positions to a reasonable range for the canvas
            node_pos = pos.get(n, [0, 0])
            
            node = {
                "id": n, 
                "data": {
                    "label": d.get("label", n),
                    "type": d.get("type", "default"),
                    "status": d.get("status", "")
                }, 
                "type": d.get("type", "default"),
                "position": {"x": float(node_pos[0] * 800), "y": float(node_pos[1] * 800)}
            }
            # Include other attributes (color, etc)
            node.update({k: v for k, v in d.items() if k not in ["label", "type", "status"]})
            nodes.append(node)
            
        edges = []
        for u, v, d in G.edges(data=True):
            edge_type = d.get("type", "")
            edges.append({
                "id": f"e-{u}-{v}",
                "source": u,
                "target": v,
                "label": edge_type,
                "animated": edge_type in ["applied", "scanning"],
                "data": {"type": edge_type},
                "style": {
                    "stroke": "#10b981" if edge_type == "matched" else "#94a3b8",
                    "strokeWidth": 2 if edge_type == "matched" else 1,
                    "opacity": 0.8
                }
            })
            
        return {"nodes": nodes, "edges": edges}

graph_service = GraphService()
