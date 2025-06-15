import json
import os
import tempfile
from fastapi import APIRouter, HTTPException
from autobot.schemas import APIKeysRequest, APIKeysResponse

router = APIRouter()

@router.post('/setup', response_model=APIKeysResponse)
async def setup_api_keys(request: APIKeysRequest):
    """
    Configure and store API keys with atomic write to config/api_keys.json
    
    Args:
        request: API keys configuration request
        
    Returns:
        APIKeysResponse: Status of the configuration
    """
    try:
        config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'config')
        os.makedirs(config_dir, exist_ok=True)
        config_file = os.path.join(config_dir, 'api_keys.json')
        
        existing_keys = {}
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                existing_keys = json.load(f)
        
        if request.binance:
            existing_keys['binance'] = {
                'api_key': request.binance.api_key,
                'secret_key': request.binance.api_secret
            }
        
        if request.coinbase:
            existing_keys['coinbase'] = {
                'api_key': request.coinbase.api_key,
                'secret_key': request.coinbase.api_secret
            }
        
        if request.kraken:
            existing_keys['kraken'] = {
                'api_key': request.kraken.api_key,
                'secret_key': request.kraken.api_secret
            }
        
        if request.other:
            for exchange, config in request.other.items():
                if exchange in ['stripe', 'shopify']:
                    existing_keys[exchange] = {
                        'api_key': config.api_key,
                        'secret_key': config.api_secret
                    }
                elif exchange in ['news_api', 'fred', 'alpha_vantage', 'twelve_data']:
                    existing_keys[exchange] = config.api_key
                else:
                    existing_keys[exchange] = {
                        'api_key': config.api_key,
                        'secret_key': config.api_secret
                    }
        
        with tempfile.NamedTemporaryFile(mode='w', dir=config_dir, delete=False, suffix='.tmp') as tmp_file:
            json.dump(existing_keys, tmp_file, indent=2)
            tmp_file_path = tmp_file.name
        
        os.replace(tmp_file_path, config_file)
        
        from autobot.config import load_api_keys
        load_api_keys()
        
        return APIKeysResponse(
            status="ok",
            message="API keys configured successfully"
        )
        
    except Exception as e:
        if 'tmp_file_path' in locals() and os.path.exists(tmp_file_path):
            os.unlink(tmp_file_path)
        raise HTTPException(status_code=500, detail=f"Failed to configure API keys: {str(e)}")
