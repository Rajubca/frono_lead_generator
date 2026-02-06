from fastapi import APIRouter, HTTPException, Depends, Header, status
from admin.config_manager import ConfigManager
import os

# Create the router
admin_router = APIRouter(prefix="/admin", tags=["Admin"])

# Security: Define your key (ideally in config.py or .env)
ADMIN_SECRET_KEY = os.getenv("ADMIN_API_KEY", "your-secure-key-123")

# Updated verify_admin in routes.py
async def verify_admin(x_api_key: str = Header(None)):
    print(f"DEBUG: Received API Key: {x_api_key}") # Add this to debug 401s
    if x_api_key != ADMIN_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Admin API Key"
        )
    return True

@admin_router.get("/settings")
def get_all_configs(authorized: bool = Depends(verify_admin)):
    """Refreshes and returns the current bot configuration."""
    ConfigManager._refresh_cache()
    return ConfigManager._cache

@admin_router.post("/settings/update")
def update_config(key: str, value: str, authorized: bool = Depends(verify_admin)):
    """Updates a specific configuration setting in OpenSearch."""
    try:
        # Convert numeric strings to actual integers for scoring logic
        if value.isdigit():
            value = int(value)
            
        ConfigManager.update_setting(key, value)
        return {"status": "success", "updated": key, "new_value": value}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Update failed: {str(e)}")